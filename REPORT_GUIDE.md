# ID Daily Business Review — How It Works

This guide covers every data source, calculation, and configuration point so the report can be maintained or replicated by anyone on the team.

---

## What It Does

Every weekday at **8am CT**, a GitHub Actions workflow:
1. Pulls data from **Looker**, **HubSpot**, and a **Google Sheet**
2. Generates a two-tab HTML report
3. Publishes it to **GitHub Pages**
4. Posts a summary link to **Slack** (`#salesoperations`)

Live report: https://maryspreck-star.github.io/id-daily-business-review/

---

## Repository Structure

```
id-daily-business-review/
├── report.py                    # Main pipeline: fetches data, builds data.json
├── scripts/
│   └── generate_report.py      # Reads data.json, renders the HTML report
├── requirements.txt             # Python dependencies (requests)
├── .github/workflows/main.yml  # GitHub Actions schedule + Slack trigger
└── docs/
    └── index.html              # Published report (auto-generated, do not edit)
```

---

## Schedule & Trigger

File: [.github/workflows/main.yml](.github/workflows/main.yml)

```yaml
on:
  schedule:
    - cron: '0 13 * * 1-5'   # 8am CDT = 1pm UTC, Mon–Fri
  workflow_dispatch:           # manual trigger via GitHub Actions UI
```

- **Scheduled runs** post to Slack automatically.
- **Manual runs** (via "Run workflow" button) generate and publish the report but **do not post to Slack**. Use these to refresh data mid-day or test changes.

---

## Environment Variables (GitHub Secrets)

Set in **Settings → Secrets and variables → Actions** on the repo.

| Secret | What it is |
|--------|-----------|
| `LOOKER_BASE_URL` | Looker instance URL, e.g. `https://havenly.looker.com` |
| `LOOKER_CLIENT_ID` | Looker API client ID |
| `LOOKER_CLIENT_SECRET` | Looker API client secret |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL for `#salesoperations` (outbound posts only) |
| `SLACK_READ_TOKEN` | Slack Bot Token (`xoxb-...`) to read `#id--retail-closing-notes` — see setup below |
| `ID_HUBSPOT_TOKEN` | HubSpot Private App token for Interior Define's account |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions — do not add manually |

---

## Slack Bot Setup (Closing Notes)

The closing notes section pulls yesterday's posts from `#id--retail-closing-notes` (channel ID `C08MYB2S3DH`). This requires a **Slack Bot Token** — not the outbound webhook used for Slack posting.

### Steps to set up

1. Go to **https://api.slack.com/apps** and create a new app (or use an existing one)
2. Under **OAuth & Permissions → Scopes → Bot Token Scopes**, add:
   - `channels:history` — read messages in public channels
   - `groups:history` — read messages in private channels
   - `channels:read` — list channels (for diagnostics)
3. Click **Install to Workspace** and copy the **Bot User OAuth Token** (starts with `xoxb-`)
4. In Slack, open `#id--retail-closing-notes` and type `/invite @<your-bot-name>` — the bot must be a member of the channel to read it
5. Add the token as `SLACK_READ_TOKEN` in the GitHub repo secrets

### Troubleshooting

Run a manual workflow and check the Actions log. The report now prints specific error messages:

| Log message | Fix |
|-------------|-----|
| `SLACK_READ_TOKEN not set` | Add the secret to GitHub repo settings |
| `channel_not_found` | Invite the bot to `#id--retail-closing-notes` with `/invite @<bot>` |
| `missing_scope` | Re-install the Slack app with `channels:history` and `groups:history` scopes |
| `invalid_auth` | Token is expired or revoked — regenerate from api.slack.com |
| `no messages in window` | No posts were made in the channel for that day — expected on low-activity days |

### How the time window works

The closing notes window is **midnight CT on yesterday** through **8am CT the following morning**. This means late posts (e.g. SF posting at 1am CT) are captured under the correct business day.

