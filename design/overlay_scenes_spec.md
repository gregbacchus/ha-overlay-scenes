# Overlay Scenes — Implementation Spec (Claude Code handoff)

Companion to `overlay_scenes_architecture.md` — that doc explains *why*, this one specifies *what to build*. Read the architecture doc first; this is the buildable contract.

## Scope for this handoff

Build **Tier 1 only**: the integration itself (registry, lifecycle, compositor, write-through, entities, services, config subentries, logging). No custom Lovelace card, no add-on. Target: `custom_components/overlay_scenes/`, HACS-distributable, HA current stable API (2026.x — verify against `developers.home-assistant.io` at implementation time, don't assume the below is current if it's been a while).

## Deliverables

```
custom_components/overlay_scenes/
├── __init__.py          # setup/unload, service registration
├── manifest.json
├── config_flow.py        # Overlay Set + Layer creation via config subentries
├── const.py               # domain, op enums, defaults
├── models.py              # Layer, SourceLayer, ModifierLayer, Channel dataclasses
├── registry.py             # per-channel active-layer bookkeeping, eviction
├── lifecycle.py            # timers, condition listeners, expiry
├── compositor.py           # pure fold function
├── writethrough.py         # context-tagged service calls, feedback filtering
├── store.py                # persistence (.storage/overlay_scenes.layers)
├── entity.py                # composite sensors, layer-status sensors, diagnostic attrs
├── services.yaml
├── strings.json / translations/en.json
└── tests/
    ├── test_compositor.py
    ├── test_registry_eviction.py
    ├── test_lifecycle.py
    ├── test_writethrough_feedback.py
    └── test_scenario_walkthrough.py   # encodes the worked example below as acceptance tests
```

## Data model

```python
ValueType = Literal["numeric", "boolean", "color"]

NumericOp = Literal["override", "add", "clamp_min", "clamp_max", "average"]
BooleanOp = Literal["override", "or", "and", "nand", "nor", "xor", "xnor"]
ColorOp = Literal["override", "screen", "multiply"]

@dataclass(frozen=True)
class Channel:
    entity_id: str
    attribute: str        # e.g. "brightness", "state", "rgb_color", "volume_level"

@dataclass
class Layer:
    id: str
    overlay_set_id: str
    role: Literal["source", "modifier"]
    priority: int
    channels: list[Channel]
    value: Any | Template          # literal or HA Template object, resolved at recompute time
    op: NumericOp | BooleanOp | ColorOp   # ignored for source layers (sources always assert)
    opacity: float = 1.0            # 0-1, used for override/replace-style crossfade only
    lifetime: LifetimeSpec

@dataclass
class LifetimeSpec:
    mode: Literal["duration", "until_trigger", "while_condition"]
    duration: timedelta | None = None
    condition_entity: str | None = None
```

Notes:
- `value` must support HA templates (Jinja) so modifiers can reference live entities (`clamp_max: {{ states('input_number.night_volume') }}`). Resolve templates at recompute time, not at activation time.
- A single `Layer` can target multiple `Channel`s (e.g. switch-on source sets both `state` and `brightness`). Per the eviction-scope decision, registry bookkeeping is per-`Channel`, not per-`Layer` — a multi-channel layer can be partially evicted.

## Registry (`registry.py`)

Responsibility: track, per `Channel`, which layers are currently active.

```python
class ChannelRegistry:
    # channel -> {"source": Layer | None, "modifiers": list[Layer]}
    _state: dict[Channel, ChannelState]

    def activate(self, layer: Layer) -> list[EvictionEvent]:
        """
        For each channel the layer targets:
          - if layer.role == "source": evict any existing source on that channel
            (cancel its lifecycle timer via lifecycle.cancel(evicted_layer, channel)),
            install this layer as the channel's source.
          - if layer.role == "modifier": append to that channel's modifier list.
        Returns eviction events for logging. Triggers recompute for affected channels.
        """

    def deactivate(self, layer_id: str, reason: str) -> None:
        """Remove layer from every channel it occupies. Triggers recompute."""

    def active_layers_for(self, channel: Channel) -> tuple[Layer | None, list[Layer]]:
        """Returns (source, modifiers_sorted_by_priority_ascending)."""
```

