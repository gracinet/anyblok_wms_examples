# -*- coding: utf-8 -*-
# This file is a part of the AnyBlok / WMS Examples project
#
#    Copyright (C) 2018 Georges Racinet <gracinet@anybox.fr>
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file,You can
# obtain one at http://mozilla.org/MPL/2.0/.
from setuptools import setup, find_packages
import os

version = '0.0.1'


here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.rst'), 'r',
          encoding='utf-8') as readme_file:
    README = readme_file.read()

requirements = [
    'anyblok_wms_base',
]

setup(
    name='anyblok_wms_examples',
    version=version,
    description="Warehouse Management and Logistics on Anyblok, examples",
    long_description=README,
    author="Georges Racinet",
    author_email='gracinet@anybox.fr',
    url="http://docs.anyblok-wms-base.anyblok.org/%s" % version,
    packages=find_packages(),
    entry_points={
        'bloks': [
            'wms-example-launcher=anyblok_wms_examples.launcher:Launcher',
            'wms-example-basic-seller=anyblok_wms_examples.basic:Seller',
        ],
        'anyblok.init':  'wms_examples=anyblok_wms_examples:init_config',
        'test_bloks': [
        ],
        'console_scripts': [
            'wms_example=anyblok_wms_examples.launcher.main:run',
        ],
    },
    include_package_data=True,
    install_requires=requirements,
    zip_safe=False,
    keywords='stock logistics wms',
    classifiers=[
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    tests_require=requirements + ['nose'],
)
