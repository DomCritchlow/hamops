from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Union


class CenterLatLon(BaseModel):
    lat: float
    lon: float

class CenterPlace(BaseModel):
    place: str

class CenterMaidenhead(BaseModel):
    maidenhead: str

Center = Union[CenterLatLon, CenterPlace, CenterMaidenhead]

class AprsActiveQuery(BaseModel):
    center: Center
    radius_km: float = Field(gt=0, le=500)
    since_minutes: int = Field(gt=0, le=1440)

class AprsStation(BaseModel):
    callsign: str
    last_heard_utc: str
    lat: float
    lon: float
    symbol: Optional[str] = None
    heard_via: Optional[List[str]] = None
    comment: Optional[str] = None
    speed_kmh: Optional[float] = None
    course_deg: Optional[float] = None
    source: Literal["APRS-IS","aprs.fi"] = "aprs.fi"

class AprsTrackPoint(BaseModel):
    t: str
    lat: float
    lon: float
    speed_kmh: Optional[float] = None
    course_deg: Optional[float] = None

class AprsTrack(BaseModel):
    callsign: str
    points: List[AprsTrackPoint]
    source: Literal["APRS-IS","aprs.fi"] = "aprs.fi"




class CallsignRecord(BaseModel):
    callsign: str
    name: Optional[str] = None
    license_class: Optional[str] = None
    status: Optional[str] = None
    country: Optional[str] = None
    grid: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    expires: Optional[str] = None
    first_issued: Optional[str] = None
    trustee: Optional[str] = None
