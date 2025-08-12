import os
import httpx
from typing import Optional, Any
from hamops.schemas import CallsignRecord



def _to_float(x: Any):
    try:
        return float(x)
    except Exception:
        return None

async def lookup_callsign(callsign: str) -> Optional[CallsignRecord]:
    """
    Minimal, forgiving HamDB lookup.
    Returns None on any error or when the callsign isn't found.
    """
    url = f"http://api.hamdb.org/{callsign.upper()}/json"
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
            r = await client.get(url)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    try:
        data = r.json()
    except Exception:
        return None

    hamdb = data.get("hamdb")
    if not isinstance(hamdb, dict):
        return None

    # Prefer presence of a callsign object over message parsing.
    cs = hamdb.get("callsign")
    if isinstance(cs, dict) and cs:
        return CallsignRecord(
            callsign=cs.get("call", callsign.upper()),
            name=cs.get("name") or cs.get("fname"),
            license_class=cs.get("class"),
            status=cs.get("status"),
            country=cs.get("country"),
            grid=cs.get("grid") or cs.get("gridsquare"),
            lat=_to_float(cs.get("lat")),
            lon=_to_float(cs.get("lon")),
            expires=cs.get("expires"),
            first_issued=cs.get("first"),
            trustee=cs.get("trustee"),
        )

    # If there is no callsign object, optionally check messages for NOT_FOUND—but safely.
    msgs = hamdb.get("messages", [])
    def _msg_text(m):
        if isinstance(m, dict):
            return (m.get("status") or m.get("message") or "").upper()
        return str(m).upper()

    if any(("NOT_FOUND" in _msg_text(m) or "NOT FOUND" in _msg_text(m)) for m in msgs):
        return None

    # Unknown shape → treat as not found.
    return None
