# Actions

The integration adds three actions. Use them in automations and scripts, or try them in
**Developer tools → Actions**.

| Action | What it does |
| --- | --- |
| [`desky_desk.move_to_height`](#move-to-height) | Moves the desk to a height in cm |
| [`desky_desk.set_height_limit`](#set-height-limit) | Sets the upper or lower height limit |
| [`desky_desk.clear_height_limits`](#clear-height-limits) | Removes both height limits |

To move to a saved preset, press its button entity instead, for example
`button.desky_desk_preset_1` (see [Entities](entities.md#presets-1-to-4)).

## Targeting a desk

Every action targets one or more desks through their cover entity, for example
`cover.desky_desk`. You can also target a desk's device, or an area that contains it. The entity
picker only offers Desky desk covers.

A desk that cannot take the command makes the action fail with an error, even while its entities are
unavailable. Every targeted desk is checked before any command is sent, so a call that is rejected
for one desk sends nothing to any of them.

## Move to height

`desky_desk.move_to_height` moves the desk to a height.

| Field | Required | Description |
| --- | --- | --- |
| `height` | Yes | The height to move to, in cm, to 0.1 cm |

The height must be within the desk's height limits, using 60 or 130 cm for a limit that is not
set. A limit the desk reports below 60 cm or above 130 cm counts as 60 or 130 cm.

```yaml
action: desky_desk.move_to_height
target:
  entity_id: cover.desky_desk
data:
  height: 105
```

## Set height limit

`desky_desk.set_height_limit` sets the desk's upper or lower height limit. The limit is stored on
the desk's control box.

| Field | Required | Description |
| --- | --- | --- |
| `limit` | Yes | `upper` or `lower` |
| `height` | Yes | The height of the limit, in cm, from 60 to 130 |

If the other limit is set, the upper limit must be above the lower one. After setting the limit,
the integration reads the limits back from the desk, so the
[limit entities](entities.md#upper-height-limit-and-lower-height-limit) show what the desk reports.

```yaml
action: desky_desk.set_height_limit
target:
  entity_id: cover.desky_desk
data:
  limit: upper
  height: 120
```

## Clear height limits

`desky_desk.clear_height_limits` removes both height limits from the desk, then reads the limits
back. It has no fields.

```yaml
action: desky_desk.clear_height_limits
target:
  entity_id: cover.desky_desk
```

## Errors

An action that cannot run fails with one of these messages. In an automation, the failure stops
the run unless the step uses `continue_on_error`.

| Message | Cause |
| --- | --- |
| *The action does not target a Desky desk* | The target contains no Desky desk |
| *The desk … is not loaded* | The desk's entry is not set up, for example while setup is retrying |
| *… cm is outside the desk's allowed range of …-… cm* | `move_to_height` with a height outside the desk's limits |
| *… cm is outside the range a limit can be set to, 60.0-130.0 cm* | `set_height_limit` with a height outside 60-130 cm |
| *The upper limit of … cm must be above the lower limit of … cm* | `set_height_limit` with an upper limit at or below the lower limit |
| *The lower limit of … cm must be below the upper limit of … cm* | `set_height_limit` with a lower limit at or above the upper limit |
| *The desk is not connected* | The desk is set up but not connected |
| *Could not send the command to the desk: …* | The Bluetooth write failed. The rest of the message is the error from the Bluetooth stack |

All but the last two are validation errors, raised before anything is sent to any desk.
