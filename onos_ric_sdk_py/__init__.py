# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import asyncio
import logging
import os
import signal
import traceback
from typing import Coroutine, Optional

from aiohttp import web
from aiohttp_swagger import setup_swagger  # type: ignore

from .e2 import E2Client
from .exceptions import DuplicateRouteError
from .sdl import SDLClient
from .server import error_middleware, routes


def run(
    main: Coroutine,
    path: str,
    app: Optional[web.Application] = None,
    **server_kwargs,
) -> None:
    """Start the webserver and the entrypoint logic passed in as ``main``.

    Args:
        main: The entrypoint for the service's logic, in the form of a coroutine.
        path: The path to the service's configuration file on disk.
        app: An existing web application object, if available.
        server_kwargs: Variable number of ``kwargs`` to pass to
                       :func:`aiohttp.web.run_app`.
    Raises:
        DuplicateRouteError: A user-supplied route conflicts with one of the default
                             :doc:`routes<./routes>`.
        ValueError: ``main`` is not a proper coroutine.
    """
    logging.basicConfig(
        format="%(levelname)s %(asctime)s %(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not asyncio.coroutines.iscoroutine(main):
        raise ValueError(f"A coroutine was expected, got {main}")

    # Create web application object and shutdown event
    if app is None:
        app = web.Application(middlewares=[error_middleware])
    app["main"] = main
    app["path"] = path
    app["shutdown_event"] = asyncio.Event()

    # Initialize the endpoints for the HTTP server
    try:
        app.add_routes(routes)
    except RuntimeError:
        app["main"].close()
        resources = [(r.method, r.path) for r in routes if isinstance(r, web.RouteDef)]
        raise DuplicateRouteError(
            f"A user-supplied route conflicts with a pre-registered route: {resources}"
        )

    # Document the endpoints with OpenAPI
    setup_swagger(app, ui_version=3)

    # Add background tasks
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    web.run_app(app, **server_kwargs)


async def on_startup(app: web.Application) -> None:
    """Create the 'main_wrapper_task' and 'shutdown_listener'."""
    app["shutdown_listener"] = asyncio.create_task(shutdown_listener(app))
    app["main_wrapper_task"] = asyncio.create_task(main_wrapper(app))


async def on_cleanup(app: web.Application) -> None:
    """Cancel the 'shutdown_listener' and 'main_wrapper_task'."""
    app["shutdown_listener"].cancel()
    app["main_wrapper_task"].cancel()
    await app["shutdown_listener"]

    try:
        await app["main_wrapper_task"]
    except:  # noqa: E722
        traceback.print_exc(chain=False)


async def main_wrapper(app: web.Application) -> None:
    """Run the 'main' coroutine and set the 'shutdown_event' if it fails."""
    try:
        await app["main"]
    except asyncio.CancelledError:
        pass
    except:  # noqa: E722
        app["shutdown_event"].set()
        raise


async def shutdown_listener(app: web.Application) -> None:
    """Wait for the 'shutdown_event' notification to kill the process."""
    try:
        await app["shutdown_event"].wait()
        logging.warning("Shutting down!")

        # Wait before shutting down
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        os.kill(os.getpid(), signal.SIGTERM)


__all__ = ["E2Client", "SDLClient", "run"]
