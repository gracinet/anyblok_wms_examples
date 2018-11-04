# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
import time
import sys
import random
import os
import logging
import select

from sqlalchemy.exc import OperationalError
from psycopg2.extensions import TransactionRollbackError

from anyblok import Declarations
from anyblok.column import Integer
from anyblok.column import Boolean

logger = logging.getLogger(__name__)

Model = Declarations.Model
Mixin = Declarations.Mixin
register = Declarations.register
Wms = Model.Wms


@register(Mixin)
class WmsExamplesContinuousWorker:
    """A mixin for workers that always run in the background.

    We could also not represent them in the database, but it's convenient
    to find out about running processes with a simple query.

    Since these have no predefined execution target, they must
    periodically check if regular workers are finished, meaning that
    the bench or test run is done.
    """
    pid = Integer(primary_key=True)
    sleep_interval = 0.01
    """Time to sleep if there's nothing to be done."""
    inactivity_count = 0
    """Number of consecutive times there's been nothing to be done."""
    max_sleep = 1
    """Maximal time to sleep."""

    conflicts = 0

    def __repr__(self):
        return "%s(pid=%d)" % (self.__registry_name__, self.pid)

    @classmethod
    def should_proceed(cls):
        """Return ``False`` iff all regular workers are finished."""
        Regular = cls.registry.Wms.Worker.Regular
        count = Regular.query().filter(Regular.active.is_(True)).count()
        # if another locking txn commits after this first request that
        # inits the mvcc but before our attempts to lock, we'll get a
        # serialization error, because the other txn has released its locks.
        cls.registry.commit()
        if count:
            logger.debug("%s: There are still %d active regular workers. "
                         "Proceeding further", cls.__registry_name__, count)
            return True
        return False

    def maybe_sleep(self, prefix, something_done):
        """If nothing has been done, sleep for a while."""
        logger.debug("%s: maybe_sleep", prefix)
        if something_done:
            self.inactivity_count = 0
        else:
            self.inactivity_count += 1
            sleep = min(self.sleep_interval * self.inactivity_count,
                        self.max_sleep)
            logger.info("%s: nothing to be done at the moment; "
                        "sleeping for %.3f seconds", prefix, sleep)
            time.sleep(sleep)
            # start a new txn, in order to avoid artificially long ones
            self.registry.commit()
            logger.info("%s: waking up", prefix)

    def run(self):
        self_str = str(self)  # can't be done after an error
        while self.should_proceed():
            try:
                # TODO make a bunch instead ?
                something_done = self.process_one(self_str=self_str)
                self.registry.commit()
            except KeyboardInterrupt:
                self.registry.rollback()
                logger.warning("%s: got keyboard interrupt, quitting",
                               self_str)
                return
            except OperationalError as exc:
                if isinstance(exc.orig, TransactionRollbackError):
                    self.conflicts += 1
                    logger.warning("%s: got conflict: %s", self_str, exc)
                else:
                    logger.exception("%s: catched exception in main loop",
                                     self_str)
                self.registry.rollback()
            except:
                logger.exception("%s: got exception in main loop", self_str)
                self.registry.rollback()
            else:
                try:
                    self.maybe_sleep(self_str, something_done)
                except KeyboardInterrupt:
                    logger.warning("%s: got keyboard interrupt, quitting",
                                   self_str)
                    return
        logger.info("%s: No more active regular worker. Stopping there. "
                    "Total number of conflicts: %d",
                    self_str, self.conflicts)


@register(Wms)
class Worker:
    """Just a namespace."""


@register(Wms.Worker)
class Planner(Mixin.WmsExamplesContinuousWorker):

    def process_one(self):
        """Select a full reservation and plan it.

        To be implemented in concrete subclasses
        """


@register(Wms.Worker)
class Reserver(Mixin.WmsExamplesContinuousWorker):

    def process_one(self, self_str=None):
        """Try and perform a reservation.

        To be refined in concrete subclasses
        """
        # TODO this commits, hence the outer loop's commit is redundant
        self.registry.Wms.Reservation.Request.reserve_all(batch_size=1)


