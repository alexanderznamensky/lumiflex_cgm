"""Sensors for LumiFlex CGM."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import LumiFlexCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up LumiFlex CGM sensors."""
    coordinator: LumiFlexCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LumiFlexGlucoseSensor(coordinator),
            LumiFlexMinutesSinceUpdateSensor(coordinator),
            LumiFlexTrendSensor(coordinator),
            LumiFlexPatientSensor(coordinator),
            LumiFlexNightscoutStatusSensor(coordinator),
        ]
    )


class LumiFlexBaseSensor(CoordinatorEntity[LumiFlexCoordinator], SensorEntity):
    """Base LumiFlex sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LumiFlexCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        identifiers = {(DOMAIN, data.get("sensor_id") or self.coordinator.entry.entry_id)}
        return {
            "identifiers": identifiers,
            "name": data.get("patient_name") or "LumiFlex CGM",
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "serial_number": data.get("device_sn"),
        }


class LumiFlexGlucoseSensor(LumiFlexBaseSensor):
    """Latest glucose value."""

    _attr_native_unit_of_measurement = "mmol/L"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:diabetes"

    def __init__(self, coordinator: LumiFlexCoordinator) -> None:
        super().__init__(coordinator, "glucose", "Glucose")

    @property
    def native_value(self) -> float | None:
        value = (self.coordinator.data or {}).get("glucose")
        return float(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "device_time": data.get("device_time"),
            "device_time_iso_local": data.get("device_time_iso_local"),
            "device_time_iso_utc": data.get("device_time_iso_utc"),
            "date_ms": data.get("date_ms"),
            "direction": data.get("direction"),
            "trend_type": data.get("trend_type"),
            "patient_no": data.get("patient_no"),
            "rpp_id": data.get("rpp_id"),
            "sensor_id": data.get("sensor_id"),
            "device_sn": data.get("device_sn"),
        }


class LumiFlexMinutesSinceUpdateSensor(LumiFlexBaseSensor):
    """Minutes since source update."""

    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: LumiFlexCoordinator) -> None:
        super().__init__(coordinator, "minutes_since_update", "Minutes since update")

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("minutes_since_update")


class LumiFlexTrendSensor(LumiFlexBaseSensor):
    """Trend / Nightscout direction."""

    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator: LumiFlexCoordinator) -> None:
        super().__init__(coordinator, "trend", "Trend")

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("direction")


class LumiFlexPatientSensor(LumiFlexBaseSensor):
    """Patient sensor."""

    _attr_icon = "mdi:account-heart"

    def __init__(self, coordinator: LumiFlexCoordinator) -> None:
        super().__init__(coordinator, "patient", "Patient")

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("patient_name")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "patient_no": data.get("patient_no"),
            "rpp_id": data.get("rpp_id"),
            "sensor_id": data.get("sensor_id"),
            "device_sn": data.get("device_sn"),
        }


class LumiFlexNightscoutStatusSensor(LumiFlexBaseSensor):
    """Nightscout upload status."""

    _attr_icon = "mdi:cloud-upload-outline"

    def __init__(self, coordinator: LumiFlexCoordinator) -> None:
        super().__init__(coordinator, "nightscout_status", "Nightscout status")

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get("nightscout_status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "error": data.get("nightscout_error"),
            "last_uploaded_date_ms": data.get("nightscout_last_uploaded_date_ms"),
        }
