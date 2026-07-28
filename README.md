# Overlay Scenes for Home Assistant

Overlay Scenes lets Home Assistant automations temporarily layer behavior over
real lights, switches, and media players.

Instead of writing one large automation that tries to remember every previous
state, you define small named layers:

- A **source** establishes a value, such as “the hallway lights are on at
  100%.”
- A **modifier** adjusts the current value, such as “cap brightness at 50% at
  night” or “temporarily raise this light to 100%.”
- Each layer has its own lifetime and can expire without destroying the layers
  underneath it.

Overlay Scenes resolves the active layers and writes the result directly to the
target Home Assistant entities. It also creates diagnostic sensors showing the
resolved values and active layer stack.

> **Breaking configuration change:** layers now accept exactly one attribute,
> and individual layer actions require `<overlay_set_id>.<layer_id>`. Before
> upgrading an existing installation, split every comma-separated layer into
> one layer per attribute and update bare layer IDs in automations.

## Contents

- [What this integration does](#what-this-integration-does)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
- [Supported entities and channels](#supported-entities-and-channels)
- [Creating an Overlay Set](#creating-an-overlay-set)
- [Activating and deactivating Overlay Sets](#activating-and-deactivating-overlay-sets)
- [Configuring layers](#configuring-layers)
- [Layer operations](#layer-operations)
- [Layer lifetimes](#layer-lifetimes)
- [Using templates](#using-templates)
- [Calling Overlay Scenes from automations](#calling-overlay-scenes-from-automations)
- [Complete hallway example](#complete-hallway-example)
- [Additional examples](#additional-examples)
- [Diagnostic entities](#diagnostic-entities)
- [Persistence and restart behavior](#persistence-and-restart-behavior)
- [Troubleshooting](#troubleshooting)
- [Current limitations](#current-limitations)
- [Removing the integration](#removing-the-integration)

## What this integration does

Each target entity attribute is treated as a separate **channel**. Examples:

- `light.hallway.brightness`
- `light.hallway.state`
- `light.office.rgb_color`
- `media_player.lounge.volume_level`

For each channel, Overlay Scenes calculates:

```text
external base value
  → active source, if one exists
  → modifiers from lowest priority to highest priority
  → resolved value
  → Home Assistant service call to the real entity
```

For example, assume the external brightness was 80%:

```text
base:                         80
source sunset_on:            100
modifier night_max:          clamp_max(50) → 50
modifier motion_boost:       override(100) → 100
resolved brightness:         100
```

When `motion_boost` expires, the layers underneath it are recomputed and the
brightness returns to 50%. When `night_max` later deactivates, the source value
of 100% is visible again.

## Requirements

- Home Assistant 2026.7.0 or newer.
- HACS is optional; manual installation is also supported.

## Installation

### HACS custom repository

Until this integration is listed in the default HACS store:

1. Open HACS.
2. Open **Integrations**.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add `https://github.com/gregbacchus/ha-overlay-scenes` and select the
   **Integration** category.
5. Find and install **Overlay Scenes**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services**, select **Add integration**, and add
   **Overlay Scenes**.

### Manual installation

1. Copy `custom_components/overlay_scenes` into your Home Assistant configuration
   directory:

   ```text
   <home-assistant-config>/custom_components/overlay_scenes/
   ```

2. Restart Home Assistant.
3. Open **Settings → Devices & services**.
4. Select **Add integration**.
5. Search for **Overlay Scenes**.

## Quick start

This example creates a 60-second light scene for one hallway light.

### 1. Create an Overlay Set

1. Open **Settings → Devices & services**.
2. Add the **Overlay Scenes** integration.
3. Set **Name** to `Hallway Boost` and **Overlay Set ID** to
   `hallway_boost`.

An Overlay Set groups related layers. All layers in the set write through to
their real target entities.

### 2. Add two layers

Each layer controls exactly one attribute. Open the `Hallway Boost` entry and
add these two **Layer** subentries. They target the same light and are activated
together by the set action.

| Field | Value |
|---|---|
| Layer ID | `front_door_boost_state` |
| Role | `source` |
| Target entities | `light.hallway_1` |
| Attribute | `state` |
| Value or template | `true` |
| Operation | `override` (ignored for sources) |
| Priority | `0` |
| Opacity | `1` |
| Include in set actions | Yes |
| Lifetime | `duration` |
| Duration | `00:01:00` |

Create a second layer with the same settings except:

| Field | Value |
|---|---|
| Layer ID | `front_door_boost_brightness` |
| Attribute | `brightness` |
| Value or template | `100` |

Brightness values are percentages from `0` to `100`.

### 3. Activate the set from an automation

```yaml
alias: Hallway - front door motion boost
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door_motion
    to: "on"
actions:
  - action: overlay_scenes.activate_set
    data:
      config_entry_id: 0123456789abcdef0123456789abcdef
mode: restart
```

Every activation refreshes both 60-second timers. With `mode: restart`, repeated
motion also restarts the automation cleanly.

## Core concepts

### Overlay Sets

An Overlay Set is the top-level integration entry and the primary activation
unit. Use a set to group layers that should normally activate and deactivate
together, for example:

- `Hallway evening scene`
- `Whole-house audio`
- `Office status lights`

Each set has a stable **Overlay Set ID**, such as `hallway_evening`. Automations
use this ID rather than the display name.

Set actions control layers whose **Include in set actions** option is enabled.
While-condition layers are always controlled by their condition and are skipped
by set actions even when the option is enabled.

An activatable set must not include two source layers targeting the same
channel. Overlay Scenes rejects the entire activation before changing anything
if it detects conflicting included sources. Turn off **Include in set actions**
and control mutually exclusive sources individually.

A channel should normally be owned by one Overlay Set. Separate sets have
independent compositors: sources in different sets do not evict or compose with
one another. If sets must overlap, deactivate the active set before activating
the other so they do not contend over the real entity.

Layer IDs are local to their Overlay Set. Individual layer actions always use
the qualified reference `<overlay_set_id>.<layer_id>`. For example,
`hallway_evening.night_max` and `bedroom_evening.night_max` are distinct layers.
Set IDs and local layer IDs may contain lowercase letters, numbers, and
underscores.

Recommended naming:

```text
hallway_evening.sunset_state
hallway_evening.sunset_brightness
hallway_evening.night_max
whole_house_audio.quiet_hours
```

### Channels

A channel is one state or attribute on one entity. A layer targets exactly one
attribute, but it may apply that attribute to multiple entities.

If a layer targets:

```text
Entities:   light.hallway_1, light.hallway_2
Attribute:  brightness
```

it occupies two independent channels:

```text
light.hallway_1.brightness
light.hallway_2.brightness
```

To control both `state` and `brightness`, create two layers in the same Overlay
Set. This keeps each value, operation, lifetime, and diagnostic status explicit.

### Sources

A source asserts a value for every channel it targets. Only one source may be
active on a channel at a time.

Activating a new source:

1. Replaces the existing source on overlapping channels.
2. Cancels the old source's expiry timer for those channels.
3. Leaves the old source active on any non-overlapping channels.

This eviction is deliberately per channel. For example:

```text
source_a targets: hallway_1 + hallway_2 brightness
source_b targets: hallway_2 brightness only
```

Activating `source_b` evicts `source_a` from hallway 2 brightness, but
`source_a` remains the source for hallway 1 brightness.

An explicit boolean `false` source is authoritative. State modifiers do not
turn the channel back on until that source is replaced or deactivated. This is
what makes a physical `switch_off` layer remain off.

### Modifiers

Modifiers fold over the base or source value. Multiple modifiers may be active
at once. They never evict sources or other modifiers.

Examples:

- `clamp_max(50)` caps brightness at 50%.
- `clamp_min(10)` ensures a night light is at least 10%.
- `add(5)` raises a numeric value by 5.
- `or(true)` turns on a state when no explicit false source holds it off.
- `multiply([255, 128, 128])` tints an RGB color.

### Priority and fold order

Modifiers are applied in ascending priority order. Higher-priority modifiers
run later and therefore see the result of lower-priority modifiers.

```text
priority 10: clamp_max(50)
priority 20: override(100)
```

The result is 100 because the priority-20 override runs last.

Reversing the priorities would produce 50 because the clamp would run last.

Use spaced priority values such as `10`, `20`, and `30` so new layers can be
inserted later. If two modifiers have the same priority, they retain activation
order; the modifier activated later is folded later. Prefer unique priorities
whenever the operations are order-sensitive.

## Supported entities and channels

| Entity domain | Attribute | Value format | Write-through action |
|---|---|---|---|
| `light` | `state` | `true` / `false` | `light.turn_on` / `light.turn_off` |
| `light` | `brightness` | Percentage `0`–`100` | `light.turn_on` with `brightness_pct` |
| `light` | `rgb_color` | Three-item RGB list | `light.turn_on` with `rgb_color` |
| `switch` | `state` | `true` / `false` | `switch.turn_on` / `switch.turn_off` |
| `media_player` | `volume_level` | Number `0.0`–`1.0` | `media_player.volume_set` |

Examples of literal values:

```text
true
false
50
0.35
[255, 80, 20]
```

Unsupported entity domains or attributes cause the write-through operation to
fail and are logged by Home Assistant.

## Creating an Overlay Set

1. Open **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **Overlay Scenes**.
4. Enter a descriptive display name.
5. Enter a stable Overlay Set ID using a concise automation-friendly value such
   as `hallway_evening`.
6. Open the newly created integration entry.
7. Use the entry's subentry controls to add one or more Layers.

Overlay Scenes configuration is form-based. It is not configured through
`configuration.yaml`.

## Activating and deactivating Overlay Sets

Set actions are the recommended way to control a complete scene.

### Activate a set

```yaml
- action: overlay_scenes.activate_set
  data:
    config_entry_id: 0123456789abcdef0123456789abcdef
```

Activation applies every layer that:

1. Has **Include in set actions** enabled.
2. Is not a `while_condition` layer.

Duration layers start or refresh their timers. Until-trigger layers remain
active until the set or layer is deactivated or a newer source evicts them.

### Deactivate a set

```yaml
- action: overlay_scenes.deactivate_set
  data:
    config_entry_id: 0123456789abcdef0123456789abcdef
```

Deactivation removes every opted-in non-condition layer from all channels it
still occupies. While-condition layers continue following their condition.

### Complete set-controlled automation

```yaml
alias: Hallway - control evening Overlay Set
triggers:
  - trigger: sun
    event: sunset
    id: activate
  - trigger: time
    at: "22:00:00"
    id: deactivate
actions:
  - choose:
      - conditions: "{{ trigger.id == 'activate' }}"
        sequence:
          - action: overlay_scenes.activate_set
            data:
              config_entry_id: 0123456789abcdef0123456789abcdef
      - conditions: "{{ trigger.id == 'deactivate' }}"
        sequence:
          - action: overlay_scenes.deactivate_set
            data:
              config_entry_id: 0123456789abcdef0123456789abcdef
mode: restart
```

Use individual layer actions only when an automation needs to control one layer
without changing the rest of its set.

## Configuring layers

### Field reference

| Field | Required | Meaning |
|---|---:|---|
| Layer ID | Yes | Stable local ID. Actions address it as `<overlay_set_id>.<layer_id>`. Must be unique within its set. |
| Role | Yes | `source` or `modifier`. |
| Target entities | Yes | One or more supported Home Assistant entities. |
| Attribute | Yes | Exactly one attribute, such as `state`, `brightness`, or `volume_level`. |
| Value or template | Yes | The literal or Home Assistant template applied to that attribute. The form shows the expected type, range, and an example after the attribute is selected. |
| Operation | Yes | Modifier operation. Ignored for source layers. |
| Priority | Yes | Modifier fold order. Lower values run first. |
| Opacity | Yes | `0`–`1`; used by numeric and RGB `override`. |
| Include in set actions | Yes | Whether `activate_set` and `deactivate_set` control this layer. Condition layers are always skipped. |
| Lifetime | Yes | `duration`, `until_trigger`, or `while_condition`. |
| Duration | For duration | Default lifetime after activation, entered as a Home Assistant duration such as `00:01:00`. |
| Condition entity | For while-condition | Entity whose truthiness controls the layer. |

### Layer values

For one attribute, enter the value directly:

```text
Attribute: brightness
Value:     50
```

```text
Attribute: state
Value:     true
```

```text
Attribute: rgb_color
Value:     [255, 120, 20]
```

The value is applied to every selected entity. For example, a brightness layer
with two target lights and value `60` supplies 60% for both lights. If two
entities need different values, create separate layers.

Lists remain valid values for a single list-valued attribute such as
`rgb_color`. To control another attribute, create another layer;
comma-separated attributes and attribute-keyed value objects are not supported.

## Layer operations

### Numeric operations

Use these with `light.brightness` and `media_player.volume_level`.

| Operation | Result | Example |
|---|---|---|
| `override` | Moves toward the new value using opacity | `override(100)` at opacity `0.5` moves 40 to 70 |
| `add` | `current + value` | 40 plus 10 becomes 50 |
| `clamp_min` | At least the supplied value | `clamp_min(10)` changes 0 to 10 |
| `clamp_max` | At most the supplied value | `clamp_max(50)` changes 80 to 50 |
| `average` | `(current + value) / 2` | 40 and 80 become 60 |

If a numeric attribute is absent—for example, brightness on a light that has
never been turned on—the modifier fold starts from zero.

### Boolean operations

Use these with `state` channels.

| Operation | Meaning |
|---|---|
| `override` | Replace the current boolean value |
| `or` | True when either input is true |
| `and` | True only when both inputs are true |
| `nand` | Inverse of `and` |
| `nor` | Inverse of `or` |
| `xor` | True when exactly one input is true |
| `xnor` | True when both inputs are equal |

Boolean override does not crossfade. Opacity `0` leaves the current value;
opacity greater than `0` applies the new value.

Remember that an explicit false source is authoritative and short-circuits
state modifiers until the source is removed or replaced.

### RGB color operations

Use these with `light.rgb_color`.

| Operation | Meaning |
|---|---|
| `override` | Crossfade toward the supplied RGB value using opacity |
| `screen` | Lighten by screening the two colors |
| `multiply` | Darken/tint by multiplying color channels |

Colors use three values from `0` to `255`:

```text
[red, green, blue]
```

Examples:

```text
[255, 0, 0]       red
[255, 160, 60]    warm orange
[80, 120, 255]    cool blue
```

## Layer lifetimes

### Duration

The layer expires automatically after its configured number of seconds.

```text
Lifetime:            duration
Duration: 00:01:00
```

Activating an already-active duration layer refreshes its timer.

An automation may override the configured duration for one activation:

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_entity_id: sensor.hallway_boost_front_door_boost_brightness_status
    duration_override: "00:02:30"
```

In YAML, use Home Assistant duration syntax such as `"00:02:30"`. In the action
UI, use the duration selector.

### Until trigger

The layer remains active until something explicitly deactivates it or a newer
source evicts it from its channels.

```text
Lifetime: until_trigger
```

Use this for physical switch sources, scene selections, or layers controlled by
separate start/stop automations.

### While condition

The layer follows another entity directly:

```text
Lifetime:         while_condition
Condition entity: input_boolean.night_mode
```

Truthiness rules:

- `off`, `false`, `no`, `closed`, `not_home`, `unknown`, `unavailable`, empty,
  and numeric zero are false.
- Nonzero numbers and other meaningful states are true.

While-condition layers self-register when Home Assistant loads the Overlay Set.
You do not need an automation calling `activate_layer` for them. They activate
and deactivate each time the condition changes.

Do not manually activate a while-condition layer. A manual activation can make
it active until the condition entity next changes; the condition is the intended
source of truth.

## Using templates

The **Value or template** field accepts Home Assistant templates.

Example: cap media volume using an input number:

This example assumes an Overlay Set with ID `whole_house_audio`.

```jinja2
{{ states('input_number.night_volume_limit') | float(0.25) }}
```

Configure that layer as:

| Field | Value |
|---|---|
| Layer ID | `audio_night_volume_max` |
| Role | `modifier` |
| Target entities | `media_player.lounge` |
| Attribute | `volume_level` |
| Operation | `clamp_max` |
| Value or template | Template above |
| Priority | `10` |
| Opacity | `1` |
| Include in set actions | Yes |
| Lifetime | `until_trigger` |

Templates are rendered when the affected channel recomputes. Recomputation
currently occurs when:

- A layer on the channel activates, deactivates, expires, or is evicted.
- The target entity receives an external state change.

Changing an entity referenced only inside a template does not by itself trigger
a recompute. To apply such a change immediately, call `activate_layer` again to
refresh the layer, or create an automation that reactivates it when the template
dependency changes.

Example:

```yaml
alias: Audio - refresh night volume limit
triggers:
  - trigger: state
    entity_id: input_number.night_volume_limit
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.whole_house_audio_audio_night_volume_max_status
mode: restart
```

Rendered template output uses Home Assistant's parsed-result behavior. A
template returning `0.25` becomes a number, and a template returning a list such
as `[255, 100, 20]` can be used for `rgb_color`.

## Calling Overlay Scenes from automations

Prefer `activate_set` and `deactivate_set` for normal scene control. The layer
actions below are targeted controls for motion boosts, mutually exclusive
sources, template refreshes, and other cases where changing the entire set would
be incorrect.

The automation editor provides an **Overlay Set** picker for set actions and a
**Layer** entity picker for layer actions. Layer choices include their Overlay
Set name, making the owning set visible in the picker. The
IDs in the YAML examples below are the values saved by those pickers; use the
editor rather than entering them manually.

### Activate a layer

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_entity_id: sensor.hallway_automation_hallway_sunset_state_status
```

For duration layers, activating again resets the timer.

### Activate with a duration override

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_entity_id: sensor.hallway_automation_hallway_front_door_boost_status
    duration_override: "00:05:00"
```

### Deactivate a layer

```yaml
- action: overlay_scenes.deactivate_layer
  data:
    layer_entity_id: sensor.hallway_automation_hallway_sunset_state_status
```

Deactivation removes that layer from every channel it still occupies.

## Complete hallway example

This example implements the walkthrough from the design: sunset lighting,
night-time brightness limiting, motion boosts, night lights, and physical
switch control.

Create an Overlay Set named `Hallway automation` with Overlay Set ID
`hallway_automation`. This is an advanced event-driven set: its mutually
exclusive sources and motion layers are controlled individually, so the tables
below turn off **Include in set actions**. For ordinary scenes, prefer separate
sets whose compatible layers can be activated together with `activate_set`.

Assumed entities:

```text
light.hallway_1
light.hallway_2
binary_sensor.front_door_motion
binary_sensor.hallway_motion
input_boolean.night_mode
switch.hallway_scene_control
sun.sun
```

### Sunset sources

| Field | Value |
|---|---|
| Layer ID | `hallway_sunset_state` |
| Role | `source` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute | `state` |
| Value | `true` |
| Operation | `override` (ignored for sources) |
| Priority | `0` |
| Opacity | `1` |
| Include in set actions | No |
| Lifetime | `until_trigger` |

Create `hallway_sunset_brightness` with the same settings, changing
**Attribute** to `brightness` and **Value** to `100`.

Activate at sunset and deactivate at 22:00:

```yaml
alias: Hallway - sunset source
triggers:
  - trigger: sun
    event: sunset
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_sunset_state_status
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_sunset_brightness_status
mode: single
```

```yaml
alias: Hallway - end sunset source
triggers:
  - trigger: time
    at: "22:00:00"
actions:
  - action: overlay_scenes.deactivate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_sunset_state_status
  - action: overlay_scenes.deactivate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_sunset_brightness_status
mode: single
```

### Night brightness cap

| Field | Value |
|---|---|
| Layer ID | `hallway_night_max` |
| Role | `modifier` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute | `brightness` |
| Value | `50` |
| Operation | `clamp_max` |
| Priority | `10` |
| Opacity | `1` |
| Include in set actions | No; condition-controlled |
| Lifetime | `while_condition` |
| Condition entity | `input_boolean.night_mode` |

Use ordinary Home Assistant automations to manage `input_boolean.night_mode`:

```yaml
alias: Night mode - enable at 21:00
triggers:
  - trigger: time
    at: "21:00:00"
actions:
  - action: input_boolean.turn_on
    target:
      entity_id: input_boolean.night_mode
mode: single
```

```yaml
alias: Night mode - disable at sunrise
triggers:
  - trigger: sun
    event: sunrise
actions:
  - action: input_boolean.turn_off
    target:
      entity_id: input_boolean.night_mode
mode: single
```

The Overlay Scenes layer follows this helper automatically.

### Front-door boost

| Field | Value |
|---|---|
| Layer ID | `hallway_front_door_boost` |
| Role | `modifier` |
| Target entities | `light.hallway_1` |
| Attribute | `brightness` |
| Value | `100` |
| Operation | `override` |
| Priority | `20` |
| Opacity | `1` |
| Include in set actions | No |
| Lifetime | `duration` |
| Duration | `00:01:00` |

```yaml
alias: Hallway - front door boost after dark
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door_motion
    to: "on"
conditions:
  - condition: state
    entity_id: sun.sun
    state: below_horizon
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_front_door_boost_status
mode: restart
```

While night mode is active, hallway 1 becomes 100% while hallway 2 remains
capped at 50%. After 60 seconds, hallway 1 returns to 50%.

### Hallway night light

State and brightness need different operations, so configure two layers.

State layer:

| Field | Value |
|---|---|
| Layer ID | `hallway_motion_state` |
| Role | `modifier` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute | `state` |
| Value | `true` |
| Operation | `or` |
| Priority | `10` |
| Opacity | `1` |
| Include in set actions | No |
| Lifetime | `duration` |
| Duration | `00:02:00` |

Brightness layer:

| Field | Value |
|---|---|
| Layer ID | `hallway_motion_floor` |
| Role | `modifier` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute | `brightness` |
| Value | `10` |
| Operation | `clamp_min` |
| Priority | `5` |
| Opacity | `1` |
| Include in set actions | No |
| Lifetime | `duration` |
| Duration | `00:02:00` |

Activate both from the same automation:

```yaml
alias: Hallway - motion night light
triggers:
  - trigger: state
    entity_id: binary_sensor.hallway_motion
    to: "on"
conditions:
  - condition: state
    entity_id: sun.sun
    state: below_horizon
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_motion_state_status
  - action: overlay_scenes.activate_layer
    data:
      layer_entity_id: sensor.hallway_automation_hallway_motion_floor_status
mode: restart
```

When no source is active and the lights are off, these layers turn them on at
10%. If the lights are already on at 50%, they make no visible change.

### Physical switch sources

Create four single-attribute source layers targeting `light.hallway_1` and
`light.hallway_2`. They share the `override` source operation, priority `0`,
opacity `1`, **Include in set actions** disabled, and an `until_trigger`
lifetime.

| Layer ID | Attribute | Value |
|---|---|---|
| `hallway_switch_on_state` | `state` | `true` |
| `hallway_switch_on_brightness` | `brightness` | `100` |
| `hallway_switch_off_state` | `state` | `false` |
| `hallway_switch_off_brightness` | `brightness` | `0` |

Activate the corresponding source when the control switch changes:

```yaml
alias: Hallway - scene control switch
triggers:
  - trigger: state
    entity_id: switch.hallway_scene_control
    to: "on"
    id: "on"
  - trigger: state
    entity_id: switch.hallway_scene_control
    to: "off"
    id: "off"
actions:
  - choose:
      - conditions: "{{ trigger.id == 'on' }}"
        sequence:
          - action: overlay_scenes.activate_layer
            data:
              layer_entity_id: sensor.hallway_automation_hallway_switch_on_state_status
          - action: overlay_scenes.activate_layer
            data:
              layer_entity_id: sensor.hallway_automation_hallway_switch_on_brightness_status
      - conditions: "{{ trigger.id == 'off' }}"
        sequence:
          - action: overlay_scenes.activate_layer
            data:
              layer_entity_id: sensor.hallway_automation_hallway_switch_off_state_status
          - action: overlay_scenes.activate_layer
            data:
              layer_entity_id: sensor.hallway_automation_hallway_switch_off_brightness_status
mode: restart
```

The switch-on layers evict the sunset sources on overlapping channels. The
separate 22:00 automation may still call `deactivate_layer`, but that later call
is harmless because the sunset source no longer occupies those channels. The
night cap still applies, so the resolved brightness is 50% while night mode is
active. The switch-off layers then become the explicit off sources and remain
off until other sources replace them.

## Additional examples

The audio examples below assume an Overlay Set with ID `whole_house_audio`.

### Quiet-hours media volume

Layer configuration:

| Field | Value |
|---|---|
| Layer ID | `audio_quiet_hours` |
| Role | `modifier` |
| Target entities | `media_player.lounge`, `media_player.kitchen` |
| Attribute | `volume_level` |
| Value | `0.25` |
| Operation | `clamp_max` |
| Priority | `10` |
| Opacity | `1` |
| Include in set actions | No; condition-controlled |
| Lifetime | `while_condition` |
| Condition entity | `input_boolean.quiet_hours` |

When quiet hours are active, external attempts to raise either player above
25% are recomposed back to 25%. When quiet hours end, the last external base
volume is restored.

### Temporary volume ducking

To force speakers toward 10% during an announcement:

| Field | Value |
|---|---|
| Layer ID | `audio_announcement_duck` |
| Role | `modifier` |
| Target entities | `media_player.lounge`, `media_player.kitchen` |
| Attribute | `volume_level` |
| Value | `0.10` |
| Operation | `override` |
| Priority | `30` |
| Opacity | `1` |
| Include in set actions | Yes |
| Lifetime | `duration` |
| Duration | `00:00:30` |

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_entity_id: sensor.whole_house_audio_audio_announcement_duck_status
```

### Warm evening color tint

Layer configuration:

| Field | Value |
|---|---|
| Layer ID | `living_room_warm_tint` |
| Role | `modifier` |
| Target entities | `light.living_room_lamp`, `light.living_room_uplight` |
| Attribute | `rgb_color` |
| Value | `[255, 170, 100]` |
| Operation | `multiply` |
| Priority | `10` |
| Opacity | `1` |
| Include in set actions | No; condition-controlled |
| Lifetime | `while_condition` |
| Condition entity | `input_boolean.evening_mode` |

### Half-opacity color override

```text
Attribute: rgb_color
Value:     [255, 0, 0]
Operation: override
Opacity:   0.5
```

If the current color is `[0, 0, 255]`, the resolved color is approximately
`[128, 0, 128]`.

## Diagnostic entities

Overlay Scenes creates two kinds of sensor.

### Composite sensors

One sensor is created per configured channel. Its generated entity ID resembles:

```text
sensor.hallway_light_hallway_1_brightness_composite
```

The exact entity ID is assigned by Home Assistant and can be changed from the
entity settings.

Composite sensor attributes include:

| Attribute | Meaning |
|---|---|
| `overlay_set_id` | Stable ID used by set-level actions |
| `entity_id` | Real target entity |
| `attribute` | Composited state or attribute |
| `source_layer_id` | Qualified reference of the current source, or null |
| `modifier_layer_ids` | Qualified modifier references in fold order |
| `resolved_value` | Latest calculated output |

### Layer-status sensors

Each configured layer receives a status sensor resembling:

```text
sensor.hallway_front_door_boost_status
```

Its state is `idle` or `active`. Attributes include:

| Attribute | Meaning |
|---|---|
| `overlay_set_id` | Stable ID used by set-level actions |
| `layer_id` | Qualified `<overlay_set_id>.<layer_id>` action reference |
| `role` | Source or modifier |
| `priority` | Modifier priority |
| `channels` | All configured channel keys |
| `expires_at` | UTC expiry for duration layers |
| `reason` | Latest activation or deactivation reason |

These sensors are useful in dashboards, Developer Tools, and automation
conditions.

For a partially evicted multi-channel source, the layer-status sensor's
`channels` attribute still lists every configured channel; it is not an
`active_channels` list. Inspect each composite sensor's `source_layer_id` to see
which channels the source still occupies.

## Persistence and restart behavior

Active layer occupancy is stored in Home Assistant's `.storage` directory.
Overlay Scenes persists:

- Each active `(layer, channel)` pair.
- Absolute duration expiry times.
- The last externally authored base value for active channels.

After a Home Assistant restart:

- Unexpired duration layers are restored with their original expiry time.
- Duration layers that expired while Home Assistant was offline are discarded.
- Until-trigger layers remain active.
- While-condition listeners are re-established and reconcile against their
  current condition entity state.
- When a restored modifier expires, the preserved external base value can
  reassert instead of accidentally preserving the integration's own output.

Do not manually edit `.storage/overlay_scenes.layers` while Home Assistant is
running.

## Troubleshooting

### Enable debug logging

Add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.overlay_scenes: debug
```

Restart Home Assistant or reload logging configuration.

Debug logs include:

- Every channel recompute and its trigger.
- Active source and modifier order.
- Base, source, and resolved values.
- Source eviction and cancelled expiry.
- Lifecycle activation, refresh, cancellation, and expiry reasons.

### A service says the layer is unknown

Check that:

1. The Layer subentry was saved successfully.
2. The parent Overlay Set is loaded.
3. The automation uses the exact qualified `<overlay_set_id>.<layer_id>`
   reference, not a display name or bare local Layer ID.

### A service says the Overlay Set is unknown

Check that the automation uses the stable Overlay Set ID configured when the
integration entry was created, not its display name. The ID is also exposed as
`overlay_set_id` on composite and layer-status sensors.

### Set activation reports conflicting sources

Two opted-in source layers in the same set target the same channel. Overlay
Scenes rejects the activation before changing the set. Disable **Include in set
actions** and activate those mutually exclusive sources individually. Do not
move overlapping sources into independently active sets; separate set
compositors do not evict each other.

### A service rejects a layer reference

Use the full `<overlay_set_id>.<layer_id>` reference, for example
`hallway_automation.hallway_motion_floor`. A bare local ID such as
`hallway_motion_floor` is intentionally rejected. Check that both IDs use only
lowercase letters, numbers, and underscores.

### A layer activates but the value is unexpected

Inspect the composite sensor attributes:

1. Confirm the expected source is present.
2. Read `modifier_layer_ids` in order.
3. Verify priorities—the highest priority runs last.
4. Confirm brightness uses `0`–`100`, not `0`–`255`.
5. Confirm volume uses `0.0`–`1.0`.
6. Confirm the layer has exactly one attribute and its value has the right type.

### A duration layer does not last as long as expected

Every activation refreshes its timer. Check for repeated automation triggers in
the Home Assistant trace. Also check whether the automation supplied a
`duration_override`.

### A source disappeared before its duration elapsed

A newer source probably evicted it from the same channel. Search debug logs for:

```text
source <new> evicted source <old> on channel <channel>
```

Remember that eviction is per channel, so the old source may remain active on
its other channels.

### A template value did not update

Template dependencies do not currently trigger recomposition automatically.
Reactivate the layer when the referenced entity changes, as shown in
[Using templates](#using-templates).

If a rendered template has the wrong type—for example, text supplied to
`clamp_max`—the recompute fails and Home Assistant logs the exception. Check the
debug recompute record and test the template in **Developer Tools → Template**.

### A while-condition layer does not activate

Inspect the condition entity in **Developer Tools → States**. Values such as
`off`, `false`, `unknown`, `unavailable`, and numeric zero are intentionally
false. Check debug logs for `condition_true` or `condition_false` transitions.

### A write-through call fails

Confirm the entity domain and attribute appear in
[Supported entities and channels](#supported-entities-and-channels). Overlay
Scenes does not currently dispatch arbitrary Home Assistant domains.

## Current limitations

- Only `light`, `switch`, and `media_player` write-through channels listed above
  are supported.
- Layer configuration is UI/subentry-based; YAML integration configuration is
  not supported.
- Each layer targets exactly one attribute. Use multiple layers in one set for
  scene behavior that controls several attributes.
- Layer IDs must be unique within their Overlay Set; the same local ID may be
  reused in another set because actions use qualified references.
- Template dependency changes do not automatically trigger recomposition.
- There is no custom Lovelace card or sidebar panel yet. Use the generated
  diagnostic sensors with standard Home Assistant cards.
- There is no mixed write-through/composite-only mode within one Overlay Set.
- RGB input validation is currently delegated to the Home Assistant service
  call.

## Removing the integration

1. Deactivate every active layer in the Overlay Set. This clears persisted
   occupancy as well as removing its effect from the real entities.
2. Open **Settings → Devices & services**.
3. Open the Overlay Scenes entry menu and remove the entry.
4. Remove the custom component files and restart Home Assistant if uninstalling
   manually.

Removing an Overlay Set stops its timers and listeners. It does not delete
persisted active occupancy or restore every real entity to an earlier historical
state. Deactivate the set before removal; otherwise recreating the same Overlay
Set ID may restore retained occupancy.
