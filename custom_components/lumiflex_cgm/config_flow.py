"""Config flow for LumiFlex CGM."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import LumiFlexApi, LumiFlexError
from .const import (
    CONF_NIGHTSCOUT_API_SECRET,
    CONF_NIGHTSCOUT_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)


def _get_value(data: dict[str, Any], options: dict[str, Any], key: str, default: Any = None) -> Any:
    return options.get(key, data.get(key, default))


def _common_schema(defaults: dict[str, Any], include_credentials: bool = True) -> vol.Schema:
    fields: dict[Any, Any] = {}

    if include_credentials:
        fields[vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, ""))] = str
        fields[
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, ""))
        ] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )

    fields[
        vol.Required(
            CONF_UPDATE_INTERVAL,
            default=int(defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_UPDATE_INTERVAL,
            max=MAX_UPDATE_INTERVAL,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )

    fields[
        vol.Optional(CONF_NIGHTSCOUT_URL, default=defaults.get(CONF_NIGHTSCOUT_URL, ""))
    ] = str
    fields[
        vol.Optional(
            CONF_NIGHTSCOUT_API_SECRET,
            default=defaults.get(CONF_NIGHTSCOUT_API_SECRET, ""),
        )
    ] = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )

    return vol.Schema(fields)


def _credentials_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    })


async def _validate_lumiflex_credentials(hass, username: str, password: str) -> str | None:
    """Validate LumiFlex credentials and return patient name if available."""
    session = async_get_clientsession(hass)
    api = LumiFlexApi(session=session, username=username, password=password)
    data = await api.async_get_current()
    return data.get("patient_name")


def _normalize_update_interval(user_input: dict[str, Any], errors: dict[str, str]) -> None:
    """Normalize and validate update interval as a plain integer field."""
    raw_value = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    try:
        numeric_value = float(raw_value)
    except (TypeError, ValueError):
        errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        return

    if not numeric_value.is_integer():
        errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        return

    value = int(numeric_value)
    if value < MIN_UPDATE_INTERVAL or value > MAX_UPDATE_INTERVAL:
        errors[CONF_UPDATE_INTERVAL] = "invalid_update_interval"
        return

    user_input[CONF_UPDATE_INTERVAL] = value


def _validate_nightscout_pair(user_input: dict[str, Any], errors: dict[str, str]) -> None:
    url = (user_input.get(CONF_NIGHTSCOUT_URL) or "").strip()
    secret = (user_input.get(CONF_NIGHTSCOUT_API_SECRET) or "").strip()
    if bool(url) != bool(secret):
        if not url:
            errors[CONF_NIGHTSCOUT_URL] = "required_with_secret"
        if not secret:
            errors[CONF_NIGHTSCOUT_API_SECRET] = "required_with_url"


class LumiFlexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LumiFlex CGM."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return LumiFlexOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _normalize_update_interval(user_input, errors)
            _validate_nightscout_pair(user_input, errors)
            if not errors:
                try:
                    title = await _validate_lumiflex_credentials(
                        self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )
                except LumiFlexError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=title or "LumiFlex CGM",
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_common_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Reconfigure an existing entry."""
        entry = self._get_reconfigure_entry()
        defaults = dict(entry.data)
        defaults.update(entry.options)
        errors: dict[str, str] = {}

        if user_input is not None:
            _validate_nightscout_pair(user_input, errors)
            if not errors:
                try:
                    await _validate_lumiflex_credentials(
                        self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    )
                except LumiFlexError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={**entry.data, **user_input},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(user_input or defaults),
            errors=errors,
        )


class LumiFlexOptionsFlow(config_entries.OptionsFlow):
    """Handle LumiFlex options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage integration options."""
        entry = self.config_entry
        defaults = {
            CONF_UPDATE_INTERVAL: _get_value(
                entry.data, entry.options, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
            CONF_NIGHTSCOUT_URL: _get_value(entry.data, entry.options, CONF_NIGHTSCOUT_URL, ""),
            CONF_NIGHTSCOUT_API_SECRET: _get_value(
                entry.data, entry.options, CONF_NIGHTSCOUT_API_SECRET, ""
            ),
        }
        errors: dict[str, str] = {}

        if user_input is not None:
            _normalize_update_interval(user_input, errors)
            _validate_nightscout_pair(user_input, errors)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_common_schema(user_input or defaults, include_credentials=False),
            errors=errors,
        )
