"""Pydantic models for solar propagation and space weather data.

This module defines data structures for solar indices, band conditions,
and propagation forecasts used by the propagation API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, field_serializer


class SolarIndices(BaseModel):
    """Current solar and geomagnetic indices."""
    
    solarFlux: float  # 10.7cm radio flux (SFU)
    sunspotNumber: int  # Smoothed sunspot number
    kIndex: float  # Planetary K-index (0-9)
    aIndex: int  # Planetary A-index
    solarWindSpeed: float  # km/s
    geomagneticField: str  # Qualitative assessment
    signalNoiseLevel: str  # S-meter noise level
    lastUpdated: datetime
    
    @field_serializer('lastUpdated')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class BandConditions(BaseModel):
    """Propagation conditions for a specific band."""
    
    day: str  # "Good", "Fair", "Poor"
    night: str  # "Good", "Fair", "Poor"


class CurrentConditions(BaseModel):
    """Current propagation conditions combining all data."""
    
    solarFlux: float
    sunspotNumber: int
    kIndex: float
    aIndex: int
    solarWindSpeed: float
    geomagneticField: str  # "Very Quiet", "Quiet", "Unsettled", "Active", "Storm"
    signalNoiseLevel: str  # "S0-S1", "S2-S3", etc.
    bandConditions: Dict[str, BandConditions]  # e.g., "80m-40m": {"day": "Fair", "night": "Good"}
    lastUpdated: datetime
    location: Optional[str] = "GLOBAL"
    muf: Optional[float] = None  # Maximum Usable Frequency in MHz
    
    @field_serializer('lastUpdated')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class PropagationForecast(BaseModel):
    """Single day propagation forecast."""
    
    date: str  # ISO date string
    predictedFlux: float
    predictedAindex: int
    predictedKindex: float
    conditions: str  # "Excellent", "Good", "Fair", "Poor", "Very Poor"
    notes: Optional[str] = None


class PropagationAnalysis(BaseModel):
    """Analysis of propagation for specific conditions."""
    
    query: Dict[str, str]  # The analysis parameters
    season: Optional[str] = None
    band: Optional[str] = None
    solarCycle: Optional[str] = None
    year: Optional[int] = None
    dayPropagation: str  # Description of daytime propagation
    nightPropagation: str  # Description of nighttime propagation
    maxDistance: str  # Typical maximum distance
    recommendations: List[str]  # Operating recommendations
    notes: Optional[str] = None


class MUFData(BaseModel):
    """Maximum Usable Frequency data for a location."""
    
    location: str  # Description or station name
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    muf3000km: float  # MUF for 3000km path in MHz
    foF2: Optional[float] = None  # Critical frequency in MHz
    timestamp: datetime
    station: Optional[str] = None  # Ionosonde station code
    
    @field_serializer('timestamp')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class SolarCycleData(BaseModel):
    """Solar cycle information for a specific year."""
    
    year: int
    observedSunspotNumber: Optional[float] = None
    predictedSunspotNumber: Optional[float] = None
    observedSolarFlux: Optional[float] = None
    predictedSolarFlux: Optional[float] = None
    cyclePhase: str  # "Solar minimum", "Rising", "Solar maximum", "Declining"
    cycleNumber: Optional[int] = None  # Solar cycle number (e.g., 25)
    expectedPropagation: str  # Description of expected conditions


class PropagationSummary(BaseModel):
    """Summary of current propagation conditions with recommendations."""
    
    summary: str  # Brief overall assessment
    currentActivity: str  # "Very Low", "Low", "Moderate", "High", "Very High"
    recommendations: Dict[str, str]  # Band-specific recommendations
    alerts: List[str]  # Any active space weather alerts
    lastUpdated: datetime
    
    @field_serializer('lastUpdated')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class AuroraData(BaseModel):
    """Aurora visibility and activity data."""
    
    observationTime: datetime
    forecastTime: datetime
    hemisphereData: Dict[str, Any]  # North/South hemisphere aurora data
    viewLine: Optional[List[float]] = None  # Latitude where aurora may be visible
    maxKp: float  # Maximum expected Kp
    visibility: str  # "Not Visible", "Low", "Moderate", "High"
    bestViewing: Optional[str] = None  # Best viewing locations
    
    @field_serializer('observationTime', 'forecastTime')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class SolarRegion(BaseModel):
    """Active solar region information."""
    
    region: int  # NOAA region number
    location: Optional[str] = None  # Position on solar disk (e.g., "N15W45")
    area: Optional[int] = None  # Area in millionths of hemisphere
    spotClass: Optional[str] = None  # McIntosh classification
    magneticClass: Optional[str] = None  # Magnetic classification
    numberOfSpots: Optional[int] = None
    flareActivity: Optional[str] = None  # Recent flare activity
    flareProbability: Optional[Dict[str, float]] = None  # C/M/X flare probabilities


class SolarEvent(BaseModel):
    """Solar flare or CME event."""
    
    eventId: str
    eventType: str  # "Flare", "CME", "Proton Event", etc.
    startTime: datetime
    peakTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    classType: Optional[str] = None  # For flares: "C", "M", "X" class
    sourceRegion: Optional[int] = None  # NOAA region number
    intensity: Optional[float] = None
    location: Optional[str] = None
    earthDirected: Optional[bool] = None  # For CMEs
    estimatedArrival: Optional[datetime] = None  # For Earth-directed CMEs
    notes: Optional[str] = None
    
    @field_serializer('startTime', 'peakTime', 'endTime', 'estimatedArrival')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None


class SpaceWeatherSummary(BaseModel):
    """Comprehensive space weather conditions."""
    
    solarActivity: str  # "Very Low", "Low", "Moderate", "High", "Very High"
    geomagneticActivity: str  # Current storm level
    radioBlackout: Optional[str] = None  # R0-R5 scale
    solarRadiation: Optional[str] = None  # S0-S5 scale
    geomagneticStorm: Optional[str] = None  # G0-G5 scale
    protonFlux: Optional[float] = None  # >10 MeV proton flux
    electronFlux: Optional[float] = None  # >2 MeV electron flux
    xrayFlux: Optional[Dict[str, float]] = None  # Short/Long wavelength
    activeRegions: int  # Number of active regions
    solarFlares24h: Dict[str, int]  # Count by class in last 24h
    earthDirectedCMEs: int  # Number of Earth-directed CMEs
    auroraActivity: Optional[str] = None  # Current aurora status
    timestamp: datetime
    
    @field_serializer('timestamp')
    def serialize_datetime(self, dt: datetime, _info) -> str:
        return dt.isoformat() + 'Z' if dt else None