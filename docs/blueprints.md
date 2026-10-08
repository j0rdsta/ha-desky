# Blueprints

Blueprints turn the common desk automations into a form you fill in. Select a button to
import a blueprint into your Home Assistant, then go to Settings → Automations & scenes →
Blueprints and select it to create an automation. The desk fields only offer Desky entities.

The notification field takes the name of a notify action, such as
`notify.mobile_app_your_phone`. It defaults to `persistent_notification.create`, which shows
the message in Home Assistant itself.

## Sit/stand reminder

[![Import the sit/stand reminder blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fsit_stand_reminder.yaml)

Reminds you to stand once the posture sensor has said **Sitting** for a set number of minutes
(60 by default), only between a start and end time and on chosen weekdays. Leave the start and
end time the same to be reminded at any time of day. Time while the desk is unavailable does not
count: the timer starts again when the desk comes back.

## Scheduled stand

[![Import the scheduled stand blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fscheduled_stand.yaml)

Moves the desk at set times on chosen weekdays, to one of its presets or, with no preset chosen,
to a height in centimetres. Choose a person so the desk only moves while they are home. Read
[Safety](safety.md) before you use it.

## Collision alert

[![Import the collision alert blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fcollision_alert.yaml)

Sends a notification naming the desk when its [collision sensor](entities.md#collision-detected)
turns on.
