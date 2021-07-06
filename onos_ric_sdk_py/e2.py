# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import os
import ssl
from typing import AsyncIterator, List, Optional, Tuple

import aiomsa.abc
from aiomsa.exceptions import ClientRuntimeError, ClientStoppedError
from grpclib import GRPCError
from grpclib.client import Channel
from onos_api.e2t.e2.v1beta1 import (
    Action,
    ActionType,
    ControlMessage,
    ControlServiceStub,
    Encoding,
    EventTrigger,
    RequestHeaders,
    ServiceModel,
    SubsequentAction,
    SubsequentActionType,
    SubscribeResponse,
    SubscriptionServiceStub,
    SubscriptionSpec,
    TimeToWait,
)


class Subscription(aiomsa.abc.Subscription):
    def __init__(self, id: str, stream: AsyncIterator[SubscribeResponse]) -> None:
        self._id = id
        self._stream = stream

    @property
    def id(self) -> str:
        return self._id

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> Tuple[bytes, bytes]:
        async for response in self._stream:
            return response.indication.header, response.indication.payload
        else:
            raise StopAsyncIteration


class E2Client(aiomsa.abc.E2Client):
    INSTANCE_ID = os.getenv("HOSTNAME", "")

    def __init__(
        self,
        app_id: str,
        e2t_endpoint: str,
        ca_path: Optional[str] = None,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        skip_verify: bool = True,
        **kwargs: str,
    ) -> None:
        self._app_id = app_id

        ssl_context = None
        if ca_path is not None and cert_path is not None and key_path is not None:
            ssl_context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=ca_path
            )
            ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            ssl_context.check_hostname = not skip_verify

        e2t_ip, e2t_port = e2t_endpoint.rsplit(":", 1)
        self._e2t_channel = Channel(e2t_ip, int(e2t_port), ssl=ssl_context)
        self._ready = True

    async def control(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        header: bytes,
        message: bytes,
        control_ack_request: aiomsa.abc.RICControlAckRequest,
    ) -> Optional[bytes]:
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

        try:
            response = await client.control(
                headers=headers,
                message=ControlMessage(header=header, payload=message),
            )
            return response.outcome.payload
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def subscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        subscription_id: str,
        trigger: bytes,
        actions: List[aiomsa.abc.RICAction],
    ) -> Subscription:
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
            event_trigger=EventTrigger(payload=trigger),
        )
        for a in actions:
            action = Action(id=a.id, type=ActionType(a.type))
            if a.definition is not None:
                action.payload = a.definition
            if a.subsequent_action is not None:
                action.subsequent_action = SubsequentAction(
                    type=SubsequentActionType(a.subsequent_action.type),
                    time_to_wait=TimeToWait(a.subsequent_action.time_to_wait),
                )
            subscription.actions.append(action)

        stream = client.subscribe(
            headers=headers, transaction_id=subscription_id, subscription=subscription
        )
        return Subscription(subscription_id, stream)

    async def unsubscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        subscription_id: str,
    ) -> None:
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

        try:
            await client.unsubscribe(headers=headers, transaction_id=subscription_id)
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def __aenter__(self) -> "E2Client":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._e2t_channel.close()
        self._ready = False
