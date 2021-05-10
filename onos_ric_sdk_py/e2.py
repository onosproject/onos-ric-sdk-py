# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

import asyncio
import ssl
from typing import AsyncIterator, List, Optional, Tuple
from uuid import uuid4

import betterproto
from betterproto.grpc.util.async_channel import AsyncChannel
from grpclib.client import Channel

from aiomsa import e2, models
from aiomsa.exceptions import E2ClientError

from .onos_api.onos.e2sub.endpoint import E2RegistryServiceStub
from .onos_api.onos.e2sub.subscription import (
    Action,
    ActionType,
    E2SubscriptionServiceStub,
    Encoding,
    EventTrigger,
    Payload,
    ServiceModel as E2SubServiceModel,
    Subscription as E2Subscription,
    SubscriptionDetails,
    SubsequentAction,
    SubsequentActionType,
    TimeToWait,
)
from .onos_api.onos.e2sub.task import E2SubscriptionTaskServiceStub, EventType, Status
from .onos_api.onos.e2t.admin import E2TAdminServiceStub
from .onos_api.onos.e2t.e2 import (  # ResponseStatus,
    ControlAckRequest,
    E2TServiceStub,
    EncodingType,
    RequestHeader,
    ServiceModel as E2TServiceModel,
    StreamRequest,
    StreamResponse,
)


class Subscription(e2.Subscription):
    def __init__(
        self,
        subscription_id: str,
        app_id: str,
        e2sub_channel: Channel,
        ssl_context: Optional[ssl.SSLContext],
    ) -> None:
        self._id = subscription_id
        self._app_id = app_id
        self._watch_task = asyncio.create_task(self._watch(e2sub_channel, ssl_context))
        self._stream_lock = asyncio.Semaphore(0)
        self._stream: Optional[AsyncIterator[StreamResponse]] = None

    async def getone(self) -> Optional[Tuple[bytes, bytes]]:
        # The lock blocks the subscription until its fully created
        async with self._stream_lock:
            if self._watch_task.done():
                self._watch_task.result()

            if self._stream is None:
                return None
            async for msg in self._stream:
                return msg.indication_header, msg.indication_message
            else:
                return None

    async def _watch(
        self, e2sub_channel: Channel, ssl_context: Optional[ssl.SSLContext]
    ) -> None:
        endpoint_client = E2RegistryServiceStub(e2sub_channel)
        task_client = E2SubscriptionTaskServiceStub(e2sub_channel)
        prev_endpoint_id = None
        async for response in task_client.watch_subscription_tasks(
            subscription_id=self._id
        ):
            event = response.event
            if event.task.subscription_id != self._id:
                # Only interested in tasks related to this subscription
                continue
            if event.task.endpoint_id == prev_endpoint_id:
                # Skip if the stream is already open for the associated E2 endpoint
                continue
            if event.task.lifecycle.status == Status.FAILED:
                raise Exception(event.task.lifecycle.failure.message)

            if event.type == EventType.NONE or event.type == EventType.CREATED:
                termination = await endpoint_client.get_termination(
                    id=event.task.endpoint_id
                )
                async with Channel(
                    termination.endpoint.ip, termination.endpoint.port, ssl=ssl_context
                ) as channel:
                    e2t_client = E2TServiceStub(channel)
                    requests: AsyncChannel = AsyncChannel()
                    await requests.send_from(
                        [
                            StreamRequest(
                                app_id=self._app_id,
                                subscription_id=self._id,
                            )
                        ],
                        close=True,
                    )
                    self._stream = e2t_client.stream(requests)
                    self._stream_lock.release()
            elif event.type == EventType.REMOVED:
                # Take the lock until the stream has been recreated
                await self._stream_lock.acquire()
                self._stream = None

    @property
    def id(self) -> str:
        return self._id

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> Optional[Tuple[bytes, bytes]]:
        while True:
            return await self.getone()


