# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import unittest
import onos_ric_sdk_py  # noqa: F401


class ONOS_RIC_SDK_py_test(unittest.TestCase):
    def test_1(self):
        """
        Pass
        """
        self.assertEqual("1", "1")
