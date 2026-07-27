"""Config flow for Overlay Scenes."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigSubentryFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
    TextSelector,
)

from .const import ALL_OPS, DOMAIN, SUBENTRY_TYPE_LAYER

ID_PATTERN = r"^[a-z0-9_]+$"

SET_SCHEMA = vol.Schema(
    {
        vol.Required("name"): TextSelector(),
        vol.Required("set_id"): TextSelector(),
    }
)
LAYER_SCHEMA = vol.Schema(
    {
        vol.Required("layer_id"): TextSelector(),
        vol.Required("role", default="modifier"): SelectSelector(
            SelectSelectorConfig(options=["source", "modifier"])
        ),
        vol.Required("entities"): EntitySelector(EntitySelectorConfig(multiple=True)),
        vol.Required("attribute", default="state"): TextSelector(),
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
            SelectSelectorConfig(options=["duration", "until_trigger", "while_condition"])
        ),
        vol.Optional("duration_seconds"): NumberSelector(
            NumberSelectorConfig(min=0.1, max=31536000, step=1)
        ),
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
            return self.async_create_entry(title=user_input["name"], data=user_input)
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Add a layer."""
        errors = self._validate(user_input)
        if user_input is not None and not errors:
            return self.async_create_entry(title=user_input["layer_id"], data=user_input)
        return self.async_show_form(step_id="user", data_schema=LAYER_SCHEMA, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Update an existing layer."""
        subentry = self._get_reconfigure_subentry()
        errors = self._validate(user_input)
        if user_input is not None and not errors:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data=user_input, title=user_input["layer_id"]
            )
        schema = self.add_suggested_values_to_schema(LAYER_SCHEMA, subentry.data)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    def _validate(user_input: dict[str, Any] | None) -> dict[str, str]:
        if not user_input:
            return {}
        if not re.fullmatch(ID_PATTERN, user_input["layer_id"]):
            return {"layer_id": "invalid_id"}
        attribute = user_input["attribute"].strip()
        if not attribute or "," in attribute:
            return {"attribute": "single_attribute_required"}
        mode = user_input["lifetime_mode"]
        if mode == "duration" and not user_input.get("duration_seconds"):
            return {"duration_seconds": "duration_required"}
        if mode == "while_condition" and not user_input.get("condition_entity"):
            return {"condition_entity": "condition_required"}
        return {}
