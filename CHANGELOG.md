# Changelog

## [2.0.0](https://github.com/j0rdsta/ha-desky/compare/v1.1.0...v2.0.0) (2026-10-09)


### ⚠ BREAKING CHANGES

* Entities changed. Update automations that use them.
    - The Collision sensitivity and Touch mode selects now use the states `high`/`medium`/`low` and `one_press`/`press_and_hold`. Update automations that compare or set them: setting an old label such as "High" now fails with an error. The labels shown are unchanged.
    - The LED color and Vibration intensity display sensors are removed. Use the LED strip light's effect instead of the LED color sensor.
    - The Vibration intensity number is removed: the desk does not support setting or reporting vibration intensity. The Vibration switch still turns vibration on and off.
    - Entity attributes are removed. Read the matching entities instead: the Height display sensor and Height number, the Upper and Lower height limit numbers, the LED strip light and the Vibration switch.
    - The Height display sensor has a fixed unit and long-term statistics, and no longer follows the desk's display unit. If it showed inches before the upgrade, Home Assistant keeps showing inches, converted from centimetres with full precision (for example 31.496… instead of 31.5), so templates that compare the state as text may need updating; otherwise it shows centimetres. To change the unit, open the entity's settings. New installs on US customary units show inches automatically.

### Features

* colour wheel for the LED strip ([#47](https://github.com/j0rdsta/ha-desky/issues/47)) ([77f8e19](https://github.com/j0rdsta/ha-desky/commit/77f8e19223abf1d4664e662ad1616591c11dbb2e))
* translated select states and a distance height sensor ([#43](https://github.com/j0rdsta/ha-desky/issues/43)) ([352dd05](https://github.com/j0rdsta/ha-desky/commit/352dd050501627a3870e3fb6f8292a40e0363255))


### Bug Fixes

* config flow picks discovered desks ([#38](https://github.com/j0rdsta/ha-desky/issues/38)) ([9576b26](https://github.com/j0rdsta/ha-desky/commit/9576b262dbb8dc15389704ca5733c4e90595e287))
* keep height limits within the desk's range ([#46](https://github.com/j0rdsta/ha-desky/issues/46)) ([44e8ffa](https://github.com/j0rdsta/ha-desky/commit/44e8ffaf6a954c2514be683062e2694ecef1f976))
* keep the close task guard for overlapping drops ([#53](https://github.com/j0rdsta/ha-desky/issues/53)) ([235c1cb](https://github.com/j0rdsta/ha-desky/commit/235c1cb781a5eac38b981bfdc19fbaf94da3d808))
* log at the levels Home Assistant expects and remove dead code ([#52](https://github.com/j0rdsta/ha-desky/issues/52)) ([bfd25ee](https://github.com/j0rdsta/ha-desky/commit/bfd25ee17f78c8d4b5cd716252ad5d44d275cc83))
* read collision sensitivity from the settings block ([#45](https://github.com/j0rdsta/ha-desky/issues/45)) ([27f83a7](https://github.com/j0rdsta/ha-desky/commit/27f83a79344c1997374868b086cb4e8108539c41))
* release the Bluetooth connection when connecting fails ([#39](https://github.com/j0rdsta/ha-desky/issues/39)) ([e60ca38](https://github.com/j0rdsta/ha-desky/commit/e60ca380bcde78e5a24f7f67db55853228850904))
* send commands with the official app's timing ([#50](https://github.com/j0rdsta/ha-desky/issues/50)) ([2cee908](https://github.com/j0rdsta/ha-desky/commit/2cee908141accc098efed8b881acc538fd5eb1f6))
* treat LED colour 0 as off ([#44](https://github.com/j0rdsta/ha-desky/issues/44)) ([a8622e4](https://github.com/j0rdsta/ha-desky/commit/a8622e47f6893e7d8fd8d55fca39c91849cf188d))
* update entities when the desk confirms a setting ([#42](https://github.com/j0rdsta/ha-desky/issues/42)) ([57957db](https://github.com/j0rdsta/ha-desky/commit/57957db18a4a382853760958fb01060782a4aa98))
* validate light effects and height limits ([#40](https://github.com/j0rdsta/ha-desky/issues/40)) ([4cc5069](https://github.com/j0rdsta/ha-desky/commit/4cc50690946732b3c724f0b5f5739fe7a01ac498))


### Documentation

* make the quality scale claims and docs hold ([#51](https://github.com/j0rdsta/ha-desky/issues/51)) ([0196f5a](https://github.com/j0rdsta/ha-desky/commit/0196f5a8517434841d2e132ebe0974d60f556af3))

## [1.1.0](https://github.com/j0rdsta/ha-desky/compare/v1.0.1...v1.1.0) (2026-10-08)


### Features

* add automation blueprints ([#31](https://github.com/j0rdsta/ha-desky/issues/31)) ([7b49513](https://github.com/j0rdsta/ha-desky/commit/7b495136d39a3b413c7bb018edc58b7281fd1b6a))
* add diagnostics, brand icon and quality scale record ([#29](https://github.com/j0rdsta/ha-desky/issues/29)) ([fbbeab6](https://github.com/j0rdsta/ha-desky/commit/fbbeab6585d4ac70b62b7acccd137252c40e9399))
* add move to height and height limit actions ([#27](https://github.com/j0rdsta/ha-desky/issues/27)) ([538f26c](https://github.com/j0rdsta/ha-desky/commit/538f26c83b64a4d67dcfe77fa3914604bc91d315))
* add sit/stand posture tracking ([#30](https://github.com/j0rdsta/ha-desky/issues/30)) ([355cc58](https://github.com/j0rdsta/ha-desky/commit/355cc584890d80f1ed5db72731f4ad631496b059))
* modernise config entry lifecycle and entity naming ([#18](https://github.com/j0rdsta/ha-desky/issues/18)) ([ff38f94](https://github.com/j0rdsta/ha-desky/commit/ff38f94b867c8e43a44abf4e253f14617f978f0b))
* reconnect when the desk reappears and raise errors for failed commands ([#25](https://github.com/j0rdsta/ha-desky/issues/25)) ([a96415d](https://github.com/j0rdsta/ha-desky/commit/a96415ded1a5f2c10d2d2339bb32e67b51a48a20))


### Bug Fixes

* do not reconnect or warn while Home Assistant stops ([#33](https://github.com/j0rdsta/ha-desky/issues/33)) ([cc4803a](https://github.com/j0rdsta/ha-desky/commit/cc4803a878afa56570c90f723c124283cbfcd4fb))
* stop false collisions and read heights correctly in inch mode ([#24](https://github.com/j0rdsta/ha-desky/issues/24)) ([cff3427](https://github.com/j0rdsta/ha-desky/commit/cff3427bc48bc0971467a11203b75d11b92b5d10))


### Documentation

* add documentation site ([#28](https://github.com/j0rdsta/ha-desky/issues/28)) ([df0728e](https://github.com/j0rdsta/ha-desky/commit/df0728e114fa82c024fb3ed91ed2279acf78649d))
* complete the documentation site and rewrite the README ([#32](https://github.com/j0rdsta/ha-desky/issues/32)) ([2f72b7e](https://github.com/j0rdsta/ha-desky/commit/2f72b7e7074495b9e565a7d877bc28970e2ee46f))
* plain-language pass over the documentation ([#36](https://github.com/j0rdsta/ha-desky/issues/36)) ([e2636f9](https://github.com/j0rdsta/ha-desky/commit/e2636f991587bcf05be07ff15a11b15ae323fefb))
* tighten the README introduction ([#35](https://github.com/j0rdsta/ha-desky/issues/35)) ([3c0e5e6](https://github.com/j0rdsta/ha-desky/commit/3c0e5e64dfd6dbd5b909e38a2ee38da0ec231dcc))
