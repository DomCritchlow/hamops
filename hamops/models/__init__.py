"""Model exports."""

from .aprs import APRSLocationRecord, APRSMessageRecord, APRSWeatherRecord
from .bandplan import BandSegment, FrequencyInfo, BandSearchResult, BandPlanSummary
from .callsign import CallsignRecord
from .propagation import (
    CurrentConditions,
    PropagationForecast,
    PropagationAnalysis,
    MUFData,
    SolarCycleData,
    AuroraData,
    SolarRegion,
    SolarEvent,
    SpaceWeatherSummary,
)

__all__ = [
    "CallsignRecord",
    "APRSLocationRecord",
    "APRSWeatherRecord",
    "APRSMessageRecord",
    "BandSegment",
    "FrequencyInfo",
    "BandSearchResult",
    "BandPlanSummary",
    "CurrentConditions",
    "PropagationForecast",
    "PropagationAnalysis",
    "MUFData",
    "SolarCycleData",
    "AuroraData",
    "SolarRegion",
    "SolarEvent",
    "SpaceWeatherSummary",
]