# Entities

Every desk is one device in Home Assistant, and all its entities belong to that device. Entity
names are translated and prefixed with the device name, which is the desk's Bluetooth name. The
entity IDs on this page are for a desk named "Desky Desk"; yours follow your desk's name.
Entities created by earlier versions of the integration keep their existing entity IDs.

All entities are enabled by default, and unavailable while the desk is not connected.

Heights are in centimetres, whatever unit the desk's display shows. The one exception is the
Height display sensor, which follows the display unit.

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
| Height display | `sensor.desky_desk_height_display` | Sensor | cm or in | Sensors |
| Posture | `sensor.desky_desk_posture` | Sensor | | Sensors |
| Standing time today | `sensor.desky_desk_standing_time_today` | Sensor | min | Sensors |
| Sitting time today | `sensor.desky_desk_sitting_time_today` | Sensor | min | Sensors |
| Upper height limit | `number.desky_desk_upper_height_limit` | Number | cm | Configuration |
| Lower height limit | `number.desky_desk_lower_height_limit` | Number | cm | Configuration |
| Vibration intensity | `number.desky_desk_vibration_intensity` | Number | % | Configuration |
| Vibration | `switch.desky_desk_vibration` | Switch | | Configuration |
| Collision sensitivity | `select.desky_desk_collision_sensitivity` | Select | | Configuration |
| Touch mode | `select.desky_desk_touch_mode` | Select | | Configuration |
| Display unit | `select.desky_desk_display_unit` | Select | | Configuration |
| Collision detected | `binary_sensor.desky_desk_collision_detected` | Binary sensor | | Diagnostic |
| LED color | `sensor.desky_desk_led_color` | Sensor | | Diagnostic |
| Vibration intensity display | `sensor.desky_desk_vibration_intensity_display` | Sensor | % | Diagnostic |

## Movement

### Desk (cover)

The main control, named after the desk.

- **Open** raises the desk, **close** lowers it and **stop** stops it.
- **Position** maps 60-130 cm to 0-100 %, whatever the desk's own range or height limits.
  Setting a position moves the desk to the matching height.
- The cover is **closed** when its position is 0 %, that is below about 60.7 cm, since the
  position is rounded down to a whole percent.
- While a movement commanded from Home Assistant is under way, it shows **opening** or
  **closing** to match its direction, so Home Assistant keeps the other direction's button
  available. Movements made with the hand controller update the position but not the opening or
  closing state.

### Height

The desk's current height in centimetres, to 0.1 cm, from 60 to 130 cm. Setting a value moves
the desk to that height. To move to a height in an automation and get an error for a height
outside the desk's limits, use the [`move_to_height` action](actions.md#move-to-height).

### Presets 1 to 4

Moves the desk to the height saved in that preset. Presets are saved on the hand controller; the
integration can only recall them.

### Move up and Move down

Starts the desk moving up or down, the same as opening or closing the cover. Stop it with the
cover's stop. The buttons stay available whatever the cover's state.

### Collision detected

On when a movement commanded from Home Assistant stops early or bounces back, which the integration
reads as a collision. It turns off after 10 seconds, or sooner if the desk disconnects or a later
commanded movement runs normally more than 2 seconds after the collision. Movements made with the
hand controller are never reported as collisions. The desk does not report collisions over
Bluetooth, so the sensor is inferred and is not a safety device (see [Safety](safety.md)).

Device class: problem.

## Height and posture

### Height display

The desk's height in the unit its display shows: centimetres or inches, to 0.1. Attributes:

| Attribute | Meaning |
| --- | --- |
| `height_cm` | The height in centimetres |
| `upper_limit_cm`, `lower_limit_cm` | The height limits in centimetres, present while at least one limit is set; a limit that is not set is `null` |

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
to 130 cm in steps of 1 cm. Setting a value writes the limit to the desk and reads the limits
back. A limit that is not set shows as unknown.

Attribute `limits_enabled`: true while at least one limit is set.

If the other limit is set, the upper limit must be above it and the lower limit below it.
Otherwise setting the value fails with an error, and nothing is sent to the desk. To set or clear
limits from an automation, use the [actions](actions.md).

### Vibration intensity

The strength of the desk's vibration, from 0 to 100 %. Setting it reads the value back from the
desk.

### Vibration

Turns the desk's vibration on or off. Attribute `intensity`: the vibration intensity in %, when
the desk has reported it.

### Lock

Locks the desk's controls.

### Collision sensitivity

How sensitive the desk's own anti-collision system is: **High**, **Medium** or **Low**.

### Touch mode

The hand controller's touch mode: **One press** or **Press and hold**. The desk does not confirm
the change, so the integration asks for its settings again after changing it.

### Display unit

The unit the desk's display shows: **cm** or **in**. Only the Height display sensor follows this
setting. The integration asks for the desk's settings again after changing it, and also picks up a
change made on the hand controller.

## LED strip

### LED strip (light)

Turns the desk's LED strip on or off and sets its brightness. The colours are effects: **White**,
**Red**, **Green**, **Blue**, **Yellow** and **Party mode**. Any other effect fails with an error,
and nothing is sent to the desk.

The desk takes brightness in whole percent. The brightness is rounded to the nearest percent, and
a light that is on is never sent as 0 %.

If the desk reports its colour as off and you turn the light on without an effect, it goes back to
the last colour you chose other than party mode. That colour is kept across restarts. Attribute
`color_name`: the current colour.

### LED color

The LED strip's current colour as text: White, Red, Green, Blue, Yellow, Party mode or Off, and
Unknown until the desk has reported it. Attributes:

| Attribute | Meaning |
| --- | --- |
| `color_value` | The colour code the desk reports, 1-7 |
| `brightness` | The brightness in %, as the desk reports it |
| `lighting_enabled` | Whether the LED strip is on |

### Vibration intensity display

The vibration intensity in %, as a sensor, or 0 until the desk has reported it. Attribute
`vibration_enabled`: whether vibration is on.
