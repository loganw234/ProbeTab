# app/

The browser app. It will hold:

- one transport interface with four implementations: WebUSB, Web Serial,
  WebSocket and Web Bluetooth;
- the LabPro protocol, written once;
- sensor recognition and calibration;
- the interface.

Started 2026-11-15, with one file:

- [src/generated/labpro-facts.ts](src/generated/labpro-facts.ts) holds the
  LabPro facts.
- `tools/generate.py` makes it from `protocol/labpro-facts.toml`. Never edit it
  by hand.
- The gate fails if it drifts, and loads it through Node to compare every value.

Its licence is the one the folder table in [README.md](../README.md) gives it.
