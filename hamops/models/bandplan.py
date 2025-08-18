"""Pydantic models for band plan data.

This file should be saved as: hamops/models/bandplan.py

This module defines data structures for amateur radio band plans,
including frequency allocations, modes, and license privileges.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class BandSegment(BaseModel):
    """A segment of radio spectrum with specific allocations and rules."""
    
    minFrequency: int  # Frequency in Hz
    maxFrequency: int  # Frequency in Hz
    minFrequencyMHz: float  # Frequency in MHz for display
    maxFrequencyMHz: float  # Frequency in MHz for display
    minFrequencyDisplay: str  # Original display string
    maxFrequencyDisplay: str  # Original display string
    bandName: Optional[str] = None  # e.g., "20m", "2m", "70cm"
    mode: Optional[str] = None  # e.g., "CW", "USB", "LSB", "FM"
    description: Optional[str] = None  # Detailed description
    licenseClass: Optional[List[str]] = None  # Required license classes
    typicalUses: Optional[List[str]] = None  # Common uses for this segment
    color: Optional[str] = None  # Display color from original data
    step: Optional[int] = None  # Tuning step in Hz


class FrequencyInfo(BaseModel):
    """Information about what's available at a specific frequency."""
    
    frequency: int  # The queried frequency in Hz
    frequencyMHz: float  # The queried frequency in MHz
    bands: List[BandSegment]  # All band segments containing this frequency
    primaryBand: Optional[str] = None  # Main amateur band (e.g., "20m")
    allowedModes: List[str]  # Modes allowed at this frequency
    requiredLicense: List[str]  # License classes with privileges here
    typicalUses: List[str]  # Common activities at this frequency


class BandSearchResult(BaseModel):
    """Results from searching the band plan."""
    
    query: dict  # The search parameters used
    count: int  # Number of results
    bands: List[BandSegment]  # Matching band segments


class BandPlanSummary(BaseModel):
    """Summary information about the band plan."""
    
    version: str
    source: str
    country: str
    totalSegments: int
    amateurBands: List[str]  # List of band names (e.g., ["160m", "80m", ...])
    availableModes: List[str]  # All modes in the band plan
    frequencyRange: dict  # {"min": Hz, "max": Hz}