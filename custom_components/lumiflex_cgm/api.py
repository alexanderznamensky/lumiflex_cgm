"""API client for LumiFlex Cloud and Nightscout."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from .const import LUMIFLEX_BASE_URL, LUMIFLEX_TIME_ZONE

LOGIN_ENDPOINT = "/user/login"
HOME_ENDPOINT = "/home/doctor/listHomeData"
MONITOR_ENDPOINT = "/monitor/getOneMonitor"


class LumiFlexError(Exception):
    """Base LumiFlex error."""


class LumiFlexAuthError(LumiFlexError):
    """Authentication error."""


def _msk_tz():
    try:
        return ZoneInfo(LUMIFLEX_TIME_ZONE)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3), name="MSK")


TZ_MSK = _msk_tz()


def clean_token(token: str | None) -> str:
    """Clean copied browser token."""
    return (token or "").strip().strip('"').strip("'").rstrip("^").strip()


def normalize_nightscout_url(url: str | None) -> str:
    """Normalize Nightscout base URL to /api/v1/entries."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/v1"):
        return f"{base}/entries"
    if base.endswith("/api/v1/entries"):
        return base
    return f"{base}/api/v1/entries"


def nightscout_secret_hash(api_secret: str) -> str:
    """Nightscout API v1 expects SHA1 hash in api-secret header."""
    return hashlib.sha1(api_secret.encode("utf-8")).hexdigest()


def parse_local_time(value: str | None) -> datetime | None:
    """Parse LumiFlex local datetime as Moscow time."""
    if not value or not isinstance(value, str):
        return None

    raw = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=TZ_MSK)
        except ValueError:
            pass

    try:
        dt_local = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt_local.tzinfo is None:
        return dt_local.replace(tzinfo=TZ_MSK)
    return dt_local.astimezone(TZ_MSK)


def parse_device_time(device_time: str | None) -> tuple[datetime | None, int | None, str | None, str | None]:
    """Parse LumiFlex deviceTimeStr as Moscow local time and return UTC details."""
    dt_local = parse_local_time(device_time)
    if dt_local is None:
        return None, None, None, None

    dt_utc = dt_local.astimezone(timezone.utc)
    date_ms = int(dt_utc.timestamp() * 1000)
    return dt_local, date_ms, dt_local.isoformat(timespec="seconds"), dt_utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_sensor_life(start_up_time: str | None, lifetime_days: Any) -> dict[str, Any]:
    """Calculate remaining sensor lifetime from startUpTime and et days."""
    start = parse_local_time(start_up_time)
    try:
        total_days = int(float(lifetime_days)) if lifetime_days is not None else None
    except (TypeError, ValueError):
        total_days = None

    result: dict[str, Any] = {
        "sensor_start_time": start_up_time,
        "sensor_lifetime_days": total_days,
        "sensor_expiration_time_iso_local": None,
        "sensor_expiration_time_iso_utc": None,
        "sensor_days_left": None,
        "sensor_expired": None,
    }

    if start is None or total_days is None or total_days <= 0:
        return result

    expiration_local = start + timedelta(days=total_days)
    expiration_utc = expiration_local.astimezone(timezone.utc)
    remaining_seconds = (expiration_local - datetime.now(TZ_MSK)).total_seconds()

    result.update({
        "sensor_expiration_time_iso_local": expiration_local.isoformat(timespec="seconds"),
        "sensor_expiration_time_iso_utc": expiration_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        # LumiFlex UI shows full days rounded up: 9d 22h => 10 days.
        "sensor_days_left": max(0, math.ceil(remaining_seconds / 86400)),
        "sensor_expired": remaining_seconds <= 0,
    })
    return result


def trend_to_direction(trend_type: Any) -> str:
    """Map LumiFlex trend type to Nightscout direction."""
    if trend_type is None:
        return "Flat"
    value = str(trend_type).strip().lower()
    mapping = {
        "0": "Flat",
        "1": "SingleUp",
        "2": "DoubleUp",
        "3": "SingleDown",
        "4": "DoubleDown",
        "flat": "Flat",
        "stable": "Flat",
        "up": "SingleUp",
        "down": "SingleDown",
    }
    return mapping.get(value, "Flat")


