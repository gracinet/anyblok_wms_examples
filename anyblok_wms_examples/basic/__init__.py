# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok.blok import Blok
from .. import version


class Seller(Blok):
    """A very crude scenario of arrivals and departures."""

    version = version
    author = 'Georges Racinet'

    required = ['wms-core', 'wms-reservation', 'wms-example-launcher']

    def install(self):
        Wms = self.registry.Wms
        POT = Wms.PhysObj.Type
        Apparition = Wms.Operation.Apparition
        loc_type = POT.insert(code="LOCATION",
                              behaviours=dict(container=True))
        # we'll use a root container for the sake of example
        root = Wms.create_root_container(loc_type, code="warehouse")
        for loc_code in ('incoming', 'stock', 'outgoing'):
            Apparition.create(state='done', location=root, quantity=1,
                              goods_type=loc_type, goods_code=loc_code)

        for width in range(25, 45):
            for height in range(20, 40):
                product = "JEANS/%d/%d" % (width, height)
                jeans = POT.insert(code=product, product=product)
                POT.insert(
                    code=product + '/PCK',
                    product=product,
                    behaviours=dict(
                        unpack=dict(
                            uniform_outcomes=True,
                            outcomes=[dict(type=jeans.code, quantity=20)]
                        )
                    )
                )

    def update(self, latest_version):
        if latest_version is None:
            self.install()

    @classmethod
    def import_declaration_module(cls):
        from . import ns # noqa
        from . import util # noqa
        from . import sale # noqa
        from . import goods # noqa
        from . import arrival # noqa
        from . import departure # noqa
        from . import regular_worker # noqa
        from . import planner # noqa
