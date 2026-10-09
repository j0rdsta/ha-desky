# Entities

Every desk is one device in Home Assistant, and all its entities belong to that device. Entity
names are translated and prefixed with the device name, which is the desk's Bluetooth name. The
entity IDs on this page are for a desk named "Desky Desk"; yours follow your desk's name.
Entities created by earlier versions of the integration keep their existing entity IDs.
Version 2.0.0 removed the LED color and Vibration intensity display sensors, which repeated other
entities, and the Vibration intensity number, which the desk does not support. Setting up the desk
deletes them.

All entities are enabled by default, and unavailable while the desk is not connected.
Entities have no attributes of their own. Each value has its own entity.

Heights are in centimetres, whatever unit the desk's display shows. To see the Height display
sensor in inches, change its unit in the entity's settings.

Not every desk has every feature, but the entities are created anyway. For a feature the desk
does not report, the entity shows unknown or a default value (see
[Supported devices](supported-devices.md#supported-desks)).

## Summary

Category is the section of the device page that lists the entity: **Controls**, **Sensors**,
**Configuration** or **Diagnostic**.

| Entity | Entity ID | Platform | Unit | Category |
| --- | --- | --- | --- | --- |
| Desky Desk | `cover.desky_desk` | Cover | % | Controls |
| Height | `number.desky_desk_height` | Number | cm | Controls |
| Presets 1 to 4 | `button.desky_desk_preset_1` … `_4` | Button | | Controls |
| Move up | `button.desky_desk_move_up` | Button | | Controls |
| Move down | `button.desky_desk_move_down` | Button | | Controls |
| LED strip | `light.desky_desk_led_strip` | Light | | Controls |
| Lock | `switch.desky_desk_lock` | Switch | | Controls |
| Height display | `sensor.desky_desk_height_display` | Sensor | cm | Sensors |
| Posture | `sensor.desky_desk_posture` | Sensor | | Sensors |
| Standing time today | `sensor.desky_desk_standing_time_today` | Sensor | min | Sensors |
| Sitting time today | `sensor.desky_desk_sitting_time_today` | Sensor | min | Sensors |
| Upper height limit | `number.desky_desk_upper_height_limit` | Number | cm | Configuration |
| Lower height limit | `number.desky_desk_lower_height_limit` | Number | cm | Configuration |
| Vibration | `switch.desky_desk_vibration` | Switch | | Configuration |
| Collision sensitivity | `select.desky_desk_collision_sensitivity` | Select | | Configuration |
| Touch mode | `select.desky_desk_touch_mode` | Select | | Configuration |
| Display unit | `select.desky_desk_display_unit` | Select | | Configuration |
| Collision detected | `binary_sensor.desky_desk_collision_detected` | Binary sensor | | Diagnostic |

## Movement

### Desk (cover)

The main control, named after the desk.

- **Open** raises the desk, **close** lowers it and **stop** stops it.
- **Position** maps 60-130 cm to 0-100 %, whatever the desk's own range or height limits.
  Setting a position moves the desk to the matching height. Positions outside the desk's limits
  move the desk to the nearest allowed height.
- The cover is **closed** when its position is 0 %, that is below about 60.7 cm, since the
  position is rounded down to a whole percent.
- While a movement commanded from Home Assistant is under way, it shows **opening** or
  **closing** to match its direction, so Home Assistant keeps the other direction's button
  available. Movements made with the hand controller update the position but not the opening or
  closing state.

### Height

The desk's current height in centimetres, to 0.1 cm, from 60 to 130 cm. Setting a value moves
the desk to that height. A height outside the desk's limits fails with an error, and the desk
does not move. To move to a height in an automation, you can also use the
[`move_to_height` action](actions.md#move-to-height). In press-and-hold touch mode the target
repeats until the desk gets there.

### Presets 1 to 4

Moves the desk to the height saved in that preset. Presets are saved on the hand controller; the
integration can only recall them. In one-press touch mode one command takes the desk all the
way. In press-and-hold touch mode the integration holds the button: the command repeats until the
desk arrives or you press stop.

### Move up and Move down

Starts the desk moving up or down, the same as opening or closing the cover. Stop it with the
cover's stop. The buttons stay available whatever the cover's state. In every touch mode the
integration holds the button, as the official app does: the command repeats until you press stop,
the desk reaches the end of its travel, or 60 seconds pass.

### Collision detected

On when a movement commanded from Home Assistant stops early or bounces back, which the integration
reads as a collision. It turns off after 10 seconds, or sooner if the desk disconnects or a later
commanded movement runs normally more than 2 seconds after the collision. Movements made with the
hand controller are never reported as collisions. The desk does not report collisions over
Bluetooth, so the sensor is inferred and is not a safety device (see [Safety](safety.md)).

Device class: problem.

## Height and posture

### Height display

The desk's height, to 0.1 cm, whatever unit the desk's display shows. It is in centimetres unless
you pick another unit in the entity's settings. If it showed inches before version 2.0.0, it keeps
showing inches. On a new install where Home Assistant uses US customary units, it shows inches
from the start. It is unknown until the desk has reported a height.

Device class: distance, state class: measurement. It is recorded in long-term statistics.

### Posture

**Sitting** or **Standing**, from the height the desk stops at. The desk counts as standing when
it stops at or above the standing threshold (95 cm unless changed in the
[options](configuration.md#options)), and as sitting when it stops below it.

The posture follows the height only once the desk has stayed at the same height for 2 seconds
and no movement commanded from Home Assistant is under way, so a desk that passes the threshold
without stopping does not change posture. After the desk connects, the state is unknown until
the desk has reported a height and stayed at it for those 2 seconds.

Device class: enum, with the states `sitting` and `standing`. Use these values in automations.

### Standing time today and Sitting time today

Minutes spent in each posture today. Only time while the desk is connected and its posture is
known counts.

- A change of posture counts from when the desk stopped in the new posture.
- Both totals reset at local midnight, including on a day whose midnight a clock change skips.
- They keep their value across a Home Assistant restart or a reload of the desk on the same day.
- They update every minute and whenever the desk reports a change.

Device class: duration, state class: total, with `last_reset` set to the start of the local day.
They are recorded in long-term statistics, so a statistics graph can show each day's total (see
[Use cases](use-cases.md#track-sitting-and-standing-time)).

## Desk settings

### Upper height limit and Lower height limit

The highest and lowest heights the desk will move to, stored on the desk's control box. From 60
to 124 cm in steps of 1 cm, the range the desk accepts. On a desk whose display shows inches, the
range is 24 to 48 in, shown as 61.0 to 121.9 cm. The desk stores whole centimetres, or whole
inches, so a value is rounded to the nearest whole unit before it is sent: on a desk that shows
inches, 74 cm is sent as 29 in and shows as 73.7 cm. Setting a value writes the limit to the desk
and reads the limits back. A limit that is not set shows as unknown. The desk only tightens a
limit that is already set, so, as the official app does, the integration clears both limits and
sets both again; setting one limit keeps the other.

If the other limit is set, the upper limit must be above it and the lower limit below it.
Otherwise setting the value fails with an error, and nothing is sent to the desk. To set or clear
limits from an automation, use the [actions](actions.md).

### Vibration

Turns the desk's vibration on or off.

### Lock

Locks the desk's controls. The switch changes as soon as the command is sent. The desk's reply
then confirms it, or switches it back.

### Collision sensitivity

How sensitive the desk's own anti-collision system is: **High**, **Medium** or **Low**. The states
are `high`, `medium` and `low`. Use these values in automations. The desk does not confirm the
change, so the integration asks for its settings again after changing it. The select changes when
the desk reports the new value.

### Touch mode

The hand controller's touch mode: **One press** or **Press and hold**. The states are `one_press`
and `press_and_hold`. Use these values in automations. The desk does not confirm the change, so
the integration asks for its settings again after changing it. If the desk ignored the change, it
is sent once more, and if the desk ignores it again, the change fails with an error. In **Press
and hold** mode the desk
moves to a preset or a height only while the command keeps arriving, so the integration repeats
those commands every 100 ms (see [Command timing](protocol.md#command-timing)). Move up and Move
down repeat in both modes.

### Display unit

The unit the desk's display shows: **cm** or **in**, with the states `cm` and `in`. It changes
only the desk's own display; entities keep using centimetres. The integration asks for the desk's
settings again after changing it, sends the change once more if the desk ignored it, and fails
with an error if it is ignored again. It also picks up a change made on the hand controller.

## LED strip

### LED strip (light)

Turns the desk's LED strip on or off and sets its brightness and colour. The colours are also
effects: **White**, **Red**, **Green**, **Blue**, **Yellow** and **Party mode**. Any other effect
fails with an error, and nothing is sent to the desk.

The light has a colour wheel (colour mode `hs`). The desk has only five fixed colours, so a colour
you pick snaps to the nearest one:

- A colour with a saturation below 30 % is **White**.
- Any other colour is the nearest of **Red** (hue 0), **Yellow** (60), **Green** (120) or
  **Blue** (240) round the colour wheel. A hue exactly between two colours goes to the one below
  it: 30 is red, 90 yellow, 180 green and 300 blue.

A colour given as RGB, XY or a colour name is converted to a hue and saturation first, so it snaps
the same way. The desk has one white, so any colour temperature sets **White**. If you give both an
effect and a colour, the effect wins.

The light reports its colour as the desk's colour, not the one you picked: pick a light blue and it
shows Blue, hue 240 and saturation 100 %. In Party mode the colours change on their own, so the
light reports no colour.

The colour wheel also reaches bridges that pick a device type from the light's colour modes, such
as the HomeKit bridge and Matter bridges (for example Home Assistant Matter Hub). Before version
2.0.0 they showed the LED strip as a dimmable light with no colour. Matter and HomeKit fix an
accessory's type when it is created, so after upgrading the bridge may show the LED strip as a new
colour light accessory. Assign its room again and update any scenes or automations in Apple Home or
your other controller that used the old one.

The desk takes brightness in whole percent. The brightness is rounded to the nearest percent, and
a light that is on is never sent as 0 %.

The desk reports an LED that is off as colour 7, or as colour 0 once the Desky app has turned it
off. Both show the light as off. If you then turn the light on without an effect, it goes back to
the last colour you chose other than party mode. That colour is kept across restarts.
