# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
import os
import sys
import anyblok
from anyblok.config import Configuration
import logging
from cProfile import Profile
from multiprocessing import Process
from multiprocessing import Event
from multiprocessing import Queue
from sqlalchemy import func
from contextlib import contextmanager

logger = logging.getLogger('multi')

DEFAULT_ISOLATION = 'REPEATABLE READ'  # 'SERIALIZABLE'

orch_workers_ready = Event()
"""Acknowledgement by the orchestrator that all regular workers are ready.
"""
orch_timeslice_finished = Event()
"""Event to tell regular workers that all of them have finished the timeslice.
"""

orch_timeslice_started = Event()
"""Event to tell workers that the timeslice has started for all of them.

This event is useful to know when to clear (reset)
``orch_timeslice_finished`` and to avoid a fast worker to wait on it before
it's been cleared.
"""

orch_stop_all = Event()
"""Event sent by the orchestrator to make all processes stop."""

workers_feedback = Queue()
"""Queue for workers to notify orchestrator of their progress."""

# message types
REGULAR_READY = 0
WORKER_TIMESLICE_START = 1
WORKER_TIMESLICE_DONE = 2
WORKER_FINISHED = 3


def dump_profile(profile, path_template, wtype='regular'):
    """Dump profile statistics in file

    The final file path is derived from path_template, wtype and the pid
    """
    base_path, ext = os.path.splitext(path_template)
    path = '%s_%s_%s' % (base_path, wtype, os.getpid()) + ext
    try:
        from pyprof2calltree import convert
    except ImportError:
        profile.dump_stats(path)
    else:
        convert(profile.getstats(), path + '.kgrind')


def start_registry(isolation_level):
    """Analog of anyblok.start(), with Configuration already loaded.

    Calling ``anyblok.start()`` from a worker process while the main
    process has already consumed command line arguments before forking
    results in an empty configuration, which can't work at all
    """

    from anyblok.blok import BlokManager
    from anyblok.registry import RegistryManager
    BlokManager.load()
    return RegistryManager.get(Configuration.get('db_name'),
                               isolation_level=isolation_level,
                               loadwithoutmigration=True)


def orchestrator():
    """Processs to orchestrate regular workers in timeslices.

    The current implementation uses events for each worker.
    It doesn't matter in which order we wait for the workers events :
    if one is triggered while we wait for another, the wait time of the first
    will be zero. In other words, event waits are commutative.
    """

    logger = logging.getLogger(__name__ + '.orchestrator')
    workers = {}

    while len(workers) < Configuration.get('regular_workers'):
        msg = workers_feedback.get()  # TODO timeout ?
        if msg[0] != REGULAR_READY:
            logger.warning("While waiting for workers to be ready, "
                           "got invalid message in queue: %r", msg)
            continue
        wid = msg[1]
        logger.info("Registered Regular Worker with id=%d", wid)
        workers[wid] = dict()

    logger.info("All workers are ready.""")
    orch_workers_ready.set()
    tsl = 0
    while workers:
        msg = workers_feedback.get()
        logger.debug("Got message in queue: %r", msg)
        mtype, wid = msg[:2]
        if wid not in workers:
            logger.warning(
                "Got and ignored message about unknown worker id %d. ", wid)
            continue
        if mtype == WORKER_TIMESLICE_START:
            workers[wid]['timeslice_status'] = 'running'
            logger.info("Timeslice start for worker id=%d", wid)
            if all(w.get('timeslice_status') == 'running'
                   for w in workers.values()):
                logger.info("Timeslice started for all workers, preparing "
                            "end event")
                orch_timeslice_finished.clear()
                logger.info("Sending global timeslice start event")
                orch_timeslice_started.set()
        elif mtype == WORKER_TIMESLICE_DONE:
            workers[wid]['timeslice_status'] = 'done'
            logger.info("Timeslice done for worker id=%d", wid)
            if all(w.get('timeslice_status') == 'done'
                   for w in workers.values()):
                tsl += 1
                logger.info("Timeslice %d done for all workers, preparing "
                            "start event", tsl)
                orch_timeslice_started.clear()
                logger.info("Sending global timeslice finished event")
                orch_timeslice_finished.set()
        elif mtype == WORKER_FINISHED:
            logger.info("Worker id=%d has done all timeslices. "
                        "Stop tracking it", wid)
            del workers[wid]
    orch_stop_all.set()


