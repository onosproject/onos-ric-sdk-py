#!/usr/bin/env python

# SPDX-FileCopyrightText: © 2020 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import
from setuptools import setup


def version():
    with open("VERSION") as f:
        return f.read()


def parse_requirements(filename):
    # parse a requirements.txt file, allowing for blank lines and comments
    requirements = []
    for line in open(filename):
        if line and not line.startswith("#"):
            requirements.append(line)
    return requirements


setup(
    name="onos-ric-sdk-python",
    version=version(),
    description="ONOS RIC SDK for Python",
    author="Open Networking Foundation and Partners",
    author_email="support@opennetworking.org",
    packages=["onos_ric_sdk_py"],
    license="Apache v2",
    install_requires=parse_requirements("requirements.txt"),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)
