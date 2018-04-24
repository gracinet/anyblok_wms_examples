# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok import Declarations
from anyblok.column import String

Model = Declarations.Model
Mixin = Declarations.Model
register = Declarations.register


@register(Model.Wms.Goods)
class Type:
    product = String(index=True)
    """Common reference shared between deliverable Goods and their packs."""
