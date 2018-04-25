Examples for Anyblok WMS
========================

.. image:: https://travis-ci.org/AnyBlok/anyblok_wms_examples.svg?branch=master
    :target: https://travis-ci.org/AnyBlok/anyblok_wms_examples
    :alt: Build status

.. image:: https://coveralls.io/repos/github/AnyBlok/anyblok_wms_examples/badge.svg?branch=master
    :target: https://coveralls.io/github/AnyBlok/anyblok_wms_examples?branch=master
    :alt: Coverage


License
~~~~~~~

Anyblok / WMS Examples is provided under the terms of the MPL v2.0.

Namely, for the present file:

  This file is a part of the AnyBlok / WMS Examples project

    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>

  This Source Code Form is subject to the terms of the Mozilla Public License,
  v. 2.0. If a copy of the MPL was not distributed with this file,You can
  obtain one at http://mozilla.org/MPL/2.0/.


wms-example-basic-seller
~~~~~~~~~~~~~~~~~~~~~~~~

This example simulates a very basic selling workflow: products are
supposed to be jeans (one for each size) as units or packs (only packs
enter the system).

At the beginning of each timeslice, the regular workers will order
some packs if needed and issue some random final customer sale orders, with
the corresponding Reservation Requests.

There are only three Locations: ``incoming``, ``stock`` and ``outgoing``.
Packs arrive in ``incoming``, are moved to ``stock`` where they are
unpacked.

The delivery process moves the goods to the ``outgoing`` location
before issuing Departures.

Everything is processed using the Reservation concepts and related
architectural processes, by specialization of the process models
provided by :ref:`wms_example_launcher`

.. _wms_example_launcher:

wms-example-launcher
~~~~~~~~~~~~~~~~~~~~

This Blok provides a multiprocessed console script that should be
partly included in anyblok_wms_base itself.

The principle is that Reserver and Planner processes work
continuously, whereas regular worker processes act in coordinated
timeslices, which one may think of simulating a day's work.

In the context of examples serving as benches, one does not want to
rely on wall clock time, the intent being to run as fast as possible.
In that context, the timeslices are useful to postpone the execution
of some Operations (typically, Arrivals).

Also, some Operations are performed only at the beginning of each
timeslice, in order to keep artificial conflicts to a minimum (in
continuously running benches, the very selection of work to be done is
a source of conflicts in itself that wouldn't happen in real life).


