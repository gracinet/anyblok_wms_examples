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
        later. Probably also needs to be optimized.

        since we only have incoming and stock locations, all of them
        hold potentially sellable product.
        """
        return """
            SELECT product FROM (
               SELECT goods_type.product, SUM(COALESCE(count, 0)) AS level
               FROM wms_goods_type goods_type
               LEFT JOIN (
                  SELECT type_id, count(*)
                  FROM wms_goods goods,
                       wms_goods_avatar avatar
                  WHERE avatar.state IN ('present', 'future')
                  AND avatar.dt_until IS NULL
                  AND avatar.goods_id = goods.id
                  GROUP BY goods.type_id
                  ) AS per_type
               ON per_type.type_id = goods_type.id
               GROUP BY goods_type.product
               ) AS per_product
            WHERE level = 0
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
        GoodsType = Wms.Goods.Type
        pack_type = GoodsType.query().filter(
            GoodsType.code.in_(pack_codes)).with_for_update(
                skip_locked=True).first()

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

    def process_one(self):
        """Find any Operation that can be done, and execute it."""
        Operation = self.registry.Wms.Operation
        HI = Operation.HistoryInput
        Avatar = self.registry.Wms.Goods.Avatar

        # history/input lines with avatars not in present state
        # TODO UPSTREAM generic query for 'ready' operations.
        subq = HI.query(HI.avatar_id, HI.operation_id).join(
            Avatar, HI.avatar_id == Avatar.id).filter(
                Avatar.state.in_(('future', 'past'))).subquery()

        query = Operation.query().outerjoin(
            subq, subq.c.operation_id == Operation.id).filter(
                subq.c.avatar_id.is_(None),
                Operation.type != 'wms_arrival',
                Operation.state == 'planned').order_by(
                    Operation.id).with_for_update(
                    of=Operation,
                    skip_locked=True)

        op = query.first()
        if op is not None:
            logger.info("Found op ready to be executed: %r, doing it now.",
                        op)
            op.execute()
        return op