---

## Date Definitions

All dates are computed in **America/Chicago** timezone and reference "yesterday" as the primary reporting date (since the report runs at 8am, the full prior business day is available).

| Key | Meaning |
|-----|---------|
| `yd` | Yesterday (primary reporting date) |
| `lw_start / lw_end` | 7-day window ending on yesterday (e.g. Jun 26–Jul 2) |
| `mtd_start` | First day of the current month |
| `ly_*` | Same period one year prior |

---

## Tab 1: Total Business

**All data comes from Looker** (`interior_define` model). No HubSpot or Snowflake data is used here.

### Looker Explores Used

| Section | Explore | Key Fields |
|---------|---------|-----------|
| Revenue by segment | `orders` | `orders.md_order_revenue`, `orders.order_count` |
| AOV | `orders` | `orders.average_order_value` |
| Assisted % | `orders` | `hubspot_deals.has_meaningful_contact` |
| Inbound engagements | `hubspot_contacts` | `hubspot_contacts.number_of_contacts` |
| Studio MTD breakdown | `orders` | `hubspot_deals.studio_name`, revenue + orders |
| Swatch orders | `swatch_orders` | count + distinct customers |
| Studio CVR | `hubspot_contacts` | contacts + `all_converted_count` |
| Monthly CVR trend | `hubspot_contacts` | 14/30/60/90-day conversion rates |
| Forecast (v-plan) | `orders` (join: `sales_forecast`) | `sales_forecast.ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS` |

### Revenue Segments

Looker returns revenue broken out by customer class: `B2C`, `Trade`, `Havenly`, and `B2B`. These roll up to a single total for each time period.

### Forecast

The YD / LW / MTD "vs plan" tiles use **Looker's `sales_forecast`** (`ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS`). The forecast is queried from `lw_start` through the end of the current month, then summed per period.

### Filters Applied

- **Studios excluded:** `Assisted No Studio`, `Automated DE`, `Santa Monica`
- **CVR and inbound:** excludes `The Inside`, `Burrow`, `General Managers`, `Remote Sales`
- **Customer group for CVR/inbound:** B2C only

---

## Tab 2: Sales Team

**All data comes from HubSpot API and the Google Sheet.** No Looker data is used here.

### Data Sources

| Section | Source |
|---------|--------|
| MTD / YD / LW Net Sales | HubSpot CRM API — Closed Won deals |
| Studio breakdown (MTD) | HubSpot CRM API |
| Rep-level actuals | HubSpot CRM API |
| Team & individual pacing % | Computed from HubSpot actuals ÷ Google Sheet forecast |
| Activities (calls/meetings) | HubSpot CRM API — calls + meetings objects |
| Closing notes | Slack channel `#id--retail-closing-notes` |

### HubSpot Deal Filters

**TY (This Year):**
- `hs_is_closed_won = true`
- `closedate` in range (UTC epoch milliseconds)
- `meaningful_contact_ = true`

**LY (Last Year):**
- `hs_is_closed_won = true`
- `closedate` in range
- No meaningful contact filter (used as approximation)

> **Important timezone note:** HubSpot stores `closedate` as **midnight UTC** of the date the rep entered. All closedate filters use UTC timestamps (`_ms()` / `_ms_eod()`). Do not convert to CT — that would shift the filter window and miss deals.

### Studio Attribution

HubSpot deals return a `hubspot_team` property. When that field is blank on a deal, the code falls back to the owner's email prefix matched against the `_DE_EMAIL_STUDIO` mapping in `report.py`. This mapping covers all 47 Design Experts and SDEs across 13 studios.

### Forecast & Pacing

**Source:** Google Sheet `ID RETAIL DAILY SALES_MC`, tab `for claude_add each month`  
**Sheet ID:** `1lJcsmRhG3ScG8s2ol2jPwUBJ18n20MMn101rXc1ZQp0` (gid=910871961)  
**Sharing:** Must be set to "Anyone with the link can view"

