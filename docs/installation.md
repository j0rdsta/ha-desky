# Installation

The integration is in the [HACS](https://hacs.xyz/) default store. You can also copy it into your
configuration directory by hand.

Before you start, check the [requirements](index.md#requirements). If an
[Upsy Desky](supported-devices.md#upsy-desky) is fitted to the desk, disconnect it first.

## HACS (recommended)

1. In Home Assistant, open **HACS**.
2. Search for **Desky Standing Desk**, open it and select **Download**.
3. Restart Home Assistant.

This button opens the integration in HACS directly:

[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=j0rdsta&repository=ha-desky&category=integration)

HACS tells you when a new release is available. Releases are listed on the
[GitHub releases page](https://github.com/j0rdsta/ha-desky/releases), with a changelog.

## Manual installation

1. Download the source of the
   [latest release](https://github.com/j0rdsta/ha-desky/releases/latest).
2. Copy the `custom_components/desky_desk` folder into the `custom_components` folder of your
   Home Assistant configuration directory (the folder that holds `configuration.yaml`). Create
   `custom_components` if it does not exist.
3. Restart Home Assistant.

To update a manual installation, replace the `desky_desk` folder with the one from the new
release and restart Home Assistant.

## Next step

[Add the desk to Home Assistant](configuration.md).
