# onos-ric-sdk-py

Python Application SDK for ONOS RIC (µONOS Architecture)

## Description

This SDK contains two modules, E2 and SDL.

The SDK uses a sidecar proxy which implements the client side distributed system
and load-balancing logic necessary to communicate to the RIC.

### E2 module

The E2 module contains functions that interact with E2 nodes. Apps can subscribe
and unsubscribe to service models, and apps can send E2 control messages to
make changes to E2 nodes. The E2 module interacts with the e2t mode

### SDL module

The SDL module contains functions to get topology information from the RIC, for
entities such as E2 nodes and cells. This module to also includes functions to
read and write properties for E2 nodes and cells.

## Developing

Run lint/licensing/static checks: `make lint`

Run unit tests (via `pytest`): `make test`
