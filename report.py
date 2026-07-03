#!/usr/bin/env python3
"""
Interior Define Daily Business Review
Runs every weekday at 8am CT via GitHub Actions.
Data: Looker (interior_define model) for Total Business tab +
      HubSpot Private App for Sales tab.
Forecast: Google Sheet CSV export (must be "Anyone with link can view").
Delivery: HTML → GitHub Pages; Slack link → #salesoperations.
"""

import os, sys, datetime, csv, io, base64, json, subprocess
import requests
from datetime import timezone

# ── Config ────────────────────────────────────────────────────────────────────

LOOKER_URL    = os.environ["LOOKER_BASE_URL"]
LOOKER_ID     = os.environ["LOOKER_CLIENT_ID"]
LOOKER_SECRET = os.environ["LOOKER_CLIENT_SECRET"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK_URL"]
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
ID_HS_TOKEN   = os.environ.get("ID_HUBSPOT_TOKEN", "")
GITHUB_REPO   = "maryspreck-star/id-daily-business-review"
PAGE_URL      = "https://maryspreck-star.github.io/id-daily-business-review/"

# Open the sheet in a browser, click the "ID RETAIL DAILY SALES_MC" tab,
# and copy the gid=XXXXXXXX number from the URL, then replace 0 below.
# Also ensure sharing is set to "Anyone with the link can view".
FORECAST_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0"
    "/export?format=csv&gid=0"  # TODO: replace 0 with correct gid
)

STUDIO_EXCLUDE = {"Assisted No Studio", "Automated DE", "Santa Monica"}

# ── Dates ─────────────────────────────────────────────────────────────────────

def compute_dates():
    today     = datetime.date.today()
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
        e = end.strftime("%Y/%m/%d")
        return s if start == end else f"{s} to {e}"

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
                fields=["swatch_orders.order_count", "swatch_orders.distinct_customers"],
                filters={
                    "swatch_orders.created_date":         self._df(start, end),
                    "customers.customer_group_class": "B2C,Trade",
                },
            )
            row = rows[0] if rows else {}
            return {
                "orders":    int(row.get("swatch_orders.order_count") or 0),
                "customers": int(row.get("swatch_orders.distinct_customers") or 0),
            }
        except Exception as e:
            print(f"  ⚠  Swatch query failed: {e}")
            return {"orders": 0, "customers": 0}

# ── HubSpot ───────────────────────────────────────────────────────────────────

def _hs_h():
    return {"Authorization": f"Bearer {ID_HS_TOKEN}", "Content-Type": "application/json"}

def _ms(dt):
    """Date → start-of-day epoch ms UTC."""
    return int(datetime.datetime(dt.year, dt.month, dt.day,
                                 tzinfo=timezone.utc).timestamp() * 1000)

def _ms_eod(dt):
    """Date → end-of-day epoch ms UTC."""
    return int(datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59,
                                 tzinfo=timezone.utc).timestamp() * 1000)

def _hs_search(filter_groups, properties):
    results, after = [], None
    while True:
        body = {"filterGroups": filter_groups, "properties": properties, "limit": 100}
        if after:
            body["after"] = after
        r = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                          headers=_hs_h(), json=body, timeout=30)
        if not r.ok:
            print(f"  ⚠  HubSpot {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return results

def hs_deals(start, end, require_mc=True):
    """
    Query closed-won deals for a date range.
    require_mc=True  → TY:  meaningful_contact_ = true (Aug 2025+)
    require_mc=False → LY:  all closed-won (approximation; ideally would use
                            stage-date filter but DATEDIFF not available in API)
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
        properties=["amount", "hubspot_owner_id", "studio_name",
                    "meaningful_contact_", "hubspot_owner_displayname"],
    )

    total     = 0.0
    by_studio = {}
    by_owner  = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("studio_name") or "").strip()
        amt    = float(p.get("amount") or 0)
        oid    = str(p.get("hubspot_owner_id") or "")
        oname  = (p.get("hubspot_owner_displayname") or oid).strip()
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
        properties=["amount", "studio_name"],
    )
    by_studio = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("studio_name") or "").strip()
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
        properties=["studio_name", "meaningful_contact_"],
    )
    by_studio = {}
    for deal in deals:
        p      = deal.get("properties", {})
        studio = (p.get("studio_name") or "").strip()
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
    if check_already_posted(today_str):
        print(f"ℹ️  Already posted today ({today_str}) — skipping")
        return

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

    print("Querying swatch (TY + LY)...")
    sw_looker_ty = lk.swatch(d["mtd_start"],    d["yd"])
    sw_looker_ly = lk.swatch(d["ly_mtd_start"], d["ly_yd"])

    # ── Forecast sheet ────────────────────────────────────────────────────────
    print("Reading forecast sheet...")
    daily_fcst   = get_daily_forecast(d)
    full_mo_fcst = sum(daily_fcst.values())

    # ── HubSpot ───────────────────────────────────────────────────────────────
    hs_yd_ty = hs_lw_ty = hs_mtd_ty = 0.0
    hs_yd_ly = hs_lw_ly = hs_mtd_ly = 0.0
    studio_yd_ty = studio_lw_ty = []
    studio_lw_ly_list = []
    reps_mtd = studio_hs_mtd = []
    mc_mtd = mc_90d = {}

    if ID_HS_TOKEN:
        print("Querying HubSpot (TY)...")
        try:
            hs_yd_ty,  studio_yd_ty,  _        = hs_deals(d["yd"],        d["yd"])
            hs_lw_ty,  studio_lw_ty,  _        = hs_deals(d["lw_start"],  d["lw_end"])
            hs_mtd_ty, _,             reps_mtd = hs_deals(d["mtd_start"], d["yd"])
            studio_hs_mtd                       = hs_studio_hs_mtd(d["mtd_start"], d["yd"])
            mc_mtd                              = hs_mc_pct(d["mtd_start"], d["yd"])
            d90_start                           = d["yd"] - datetime.timedelta(days=89)
            mc_90d                              = hs_mc_pct(d90_start,      d["yd"])
        except Exception as e:
            print(f"  ⚠  HubSpot TY error: {e}")

        print("Querying HubSpot (LY)...")
        try:
            hs_yd_ly,  _,                 _ = hs_deals(d["ly_yd"],        d["ly_yd"],       require_mc=False)
            hs_lw_ly,  studio_lw_ly_list, _ = hs_deals(d["ly_lw_start"],  d["ly_lw_end"],   require_mc=False)
            hs_mtd_ly, _,                 _ = hs_deals(d["ly_mtd_start"], d["ly_yd"],        require_mc=False)
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
        # Forecast (Google Sheet retail daily)
        "daily_fcst":   daily_fcst,
        "full_mo_fcst": full_mo_fcst,
        # All-company Snowflake forecast — not available from GitHub Actions, left as 0
        # The report shows these as blank/missing rather than wrong numbers
        "yd_fcst":  0,
        "lw_fcst":  0,
        "mtd_fcst": 0,
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
        # Fields requiring Snowflake/complex logic — generate_report.py handles empty gracefully
        "activities":     {},
        "studio_cvr_mtd": [],
        "studio_cvr_90d": {},
        "monthly_cvr":    [],
        "repeat_pct":     0,
        "merch":          [],
        "closing_notes":  "",
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
