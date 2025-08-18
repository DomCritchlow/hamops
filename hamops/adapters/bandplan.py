"""Band plan adapter for querying US amateur radio frequency allocations.

This file should be saved as: hamops/adapters/bandplan.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from hamops.middleware.logging import log_error, log_info
from hamops.models.bandplan import (
    BandSegment,
    FrequencyInfo,
    BandSearchResult,
    BandPlanSummary,
)


class BandPlanAdapter:
    """Adapter for querying the US amateur radio band plan."""
    
    def __init__(self):
        """Initialize the band plan adapter and load data."""
        self.data: Optional[Dict[str, Any]] = None
        self.bands: List[Dict[str, Any]] = []
        self.indices: Dict[str, Any] = {}
        self._load_bandplan()
    
    def _load_bandplan(self) -> None:
        """Load the band plan JSON data into memory."""
        try:
            data_file = Path("hamops/data/us_bandplan.json")
            if not data_file.exists():
                log_error(
                    "bandplan_data_missing",
                    message=f"Band plan data file not found at {data_file}. Run scripts/gen_bandplan.py first.",
                )
                return
            
            with open(data_file, "r") as f:
                self.data = json.load(f)
                self.bands = self.data.get("bands", [])
                self.indices = self.data.get("indices", {})
            
            log_info(
                "bandplan_loaded",
                segments=len(self.bands),
                version=self.data.get("version"),
            )
        except Exception as e:
            log_error("bandplan_load_error", error=str(e))
            self.data = None
            self.bands = []
            self.indices = {}
    
    def parse_frequency(self, freq_str: str) -> Optional[int]:
        """Parse a frequency string with unit detection.
        
        Accepts formats like:
        - "14.225 MHz" or "14.225MHz"
        - "14225 kHz" or "14225kHz"  
        - "14225000 Hz" or "14225000"
        - "14,225,000" (with commas)
        - "14.225" (assumes MHz if has decimal)
        """
        if not freq_str:
            return None
        
        # Clean up the string
        freq_str = freq_str.strip().upper()
        freq_str = freq_str.replace(",", "")
        freq_str = freq_str.replace(" ", "")
        
        # Extract number and unit using regex
        match = re.match(r"^([\d.]+)([KMGH]?HZ)?$", freq_str)
        if not match:
            return None
        
        try:
            value = float(match.group(1))
            unit = match.group(2) or ""
            
            # Determine multiplier based on unit
            if unit == "GHZ":
                return int(value * 1_000_000_000)
            elif unit == "MHZ":
                return int(value * 1_000_000)
            elif unit == "KHZ":
                return int(value * 1_000)
            elif unit == "HZ":
                return int(value)
            else:
                # No unit specified - guess based on value
                if "." in match.group(1):
                    # Has decimal - assume MHz
                    return int(value * 1_000_000)
                elif value < 1000:
                    # Small number - assume MHz
                    return int(value * 1_000_000)
                elif value < 1_000_000:
                    # Medium number - assume kHz
                    return int(value * 1_000)
                else:
                    # Large number - assume Hz
                    return int(value)
        except ValueError:
            return None
    
    def get_frequency_info(self, frequency: int) -> FrequencyInfo:
        """Get information about what's available at a specific frequency.
        
        Args:
            frequency: Frequency in Hz
            
        Returns:
            FrequencyInfo with all bands containing this frequency
        """
        matching_bands = []
        
        # Find all band segments containing this frequency
        for band_data in self.bands:
            if band_data["minFrequency"] <= frequency <= band_data["maxFrequency"]:
                matching_bands.append(BandSegment(**band_data))
        
        # Aggregate information from matching bands
        all_modes = set()
        all_licenses = set()
        all_uses = set()
        primary_band = None
        
        for band in matching_bands:
            if band.mode:
                all_modes.add(band.mode)
            if band.licenseClass:
                all_licenses.update(band.licenseClass)
            if band.typicalUses:
                all_uses.update(band.typicalUses)
            if band.bandName and not primary_band:
                primary_band = band.bandName
        
        return FrequencyInfo(
            frequency=frequency,
            frequencyMHz=frequency / 1_000_000,
            bands=matching_bands,
            primaryBand=primary_band,
            allowedModes=sorted(list(all_modes)),
            requiredLicense=sorted(list(all_licenses)),
            typicalUses=sorted(list(all_uses)),
        )
    
    def search_bands(
        self,
        mode: Optional[str] = None,
        band_name: Optional[str] = None,
        license_class: Optional[str] = None,
        typical_use: Optional[str] = None,
        min_freq: Optional[int] = None,
        max_freq: Optional[int] = None,
    ) -> BandSearchResult:
        """Search for band segments matching criteria.
        
        Args:
            mode: Filter by mode (e.g., "CW", "USB", "FM")
            band_name: Filter by band name (e.g., "20m", "2m")
            license_class: Filter by required license (e.g., "General", "Extra")
            typical_use: Filter by typical use (e.g., "Phone", "Digital", "Satellite")
            min_freq: Minimum frequency in Hz
            max_freq: Maximum frequency in Hz
            
        Returns:
            BandSearchResult with matching segments
        """
        results = []
        candidate_indices = set()
        
        # Start with all bands if no specific filters
        if not any([mode, band_name, typical_use]):
            candidate_indices = set(range(len(self.bands)))
        
        # Use indices for efficient filtering
        if mode and mode in self.indices.get("modeIndex", {}):
            mode_indices = set(self.indices["modeIndex"][mode])
            if candidate_indices:
                candidate_indices &= mode_indices
            else:
                candidate_indices = mode_indices
        
        if band_name and band_name in self.indices.get("bandNameIndex", {}):
            band_indices = set(self.indices["bandNameIndex"][band_name])
            if candidate_indices:
                candidate_indices &= band_indices
            else:
                candidate_indices = band_indices
        
        if typical_use and typical_use in self.indices.get("useIndex", {}):
            use_indices = set(self.indices["useIndex"][typical_use])
            if candidate_indices:
                candidate_indices &= use_indices
            else:
                candidate_indices = use_indices
        
        # Apply additional filters
        for idx in candidate_indices:
            band_data = self.bands[idx]
            
            # Check license class
            if license_class:
                licenses = band_data.get("licenseClass", [])
                if license_class not in licenses:
                    continue
            
            # Check frequency range
            if min_freq and band_data["maxFrequency"] < min_freq:
                continue
            if max_freq and band_data["minFrequency"] > max_freq:
                continue
            
            results.append(BandSegment(**band_data))
        
        # Sort by frequency
        results.sort(key=lambda x: x.minFrequency)
        
        query = {
            "mode": mode,
            "band_name": band_name,
            "license_class": license_class,
            "typical_use": typical_use,
            "min_freq": min_freq,
            "max_freq": max_freq,
        }
        
        return BandSearchResult(
            query={k: v for k, v in query.items() if v is not None},
            count=len(results),
            bands=results,
        )
    
    def get_bands_in_range(self, min_freq: int, max_freq: int) -> List[BandSegment]:
        """Get all band segments within a frequency range.
        
        Args:
            min_freq: Minimum frequency in Hz
            max_freq: Maximum frequency in Hz
            
        Returns:
            List of BandSegment objects that overlap with the range
        """
        results = []
        
        for band_data in self.bands:
            # Check if band overlaps with the range
            if (
                band_data["minFrequency"] <= max_freq
                and band_data["maxFrequency"] >= min_freq
            ):
                results.append(BandSegment(**band_data))
        
        results.sort(key=lambda x: x.minFrequency)
        return results
    
    def get_summary(self) -> Optional[BandPlanSummary]:
        """Get summary information about the loaded band plan."""
        if not self.data:
            return None
        
        # Collect unique values
        band_names = set()
        modes = set()
        min_freq = float("inf")
        max_freq = 0
        
        for band in self.bands:
            if "bandName" in band:
                band_names.add(band["bandName"])
            if "mode" in band:
                modes.add(band["mode"])
            min_freq = min(min_freq, band["minFrequency"])
            max_freq = max(max_freq, band["maxFrequency"])
        
        return BandPlanSummary(
            version=self.data.get("version", "unknown"),
            source=self.data.get("source", "unknown"),
            country=self.data.get("country", "unknown"),
            totalSegments=len(self.bands),
            amateurBands=sorted(list(band_names)),
            availableModes=sorted(list(modes)),
            frequencyRange={"min": min_freq, "max": max_freq},
        )


# Create a singleton instance
_bandplan_adapter = None


def get_bandplan_adapter() -> BandPlanAdapter:
    """Get the singleton band plan adapter instance."""
    global _bandplan_adapter
    if _bandplan_adapter is None:
        _bandplan_adapter = BandPlanAdapter()
    return _bandplan_adapter