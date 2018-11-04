# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok_wms_base.testing import WmsTestCase


class PlannerTestCase(WmsTestCase):

    def setUp(self):
        super().setUp()
        Wms = self.Wms = self.registry.Wms
        self.Request = Wms.Reservation.Request
        self.Planner = Wms.Worker.Planner
        self.Regular = Wms.Worker.Regular

    def test_maybe_sleep(self):
        planner = self.Planner.insert()
        prefix = str(planner)
        planner.maybe_sleep(prefix, False)
        self.assertEqual(planner.inactivity_count, 1)
        planner.maybe_sleep(prefix, False)
        self.assertEqual(planner.inactivity_count, 2)
        planner.maybe_sleep(prefix, True)
        self.assertEqual(planner.inactivity_count, 0)

    def test_pick_request(self):
        regular = self.Regular.insert()
        planner = self.Planner.insert()
        pack_code = regular.purchase()

        # the db being empty, the regular worker should have issued a pack
        # arrival and its reservation
        self.assertIsNotNone(pack_code)

        with self.Request.claim_reservations(planned=False) as req_id:
            request, resas = planner.unfold_request(req_id)

        self.assertEqual(len(resas), 1)
        resa = resas[0]
        self.assertEqual(request.purpose, "unpack")
        self.assertEqual(resa.goods.type.code, pack_code)

    def test_unpack(self, outer=False):
        """Test planning of unpacks.

        :param bool outer:
           if ``True``, the outermost method,
           ``process_one()``, is tested, otherwise that's the innermost.
        """
        regular = self.Regular.insert()
        planner = self.Planner.insert()
        Reservation = self.Wms.Reservation
        Request = Reservation.Request
        pack_code = regular.purchase()

        # the db being empty, the regular worker should have issued pack
        # arrival
        self.assertIsNotNone(pack_code)
        product = pack_code[:-4]

        Goods = self.Wms.PhysObj
        Avatar = Goods.Avatar

        if outer:
            planner.process_one()
        else:
            with Request.claim_reservations() as req_id:
                _, resas = planner.unfold_request(req_id)
                planner.plan_unpack(resas)

        stock_loc = Goods.query().filter_by(code='stock').one()
        # too lazy to think of the join and besides, we could succeed by
        # chance
        unpacked_type = Goods.Type.query().filter_by(code=product).one()
        avatars = Avatar.query().join(Avatar.goods).filter(
            Goods.type == unpacked_type).all()
        self.assertEqual(len(avatars), 20)
        for av in avatars:
            self.assertEqual(av.state, 'future')
            self.assertEqual(av.dt_until, None)
            self.assertEqual(av.location, stock_loc)

    def test_unpack_outer(self):
        self.test_unpack(outer=True)

    def test_delivery(self, outer=False):
        """Test planning of deliveries.

        :param bool outer:
           if ``True``, the outermost method,
           ``process_one()``, is tested, otherwise that's the innermost.
        """
        planner = self.Planner.insert()

        Sale = self.Wms.Example.Sale
        Goods = self.Wms.PhysObj
        product_1 = 'JEANS/25/28'
        product_2 = 'JEANS/31/32'
        sale, req = Sale.create({product_1: 2, product_2: 1})

        gt1 = Goods.Type.query().filter_by(code=product_1).one()
        gt2 = Goods.Type.query().filter_by(code=product_2).one()

        # Let's create enough goods in stock
        stock = Goods.query().filter_by(code='stock').one()
        Arrival = self.Wms.Operation.Arrival
        for goods_type in (gt1, gt1, gt2):
            Arrival.create(location=stock,
                           dt_execution=self.dt_test1,
                           timeslice=123,
                           goods_type=goods_type,
                           )

        # So that reserving them for the Request related to the Sale will work
        req.reserve()
        self.assertTrue(req.reserved)

        # Now, let's plan that delivery
        if outer:
            planner.process_one()
        else:
            with self.Request.claim_reservations() as req_id:
                _, resas = planner.unfold_request(req_id)
                planner.plan_delivery(resas, sale.id)

        departures = self.Wms.Operation.Departure.query().all()
        self.assertEqual(
            sorted(dep.input.goods.type.code for dep in departures),
            [product_1, product_1, product_2])

    def test_delivery_outer(self):
        self.test_delivery(outer=True)

    def test_nothing_to_do(self):
        planner = self.Planner.insert()
        self.assertFalse(planner.process_one())
