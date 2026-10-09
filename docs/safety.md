# Safety

!!! danger "Use at your own risk"
    A standing desk is motorised furniture. This integration is unofficial and has no affiliation
    with, endorsement from or support by Desky. The authors accept no responsibility for damage to
    property, personal injury, loss of warranty or any malfunction resulting from its use. See the
    [licence](https://github.com/j0rdsta/ha-desky/blob/main/LICENSE).

## Hazards

- **Crushing and pinch points.** Keep hands, feet, children and pets away from the frame, the
  legs and the space under the desktop while it moves.
- **Collisions.** Keep the space above and below the desk clear of shelves, window sills, chairs,
  drawers and cables.
- **Unexpected movement.** A remote command or an automation can move the desk when nobody
  expects it.

Always follow the manufacturer's safety guidance, and keep the desk's hand controller within
reach.

## What the integration does and does not do

- When you stop the desk from Home Assistant, it sends **stop** twice, 50 ms apart, without the
  wake-up handshake that precedes other commands. A stop is never held up by another command's
  pauses.
- In press-and-hold touch mode, Move up, Move down, opening or closing the cover and the presets
  repeat their command every 100 ms until you stop the desk, it stops on its own, or 60 seconds
  pass.
- A command that cannot reach the desk fails with an error, so an automation records the failure
  instead of carrying on as if the desk moved.
- The collision sensor is inferred from how a commanded movement ends (see
  [limitations](supported-devices.md#known-limitations)). It is information, not a safety device,
  and reacts after the desk has stopped.
- It cannot make the desk stop faster than the desk's own anti-collision system. Set the desk's
  collision sensitivity to suit your setup.
- The move to height action refuses heights outside the height limits set on the desk. Set
  limits that keep the desk clear of fixed obstacles.

## Automating the desk

Before you write an automation that moves the desk:

1. **Require presence.** Only move the desk when a presence or occupancy sensor shows someone at it,
   ideally for a minute or more. Remember pets and children who may be under the desk.
2. **Warn first.** Send a notification, flash a light or play a sound, then wait a few seconds
   and check presence again before moving.
3. **Prefer prompts to automatic movement.** An actionable notification that asks before raising
   or lowering the desk is safer than a timed movement.
4. **Limit when it runs.** Restrict automations that move the desk to the hours someone works
   at it.
5. **Keep a manual override.** Use an input boolean to turn desk automations off, and turn them
   off when nobody is home.
6. **Test with care.** Test new automations with small movements first, with the area clear and
   the hand controller in reach.

The [use cases](use-cases.md) follow these rules.
