# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
import logging
from datetime import datetime, timedelta

from anyblok import Declarations

logger = logging.getLogger(__name__)

Model = Declarations.Model
Mixin = Declarations.Mixin
register = Declarations.register
Wms = Model.Wms


@register(Wms.Worker)
class Regular(Mixin.WmsBasicSellerUtil):

    @classmethod
    def missing_product_query(cls):
        """A query for product that's entirely missing.

        For now, a pure SQL query, to be converted into proper SQLAlchemy
        later. It is probably more efficient than using the quantity queries
        because the DISTINCT ON avoids fetching all matching avatars.

        since we only have incoming and stock locations, all of them
        hold potentially sellable product.
        """
        return """
        SELECT product FROM (
          SELECT pot2.product,
                 bool_or(COALESCE(has_avatar.has, FALSE)) AS has_some
          FROM wms_physobj_type pot2
          LEFT JOIN (
            SELECT DISTINCT ON (pot.id) pot.id, TRUE AS has
            FROM wms_physobj_type pot
            JOIN wms_physobj po ON pot.id = po.type_id
            JOIN wms_physobj_avatar av ON av.obj_id=po.id
            WHERE av.state IN ('present', 'future')
            AND av.dt_until IS NULL
          ) AS has_avatar
          ON has_avatar.id = pot2.id
          GROUP BY pot2.product
        ) AS by_product
        WHERE has_some IS FALSE
        """.strip()

    def purchase(self):
        """Find a Goods Type with 0 future stock and issue an arrival.

        :rtype: bool
        :return: pack code for which an Arrival is scheduled (was needed),
                 or None (in which case the
                 caller probably wants to stop purchases).
        """
        # TODO make a method upstream for quantity queries grouped by type.
        products = self.registry.execute("\n".join((
            self.missing_product_query(),
            "LIMIT 10"  # TODO use the number of workers or something
            ))).fetchall()
        if not products:
            return False

        pack_codes = [r[0] + '/PCK' for r in products]

        Wms = self.registry.Wms
        GoodsType = Wms.PhysObj.Type
        pack_type = GoodsType.query().filter(
            GoodsType.code.in_(pack_codes)).with_for_update(
                skip_locked=True).first()
        if pack_type is None:
            logger.info("No product missing that isn't taken care of by "
                        "other processes")
            return

        Operation = Wms.Operation
        logger.info("Product whose pack is %r is missing, ordering some",
                    pack_type.code)
        arrival = Operation.Arrival.create(
            goods_type=pack_type,
            location=self.incoming_location,
            timeslice=self.current_timeslice + 2,
            # we don't know how long timeslices actually take, but
            # it doesn't matter
            dt_execution=datetime.now() + timedelta(minutes=10),
        )
        self.reserve_for_unpack(arrival.outcomes[0].goods)
        return pack_type.code

    def reserve_for_unpack(self, pack):
        """Reserve a pack for future unpacking.

        :param pack: ``Wms.Goods`` instance

        The case where Goods records are already there is a simpler one
        (wms-reservation is meant to handle common cases where the Goods
        aren't known before hand, maybe because they don't even exist in
        ``future`` state)
        """
        Reservation = self.registry.Wms.Reservation
        return Reservation.insert(
            goods=pack,
            request_item=Reservation.RequestItem.insert(
                request=Reservation.Request.insert(
                    purpose="unpack", reserved=True),
                goods_type=pack.type,
                quantity=1),
            quantity=1)

    def process_arrival(self):
        Arrival = self.registry.Wms.Operation.Arrival
        arrival = Arrival.query().filter(
            Arrival.state == 'planned',
            Arrival.timeslice <= self.current_timeslice).with_for_update(
                skip_locked=True).first()
        if not arrival:
            return False
        arrival.execute()
        return True

    def begin_timeslice(self):
        self_str = str(self)
        c = 0
        proceed = True
        while proceed:
            try:
                proceed = self.process_arrival()
                c += 1
                self.registry.commit()
            except KeyboardInterrupt:
                raise
            except:
                logger.exception("%s, exception in process_arrival()",
                                 self_str)
                self.registry.rollback()

        logger.info("%s, finished processing arrivals, got %d of them",
                    self_str, c)
        c = 0
        proceed = True
        while proceed:
            try:
                proceed = bool(self.purchase())
                c += 1
                self.registry.commit()
            except KeyboardInterrupt:
                raise
            except:
                logger.exception("%s, exception in purchase()",
                                 self_str)
                self.registry.rollback()

        logger.info("%s, finished issuing purchases (did %d of them)",
                    self_str, c)
        Sale = self.registry.Wms.Example.Sale
        for i in range(self.sales_per_timeslice):
            Sale.create_random()
        logger.info("%s, done issuing client sales", self_str)
        self.registry.commit()

    def planned_op_lock_query(self):
        # this caching helps speeding things up between
        # transaction begin and lock querying, hence reducing conflicts
        # (the MVCC snapshot is supposed to be taken at first query,
        #  but I still can see a few)
        query = getattr(self, '_planned_lock_query', None)
        if query is not None:
            return query
        logger.warning("Lock query not found in cache")
        Operation = self.registry.Wms.Operation
        query = Operation.query(Operation.id).filter(
            Operation.type != 'wms_arrival',
            Operation.state == 'planned').order_by(
                Operation.dt_execution).with_for_update(
                    key_share=True,
                    skip_locked=True)
        self._planned_lock_query = query
        return query

    def select_ready_operation(self):
        """Find an operation ready to be processed (and lock it)

        :return: the operation or None and boolean telling if no operation was
                 found if that's definitive
        """
        Operation = self.registry.Wms.Operation
        # starting with a fresh MVCC snapshot
        self.registry.commit()
        # TODO this is too complicated: locking an op then climbing along
        # the 'follows' relation to find an executable one.
        # it'd be much simpler to look for an Operation whose inputs are
        # all present.
        planned_id = self.planned_op_lock_query().first()
        if planned_id is None:
            return None, True
        planned = Operation.query().get(planned_id)
        previous_planned = True
        while previous_planned:
            previous_planned = [
                op.id for op in planned.follows if op.state == 'planned']
            if not previous_planned:
                break
            planned = Operation.query().filter(
                Operation.id.in_(previous_planned)).with_for_update(
                    key_share=True,
                    skip_locked=True).first()
            if planned is None:
                return None, False
        return planned, None

    def process_one(self):
        """Find any Operation that can be done, and execute it."""
        # first alternative: climbing up planned operations, without
        # complicated outer join to avatars that are conflict sources
        # for PG
        op, stop = self.select_ready_operation()
        if op is None:
            if stop:
                return
            else:
                return True

        logger.info("%s, found op ready to be executed: %r, doing it now.",
                    self, op)
        op.execute()
        # returning op info instead of instance to avoid any
        # after-commit query
        return op.__registry_name__, op.id
