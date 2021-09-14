..
   SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
   SPDX-License-Identifier: Apache-2.0

===========================================
Welcome to onos_ric_sdk_py's documentation!
===========================================

.. toctree::
   :hidden:
   :maxdepth: 2

   reference
   misc

*onos_ric_sdk_py* is a Python 3.7+ framework built using :mod:`asyncio` and
:mod:`aiohttp.web`. At its core, *onos_ric_sdk_py* provides a simple and standardized
way to write xApps that can be deployed as microservices in Python along with the ONF
RIC.

In addition, *onos_ric_sdk_py* creates an HTTP server with
:doc:`preregistered endpoints<./routes>` for xApp configuration and Prometheus metric
exposition. Developers can add their own endpoints to this server for their own
application logic.

Usage
=====

The entrypoint for the *onos_ric_sdk_py* framework is the :func:`~.run` function.

.. autofunction:: onos_ric_sdk_py.run

Quickstart
----------

The follwing example shows how to use *onos_ric_sdk_py* to create a simple microservice
for consuming and printing indication messages from an E2T subscription.

.. code-block:: python

   import asyncio

   import onos_ric_sdk_py as sdk
   from onos_api.e2t.e2.v1beta1 import (
      Action,
      ActionType,
      SubsequentAction,
      SubsequentActionType,
      TimeToWait,
   )

   from .models import MyModel


   async def run(e2_client: sdk.E2Client, e2_node_id: str) -> None:
      async for (header, message) in await e2_client.subscribe(
         e2_node_id,
         service_model_name="my_model",
         service_model_version="v1",
         subscription_id="my_app-my_model-sub",
         trigger=bytes(MyModel(param="foo")),
         actions=[
            Action(
               id=1,
               type=ActionType.ACTION_TYPE_REPORT,
               payload=b"",
               subsequent_actionSubsequentAction(
                  type=SubsequentActionType.SUBSEQUENT_ACTION_TYPE_CONTINUE,
                  time_to_wait=TimeToWait.TIME_TO_WAIT_ZERO,
               )
            )
         ],
      ):
         print(header, message)


   async def main() -> None:
      e2_client = sdk.E2Client(app_id="my_app", e2t_endpoint="onos-e2t:5150")
      sdl_client = sdk.SDLClient(topo_endpoint="onos-topo:5150")
      async with e2_client, sdl_client:
         async for e2_node_id, _ in sdl_client.watch_e2_connections():
            asyncio.create_task(run(e2_client, e2_node_id))


   if __name__ == "__main__":
      sdk.run(main())

Installation
============

*onos_ric_sdk_py* can be installed from PyPI.

.. code-block:: bash

    $ pip install onos_ric_sdk_py

You can also get the latest code from GitHub.

.. code-block:: bash

    $ pip install git+https://github.com/onosproject/onos-ric-sdk-py

Dependencies
============

* Python 3.7+
* aiohttp
* aiohttp-swagger
* betterproto
* onos-api
* prometheus-async
