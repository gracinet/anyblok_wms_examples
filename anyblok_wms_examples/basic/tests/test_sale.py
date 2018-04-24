# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok_wms_base.testing import WmsTestCase


class SaleTestCase(WmsTestCase):

    def setUp(self):
        super().setUp()
        Wms = self.Wms = self.registry.Wms
        self.Sale = Wms.Example.Sale

    def test_create_random(self):
        sale, req = self.Sale.create_random()
        self.assertEqual(req.purpose, ['sale', sale.id])
