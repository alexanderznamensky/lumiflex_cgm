"""LumiFlex CGM integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LumiFlexApi, NightscoutApi
from .const import CONF_NIGHTSCOUT_API_SECRET, CONF_NIGHTSCOUT_URL, DOMAIN
from .coordinator import LumiFlexCoordinator, merged_config

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LumiFlex CGM from a config entry."""
    config = merged_config(entry)
    session = async_get_clientsession(hass)

    api = LumiFlexApi(
        session=session,
        username=config[CONF_USERNAME],
        password=config[CONF_PASSWORD],
    )
    nightscout = NightscoutApi(
        session=session,
        url=config.get(CONF_NIGHTSCOUT_URL, ""),
        api_secret=config.get(CONF_NIGHTSCOUT_API_SECRET, ""),
    )

    coordinator = LumiFlexCoordinator(hass, entry, api, nightscout)
    await coordinator.async_load_last_uploaded()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload LumiFlex CGM config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options update."""
    await hass.config_entries.async_reload(entry.entry_id)
