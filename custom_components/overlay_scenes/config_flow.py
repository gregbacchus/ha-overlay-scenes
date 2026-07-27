"""Config flow for Overlay Scenes."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    DurationSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
    TextSelector,
)

from .const import ALL_OPS, DOMAIN, SUBENTRY_TYPE_LAYER
from .ha_presentation import layer_target_names
from .pickers import common_entity_attributes
from .presentation import layer_title, overlay_set_title

ID_PATTERN = r"^[a-z0-9_]+$"

SET_SCHEMA = vol.Schema(
    {
        vol.Required("name"): TextSelector(),
        vol.Required("set_id"): TextSelector(),
    }
)
LAYER_TARGET_SCHEMA = vol.Schema(
    {
        vol.Required("layer_id"): TextSelector(),
        vol.Required("role", default="modifier"): SelectSelector(
            SelectSelectorConfig(options=["source", "modifier"])
        ),
        vol.Required("entities"): EntitySelector(EntitySelectorConfig(multiple=True)),
    }
)


def layer_details_schema(attributes: list[str]) -> vol.Schema:
    """Build the layer details form from verified common attributes."""
    return vol.Schema(
        {
            vol.Required("attribute", default="state"): SelectSelector(
                SelectSelectorConfig(options=attributes)
            ),
            vol.Required("value"): TemplateSelector(),
            vol.Required("op", default="override"): SelectSelector(
                SelectSelectorConfig(options=list(ALL_OPS))
            ),
            vol.Required("priority", default=0): NumberSelector(
                NumberSelectorConfig(min=-10000, max=10000, step=1)
            ),
            vol.Required("opacity", default=1.0): NumberSelector(
                NumberSelectorConfig(min=0, max=1, step=0.05)
            ),
            vol.Required("include_in_set_actions", default=True): BooleanSelector(),
            vol.Required("lifetime_mode", default="until_trigger"): SelectSelector(
                SelectSelectorConfig(
                    options=["duration", "until_trigger", "while_condition"]
                )
            ),
            vol.Optional("duration_seconds"): DurationSelector(),
            vol.Optional("condition_entity"): EntitySelector(),
        }
    )


class OverlayScenesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create an Overlay Set."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create the parent Overlay Set entry."""
        if user_input is not None:
            if not re.fullmatch(ID_PATTERN, user_input["set_id"]):
                return self.async_show_form(
                    step_id="user", data_schema=SET_SCHEMA, errors={"set_id": "invalid_id"}
                )
            await self.async_set_unique_id(user_input["set_id"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=overlay_set_title(user_input["name"], user_input["set_id"]),
                data=user_input,
            )
        return self.async_show_form(step_id="user", data_schema=SET_SCHEMA)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Declare repeatable layer subentries."""
        return {SUBENTRY_TYPE_LAYER: LayerSubentryFlowHandler}


class LayerSubentryFlowHandler(ConfigSubentryFlow):
    """Create and reconfigure layers."""

    _target_input: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Choose the identity and target entities for a new layer."""
        errors = self._validate_targets(user_input)
        if user_input is not None and not errors and not common_entity_attributes(
            self.hass.states.get, user_input["entities"]
        ):
            errors["entities"] = "no_common_attribute"
        if user_input is not None and not errors:
            self._target_input = user_input
            return await self.async_step_details()
        return self.async_show_form(
            step_id="user", data_schema=LAYER_TARGET_SCHEMA, errors=errors
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None):
        """Choose a common target attribute and layer behavior."""
        if self._target_input is None:
            return await self.async_step_user()
        errors = self._validate_details(user_input)
        if user_input is not None and not errors:
            data = {**self._target_input, **user_input}
            entry = self._get_entry()
            set_id = entry.data["set_id"]
            return self.async_create_entry(
                title=layer_title(set_id, data, layer_target_names(self.hass, data)),
                data=data,
            )
        attributes = common_entity_attributes(
            self.hass.states.get, self._target_input["entities"]
        )
        return self.async_show_form(
            step_id="details",
            data_schema=layer_details_schema(attributes),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Choose updated identity and target entities."""
        subentry = self._get_reconfigure_subentry()
        errors = self._validate_targets(user_input)
        if user_input is not None and not errors and not common_entity_attributes(
            self.hass.states.get, user_input["entities"]
        ):
            errors["entities"] = "no_common_attribute"
        if user_input is not None and not errors:
            self._target_input = user_input
            return await self.async_step_reconfigure_details()
        schema = self.add_suggested_values_to_schema(LAYER_TARGET_SCHEMA, subentry.data)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    def _validate_targets(user_input: dict[str, Any] | None) -> dict[str, str]:
        if not user_input:
            return {}
        if not re.fullmatch(ID_PATTERN, user_input["layer_id"]):
            return {"layer_id": "invalid_id"}
        return {}

    async def async_step_reconfigure_details(
        self, user_input: dict[str, Any] | None = None
    ):
        """Choose updated common attribute and layer behavior."""
        subentry = self._get_reconfigure_subentry()
        if self._target_input is None:
            return await self.async_step_reconfigure()
        errors = self._validate_details(user_input)
        if user_input is not None and not errors:
            data = {**self._target_input, **user_input}
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                data=data,
                title=layer_title(
                    self._get_entry().data["set_id"],
                    data,
                    layer_target_names(self.hass, data),
                ),
            )
        attributes = common_entity_attributes(
            self.hass.states.get, self._target_input["entities"]
        )
        configured_attribute = subentry.data["attribute"]
        if configured_attribute not in attributes:
            attributes.append(configured_attribute)
        schema = self.add_suggested_values_to_schema(
            layer_details_schema(attributes), subentry.data
        )
        return self.async_show_form(
            step_id="reconfigure_details", data_schema=schema, errors=errors
        )

    @staticmethod
    def _validate_details(user_input: dict[str, Any] | None) -> dict[str, str]:
        if not user_input:
            return {}
        mode = user_input["lifetime_mode"]
        if mode == "duration" and not user_input.get("duration_seconds"):
            return {"duration_seconds": "duration_required"}
        if mode == "while_condition" and not user_input.get("condition_entity"):
            return {"condition_entity": "condition_required"}
        return {}
