# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

import json
import ssl
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Type

import betterproto
from grpclib import GRPCError
from grpclib.client import Channel
from onos_api.topo import (
    E2Cell,
    E2Node,
    EqualFilter,
    EventType,
    Filter,
    Filters,
    KpmRanFunction,
    MhoRanFunction,
    RanEntityKinds,
    RanRelationKinds,
    RcRanFunction,
    RelationFilter,
    RsmRanFunction,
    TopoStub,
)

from .exceptions import ClientRuntimeError, ClientStoppedError


class SDLClient:
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
        self._ready = True

    async def get_cells(self, e2_node_id: str) -> List[E2Cell]:
        """Get the cells corresponding to the given E2 node ID.

        Args:
            e2_node_id: The target E2 node ID.

        Returns:
            A list of cells that belong to ``e2_node_id``.

        Raises:
            ClientStoppedError: The underlying client resources have not been started.
            ClientRuntimeError: There was an error performing the request.
        """
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

        cells = []
        try:
            response = await client.list(filters=filters)
            for obj in response.objects:
                if obj.entity.kind_id != RanEntityKinds.E2CELL.name.lower():
                    continue

                aspects = obj.aspects["onos.topo.E2Cell"].value
                e2_cell = E2Cell().from_json(aspects)
                cells.append(e2_cell)
            return cells
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def _get_cell_entity_id(
        self, e2_node_id: str, cell_global_id: str
    ) -> Optional[str]:
        """
        given e2_node_id and cell_global_id, returns entity id
        returns None if cell_global_id is not found
        """
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

        try:
            response = await client.list(filters=filters)
            for obj in response.objects:
                if obj.entity.kind_id != RanEntityKinds.E2CELL.name.lower():
                    continue

                aspects = obj.aspects["onos.topo.E2Cell"].value
                e2_cell = E2Cell().from_json(aspects)
                if e2_cell.cell_global_id.value == cell_global_id:
                    return obj.id
        except GRPCError as e:
            raise ClientRuntimeError() from e

        return None

    async def get_cell_data(
        self, e2_node_id: str, cell_id: str, keys: List[str]
    ) -> Optional[List[Optional[bytes]]]:
        """
        get data referenced by key attached to a cell_id, if available
        otherwise returns None
        """

        if not self._ready:
            raise ClientStoppedError()

        entity_id = await self._get_cell_entity_id(e2_node_id, cell_id)
        if entity_id is None:
            return None

        client = TopoStub(self._topo_channel)
        try:
            resp = await client.get(id=entity_id)
        except GRPCError as e:
            raise ClientRuntimeError() from e

        data: List[Optional[bytes]] = []
        for k in keys:
            type_data = resp.object.aspects.get(k)
            if type_data is None:
                data.append(None)
            else:
                data.append(type_data.value)

        return data

    async def set_cell_data(
        self, e2_node_id: str, cell_id: str, key_data_map: Dict[str, bytes]
    ) -> None:
        """
        set data referenced by key attached to a cell_id
        remove data referenced by key if data is None

        raises ClientRuntimeError if data cannot be saved
        """

        if not self._ready:
            raise ClientStoppedError()

        entity_id = await self._get_cell_entity_id(e2_node_id, cell_id)
        if entity_id is None:
            raise ClientRuntimeError(
                f"cannot find cell_id:{cell_id} in e2_node:{e2_node_id}"
            )

        client = TopoStub(self._topo_channel)
        try:
            resp = await client.get(id=entity_id)
        except GRPCError as e:
            raise ClientRuntimeError() from e

        op_count = 0
        for key, data in key_data_map.items():
            if data is None:
                if key not in resp.object.aspects:
                    pass
                else:
                    del resp.object.aspects[key]
                    op_count += 1
            else:
                resp.object.aspects[key] = betterproto.lib.google.protobuf.Any(
                    key, data
                )
                op_count += 1

        if op_count == 0:
            return

        try:
            await client.update(object=resp.object)
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def watch_e2_connections(self) -> AsyncIterator[Tuple[str, E2Node]]:
        """Stream for newly available E2 node connections.

        Yields:
            An available E2 node and its ID.

        Raises:
            ClientStoppedError: The underlying client resources have not been started.
            ClientRuntimeError: There was an error performing the request.
        """
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
                if event.type in (EventType.ADDED, EventType.NONE):
                    e2_node_id = event.object.relation.tgt_entity_id
                    get_response = await client.get(id=e2_node_id)
                    aspects = get_response.object.aspects["onos.topo.E2Node"].value

                    # Also decode manually because betterproto can't parse 'Any' from JSON
                    e2_node = E2Node().from_json(aspects)
                    e2_node_json = json.loads(aspects.decode())

                    for oid, sm in e2_node_json["serviceModels"].items():
                        ran_functions = []
                        for func_dict in sm.get("ranFunctions", []):
                            type_url = func_dict.pop("@type")
                            if type_url.endswith("KPMRanFunction"):
                                func: Any = KpmRanFunction().from_dict(func_dict)
                            elif type_url.endswith("MHORanFunction"):
                                func = MhoRanFunction().from_dict(func_dict)
                            elif type_url.endswith("RCRanFunction"):
                                func = RcRanFunction().from_dict(func_dict)
                            elif type_url.endswith("RSMRanFunction"):
                                func = RsmRanFunction().from_dict(func_dict)
                            else:
                                raise ValueError(f"Unknown RAN function: {type_url}")

                            ran_functions.append(func)

                        e2_node.service_models[oid].ran_functions = ran_functions

                    yield e2_node_id, e2_node
        except GRPCError as e:
            raise ClientRuntimeError() from e

    async def __aenter__(self) -> "SDLClient":
        """Create any underlying resources required for the client to run."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Cleanly stop all underlying resources used by the client."""
        self._topo_channel.close()
        self._ready = False
