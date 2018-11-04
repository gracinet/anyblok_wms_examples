# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok import Declarations
register = Declarations.register
Wms = Declarations.Model.Wms


@register(Declarations.Mixin)
class WmsBasicSellerUtil:

    # I'm actually tempted to set in on the Blok itself !

    def location_by_code(self, code):
        return self.registry.Wms.PhysObj.query().filter_by(code=code).one()

    @property
    def incoming_location(self):
        # TODO cache
        return self.location_by_code("incoming")

    @property
    def stock_location(self):
        # TODO cache
        return self.location_by_code("stock")

    @property
    def outgoing_location(self):
        # TODO cache
        return self.location_by_code("outgoing")