class E2Client(e2.E2Client):
    def __init__(
        self,
        app_id: str,
        e2t_endpoint: str,
        e2sub_endpoint: str,
        ca_path: Optional[str] = None,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        skip_verify: bool = True,
    ) -> None:
        self._app_id = app_id

        self._ssl_context = None
        if ca_path is not None and cert_path is not None and key_path is not None:
            self._ssl_context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=ca_path
            )
            self._ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            self._ssl_context.check_hostname = not skip_verify

        e2t_ip, e2t_port = e2t_endpoint.rsplit(":", 1)
        e2sub_ip, e2sub_port = e2sub_endpoint.rsplit(":", 1)
        self._e2t_channel = Channel(e2t_ip, int(e2t_port), ssl=self._ssl_context)
        self._e2sub_channel = Channel(e2sub_ip, int(e2sub_port), ssl=self._ssl_context)

    async def list_nodes(self, oid: Optional[str] = None) -> List[models.E2Node]:
        nodes = []

        admin_client = E2TAdminServiceStub(self._e2t_channel)
        async for conn in admin_client.list_e2_node_connections():
            if not conn.ran_functions:
                continue
            if oid is None or any(func.oid == oid for func in conn.ran_functions):
                nodes.append(
                    models.E2Node(
                        id=conn.id,
                        ran_functions=[
                            models.RanFunction(
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
        control_ack_request: models.RICControlAckRequest,
    ) -> Optional[bytes]:
        e2t_client = E2TServiceStub(self._e2t_channel)
        request_header = RequestHeader(
            encoding_type=EncodingType.PROTO,
            service_model=E2TServiceModel(
                name=service_model_name, version=service_model_version
            ),
        )

        control_response = await e2t_client.control(
            header=request_header,
            e2_node_id=e2_node_id,
            control_header=header,
            control_message=message,
            control_ack_request=ControlAckRequest(control_ack_request),
        )
        name, value = betterproto.which_one_of(control_response, "response")
        if value is None:
            raise E2ClientError("E2 control response is missing")
        if name == "control_failure":
            raise E2ClientError(f"Control failure ({value.cause}): {value.message}")

        # The value of response is `control_acknowledge`
        if control_ack_request == ControlAckRequest.NO_ACK:
            return None
        # TODO: Restore this when response_status is populated
        # if control_response.header.response_status == ResponseStatus.FAILED:
        #     pass
        # elif control_response.header.response_status == ResponseStatus.REJECTED:
        #     pass

        return value.control_outcome

    async def subscribe(
        self,
        e2_node_id: str,
        service_model_name: str,
        service_model_version: str,
        trigger: bytes,
        actions: List[models.RICAction],
    ) -> Subscription:
        subscription_client = E2SubscriptionServiceStub(self._e2sub_channel)
        subscription = E2Subscription(
            id=str(uuid4()),
            app_id=self._app_id,
            details=SubscriptionDetails(
                e2_node_id=e2_node_id,
                service_model=E2SubServiceModel(
                    name=service_model_name, version=service_model_version
                ),
                event_trigger=EventTrigger(
                    payload=Payload(encoding=Encoding.ENCODING_PROTO, data=trigger)
                ),
            ),
        )
        for a in actions:
            action = Action(id=a.id, type=ActionType(a.type))
            if a.definition is not None:
                action.payload = Payload(
                    encoding=Encoding.ENCODING_PROTO, data=a.definition
                )
            if a.subsequent_action is not None:
                action.subsequent_action = SubsequentAction(
                    type=SubsequentActionType(a.subsequent_action.type),
                    time_to_wait=TimeToWait(a.subsequent_action.time_to_wait),
                )
            subscription.details.actions.append(action)

        await subscription_client.add_subscription(subscription=subscription)
        return Subscription(
            subscription.id,
            self._app_id,
            self._e2sub_channel,
            self._ssl_context,
        )

    async def unsubscribe(self, subscription_id: str) -> None:
        subscription_client = E2SubscriptionServiceStub(self._e2sub_channel)
        await subscription_client.remove_subscription(id=subscription_id)

    async def __aenter__(self) -> "E2Client":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._e2t_channel.close()
        self._e2sub_channel.close()
