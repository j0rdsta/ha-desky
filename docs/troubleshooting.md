# Troubleshooting

## The desk is not discovered

- Check that the desk is powered on. Press a button on the hand controller to wake it.
- Check that Home Assistant has a working Bluetooth adapter or proxy within range of the desk:
  **Settings → Devices & services → Bluetooth** lists them, and the advertisement monitor there
  shows the devices each one hears.
- Look for a device named `Desky…`. Only names that start with `Desky` are discovered
  automatically. If your desk has a different name, add it by its Bluetooth address instead (see
  [Configuration](configuration.md#adding-the-desk-yourself)).
- The desk accepts one Bluetooth connection at a time. Close the Desky app on any phone or tablet.

## Setup keeps retrying

If setup fails with *Could not find the desk* or *Could not connect to the desk*, Home Assistant
keeps retrying in the background. Check the points above, then:

- Make sure a Bluetooth proxy near the desk has a free connection slot (see below).
- Restart the desk by unplugging it for 10 seconds.

## The desk becomes unavailable

When the connection drops, every entity of the desk becomes unavailable and the log gets one
warning:

```text
The desk at AA:BB:CC:DD:EE:FF is unavailable
```

The integration reconnects on its own when the desk advertises again (see
[Connection loss and reconnecting](data-updates.md#connection-loss-and-reconnecting)). Failed
attempts are logged at debug level only, so a long outage does not fill the log. When the desk is back, the
log gets one info line:

```text
The desk at AA:BB:CC:DD:EE:FF is available again
```

If the desk stays unavailable, work through [Setup keeps retrying](#setup-keeps-retrying).

## A command fails

Home Assistant does not run commands on unavailable entities. If the connection drops just as a
command is sent, the command fails with:

- **The desk is not connected**: the desk was not connected when the command was sent.
- **Could not send the command to the desk: …**: the Bluetooth write failed. The rest of the
  message is the error from the Bluetooth stack.

An automation records either as an error, and stops unless the step uses `continue_on_error`.

## The height is wrong or does not update

- **Heights are 2.54 times too small or too large.** The desk reports heights in its display
  unit, and the integration converts inches to centimetres. Turn on debug logging and look for the
  `Display unit response:` line after the desk connects, and the raw `Received notification:`
  frames next to it, then report them in an issue.
- **The height does not change while the desk moves.** Turn on debug logging and move the desk.
  You should see `Height notification (0x98 0x98):` or `Status notification (0xF2 0xF2 0x01 0x03):`
  lines with the height in cm. If you only see `Unknown notification format:` lines, your
  controller uses a format the integration does not know yet. Please report it, with the raw
  frames.

## ESPHome Bluetooth proxies

The integration works through ESPHome Bluetooth proxies. Configure the proxy with
`bluetooth_proxy` and `active: true`, so it can make connections, not just pass on
advertisements:

```yaml
esp32_ble_tracker:

bluetooth_proxy:
  active: true
```

The desk stays connected, so it holds one of the proxy's connection slots for as long as it is
loaded. An ESP32 proxy has three slots by default. If every slot is taken by other devices, the
desk cannot connect and stays unavailable. Free a slot, or add
another proxy near the desk.

## Debug logging

Debug logs show every frame the desk sends. Turn them on in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.desky_desk: debug
```

Restart Home Assistant, reproduce the problem, then download the log from **Settings → System →
Logs**. You can also turn on debug logging without a restart from the integration's page in
**Settings → Devices & services**, and turn it off again to download the log.

Useful lines:

| Log line | Meaning |
| --- | --- |
| `Received notification: …` | A raw frame from the desk, in hex |
| `Height notification (0x98 0x98): … cm` | A movement height frame, decoded |
| `Status notification (0xF2 0xF2 0x01 0x03): … cm` | A status height frame, decoded |
| `Display unit response: cm` or `in` | The unit the desk's display uses |
| `Unknown notification format: …` | A frame the integration does not understand |
| `Could not reconnect to the desk at …, retrying in … seconds` | A failed reconnect attempt |

When you [report an issue](https://github.com/j0rdsta/ha-desky/issues), include the relevant
lines, your desk model if you know it, and whether you connect through a proxy.
