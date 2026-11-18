# hardware/

The bridge's schematics, board files and enclosure, from version 1. Version 0
is an off-the-shelf ESP32-S3 board with a separate USB-to-UART port, such as
Espressif's ESP32-S3-DevKitC-1, and needs no files here.

Version 1's files are not started (2026-11-15). Their licence is the one the
folder table in [README.md](../README.md) gives this folder.

## The board in use

The project's first board is a Lonely Binary ESP32-S3 N16R8, not a
DevKitC-1. Its bring-up, on 2026-11-17, found:

- **The chip:** an ESP32-S3 (QFN56), revision v0.2, with 8 MB of embedded
  PSRAM and 16 MB of flash (MEASURED, esptool 5.6.0).
- **The UART port** goes through a WCH CH340K, USB vendor 1A86 and product
  7522 (MEASURED, Windows' device list). The ROM's boot banner comes out
  there, and the chip is flashed through it (MEASURED), so it is BELIEVED to
  carry the chip's first UART, which the ROM uses. In the bridge's design it
  is the computer's port.
- **The Main USB port** is the chip's own USB. Running Espressif's
  `usb_host_lib` example from ESP-IDF v6.1.1, the chip read USB devices'
  descriptors through it as a USB host (MEASURED: the UART port was on the
  computer throughout, so the devices were on Main USB). In the bridge's
  design it is the LabPro's port.
- **Main USB had no 5 V until a solder pad was bridged.** The owner's meter
  read 0 V on it before he bridged a pad at the bottom of the board, and 5 V
  after, as he reported them ("0v" and "5v"). The board is BELIEVED to have
  been powered from its UART port alone at the time. The pad's label is not
  recorded.
- **While that pad is bridged,** nothing that supplies power, such as a
  computer, a charger or a powered hub, goes into Main USB while the UART
  port is connected. On a similar clone board, the matching pad joins the
  two ports' 5 V lines (READ, [that board's notes](https://github.com/deepcoder/YD-ESP32-23)).
  This board's circuit is not read, so for it that is BELIEVED.
- **The host test:** a low-speed USB mouse, through a USB-C video adapter,
  was found and read six times in five minutes (MEASURED).
  - The adapter's charging port was empty (the owner's word), so the adapter
    and the mouse ran on Main USB's power.
  - The adapter is BELIEVED to hold a USB hub, which the example cannot
    show: the USB library in use lists every device as on the root port.
  - After two attaches six seconds apart, the mouse was found again, at a
    new address, every 61.4 seconds, four times (MEASURED). The example logs
    no disconnects, and why this happened is not determined.
- **For the LabPro,** the owner plans a plain USB-C to USB-B cable, "to avoid
  issues". That the LabPro's port is USB-B is BELIEVED; it is not yet in the
  facts file.
