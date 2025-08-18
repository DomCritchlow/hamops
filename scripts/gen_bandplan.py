#!/usr/bin/env python3
"""Script to fetch and process US band plan data from SDR-Band-Plans repo.

This script fetches the US Amateur Radio band plan XML from the GitHub repo
and converts it to a structured JSON format for efficient querying.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any

import httpx


def parse_frequency(freq_str: str) -> int:
    """Convert frequency string to Hz.
    
    Handles formats like:
    - "14000000" (Hz)
    - "14.000" (MHz)
    - "14000" (kHz)
    """
    freq_str = freq_str.strip()
    
    # Remove commas if present
    freq_str = freq_str.replace(",", "")
    
    # Check if it has a decimal point (likely MHz)
    if "." in freq_str:
        return int(float(freq_str) * 1_000_000)
    
    # If it's a large number (> 100000), assume Hz
    freq_val = int(freq_str)
    if freq_val > 100_000:
        return freq_val
    
    # Otherwise assume kHz
    return freq_val * 1000


def fetch_bandplan_xml() -> str:
    """Fetch the US Amateur Radio band plan XML from GitHub."""
    # The file is located at US/SDR#/BandPlan.xml
    # The # character needs to be URL encoded as %23
    url = "https://raw.githubusercontent.com/Arrin-KN1E/SDR-Band-Plans/master/US/SDR%23/BandPlan.xml"
    
    print(f"Fetching band plan from: {url}")
    
    with httpx.Client() as client:
        response = client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


def parse_bandplan_xml(xml_content: str) -> List[Dict[str, Any]]:
    """Parse the SDR# band plan XML format."""
    root = ET.fromstring(xml_content)
    
    bands = []
    
    # SDR# format has RangeEntry elements
    for entry in root.findall(".//RangeEntry"):
        # Extract attributes
        minfreq = entry.get("minFrequency")
        maxfreq = entry.get("maxFrequency")
        
        if not minfreq or not maxfreq:
            continue
            
        band = {
            "minFrequency": parse_frequency(minfreq),
            "maxFrequency": parse_frequency(maxfreq),
            "minFrequencyDisplay": minfreq,
            "maxFrequencyDisplay": maxfreq,
        }
        
        # Add optional attributes if present
        if entry.get("mode"):
            band["mode"] = entry.get("mode")
        
        if entry.get("step"):
            band["step"] = int(entry.get("step"))
            
        if entry.get("color"):
            band["color"] = entry.get("color")
            
        # The text content often contains the band description
        if entry.text and entry.text.strip():
            band["description"] = entry.text.strip()
        
        # Some entries have additional info in attributes
        for attr in ["name", "comment", "info"]:
            if entry.get(attr):
                band[attr] = entry.get(attr)
        
        bands.append(band)
    
    # Sort by minimum frequency
    bands.sort(key=lambda x: x["minFrequency"])
    
    return bands


