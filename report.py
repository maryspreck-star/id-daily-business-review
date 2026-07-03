#!/usr/bin/env python3
"""
Interior Define Daily Business Review
Runs every weekday at 8am CT via GitHub Actions.
Data: Looker (interior_define model) for Total Business tab +
      HubSpot Private App for Sales tab.
Forecast: Google Sheet CSV export (must be "Anyone with link can view").
Delivery: HTML → GitHub Pages; Slack link → #salesoperations.
"""

import os, sys, datetime, csv, io, base64, json, subprocess, zoneinfo, html, re, time
import requests
from datetime import timezone

_CT = zoneinfo.ZoneInfo("America/Chicago")

# ── Config ────────────────────────────────────────────────────────────────────

LOOKER_URL    = os.environ["LOOKER_BASE_URL"]
LOOKER_ID     = os.environ["LOOKER_CLIENT_ID"]
LOOKER_SECRET = os.environ["LOOKER_CLIENT_SECRET"]
SLACK_WEBHOOK    = os.environ["SLACK_WEBHOOK_URL"]
SLACK_READ_TOKEN = os.environ.get("SLACK_READ_TOKEN", "")
GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
ID_HS_TOKEN      = os.environ.get("ID_HUBSPOT_TOKEN", "")
# "schedule" = automated 8am run; "workflow_dispatch" = manual trigger
TRIGGERED_BY     = os.environ.get("TRIGGERED_BY", "workflow_dispatch")
GITHUB_REPO   = "maryspreck-star/id-daily-business-review"
PAGE_URL      = "https://maryspreck-star.github.io/id-daily-business-review/"

FORECAST_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0"
    "/export?format=csv&gid=910871961"  # tab: "for claude_add each month"
)

STUDIO_EXCLUDE = {"Assisted No Studio", "Automated DE", "Santa Monica"}

# email prefix → studio, used to attribute HubSpot activities to the right studio
_DE_EMAIL_STUDIO = {
    "ashanti.gillespie": "Baltimore",    "nikolaus.pollutra": "Baltimore",   "olga.pushina": "Baltimore",
    "abby.keane": "Boston",              "brynn.cohune": "Boston",           "eric.sorensen": "Boston",      "heaven.chartier": "Boston",
    "julie.alfonso": "Charlotte",        "vaughan.hazeldine": "Charlotte",
    "brandi.davis": "Chicago",           "kaylee.krostag": "Chicago",        "kristen.rosario": "Chicago",   "sean.steele": "Chicago",
    "emily.nunn": "Dallas",              "jasmyne.boles": "Dallas",          "victoria.correa": "Dallas",
    "brittany.herrera": "Denver",        "robyn.yannoukos": "Denver",        "sydney.stetzel": "Denver",
    "david.mckeever": "Los Angeles",     "nick.pagdilao": "Los Angeles",     "richard.boone": "Los Angeles", "sarah.dreier": "Los Angeles",
    "angela.sunder": "Minneapolis",      "jose.macario": "Minneapolis",      "luz.rivera": "Minneapolis",    "zoe.finkelstein": "Minneapolis",
    "anastasia.seminchenko": "New York", "ibtesam.chowdhury": "New York",    "jamie.williams": "New York",
    "lauren.shull": "New York",          "mouny.alfraik": "New York",        "robert.perez": "New York",
    "jenee.satterwhite": "Philadelphia", "kagen.haberstick": "Philadelphia", "laurel.clark": "Philadelphia",
    "amira.seale": "San Francisco",      "bran.randol": "San Francisco",     "mary.langridge": "San Francisco", "rachel.kivo": "San Francisco",
    "alejandra.jimenez": "Seattle",      "kai.davies": "Seattle",            "laura.tulloch": "Seattle",     "lindsay.reyna": "Seattle",  "rachel.roth": "Seattle",
    "maico.vergara": "Washington DC",    "sameera.tanveer": "Washington DC", "shawn.neifert": "Washington DC",
}

# ── Dates ─────────────────────────────────────────────────────────────────────

def compute_dates():
    import zoneinfo
    today     = datetime.datetime.now(zoneinfo.ZoneInfo("America/Denver")).date()
    yd        = today - datetime.timedelta(days=1)
    lw_end    = yd
    lw_start  = lw_end  - datetime.timedelta(days=6)
    mtd_start = yd.replace(day=1)
    def ly(dt): return dt.replace(year=dt.year - 1)
    return dict(
        today=today, yd=yd,
        lw_start=lw_start, lw_end=lw_end, mtd_start=mtd_start,
        ly_yd=ly(yd),
        ly_lw_start=ly(lw_start), ly_lw_end=ly(lw_end),
        ly_mtd_start=ly(mtd_start),
    )

# ── Looker ────────────────────────────────────────────────────────────────────

