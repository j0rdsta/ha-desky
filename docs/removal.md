# Removal

Removing the integration closes the Bluetooth connection to the desk. The desk itself keeps its
presets, height limits and other settings, and works from its hand controller and the Desky app
as before.

## Remove a desk

1. Go to **Settings → Devices & services** and open **Desky Standing Desk**.
2. Open the menu next to the desk's entry and select **Delete**.

Repeat for every desk you added. Automations, scripts and dashboards that use the desk's
entities or actions stop working, so remove or update them as well.

## Remove the integration files

After deleting every desk:

- **HACS:** open **HACS**, find **Desky Standing Desk**, open its menu and select **Remove**,
  then restart Home Assistant.
- **Manual installation:** delete the `custom_components/desky_desk` folder from your
  configuration directory, then restart Home Assistant.

If you turned on debug logging for the integration, remove the `custom_components.desky_desk`
line from the `logger` section of `configuration.yaml`.
