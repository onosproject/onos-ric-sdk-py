# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import os
import ssl
from typing import AsyncIterator, List, Optional, Tuple
from uuid import uuid4

import aiomsa.abc
from grpclib.client import Channel
from onos_api.e2t.admin import E2TAdminServiceStub
from onos_api.e2t.aiomsa.abc.v1beta1 import (
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
    Subscription as E2Subscription,
    SubscriptionServiceStub,
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

    async def list_nodes(self, oid: Optional[str] = None) -> List[aiomsa.abc.E2Node]:
        nodes = []

        admin_client = E2TAdminServiceStub(self._e2t_channel)
        async for conn in admin_client.list_e2_node_connections():
            if not conn.ran_functions:
                continue
            if oid is None or any(func.oid == oid for func in conn.ran_functions):
                nodes.append(
                    aiomsa.abc.E2Node(
                        id=conn.id,
                        ran_functions=[
                            aiomsa.abc.RanFunction(
                                id=func.ran_function_id,
                                oid=func.oid,
                                definition=func.description,
                            )
                            for func in conn.ran_functions
                        ],
                    )
                )

        return nodes

    async def control(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        header: bytes,
        message: bytes,
        control_ack_request: aiomsa.abc.RICControlAckRequest,
    ) -> Optional[bytes]:
        client = ControlServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            instance_id=self.INSTANCE_ID,
            node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )

        outcome = await client.control(
            headers=headers,
            message=ControlMessage(header=header, payload=message),
        )
        return outcome.payload

    async def subscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        trigger: bytes,
        actions: List[aiomsa.abc.RICAction],
    ) -> Subscription:
        client = SubscriptionServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            instance_id=self.INSTANCE_ID,
            node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )
        subscription = E2Subscription(
            id=str(uuid4()),
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

        stream = client.subscribe(headers=headers, subscription=subscription)
        return Subscription(subscription.id, stream)

    async def unsubscribe(  # type: ignore
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        subscription_id: str,
    ) -> None:
        client = SubscriptionServiceStub(self._e2t_channel)
        headers = RequestHeaders(
            app_id=self._app_id,
            instance_id=self.INSTANCE_ID,
            node_id=e2_node_id,
            service_model=ServiceModel(
                name=service_model_name, version=service_model_version
            ),
            encoding=Encoding.PROTO,
        )

        await client.unsubscribe(headers=headers, subscription_id=subscription_id)

    async def __aenter__(self) -> "E2Client":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._e2t_channel.close()