class Looker:
    MODEL = "interior_define"

    def __init__(self):
        r = requests.post(f"{LOOKER_URL}/api/4.0/login",
                          data={"client_id": LOOKER_ID, "client_secret": LOOKER_SECRET},
                          timeout=30)
        r.raise_for_status()
        self._h = {"Authorization": f"token {r.json()['access_token']}",
                   "Content-Type": "application/json"}

    def _df(self, start, end):
        s = start.strftime("%Y/%m/%d")
        if start == end:
            return s
        # Looker "A to B" is exclusive of B; add 1 day to include end date
        e = (end + datetime.timedelta(days=1)).strftime("%Y/%m/%d")
        return f"{s} to {e}"

    def query(self, explore, fields, filters, sorts=None, limit=500, tz=None):
        body = {"model": self.MODEL, "view": explore,
                "fields": fields, "filters": filters,
                "sorts": sorts or [], "limit": str(limit)}
        if tz:
            body["query_timezone"] = tz
        r = requests.post(f"{LOOKER_URL}/api/4.0/queries/run/json",
                          headers=self._h, json=body, timeout=60)
        if not r.ok:
            print(f"  ⚠  Looker {explore} {r.status_code}: {r.text[:300]}", file=sys.stderr)
            r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else [data]

    def seg_revenue(self, start, end):
        """Revenue + orders by customer_group_class → {class: {rev, ord}}"""
        rows = self.query(
            explore="orders",
            fields=["customers.customer_group_class",
                    "orders.md_order_revenue", "orders.order_count"],
            filters={"orders.order_created_date": self._df(start, end)},
            tz="America/Denver",
        )
        result = {}
        for r in rows:
            cls = r.get("customers.customer_group_class") or "Other"
            result[cls] = {
                "rev": float(r.get("orders.md_order_revenue") or 0),
                "ord": int(r.get("orders.order_count") or 0),
            }
        return result

    def aov_by_class(self, start, end):
        """AOV per customer class → {class: float, blended: float}"""
        rows = self.query(
            explore="orders",
            fields=["customers.customer_group_class",
                    "orders.average_order_value", "orders.order_count"],
            filters={"orders.order_created_date": self._df(start, end)},
            tz="America/Denver",
        )
        result = {}
        total_rev, total_ord = 0.0, 0
        for r in rows:
            cls  = r.get("customers.customer_group_class") or "Other"
            aov  = float(r.get("orders.average_order_value") or 0)
            ords = int(r.get("orders.order_count") or 0)
            result[cls] = aov
            total_rev += aov * ords
            total_ord += ords
        result["blended"] = total_rev / total_ord if total_ord else 0.0
        return result

    def assisted_pct(self, start, end):
        """Fraction of revenue with meaningful contact (0–1)."""
        rows = self.query(
            explore="orders",
            fields=["hubspot_deals.has_meaningful_contact", "orders.md_order_revenue"],
            filters={"orders.order_created_date": self._df(start, end)},
            tz="America/Denver",
        )
        yes_rev = total_rev = 0.0
        for r in rows:
            rev = float(r.get("orders.md_order_revenue") or 0)
            total_rev += rev
            if r.get("hubspot_deals.has_meaningful_contact") == "Yes":
                yes_rev += rev
        return yes_rev / total_rev if total_rev else 0.0

    def inbound_contacts(self, start, end):
        """Inbound B2C contact count (excludes inside/burrow/GM/remote)."""
        try:
            rows = self.query(
                explore="hubspot_contacts",
                fields=["hubspot_contacts.number_of_contacts"],
                filters={
                    "hubspot_contacts.studio_name":
                        "-The Inside,-Burrow,-General Managers,-Remote Sales",
                    "hubspot_engagements.inbound_engagement": "Yes",
                    "hubspot_contacts.customer_group":        "B2C",
                    "hubspot_engagements.engagement_created_at_date": self._df(start, end),
                },
                tz="America/Chicago",
            )
            return int(rows[0].get("hubspot_contacts.number_of_contacts") or 0) if rows else 0
        except Exception as e:
            print(f"  ⚠  Inbound contacts query failed: {e}")
            return 0

    def studio_mtd(self, start, end):
        """Looker studio breakdown (MC + closed won) → list of {name, rev, orders, aov}"""
        try:
            rows = self.query(
                explore="orders",
                fields=["hubspot_deals.studio_name", "orders.md_order_revenue",
                        "orders.order_count", "orders.average_order_value"],
                filters={
                    "orders.order_created_date": self._df(start, end),
                    "hubspot_deals.has_meaningful_contact": "Yes",
                },
                sorts=["orders.md_order_revenue desc"],
                tz="America/Denver",
            )
            result = []
            for r in rows:
                name = (r.get("hubspot_deals.studio_name") or "").strip()
                if not name or name in STUDIO_EXCLUDE:
                    continue
                result.append({
                    "name":   name,
                    "rev":    float(r.get("orders.md_order_revenue") or 0),
                    "orders": int(r.get("orders.order_count") or 0),
                    "aov":    float(r.get("orders.average_order_value") or 0),
                })
            return result
        except Exception as e:
            print(f"  ⚠  Studio MTD query failed: {e}")
            return []

    def swatch(self, start, end):
        """Swatch orders + distinct customers → {orders, customers}"""
        try:
            rows = self.query(
                explore="swatch_orders",
                fields=["swatch_orders.count", "customers.count"],
                filters={
                    "swatch_orders.swatch_order_created_date": self._df(start, end),
                    "customers.customer_group_class":          "B2C,Trade",
                },
            )
            row = rows[0] if rows else {}
            return {
                "orders":    int(row.get("swatch_orders.count") or 0),
                "customers": int(row.get("customers.count") or 0),
            }
        except Exception as e:
            print(f"  ⚠  Swatch query failed: {e}")
            return {"orders": 0, "customers": 0}

    def studio_cvr(self, start, end):
        """Inbound B2C CVR by studio → list of {studio, contacts, orders, cvr}"""
        try:
            rows = self.query(
                explore="hubspot_contacts",
                fields=["hubspot_contacts.studio_name",
                        "hubspot_contacts.number_of_contacts",
                        "hubspot_contacts.all_converted_count"],
                filters={
                    "hubspot_contacts.studio_name":
                        "-The Inside,-Burrow,-General Managers,-Remote Sales",
                    "hubspot_engagements.inbound_engagement": "Yes",
                    "hubspot_contacts.customer_group":        "B2C",
                    "hubspot_engagements.engagement_created_at_date": self._df(start, end),
                },
                sorts=["hubspot_contacts.number_of_contacts desc"],
                tz="America/Chicago",
            )
            result = []
            for r in rows:
                studio   = (r.get("hubspot_contacts.studio_name") or "").strip()
                contacts = int(r.get("hubspot_contacts.number_of_contacts") or 0)
                orders   = int(r.get("hubspot_contacts.all_converted_count") or 0)
                if not studio or contacts == 0:
                    continue
                result.append({
                    "studio":   studio,
                    "contacts": contacts,
                    "orders":   orders,
                    "cvr":      round(orders / contacts * 100, 2),
                })
            return result
        except Exception as e:
            print(f"  ⚠  Studio CVR query failed: {e}")
            return []

    def monthly_inbound_cvr(self, months=12, today=None):
        """Monthly inbound B2C CVR trend → list of {month, contacts, d14, d30, d90}
        sorted oldest-first so charts render chronologically (left=old, right=new).
        The current partial month is included as the last entry (in-progress)."""
        if today is None:
            today = datetime.date.today()
        try:
            # Start at the first day of the same month one year ago to include 12
            # complete months plus the current partial month (13 rows total).
            start_mo = today.replace(year=today.year - 1, day=1)
            rows = self.query(
                explore="hubspot_contacts",
                fields=["hubspot_engagements.engagement_created_at_month",
                        "hubspot_contacts.number_of_contacts",
                        "hubspot_contacts.14_day_conversion_rate",
                        "hubspot_contacts.30_day_conversion_rate",
                        "hubspot_contacts.60_day_conversion_rate",
                        "hubspot_contacts.90_day_conversion_rate"],
                filters={
                    "hubspot_contacts.studio_name":
                        "-The Inside,-Burrow,-General Managers,-Remote Sales",
                    "hubspot_engagements.inbound_engagement": "Yes",
                    "hubspot_contacts.customer_group":        "B2C",
                    "hubspot_engagements.engagement_created_at_date":
                        self._df(start_mo, today),
                },
                sorts=["hubspot_engagements.engagement_created_at_month asc"],
                tz="America/Chicago",
                limit=months + 2,
            )
            result = []
            for r in rows:
                mo = r.get("hubspot_engagements.engagement_created_at_month")
                if not mo:
                    continue
                result.append({
                    "month":    mo,
                    "contacts": int(r.get("hubspot_contacts.number_of_contacts") or 0),
                    "d14":      round(float(r.get("hubspot_contacts.14_day_conversion_rate") or 0) * 100, 2),
                    "d30":      round(float(r.get("hubspot_contacts.30_day_conversion_rate") or 0) * 100, 2),
                    "d60":      round(float(r.get("hubspot_contacts.60_day_conversion_rate") or 0) * 100, 2),
                    "d90":      round(float(r.get("hubspot_contacts.90_day_conversion_rate") or 0) * 100, 2),
                })
            return result
        except Exception as e:
            print(f"  ⚠  Monthly CVR query failed: {e}")
            return []

    def forecast_by_day(self, start, end):
        """Daily forecast → {YYYY-MM-DD: amount} for the date range."""
        try:
            rows = self.query(
                explore="orders",
                fields=["sales_forecast.forecast_date_date",
                        "sales_forecast.ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS"],
                filters={"sales_forecast.forecast_date_date": self._df(start, end)},
                sorts=["sales_forecast.forecast_date_date"],
                limit=100,
            )
            return {
                r["sales_forecast.forecast_date_date"]:
                    float(r.get("sales_forecast.ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS") or 0)
                for r in rows
                if r.get("sales_forecast.forecast_date_date")
            }
        except Exception as e:
            print(f"  ⚠  Forecast query failed: {e}")
            return {}

