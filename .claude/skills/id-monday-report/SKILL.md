---
name: id-monday-report
description: Run, verify, or edit the Interior Define Monday Business Review report. Use when coverage needs to manually trigger the report, check if data is fresh, update monthly goals, or fix a specific metric that looks wrong.
---

# Interior Define Monday Business Review — Coverage Skill

## What This Report Is

A two-tab HTML + PDF report that runs automatically every Monday at 8am CT and posts to **havenlyteam.slack.com** via the ID Report Bot. It covers:
- **Tab 1 — Total Business:** Revenue, AOV, inbound engagements, swatch orders, merch mix, studio performance, CVR trends
- **Tab 2 — Sales Team:** HubSpot net sales, pacing vs goals, closing notes, MC%, inbound CVR

**If something looks wrong or you need to re-run it:**

---

## How to Verify Data is Fresh

The Slack message from the bot will always include a line like:
> *Data as of Sun Jun 22, 2026 — yesterday revenue $XXX,XXX*

Cross-check that number against [Looker dashboard 1156](https://havenly.looker.com/dashboards/1156) → "Discounted Order Revenue Yesterday" tile. If they match, data is fresh.

---

## How to Re-Run the Report Manually

1. Open Claude Code (this app)
2. Type `/id-monday-report run` — this skill will execute the report
3. Or say: "run the ID Monday report for today"

The skill will:
1. Pull fresh data from Snowflake (Havenly Analytics MCP)
2. Fetch HubSpot deal data
3. Read Slack closing notes
4. Generate the 2-tab HTML report + PDF
5. Post to havenlyteam.slack.com via webhook

---

## Quick Run Instructions

When invoked to run the report:

**Step 1: Compute dates**
```python
import datetime
today = datetime.date.today()
yd = today - datetime.timedelta(days=1)  # yesterday (Sunday if run on Monday)
mo_start = yd.replace(day=1)
ly_yd = yd.replace(year=yd.year - 1)
ly_mo_start = mo_start.replace(year=mo_start.year - 1)
```

**Step 2: Fetch key data via Havenly Analytics MCP**

Run these Snowflake queries (via `mcp__claude_ai_Havenly_Brands_Analytics_MCP__execute_query`):

Yesterday revenue:
```sql
SELECT CASE WHEN c.CUSTOMER_ID=20 THEN 'Havenly' ELSE c.CUSTOMER_GROUP_CLASS END AS segment,
  SUM(o.subtotal-ABS(o.discount_amount)+o.shipping_amount) AS revenue, COUNT(*) AS orders
FROM PROD.ID_WAREHOUSE.ORDERS o JOIN ID_WAREHOUSE.CUSTOMERS c ON o.CUSTOMER_ID=c.CUSTOMER_ID
WHERE CONVERT_TIMEZONE('UTC','America/Denver',CAST(o.ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE='[YD]'
  AND (c.EMAIL NOT LIKE '%@interiordefine.com%' OR c.EMAIL IS NULL)
GROUP BY segment
```

MTD revenue (same but date BETWEEN [MO_START] AND [YD]).

Yesterday forecast:
```sql
SELECT ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS FROM FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST
WHERE TO_DATE(Date)='[YD]'
```

**Step 3: Update the script and generate report**
```bash
# Navigate to wherever you cloned the repo on your machine, e.g.:
# cd ~/id-daily-business-review   (Matthew/Leeanne)
# cd /Users/mc.spreck/mary-claire-daily-business-review   (MC's machine)
source venv/bin/activate
# Update data variables in scripts/run_from_mcp.py (see HOW TO EDIT below)
python scripts/run_from_mcp.py
```

**Step 4: Generate PDF**
```python
import asyncio, os, pathlib
from playwright.async_api import async_playwright

# Works from any machine — uses the repo root, not a hardcoded path
REPO = pathlib.Path(__file__).parent.parent if '__file__' in dir() else pathlib.Path.cwd()
HTML = (REPO / 'output' / 'report.html').resolve()
PDF  = (REPO / 'output' / 'report.pdf').resolve()

async def gen():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(f'file://{HTML}')
        await pg.wait_for_load_state('networkidle')
        await pg.pdf(path=str(PDF), format='A4', print_background=True,
            margin={'top':'10mm','bottom':'10mm','left':'8mm','right':'8mm'})
        await b.close()

asyncio.run(gen())
```

**Step 5: Upload PDF and post to Slack**
```python
import requests, pathlib

REPO    = pathlib.Path.cwd()  # run from repo root
PDF     = str(REPO / 'output' / 'report.pdf')
WEBHOOK = 'https://hooks.slack.com/services/[ask-MC-for-webhook-url]'

URL = requests.post('https://tmpfiles.org/api/v1/upload',
    files={'file': open(PDF,'rb')}, data={'expires':'1d'}).json().get('data',{}).get('url','').replace('tmpfiles.org/','tmpfiles.org/dl/')

requests.post(WEBHOOK, json={'text': f'<{URL}|📄 ID Business Review — {yd.strftime("%a %b %-d, %Y")}>\n\n*Data as of {yd.strftime("%a %b %-d, %Y")} — verify yesterday revenue matches Looker dashboard 1156*'})
```

---

## How to Edit the Report

The main script is at:
`/Users/mc.spreck/mary-claire-daily-business-review/scripts/run_from_mcp.py`

Also on GitHub: https://github.com/maryspreck-star/id-daily-business-review

### Update monthly rep/studio goals (do this at start of each new month)
Find `STUDIO_GOALS` and `REP_GOALS` dicts in the script (~line 440). Update with new month's numbers from the Google Sheet:
- **Forecast sheet:** `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` (tab: "For claude_add each month")  
- **Goals sheet:** `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` (tab: "for claude")

Also update `DAILY_FCST` dict with the new month's daily forecast values.

### Add a new rep who shows $0
Find `REP_GOALS` dict. Add an entry:
```python
"first.last": ("Full Name", "Studio Name", goal_amount),
```
Key = their email prefix (e.g., `"jane.doe"` for `jane.doe@interiordefine.com`).

### Fix a metric that looks wrong
Find the variable at the top of the script (all data vars are in the `# ── DATA` section, lines ~180-470). Update the value. Run `python scripts/run_from_mcp.py` to preview, then regenerate PDF.

### Add someone to the email/Slack list
Currently posts to the havenlyteam.slack.com webhook. To add more people to the routine's automated delivery, contact MC or update the routine at:
https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5

---

## Key References

| Resource | Link/Value |
|---|---|
| GitHub repo | https://github.com/maryspreck-star/id-daily-business-review |
| Routine (manage/pause) | https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 |
| Looker dashboard | https://havenly.looker.com/dashboards/1156 |
| Slack webhook | `https://hooks.slack.com/services/[ask-MC-for-webhook-url]` |
| HubSpot API key | In script (or ask MC) |
| Methodology doc | `mary-claire-daily-business-review/docs/data-methodology.md` |
| Script location | `mary-claire-daily-business-review/scripts/run_from_mcp.py` |

---

## Troubleshooting

**No Slack message received Monday morning:**
1. Check the routine is enabled: https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5
2. Run manually using this skill
3. Check havenlyteam.slack.com for any partial messages

**Numbers look stale (same as last week):**
- The agent may not have refreshed the data. Run this skill to force a fresh pull.

**PDF only shows one tab:**
- The `@media print` CSS should fix this. If broken, check that the CSS block in the script contains `#content-sales{page-break-before:always}` and both tab-content divs are set to `display:block!important`.

**DST change (November — report fires at 7am CT instead of 8am):**
- Update the cron at the routine URL above from `0 13 * * 1` to `0 14 * * 1`.

**New rep not appearing in pacing table:**
- Add them to `REP_GOALS` dict in the script. Key = email prefix.

**Pacing table goals are for wrong month:**
- Update `STUDIO_GOALS`, `REP_GOALS`, and `DAILY_FCST` at the start of each month.
