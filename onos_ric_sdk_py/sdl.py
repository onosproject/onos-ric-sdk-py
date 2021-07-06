# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import json
import ssl
from typing import AsyncIterator, List, Optional

import aiomsa.abc
from aiomsa.exceptions import ClientRuntimeError, ClientStoppedError
from grpclib import GRPCError
from grpclib.client import Channel
from onos_api.topo import (
    E2Cell,
    EqualFilter,
    EventType,
    Filter,
    Filters,
    RanEntityKinds,
    RanRelationKinds,
    RelationFilter,
    TopoStub,
)


class SDLClient(aiomsa.abc.SDLClient):
    def __init__(
        self,
        topo_endpoint: str,
        ca_path: Optional[str] = None,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        skip_verify: bool = True,
        **kwargs: str,
    ) -> None:
        ssl_context = None
        if ca_path is not None and cert_path is not None and key_path is not None:
            ssl_context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=ca_path
            )
            ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            ssl_context.check_hostname = not skip_verify

        topo_ip, topo_port = topo_endpoint.rsplit(":", 1)
        self._topo_channel = Channel(topo_ip, int(topo_port), ssl=ssl_context)
        self._ready = True

    async def get_cell_ids(self, e2_node_id: str) -> List[str]:
        if not self._ready:
            raise ClientStoppedError()

        client = TopoStub(self._topo_channel)
        filters = Filters(
            relation_filter=RelationFilter(
                src_id=e2_node_id,
                relation_kind=RanRelationKinds.CONTAINS.name.lower(),
                target_kind="",
            )
        )

        cell_ids = []
        try:
            response = await client.list(filters=filters)
            for obj in response.objects:
                if obj.entity.kind_id != RanEntityKinds.E2CELL.name.lower():
                    continue

                aspects = obj.aspects["onos.topo.E2Cell"].value
                e2_cell = E2Cell().from_json(aspects)
                cell_ids.append(e2_cell.cell_object_id)

            return cell_ids
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def watch_e2_connections(self) -> AsyncIterator[aiomsa.abc.E2Node]:
        if not self._ready:
            raise ClientStoppedError()

        client = TopoStub(self._topo_channel)
        filters = Filters(
            kind_filter=Filter(
                equal=EqualFilter(value=RanRelationKinds.CONTROLS.name.lower())
            )
        )

        try:
            async for response in client.watch(filters=filters):
                event = response.event
                if event.type == EventType.ADDED or event.type == EventType.NONE:
                    e2_node_id = event.object.relation.tgt_entity_id
                    get_response = await client.get(id=e2_node_id)
                    aspects = get_response.object.aspects["onos.topo.E2Node"].value

                    ran_functions = []
                    e2_node = json.loads(aspects.decode())
                    for service_model_info in e2_node["serviceModels"].values():
                        ran_functions.append(
                            aiomsa.abc.RanFunction(
                                id=service_model_info.get("name", ""),
                                oid=service_model_info["oid"],
                                definition=service_model_info.get("ranFunctions", [{}])[
                                    0
                                ],
                            )
                        )

                    yield aiomsa.abc.E2Node(id=e2_node_id, ran_functions=ran_functions)
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def __aenter__(self) -> "SDLClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._topo_channel.close()
        self._ready = False
