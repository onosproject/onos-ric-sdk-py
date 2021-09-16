# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

from typing import Any
from unittest import mock

import pytest
from aiohttp import web

import onos_ric_sdk_py


@pytest.fixture
def onos_ric_sdk_py_app() -> Any:
    app = web.Application(middlewares=[onos_ric_sdk_py.server.error_middleware])
    app["shutdown_event"] = mock.Mock()
    app.add_routes(onos_ric_sdk_py.server.routes)
    yield app


@pytest.fixture
def inaccessible_config_file(tmp_path: Any) -> Any:
    conf = tmp_path / "inaccessible.json"
    conf.touch(mode=0o000)
    yield conf
    conf.unlink()


async def test_json_error_middleware(
    onos_ric_sdk_py_app: Any, aiohttp_client: Any
) -> None:
    async def raise_exception(request: web.Request) -> web.Response:
        raise Exception

    onos_ric_sdk_py_app.router.add_get("/", raise_exception)
    client = await aiohttp_client(onos_ric_sdk_py_app)
    resp = await client.get("/")
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Server got itself in trouble"


async def test_get_status(onos_ric_sdk_py_app: Any, aiohttp_client: Any) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)
    resp = await client.get("/status")
    assert resp.status == 200
    assert resp.content_type == "text/plain"
    text = await resp.text()
    assert text == "Alive"


async def test_get_config(
    onos_ric_sdk_py_app: Any,
    aiohttp_client: Any,
    tmp_config_file: Any,
    inaccessible_config_file: Any,
) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)

    # Invalid permissions
    onos_ric_sdk_py_app["path"] = str(inaccessible_config_file)
    resp = await client.get("/config")
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Failed to load existing configuration"

    # Valid
    onos_ric_sdk_py_app["path"] = str(tmp_config_file)
    resp = await client.get("/config")
    assert resp.status == 200
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response == {}

    # Invalid JSON
    tmp_config_file.write_text("{")
    resp = await client.get("/config")
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Existing configuration is not valid JSON"


async def test_set_config(
    onos_ric_sdk_py_app: Any,
    aiohttp_client: Any,
    tmp_config_file: Any,
    inaccessible_config_file: Any,
) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)

    # Invalid configuration (missing 'config')
    resp = await client.put("/config", json={"foo": "bar"})
    assert resp.status == 400
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Missing required 'config' param"

    # Invalid configuration ('config' not an object)
    resp = await client.put("/config", json={"config": 10})
    assert resp.status == 400
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Invalid value for 'config': Not object"

    # Invalid permissions
    onos_ric_sdk_py_app["path"] = str(inaccessible_config_file)
    resp = await client.put("/config", json={"config": {"foo": "bar"}})
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Failed to overwrite configuration"

    # Valid
    onos_ric_sdk_py_app["path"] = str(tmp_config_file)
    resp = await client.put("/config", json={"config": {"foo": "bar"}})
    assert resp.status == 200
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response == {"foo": "bar"}
    onos_ric_sdk_py_app["shutdown_event"].set.assert_called_once()


async def test_update_config(
    onos_ric_sdk_py_app: Any,
    aiohttp_client: Any,
    tmp_config_file: Any,
    inaccessible_config_file: Any,
) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)

    # Invalid configuration (missing 'config')
    resp = await client.patch("/config", json={"foo": "bar"})
    assert resp.status == 400
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Missing required 'config' param"

    # Invalid configuration ('config' not an object)
    resp = await client.patch("/config", json={"config": 10})
    assert resp.status == 400
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Invalid value for 'config': Not object"

    # Invalid permissions
    onos_ric_sdk_py_app["path"] = str(inaccessible_config_file)
    resp = await client.patch("/config", json={"config": {"foo": "bar"}})
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Failed to update configuration"

    # Valid
    onos_ric_sdk_py_app["path"] = str(tmp_config_file)
    tmp_config_file.write_text('{"foo": {"bar": "qux", "quux": "quuz"}}')
    resp = await client.patch("/config", json={"config": {"foo": {"bar": "baz"}}})
    assert resp.status == 200
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response == {"foo": {"bar": "baz", "quux": "quuz"}}
    onos_ric_sdk_py_app["shutdown_event"].set.assert_called_once()

    # Invalid JSON
    tmp_config_file.write_text("{")
    resp = await client.patch("/config", json={"config": {"foo": "bar"}})
    assert resp.status == 500
    assert resp.content_type == "application/json"
    json_response = await resp.json()
    assert json_response["status"] == "error"
    assert json_response["message"] == "Existing configuration is not valid JSON"


async def test_set_log_level(onos_ric_sdk_py_app: Any, aiohttp_client: Any) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)
    with mock.patch.object(
        onos_ric_sdk_py.server.logging, "getLevelName", return_value="WARNING"
    ):
        # Log level already the same
        resp = await client.put("/log/WARNING")
        assert resp.status == 200
        assert resp.content_type == "text/plain"
        text = await resp.text()
        assert text == "Log level is already WARNING"

        # Log level set
        resp = await client.put("/log/INFO")
        assert resp.status == 200
        assert resp.content_type == "text/plain"
        text = await resp.text()
        assert text == "Log level set to INFO from WARNING"

        # Unknown log level
        resp = await client.put("/log/FAKELEVEL")
        assert resp.status == 400
        assert resp.content_type == "application/json"
        json_response = await resp.json()
        assert json_response["status"] == "error"
        assert json_response["message"] == "Unknown level: 'FAKELEVEL'"


async def test_get_metrics(onos_ric_sdk_py_app: Any, aiohttp_client: Any) -> None:
    client = await aiohttp_client(onos_ric_sdk_py_app)
    resp = await client.get("/metrics")
    assert resp.status == 200
    assert resp.content_type == "text/plain"
