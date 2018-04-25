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
import time
from cProfile import Profile
from multiprocessing import Process
from sqlalchemy import func


logger = logging.getLogger('multi')

DEFAULT_ISOLATION = 'REPEATABLE READ'  # 'SERIALIZABLE'


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


def regular_worker():
    registry = start_registry(DEFAULT_ISOLATION)
    if registry is None:
        logging.critical("regular_worker: couldn't init registry")
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

    with_profile = Configuration.get('with_profile')

    if with_profile:
        profile = Profile()
        profile.enable()
    for i in range(1, 1 + timeslices):
        registry.commit()
        try:
            process.run_timeslice()
        except KeyboardInterrupt:
            process.stop()
            break
        process.wait_others(i)
    registry.commit()
    if with_profile:
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

    process = Worker.insert(pid=os.getpid())
    registry.commit()
    while not process.should_proceed():
        logger.info("Regular workers not yet running. Waiting a bit")
        time.sleep(0.1)
        registry.rollback()
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
    for process in (Process(target=regular_worker, args=())
                    for i in range(regular)):
        process.start()

    Process(target=reserver, args=()).start()

    planners = [Process(target=planner, args=(i, ))
                for i in range(planners)]
    for process in planners:
        process.start()