# ── HubSpot ───────────────────────────────────────────────────────────────────

def _hs_h():
    return {"Authorization": f"Bearer {ID_HS_TOKEN}", "Content-Type": "application/json"}

def _hs_owner_map():
    """Fetch all HubSpot owners.
    Returns: ({owner_id: 'First Last'}, {owner_id: email_prefix})
    email_prefix is the part before '@', e.g. 'brandi.davis'.
    """
    try:
        names  = {}
        emails = {}
        after  = None
        while True:
            params = {"limit": 250}
            if after:
                params["after"] = after
            r = requests.get("https://api.hubapi.com/crm/v3/owners",
                             headers=_hs_h(), params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            for o in data.get("results", []):
                oid   = str(o.get("id", ""))
                name  = f"{o.get('firstName', '').strip()} {o.get('lastName', '').strip()}".strip()
                email = (o.get("email") or "").lower()
                if not name:
                    name = email or oid
                names[oid] = name
                if "@" in email:
                    emails[oid] = email.split("@")[0]   # e.g. "brandi.davis"
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        print(f"  Loaded {len(names)} HubSpot owners")
        return names, emails
    except Exception as e:
        print(f"  ⚠  Owner lookup failed: {e}")
        return {}, {}

def _ms(dt):
    """Date → start-of-day epoch ms UTC. HubSpot stores closedate as midnight UTC of
    the date the rep entered, so UTC boundaries are required to capture all deals."""
    return int(datetime.datetime(dt.year, dt.month, dt.day,
                                 tzinfo=timezone.utc).timestamp() * 1000)

def _ms_eod(dt):
    """Date → end-of-day epoch ms UTC (23:59:59 UTC)."""
    return int(datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59,
                                 tzinfo=timezone.utc).timestamp() * 1000)

