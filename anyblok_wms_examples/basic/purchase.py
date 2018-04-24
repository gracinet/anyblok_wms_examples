# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from anyblok import Declarations
from anyblok.column import Integer
from anyblok_postgres.column import Jsonb
register = Declarations.register
Example = Declarations.Model.Wms.Example


@register(Example)
class Purchase:
    id = Integer(label="Identifier", primary_key=True)
    properties = Jsonb(label="Properties")
