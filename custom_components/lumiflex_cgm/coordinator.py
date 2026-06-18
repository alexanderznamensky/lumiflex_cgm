"""DataUpdateCoordinator for LumiFlex CGM."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    LumiFlexApi,
    LumiFlexAuthError,
    LumiFlexError,
    NightscoutApi,
    build_nightscout_entry,
)
from .const import (
    CONF_NIGHTSCOUT_API_SECRET,
    CONF_NIGHTSCOUT_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return entry data with options overriding optional values."""
    data = dict(entry.data)
    data.update(entry.options)
    return data


class LumiFlexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for LumiFlex CGM."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LumiFlexApi,
        nightscout: NightscoutApi,
    ) -> None:
        config = merged_config(entry)
        interval_min = int(config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        update_interval = timedelta(minutes=interval_min) if interval_min > 0 else None

        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        self.entry = entry
        self.api = api
        self.nightscout = nightscout
        self.nightscout_status = "disabled" if not nightscout.configured else "not_uploaded_yet"
        self.nightscout_error: str | None = None
        self.last_uploaded_date_ms: int | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}_{entry.entry_id}_nightscout.json"
        )

    async def async_load_last_uploaded(self) -> None:
        """Load persistent upload state to avoid duplicates across restarts."""
        stored = await self._store.async_load()
        if stored:
            self.last_uploaded_date_ms = stored.get("last_uploaded_date_ms")

    async def _async_save_last_uploaded(self, date_ms: int) -> None:
        self.last_uploaded_date_ms = date_ms
        await self._store.async_save({"last_uploaded_date_ms": date_ms})

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch LumiFlex data and optionally upload latest point to Nightscout."""
        try:
            data = await self.api.async_get_current()
        except LumiFlexAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except LumiFlexError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

        await self._async_maybe_upload_nightscout(data)
        data["nightscout_status"] = self.nightscout_status
        data["nightscout_error"] = self.nightscout_error
        data["nightscout_last_uploaded_date_ms"] = self.last_uploaded_date_ms
        return data

    async def _async_maybe_upload_nightscout(self, data: dict[str, Any]) -> None:
        if not self.nightscout.configured:
            self.nightscout_status = "disabled"
            self.nightscout_error = None
            return

        entry = build_nightscout_entry(data)
        if entry is None:
            self.nightscout_status = "no_valid_entry"
            self.nightscout_error = "No valid glucose/time pair"
            return

        date_ms = entry["date"]
        if self.last_uploaded_date_ms == date_ms:
            self.nightscout_status = "duplicate_skipped"
            self.nightscout_error = None
            return

        try:
            await self.nightscout.async_upload_entry(entry)
        except LumiFlexError as err:
            self.nightscout_status = "upload_error"
            self.nightscout_error = str(err)
            return

        await self._async_save_last_uploaded(date_ms)
        self.nightscout_status = "uploaded"
        self.nightscout_error = None
