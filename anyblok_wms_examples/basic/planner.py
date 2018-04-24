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
class Planner(Mixin.WmsBasicSellerUtil):

    def unfold_request(self, req_id):
        """Pick a Reservation Request that needs to be planned.

        :rtype: (Request, list(Reservation)) or None
        """
        Reservation = self.registry.Wms.Reservation
        Request = Reservation.Request
        RequestItem = Reservation.RequestItem
        req = Request.query().get(req_id)
        resas = Reservation.query().join(
            Reservation.request_item).filter(RequestItem.request == req).all()
        return req, resas

    def process_one(self):
        Reservation = self.registry.Wms.Reservation
        Request = Reservation.Request
        with Request.claim_reservations(planned=False) as req_id:
            if req_id is None:
                return False
            req, resas = self.unfold_request(req_id)
            purpose = req.purpose
            if purpose == 'unpack':
                self.plan_unpack(resas)
            elif isinstance(purpose, list) and purpose[0] == 'sale':
                self.plan_delivery(resas, purpose[1])
            req.planned = True
            return True

    def plan_unpack(self, resas):
        Wms = self.registry.Wms
        Goods = Wms.Goods
        Operation = Wms.Operation
        for resa in resas:
            avatar = Goods.Avatar.query().filter_by(goods=resa.goods,
                                                    dt_until=None).one()
            dt = datetime.now() + timedelta(minutes=10)
            move = Operation.Move.create(input=avatar,
                                         dt_execution=dt,
                                         destination=self.stock_location)
            moved = move.outcomes[0]
            Operation.Unpack.create(
                input=moved,
                dt_execution=dt + timedelta(minutes=10)
            )

    def plan_delivery(self, resas, sale_id):
        Wms = self.registry.Wms
        Goods = Wms.Goods
        Operation = Wms.Operation
        for resa in resas:
            avatar = Goods.Avatar.query().filter_by(goods=resa.goods,
                                                    dt_until=None).one()
            dt = datetime.now() + timedelta(minutes=10)
            move = Operation.Move.create(input=avatar,
                                         dt_execution=dt,
                                         destination=self.outgoing_location)
            moved = move.outcomes[0]
            Operation.Departure.create(
                input=moved,
                dt_execution=dt + timedelta(minutes=10),
                sale_id=sale_id,
            )
