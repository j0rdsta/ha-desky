# Use cases

Ideas for using the desk in Home Assistant. The examples use the entity IDs of a desk named
"Desky Desk", such as `cover.desky_desk` and `button.desky_desk_preset_1`; yours are named after
your desk. Read [Safety](safety.md) before you automate movement.

## Sit and stand from a dashboard

The cover entity gives you raise, lower, stop and a position slider, where 0 % is 60 cm and
100 % is 130 cm. The preset buttons recall the heights saved on the hand controller.

```yaml
type: entities
title: Standing desk
entities:
  - entity: cover.desky_desk
  - entity: number.desky_desk_height
  - entity: button.desky_desk_preset_1
    name: Sitting
  - entity: button.desky_desk_preset_2
    name: Standing
```

## Voice control

Expose the cover to Assist, Google Assistant or Alexa, and say "open the desk" to raise it or
"close the desk" to lower it. A position ("set the desk to 60 %") moves it to that point of the
60-130 cm range. Give the cover an alias such as "standing desk" so the commands sound natural.

## Go to an exact height

The `desky_desk.move_to_height` action moves the desk to a height in centimetres. It fails with
an error if the desk is not connected or the height is outside its limits.

```yaml
action: desky_desk.move_to_height
target:
  entity_id: cover.desky_desk
data:
  height: 105
```

## Standing reminders

Remind yourself to stand, and let the notification ask before it moves the desk. This example
assumes an occupancy sensor at the desk, `binary_sensor.office_occupied`, and the Home Assistant
companion app.

```yaml
alias: Standing reminder
triggers:
  - trigger: state
    entity_id: binary_sensor.office_occupied
    to: "on"
    for:
      minutes: 45
conditions:
  - condition: numeric_state
    entity_id: number.desky_desk_height
    below: 90
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

The height entity is recorded like any other sensor. A
[history stats](https://www.home-assistant.io/integrations/history_stats/) sensor based on a
template binary sensor that is on above your standing threshold counts the time you stand each
day.

## Get told about collisions

The collision binary sensor turns on when a commanded movement stops early or bounces back, and
clears itself after 10 seconds.

```yaml
alias: Desk collision
triggers:
  - trigger: state
    entity_id: binary_sensor.desky_desk_collision_detected
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Desk collision
      message: The desk stopped early. Check what is under or above it.
```

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