def _hs_post(url, body, max_retries=5):
    """POST to HubSpot with exponential backoff on 429 rate-limit responses."""
    for attempt in range(max_retries):
        r = requests.post(url, headers=_hs_h(), json=body, timeout=30)
        if r.status_code == 429 and attempt < max_retries - 1:
            wait = 2 ** attempt   # 1 → 2 → 4 → 8 seconds
            print(f"  ⚠  HubSpot 429 — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        return r
    return r

def _hs_search(filter_groups, properties):
    results, after = [], None
    while True:
        body = {"filterGroups": filter_groups, "properties": properties, "limit": 100}
        if after:
            body["after"] = after
        r = _hs_post("https://api.hubapi.com/crm/v3/objects/deals/search", body)
        if not r.ok:
            print(f"  ⚠  HubSpot {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return results

def hs_deals(start, end, require_mc=True, owner_map=None, owner_studio_map=None):
    """
    Query closed-won deals for a date range.
    require_mc=True  → TY:  meaningful_contact_ = true (Aug 2025+)
    require_mc=False → LY:  all closed-won (approximation)
    owner_studio_map → {owner_id: studio} fallback when studio_name is blank on deal
    Returns: (total_rev, studio_list [{name, rev}], owner_list [{name, studio, rev}])
    """
    filters = [
        {"propertyName": "hs_is_closed_won", "operator": "EQ",  "value": "true"},
        {"propertyName": "closedate",         "operator": "GTE", "value": str(_ms(start))},
        {"propertyName": "closedate",         "operator": "LTE", "value": str(_ms_eod(end))},
    ]
    if require_mc:
        filters.append({"propertyName": "meaningful_contact_",
                        "operator": "EQ", "value": "true"})

    deals = _hs_search(
        filter_groups=[{"filters": filters}],
        properties=["amount", "hubspot_owner_id", "hubspot_team", "meaningful_contact_"],
    )

    total     = 0.0
    by_studio = {}
    by_owner  = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("hubspot_team") or "").strip()
        amt    = float(p.get("amount") or 0)
        oid    = str(p.get("hubspot_owner_id") or "")
        oname  = (owner_map or {}).get(oid) or oid
        # Fall back to owner email→studio mapping when HubSpot studio_name is blank
        if not studio and owner_studio_map:
            studio = owner_studio_map.get(oid, "")
        if studio in STUDIO_EXCLUDE:
            continue
        total += amt
        if studio:
            by_studio[studio] = by_studio.get(studio, 0) + amt
        if oid:
            if oid not in by_owner:
                by_owner[oid] = {"name": oname, "studio": studio, "rev": 0.0}
            by_owner[oid]["rev"] += amt

    studio_list = [{"name": k, "rev": v}
                   for k, v in sorted(by_studio.items(), key=lambda x: -x[1])]
    owner_list  = sorted(by_owner.values(), key=lambda x: -x["rev"])[:10]

    return total, studio_list, owner_list

def hs_studio_hs_mtd(start, end):
    """studio_hs_mtd: deals + deal count per studio → list of {name, rev, deals}"""
    deals = _hs_search(
        filter_groups=[{"filters": [
            {"propertyName": "hs_is_closed_won",   "operator": "EQ",  "value": "true"},
            {"propertyName": "meaningful_contact_", "operator": "EQ",  "value": "true"},
            {"propertyName": "closedate",           "operator": "GTE", "value": str(_ms(start))},
            {"propertyName": "closedate",           "operator": "LTE", "value": str(_ms_eod(end))},
        ]}],
        properties=["amount", "hubspot_team"],
    )
    by_studio = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("hubspot_team") or "").strip()
        amt    = float(p.get("amount") or 0)
        if not studio or studio in STUDIO_EXCLUDE:
            continue
        s = by_studio.setdefault(studio, {"rev": 0.0, "deals": 0})
        s["rev"]   += amt
        s["deals"] += 1
    return [{"name": k, "rev": v["rev"], "deals": v["deals"]}
            for k, v in sorted(by_studio.items(), key=lambda x: -x[1]["rev"])]

def hs_mc_pct(start, end):
    """MC% by studio → {studio: {total, mc_yes, mc_pct, mc_cvr, no_cvr}}"""
    deals = _hs_search(
        filter_groups=[{"filters": [
            {"propertyName": "hs_is_closed_won", "operator": "EQ",  "value": "true"},
            {"propertyName": "closedate",         "operator": "GTE", "value": str(_ms(start))},
            {"propertyName": "closedate",         "operator": "LTE", "value": str(_ms_eod(end))},
        ]}],
        properties=["hubspot_team", "meaningful_contact_"],
    )
    by_studio = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("hubspot_team") or "").strip()
        mc     = str(p.get("meaningful_contact_") or "").lower() == "true"
        if not studio or studio in STUDIO_EXCLUDE:
            continue
        s = by_studio.setdefault(studio, {"total": 0, "mc_yes": 0})
        s["total"]  += 1
        if mc:
            s["mc_yes"] += 1
    result = {}
    for studio, s in by_studio.items():
        total  = s["total"]
        mc_yes = s["mc_yes"]
        result[studio] = {
            "total":  total,
            "mc_yes": mc_yes,
            "mc_pct": round(mc_yes / total * 100, 1) if total else 0,
            "mc_cvr": 0.0,  # contact-level CVR requires engagements data
            "no_cvr": 0.0,
        }
    return result

def hs_activities(start, end, owner_studio_map):
    """
    Fetch HubSpot calls, meetings, emails for the date range and group by studio.
    owner_studio_map: {owner_id_str: studio_name} — only activities from mapped owners counted.
    Returns: {studio_name: {calls, meetings, emails, deals}}
    """
    def _fetch(object_type):
        counts = {}
        after  = None
        while True:
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": "hs_createdate", "operator": "GTE", "value": str(_ms(start))},
                    {"propertyName": "hs_createdate", "operator": "LTE", "value": str(_ms_eod(end))},
                ]}],
                "properties": ["hubspot_owner_id"],
                "limit": 100,
            }
            if after:
                body["after"] = after
            r = _hs_post(f"https://api.hubapi.com/crm/v3/objects/{object_type}/search", body)
            if r.status_code == 403:
                # Missing scope — skip this engagement type silently
                break
            if not r.ok:
                print(f"  ⚠  {object_type} activities {r.status_code}: {r.text[:200]}")
                break
            data = r.json()
            for obj in data.get("results", []):
                oid    = str((obj.get("properties") or {}).get("hubspot_owner_id") or "")
                studio = owner_studio_map.get(oid)
                if studio:
                    counts[studio] = counts.get(studio, 0) + 1
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        return counts

    try:
        calls    = _fetch("calls")
        meetings = _fetch("meetings")
        emails   = _fetch("emails")   # may return {} if scope not granted — handled above
        all_studios = set(calls) | set(meetings) | set(emails)
        result = {
            s: {
                "calls":    calls.get(s, 0),
                "meetings": meetings.get(s, 0),
                "emails":   emails.get(s, 0),
                "deals":    0,
            }
            for s in all_studios
        }
        total_acts = sum(v["calls"] + v["meetings"] + v["emails"] for v in result.values())
        print(f"  Activities: {total_acts} total across {len(result)} studios")
        return result
    except Exception as e:
        print(f"  ⚠  Activities fetch failed: {e}")
        return {}

