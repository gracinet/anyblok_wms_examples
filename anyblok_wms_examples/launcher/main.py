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
import logging
import time
from multiprocessing import Process
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from sqlalchemy import func


logger = logging.getLogger('multi')

DEFAULT_ISOLATION = 'REPEATABLE READ'  # 'SERIALIZABLE'


def regular_worker(arguments):
    registry = anyblok.start('basic', configuration_groups=[],
                             loadwithoutmigration=True,
                             isolation_level=DEFAULT_ISOLATION)
    if registry is None:
        logging.critical("regular_worker: couldn't init registry")
        sys.exit(1)

    Worker = registry.Wms.Worker.Regular
    previous_run_timeslice = Worker.query(
        func.max(Worker.done_timeslice)).first()[0]
    if previous_run_timeslice is None:
        previous_run_timeslice = 0

    timeslices = arguments.timeslices
    process = Worker.insert(
        pid=os.getpid(),
        active=True,
        done_timeslice=previous_run_timeslice,
        max_timeslice=previous_run_timeslice + timeslices,
        )

    for i in range(1, 1 + timeslices):
        registry.commit()
        try:
            process.run_timeslice()
        except KeyboardInterrupt:
            process.stop()
            break
        process.wait_others(i)
    registry.commit()


def continuous(wtype, arguments,
               isolation_level=DEFAULT_ISOLATION, cleanup=False):
    """Start a continuous worker.

    :param bool cleanup: if ``True`` remove all existing records of
                         the same worker type. They are considered stale
                         from previous runs.
    """
    registry = anyblok.start('basic', configuration_groups=[],
                             loadwithoutmigration=True,
                             isolation_level=DEFAULT_ISOLATION)
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

    process.run()


def reserver(arguments):
    return continuous('Reserver', arguments, cleanup=True)


def planner(number, arguments):
    return continuous('Planner', arguments, cleanup=(number == 0))


class Arguments:
    pass


def run():
    parser = ArgumentParser(
        description="Run the application in pure batch mode",
        formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--timeslices", type=int, default=10,
                        help="Number of time slices to run")
    parser.add_argument("--planner-workers", type=int, default=2,
                        help="Number of planner worker processes to run")
    parser.add_argument("--regular-workers", type=int, default=4,
                        help="Number of regular worker processes to run. "
                        "in a normal application, these would be the ones "
                        "reacting to external events (bus, HTTP requests)")

    logging.basicConfig(level=logging.INFO)
#    arguments = parser.parse_args()
    arguments = Arguments()
    arguments.regular_workers = 4
    arguments.timeslices = 10
    arguments.planner_workers = 2

    # starting regular workers right away, otherwise continuous workers
    # would believe the test/bench run is already finished.
    for process in (Process(target=regular_worker, args=(arguments, ))
                    for i in range(arguments.regular_workers)):
        process.start()

    Process(target=reserver, args=(arguments, )).start()

    planners = [Process(target=planner, args=(i, arguments, ))
                for i in range(arguments.planner_workers)]
    for process in planners:
        process.start()
