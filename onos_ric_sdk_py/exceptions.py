# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

from __future__ import absolute_import

from typing import Optional


class OnosRicSdkPyError(Exception):
    """Base class for all *onos_ric_sdk_py* errors."""

    pass


class DuplicateRouteError(OnosRicSdkPyError):
    """Raised if more than one route has the same method and path."""

    pass


class ClientError(OnosRicSdkPyError):
    """Base class for all client errors."""

    pass


class ClientStoppedError(ClientError):
    """Raised if a client is used before it's started.
    Args:
        msg: The exception message.
    """

    def __init__(self, msg: Optional[str] = None) -> None:
        if msg is None:
            msg = "The client cannot be used before it's started"
        super().__init__(msg)


class ClientRuntimeError(ClientError):
    """Raised if a client operation fails.
    Args:
        msg: The exception message.
    """

    def __init__(self, msg: Optional[str] = None) -> None:
        if msg is None:
            msg = "An issue with the client occurred at runtime"
        super().__init__(msg)