@contextmanager
def worker_timeslice(logger, wid):
    """Context manager to encapsulate work in a timeslice."""
    logger.info("(id=%d), sending timeslice start message", wid)
    workers_feedback.put((WORKER_TIMESLICE_START, wid))
    # wait for orchestrator to acknowledge start on all workers
    # so that we are sure that at the end we won't wait for previous
    # timeslice end event
    orch_timeslice_started.wait()
    yield

    logger.info("(id=%d), sending timeslice done message", wid)
    workers_feedback.put((WORKER_TIMESLICE_DONE, wid))

    logger.info("(id=%d), waiting for global end of timeslice", wid)
    orch_timeslice_finished.wait()

    logger.info("(id=%d), timeslice globally finished", wid)


def regular_worker():
    logger = logging.getLogger(__name__ + '.regular_worker')
    registry = start_registry(DEFAULT_ISOLATION)
    if registry is None:
        logger.critical("Couldn't init registry")
        sys.exit(1)

    Worker = registry.Wms.Worker.Regular
    previous_run_timeslice = Worker.query(
        func.max(Worker.done_timeslice)).first()[0]
    if previous_run_timeslice is None:
        previous_run_timeslice = 0

    timeslices = Configuration.get('timeslices')
    process = Worker.insert(
        pid=os.getpid(),
        active=True,
        done_timeslice=previous_run_timeslice,
        max_timeslice=previous_run_timeslice + timeslices,
        )
    wid = process.id
    registry.commit()
    workers_feedback.put((REGULAR_READY, wid))

    logger.info("(id=%d), waiting for orchestrator "
                "to register all workers.",  wid)
    orch_workers_ready.wait()

    with_profile = Configuration.get('with_profile')

    if with_profile:
        profile = Profile()
        profile.enable()
    for i in range(timeslices):
        try:
            with worker_timeslice(logger, wid):
                process.run_timeslice()
        except Exception:
            logger.exception("Uncatched exception in main loop")
        except KeyboardInterrupt:
            process.stop()
            break
    registry.commit()
    logger.warn("(id=%d), all timeslices done. Starting end sequence", wid)
    process.stop()
    workers_feedback.put((WORKER_FINISHED, wid))
    if with_profile:
        logger.info("Producing profiling statistics")
        profile.disable()
        dump_profile(profile, Configuration.get('profile_file'))


def continuous(wtype,
               isolation_level=DEFAULT_ISOLATION, cleanup=False):
    """Start a continuous worker.

    :param bool cleanup: if ``True`` remove all existing records of
                         the same worker type. They are considered stale
                         from previous runs.
    """
    registry = start_registry(isolation_level)
    if registry is None:
        logging.critical("continuous worker(type=%s): couldn't init registry",
                         wtype)
        sys.exit(1)

    Worker = getattr(registry.Wms.Worker, wtype)
    if cleanup:
        logger.info("Cleaning up any stale %s record due to previous runs",
                    Worker.__registry_name__)
        Worker.query().delete()
        registry.commit()

    pid = os.getpid()
    process = Worker.insert(pid=pid)
    registry.commit()

    # as the continuous workers uses the status of the regular workers to
    # know when to stop, it has to wait for them to be ready before actually
    # starting
    logger.info("Waiting for the regular workers to be ready.")
    orch_workers_ready.wait()

    def should_proceed():
        if not orch_stop_all.is_set():
            return True
        logger.info("%s(pid=%d) got the stop_all signal from orchestrator",
                    wtype, pid)

    process.should_proceed = should_proceed

    with_profile = Configuration.get('with_profile')
    if with_profile:
        profile = Profile()
        profile.enable()
    process.run()
    if with_profile:
        profile.disable()
        dump_profile(profile, Configuration.get('profile_file'), wtype=wtype)


def reserver():
    return continuous('Reserver', cleanup=True)


def planner(number):
    return continuous('Planner', cleanup=(number == 0))


def run():
    anyblok.load_init_function_from_entry_points()
    Configuration.load('wms-bench')

    regular = Configuration.get('regular_workers')
    planners = Configuration.get('planner_workers')
    print("Starting example/bench for {timeslices} time slices, "
          "with {regular} regular workers and "
          "{planners} planners\n\n".format(
              regular=regular, planners=planners,
              timeslices=Configuration.get('timeslices')))

    # starting regular workers right away, otherwise continuous workers
    # would believe the test/bench run is already finished.
    processes = [Process(target=orchestrator), Process(target=reserver)]
    processes.extend(Process(target=regular_worker) for i in range(regular))
    processes.extend(Process(target=planner, args=(i, ))
                     for i in range(planners))
    for process in processes:
        process.start()
