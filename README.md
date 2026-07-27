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

## Contents

- [What this integration does](#what-this-integration-does)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
- [Supported entities and channels](#supported-entities-and-channels)
- [Creating an Overlay Set](#creating-an-overlay-set)
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

This example creates a 60-second brightness boost for one light.

### 1. Create an Overlay Set

1. Open **Settings → Devices & services**.
2. Add the **Overlay Scenes** integration.
3. Name the Overlay Set `Hallway`.

An Overlay Set groups related layers. All layers in the set write through to
their real target entities.

### 2. Add a layer

Open the `Hallway` Overlay Scenes entry and add a **Layer** subentry with these
values:

| Field | Value |
|---|---|
| Layer ID | `front_door_boost` |
| Role | `modifier` |
| Target entities | `light.hallway_1` |
| Attribute(s) | `brightness` |
| Value or template | `100` |
| Operation | `override` |
| Priority | `20` |
| Opacity | `1` |
| Lifetime | `duration` |
| Duration in seconds | `60` |

Brightness values are percentages from `0` to `100`.

### 3. Activate it from an automation

```yaml
alias: Hallway - front door motion boost
triggers:
  - trigger: state
    entity_id: binary_sensor.front_door_motion
    to: "on"
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_id: front_door_boost
mode: restart
```

Every activation refreshes the 60-second timer. With `mode: restart`, repeated
motion also restarts the automation cleanly.

## Core concepts

### Overlay Sets

An Overlay Set is the top-level integration entry. Use separate sets to group
layers by purpose or area, for example:

- `Hallway lighting`
- `Whole-house audio`
- `Office status lights`

Layer IDs used by service calls must be unique across all loaded Overlay Sets.
If two sets both contain `night_mode`, calling
`overlay_scenes.activate_layer` with that ID is ambiguous and fails.

Recommended naming:

```text
hallway_sunset_on
hallway_night_max
hallway_front_door_boost
audio_quiet_hours
```

### Channels

A channel is one state or attribute on one entity. A layer may target multiple
entities and multiple attributes.

If a layer targets:

```text
Entities:   light.hallway_1, light.hallway_2
Attributes: state,brightness
```

it occupies four independent channels:

```text
light.hallway_1.state
light.hallway_1.brightness
light.hallway_2.state
light.hallway_2.brightness
```

Enter multiple attributes as a comma-separated list in the **Attribute(s)**
field:

```text
state,brightness
```

### Sources

A source asserts a value for every channel it targets. Only one source may be
active on a channel at a time.

Activating a new source:

1. Replaces the existing source on overlapping channels.
2. Cancels the old source's expiry timer for those channels.
3. Leaves the old source active on any non-overlapping channels.

This eviction is deliberately per channel. For example:

```text
source_a targets: state + brightness
source_b targets: brightness only
```

Activating `source_b` evicts `source_a` from brightness, but `source_a` remains
the source for state.

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
4. Enter a descriptive name.
5. Open the newly created integration entry.
6. Use the entry's subentry controls to add one or more Layers.

Overlay Scenes configuration is form-based. It is not configured through
`configuration.yaml`.

## Configuring layers

### Field reference

| Field | Required | Meaning |
|---|---:|---|
| Layer ID | Yes | Stable ID used by `activate_layer` and `deactivate_layer`. Must be globally unique across loaded sets. |
| Role | Yes | `source` or `modifier`. |
| Target entities | Yes | One or more supported Home Assistant entities. |
| Attribute(s) | Yes | One attribute or a comma-separated list such as `state,brightness`. |
| Value or template | Yes | A JSON literal, scalar value, or Home Assistant template. |
| Operation | Yes | Modifier operation. Ignored for source layers. |
| Priority | Yes | Modifier fold order. Lower values run first. |
| Opacity | Yes | `0`–`1`; used by numeric and RGB `override`. |
| Lifetime | Yes | `duration`, `until_trigger`, or `while_condition`. |
| Duration in seconds | For duration | Default lifetime after activation. |
| Condition entity | For while-condition | Entity whose truthiness controls the layer. |

### Single-channel values

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

### Multi-attribute values

When one layer targets several attributes, enter a JSON object keyed by
attribute:

```text
Attribute(s): state,brightness
```

```json
{
  "state": true,
  "brightness": 100
}
```

You can also target a particular entity or channel with more specific keys.
Value lookup uses this order:

1. Full channel key: `entity_id|attribute`
2. Attribute name: `brightness`
3. Entity ID: `light.hallway_1`

Example:

```json
{
  "light.hallway_1|brightness": 100,
  "light.hallway_2|brightness": 70,
  "state": true
}
```

For complex behavior, separate layers are often clearer than one large
multi-attribute layer—especially when state and brightness need different
modifier operations.

A scalar value broadcasts to every channel targeted by the layer. For a
mapping, every targeted channel must match a full channel key, attribute key, or
entity-ID key. An entity-ID match is used as the final value; it is not treated
as a nested mapping. If no key matches, the layer resolves `null` for that
channel, which can prevent a write or make the selected operation invalid.
Always provide a value for every targeted channel.

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
Duration in seconds: 60
```

Activating an already-active duration layer refreshes its timer.

An automation may override the configured duration for one activation:

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_id: front_door_boost
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
      layer_id: audio_night_volume_max
mode: restart
```

Rendered template output uses Home Assistant's parsed-result behavior. A
template returning `0.25` becomes a number, and a template returning a list such
as `[255, 100, 20]` can be used for `rgb_color`. For multi-attribute layers,
prefer a literal JSON mapping; template-generated mappings are harder to
validate and troubleshoot.

## Calling Overlay Scenes from automations

### Activate a layer

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_id: hallway_sunset_on
```

For duration layers, activating again resets the timer.

### Activate with a duration override

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_id: hallway_motion_boost
    duration_override: "00:05:00"
```

### Deactivate a layer

```yaml
- action: overlay_scenes.deactivate_layer
  data:
    layer_id: hallway_sunset_on
```

Deactivation removes that layer from every channel it still occupies.

## Complete hallway example

This example implements the walkthrough from the design: sunset lighting,
night-time brightness limiting, motion boosts, night lights, and physical
switch control.

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

### Layer 1: sunset source

| Field | Value |
|---|---|
| Layer ID | `hallway_sunset_on` |
| Role | `source` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute(s) | `state,brightness` |
| Value | `{"state": true, "brightness": 100}` |
| Operation | `override` (ignored for sources) |
| Priority | `0` |
| Opacity | `1` |
| Lifetime | `until_trigger` |

Activate at sunset and deactivate at 22:00:

```yaml
alias: Hallway - sunset source
triggers:
  - trigger: sun
    event: sunset
actions:
  - action: overlay_scenes.activate_layer
    data:
      layer_id: hallway_sunset_on
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
      layer_id: hallway_sunset_on
mode: single
```

### Layer 2: night brightness cap

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

### Layer 3: front-door boost

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
| Lifetime | `duration` |
| Duration in seconds | `60` |

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
      layer_id: hallway_front_door_boost
mode: restart
```

While night mode is active, hallway 1 becomes 100% while hallway 2 remains
capped at 50%. After 60 seconds, hallway 1 returns to 50%.

### Layers 4 and 5: hallway night light

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
| Lifetime | `duration` |
| Duration in seconds | `120` |

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
| Lifetime | `duration` |
| Duration in seconds | `120` |

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
      layer_id: hallway_motion_state
  - action: overlay_scenes.activate_layer
    data:
      layer_id: hallway_motion_floor
mode: restart
```

When no source is active and the lights are off, these layers turn them on at
10%. If the lights are already on at 50%, they make no visible change.

### Layer 6: physical switch on

| Field | Value |
|---|---|
| Layer ID | `hallway_switch_on` |
| Role | `source` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute(s) | `state,brightness` |
| Value | `{"state": true, "brightness": 100}` |
| Operation | `override` (ignored for sources) |
| Priority | `0` |
| Opacity | `1` |
| Lifetime | `until_trigger` |

### Layer 7: physical switch off

| Field | Value |
|---|---|
| Layer ID | `hallway_switch_off` |
| Role | `source` |
| Target entities | `light.hallway_1`, `light.hallway_2` |
| Attribute(s) | `state,brightness` |
| Value | `{"state": false, "brightness": 0}` |
| Operation | `override` (ignored for sources) |
| Priority | `0` |
| Opacity | `1` |
| Lifetime | `until_trigger` |

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
              layer_id: hallway_switch_on
      - conditions: "{{ trigger.id == 'off' }}"
        sequence:
          - action: overlay_scenes.activate_layer
            data:
              layer_id: hallway_switch_off
mode: restart
```

`hallway_switch_on` evicts the sunset source on overlapping channels. The
separate 22:00 automation may still call `deactivate_layer`, but that later call
is harmless because the sunset source no longer occupies those channels. The
night cap still applies, so the resolved brightness is 50% while night mode is
active. `hallway_switch_off` then becomes the explicit off source and remains
off until another source replaces it.

## Additional examples

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
| Lifetime | `duration` |
| Duration in seconds | `30` |

```yaml
- action: overlay_scenes.activate_layer
  data:
    layer_id: audio_announcement_duck
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
| `entity_id` | Real target entity |
| `attribute` | Composited state or attribute |
| `source_layer_id` | Current source, or null |
| `modifier_layer_ids` | Modifiers in fold order |
| `resolved_value` | Latest calculated output |

### Layer-status sensors

Each configured layer receives a status sensor resembling:

```text
sensor.hallway_front_door_boost_status
```

Its state is `idle` or `active`. Attributes include:

| Attribute | Meaning |
|---|---|
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
3. The automation uses the exact Layer ID, not the display name.

### A service says the layer ID is ambiguous

Two loaded Overlay Sets contain the same Layer ID. Rename one layer so every ID
is globally unique.

### A layer activates but the value is unexpected

Inspect the composite sensor attributes:

1. Confirm the expected source is present.
2. Read `modifier_layer_ids` in order.
3. Verify priorities—the highest priority runs last.
4. Confirm brightness uses `0`–`100`, not `0`–`255`.
5. Confirm volume uses `0.0`–`1.0`.
6. Confirm multi-attribute values are valid JSON objects.

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
- Layer IDs must be unique across all loaded Overlay Sets.
- Template dependency changes do not automatically trigger recomposition.
- There is no custom Lovelace card or sidebar panel yet. Use the generated
  diagnostic sensors with standard Home Assistant cards.
- There is no mixed write-through/composite-only mode within one Overlay Set.
- RGB input validation is currently delegated to the Home Assistant service
  call.

## Removing the integration

1. Deactivate any layers whose effects you do not want left on the real
   entities.
2. Open **Settings → Devices & services**.
3. Open the Overlay Scenes entry menu and remove the entry.
4. Remove the custom component files and restart Home Assistant if uninstalling
   manually.

Removing an Overlay Set stops its timers and listeners. It does not attempt to
restore every real entity to an earlier historical state after removal.
