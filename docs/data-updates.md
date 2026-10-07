# How data updates

The integration is a local push integration: it keeps a Bluetooth connection open to the desk,
and the desk sends changes over it as they happen. A slow poll fills the gaps.

## On connecting

When the desk connects, the integration:

1. Subscribes to the desk's notifications.
2. Sends the handshake, which enables movement commands.
3. Asks for the desk's status. The desk replies with its height and, because the request follows
   a handshake, its settings block (display unit, touch mode, collision sensitivity and presets).
4. Asks for the lighting, vibration, lock, collision sensitivity and height limit settings. A
   query the desk does not answer is ignored.
5. Reads the standard Bluetooth Device Information service for the manufacturer, model, serial
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

Every 30 seconds the integration asks the desk for its status. This keeps the height current
when the desk was moved while a notification was missed, and checks that the connection still
works: a status request that cannot be sent closes the connection, and the reconnect logic takes
over.

The poll sends no handshake, so it does not wake the desk's display. The first poll after each connection is
different: a desk connected within about a second of powering up ignores the settings request it
gets while connecting, so if the display unit or touch mode is still unknown, the first poll asks
for the settings again. It asks once per connection, because asking wakes the display.

A poll while the desk is disconnected sends nothing and is not reported as an error.

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
