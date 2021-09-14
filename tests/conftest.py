# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

from typing import Any

import pytest


@pytest.fixture
def tmp_config_file(tmp_path: Any) -> Any:
    conf = tmp_path / "config.json"
    conf.write_text("{}")
    yield conf
    conf.unlink()
