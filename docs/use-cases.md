# Use cases

The examples on this page use the entity IDs of a desk named "Desky Desk", such as
`cover.desky_desk` and `button.desky_desk_preset_1`; yours are named after your desk. They treat
preset 1 as your sitting height and preset 2 as your standing height. Read [Safety](safety.md)
before you automate movement.

Each automation example is the YAML of a whole automation: create a new automation, choose
**Edit in YAML** from its menu, and paste it in. Then replace the entity IDs, and the notify
action, with your own.

## Sit and stand from a dashboard

The cover entity gives you raise, lower, stop and a [position slider](entities.md#desk-cover). The
preset buttons recall the heights saved on the hand controller, and the posture sensor shows whether
you are sitting or standing.

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

Opening the cover raises the desk all the way. To stand and sit at your preset heights with Assist,
add sentences of your own. This automation presses preset 2 when you say "stand up" or "raise the
desk", presses preset 1 for "sit down" or "lower the desk", and answers you. Square brackets mark
optional words.

```yaml
alias: Desk voice commands
triggers:
  - trigger: conversation
    command:
      - stand up
      - raise [the] desk
    id: stand
  - trigger: conversation
    command:
      - sit down
      - lower [the] desk
    id: sit
actions:
  - action: button.press
    target:
      entity_id: >-
        {{ 'button.desky_desk_preset_2' if trigger.id == 'stand'
           else 'button.desky_desk_preset_1' }}
  - set_conversation_response: >-
      {{ 'Raising' if trigger.id == 'stand' else 'Lowering' }} the desk.
mode: single
```

Sentences like these work with Assist only. A voice command moves the desk wherever you are, so
read [automating the desk](safety.md#automating-the-desk) first.

## Go to an exact height

The [`desky_desk.move_to_height`](actions.md#move-to-height) action moves the desk to a height in
centimetres. It fails with an error if the desk is not connected or the height is outside its
limits.

To reuse a height from dashboards and automations, wrap the action in a script. Create a script,
choose **Edit in YAML**, and paste this in. Saved, it is `script.desk_to_height`, and running it
asks for a height.

```yaml
alias: Desk to height
fields:
  height:
    name: Height
    description: The height to move the desk to.
    required: true
    selector:
      number:
        min: 60
        max: 130
        step: 0.5
        unit_of_measurement: cm
sequence:
  - action: desky_desk.move_to_height
    target:
      entity_id: cover.desky_desk
    data:
      height: "{{ height }}"
mode: single
```

A dashboard button then moves the desk to 105 cm with one tap:

```yaml
type: button
name: Desk to 105 cm
icon: mdi:desk
tap_action:
  action: perform-action
  perform_action: script.desk_to_height
  data:
    height: 105
```

See [automating the desk](safety.md#automating-the-desk) before you put movement on a dashboard.

## Standing reminders

For a plain reminder, import the [sit/stand reminder blueprint](blueprints.md#sitstand-reminder).
It goes off once the posture sensor has shown **Sitting** for a set time.

To have the reminder offer to raise the desk, write the automation yourself. This example waits
until the posture sensor has said **Sitting** for 45 minutes, asks on your phone, and only moves the
desk if you accept and you are still there. It assumes an occupancy sensor at the desk,
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

## Stand for meetings

Stand through your meetings. A minute before an event on your calendar starts, this automation
asks on your phone whether to raise the desk, and when the event ends it asks whether to lower it.
It only asks while you are at the desk, sitting before a meeting or standing after one, and it only
moves the desk if you accept and you are still there. It assumes a calendar, `calendar.work`, the
occupancy sensor and the companion app.

```yaml
alias: Stand for meetings
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.work
    offset: "-0:1:0"
    id: start
  - trigger: calendar
    event: end
    entity_id: calendar.work
    id: end
conditions:
  - condition: state
    entity_id: binary_sensor.office_occupied
    state: "on"
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: start
          - condition: state
            entity_id: sensor.desky_desk_posture
            state: sitting
        sequence:
          - action: notify.mobile_app_your_phone
            data:
              message: "{{ trigger.calendar_event.summary }} starts in a minute. Stand up?"
              data:
                actions:
                  - action: DESK_MEETING_STAND
                    title: Raise the desk
          - wait_for_trigger:
              - trigger: event
                event_type: mobile_app_notification_action
                event_data:
                  action: DESK_MEETING_STAND
            timeout:
              minutes: 2
            continue_on_timeout: false
          - condition: state
            entity_id: binary_sensor.office_occupied
            state: "on"
          - action: button.press
            target:
              entity_id: button.desky_desk_preset_2
      - conditions:
          - condition: trigger
            id: end
          - condition: state
            entity_id: sensor.desky_desk_posture
            state: standing
        sequence:
          - action: notify.mobile_app_your_phone
            data:
              message: "{{ trigger.calendar_event.summary }} has ended. Sit down?"
              data:
                actions:
                  - action: DESK_MEETING_SIT
                    title: Lower the desk
          - wait_for_trigger:
              - trigger: event
                event_type: mobile_app_notification_action
                event_data:
                  action: DESK_MEETING_SIT
            timeout:
              minutes: 5
            continue_on_timeout: false
          - condition: state
            entity_id: binary_sensor.office_occupied
            state: "on"
          - action: button.press
            target:
              entity_id: button.desky_desk_preset_1
mode: single
```

To stand only for some events, add a condition on the event's title. This one keeps events with
"meeting" in the title:

```yaml
  - condition: template
    value_template: "{{ 'meeting' in trigger.calendar_event.summary | lower }}"
```

See [automating the desk](safety.md#automating-the-desk) before you let a calendar move the desk.

## Track sitting and standing time

The **Standing time today** and **Sitting time today** sensors add up the minutes in each posture,
reset at midnight, and are recorded in long-term statistics. A statistics graph shows each day's
totals:

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

The posture follows the [standing threshold](configuration.md#options). See
[Entities](entities.md#height-and-posture) for how posture and time are counted.

## Daily standing goal

Get told when you reach a standing goal for the day. This automation sends a notification once
**Standing time today** passes 120 minutes. It goes off once a day at most, because the total only
rises during the day and starts again from 0 at midnight.

```yaml
alias: Standing goal reached
triggers:
  - trigger: numeric_state
    entity_id: sensor.desky_desk_standing_time_today
    above: 120
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Standing goal reached
      message: You have stood for 2 hours today.
mode: single
```

## Get told about collisions

Import the [collision alert blueprint](blueprints.md#collision-alert) to get a notification when
the [collision sensor](entities.md#collision-detected) turns on.

To do more than notify, write the automation yourself. On a desk with an LED strip, this one also
turns the strip red while the sensor is on. It saves the strip's state in a scene first, and
restores it when the sensor turns off again, at most 10 seconds later.

```yaml
alias: Desk collision alert
triggers:
  - trigger: state
    entity_id: binary_sensor.desky_desk_collision_detected
    from: "off"
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Desk collision
      message: The desk stopped early. Check what is under or above it.
  - action: scene.create
    data:
      scene_id: desk_light_before_collision
      snapshot_entities:
        - light.desky_desk_led_strip
  - action: light.turn_on
    target:
      entity_id: light.desky_desk_led_strip
    data:
      effect: Red
  - wait_template: "{{ is_state('binary_sensor.desky_desk_collision_detected', 'off') }}"
    timeout:
      minutes: 1
  - action: scene.turn_on
    target:
      entity_id: scene.desk_light_before_collision
mode: single
```

## Lock the desk when nobody is home

Lock the hand controller when everyone leaves, so children or pets cannot move the desk. The same
automation unlocks it when someone comes home.

```yaml
alias: Lock the desk when away
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
    id: away
  - trigger: state
    entity_id: zone.home
    from: "0"
    not_to:
      - unavailable
      - unknown
    id: home
actions:
  - if:
      - condition: trigger
        id: away
    then:
      - action: switch.turn_on
        target:
          entity_id: switch.desky_desk_lock
    else:
      - action: switch.turn_off
        target:
          entity_id: switch.desky_desk_lock
mode: single
```

## Use the LED strip as a status light

On desks with an LED strip, change its colour to show a status, such as a meeting in progress or
a door left open.

The strip shows white, red, green, blue or yellow. Pick one by effect, or by colour: any colour is
snapped to the nearest of the five. This automation turns the strip red while a door sensor,
here `binary_sensor.front_door`, shows the door open, and back to white when it closes.

```yaml
alias: Desk light shows an open door
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door
    to: ["on", "off"]
actions:
  - action: light.turn_on
    target:
      entity_id: light.desky_desk_led_strip
    data:
      effect: "{{ 'Red' if trigger.to_state.state == 'on' else 'White' }}"
```

## Show your posture on the LED strip

The strip can show your posture too: green while you stand, white while you sit, and yellow once
you have sat for 45 minutes, as a nudge to stand. The automation only changes the colour while the
strip is on, so turning the strip off silences it.

```yaml
alias: Desk light shows posture
triggers:
  - trigger: state
    entity_id: sensor.desky_desk_posture
    to: standing
    id: standing
  - trigger: state
    entity_id: sensor.desky_desk_posture
    to: sitting
    id: sitting
  - trigger: state
    entity_id: sensor.desky_desk_posture
    to: sitting
    for:
      minutes: 45
    id: long_sit
conditions:
  - condition: state
    entity_id: light.desky_desk_led_strip
    state: "on"
actions:
  - action: light.turn_on
    target:
      entity_id: light.desky_desk_led_strip
    data:
      effect: >-
        {{ {'standing': 'Green', 'sitting': 'White', 'long_sit': 'Yellow'}[trigger.id] }}
mode: single
```

The strip has one colour at a time, so pick either this or another status light, such as the
open-door example above. Two automations that set the colour would overwrite each other.
