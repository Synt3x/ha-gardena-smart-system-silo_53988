"""Constants for GARDENA SILENO local."""

DOMAIN = "gardena_sileno_local"

CONF_START_MINUTES = "start_minutes"
DEFAULT_START_MINUTES = 180

# What the lawn mower card's Dock button does.
CONF_DOCK_MODE = "dock_mode"
DOCK_NEXT_SCHEDULE = "next_schedule"
DOCK_FURTHER_NOTICE = "further_notice"
DEFAULT_DOCK_MODE = DOCK_NEXT_SCHEDULE

MODEL_NAMES = {
    "53988": "smart SILENO city/life (LONA)",
    "29694": "smart SILENO city/life",
    "6146": "smart SILENO",
}
