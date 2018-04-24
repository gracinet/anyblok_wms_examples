# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from random import randrange

from anyblok import Declarations
from anyblok.column import Integer
from anyblok_postgres.column import Jsonb
register = Declarations.register
Example = Declarations.Model.Wms.Example


@register(Example)
class Sale:
    id = Integer(label="Identifier", primary_key=True)
    contents = Jsonb(label="Properties")

    @classmethod
    def create(cls, contents):
        """Create a Sale, returning it, and corresponding Reservation Request.
        """
        sale = cls.insert(contents=contents)
        Wms = cls.registry.Wms
        Reservation = Wms.Reservation
        RequestItem = Reservation.RequestItem
        GoodsType = Wms.Goods.Type

        req = Reservation.Request.insert(purpose=['sale', sale.id])
        for product, qty in contents.items():
            gt = GoodsType.query().filter(GoodsType.code == product).one()
            RequestItem.insert(goods_type=gt,
                               quantity=qty,
                               request=req)
        return sale, req

    @classmethod
    def create_random(cls):
        contents = {}
        for _ in range(randrange(4)):
            width = randrange(25, 45)
            height = randrange(20, 40)
            contents['JEANS/%d/%d' % (width, height)] = randrange(1, 3)
        return cls.create(contents)