def enrich_band_data(bands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add additional metadata to band entries based on frequency ranges.
    
    This adds standard amateur radio band names, license classes, and typical uses.
    """
    
    # Define amateur radio bands with their typical ranges (in Hz)
    amateur_bands = {
        "2200m": (135_700, 137_800),
        "630m": (472_000, 479_000),
        "160m": (1_800_000, 2_000_000),
        "80m": (3_500_000, 4_000_000),
        "60m": (5_330_500, 5_406_400),
        "40m": (7_000_000, 7_300_000),
        "30m": (10_100_000, 10_150_000),
        "20m": (14_000_000, 14_350_000),
        "17m": (18_068_000, 18_168_000),
        "15m": (21_000_000, 21_450_000),
        "12m": (24_890_000, 24_990_000),
        "10m": (28_000_000, 29_700_000),
        "6m": (50_000_000, 54_000_000),
        "2m": (144_000_000, 148_000_000),
        "1.25m": (219_000_000, 225_000_000),
        "70cm": (420_000_000, 450_000_000),
        "33cm": (902_000_000, 928_000_000),
        "23cm": (1_240_000_000, 1_300_000_000),
        "13cm": (2_300_000_000, 2_450_000_000),
    }
    
    # License class privileges (simplified - actual rules are more complex)
    license_privileges = {
        "CW": ["Extra", "Advanced", "General", "Technician"],
        "Phone": ["Extra", "Advanced", "General", "Technician"],
        "Digital": ["Extra", "Advanced", "General", "Technician"],
        "Data": ["Extra", "Advanced", "General", "Technician"],
    }
    
    for band in bands:
        min_freq = band["minFrequency"]
        max_freq = band["maxFrequency"]
        center_freq = (min_freq + max_freq) / 2
        
        # Determine which amateur band this belongs to
        for band_name, (band_min, band_max) in amateur_bands.items():
            if band_min <= center_freq <= band_max:
                band["bandName"] = band_name
                break
        
        # Add frequency display in MHz for readability
        band["minFrequencyMHz"] = round(min_freq / 1_000_000, 6)
        band["maxFrequencyMHz"] = round(max_freq / 1_000_000, 6)
        
        # Determine license class based on frequency and mode
        # This is simplified - actual rules depend on specific frequency segments
        if "description" in band:
            desc_lower = band["description"].lower()
            
            # Extra class segments typically mentioned explicitly
            if "extra" in desc_lower:
                band["licenseClass"] = ["Extra"]
            elif "advanced" in desc_lower:
                band["licenseClass"] = ["Extra", "Advanced"]
            elif "general" in desc_lower:
                band["licenseClass"] = ["Extra", "Advanced", "General"]
            elif "technician" in desc_lower or center_freq > 50_000_000:
                # VHF/UHF typically available to all
                band["licenseClass"] = ["Extra", "Advanced", "General", "Technician"]
            elif "novice" in desc_lower:
                band["licenseClass"] = ["Extra", "Advanced", "General", "Technician", "Novice"]
            
            # Identify common uses
            uses = []
            if "cw" in desc_lower or "morse" in desc_lower:
                uses.append("CW")
            if "phone" in desc_lower or "ssb" in desc_lower or "voice" in desc_lower:
                uses.append("Phone")
            if "digital" in desc_lower or "rtty" in desc_lower or "psk" in desc_lower:
                uses.append("Digital")
            if "data" in desc_lower or "packet" in desc_lower:
                uses.append("Data")
            if "fm" in desc_lower or "repeater" in desc_lower:
                uses.append("FM")
            if "eme" in desc_lower or "moonbounce" in desc_lower:
                uses.append("EME")
            if "satellite" in desc_lower:
                uses.append("Satellite")
            if "beacon" in desc_lower:
                uses.append("Beacon")
            if "emergency" in desc_lower or "ares" in desc_lower:
                uses.append("Emergency")
            
            if uses:
                band["typicalUses"] = uses
    
    return bands


def generate_index(bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate indices for efficient querying."""
    
    # Create a frequency lookup table for binary search
    freq_index = []
    for i, band in enumerate(bands):
        freq_index.append({
            "min": band["minFrequency"],
            "max": band["maxFrequency"],
            "index": i
        })
    
    # Create mode index
    mode_index = {}
    for i, band in enumerate(bands):
        if "mode" in band:
            mode = band["mode"]
            if mode not in mode_index:
                mode_index[mode] = []
            mode_index[mode].append(i)
    
    # Create band name index
    band_name_index = {}
    for i, band in enumerate(bands):
        if "bandName" in band:
            name = band["bandName"]
            if name not in band_name_index:
                band_name_index[name] = []
            band_name_index[name].append(i)
    
    # Create typical use index
    use_index = {}
    for i, band in enumerate(bands):
        if "typicalUses" in band:
            for use in band["typicalUses"]:
                if use not in use_index:
                    use_index[use] = []
                use_index[use].append(i)
    
    return {
        "frequencyIndex": freq_index,
        "modeIndex": mode_index,
        "bandNameIndex": band_name_index,
        "useIndex": use_index
    }


def main():
    """Main script execution."""
    # Create data directory if it doesn't exist
    data_dir = Path("hamops/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = data_dir / "us_bandplan.json"
    
    try:
        # Fetch the XML
        print("Fetching US Amateur Radio band plan...")
        xml_content = fetch_bandplan_xml()
        
        # Parse the XML
        print("Parsing band plan XML...")
        bands = parse_bandplan_xml(xml_content)
        print(f"Found {len(bands)} band entries")
        
        # Enrich with additional metadata
        print("Enriching band data...")
        bands = enrich_band_data(bands)
        
        # Generate indices
        print("Generating search indices...")
        indices = generate_index(bands)
        
        # Combine into final structure
        bandplan_data = {
            "version": "1.0",
            "source": "https://github.com/Arrin-KN1E/SDR-Band-Plans",
            "country": "United States",
            "bands": bands,
            "indices": indices
        }
        
        # Write to JSON file
        print(f"Writing to {output_file}...")
        with open(output_file, "w") as f:
            json.dump(bandplan_data, f, indent=2)
        
        print(f"✓ Successfully generated band plan with {len(bands)} entries")
        
        # Print some statistics
        band_names = set(b.get("bandName") for b in bands if "bandName" in b)
        modes = set(b.get("mode") for b in bands if "mode" in b)
        
        print(f"  Amateur bands covered: {', '.join(sorted(band_names))}")
        print(f"  Modes found: {', '.join(sorted(modes))}")
        
    except Exception as e:
        print(f"✗ Error generating band plan: {e}")
        raise


if __name__ == "__main__":
    main()