The sheet must have:
- A column with daily dates in `M/D/YYYY` format
- A column whose header contains the word "forecast" (case-insensitive)
- Daily rows for every day of each month (the code loads all months present in the sheet)

**Pacing % calculation:**
```
MTD_SALES_FCST = sum of forecast for all days from month start through yesterday
PACING_PCT     = MTD_SALES_FCST / FULL_MO_FCST
paced_goal     = monthly_goal × PACING_PCT
pct_paced      = actual_MTD / paced_goal
```

### Activities

Calls and meetings are fetched from HubSpot's CRM objects API (`/crm/v3/objects/calls` and `/crm/v3/objects/meetings`) filtered by `hs_createdate` for the MTD window. Each activity is attributed to a studio via the owner's email prefix.

> Email read scope is **not** enabled on the current HubSpot Private App, so email activity counts will always be 0. Add the `crm.objects.emails.read` scope to the app in HubSpot settings if you want email counts.

---

## Updating Goals

### Studio Monthly Goals

Edit the `STUDIO_GOALS` dict in [scripts/generate_report.py](scripts/generate_report.py):

```python
STUDIO_GOALS = {
    "Baltimore":     264_000,
    "Boston":        476_000,
    # ... one entry per studio
}
```

### Individual Rep Goals

Edit the `REP_GOALS` dict in the same file:

```python
REP_GOALS = {
    "email.prefix": ("Display Name", "Studio", monthly_goal),
    # e.g.:
    "brynn.cohune": ("Brynn Cohune", "Boston", 113_000),
}
```

- **Key** = email prefix (part before `@interiordefine.com`)
- **Display Name** = must match the rep's `firstName + ' ' + lastName` in HubSpot exactly (this is how actuals are matched to goals)
- **Goal** = monthly dollar goal

### Adding a New Rep

1. Add them to `REP_GOALS` in `scripts/generate_report.py`
2. Add them to `_DE_EMAIL_STUDIO` in `report.py` (for activity attribution)
3. Both use the same email prefix format

### Removing a Rep

Delete their entry from both dicts. If a rep has no goal entry, they still appear in the Top 5 MTD bar chart if they had deals, but won't appear in the individual pacing table.

---

## Month-End / New Month Setup

1. **Add the new month's daily forecast rows** to the Google Sheet tab `for claude_add each month`. Dates must be in `M/D/YYYY` format. The sheet is shared — anyone with the link can view.
2. **Update `STUDIO_GOALS` and `REP_GOALS`** in `scripts/generate_report.py` if goals change.
3. No other changes are needed — the report auto-detects the current month.

---

## HubSpot Private App Scopes Required

The token in `ID_HUBSPOT_TOKEN` needs these CRM read scopes:

- `crm.objects.deals.read`
- `crm.objects.owners.read`
- `crm.objects.calls.read`
- `crm.objects.meetings.read`
- `crm.objects.emails.read` _(optional — for email activity counts)_

---

## How the Pipeline Runs

```
GitHub Actions (cron 8am CT)
        │
        ▼
report.py
  ├── Looker API  ──────────────────────► revenue, AOV, CVR, forecast → Total Business
  ├── Google Sheet CSV ─────────────────► daily forecast → Sales Team pacing
  ├── HubSpot CRM API
  │     ├── /crm/v3/owners ────────────► owner_id → name + email prefix
  │     ├── /crm/v3/objects/deals/search → MTD/LW/YD revenue, rep actuals, studio rev
  │     ├── /crm/v3/objects/calls/search → call activity counts by studio
  │     └── /crm/v3/objects/meetings/search → meeting activity counts
  └── Slack API ────────────────────────► #id--retail-closing-notes (yesterday's notes)
        │
        ▼
  /tmp/id/data.json  (intermediate)
        │
        ▼
scripts/generate_report.py
        │
        ▼
  /tmp/id/report.html
        │
        ▼
  git commit → docs/index.html  (GitHub Pages)
        │
        ▼
  Slack webhook → #salesoperations  (scheduled runs only)
```

