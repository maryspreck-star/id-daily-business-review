# ID Monday Business Review — Coverage Guide
**For: Matthew Gomes, Leeanne, and new hire**
**While MC is on maternity leave**

---

## Overview

The Monday Business Review is a two-tab report (Total Business + Sales Team) that automatically runs every Monday at 8am CT and posts to the `#id-report` channel in havenlyteam.slack.com. **Most weeks you don't need to do anything — it runs itself.**

There are two situations where you'll need to step in:

1. **Start of each new month** — update goals and forecast in the script (Matthew does this)
2. **If the Monday report doesn't arrive or looks wrong** — manually re-run it

---

## PART 1 — One-Time Setup (do this before MC leaves)

### Step 1: Install Claude Code

Download from https://claude.ai/code and sign in with your Anthropic account.

### Step 2: Get the Havenly Analytics MCP connected

In Claude Code, make sure you have the **Havenly Brands Analytics MCP** connected — this is what pulls Snowflake data. If you're not sure, ask MC before she leaves.

### Step 3: Clone the repo

Open Terminal and run:
```bash
git clone https://github.com/maryspreck-star/id-daily-business-review
cd id-daily-business-review
```

### Step 4: Set up Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Step 5: Get the Slack webhook URL from MC

The webhook URL is not in GitHub (for security). Ask MC to send it to you before she leaves. You'll need it if you ever manually post the report to Slack.

---

## PART 2 — Monthly Update (1st of every month — Matthew)

This is the main recurring task. At the start of July (and every subsequent month), you need to update three things in the script:

1. **STUDIO_GOALS** — monthly revenue goal per studio
2. **REP_GOALS** — monthly revenue goal per rep
3. **DAILY_FCST** — daily forecast breakdown for the new month

**Where the numbers come from:**
- Studio goals + rep goals → Google Sheet: `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` (tab: "for claude")
- Daily forecast → Google Sheet: `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` (tab: "For claude_add each month")

Matthew: you're already updating these Google Sheets as part of your normal job — just add the July tab in the same format as June and the data will be ready to copy into the script.

### How to update the script

Open the script in any text editor (or in Claude Code):
```
scripts/run_from_mcp.py
```

**Find `DAILY_FCST` (~line 437).** Replace the June dates/values with July's. Format is `"YYYY-MM-DD": amount`. Example for July:
```python
DAILY_FCST = {
    "2026-07-01": 180_000, "2026-07-02": 390_000, "2026-07-03": 70_000,
    # ... one entry per day in July
}
FULL_MO_FCST = 5_200_000   # total July forecast from Google Sheet
```

**Find `STUDIO_GOALS` (~line 449).** Update each studio's number with July's goal:
```python
STUDIO_GOALS = {
    "Baltimore":     260_000,
    "Boston":        470_000,
    # ... etc
}
```

**Find `REP_GOALS` (~line 458).** Update each rep's goal number (third value in the tuple). The name and studio don't change — only the number:
```python
REP_GOALS = {
    "ashanti.gillespie": ("Ashanti Gillespie", "Baltimore", 85_000),  # ← update this number
    # ...
}
```

### Run the script to verify

```bash
cd id-daily-business-review
source venv/bin/activate
python scripts/run_from_mcp.py
```

Open `output/report.html` in a browser to spot-check the pacing table. Goals and forecast should reflect July numbers.

### Push your changes to GitHub

```bash
git add scripts/run_from_mcp.py
git commit -m "update: July 2026 studio goals, rep goals, and daily forecast"
git push
```

---

## PART 3 — If the Monday Report Doesn't Arrive

Check Slack first — the report posts to havenlyteam.slack.com. If it's not there by 9am CT, follow these steps.

### Step 1: Check the routine

Go to: https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5

Make sure it's enabled. If it failed, you'll see an error log there.

### Step 2: Run it manually

In Claude Code (with the repo folder open), type:
```
/id-monday-report run
```

Or open a conversation in Claude Code and say: **"run the ID Monday report for today"**

The skill will guide Claude through:
1. Pulling fresh data from Snowflake
2. Fetching HubSpot deal data
3. Generating the 2-tab HTML report + PDF
4. Posting to Slack

### Step 3: If you need to run the Python script directly

```bash
cd id-daily-business-review
source venv/bin/activate
python scripts/run_from_mcp.py
```

This generates `output/report.html`. Open it in Chrome to review.

To generate the PDF:
```bash
python - <<'EOF'
import asyncio, pathlib
from playwright.async_api import async_playwright

REPO = pathlib.Path.cwd()
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
EOF
```

---

## PART 4 — If a Number Looks Wrong

**Tab 1 (Total Business) must always match Looker dashboard 1156:**
https://havenly.looker.com/dashboards/1156

**Tab 2 (Sales Team) must always match HubSpot dashboard.**

All data values are hardcoded variables at the top of `scripts/run_from_mcp.py` (lines ~180–470). To fix a wrong number:

1. Find the variable (search for the metric name — e.g. `MTD_TOT_REV`, `YD_BLENDED_AOV`)
2. Update it to match the Looker or HubSpot dashboard value
3. Re-run `python scripts/run_from_mcp.py`
4. Check `output/report.html` in browser
5. Push to GitHub

**Critical rule: never change the methodology — only update the values. The formulas and data sources are documented in `docs/data-methodology.md`.**

---

## PART 5 — Adding a New Rep

If a new rep joins and shows $0 in the pacing table, add them to `REP_GOALS` in the script:

```python
"first.last": ("Full Name", "Studio Name", goal_amount),
```

The key is their email prefix — e.g. for `jane.doe@interiordefine.com`, use `"jane.doe"`.

---

## Key Links

| What | Link |
|---|---|
| GitHub repo | https://github.com/maryspreck-star/id-daily-business-review |
| Automated routine | https://claude.ai/code/routines/trig_01RswSW7MsvW5ZGDdvKMhqB5 |
| Looker dashboard (Tab 1 source of truth) | https://havenly.looker.com/dashboards/1156 |
| Goals Google Sheet | `1CkbEVt9utgqkO4xbCnxpc1A6tJCTTRaXWo_iQZQiyJw` |
| Forecast Google Sheet | `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` |
| Methodology doc | `docs/data-methodology.md` in the repo |
| Script | `scripts/run_from_mcp.py` in the repo |

---

## DST Note (November)

When clocks fall back in November, update the routine cron from `0 13 * * 1` to `0 14 * * 1` at the routine URL above so it continues to fire at 8am CT.

---

## Questions?

If you're stuck, open a conversation in Claude Code and describe what's wrong. Claude has access to all the data sources and methodology and can walk you through a fix. The methodology doc (`docs/data-methodology.md`) explains every single metric and where it comes from.
