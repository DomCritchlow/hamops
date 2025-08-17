"""
Band Plan Data Ingestion Script
Parses and imports band plan data from various sources
"""

import json
import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import logging
from pathlib import Path

# For PDF parsing (install: pip install pypdf2 tabula-py)
import PyPDF2
import tabula

# For web scraping (install: pip install beautifulsoup4 requests)
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BandPlanParser:
    """Base class for parsing band plan documents"""
    
    def __init__(self):
        self.bands = {}
        self.frequency_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(?:MHz|kHz)?')
        
    def parse_frequency(self, freq_str: str) -> Optional[float]:
        """Convert frequency string to MHz"""
        match = self.frequency_pattern.search(freq_str)
        if match:
            freq = float(match.group(1))
            if 'kHz' in freq_str.lower():
                freq = freq / 1000
            return freq
        return None
    
    def parse_frequency_range(self, range_str: str) -> Tuple[Optional[float], Optional[float]]:
        """Parse a frequency range like '3.500-3.600 MHz'"""
        parts = range_str.replace('–', '-').split('-')
        if len(parts) == 2:
            start = self.parse_frequency(parts[0])
            end = self.parse_frequency(parts[1])
            # Handle abbreviated end frequency (e.g., "14.150-350")
            if end and end < start:
                # Assume same magnitude
                magnitude = 10 ** (len(str(int(start))))
                if end < magnitude:
                    end = int(start) + (end - int(start) % magnitude)
            return start, end
        return None, None


class FCCBandPlanParser(BandPlanParser):
    """Parser for FCC Part 97 regulations"""
    
    # Simplified US Amateur Radio bands (Part 97.301)
    US_BANDS = {
        "160m": (1.800, 2.000),
        "80m": (3.500, 4.000),
        "60m": [(5.332, 5.333), (5.348, 5.349), (5.358, 5.359), (5.373, 5.374), (5.405, 5.406)],
        "40m": (7.000, 7.300),
        "30m": (10.100, 10.150),
        "20m": (14.000, 14.350),
        "17m": (18.068, 18.168),
        "15m": (21.000, 21.450),
        "12m": (24.890, 24.990),
        "10m": (28.000, 29.700),
        "6m": (50.000, 54.000),
        "2m": (144.000, 148.000),
        "1.25m": (222.000, 225.000),
        "70cm": (420.000, 450.000),
        "33cm": (902.000, 928.000),
        "23cm": (1240.000, 1300.000),
    }
    
    # Simplified privileges by license class (Part 97.301, 97.303, 97.305)
    PRIVILEGES = {
        "160m": {
            "extra": [(1.800, 2.000, ["CW", "Phone", "Digital"])],
            "general": [(1.800, 2.000, ["CW", "Phone", "Digital"])],
            "technician": []
        },
        "80m": {
            "extra": [(3.500, 4.000, ["CW", "Digital", "Phone"])],
            "general": [
                (3.525, 3.600, ["CW", "Digital"]),
                (3.800, 4.000, ["CW", "Phone", "Digital"])
            ],
            "technician": [(3.525, 3.600, ["CW"])]
        },
        "40m": {
            "extra": [(7.000, 7.300, ["CW", "Digital", "Phone"])],
            "general": [
                (7.025, 7.125, ["CW", "Digital"]),
                (7.175, 7.300, ["CW", "Phone", "Digital"])
            ],
            "technician": [(7.025, 7.125, ["CW"])]
        },
        "20m": {
            "extra": [(14.000, 14.350, ["CW", "Digital", "Phone"])],
            "general": [
                (14.025, 14.150, ["CW", "Digital"]),
                (14.225, 14.350, ["CW", "Phone", "Digital"])
            ],
            "technician": [(14.025, 14.070, ["CW", "Digital"])]
        },
        "15m": {
            "extra": [(21.000, 21.450, ["CW", "Digital", "Phone"])],
            "general": [
                (21.025, 21.200, ["CW", "Digital"]),
                (21.275, 21.450, ["CW", "Phone", "Digital"])
            ],
            "technician": [(21.025, 21.200, ["CW", "Digital"])]
        },
        "10m": {
            "extra": [(28.000, 29.700, ["CW", "Digital", "Phone"])],
            "general": [(28.000, 29.700, ["CW", "Digital", "Phone"])],
            "technician": [
                (28.000, 28.300, ["CW", "Digital"]),
                (28.300, 28.500, ["CW", "Phone", "Digital"])
            ]
        },
        "6m": {
            "extra": [(50.000, 54.000, ["CW", "Digital", "Phone"])],
            "general": [(50.000, 54.000, ["CW", "Digital", "Phone"])],
            "technician": [(50.000, 54.000, ["CW", "Digital", "Phone"])]
        },
        "2m": {
            "extra": [(144.000, 148.000, ["CW", "Digital", "Phone"])],
            "general": [(144.000, 148.000, ["CW", "Digital", "Phone"])],
            "technician": [(144.000, 148.000, ["CW", "Digital", "Phone"])]
        },
        "70cm": {
            "extra": [(420.000, 450.000, ["CW", "Digital", "Phone"])],
            "general": [(420.000, 450.000, ["CW", "Digital", "Phone"])],
            "technician": [(420.000, 450.000, ["CW", "Digital", "Phone"])]
        }
    }
    
    def generate_fcc_band_plan(self) -> Dict:
        """Generate structured band plan from FCC regulations"""
        band_plan = {
            "jurisdiction": {
                "code": "US",
                "name": "United States",
                "regulatory_body": "FCC",
                "license_classes": ["technician", "general", "extra"]
            },
            "bands": [],
            "effective_date": "2024-05-01",
            "version": "Part 97 - 2024",
            "source_documents": ["FCC Part 97.301", "FCC Part 97.303", "FCC Part 97.305"]
        }
        
        for band_name, band_range in self.US_BANDS.items():
            if isinstance(band_range, list):
                # Handle 60m channels
                continue  # Skip for simplicity in this example
            
            start_freq, end_freq = band_range
            
            band_data = {
                "band_name": band_name,
                "start_freq_mhz": start_freq,
                "end_freq_mhz": end_freq,
                "segments": []
            }
            
            # Add segments based on privileges
            if band_name in self.PRIVILEGES:
                for license_class in ["extra", "general", "technician"]:
                    for seg_start, seg_end, modes in self.PRIVILEGES[band_name][license_class]:
                        segment = {
                            "start_freq_mhz": seg_start,
                            "end_freq_mhz": seg_end,
                            "license_class": license_class,
                            "permitted_modes": modes,
                            "source": "FCC Part 97"
                        }
                        band_data["segments"].append(segment)
            
            band_plan["bands"].append(band_data)
        
        return band_plan


