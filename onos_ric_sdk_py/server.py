# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import collections.abc
import json
import logging
from typing import Callable, cast

from aiohttp import web
from prometheus_async import aio  # type: ignore


routes = web.RouteTableDef()


@web.middleware
async def error_middleware(request: web.Request, handler: Callable) -> web.Response:
    """Middleware for returning non-200 responses as JSON."""
    try:
        return cast(web.Response, await handler(request))
    except web.HTTPError as e:
        return web.json_response(
            {"status": "error", "message": e.text}, status=e.status
        )
    except Exception:
        logging.exception("Error handling request")
        return web.json_response(
            {"status": "error", "message": "Server got itself in trouble"}, status=500
        )


@routes.get("/status")
async def handle_get_status(request: web.Request) -> web.Response:
    """
    ---
    description: Check if the webserver is responsive.
    tags:
    - Health
    responses:
      "200":
        description: Successful operation.
        content:
          text/plain:
            example: "Alive"
    """
    return web.Response(text="Alive")


@routes.get("/config")
async def handle_get_config(request: web.Request) -> web.Response:
    """
    ---
    description: Return the current service configuration settings.
    tags:
    - Configuration
    responses:
      "200":
        description: Successful operation.
        content:
          application/json:
            example:
              foo:
              - bar
              - baz
              timeout: 15
      "500":
        description: Failed to load or parse the configuration file.
    """
    try:
        with open(request.app["path"], encoding="utf-8") as f:
            config = json.load(f)
            return web.json_response(config)
    except json.JSONDecodeError:
        raise web.HTTPInternalServerError(
            text="Existing configuration is not valid JSON"
        )
    except OSError:
        raise web.HTTPInternalServerError(text="Failed to load existing configuration")


@routes.put("/config")
async def handle_set_config(request: web.Request) -> web.Response:
    """
    ---
    description: Completely overwrite the service's configuration settings.
    tags:
    - Configuration
    requestBody:
      description: New service configuration object
      required: true
      content:
        application/json:
          example:
            config:
              foo:
              - bar
              - baz
              timeout: 30
    responses:
      "200":
        description: Successful operation.
        content:
          application/json:
            example:
              foo:
              - bar
              - baz
              timeout: 30
      "400":
        description: Missing or invalid 'config' parameter.
      "500":
        description: Failed to overwrite service configuration.
    """
    body = await request.json()

    if "config" not in body:
        raise web.HTTPBadRequest(text="Missing required 'config' param")

    config = body["config"]
    if not isinstance(config, dict):
        raise web.HTTPBadRequest(text="Invalid value for 'config': Not object")

    try:
        with open(request.app["path"], "w", encoding="utf-8") as f:
            json.dump(config, f)

        # Trigger the shutdown event
        request.app["shutdown_event"].set()
        return web.json_response(config)
    except OSError:
        raise web.HTTPInternalServerError(text="Failed to overwrite configuration")


@routes.patch("/config")
async def handle_update_config(request: web.Request) -> web.Response:
    """
    ---
    description: Partially update the service's configuration settings.
    tags:
    - Configuration
    requestBody:
      description: New service configuration object
      required: true
      content:
        application/json:
          example:
            config:
              timeout: 60
    responses:
      "200":
        description: Successful operation.
        content:
          application/json:
            example:
              foo:
              - bar
              - baz
              timeout: 60
      "400":
        description: Missing or invalid 'config' parameter.
      "500":
        description: Failed to update service configuration.
    """
    body = await request.json()

    if "config" not in body:
        raise web.HTTPBadRequest(text="Missing required 'config' param")

    updates = body["config"]
    if not isinstance(updates, dict):
        raise web.HTTPBadRequest(text="Invalid value for 'config': Not object")

    try:
        with open(request.app["path"], "r+", encoding="utf-8") as f:
            config = json.load(f)

            # Deeply merge the updates onto the base config
            stack = [(config, updates)]
            while stack:
                dst, src = stack.pop(0)
                for k, v in src.items():
                    if isinstance(v, dict) and isinstance(
                        dst.get(k), collections.abc.Mapping
                    ):
                        stack.append((dst[k], v))
                    else:
                        dst[k] = v

            # Write new config at the beginning of the file and truncate what's left
            f.seek(0)
            json.dump(config, f)
            f.truncate()

        # Trigger the shutdown event
        request.app["shutdown_event"].set()
        return web.json_response(config)
    except json.JSONDecodeError:
        raise web.HTTPInternalServerError(
            text="Existing configuration is not valid JSON"
        )
    except OSError:
        raise web.HTTPInternalServerError(text="Failed to update configuration")


@routes.put("/log/{level:[A-Z]+}")
async def handle_set_log_level(request: web.Request) -> web.Response:
    """
    ---
    description: Dynamically set the service's log level.
    tags:
    - Configuration
    parameters:
    - in: path
      name: level
      description: The new log level.
      required: true
      schema:
        enum: [DEBUG, INFO, WARNING, ERROR, FATAL]
        type: string
    responses:
      "200":
        description: Successful operation.
        content:
          text/plain:
            example: "Log level set to WARNING from INFO"
      "400":
        description: Invalid log level.
    """
    level = request.match_info["level"]
    prev_level = logging.getLevelName(logging.root.level)

    if level == prev_level:
        return web.Response(text=f"Log level is already {prev_level}")

    try:
        logging.root.setLevel(level)
    except ValueError as e:
        raise web.HTTPBadRequest(text=str(e))

    return web.Response(text=f"Log level set to {level} from {prev_level}")


@routes.get("/metrics")
async def handle_get_metrics(request: web.Request) -> web.Response:
    """
    ---
    description: Scrape the service's Prometheus metrics cache.
    tags:
    - Prometheus
    responses:
      "200":
        description: Successful operation.
        content:
          text/plain:
            example:
              python_gc_objects_collected_total{generation="0"} 479.0\n
              python_gc_objects_collected_total{generation="1"} 260.0\n
              python_gc_objects_collected_total{generation="2"} 0.0
    """
    return await aio.web.server_stats(request)