@register(Wms.Worker)
class Regular:
    """A regular worker, processing time slices.

    A time slice is the batch operation equivalent of a day's work,
    or if one prefers, a team's shift.
    """
    id = Integer(label="Identifier", primary_key=True)
    pid = Integer()
    done_timeslice = Integer(label="Latest done timeslice",
                             nullable=False,
                             default=0)
    max_timeslice = Integer(label="Greatest timeslice to run")
    active = Boolean()
    sales_per_timeslice = Integer(default=10)

    other = set()

    simulate_sleep = 10

    conflicts = 0
    """Used to report number of database conflicts."""

    def process_one(self):
        """To be implemented by concrete subclasses.

        The default implementation is a stub that simply sleeps for a while.
        """
        time.sleep(random.randrange(self.simulate_sleep)/100.0)
        return False

    def begin_timeslice(self):
        """Do all business logic that has to be done at the timeslice start.
        """

    @property
    def current_timeslice(self):
        done = self.done_timeslice
        if done is None:
            return 1
        return done + 1

    def __str__(self):
        # in tests, id and pid can be None, hence let's avoid %d
        return "Regular Worker (id=%s, pid=%s)" % (self.id, self.pid)

    def stop(self):
        self.registry.rollback()
        self.active = False
        self.registry.commit()
        return

    def run_timeslice(self):
        tsl = self.current_timeslice
        self_str = str(self)
        logger.info("%s, starting timeslice %d", self_str, tsl)
        self.begin_timeslice()
        logger.info("%s, begin sequence for timeslice %d finished, now "
                    "proceeding to normal work", self, tsl)
        # it's important to start with a fresh MVCC snapshot
        # no matter what (especially requests due to logging)
        self.registry.commit()
        proceed = True
        while proceed:
            try:
                op = self.process_one()
                self.registry.commit()
                if op is None:
                    proceed = False
                elif op is not True:
                    logger.info("%s, %s(id=%d) done and committed",
                                self_str, op[0], op[1])
            except KeyboardInterrupt:
                raise
            except OperationalError as exc:
                if isinstance(exc.orig, TransactionRollbackError):
                    self.conflicts += 1
                    logger.warning("%s, got conflict: %s", self_str, exc)
                else:
                    logger.exception("%s, catched exception in main loop",
                                     self_str)
                self.registry.rollback()
            except:
                self.registry.rollback()
                logger.exception("%s, exception in process_one()", self_str)

        self.done_timeslice = tsl
        if tsl == self.max_timeslice:
            self.active = False
        self.registry.commit()
        logger.info("%s, finished timeslice %d. "
                    "Cumulated number of conflicts: %d", self_str, tsl,
                    self.conflicts)
        sys.stderr.flush()
        self.registry.session.execute("NOTIFY timeslice_finished, '%d'" % tsl)
        self.registry.commit()

    def wait_others(self, timeslice):
        self.registry.session.execute("LISTEN timeline_finished")
        while 1:
            self.registry.commit()
            conn = self.registry.session.connection().connection
            if select.select([conn], [], [], self.simulate_sleep) == (
                    [], [], []):
                logger.warning("Timeout in LISTEN")
                if self.all_finished(timeslice):
                    return
            else:
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    logger.debug(
                        "Process %d got end signal for process_id %d, "
                        "timeslice %s", os.getpid(), notify.pid,
                        notify.payload)
                    if self.all_finished(timeslice):
                        return

    def all_finished(self, timeslice):
        cls = self.__class__
        query = cls.query().filter(
            cls.done_timeslice < timeslice, cls.active.is_(True))
        if query.count():
            logger.info("%s: timeslice %d not done yet for %s",
                        self,
                        timeslice, [p.pid for p in query.all()])
            return False
        return True
