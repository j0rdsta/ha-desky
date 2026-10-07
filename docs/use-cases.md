# Use cases

Ideas for using the desk in Home Assistant. The examples use the entity IDs of a desk named
"Desky Desk", such as `cover.desky_desk` and `button.desky_desk_preset_1`; yours are named after
your desk. Read [Safety](safety.md) before you automate movement.

For a sit/stand reminder, a scheduled stand or a collision alert, import one of the
[blueprints](blueprints.md) instead of writing the YAML yourself.

## Sit and stand from a dashboard

The cover entity gives you raise, lower, stop and a position slider, where 0 % is 60 cm and
100 % is 130 cm. The preset buttons recall the heights saved on the hand controller, and the
posture sensor shows whether you are sitting or standing.

```yaml
type: entities
title: Standing desk
entities:
  - entity: cover.desky_desk
  - entity: number.desky_desk_height
  - entity: sensor.desky_desk_posture
  - type: section
    label: Presets
  - entity: button.desky_desk_preset_1
    name: Sitting
  - entity: button.desky_desk_preset_2
    name: Standing
  - type: section
    label: Manual controls
  - entity: button.desky_desk_move_up
  - entity: button.desky_desk_move_down
  - type: section
    label: Status
  - entity: binary_sensor.desky_desk_collision_detected
```

## Voice control

Expose the cover to Assist, Google Assistant or Alexa, and say "open the desk" to raise it or
"close the desk" to lower it. A position ("set the desk to 60 %") moves it to that point of the
60-130 cm range. Give the cover an alias such as "standing desk" so the commands sound natural.

## Go to an exact height

The [`desky_desk.move_to_height`](actions.md#move-to-height) action moves the desk to a height in
centimetres. It fails with an error if the desk is not connected or the height is outside its
limits.

```yaml
action: desky_desk.move_to_height
target:
  entity_id: cover.desky_desk
data:
  height: 105
```

## Standing reminders

For a plain reminder, import the [sit/stand reminder blueprint](blueprints.md#sitstand-reminder).
It uses the posture sensor, so it knows when you have been sitting, not just how long you have
been at the desk.

To have the reminder offer to raise the desk, write the automation yourself. This example waits
until the posture sensor has said **Sitting** for 45 minutes, asks on your phone, and only moves
the desk if you accept and you are still at it. It assumes an occupancy sensor at the desk,
`binary_sensor.office_occupied`, and the Home Assistant companion app.

```yaml
alias: Standing reminder
triggers:
  - trigger: state
    entity_id: sensor.desky_desk_posture
    to: sitting
    for:
      minutes: 45
conditions:
  - condition: state
    entity_id: binary_sensor.office_occupied
    state: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: You have been sitting for 45 minutes. Stand up?
      data:
        actions:
          - action: DESK_STAND
            title: Raise the desk
  - wait_for_trigger:
      - trigger: event
        event_type: mobile_app_notification_action
        event_data:
          action: DESK_STAND
    timeout:
      minutes: 5
    continue_on_timeout: false
  - condition: state
    entity_id: binary_sensor.office_occupied
    state: "on"
  - action: button.press
    target:
      entity_id: button.desky_desk_preset_2
mode: single
```

## Track sitting and standing time

The integration counts this for you. The **Standing time today** and **Sitting time today**
sensors add up the minutes in each posture, reset at midnight, and are recorded in long-term
statistics. A statistics graph shows each day's totals:

```yaml
type: statistics-graph
title: Sitting and standing
entities:
  - entity: sensor.desky_desk_standing_time_today
    name: Standing
  - entity: sensor.desky_desk_sitting_time_today
    name: Sitting
chart_type: bar
period: day
stat_types:
  - change
days_to_show: 14
```

The posture follows the [standing threshold](configuration.md#options), 95 cm unless you change
it. See [Entities](entities.md#height-and-posture) for how posture and time are counted.

## Get told about collisions

The collision binary sensor turns on when a commanded movement stops early or bounces back.
Import the [collision alert blueprint](blueprints.md#collision-alert) to get a notification when
it does.

## Lock the desk when nobody is home

Lock the hand controller when everyone leaves, so children or pets cannot move the desk. A
second automation can turn the switch off when someone comes home.

```yaml
alias: Lock the desk when away
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.desky_desk_lock
```

## Use the LED strip as a status light

On desks with an LED strip, change its colour to show something at a glance, such as a meeting
in progress or a door left open.
