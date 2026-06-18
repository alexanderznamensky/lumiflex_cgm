"""Constants for the LumiFlex CGM integration."""

from __future__ import annotations

DOMAIN = "lumiflex_cgm"

CONF_UPDATE_INTERVAL = "update_interval"
CONF_NIGHTSCOUT_URL = "nightscout_url"
CONF_NIGHTSCOUT_API_SECRET = "nightscout_api_secret"

DEFAULT_UPDATE_INTERVAL = 5
MIN_UPDATE_INTERVAL = 0
MAX_UPDATE_INTERVAL = 60

LUMIFLEX_BASE_URL = "https://cloud.lumiflex.ru/api/v2"
LUMIFLEX_TIME_ZONE = "Europe/Moscow"

MANUFACTURER = "LumiFlex"
MODEL = "LumiFlex Cloud CGM"
