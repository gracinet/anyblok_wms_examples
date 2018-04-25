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

    def __repr__(self):
        return "%s(pid=%d)" % (self.__registry_name__, self.pid)

    @classmethod
    def should_proceed(cls):
        """Return ``False`` iff all regular workers are finished."""
        Regular = cls.registry.Wms.Worker.Regular
        count = Regular.query().filter(Regular.active.is_(True)).count()
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

    def run(self):
        self_str = str(self)  # can't be done after an error
        while self.should_proceed():
            try:
                # TODO make a bunch instead ?
                something_done = self.process_one()
            except KeyboardInterrupt:
                self.registry.rollback()
                logger.warning("%s: got keyboard interrupt, quitting",
                               self_str)
                return
            except Exception:
                logger.exception("%s: got exception in main loop", self_str)
                self.registry.rollback()
            else:
                self.registry.commit()
                self.maybe_sleep(self_str, something_done)
        logger.info("%s: No more active regular worker. Stopping there.",
                    self_str)


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

    def process_one(self):
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
        return "Regular Worker (id=%d, pid=%d)" % (self.id, self.pid)

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
        proceed = True
        while proceed:
            try:
                proceed = self.process_one() is not None
                self.registry.commit()
            except Exception:
                self.registry.rollback()
                logger.exception("%s, exception in process_one()", self_str)

        self.done_timeslice = tsl
        if tsl == self.max_timeslice:
            self.active = False
        self.registry.commit()
        logger.info("%s, finished timeslice %d", self_str, tsl)
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
