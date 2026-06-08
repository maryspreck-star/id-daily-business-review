import datetime
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://api.hubapi.com"
_STUDIO_TEAMS = {
    "New York", "Chicago", "Minneapolis", "Seattle", "Dallas",
    "Charlotte", "Los Angeles", "Washington DC", "Boston",
    "Denver", "Philadelphia", "San Francisco", "Baltimore",
}


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}", "Content-Type": "application/json"}


def _count(url: str, owner_id: str, month_start_ms: int) -> int:
    """Return total activity count for one owner for the current month."""
    r = requests.post(url, headers=_headers(), timeout=15, json={
        "filterGroups": [{"filters": [
            {"propertyName": "hs_createdate", "operator": "GTE", "value": str(month_start_ms)},
            {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
        ]}],
        "limit": 1,
    })
    r.raise_for_status()
    return r.json().get("total", 0)


def fetch_activities() -> dict:
    """MTD call and meeting counts per rep and per studio from HubSpot API."""
    today = datetime.date.today()
    month_start = datetime.datetime(today.year, today.month, 1, tzinfo=datetime.timezone.utc)
    month_start_ms = int(month_start.timestamp() * 1000)

    # Get all active reps assigned to a studio team
    resp = requests.get(
        f"{_BASE}/crm/v3/owners?limit=100&includeInactive=false",
        headers=_headers(), timeout=15,
    )
    resp.raise_for_status()

    owner_map = {}
    for o in resp.json().get("results", []):
        teams = o.get("teams", [])
        primary = next(
            (t for t in teams if t.get("primary") and t["name"] in _STUDIO_TEAMS), None
        )
        if primary:
            owner_map[o["id"]] = {
                "name":     f"{o.get('firstName', '')} {o.get('lastName', '')}".strip(),
                "studio":   primary["name"],
                "owner_id": o["id"],
            }

    call_url    = f"{_BASE}/crm/v3/objects/calls/search"
    meeting_url = f"{_BASE}/crm/v3/objects/meetings/search"

    per_rep = []
    for owner_id, info in owner_map.items():
        calls    = _count(call_url,    owner_id, month_start_ms)
        time.sleep(0.12)  # stay well under 100 req/10s limit
        meetings = _count(meeting_url, owner_id, month_start_ms)
        time.sleep(0.12)
        per_rep.append({
            "name":     info["name"],
            "studio":   info["studio"],
            "calls":    calls,
            "meetings": meetings,
        })

    per_rep.sort(key=lambda r: r["calls"], reverse=True)

    # Roll up per studio
    studio_totals: dict[str, dict] = {}
    for rep in per_rep:
        s = rep["studio"]
        if s not in studio_totals:
            studio_totals[s] = {"studio": s, "reps": 0, "calls": 0, "meetings": 0}
        studio_totals[s]["reps"]     += 1
        studio_totals[s]["calls"]    += rep["calls"]
        studio_totals[s]["meetings"] += rep["meetings"]

    per_studio = sorted(studio_totals.values(), key=lambda x: x["calls"], reverse=True)

    # Add per-rep averages to studio rows
    for row in per_studio:
        row["calls_per_rep"]    = round(row["calls"]    / row["reps"], 1) if row["reps"] else 0
        row["meetings_per_rep"] = round(row["meetings"] / row["reps"], 1) if row["reps"] else 0

    return {
        "per_rep":    per_rep,
        "per_studio": per_studio,
        "month":      today.strftime("%B %Y"),
    }