class ARRLBandPlanParser(BandPlanParser):
    """Parser for ARRL band plan conventions"""
    
    def parse_arrl_web_page(self, url: str = "http://www.arrl.org/band-plan") -> Dict:
        """Scrape ARRL band plan from web"""
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # This is a simplified example - actual parsing would be more complex
            conventions = {
                "20m_conventions": [
                    {"freq_range": (14.070, 14.095), "use": "Digital modes"},
                    {"freq_range": (14.095, 14.150), "use": "CW/Digital DX window"},
                    {"freq_range": (14.230, 14.230), "use": "SSTV calling"},
                    {"freq_range": (14.286, 14.286), "use": "AM calling"}
                ],
                "40m_conventions": [
                    {"freq_range": (7.040, 7.040), "use": "RTTY DX"},
                    {"freq_range": (7.070, 7.125), "use": "Digital modes"},
                    {"freq_range": (7.171, 7.171), "use": "SSTV"},
                    {"freq_range": (7.290, 7.290), "use": "AM calling"}
                ]
            }
            
            return conventions
            
        except Exception as e:
            logger.error(f"Error parsing ARRL web page: {e}")
            return {}


class CanadianBandPlanParser(BandPlanParser):
    """Parser for Canadian (ISED) band plans"""
    
    def parse_rac_band_plan(self) -> Dict:
        """Parse Radio Amateurs of Canada band plan"""
        # Simplified Canadian band plan
        canadian_plan = {
            "jurisdiction": {
                "code": "CA",
                "name": "Canada",
                "regulatory_body": "ISED",
                "license_classes": ["basic", "basic_honours", "advanced"]
            },
            "bands": [
                {
                    "band_name": "80m",
                    "start_freq_mhz": 3.500,
                    "end_freq_mhz": 4.000,
                    "segments": [
                        {
                            "start_freq_mhz": 3.500,
                            "end_freq_mhz": 3.700,
                            "license_class": "advanced",
                            "permitted_modes": ["CW", "Digital"],
                            "source": "ISED"
                        },
                        {
                            "start_freq_mhz": 3.700,
                            "end_freq_mhz": 4.000,
                            "license_class": "advanced",
                            "permitted_modes": ["Phone", "Digital"],
                            "source": "ISED"
                        }
                    ]
                }
            ]
        }
        return canadian_plan


