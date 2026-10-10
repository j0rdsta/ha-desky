# Blueprints

Blueprints turn the common desk automations into a form you fill in. Select a button to
import a blueprint into your Home Assistant, then go to Settings → Automations & scenes →
Blueprints and select it to create an automation. The desk fields only offer Desky entities.

The notification field takes the name of a notify action, such as
`notify.mobile_app_your_phone`. It defaults to `persistent_notification.create`, which shows
the message in Home Assistant itself.

If you keep automations in YAML, each blueprint below has an example automation with every input
filled in. The import saves a blueprint as `j0rdsta/<file name>`, which is the `path` in the
examples; if you saved it under another name, use that instead.

## Sit/stand reminder

[![Import the sit/stand reminder blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fsit_stand_reminder.yaml)

Reminds you to stand once the posture sensor has said **Sitting** for a set number of minutes
(60 by default), only between a start and end time and on chosen weekdays. Leave the start and
end time the same to be reminded at any time of day. Time while the desk is unavailable does not
count: the timer starts again when the desk comes back.

This one reminds you after 45 minutes of sitting, between 9:00 and 17:00 on weekdays:

```yaml
alias: Sit/stand reminder
use_blueprint:
  path: j0rdsta/sit_stand_reminder.yaml
  input:
    posture_sensor: sensor.desky_desk_posture
    sitting_minutes: 45
    notify_action: notify.mobile_app_your_phone
    start_time: "09:00:00"
    end_time: "17:00:00"
    weekdays: [mon, tue, wed, thu, fri]
```

## Scheduled stand

[![Import the scheduled stand blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fscheduled_stand.yaml)

Moves the desk at set times on chosen weekdays, to one of its presets or, with no preset chosen,
to a height in centimetres. Choose a person so the desk only moves while they are home. Read
[Safety](safety.md) before you use it.

This one raises the desk to preset 2 at 10:00 and 15:00 on weekdays, while `person.you` is home.
To move to a height instead, leave out `preset_button`, or set it to `""`, and set `height`:

```yaml
alias: Scheduled stand
use_blueprint:
  path: j0rdsta/scheduled_stand.yaml
  input:
    desk: cover.desky_desk
    preset_button: button.desky_desk_preset_2
    height: 110
    times: ["10:00", "15:00"]
    weekdays: [mon, tue, wed, thu, fri]
    person: person.you
```

## Collision alert

[![Import the collision alert blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fcollision_alert.yaml)

Sends a notification naming the desk when its [collision sensor](entities.md#collision-detected)
turns on.

This one sends the alert to your phone:

```yaml
alias: Collision alert
use_blueprint:
  path: j0rdsta/collision_alert.yaml
  input:
    collision_sensor: binary_sensor.desky_desk_collision_detected
    notify_action: notify.mobile_app_your_phone
```