**Eviction is per-channel, not per-layer** (decided). Every layer targets exactly one attribute but may target several entities. If layer A targets brightness on hallway lights 1 and 2 and layer B targets brightness on light 2 only, activating B evicts A *only* from light 2's brightness channel — A's light 1 channel entry is untouched and keeps running on A's original timer. This means `lifecycle.py` tracks expiry per (layer, channel) pair, not just per layer.

## Lifecycle (`lifecycle.py`)

```python
class LifecycleManager:
    def start(self, layer: Layer) -> None:
        """
        duration: schedule async callback at now + duration, calls registry.deactivate(layer.id, "duration_elapsed")
        until_trigger: no timer; waits for explicit deactivate_layer service call
        while_condition: subscribe to condition_entity state changes;
          treat "on"/truthy as should-be-active, "off"/falsy as immediate deactivate("condition_false")
          Note: while_condition layers may not need an explicit activate() call at all —
          consider having them self-register at HA startup / config-entry setup and simply
          track the condition_entity's state directly, rather than requiring a service call to arm them.
        """

    def cancel(self, layer: Layer, channel: Channel, reason: str) -> None:
        """Called by registry on eviction. Cancels the specific timer/listener for
        that (layer, channel) pair. If the layer has other channels still active
        elsewhere, only cancel the affected channel's bookkeeping, not the whole layer."""

    def refresh(self, layer: Layer) -> None:
        """activate() called again on an already-active duration-mode layer: reset its timer."""
```

## Compositor (`compositor.py`)

Pure function, no side effects, easiest thing to unit test — get this right first.

```python
def resolve_channel(base_value: Any, source: Layer | None, modifiers: list[Layer]) -> Any:
    """
    result = source.value if source else base_value
    for modifier in modifiers:  # sorted ascending priority — later ones apply last
        result = apply_op(modifier.op, result, resolve_value(modifier.value), modifier.opacity)
    return result
```

`apply_op` implementations per type — this is the full op table, implement all of these:

| Type | Ops |
|---|---|
| numeric | `override` (opacity-lerp toward new value), `add`, `clamp_min`, `clamp_max`, `average` |
| boolean | `override`, `or`, `and`, `nand`, `nor`, `xor`, `xnor` |
| color (RGB tuple) | `override`, `screen` (`1-(1-a)(1-b)` per channel, 0-255 normalized), `multiply` (per channel) |

Recompute is triggered on: (a) base entity state change (context-filtered, see write-through below), (b) any registry mutation affecting that channel (activate/deactivate/evict).

## Write-through (`writethrough.py`)

```python
class WriteThroughHandler:
    _pending_contexts: set[str]   # context.id of calls we just issued, short TTL

    async def apply(self, channel: Channel, value: Any) -> None:
        """
        Call the appropriate service for channel.attribute (light.turn_on with
        brightness=/rgb_color=, switch.turn_on/off, media_player.volume_set, etc.
        — needs a small dispatch table keyed on domain + attribute).
        Capture the returned context.id, add to _pending_contexts.
        """

    def should_ignore(self, event: Event) -> bool:
        """True if event.context.id (or parent_id) is in _pending_contexts.
        Called from the base-state-change listener before treating a change
        as new external input. This is the mechanism that prevents feedback
        loops and the 'clamp becomes permanent' bug."""
```

Domain dispatch table for write-through — build incrementally, don't try to cover every domain up front. Minimum for this project's scope: `light` (state, brightness, rgb_color), `switch` (state), `media_player` (volume_level).

## Storage (`store.py`)

Use HA's `homeassistant.helpers.storage.Store`. Persist: active layer instances per channel, their remaining duration (recompute absolute expiry time, not remaining seconds, to survive HA being down), `while_condition` bindings. Restore on `async_setup_entry`, re-establish timers/listeners from persisted absolute expiry times.

