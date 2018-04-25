# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.

from anyblok.config import Configuration


Configuration.add_application_properties(
    'wms-bench', ['logging', 'database', 'wms-bench'],
    prog='AnyBlok WMS Example and Bench',
    description="Example Anyblok WMS application without human interaction, "
    "for demonstration and performance analysis."""
)


@Configuration.add('wms-bench', label="WMS Benchmarking")
def bench_options(group):
    group.add_argument("--timeslices", type=int, default=10,
                       help="Number of time slices to run")
    group.add_argument("--planner-workers", type=int, default=2,
                       help="Number of planner worker processes to run")
    group.add_argument("--regular-workers", type=int, default=4,
                       help="Number of regular worker processes to run. "
                       "in a normal application, these would be the ones "
                       "reacting to external events (bus, HTTP requests)")
    group.add_argument("--with-profile", action='store_true',
                       help="If set, activates profiling")
    group.add_argument("--profile-file", default='wms.stats',
                       help="Base filename for profile files. "
                       "if pyprof2calltree is installed, they'll "
                       "be converted in .kgrind files, to visualize "
                       "with kcachegrind")
