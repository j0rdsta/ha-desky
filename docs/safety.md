# Safety

!!! danger "Use at your own risk"
    A standing desk is motorised furniture. This integration is unofficial and has no affiliation
    with, endorsement from or support by Desky. The authors accept no responsibility for damage to
    property, personal injury, loss of warranty or any malfunction resulting from its use. See the
    [licence](https://github.com/j0rdsta/ha-desky/blob/main/LICENSE).

## Hazards

- **Crushing and pinch points.** Keep hands, feet, children and pets away from the frame, the
  legs and the space under the desktop while it moves.
- **Collisions.** Make sure the space above and below the desk is clear: shelves, window sills,
  chairs, drawers and cables.
- **Unexpected movement.** A remote command or an automation can move the desk when nobody
  expects it.

Always follow the manufacturer's safety guidance, and keep the desk's hand controller within
reach.

## What the integration does and does not do

- It sends **stop** at once, without waiting for anything else, when you stop the desk from Home
  Assistant.
- A command that cannot reach the desk fails with an error, so an automation records the failure
  instead of carrying on as if the desk moved.
- The **collision** sensor is inferred from how a commanded movement ends (see
  [limitations](supported-devices.md#known-limitations)). It is information, not a safety device.
  It reacts after the desk has stopped, and does not see movements made with the hand controller.
- It cannot make the desk stop faster than the desk's own anti-collision system. Set the desk's
  collision sensitivity to suit your setup.
- Height limits set on the desk apply to every movement, including those started from Home
  Assistant. Use them to keep the desk clear of fixed obstacles.

## Automating the desk

Before you write an automation that moves the desk:

1. **Require presence.** Only move the desk when someone is at it, confirmed by a presence or
   occupancy sensor, and preferably for a minute or more. Remember pets and children who may be
   under the desk.
2. **Warn first.** Send a notification, flash a light or play a sound, then wait a few seconds
   and check presence again before moving.
3. **Prefer prompts to automatic movement.** An actionable notification that asks before raising
   or lowering the desk is safer than a timed movement.
4. **Keep a manual override.** Use an input boolean to turn desk automations off, and turn them
   off when nobody is home.
5. **Test with care.** Test new automations with small movements first, with the area clear and
   the hand controller in reach.

The [use cases](use-cases.md) follow these rules.
