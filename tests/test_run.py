# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import asyncio
from typing import Any, Callable
from unittest import mock

import pytest
from aiohttp import web

import onos_ric_sdk_py


async def async_main() -> None:
    await asyncio.sleep(1)


def stopper(loop: Any) -> Callable:
    def raiser():
        raise KeyboardInterrupt

    def f(*args):
        loop.call_soon(raiser)

    return f


def test_run_invalid_main_coroutine(tmp_config_file: Any) -> None:
    def sync_main() -> None:
        pass

    # Test with synchronous function
    with pytest.raises(ValueError):
        onos_ric_sdk_py.run(sync_main(), path=str(tmp_config_file))
    # Test with lambda function
    with pytest.raises(ValueError):
        onos_ric_sdk_py.run(lambda *args, **kwargs: None, path=str(tmp_config_file))
    # Test with async callable
    with pytest.raises(ValueError):
        onos_ric_sdk_py.run(async_main, path=str(tmp_config_file))


def test_run_duplicate_route_error(tmp_config_file: Any) -> None:
    async def status(request: web.Request) -> web.Response:
        return web.Response(text="Hello, world")

    app = web.Application()
    app.router.add_get("/status", status)
    with pytest.raises(onos_ric_sdk_py.exceptions.DuplicateRouteError):
        onos_ric_sdk_py.run(async_main(), path=str(tmp_config_file), app=app)


def test_run_logging_configuration_set(event_loop: Any, tmp_config_file: Any) -> None:
    with mock.patch.object(onos_ric_sdk_py.logging, "basicConfig") as mock_basic_config:
        onos_ric_sdk_py.run(
            async_main(), path=str(tmp_config_file), print=stopper(event_loop)
        )
        mock_basic_config.assert_called_once_with(
            format="%(levelname)s %(asctime)s %(filename)s:%(lineno)d] %(message)s",
            level=onos_ric_sdk_py.logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def test_run_items_are_saved_in_app(event_loop: Any, tmp_config_file: Any) -> None:
    app = web.Application()
    main = async_main()
    path = str(tmp_config_file)
    onos_ric_sdk_py.run(main, path=path, app=app, print=stopper(event_loop))
    assert app["main"] is main
    assert app["path"] is path
    assert isinstance(app["shutdown_event"], asyncio.Event)
    assert isinstance(app["main_wrapper_task"], asyncio.Task)
    assert isinstance(app["shutdown_listener"], asyncio.Task)


def test_run_add_routes_called(event_loop: Any, tmp_config_file: Any) -> None:
    app = web.Application()
    with mock.patch.object(app, "add_routes") as mock_add_routes:
        onos_ric_sdk_py.run(
            async_main(), path=str(tmp_config_file), app=app, print=stopper(event_loop)
        )
        mock_add_routes.assert_called_once_with(onos_ric_sdk_py.server.routes)


def test_run_setup_swagger_called(event_loop: Any, tmp_config_file: Any) -> None:
    app = web.Application()
    with mock.patch("onos_ric_sdk_py.setup_swagger") as mock_setup_swagger:
        onos_ric_sdk_py.run(
            async_main(), path=str(tmp_config_file), app=app, print=stopper(event_loop)
        )
        mock_setup_swagger.assert_called_once_with(app, ui_version=3)


def test_run_app_created_if_one_not_provided(
    event_loop: Any, tmp_config_file: Any
) -> None:
    with mock.patch(
        "onos_ric_sdk_py.web.Application", return_value=web.Application()
    ) as mock_app:
        onos_ric_sdk_py.run(
            async_main(), path=str(tmp_config_file), print=stopper(event_loop)
        )
        mock_app.assert_called_once_with(
            middlewares=[onos_ric_sdk_py.server.error_middleware]
        )


def test_run_existing_app_used_if_one_provided(
    event_loop: Any, tmp_config_file: Any
) -> None:
    app = web.Application()
    with mock.patch("onos_ric_sdk_py.web.Application") as mock_app:
        onos_ric_sdk_py.run(
            async_main(), path=str(tmp_config_file), app=app, print=stopper(event_loop)
        )
        mock_app.assert_not_called()


def test_run_tasks_are_added(event_loop: Any, tmp_config_file: Any) -> None:
    mock_app = mock.MagicMock()
    with mock.patch.object(
        onos_ric_sdk_py.asyncio.coroutines, "iscoroutine", return_value=True
    ):
        with mock.patch("onos_ric_sdk_py.web") as mock_web:
            onos_ric_sdk_py.run(
                mock.Mock(),
                path=str(tmp_config_file),
                app=mock_app,
                print=stopper(event_loop),
            )
            mock_app.on_startup.append.assert_called_once_with(
                onos_ric_sdk_py.on_startup
            )
            mock_app.on_cleanup.append.assert_called_once_with(
                onos_ric_sdk_py.on_cleanup
            )
            mock_web.run_app.assert_called_once_with(mock_app, print=mock.ANY)


def test_run_main_exception(tmp_config_file: Any) -> None:
    async def main_exception():
        raise Exception

    with mock.patch("onos_ric_sdk_py.logging") as mock_logging:
        with mock.patch("onos_ric_sdk_py.traceback") as mock_traceback:
            onos_ric_sdk_py.run(main_exception(), path=str(tmp_config_file))
            mock_logging.warning.assert_called_once_with("Shutting down!")
            mock_traceback.print_exc.assert_called_once_with(chain=False)