# ── Google Sheet forecast ─────────────────────────────────────────────────────

def get_daily_forecast(d):
    """
    Returns {YYYY-MM-DD: amount} for the current month.
    Falls back to {} if unavailable.
    Expects the sheet to be "Anyone with the link can view" and gid to be set above.
    """
    try:
        resp = requests.get(FORECAST_CSV_URL, timeout=15)
        resp.raise_for_status()
        if resp.text.strip().startswith("<!"):
            print("  ⚠  Forecast sheet requires auth — set sharing to 'Anyone with the link' and fix gid")
            return {}
    except Exception as e:
        print(f"  ⚠  Forecast sheet unavailable: {e}")
        return {}

    rows = list(csv.reader(io.StringIO(resp.text)))
    mo, yr = d["mtd_start"].month, d["mtd_start"].year

    # Find the "Forecasted" column
    hdr_row = fcst_col = None
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if "forecast" in cell.strip().lower():
                hdr_row, fcst_col = i, j
                break
        if fcst_col is not None:
            break

    if fcst_col is None:
        # Fallback: assume second column is forecast
        hdr_row, fcst_col = 0, 1

    def pv(s):
        try:    return float(str(s).replace("$", "").replace(",", "").strip() or 0)
        except: return 0.0

    result = {}
    for row in rows[(hdr_row or 0) + 1:]:
        if not row or not row[0].strip():
            continue
        try:
            raw = row[0].strip().replace("-", "/")
            parts = raw.split("/")
            if len(parts) == 3:
                m2, day, y2 = int(parts[0]), int(parts[1]), int(parts[2])
                if y2 < 100: y2 += 2000
                if m2 != mo or y2 != yr:
                    continue
                dt_str = f"{yr}-{mo:02d}-{day:02d}"
                result[dt_str] = pv(row[fcst_col]) if fcst_col < len(row) else 0.0
        except:
            continue

    print(f"  Forecast: {len(result)} days loaded")
    return result

# ── Closing Notes (Slack #id--retail-closing-notes) ──────────────────────────

_CLOSING_NOTES_CHANNEL = "C08MYB2S3DH"

def get_closing_notes(yd):
    """
    Fetch studio closing notes for `yd` from #id--retail-closing-notes.
    Window: midnight CT on yd through 8am CT the following morning, so late
    posts (e.g. SF posting at 3am CT) are always captured.
    Returns an HTML string ready to drop into the report, or "" on failure.
    """
    if not SLACK_READ_TOKEN:
        return ""
    try:
        # Slack timestamps are real Unix seconds; use CT midnight so late posts
        # (e.g. SF posting after midnight UTC) are still captured under the right day.
        oldest_ts = datetime.datetime(yd.year, yd.month, yd.day, 0, 0, 0,
                                      tzinfo=_CT).timestamp()
        latest_ts = oldest_ts + 32 * 3600           # + 32 h = 8am CT next day

        r = requests.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {SLACK_READ_TOKEN}"},
            params={
                "channel": _CLOSING_NOTES_CHANNEL,
                "oldest":  oldest_ts,
                "latest":  latest_ts,
                "limit":   50,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            print(f"  ⚠  Slack closing notes error: {data.get('error')}")
            return ""

        messages = data.get("messages", [])
        if not messages:
            return "No closing notes posted for this date."

        parts = []
        for msg in reversed(messages):          # chronological order
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            safe = html.escape(text)
            # Convert Slack *bold* to <strong>
            safe = re.sub(r'\*([^*\n]+)\*', r'<strong>\1</strong>', safe)
            # Indent Slack bullet • into a styled span
            safe = re.sub(r'^([\t ]*)[••]', r'\1<span style="color:#6366f1">▸</span>', safe, flags=re.MULTILINE)
            parts.append(
                f'<div style="padding:10px 0;border-bottom:1px solid #f1f5f9;'
                f'white-space:pre-wrap;font-size:11.5px;line-height:1.65;color:#1e293b">'
                f'{safe}</div>'
            )

        print(f"  Closing notes: {len(parts)} studio posts loaded")
        return "".join(parts)
    except Exception as e:
        print(f"  ⚠  Closing notes fetch failed: {e}")
        return ""


# ── GitHub Pages ──────────────────────────────────────────────────────────────

def push_report_page(html, d):
    if not GITHUB_TOKEN:
        print("  ⚠  No GITHUB_TOKEN — skipping page publish")
        return None
    encoded = base64.b64encode(html.encode()).decode()
    headers = {"Authorization": f"token {GITHUB_TOKEN}",
               "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/index.html",
                     headers=headers, params={"ref": "gh-pages"})
    body = {"message": f"Report {d['yd']}", "content": encoded, "branch": "gh-pages"}
    if r.ok:
        body["sha"] = r.json()["sha"]
    r2 = requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/index.html",
                      headers=headers, json=body)
    if r2.ok:
        print(f"✅  Published → {PAGE_URL}")
        return PAGE_URL
    print(f"  ⚠  Page publish failed: {r2.status_code} {r2.text[:300]}")
    return None

