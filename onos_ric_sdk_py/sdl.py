# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import json
import ssl
from typing import AsyncIterator, List, Optional

import aiomsa.abc
from grpclib.client import Channel
from onos_api.topo import (
    E2Cell,
    EqualFilter,
    EventType,
    Filter,
    Filters,
    RanEntityKinds,
    RanRelationKinds,
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

    async def get_cell_ids(self, e2_node_id: str) -> List[str]:
        client = TopoStub(self._topo_channel)
        filters = Filters(
            kind_filters=[
                Filter(equal=EqualFilter(value=RanRelationKinds.CONTAINS.name))
            ]
        )

        cell_ids = []
        list_response = await client.list(filters=filters)
        for obj in list_response.objects:
            if obj.relation.src_entity_id != e2_node_id:
                continue

            get_response = await client.get(id=obj.relation.tgt_entity_id)
            if get_response.object.entity.kind_id != RanEntityKinds.E2CELL.name:
                continue

            aspects = get_response.object.aspects["onos.topo.E2Cell"].value
            e2_cell = E2Cell().from_json(aspects)
            cell_ids.append(e2_cell.cell_object_id)

        return cell_ids

    async def watch_e2_connections(self) -> AsyncIterator[aiomsa.abc.E2Node]:
        client = TopoStub(self._topo_channel)
        filters = Filters(
            kind_filters=[
                Filter(equal=EqualFilter(value=RanRelationKinds.CONTROLS.name))
            ]
        )

        async for response in client.watch(filters=filters):
            event = response.event
            if event.type == EventType.ADDED or event.type == EventType.NONE:
                e2_node_id = event.object.relation.tgt_entity_id
                get_response = await client.get(id=e2_node_id)
                aspects = get_response.object.aspects["onos.topo.E2Node"].value

                ran_functions = []
                for v in json.loads(aspects.decode())["serviceModels"].values():
                    ran_functions.append(
                        aiomsa.abc.RanFunction(
                            id=v.get("name", ""),
                            oid=v["oid"],
                            definition=v.get("ranFunctions", [{}])[0],
                        )
                    )

                yield aiomsa.abc.E2Node(id=e2_node_id, ran_functions=ran_functions)

    async def __aenter__(self) -> "SDLClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._topo_channel.close()