class BandPlanIngestionService:
    """Service to orchestrate band plan data ingestion"""
    
    def __init__(self, db_connection=None):
        self.db = db_connection
        self.fcc_parser = FCCBandPlanParser()
        self.arrl_parser = ARRLBandPlanParser()
        self.canadian_parser = CanadianBandPlanParser()
    
    def ingest_all_sources(self):
        """Ingest band plans from all configured sources"""
        results = {}
        
        # Parse FCC regulations
        logger.info("Parsing FCC band plan...")
        fcc_plan = self.fcc_parser.generate_fcc_band_plan()
        results['fcc'] = self.save_band_plan(fcc_plan, "US")
        
        # Parse ARRL conventions
        logger.info("Parsing ARRL conventions...")
        arrl_conventions = self.arrl_parser.parse_arrl_web_page()
        results['arrl'] = self.save_conventions(arrl_conventions, "US")
        
        # Parse Canadian regulations
        logger.info("Parsing Canadian band plan...")
        canadian_plan = self.canadian_parser.parse_rac_band_plan()
        results['canada'] = self.save_band_plan(canadian_plan, "CA")
        
        return results
    
    def save_band_plan(self, band_plan: Dict, jurisdiction_code: str) -> bool:
        """Save band plan to database"""
        try:
            # Save to JSON file as example (would be database in production)
            filename = f"band_plan_{jurisdiction_code}_{datetime.now().strftime('%Y%m%d')}.json"
            with open(filename, 'w') as f:
                json.dump(band_plan, f, indent=2)
            
            logger.info(f"Saved band plan to {filename}")
            
            # In production, this would insert into PostgreSQL
            # if self.db:
            #     self.db.execute(
            #         "INSERT INTO band_plans (jurisdiction, data, version, created_at) VALUES (?, ?, ?, ?)",
            #         (jurisdiction_code, json.dumps(band_plan), band_plan['version'], datetime.now())
            #     )
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving band plan: {e}")
            return False
    
    def save_conventions(self, conventions: Dict, jurisdiction_code: str) -> bool:
        """Save band conventions to database"""
        try:
            filename = f"conventions_{jurisdiction_code}_{datetime.now().strftime('%Y%m%d')}.json"
            with open(filename, 'w') as f:
                json.dump(conventions, f, indent=2)
            
            logger.info(f"Saved conventions to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving conventions: {e}")
            return False
    
    def validate_band_plan(self, band_plan: Dict) -> List[str]:
        """Validate band plan data for consistency"""
        errors = []
        
        for band in band_plan.get('bands', []):
            # Check frequency ranges
            if band['start_freq_mhz'] >= band['end_freq_mhz']:
                errors.append(f"Invalid frequency range for {band['band_name']}")
            
            # Check segments don't overlap inappropriately
            segments = band.get('segments', [])
            for i, seg1 in enumerate(segments):
                for seg2 in segments[i+1:]:
                    if seg1['license_class'] == seg2['license_class']:
                        if not (seg1['end_freq_mhz'] <= seg2['start_freq_mhz'] or 
                               seg2['end_freq_mhz'] <= seg1['start_freq_mhz']):
                            errors.append(f"Overlapping segments in {band['band_name']}")
        
        return errors
    
    def update_band_conditions(self):
        """Update current band conditions from external APIs"""
        # This would fetch from solar weather APIs, PSKReporter, etc.
        conditions = {
            "timestamp": datetime.now().isoformat(),
            "solar_flux": 120,
            "k_index": 2,
            "bands": {
                "20m": {"condition": "good", "muf": 28.5},
                "40m": {"condition": "fair", "noise": "S3"},
                "80m": {"condition": "poor", "noise": "S7"}
            }
        }
        
        # Save to cache/database
        with open('current_conditions.json', 'w') as f:
            json.dump(conditions, f, indent=2)
        
        return conditions


def main():
    """Main entry point for band plan ingestion"""
    service = BandPlanIngestionService()
    
    # Ingest all sources
    results = service.ingest_all_sources()
    
    # Validate the data
    fcc_plan = service.fcc_parser.generate_fcc_band_plan()
    errors = service.validate_band_plan(fcc_plan)
    if errors:
        logger.warning(f"Validation errors: {errors}")
    
    # Update current conditions
    conditions = service.update_band_conditions()
    
    logger.info("Band plan ingestion complete!")
    logger.info(f"Results: {results}")
    logger.info(f"Current conditions: Solar flux={conditions['solar_flux']}, K={conditions['k_index']}")


if __name__ == "__main__":
    main()