# ── Slack deduplication ───────────────────────────────────────────────────────

_POSTED_FLAG = "last_slack_post.txt"

def _gh_h():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def check_already_posted(date_str):
    if not GITHUB_TOKEN: return False
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_POSTED_FLAG}",
                     headers=_gh_h())
    if not r.ok: return False
    try:   return base64.b64decode(r.json()["content"]).decode().strip() == date_str
    except: return False

def mark_as_posted(date_str):
    if not GITHUB_TOKEN: return
    encoded = base64.b64encode(date_str.encode()).decode()
    body    = {"message": f"Mark posted {date_str}", "content": encoded}
    r       = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_POSTED_FLAG}",
                           headers=_gh_h())
    if r.ok: body["sha"] = r.json()["sha"]
    r2 = requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_POSTED_FLAG}",
                      headers=_gh_h(), json=body)
    if not r2.ok:
        print(f"  ⚠  Could not update flag: {r2.status_code}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmtd(v):  return f"${v:,.0f}" if v else "$0"
def pct(a, b): return round((a / b - 1) * 100, 1) if b else None
def sign(v):
    if v is None: return "–"
    return f"▲ {abs(v):.0f}%" if v >= 0 else f"▼ {abs(v):.0f}%"

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    d = compute_dates()
    print(f"yd={d['yd']}  mtd_start={d['mtd_start']}")

    today_str = str(d["today"])
    already_posted = check_already_posted(today_str)

    # ── Looker ────────────────────────────────────────────────────────────────
    print("Connecting to Looker...")
    lk = Looker()

    print("Querying segment revenue (6 windows)...")
    seg_yd_ty  = lk.seg_revenue(d["yd"],           d["yd"])
    seg_yd_ly  = lk.seg_revenue(d["ly_yd"],        d["ly_yd"])
    seg_lw_ty  = lk.seg_revenue(d["lw_start"],     d["lw_end"])
    seg_lw_ly  = lk.seg_revenue(d["ly_lw_start"],  d["ly_lw_end"])
    seg_mtd_ty = lk.seg_revenue(d["mtd_start"],    d["yd"])
    seg_mtd_ly = lk.seg_revenue(d["ly_mtd_start"], d["ly_yd"])

    print("Querying AOV (6 windows)...")
    aov_yd_ty  = lk.aov_by_class(d["yd"],           d["yd"])
    aov_yd_ly  = lk.aov_by_class(d["ly_yd"],        d["ly_yd"])
    aov_lw_ty  = lk.aov_by_class(d["lw_start"],     d["lw_end"])
    aov_lw_ly  = lk.aov_by_class(d["ly_lw_start"],  d["ly_lw_end"])
    aov_mtd_ty = lk.aov_by_class(d["mtd_start"],    d["yd"])
    aov_mtd_ly = lk.aov_by_class(d["ly_mtd_start"], d["ly_yd"])

    print("Querying assisted % (3 windows)...")
    assisted_yd  = lk.assisted_pct(d["yd"],        d["yd"])
    assisted_lw  = lk.assisted_pct(d["lw_start"],  d["lw_end"])
    assisted_mtd = lk.assisted_pct(d["mtd_start"], d["yd"])

    print("Querying inbound contacts (6 windows)...")
    inbound_yd_ty  = lk.inbound_contacts(d["yd"],           d["yd"])
    inbound_yd_ly  = lk.inbound_contacts(d["ly_yd"],        d["ly_yd"])
    inbound_lw_ty  = lk.inbound_contacts(d["lw_start"],     d["lw_end"])
    inbound_lw_ly  = lk.inbound_contacts(d["ly_lw_start"],  d["ly_lw_end"])
    inbound_mtd_ty = lk.inbound_contacts(d["mtd_start"],    d["yd"])
    inbound_mtd_ly = lk.inbound_contacts(d["ly_mtd_start"], d["ly_yd"])

    print("Querying Looker studios MTD...")
    looker_studios = lk.studio_mtd(d["mtd_start"], d["yd"])

    print("Querying studio CVR (MTD + 90d)...")
    studio_cvr_mtd_data = lk.studio_cvr(d["mtd_start"], d["yd"])
    d90_cvr_start       = d["yd"] - datetime.timedelta(days=89)
    studio_cvr_90d_rows = lk.studio_cvr(d90_cvr_start, d["yd"])
    studio_cvr_90d_data = {r["studio"]: r["cvr"] for r in studio_cvr_90d_rows}

    print("Querying monthly inbound CVR trend...")
    monthly_cvr_data = lk.monthly_inbound_cvr(months=12, today=d["today"])

    print("Querying swatch (TY + LY)...")
    sw_looker_ty = lk.swatch(d["mtd_start"],    d["yd"])
    sw_looker_ly = lk.swatch(d["ly_mtd_start"], d["ly_yd"])

    # ── Forecast ──────────────────────────────────────────────────────────────
    # Looker sales_forecast → Total Business tab (yd_fcst, lw_fcst, mtd_fcst)
    # Google Sheet         → Sales Team tab only (daily_fcst, full_mo_fcst)
    print("Querying Looker forecast (Total Business)...")
    mo_end = d["yd"].replace(day=28) + datetime.timedelta(days=4)
    mo_end = mo_end - datetime.timedelta(days=mo_end.day)  # last day of month
    looker_daily_fcst = lk.forecast_by_day(d["mtd_start"], mo_end)

    def sum_looker_fcst(start, end):
        cur, total = start, 0.0
        while cur <= end:
            total += looker_daily_fcst.get(str(cur), 0.0)
            cur += datetime.timedelta(days=1)
        return total

    yd_fcst  = sum_looker_fcst(d["yd"],        d["yd"])
    lw_fcst  = sum_looker_fcst(d["lw_start"],  d["lw_end"])
    mtd_fcst = sum_looker_fcst(d["mtd_start"], d["yd"])

    print("Fetching Google Sheet forecast (Sales tab)...")
    sales_daily_fcst   = get_daily_forecast(d)
    sales_full_mo_fcst = sum(sales_daily_fcst.values())

    # ── HubSpot ───────────────────────────────────────────────────────────────
    hs_yd_ty = hs_lw_ty = hs_mtd_ty = 0.0
    hs_yd_ly = hs_lw_ly = hs_mtd_ly = 0.0
    studio_yd_ty = studio_lw_ty = []
    studio_lw_ly_list = []
    reps_mtd = studio_hs_mtd = []
    mc_mtd = mc_90d = {}
    activities_data = {}
    owner_studio_map = {}

    if ID_HS_TOKEN:
        print("Fetching HubSpot owner names...")
        owner_map, owner_emails = _hs_owner_map()
        # Map owner_id → studio for activities attribution (DE/SDE email prefixes only)
        owner_studio_map = {
            oid: _DE_EMAIL_STUDIO[prefix]
            for oid, prefix in owner_emails.items()
            if prefix in _DE_EMAIL_STUDIO
        }
        print(f"  Mapped {len(owner_studio_map)} DE/SDE owners to studios")

        print("Querying HubSpot (TY)...")
        try:
            hs_yd_ty,  studio_yd_ty,  _              = hs_deals(d["yd"],        d["yd"],       owner_map=owner_map, owner_studio_map=owner_studio_map)
            hs_lw_ty,  studio_lw_ty,  _              = hs_deals(d["lw_start"],  d["lw_end"],   owner_map=owner_map, owner_studio_map=owner_studio_map)
            hs_mtd_ty, studio_mtd_list, reps_mtd     = hs_deals(d["mtd_start"], d["yd"],       owner_map=owner_map, owner_studio_map=owner_studio_map)
            studio_hs_mtd = [{"name": s["name"], "rev": s["rev"], "deals": 0} for s in studio_mtd_list]
            d90_start                           = d["yd"] - datetime.timedelta(days=89)
            mc_mtd                              = hs_mc_pct(d["mtd_start"], d["yd"])
            if not mc_mtd:
                print("  MTD mc_pct empty (early month) — falling back to last 30 days")
                mc_mtd = hs_mc_pct(d["yd"] - datetime.timedelta(days=29), d["yd"])
            mc_90d                              = hs_mc_pct(d90_start,      d["yd"])
        except Exception as e:
            print(f"  ⚠  HubSpot TY error: {e}")

        print("Querying HubSpot activities (calls/meetings/emails MTD)...")
        try:
            activities_data = hs_activities(d["mtd_start"], d["yd"], owner_studio_map)
        except Exception as e:
            print(f"  ⚠  HubSpot activities error: {e}")

        print("Querying HubSpot (LY)...")
        try:
            hs_yd_ly,  _,                 _ = hs_deals(d["ly_yd"],        d["ly_yd"],       require_mc=False, owner_map=owner_map)
            hs_lw_ly,  studio_lw_ly_list, _ = hs_deals(d["ly_lw_start"],  d["ly_lw_end"],   require_mc=False, owner_map=owner_map)
            hs_mtd_ly, _,                 _ = hs_deals(d["ly_mtd_start"], d["ly_yd"],        require_mc=False, owner_map=owner_map)
        except Exception as e:
            print(f"  ⚠  HubSpot LY error: {e}")
    else:
        print("  ⚠  ID_HUBSPOT_TOKEN not set — skipping HubSpot queries")

    studio_lw_ly = {s["name"]: s["rev"] for s in studio_lw_ly_list}

    # ── Assemble data dict ────────────────────────────────────────────────────
    data = {
        "dates": {
            "today":       str(d["today"]),
            "yd":          str(d["yd"]),
            "mo_start":    str(d["mtd_start"]),
            "lw_start":    str(d["lw_start"]),
            "lw_end":      str(d["lw_end"]),
            "ly_yd":       str(d["ly_yd"]),
            "ly_mo_start": str(d["ly_mtd_start"]),
            "ly_lw_start": str(d["ly_lw_start"]),
            "ly_lw_end":   str(d["ly_lw_end"]),
        },
        # Revenue by segment
        "seg_yd_ty":  seg_yd_ty,   "seg_yd_ly":  seg_yd_ly,
        "seg_lw_ty":  seg_lw_ty,   "seg_lw_ly":  seg_lw_ly,
        "seg_mtd_ty": seg_mtd_ty,  "seg_mtd_ly": seg_mtd_ly,
        # AOV
        "aov_yd_ty":      aov_yd_ty.get("blended", 0),
        "aov_yd_ly":      aov_yd_ly.get("blended", 0),
        "aov_yd_b2c_ty":  aov_yd_ty.get("B2C", 0),
        "aov_yd_b2c_ly":  aov_yd_ly.get("B2C", 0),
        "aov_yd_tr_ty":   aov_yd_ty.get("Trade", 0),
        "aov_yd_tr_ly":   aov_yd_ly.get("Trade", 0),
        "aov_lw_ty":      aov_lw_ty.get("blended", 0),
        "aov_lw_ly":      aov_lw_ly.get("blended", 0),
        "aov_lw_b2c_ty":  aov_lw_ty.get("B2C", 0),
        "aov_lw_b2c_ly":  aov_lw_ly.get("B2C", 0),
        "aov_lw_tr_ty":   aov_lw_ty.get("Trade", 0),
        "aov_lw_tr_ly":   aov_lw_ly.get("Trade", 0),
        "aov_mtd_ty":     aov_mtd_ty.get("blended", 0),
        "aov_mtd_ly":     aov_mtd_ly.get("blended", 0),
        "aov_mtd_b2c_ty": aov_mtd_ty.get("B2C", 0),
        "aov_mtd_b2c_ly": aov_mtd_ly.get("B2C", 0),
        "aov_mtd_tr_ty":  aov_mtd_ty.get("Trade", 0),
        "aov_mtd_tr_ly":  aov_mtd_ly.get("Trade", 0),
        # Assisted %
        "assisted_yd":  assisted_yd,
        "assisted_lw":  assisted_lw,
        "assisted_mtd": assisted_mtd,
        # Inbound
        "inbound_yd_ty":  inbound_yd_ty,   "inbound_yd_ly":  inbound_yd_ly,
        "inbound_lw_ty":  inbound_lw_ty,   "inbound_lw_ly":  inbound_lw_ly,
        "inbound_mtd_ty": inbound_mtd_ty,  "inbound_mtd_ly": inbound_mtd_ly,
        # Looker studios (MC + closed won, MTD)
        "looker_studios": looker_studios,
        # Swatch
        "sw_looker_ty": sw_looker_ty,  "sw_looker_ly": sw_looker_ly,
        "sw_mtd_ty":    sw_looker_ty,  "sw_mtd_ly":    sw_looker_ly,
        # Forecast — Google Sheet for Sales tab pacing; Looker sums for Total Business
        "daily_fcst":   sales_daily_fcst,     # Google Sheet → DAILY_FCST in Sales tab
        "full_mo_fcst": sales_full_mo_fcst,
        "yd_fcst":  yd_fcst,                  # Looker → YD/LW/MTD v-plan in Total Business
        "lw_fcst":  lw_fcst,
        "mtd_fcst": mtd_fcst,
        # HubSpot sales totals
        "hs_yd_ty":  hs_yd_ty,   "hs_yd_ly":  hs_yd_ly,
        "hs_lw_ty":  hs_lw_ty,   "hs_lw_ly":  hs_lw_ly,
        "hs_mtd_ty": hs_mtd_ty,  "hs_mtd_ly": hs_mtd_ly,
        # HubSpot by-studio breakdowns
        "studio_yd_ty":  studio_yd_ty,
        "studio_lw_ty":  studio_lw_ty,
        "studio_lw_ly":  studio_lw_ly,
        "studio_hs_mtd": studio_hs_mtd,
        # By-rep and MC%
        "reps_mtd": reps_mtd,
        "mc_mtd":   mc_mtd,
        "mc_90d":   mc_90d,
        "studio_cvr_mtd": studio_cvr_mtd_data,
        "studio_cvr_90d": studio_cvr_90d_data,
        "monthly_cvr":    monthly_cvr_data,
        "activities":     activities_data,   # HubSpot calls/meetings/emails by studio
        "repeat_pct":     0,
        "merch":          [],
        "closing_notes":  get_closing_notes(d["yd"]),
    }

    # ── Generate HTML ─────────────────────────────────────────────────────────
    print("Generating HTML...")
    os.makedirs("/tmp/id", exist_ok=True)
    with open("/tmp/id/data.json", "w") as f:
        json.dump(data, f)

    result = subprocess.run(
        ["python3", "scripts/generate_report.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌  generate_report.py failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    with open("/tmp/id/report.html") as f:
        html = f.read()

    # ── Publish ───────────────────────────────────────────────────────────────
    report_url = push_report_page(html, d)

    # ── Slack ─────────────────────────────────────────────────────────────────
    yd_tot  = sum(v.get("rev", 0) for v in seg_yd_ty.values())
    mtd_tot = sum(v.get("rev", 0) for v in seg_mtd_ty.values())
    ly_tot  = sum(v.get("rev", 0) for v in seg_mtd_ly.values())
    mtd_aov = aov_mtd_ty.get("blended", 0)

    lw_label = (f"{d['lw_start'].strftime('%b %-d')}–{d['lw_end'].strftime('%-d')}"
                if d["lw_start"].month == d["lw_end"].month
                else f"{d['lw_start'].strftime('%b %-d')}–{d['lw_end'].strftime('%b %-d')}")

    link_line = f"\n<{report_url}|View full report →>" if report_url else ""

    text = (
        f"📊 *Interior Define Daily Business Review — {d['yd'].strftime('%a %b %-d, %Y')}*"
        f"{link_line}\n\n"
        f"*Total Business MTD (thru {d['yd'].strftime('%b %-d')})*\n"
        f"Revenue: *{fmtd(mtd_tot)}*  {sign(pct(mtd_tot, ly_tot))} vs LY  "
        f"|  AOV: *{fmtd(mtd_aov)}*\n"
        f"Assisted: *{assisted_mtd*100:.1f}%*  |  Inbound: *{inbound_mtd_ty:,}*\n\n"
        f"*Yesterday ({d['yd'].strftime('%a %b %-d')})*\n"
        f"Revenue: *{fmtd(yd_tot)}*  |  HS Sales: *{fmtd(hs_yd_ty)}*\n"
    )
    if looker_studios:
        text += f"\n*Studio MTD (MC + Closed Won)*\n"
        for s in looker_studios[:6]:
            text += f"• {s['name']}: {fmtd(s['rev'])}\n"

    if TRIGGERED_BY != "schedule":
        print(f"ℹ️  Manual run (TRIGGERED_BY={TRIGGERED_BY!r}) — skipping Slack")
    elif already_posted:
        print(f"ℹ️  Already posted today ({today_str}) — skipping Slack")
    else:
        print("Posting to Slack...")
        resp = requests.post(SLACK_WEBHOOK, json={"text": text, "mrkdwn": True}, timeout=15)
        if resp.status_code == 200 and resp.text == "ok":
            print("✅  Slack posted")
            mark_as_posted(today_str)
        else:
            print(f"❌  Slack error: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
