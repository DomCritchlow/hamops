"""Adapter for fetching and processing solar propagation data.

This module fetches real-time solar indices from hamqsl.com and
NOAA space weather JSON APIs, providing propagation analysis and forecasts.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

import httpx

from hamops.middleware.logging import log_error, log_info, log_warning
from hamops.models.propagation import (
    CurrentConditions,
    BandConditions,
    PropagationForecast,
    PropagationAnalysis,
    MUFData,
    SolarCycleData,
    AuroraData,
    SolarRegion,
    SolarEvent,
    SpaceWeatherSummary,
)


class PropagationAdapter:
    """Adapter for solar propagation and space weather data."""
    
    def __init__(self):
        """Initialize the propagation adapter."""
        # Primary data sources
        self.hamqsl_url = "https://www.hamqsl.com/solarxml.php"
        
        # NOAA JSON endpoints
        self.noaa_base = "https://services.swpc.noaa.gov/json"
        self.noaa_endpoints = {
            "k_index": f"{self.noaa_base}/planetary_k_index_1m.json",
            "solar_flux": f"{self.noaa_base}/f107_cm_flux.json",
            "predicted_flux": f"{self.noaa_base}/predicted_f107cm_flux.json",
            "predicted_k": f"{self.noaa_base}/predicted_fredericksburg_a_index.json",
            "sunspot_number": f"{self.noaa_base}/solar-cycle/sunspots.json",
            "sunspot_smoothed": f"{self.noaa_base}/solar-cycle/sunspots-smoothed.json",
            "solar_cycle": f"{self.noaa_base}/solar-cycle/predicted-solar-cycle.json",
            "solar_regions": f"{self.noaa_base}/solar_regions.json",
            "solar_wind": f"{self.noaa_base}/rtsw/rtsw_wind_1m.json",
            "aurora": f"{self.noaa_base}/ovation_aurora_latest.json",
            "solar_events": f"{self.noaa_base}/edited_events.json",
            "goes_xray": f"{self.noaa_base}/goes/primary/xrays-6-hour.json",
            "goes_proton": f"{self.noaa_base}/goes/primary/integral-protons-1-day.json",
            "goes_electron": f"{self.noaa_base}/goes/primary/integral-electrons-1-day.json",
            "solar_probabilities": f"{self.noaa_base}/solar_probabilities.json",
        }
        
        # KC2G ionosonde (future implementation)
        self.kc2g_ionosonde_url = "https://prop.kc2g.com/api/stations.json"
        
        # Load static knowledge base
        self._load_knowledge_base()
        
        # Cache for data with TTL
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._cache_ttl = 900  # 15 minutes
    
    def _load_knowledge_base(self) -> None:
        """Load static propagation knowledge from JSON file."""
        try:
            kb_file = Path("hamops/data/propagation_knowledge.json")
            if kb_file.exists():
                with open(kb_file, "r") as f:
                    self.knowledge = json.load(f)
            else:
                # Default knowledge base
                self.knowledge = self._get_default_knowledge()
                # Try to save it for future use
                try:
                    kb_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(kb_file, "w") as f:
                        json.dump(self.knowledge, f, indent=2)
                except Exception:
                    pass  # Non-critical if we can't save
        except Exception as e:
            log_warning("propagation_kb_load_error", error=str(e))
            self.knowledge = self._get_default_knowledge()
    
    def _get_default_knowledge(self) -> Dict[str, Any]:
        """Get default propagation knowledge base."""
        return {
            "seasonal": {
                "summer": {
                    "80m": {
                        "day": "Mostly NVIS (~100-300 km) due to strong D-layer absorption",
                        "night": "Good up to 1500+ km, but reduced from winter",
                    },
                    "40m": {
                        "day": "Limited range (~500 km) due to D-layer absorption",
                        "night": "Good for intercontinental DX",
                    },
                    "20m": {
                        "day": "Excellent worldwide propagation if solar flux adequate",
                        "night": "Limited, depends on solar activity",
                    },
                    "10m": {
                        "day": "Open during solar maximum, sporadic-E in summer",
                        "night": "Usually closed except during high solar activity",
                    },
                },
                "winter": {
                    "80m": {
                        "day": "Better than summer, 500-1000 km possible",
                        "night": "Excellent DX, can work worldwide",
                    },
                    "40m": {
                        "day": "Good regional coverage",
                        "night": "Excellent worldwide DX",
                    },
                    "20m": {
                        "day": "Excellent with slightly higher MUF than summer",
                        "night": "Good during solar maximum periods",
                    },
                    "10m": {
                        "day": "Open during solar maximum",
                        "night": "Rarely open, needs high solar activity",
                    },
                },
            },
            "solar_cycle": {
                "minimum": {
                    "description": "Solar flux 65-75, few sunspots",
                    "propagation": "Poor upper HF (15m/10m), rely on 20m and below",
                },
                "rising": {
                    "description": "Solar flux 75-120, increasing sunspots",
                    "propagation": "Improving conditions, 15m opening regularly",
                },
                "maximum": {
                    "description": "Solar flux 120-200+, many sunspots",
                    "propagation": "Excellent HF propagation, 10m open daily for DX",
                },
                "declining": {
                    "description": "Solar flux 80-120, decreasing sunspots",
                    "propagation": "Good but declining, enjoy while it lasts",
                },
            },
            "geomagnetic": {
                "quiet": {
                    "k_range": [0, 3],
                    "description": "Stable ionosphere, excellent propagation",
                    "effects": "Higher MUF, lower noise, better DX",
                },
                "unsettled": {
                    "k_range": [4, 4],
                    "description": "Minor disturbances possible",
                    "effects": "Slightly degraded conditions, some fading",
                },
                "active": {
                    "k_range": [5, 5],
                    "description": "Storm conditions beginning",
                    "effects": "Degraded HF, auroral propagation possible",
                },
                "storm": {
                    "k_range": [6, 9],
                    "description": "Geomagnetic storm in progress",
                    "effects": "HF blackout likely, enhanced VHF auroral",
                },
            },
        }
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache_times:
            return False
        age = (datetime.utcnow() - self._cache_times[key]).total_seconds()
        return age < self._cache_ttl
    
    async def _fetch_noaa_json(self, endpoint_key: str) -> Optional[Any]:
        """Fetch JSON data from NOAA endpoint."""
        if endpoint_key not in self.noaa_endpoints:
            return None
        
        url = self.noaa_endpoints[endpoint_key]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            log_error(f"noaa_json_fetch_error_{endpoint_key}", error=str(e), url=url)
            return None
    
    async def fetch_current_conditions(
        self, location: Optional[str] = None
    ) -> Optional[CurrentConditions]:
        """Fetch current solar and propagation conditions.
        
        Combines data from:
        1. Hamqsl.com for band conditions
        2. NOAA JSON APIs for precise solar indices
        """
        cache_key = "current_conditions"
        
        # Check cache
        if self._is_cache_valid(cache_key):
            data = self._cache[cache_key]
            if location and location != "GLOBAL":
                # Add location-specific MUF if requested
                muf_data = await self.fetch_muf(location)
                if muf_data:
                    data.muf = muf_data.muf3000km
                    data.location = location
            return data
        
        try:
            # Fetch from multiple sources in parallel
            # 1. Get hamqsl data for band conditions
            hamqsl_task = self._fetch_hamqsl_data()
            
            # 2. Get NOAA K-index
            k_index_data = await self._fetch_noaa_json("k_index")
            
            # 3. Get NOAA solar flux
            flux_data = await self._fetch_noaa_json("solar_flux")
            
            # 4. Get sunspot number
            ssn_data = await self._fetch_noaa_json("sunspot_number")
            
            # 5. Get solar wind data
            wind_data = await self._fetch_noaa_json("solar_wind")
            
            # Wait for hamqsl data
            hamqsl_conditions = await hamqsl_task
            
            # Extract latest values from NOAA data
            k_index = 0.0
            a_index = 0
            if k_index_data and isinstance(k_index_data, list) and len(k_index_data) > 0:
                # Get the most recent K-index
                latest_k = k_index_data[-1]
                k_index = float(latest_k.get("planetary_k_index", 0))
                a_index = int(latest_k.get("planetary_a_index", 0))
            
            solar_flux = 100.0
            if flux_data and isinstance(flux_data, list) and len(flux_data) > 0:
                # Get the most recent flux
                latest_flux = flux_data[-1]
                solar_flux = float(latest_flux.get("flux", 100))
            
            sunspot_number = 50
            if ssn_data and isinstance(ssn_data, list) and len(ssn_data) > 0:
                # Get the most recent sunspot number
                latest_ssn = ssn_data[-1]
                sunspot_number = int(latest_ssn.get("sunspot_number", 50))
            
            solar_wind_speed = 400.0
            if wind_data and isinstance(wind_data, list) and len(wind_data) > 0:
                # Get the most recent solar wind speed
                latest_wind = wind_data[-1]
                solar_wind_speed = float(latest_wind.get("proton_speed", 400))
            
            # Determine geomagnetic field status from K-index
            if k_index >= 6:
                geo_field = "Storm"
            elif k_index >= 5:
                geo_field = "Active"
            elif k_index >= 4:
                geo_field = "Unsettled"
            elif k_index >= 2:
                geo_field = "Quiet"
            else:
                geo_field = "Very Quiet"
            
            # Determine signal noise level
            if k_index >= 5:
                signal_noise = "S3-S5"
            elif k_index >= 4:
                signal_noise = "S2-S3"
            elif k_index >= 3:
                signal_noise = "S1-S2"
            else:
                signal_noise = "S0-S1"
            
            # Use hamqsl band conditions if available, otherwise estimate
            if hamqsl_conditions:
                band_conditions = hamqsl_conditions.bandConditions
            else:
                # Estimate band conditions from solar indices
                band_conditions = self._estimate_band_conditions(solar_flux, k_index)
            
            conditions = CurrentConditions(
                solarFlux=solar_flux,
                sunspotNumber=sunspot_number,
                kIndex=k_index,
                aIndex=a_index,
                solarWindSpeed=solar_wind_speed,
                geomagneticField=geo_field,
                signalNoiseLevel=signal_noise,
                bandConditions=band_conditions,
                lastUpdated=datetime.utcnow(),
                location="GLOBAL",
            )
            
            # Cache the result
            self._cache[cache_key] = conditions
            self._cache_times[cache_key] = datetime.utcnow()
            
            # Add location-specific MUF if requested
            if location and location != "GLOBAL":
                muf_data = await self.fetch_muf(location)
                if muf_data:
                    conditions.muf = muf_data.muf3000km
                    conditions.location = location
            
            log_info(
                "propagation_conditions_fetched",
                sfi=conditions.solarFlux,
                k_index=conditions.kIndex,
                source="combined",
            )
            
            return conditions
            
        except Exception as e:
            log_error("propagation_fetch_error", error=str(e))
            return None
    
    async def _fetch_hamqsl_data(self) -> Optional[CurrentConditions]:
        """Fetch and parse hamqsl XML data."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.hamqsl_url)
                response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.text)
            solar_data = root.find("solardata")
            if not solar_data:
                return None
            
            def get_float(elem: Optional[ET.Element], default: float = 0.0) -> float:
                if elem is not None and elem.text:
                    try:
                        return float(elem.text)
                    except ValueError:
                        return default
                return default
            
            def get_int(elem: Optional[ET.Element], default: int = 0) -> int:
                if elem is not None and elem.text:
                    try:
                        return int(float(elem.text))
                    except ValueError:
                        return default
                return default
            
            def get_text(elem: Optional[ET.Element], default: str = "") -> str:
                if elem is not None and elem.text:
                    return elem.text.strip()
                return default
            
            # Parse band conditions
            band_conditions = {}
            for band in root.findall(".//band"):
                name = band.get("name", "")
                time_attr = band.get("time", "")
                condition = band.text or "Unknown"
                
                if name and time_attr:
                    if name not in band_conditions:
                        band_conditions[name] = BandConditions(day="Unknown", night="Unknown")
                    
                    if time_attr.lower() == "day":
                        band_conditions[name].day = condition
                    else:
                        band_conditions[name].night = condition
            
            # Get update time
            updated_elem = solar_data.find("updated")
            if updated_elem is not None and updated_elem.text:
                try:
                    last_updated = datetime.strptime(
                        updated_elem.text.replace(" GMT", ""),
                        "%d %b %Y %H%M"
                    )
                except ValueError:
                    last_updated = datetime.utcnow()
            else:
                last_updated = datetime.utcnow()
            
            return CurrentConditions(
                solarFlux=get_float(solar_data.find("solarflux")),
                sunspotNumber=get_int(solar_data.find("sunspots")),
                kIndex=get_float(solar_data.find("kindex")),
                aIndex=get_int(solar_data.find("aindex")),
                solarWindSpeed=get_float(solar_data.find("solarwind")),
                geomagneticField=get_text(solar_data.find("geomagfield"), "Unknown"),
                signalNoiseLevel=get_text(solar_data.find("signalnoise"), "S0"),
                bandConditions=band_conditions,
                lastUpdated=last_updated,
                location="GLOBAL",
            )
        except Exception as e:
            log_warning("hamqsl_fetch_error", error=str(e))
            return None
    
    def _estimate_band_conditions(self, solar_flux: float, k_index: float) -> Dict[str, BandConditions]:
        """Estimate band conditions from solar indices."""
        conditions = {}
        
        # Basic estimation logic
        if solar_flux >= 150 and k_index <= 3:
            # Excellent conditions
            conditions["80m-40m"] = BandConditions(day="Fair", night="Good")
            conditions["30m-20m"] = BandConditions(day="Good", night="Good")
            conditions["17m-15m"] = BandConditions(day="Good", night="Fair")
            conditions["12m-10m"] = BandConditions(day="Good", night="Fair")
        elif solar_flux >= 100 and k_index <= 4:
            # Good conditions
            conditions["80m-40m"] = BandConditions(day="Fair", night="Good")
            conditions["30m-20m"] = BandConditions(day="Good", night="Fair")
            conditions["17m-15m"] = BandConditions(day="Fair", night="Poor")
            conditions["12m-10m"] = BandConditions(day="Fair", night="Poor")
        elif k_index >= 5:
            # Disturbed conditions
            conditions["80m-40m"] = BandConditions(day="Poor", night="Fair")
            conditions["30m-20m"] = BandConditions(day="Fair", night="Poor")
            conditions["17m-15m"] = BandConditions(day="Poor", night="Poor")
            conditions["12m-10m"] = BandConditions(day="Poor", night="Poor")
        else:
            # Low solar activity
            conditions["80m-40m"] = BandConditions(day="Fair", night="Good")
            conditions["30m-20m"] = BandConditions(day="Fair", night="Fair")
            conditions["17m-15m"] = BandConditions(day="Poor", night="Poor")
            conditions["12m-10m"] = BandConditions(day="Poor", night="Poor")
        
        return conditions
    
    async def fetch_forecast(
        self, days: int = 27
    ) -> List[PropagationForecast]:
        """Fetch propagation forecast from NOAA JSON APIs.
        
        Uses the predicted flux and K-index data from NOAA.
        """
        cache_key = f"forecast_{days}"
        
        # Check cache (cache for 6 hours for forecasts)
        if cache_key in self._cache_times:
            age = (datetime.utcnow() - self._cache_times[cache_key]).total_seconds()
            if age < 21600:  # 6 hours
                return self._cache.get(cache_key, [])
        
        try:
            # Fetch predicted flux and K-index from NOAA
            flux_data = await self._fetch_noaa_json("predicted_flux")
            k_data = await self._fetch_noaa_json("predicted_k")
            
            forecasts = []
            
            if flux_data and isinstance(flux_data, list):
                for i, entry in enumerate(flux_data[:days]):
                    # Parse date from time_tag
                    time_tag = entry.get("time_tag", "")
                    if time_tag:
                        try:
                            date = datetime.fromisoformat(time_tag.replace("Z", ""))
                            date_str = date.strftime("%Y-%m-%d")
                        except:
                            date = datetime.utcnow() + timedelta(days=i)
                            date_str = date.strftime("%Y-%m-%d")
                    else:
                        date = datetime.utcnow() + timedelta(days=i)
                        date_str = date.strftime("%Y-%m-%d")
                    
                    flux = float(entry.get("predicted_flux", 100))
                    
                    # Get corresponding K/A index if available
                    a_index = 10
                    k_index = 2.0
                    if k_data and isinstance(k_data, list) and i < len(k_data):
                        k_entry = k_data[i]
                        a_index = int(k_entry.get("predicted_a", 10))
                        # Estimate K from A
                        k_index = min(9, max(0, a_index / 8))
                    
                    # Determine conditions
                    if k_index >= 6:
                        conditions = "Very Poor"
                        notes = "Geomagnetic storm - HF blackout likely"
                    elif k_index >= 5:
                        conditions = "Poor"
                        notes = "Minor storm - degraded HF propagation"
                    elif k_index >= 4:
                        conditions = "Fair"
                        notes = "Unsettled - some HF degradation"
                    elif flux >= 150 and k_index <= 2:
                        conditions = "Excellent"
                        notes = "High flux, quiet field - optimal DX"
                    elif flux >= 100 and k_index <= 3:
                        conditions = "Good"
                        notes = "Moderate flux, stable conditions"
                    else:
                        conditions = "Fair"
                        notes = "Low flux - limited upper HF"
                    
                    forecasts.append(
                        PropagationForecast(
                            date=date_str,
                            predictedFlux=flux,
                            predictedAindex=a_index,
                            predictedKindex=k_index,
                            conditions=conditions,
                            notes=notes,
                        )
                    )
            
            # If no data from NOAA, generate defaults
            if not forecasts:
                log_warning("noaa_forecast_empty", message="No forecast data from NOAA")
                today = datetime.utcnow()
                for i in range(min(7, days)):
                    date = today + timedelta(days=i)
                    forecasts.append(
                        PropagationForecast(
                            date=date.strftime("%Y-%m-%d"),
                            predictedFlux=100.0,
                            predictedAindex=10,
                            predictedKindex=2.0,
                            conditions="Fair",
                            notes="Default forecast - actual data unavailable",
                        )
                    )
            
            # Cache the result
            self._cache[cache_key] = forecasts
            self._cache_times[cache_key] = datetime.utcnow()
            
            log_info("propagation_forecast_fetched", days=len(forecasts), source="noaa_json")
            return forecasts
            
        except Exception as e:
            log_error("propagation_forecast_error", error=str(e))
            return []
    
    def analyze_propagation(
        self,
        season: Optional[str] = None,
        band: Optional[str] = None,
        solar_cycle: Optional[str] = None,
        year: Optional[int] = None,
    ) -> PropagationAnalysis:
        """Analyze propagation for given conditions.
        
        Args:
            season: "summer" or "winter"
            band: Amateur band (e.g., "20m", "40m")
            solar_cycle: Cycle phase or "min"/"max"
            year: Specific year for cycle analysis
            
        Returns:
            PropagationAnalysis with recommendations
        """
        query = {}
        if season:
            query["season"] = season
        if band:
            query["band"] = band
        if solar_cycle:
            query["solar_cycle"] = solar_cycle
        if year:
            query["year"] = str(year)
        
        # Default responses
        day_prop = "Varies by band and solar conditions"
        night_prop = "Varies by band and solar conditions"
        max_dist = "Depends on band and conditions"
        recommendations = []
        
        # Season + band analysis
        if season and band:
            season_data = self.knowledge.get("seasonal", {}).get(season, {})
            band_data = season_data.get(band, {})
            if band_data:
                day_prop = band_data.get("day", day_prop)
                night_prop = band_data.get("night", night_prop)
                
                # Add recommendations based on season
                if season == "summer":
                    if band in ["80m", "40m"]:
                        recommendations.append("Focus on nighttime operation due to D-layer absorption")
                    if band in ["10m", "6m"]:
                        recommendations.append("Watch for sporadic-E openings in late afternoon")
                elif season == "winter":
                    if band in ["80m", "40m"]:
                        recommendations.append("Excellent DX opportunities at night")
                    if band == "20m":
                        recommendations.append("Higher MUF than summer - good daytime DX")
        
        # Solar cycle analysis
        if solar_cycle:
            cycle_data = self.knowledge.get("solar_cycle", {}).get(solar_cycle, {})
            if cycle_data:
                if not recommendations:
                    desc = cycle_data.get("propagation", "")
                    if desc:
                        recommendations.append(desc)
                
                # Adjust distance based on cycle
                if solar_cycle == "maximum":
                    max_dist = "Worldwide on most HF bands"
                elif solar_cycle == "minimum":
                    max_dist = "Limited on upper HF, good on lower bands"
        
        # Year-specific analysis
        if year:
            # Determine solar cycle phase for the year
            # Cycle 25 started Dec 2019, expected to peak 2024-2025
            if 2019 <= year <= 2020:
                cycle_phase = "Solar minimum"
            elif 2021 <= year <= 2023:
                cycle_phase = "Rising"
            elif 2024 <= year <= 2026:
                cycle_phase = "Solar maximum"
            elif 2027 <= year <= 2030:
                cycle_phase = "Declining"
            else:
                cycle_phase = "Unknown"
            
            if not solar_cycle:
                recommendations.append(f"Year {year} is in {cycle_phase} phase of Solar Cycle 25")
        
        return PropagationAnalysis(
            query=query,
            season=season,
            band=band,
            solarCycle=solar_cycle,
            year=year,
            dayPropagation=day_prop,
            nightPropagation=night_prop,
            maxDistance=max_dist,
            recommendations=recommendations if recommendations else ["Check current solar indices for best assessment"],
        )
    
    async def fetch_muf(
        self, location: str
    ) -> Optional[MUFData]:
        """Fetch MUF data for a location.
        
        Args:
            location: Location string or coordinates
            
        Returns:
            MUFData object or None if not found
        """
        # This is a simplified implementation
        # In production, you would query the KC2G ionosonde API
        # and find the nearest station
        
        try:
            # For demo purposes, return estimated MUF based on current conditions
            conditions = await self.fetch_current_conditions()
            if conditions:
                # Rough MUF estimation from solar flux
                # MUF ≈ 9 MHz + (SFI - 70) * 0.1
                estimated_muf = 9.0 + (conditions.solarFlux - 70) * 0.1
                estimated_muf = max(7.0, min(30.0, estimated_muf))  # Clamp to reasonable range
                
                return MUFData(
                    location=location,
                    muf3000km=estimated_muf,
                    foF2=estimated_muf / 3.0,  # Rough estimate
                    timestamp=datetime.utcnow(),
                    station="ESTIMATED",
                )
            else:
                return MUFData(
                    location=location,
                    muf3000km=14.5,  # Default
                    foF2=5.2,
                    timestamp=datetime.utcnow(),
                    station="DEFAULT",
                )
        except Exception as e:
            log_error("muf_fetch_error", error=str(e), location=location)
            return None
    
    async def get_solar_cycle_data(self, year: int) -> SolarCycleData:
        """Get solar cycle data for a specific year.
        
        Fetches actual data from NOAA if available, otherwise estimates.
        """
        try:
            # Try to get actual data from NOAA
            cycle_data = await self._fetch_noaa_json("solar_cycle")
            
            if cycle_data and isinstance(cycle_data, list):
                # Look for data matching the year
                for entry in cycle_data:
                    time_tag = entry.get("time_tag", "")
                    if str(year) in time_tag:
                        pred_flux = float(entry.get("predicted_solar_flux", 100))
                        pred_ssn = float(entry.get("predicted_sunspot_number", 50))
                        
                        # Determine cycle phase based on values
                        if pred_ssn < 20:
                            phase = "Solar minimum"
                        elif pred_ssn > 100:
                            phase = "Solar maximum"
                        elif year <= 2023:
                            phase = "Rising"
                        else:
                            phase = "Declining"
                        
                        # Determine expected propagation
                        if phase == "Solar maximum":
                            expected = "Excellent HF propagation. Upper bands (15m/12m/10m) open daily for worldwide DX."
                        elif phase == "Solar minimum":
                            expected = "Poor upper HF bands. Focus on 40m/20m for DX. 80m excellent at night."
                        elif phase == "Rising":
                            expected = "Improving conditions. 15m opening regularly, 10m during peaks."
                        elif phase == "Declining":
                            expected = "Degrading but still good. Enjoy upper bands while they last."
                        else:
                            expected = "Variable conditions."
                        
                        return SolarCycleData(
                            year=year,
                            predictedSunspotNumber=pred_ssn,
                            predictedSolarFlux=pred_flux,
                            cyclePhase=phase,
                            cycleNumber=25 if year >= 2019 else 24,
                            expectedPropagation=expected,
                        )
            
            # If no specific data found, fall back to estimation
            return self._estimate_solar_cycle_data(year)
            
        except Exception as e:
            log_error("solar_cycle_fetch_error", error=str(e))
            return self._estimate_solar_cycle_data(year)
    
    def _estimate_solar_cycle_data(self, year: int) -> SolarCycleData:
        """Estimate solar cycle data for a year when actual data isn't available."""
        # Determine cycle number
        if year < 2019:
            cycle_num = 24
        else:
            cycle_num = 25
        
        # Simplified cycle phase determination for Cycle 25
        if cycle_num == 25:
            if year <= 2020:
                phase = "Solar minimum"
                pred_flux = 70
                pred_ssn = 10
            elif year <= 2023:
                phase = "Rising"
                pred_flux = 100 + (year - 2021) * 15
                pred_ssn = 30 + (year - 2021) * 20
            elif year <= 2026:
                phase = "Solar maximum"
                pred_flux = 140
                pred_ssn = 100
            elif year <= 2030:
                phase = "Declining"
                pred_flux = 120 - (year - 2027) * 10
                pred_ssn = 80 - (year - 2027) * 15
            else:
                phase = "Solar minimum"
                pred_flux = 70
                pred_ssn = 10
        else:
            # Default for unknown cycles
            phase = "Unknown"
            pred_flux = 100
            pred_ssn = 50
        
        # Determine expected propagation
        if phase == "Solar maximum":
            expected = "Excellent HF propagation. Upper bands (15m/12m/10m) open daily for worldwide DX."
        elif phase == "Solar minimum":
            expected = "Poor upper HF bands. Focus on 40m/20m for DX. 80m excellent at night."
        elif phase == "Rising":
            expected = "Improving conditions. 15m opening regularly, 10m during peaks."
        elif phase == "Declining":
            expected = "Degrading but still good. Enjoy upper bands while they last."
        else:
            expected = "Variable conditions."
        
        return SolarCycleData(
            year=year,
            predictedSunspotNumber=pred_ssn,
            predictedSolarFlux=pred_flux,
            cyclePhase=phase,
            cycleNumber=cycle_num,
            expectedPropagation=expected,
        )
    
    async def fetch_aurora_data(self) -> Optional[AuroraData]:
        """Fetch current aurora visibility data from NOAA."""
        try:
            aurora_data = await self._fetch_noaa_json("aurora")
            
            if not aurora_data:
                return None
            
            # Parse the OVATION aurora model output
            observation_time = aurora_data.get("Observation Time", "")
            forecast_time = aurora_data.get("Forecast Time", "")
            
            # Convert times
            try:
                obs_dt = datetime.fromisoformat(observation_time.replace("Z", ""))
            except:
                obs_dt = datetime.utcnow()
            
            try:
                fore_dt = datetime.fromisoformat(forecast_time.replace("Z", ""))
            except:
                fore_dt = datetime.utcnow()
            
            # Get hemisphere data
            hemisphere_data = {
                "north": aurora_data.get("coordinates", []),
                "south": aurora_data.get("coordinates_south", [])
            }
            
            # Estimate visibility based on data
            # The view line is typically around 50-60 degrees latitude during storms
            max_kp = 0
            visibility = "Not Visible"
            best_viewing = None
            view_line = []
            
            # Try to extract view line from coordinates
            if "coordinates" in aurora_data:
                coords = aurora_data["coordinates"]
                if isinstance(coords, list) and len(coords) > 0:
                    # Extract latitudes to find southernmost extent
                    lats = [c[1] for c in coords if isinstance(c, list) and len(c) >= 2]
                    if lats:
                        min_lat = min(lats)
                        view_line = [min_lat]
                        
                        # Estimate visibility based on latitude
                        if min_lat <= 65:
                            visibility = "Low"
                            best_viewing = "Alaska, Northern Canada, Scandinavia"
                        if min_lat <= 55:
                            visibility = "Moderate"
                            best_viewing = "Northern US states, Scotland, Northern Europe"
                        if min_lat <= 45:
                            visibility = "High"
                            best_viewing = "Mid-latitude US, Central Europe"
                        
                        # Estimate Kp from latitude
                        max_kp = max(0, min(9, (70 - min_lat) / 5))
            
            return AuroraData(
                observationTime=obs_dt,
                forecastTime=fore_dt,
                hemisphereData=hemisphere_data,
                viewLine=view_line,
                maxKp=max_kp,
                visibility=visibility,
                bestViewing=best_viewing,
            )
            
        except Exception as e:
            log_error("aurora_fetch_error", error=str(e))
            return None
    
    async def fetch_solar_regions(self) -> List[SolarRegion]:
        """Fetch active solar region data from NOAA."""
        try:
            regions_data = await self._fetch_noaa_json("solar_regions")
            
            if not regions_data or not isinstance(regions_data, list):
                return []
            
            regions = []
            for entry in regions_data:
                try:
                    # Parse flare probabilities if available
                    flare_probs = None
                    if "Prob_C" in entry or "Prob_M" in entry or "Prob_X" in entry:
                        flare_probs = {
                            "C": float(entry.get("Prob_C", 0)),
                            "M": float(entry.get("Prob_M", 0)),
                            "X": float(entry.get("Prob_X", 0)),
                        }
                    
                    region = SolarRegion(
                        region=int(entry.get("Region", 0)),
                        location=entry.get("Location"),
                        area=int(entry.get("Area", 0)) if entry.get("Area") else None,
                        spotClass=entry.get("Spot_Class"),
                        magneticClass=entry.get("Mag_Type"),
                        numberOfSpots=int(entry.get("Number_Spots", 0)) if entry.get("Number_Spots") else None,
                        flareActivity=entry.get("Latest_Flare"),
                        flareProbability=flare_probs,
                    )
                    regions.append(region)
                except Exception as e:
                    log_warning("solar_region_parse_error", error=str(e), entry=entry)
                    continue
            
            return regions
            
        except Exception as e:
            log_error("solar_regions_fetch_error", error=str(e))
            return []
    
    async def fetch_solar_events(self, days: int = 3) -> List[SolarEvent]:
        """Fetch recent solar events (flares, CMEs) from NOAA."""
        try:
            events_data = await self._fetch_noaa_json("solar_events")
            
            if not events_data or not isinstance(events_data, list):
                return []
            
            events = []
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            for entry in events_data:
                try:
                    # Parse event time
                    begin_time = entry.get("beginTime", "")
                    if begin_time:
                        try:
                            start_dt = datetime.fromisoformat(begin_time.replace("Z", ""))
                        except:
                            continue
                        
                        # Skip old events
                        if start_dt < cutoff_date:
                            continue
                    else:
                        continue
                    
                    # Parse peak and end times
                    peak_dt = None
                    end_dt = None
                    if entry.get("peakTime"):
                        try:
                            peak_dt = datetime.fromisoformat(entry["peakTime"].replace("Z", ""))
                        except:
                            pass
                    
                    if entry.get("endTime"):
                        try:
                            end_dt = datetime.fromisoformat(entry["endTime"].replace("Z", ""))
                        except:
                            pass
                    
                    # Determine event type
                    event_type = entry.get("eventType", "Unknown")
                    if "flare" in entry.get("classType", "").lower():
                        event_type = "Flare"
                    elif "cme" in event_type.lower():
                        event_type = "CME"
                    elif "proton" in event_type.lower():
                        event_type = "Proton Event"
                    
                    event = SolarEvent(
                        eventId=entry.get("flrID", f"event_{start_dt.timestamp()}"),
                        eventType=event_type,
                        startTime=start_dt,
                        peakTime=peak_dt,
                        endTime=end_dt,
                        classType=entry.get("classType"),
                        sourceRegion=int(entry.get("activeRegionNum", 0)) if entry.get("activeRegionNum") else None,
                        intensity=float(entry.get("intensity", 0)) if entry.get("intensity") else None,
                        location=entry.get("sourceLocation"),
                        earthDirected=entry.get("linkedEvents") is not None,  # Simplified
                        notes=entry.get("note"),
                    )
                    events.append(event)
                    
                except Exception as e:
                    log_warning("solar_event_parse_error", error=str(e), entry=entry)
                    continue
            
            # Sort by start time, most recent first
            events.sort(key=lambda x: x.startTime, reverse=True)
            return events
            
        except Exception as e:
            log_error("solar_events_fetch_error", error=str(e))
            return []
    
    async def fetch_space_weather_summary(self) -> Optional[SpaceWeatherSummary]:
        """Fetch comprehensive space weather summary combining multiple sources."""
        try:
            # Fetch multiple data sources in parallel
            conditions = await self.fetch_current_conditions()
            regions = await self.fetch_solar_regions()
            events = await self.fetch_solar_events(days=1)
            aurora = await self.fetch_aurora_data()
            
            # Fetch additional GOES data
            xray_data = await self._fetch_noaa_json("goes_xray")
            proton_data = await self._fetch_noaa_json("goes_proton")
            electron_data = await self._fetch_noaa_json("goes_electron")
            
            # Determine solar activity level
            solar_activity = "Very Low"
            if conditions:
                if conditions.solarFlux >= 150:
                    solar_activity = "High"
                elif conditions.solarFlux >= 120:
                    solar_activity = "Moderate"
                elif conditions.solarFlux >= 90:
                    solar_activity = "Low"
            
            # Determine geomagnetic activity
            geo_activity = "Quiet"
            if conditions:
                if conditions.kIndex >= 7:
                    geo_activity = "Severe Storm"
                elif conditions.kIndex >= 6:
                    geo_activity = "Strong Storm"
                elif conditions.kIndex >= 5:
                    geo_activity = "Minor Storm"
                elif conditions.kIndex >= 4:
                    geo_activity = "Active"
            
            # Count flares by class in last 24h
            flare_counts = {"C": 0, "M": 0, "X": 0}
            earth_directed_cmes = 0
            for event in events:
                if event.eventType == "Flare" and event.classType:
                    class_letter = event.classType[0].upper()
                    if class_letter in flare_counts:
                        flare_counts[class_letter] += 1
                elif event.eventType == "CME" and event.earthDirected:
                    earth_directed_cmes += 1
            
            # Parse GOES data for latest values
            proton_flux = None
            electron_flux = None
            xray_flux = None
            
            if proton_data and isinstance(proton_data, list) and len(proton_data) > 0:
                latest = proton_data[-1]
                proton_flux = float(latest.get("flux", 0))
            
            if electron_data and isinstance(electron_data, list) and len(electron_data) > 0:
                latest = electron_data[-1]
                electron_flux = float(latest.get("flux", 0))
            
            if xray_data and isinstance(xray_data, list) and len(xray_data) > 0:
                latest = xray_data[-1]
                xray_flux = {
                    "short": float(latest.get("flux_short", 0)) if latest.get("flux_short") else None,
                    "long": float(latest.get("flux_long", 0)) if latest.get("flux_long") else None,
                }
            
            # Determine space weather scales
            # R-scale (Radio blackouts) based on X-ray flux
            radio_blackout = "R0"
            if xray_flux and xray_flux.get("long"):
                if xray_flux["long"] >= 1e-3:
                    radio_blackout = "R5"
                elif xray_flux["long"] >= 5e-4:
                    radio_blackout = "R4"
                elif xray_flux["long"] >= 1e-4:
                    radio_blackout = "R3"
                elif xray_flux["long"] >= 5e-5:
                    radio_blackout = "R2"
                elif xray_flux["long"] >= 1e-5:
                    radio_blackout = "R1"
            
            # S-scale (Solar radiation storms) based on proton flux
            solar_radiation = "S0"
            if proton_flux:
                if proton_flux >= 1e5:
                    solar_radiation = "S5"
                elif proton_flux >= 1e4:
                    solar_radiation = "S4"
                elif proton_flux >= 1e3:
                    solar_radiation = "S3"
                elif proton_flux >= 1e2:
                    solar_radiation = "S2"
                elif proton_flux >= 10:
                    solar_radiation = "S1"
            
            # G-scale (Geomagnetic storms) based on K-index
            geomagnetic_storm = "G0"
            if conditions:
                if conditions.kIndex >= 9:
                    geomagnetic_storm = "G5"
                elif conditions.kIndex >= 8:
                    geomagnetic_storm = "G4"
                elif conditions.kIndex >= 7:
                    geomagnetic_storm = "G3"
                elif conditions.kIndex >= 6:
                    geomagnetic_storm = "G2"
                elif conditions.kIndex >= 5:
                    geomagnetic_storm = "G1"
            
            # Aurora activity
            aurora_activity = "Not Active"
            if aurora:
                aurora_activity = aurora.visibility
            
            return SpaceWeatherSummary(
                solarActivity=solar_activity,
                geomagneticActivity=geo_activity,
                radioBlackout=radio_blackout,
                solarRadiation=solar_radiation,
                geomagneticStorm=geomagnetic_storm,
                protonFlux=proton_flux,
                electronFlux=electron_flux,
                xrayFlux=xray_flux,
                activeRegions=len(regions),
                solarFlares24h=flare_counts,
                earthDirectedCMEs=earth_directed_cmes,
                auroraActivity=aurora_activity,
                timestamp=datetime.utcnow(),
            )
            
        except Exception as e:
            log_error("space_weather_summary_error", error=str(e))
            return None


# Singleton instance
_propagation_adapter = None


def get_propagation_adapter() -> PropagationAdapter:
    """Get the singleton propagation adapter instance."""
    global _propagation_adapter
    if _propagation_adapter is None:
        _propagation_adapter = PropagationAdapter()
    return _propagation_adapter