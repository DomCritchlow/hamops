# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from pydantic import BaseModel
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class CallsignRecord(BaseModel):
    """Normalized callsign data returned from the HamDB service."""

    callsign: str
    name: Optional[str] = None
    license_class: Optional[str] = None
    status: Optional[str] = None
    country: Optional[str] = None
    grid: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    expires: Optional[str] = None
