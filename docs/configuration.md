# Configuration

The desk is added through the Home Assistant UI. There is nothing to add to
`configuration.yaml`.

## Add the desk

Power on the desk and make sure it is in range of a Bluetooth adapter or proxy. The desk accepts
one Bluetooth connection at a time, so if Home Assistant cannot connect, close the Desky app on
your phone.

### When Home Assistant discovers the desk

Home Assistant discovers desks whose Bluetooth name starts with `Desky`. A discovered desk shows
up under **Settings → Devices & services** as a new device to set up.

1. Select **Add** on the discovered desk.
2. Confirm that you want to set up the desk shown, with its name and Bluetooth address.

### Adding the desk yourself

1. Go to **Settings → Devices & services** and select **Add integration**.
2. Search for **Desky Standing Desk**.
3. If Home Assistant can see one or more desks that are not set up yet, select yours from the
   list. Each entry shows the desk's Bluetooth name and address. Desks that are already set up
   are not listed.
4. If it cannot see a new desk, enter the desk's Bluetooth address, for example
   `AA:BB:CC:DD:EE:FF`. You can find it under **Settings → Devices & services → Bluetooth** in
   the advertisement monitor, in an ESPHome Bluetooth proxy's log, or with a BLE scanner app such
   as nRF Connect. Home Assistant must be able to see a device at that address right now.

The address is six pairs of letters or digits separated by colons. Lower case, dashes or no
separators also work. Anything else shows *This is not a Bluetooth address. Use the form
AA:BB:CC:DD:EE:FF.*

You can add a desk this way even while Home Assistant shows it as discovered. The discovered
desk goes away once it is added.

### Connection check

However you add the desk, setup connects to it once before it finishes, then disconnects. If
Home Assistant cannot see the desk, or the desk does not accept the connection, the form shows
*Could not connect to the desk. Make sure it is powered on, in range and not connected to the
Desky app.* See [Troubleshooting](troubleshooting.md#adding-the-desk-fails), then submit again.

Each desk can only be added once. Adding the same desk again stops with *Device is already
configured*.

## What happens after setup

The integration connects to the desk and keeps the connection open. The device is named after
the desk's Bluetooth name, and its manufacturer, model, serial number and versions come from the
desk's Device Information service where the desk reports them. A desk that reports nothing useful
is shown as a Desky Standing Desk.

If the desk cannot be found or does not accept the connection when the integration loads, Home
Assistant shows one of these messages and retries in the background:

- *Could not find the desk at AA:BB:CC:DD:EE:FF. Make sure it is powered on and in Bluetooth
  range*
- *Could not connect to the desk at AA:BB:CC:DD:EE:FF*

See [Troubleshooting](troubleshooting.md) if it does not recover.

## Options

To change a desk's options, go to **Settings → Devices & services → Desky Standing Desk** and
select **Configure** on the desk's entry.

| Option | Default | Range | Description |
| --- | --- | --- | --- |
| Standing threshold | 95 cm | 60-130 cm, in steps of 1 cm | Height at or above which the desk counts as standing |

The threshold sets the [Posture](entities.md#posture) sensor, and through it the
[sitting and standing time](entities.md#standing-time-today-and-sitting-time-today) sensors and
the sit/stand reminder [blueprint](blueprints.md).

Saving the options reloads the desk: the integration disconnects, reconnects and applies the new
threshold. Today's sitting and standing times are kept. The posture is unknown until the desk
reports its height again.

## More than one desk

Add each desk separately. Each desk gets its own device and entities, and uses its own Bluetooth
connection slot.