---

## Known Quirks

**HubSpot rate limits:** The HubSpot API has a per-second rate limit. If two workflow runs fire simultaneously (e.g. a double-trigger), both will get 429 errors. The code retries with exponential backoff (1→2→4→8s). To avoid this, don't manually trigger a run at exactly 8am CT.

**MC% (Meaningful Contact %) chart:** This chart can show empty at the very start of a month when there are too few deals to populate by studio. It falls back to the last 30 days automatically.

**LW spanning two months:** In the first 6 days of any month, last week spans two calendar months. The Looker forecast query extends back to `lw_start` to cover the full 7-day window. The Google Sheet forecast loads all months present in the sheet, so both tabs show a correct 7-day forecast comparison.

**Closing notes:** The Slack window is midnight CT through 8am CT the following morning, so late posts (e.g. SF posting after midnight) still appear under the correct date. If the section shows blank, check the Actions log for a specific error message — see the Slack Bot Setup section above.

---

## Making Edits with Claude Code

Anyone on the team can edit this report using Claude Code — no need to write Python manually.

### Setup (one time)

1. **Get repo access** — ask Mary to add you as a collaborator in **GitHub → Settings → Collaborators**
2. **Clone the repo** locally:
   ```bash
   git clone https://github.com/maryspreck-star/id-daily-business-review
   cd id-daily-business-review
   ```
3. **Open Claude Code** in that folder:
   - Terminal: run `claude` from inside the folder
   - VS Code: open the folder, then open the Claude panel

### Making a change

Just describe what you want in plain English. Examples:

> "Update Boston's monthly goal to $500K"

> "Add a new rep: jane.smith in Chicago, goal $120K, display name Jane Smith"

> "Remove rachel.roth from Seattle — she left the team"

> "The MTD revenue tile is showing the wrong number — can you investigate?"

Claude will read the relevant files, make the edit, and show you a diff to review. Once you're happy, push it:

```bash
git push
```

The next scheduled 8am CT run will use the updated code automatically. You can also trigger an immediate refresh via the **Run workflow** button on the [Actions page](https://github.com/maryspreck-star/id-daily-business-review/actions/workflows/main.yml) (manual runs don't post to Slack).

### What you can safely edit

| Task | File |
|------|------|
| Studio monthly goals | `scripts/generate_report.py` → `STUDIO_GOALS` |
| Rep goals + display names | `scripts/generate_report.py` → `REP_GOALS` |
| Add/remove reps | `scripts/generate_report.py` → `REP_GOALS` + `report.py` → `_DE_EMAIL_STUDIO` |
| New month forecast source | Update Google Sheet (no code change needed) |
| Report layout / styling | `scripts/generate_report.py` |
| Data sources / filters | `report.py` |

### What you don't need to touch

GitHub secrets (Looker credentials, HubSpot token, Slack tokens) live only in the repo's GitHub Actions settings and never appear in the code. Team members can edit and push code without ever seeing them.

---

## Replicating for Another Brand

1. Fork the repo
2. Replace all secrets with the new brand's credentials
3. Update `STUDIO_GOALS`, `REP_GOALS`, and `_DE_EMAIL_STUDIO` in the two Python files
4. Update `FORECAST_CSV_URL` to point to the new brand's Google Sheet
5. Update `STUDIO_EXCLUDE` if different studios should be filtered
6. Update the `GITHUB_REPO` and `PAGE_URL` constants in `report.py`
7. Enable GitHub Pages on the new repo (`Settings → Pages → Deploy from branch: main, /docs`)
8. Add all secrets to the new repo's Settings
9. Create a new Slack Bot and add `SLACK_READ_TOKEN` for closing notes (see Slack Bot Setup above)
