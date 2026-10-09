# How data updates

The integration is a local push integration: it keeps a Bluetooth connection open to the desk,
and the desk sends changes over it as they happen. It also polls the desk after 30 seconds
without an update.

## On connecting

When the desk connects, the integration:

1. Subscribes to the desk's notifications.
2. Sends the handshake, which enables movement commands, and asks for the desk's status
   together. The desk replies with its height and, because the request follows a handshake, its
   settings block (display unit, touch mode, collision sensitivity and presets).
3. Asks for the lighting, vibration, lock and height limit settings. The queries go out 200 ms
   apart, as the official Desky app spaces them. A query the desk does not answer is ignored. The
   collision sensitivity comes from the settings block in step 2.
4. Reads the standard Bluetooth Device Information service for the manufacturer, model, serial
   number and versions shown on the device page.

## Push updates

The desk sends a notification:

- with its height about every 200 ms while it moves;
- in reply to every status request and setting query;
- with its settings block, including the display unit, when the unit is changed on the hand
  controller.

Each notification updates the entities straight away. Movement state, the cover's opening and
closing state, and collision detection are worked out from the stream of heights.

## Polling

When 30 seconds pass without an update from the desk, the integration asks the desk for its
status. Every update restarts the 30-second timer, so a desk that is moving or answering commands
is not polled, and a quiet desk is polled about every 30 seconds.

The poll catches height changes whose notification was missed. It also checks the connection: if
the request cannot be sent, the integration closes the connection and the reconnect logic takes
over.

The poll sends no handshake, so it does not wake the desk's display. A desk connected within about
a second of powering up ignores the settings request sent while connecting. If the display unit,
touch mode or collision sensitivity is still unknown at the first poll after a connection, that
poll asks for the settings again. It asks only once per connection, because asking wakes the display.

A poll while the desk is disconnected sends nothing and is not reported as an error. A poll while
a movement command is being held (repeated) sends nothing either, so it cannot hold up the repeats;
the moving desk reports its height anyway.

## Connection loss and reconnecting

- If the connection drops, all entities become unavailable.
- The integration listens for the desk's Bluetooth advertisements. As soon as any adapter or
  proxy hears the desk, it reconnects through that one.
- If a reconnect attempt fails, it waits 5 seconds before trying again, doubling the wait up to
  2 minutes, and resetting it after a successful connection. Advertisements do not cut a wait
  short.
- When Home Assistant stops seeing the desk's advertisements while it is still connected, the
  integration asks for its status, and only closes the connection if that fails, because a
  connected desk may stop advertising.

See [Troubleshooting](troubleshooting.md#the-desk-becomes-unavailable) for what this looks like in
the log.