## Entities (`entity.py`)

- `sensor.<overlay_set>_<channel>_composite` — state = current resolved value (or omit if write-through-only makes this redundant; still recommended per the diagnostic-logging decision)
- `sensor.<layer_id>_status` — state = `idle`/`active`, attributes: `role`, `priority`, `channels`, `expires_at` (if duration mode), `reason` (last activation/deactivation reason)
- Diagnostic attributes on the composite sensor: current source layer id, list of active modifier layer ids in fold order — this is the "get Tier 2 monitoring value for free" item from the architecture doc.

## Services (`services.yaml`)

```yaml
activate_layer:
  fields:
    layer_id: {required: true, selector: {text}}
    duration_override: {required: false, selector: {duration}}

deactivate_layer:
  fields:
    layer_id: {required: true, selector: {text}}
```

## Config flow (`config_flow.py`)

Tier 1, form-based (decided — see architecture doc). Use config subentries for repeatable Layer definitions within an Overlay Set config entry. `value` fields that need template support should use HA's template selector, not a plain string field — verify current selector support for this before finalizing the schema (`selector.TemplateSelector` as of recent HA versions, confirm still current).

## Logging spec

Implement per the architecture doc's "Diagnostic logging" section verbatim:
- `_LOGGER.debug` structured log on every compositor recompute: channel, trigger, active layer set, inputs, output
- Separate, distinct log line for evictions: `"source %s evicted source %s on channel %s, cancelling expiry at %s"`
- Lifecycle transition logs with explicit `reason` field: `duration_elapsed | condition_false | evicted_by:<layer_id> | service_call`
- All gated behind standard `logger:` component config (`custom_components.overlay_scenes: debug`), silent by default

## Acceptance test: the worked scenario

Encode this directly as `tests/test_scenario_walkthrough.py` — it's the sharpest spec of correct behavior available and should be a literal test, not just documentation:

1. Sunset fires → source layer `sunset_on` activates on `power` channel (light.hallway_1 and light.hallway_2), value on/100%, lifetime=until 22:00. **Assert:** both lights on, 100%.
2. Clock reaches 21:00 → `while_condition` modifier `night_max` activates on `brightness` channel, `clamp_max(50)`. **Assert:** both lights 50%.
3. Front-door motion at 21:30 (sun down) → modifier `front_door_boost` activates on light.hallway_1's `brightness` only, `override(100)`, duration 60s. **Assert:** hallway_1 = 100%, hallway_2 = 50%.
4. 60s elapse, no further input → `front_door_boost` expires (`duration_elapsed`). **Assert:** hallway_1 back to 50%.
5. Hallway motion fires (sun down) → modifier `hallway_night_light` activates on `state` (`or(true)`) and `brightness` (`clamp_min(10)`) for both lights. **Assert:** no visible change (lights already on at 50%, above the 10% floor).
6. *Separately* — same hallway-motion trigger at 22:30 instead (`sunset_on` already expired, base off) → **Assert:** lights turn on at 10%, not 50% (night_max's `clamp_max(50)` still applies but there's no source asserting "on" at 100 first — trace through `resolve_channel` with `source=None`).
7. Switch turned on at any point in the walkthrough → new source layer `switch_on` activates on `power` (both channels: `state`, `brightness`), value on/100%, lifetime=`until_trigger`. **Assert:** `sunset_on`'s pending 22:00 expiry is cancelled (eviction event logged); `night_max` clamp still applies (50%); no automatic off occurs at 22:00.
8. Switch turned off → source layer `switch_off` activates, value off, evicts whatever source currently holds `power`. **Assert:** lights off, stay off until another source activates (not just until end of day).

If all eight pass, the compositor and eviction model are implemented correctly per spec.

## Explicitly out of scope for this handoff

- Custom Lovelace card (Tier 2)
- Custom panel (Tier 3)
- Add-on / separate Docker process
- Domain dispatch coverage beyond `light`, `switch`, `media_player`
- HACS store submission/validation (`hacs.json`, brand icons) — functional integration first
