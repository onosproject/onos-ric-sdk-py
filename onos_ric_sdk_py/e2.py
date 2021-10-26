# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import asyncio
import logging
import os
import ssl
from types import TracebackType
from typing import AsyncIterator, List, Optional, Tuple, Type

from grpclib import GRPCError
from grpclib.client import Channel
from onos_api.e2t.e2.v1beta1 import (
    Action,
    ControlMessage,
    ControlServiceStub,
    Encoding,
    EventTrigger,
    RequestHeaders,
    ServiceModel,
    SubscriptionServiceStub,
    SubscriptionSpec,
)

from .exceptions import ClientRuntimeError, ClientStoppedError


class E2Client:
    INSTANCE_ID = os.getenv("HOSTNAME", "")
    PROXY_ENDPOINT = "localhost:5151"
    RETRY_COUNT = 20
    RETRY_DELAY = 0.1

    def __init__(
        self,
        app_id: str,
        e2t_endpoint: str,  # Deprecated
        ca_path: Optional[str] = None,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        skip_verify: bool = True,
    ) -> None:
        self._app_id = app_id

        ssl_context = None
        if ca_path is not None and cert_path is not None and key_path is not None:
            ssl_context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=ca_path
            )
            ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            ssl_context.check_hostname = not skip_verify

        # Connect to sidecar proxy on localhost:5151
        e2t_ip, e2t_port = self.PROXY_ENDPOINT.rsplit(":", 1)
        self._e2t_channel = Channel(e2t_ip, int(e2t_port), ssl=ssl_context)
        self._ready = True

    async def control(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        header: bytes,
        message: bytes,
    ) -> bytes:
        """Send a control message to the RIC to initiate or resume some functionality.

        Args:
            e2_node_id: The target E2 node ID.
            service_model_name: The service model name.
            service_model_version: The service model version.
            header: The RIC control header.
            message: The RIC control message.

        Returns:
            The control outcome.

        Raises:
            ClientStoppedError: The underlying client resources have not been started.
            ClientRuntimeError: There was an error performing the request.
        """
        if not self._ready:
            raise ClientStoppedError()

        client = ControlServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            app_instance_id=self.INSTANCE_ID,
            e2_node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )

        for retry_idx in range(self.RETRY_COUNT):
            try:
                response = await client.control(
                    headers=headers,
                    message=ControlMessage(header=header, payload=message),
                )
                return response.outcome.payload
            except GRPCError as e:
                raise ClientRuntimeError() from e
            except OSError:
                logging.exception("OSError retry %s", retry_idx + 1)
                await asyncio.sleep(self.RETRY_DELAY * retry_idx)
        raise ClientRuntimeError("control exceeded retries")

    async def subscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        subscription_id: str,
        trigger: bytes,
        actions: List[Action],
    ) -> AsyncIterator[Tuple[bytes, bytes]]:
        """Establish an E2 subscription.

        Args:
            e2_node_id: The target E2 node ID.
            service_model_name: The service model name.
            service_model_version: The service model version.
            subscription_id: The ID to use for the subscription.
            trigger: The event trigger.
            actions: A sequence of RIC service actions.

        Yields:
            The next indication header and message, if available.

        Raises:
            ClientStoppedError: The underlying client resources have not been started.
            ClientRuntimeError: There was an error performing the request.
        """
        if not self._ready:
            raise ClientStoppedError()

        client = SubscriptionServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            app_instance_id=self.INSTANCE_ID,
            e2_node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )
        subscription = SubscriptionSpec(
            actions=actions,
            event_trigger=EventTrigger(payload=trigger),
        )

        for retry_idx in range(self.RETRY_COUNT):
            try:
                stream = client.subscribe(
                    headers=headers,
                    transaction_id=subscription_id,
                    subscription=subscription,
                )
                async for response in stream:
                    yield response.indication.header, response.indication.payload
                break
            except OSError:
                logging.exception("OSError retry %s", retry_idx + 1)
                await asyncio.sleep(self.RETRY_DELAY * retry_idx)
        else:
            raise ClientRuntimeError("subscribe exceeded retries")

    async def unsubscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        subscription_id: str,
    ) -> None:
        """Delete an E2 subscription.

        Args:
            e2_node_id: The target E2 node ID.
            service_model_name: The service model name.
            service_model_version: The service model version.
            subscription_id: The ID of the subscription to delete.

        Raises:
            ClientStoppedError: The underlying client resources have not been started.
            ClientRuntimeError: There was an error performing the request.
        """
        if not self._ready:
            raise ClientStoppedError()

        client = SubscriptionServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            app_instance_id=self.INSTANCE_ID,
            e2_node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )

        for retry_idx in range(self.RETRY_COUNT):
            try:
                await client.unsubscribe(
                    headers=headers, transaction_id=subscription_id
                )
                break
            except GRPCError as e:
                raise ClientRuntimeError() from e
            except OSError:
                logging.exception("OSError retry %s", retry_idx + 1)
                await asyncio.sleep(self.RETRY_DELAY * retry_idx)
        else:
            raise ClientRuntimeError("unsubscribe exceeded retries")

    async def __aenter__(self) -> "E2Client":
        """Create any underlying resources required for the client to run."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Cleanly stop all underlying resources used by the client."""
        self._e2t_channel.close()
        self._ready = False
