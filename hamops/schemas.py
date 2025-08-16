from pydantic import BaseModel, Field
from typing import  Optional


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