class LumiFlexApi:
    """Minimal async API client for LumiFlex Cloud."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        base_url: str = LUMIFLEX_BASE_URL,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._token: str = ""

    def _url(self, endpoint: str) -> str:
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return f"{self._base_url}{endpoint}"

    def _headers(self, token: str = "", include_content_type: bool = False) -> dict[str, str]:
        """Build LumiFlex API headers."""
        headers = {
            "Accept": "application/json",
            "Time-Zone": LUMIFLEX_TIME_ZONE,
        }
        if include_content_type:
            headers["Content-Type"] = "application/json"

        token = clean_token(token)
        if token:
            headers["Token"] = token
        return headers

    @staticmethod
    async def _json_or_error(response: aiohttp.ClientResponse) -> dict[str, Any]:
        """Read JSON response or raise a LumiFlex error."""
        text = await response.text()
        if response.status >= 400:
            raise LumiFlexError(f"HTTP {response.status}: {text[:500]}")
        try:
            return await response.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            raise LumiFlexError(f"LumiFlex response is not JSON: {text[:500]}") from err

    def _store_response_token(self, response: aiohttp.ClientResponse) -> None:
        """Store token from response header when LumiFlex returns it."""
        header_token = clean_token(response.headers.get("token"))
        if header_token:
            self._token = header_token

    async def _post(self, endpoint: str, payload: dict[str, Any] | None = None, token: str = "") -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=45)
        async with self._session.post(
            self._url(endpoint),
            headers=self._headers(token, include_content_type=True),
            json=payload or {},
            timeout=timeout,
        ) as response:
            data = await self._json_or_error(response)
            self._store_response_token(response)
            return data

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        token: str = "",
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=45)
        async with self._session.get(
            self._url(endpoint),
            headers=self._headers(token),
            params=params or {},
            timeout=timeout,
        ) as response:
            data = await self._json_or_error(response)
            self._store_response_token(response)
            return data

    async def async_login(self) -> None:
        """Login and store response header token."""
        payload = {
            "userName": self._username,
            "password": self._password,
            "project": "pancares-new",
            "appId": "eu",
            "identity": 2,
            "passwordType": 1,
            "operation": "NORMAL",
        }
        data = await self._post(LOGIN_ENDPOINT, payload=payload)
        if str(data.get("code")) != "200" or not self._token:
            raise LumiFlexAuthError(f"Login failed: {data}")

    async def async_get_home_data(self) -> dict[str, Any]:
        """Fetch current home data, refreshing token if needed."""
        if not self._token:
            await self.async_login()

        data = await self._post(HOME_ENDPOINT, payload={}, token=self._token)
        if str(data.get("code")) == "801":
            await self.async_login()
            data = await self._post(HOME_ENDPOINT, payload={}, token=self._token)

        if str(data.get("code")) != "200":
            raise LumiFlexError(f"LumiFlex error: {data}")
        return data

    async def async_get_monitor_data(self, rpp_id: str) -> dict[str, Any]:
        """Fetch detailed monitor data by rppId."""
        if not self._token:
            await self.async_login()

        data = await self._get(MONITOR_ENDPOINT, params={"rppId": rpp_id}, token=self._token)
        if str(data.get("code")) == "801":
            await self.async_login()
            data = await self._get(MONITOR_ENDPOINT, params={"rppId": rpp_id}, token=self._token)

        if str(data.get("code")) != "200":
            raise LumiFlexError(f"LumiFlex monitor error: {data}")
        return data

    async def async_get_current(self) -> dict[str, Any]:
        """Fetch and parse latest current glucose data."""
        raw = await self.async_get_home_data()
        parsed = parse_home_data(raw)

        rpp_id = parsed.get("rpp_id")
        if rpp_id:
            monitor_raw = await self.async_get_monitor_data(str(rpp_id))
            monitor_parsed = parse_monitor_data(monitor_raw)
            for key, value in monitor_parsed.items():
                if value is not None:
                    parsed[key] = value

        return parsed


class NightscoutApi:
    """Small Nightscout API v1 uploader."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_secret: str) -> None:
        self._session = session
        self._entries_url = normalize_nightscout_url(url)
        self._api_secret = (api_secret or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self._entries_url and self._api_secret)

    async def async_upload_entry(self, entry: dict[str, Any]) -> None:
        """Upload a single entry to Nightscout API v1."""
        if not self.configured:
            return
        headers = {
            "Content-Type": "application/json",
            "api-secret": nightscout_secret_hash(self._api_secret),
        }
        timeout = aiohttp.ClientTimeout(total=30)
        # Nightscout v1 upload examples commonly POST an array of entries.
        async with self._session.post(
            self._entries_url, headers=headers, json=[entry], timeout=timeout
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise LumiFlexError(f"Nightscout HTTP {response.status}: {text[:500]}")


def _parse_monitor(monitor: dict[str, Any], patient: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse one LumiFlex monitor object."""
    patient = patient or {}

    first_name = monitor.get("firstName") or patient.get("firstName")
    middle_name = monitor.get("middleName") or patient.get("middleName")
    last_name = monitor.get("lastName") or patient.get("lastName")
    full_name = " ".join(x for x in [last_name, first_name, middle_name] if x)

    glucose = monitor.get("glucose")
    device_time = monitor.get("deviceTimeStr") or monitor.get("deviceTime")
    dt_local, date_ms, iso_local, iso_utc = parse_device_time(device_time)

    minutes_since_update = None
    if dt_local is not None:
        minutes_since_update = max(0, int((datetime.now(TZ_MSK) - dt_local).total_seconds() // 60))

    trend_type = monitor.get("trendType")
    parsed = {
        "glucose": glucose,
        "unit": "mmol/L",
        "device_time": device_time,
        "device_time_iso_local": iso_local,
        "device_time_iso_utc": iso_utc,
        "date_ms": date_ms,
        "minutes_since_update": minutes_since_update,
        "patient_name": full_name or None,
        "patient_no": monitor.get("patientNo") or patient.get("patientNo"),
        "rpp_id": monitor.get("rppId"),
        "device_sn": monitor.get("deviceSn"),
        "sensor_id": monitor.get("sensorId"),
        "trend_type": trend_type,
        "direction": trend_to_direction(trend_type),
    }
    parsed.update(parse_sensor_life(monitor.get("startUpTime"), monitor.get("et")))
    return parsed


def parse_home_data(data: dict[str, Any]) -> dict[str, Any]:
    """Parse LumiFlex listHomeData response."""
    root = data.get("data") or {}
    monitor_list = root.get("monitorList") or []
    patient_list = root.get("patientList") or []

    monitor = monitor_list[0] if monitor_list else {}
    patient = patient_list[0] if patient_list else {}
    return _parse_monitor(monitor, patient)


def parse_monitor_data(data: dict[str, Any]) -> dict[str, Any]:
    """Parse LumiFlex getOneMonitor response."""
    monitor = data.get("data") or {}
    return _parse_monitor(monitor)


def build_nightscout_entry(data: dict[str, Any]) -> dict[str, Any] | None:
    """Build Nightscout entry from parsed LumiFlex data."""
    glucose = data.get("glucose")
    date_ms = data.get("date_ms")
    date_string = data.get("device_time_iso_utc")
    if glucose is None or date_ms is None or date_string is None:
        return None

    try:
        sgv = round(float(glucose) * 18)
    except (TypeError, ValueError):
        return None

    return {
        "type": "sgv",
        "sgv": sgv,
        "date": date_ms,
        "dateString": date_string,
        "device": "lumiflex-cloud",
        "direction": data.get("direction") or "Flat",
    }
