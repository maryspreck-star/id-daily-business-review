"""
HubSpot API revenue collector for the Sales Team tab.

Uses the exact same filter as the "MTD Sales by Team" HubSpot dashboard:
  - Deal stage: Closed Won (3 pipelines)
  - Meaningful Contact? = Yes
  - Deal owner is known
  - HubSpot team is known
  - Close Date: specified date range

Source: HubSpot Search API (not Snowflake) for exact match with live dashboard.
"""
import datetime
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://api.hubapi.com"

# Three Closed Won pipeline stage IDs matching HubSpot dashboard filter
_CLOSED_WON_STAGES = [
    "957899065",                                    # 2025 Sales Pipeline
    "264c3b2f-856c-4973-b659-95b5f775dc8b",        # Salesforce / Sales Pipeline
    "closedwon",                                    # Default pipeline
]

# Studio team ID → name (from HubSpot owners API)
_TEAM_NAMES = {
    "14075804": "New York",
    "14075800": "Minneapolis",
    "14075778": "Dallas",
    "14072444": "Denver",
    "14075806": "Seattle",
    "14075744": "Boston",
    "14072464": "Chicago",
    "14075777": "Charlotte",
    "14118313": "Washington DC",
    "14075781": "Los Angeles",
    "14075805": "San Francisco",
    "55992894": "Baltimore",
    "14118420": "Philadelphia",
    "15106179": "General Managers",  # excluded from totals
}

_STUDIO_TEAMS = {k for k, v in _TEAM_NAMES.items()
                 if v not in ("General Managers",)}


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['HUBSPOT_API_KEY']}",
            "Content-Type": "application/json"}


def _date_epoch_ms(d: datetime.date) -> int:
    """Convert date to milliseconds since epoch (midnight UTC)."""
    return int(datetime.datetime(d.year, d.month, d.day,
                                 tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _search_deals(start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    """Fetch all deals matching the dashboard filter for the given close date range."""
    start_ms = _date_epoch_ms(start_date)
    # end is exclusive: add 1 day to make it inclusive through end_date
    end_ms = _date_epoch_ms(end_date + datetime.timedelta(days=1))

    body = {
        "filterGroups": [{
            "filters": [
                {"propertyName": "dealstage",
                 "operator": "IN",
                 "values": _CLOSED_WON_STAGES},
                {"propertyName": "meaningful_contact_",
                 "operator": "EQ",
                 "value": "true"},
                {"propertyName": "hubspot_owner_id",
                 "operator": "HAS_PROPERTY"},
                {"propertyName": "hs_all_team_ids",
                 "operator": "HAS_PROPERTY"},
                {"propertyName": "closedate",
                 "operator": "BETWEEN",
                 "value": str(start_ms),
                 "highValue": str(end_ms)},
            ]
        }],
        "properties": ["amount", "hubspot_owner_id", "hs_all_team_ids",
                        "closedate", "hs_owning_teams"],
        "limit": 100,
    }

    deals = []
    after = None
    while True:
        if after:
            body["after"] = after
        r = requests.post(f"{_BASE}/crm/v3/objects/deals/search",
                          headers=_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        deals.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {}).get("after")
        if not paging:
            break
        after = paging
        time.sleep(0.15)  # stay under rate limit

    return deals


def _get_owner_teams() -> dict[str, str]:
    """Return {owner_id: primary_studio_team_id} for all active studio reps."""
    r = requests.get(f"{_BASE}/crm/v3/owners?limit=100&includeInactive=true",
                     headers=_headers(), timeout=15)
    r.raise_for_status()
    owner_team = {}
    for o in r.json().get("results", []):
        primary = next((t for t in o.get("teams", [])
                        if t.get("primary") and str(t["id"]) in _STUDIO_TEAMS), None)
        if primary:
            owner_team[str(o["id"])] = str(primary["id"])
    return owner_team


def _aggregate(deals: list[dict], owner_team: dict[str, str]) -> dict:
    """Aggregate deal amounts by studio team and by owner."""
    by_team: dict[str, float] = {}
    by_owner: dict[str, dict] = {}

    for deal in deals:
        props = deal.get("properties", {})
        try:
            amount = float(props.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount == 0:
            continue

        owner_id = props.get("hubspot_owner_id", "")
        team_id = owner_team.get(str(owner_id), "")
        if not team_id or team_id not in _STUDIO_TEAMS:
            continue

        studio = _TEAM_NAMES.get(team_id, team_id)
        by_team[studio] = by_team.get(studio, 0.0) + amount
        if owner_id not in by_owner:
            by_owner[owner_id] = {"owner_id": owner_id, "studio": studio, "amount": 0.0}
        by_owner[owner_id]["amount"] += amount

    by_team_list = sorted(by_team.items(), key=lambda x: -x[1])
    by_owner_list = sorted(by_owner.values(), key=lambda x: -x["amount"])
    total = sum(by_team.values())

    return {
        "total": total,
        "by_team":  [{"studio": s, "amount": a} for s, a in by_team_list],
        "by_owner": by_owner_list,
    }


def fetch_revenue(
    yesterday: datetime.date,
    month_start: datetime.date,
) -> dict:
    """Fetch HubSpot revenue matching the MTD Sales by Team dashboard filter.

    Returns yesterday, last_week (= MTD for first week), and mtd revenue
    broken down by studio team and owner, plus LY comparisons.
    """
    owner_team = _get_owner_teams()

    today = yesterday + datetime.timedelta(days=1)
    ly_yesterday = yesterday - datetime.timedelta(days=365)
    ly_month_start = month_start.replace(year=month_start.year - 1)

    yd_deals   = _search_deals(yesterday, yesterday)
    mtd_deals  = _search_deals(month_start, yesterday)
    yd_ly_deals  = _search_deals(ly_yesterday, ly_yesterday)
    mtd_ly_deals = _search_deals(ly_month_start,
                                  yesterday.replace(year=yesterday.year - 1))

    yd  = _aggregate(yd_deals,   owner_team)
    mtd = _aggregate(mtd_deals,  owner_team)
    yd_ly  = _aggregate(yd_ly_deals,  owner_team)
    mtd_ly = _aggregate(mtd_ly_deals, owner_team)

    return {
        "yesterday": {**yd,  "ly_total": yd_ly["total"]},
        "mtd":       {**mtd, "ly_total": mtd_ly["total"]},
        # last_week alias — same as MTD when in first week of month
        "last_week": {**mtd, "ly_total": mtd_ly["total"]},
    }
