# Daily Business Review — Synthesis & Delivery Design

**Status:** Approved  
**Date:** 2026-06-07

## What This Builds

The remaining pipeline after the Snowflake data layer: deal/CVR metrics, Slack closing notes, Claude-generated narrative, HTML email assembly, and scheduled delivery.

## Data Flow

```
fetch_all()          → Snowflake: revenue, AOV, engagements, swatches, merch, studios
fetch_deals()        → Snowflake STG_DEAL: inbound count, CVR, by-studio, by-rep
fetch_slack_notes()  → Slack API: last 24h of #id-retail-closing-notes

All three → synthesize(data) → {tldr, yesterday_story, watch_items} as HTML strings
All data + synthesis → render(data, narrative) → complete HTML email string
HTML string → send(html) → SendGrid → mary.spreck@interiordefine.com
```

## Components

### src/collectors/deals.py

Queries `PROD.ID_WAREHOUSE.STG_DEAL`. Key columns already pre-calculated:
- `MEANINGFUL_CONTACT` — whether the deal had a meaningful contact
- `14_DAY_CONVERTED`, `IS_CONVERTED` — conversion flags
- `INBOUND_ENGAGEMENTS` — engagement count on the deal
- `DEAL_AMOUNT` — deal value
- `DEAL_OWNER_EMAIL`, `STUDIO_NAME` — rep and studio attribution
- `CREATE_DATE` — inbound date (Denver timezone)

Returns a dict matching the existing data contract:
```python
{
  "inbound_mtd": int,               # total B2C+Trade deals created this month
  "inbound_yesterday": int,         # deals created yesterday
  "cvr_14day_mtd": float,           # 14-day CVR for MTD inbound cohort
  "cvr_meaningful_mtd": float,      # meaningful contact CVR MTD
  "by_studio": list[dict],          # [{studio, inbound, closed_won, cvr}, ...]
  "by_rep": list[dict],             # [{name, email, inbound, closed_won, cvr}, ...]
}
```

Filter: exclude `@interiordefine.com` deal owner emails. Exclude swatch-only deals.

### src/collectors/slack_notes.py

Reads the last 24h of messages from #id-retail-closing-notes using the Slack Web API (`conversations.history`). The SLACK_BOT_TOKEN is already in `.env`.

Returns:
```python
{
  "channel": "#id-retail-closing-notes",
  "messages": list[str],   # raw message text, last 24h, newest first
  "date": date,
}
```

If the channel has no messages or the token lacks access, returns empty messages list (non-fatal).

### src/synthesizer.py

Single function `synthesize(data: dict) -> dict` that calls Claude API (`claude-sonnet-4-6`) with the full data payload and returns three HTML snippet strings:

```python
{
  "tldr": str,            # 1-2 sentence HTML summary for the blue TL;DR box
  "yesterday_story": str, # 2-3 sentence HTML prose about yesterday's performance
  "watch_items": list[dict],  # [{tag: str, text: str}, ...] for the amber watch section
}
```

Prompt includes:
- Full data dict as JSON
- Slack closing notes (if any)
- Whether it's Monday mode
- Instructions: be specific with numbers, flag anomalies, surface actionable items

Monday mode adds a last-week recap section to the output.

Uses prompt caching (system prompt cached) to reduce cost on repeated runs.

### src/renderer.py

Function `render(data: dict, narrative: dict, is_monday: bool) -> str` that builds the full two-tab HTML email as a Python string.

Uses the existing mockup ([id-email-template-two-tabs.html](../../id-email-template-two-tabs.html)) as the style reference. Builds the HTML programmatically using f-strings — no template engine needed. Reuses the CSS verbatim from the mockup (extracted as a constant).

Tab 1 — Total Business: revenue KPIs, segment mix bars, merch mix, swatch performance, studio breakdown, engagements chart, marketing spend placeholder.

Tab 2 — Sales Team: TL;DR (from synthesizer), yesterday's story (from synthesizer), watch items (from synthesizer), CVR trend, rep performance tables.

Monday additions (Tab 2 only): last-week recap section, weekly engagement chart.

### src/email_sender.py

Function `send(html: str, subject: str)` using SendGrid Python SDK.

- `EMAIL_TO`: mary.spreck@interiordefine.com  
- `EMAIL_FROM`: reports@interiordefine.com (or configurable via env var)
- `SENDGRID_API_KEY`: from `.env`

Subject line: `Interior Define Daily Review — {date} {'(Monday Mode)' if monday else ''}`

### src/main.py

Entry point. Detects Monday via `datetime.date.today().weekday() == 0`.

```python
def main():
    is_monday = datetime.date.today().weekday() == 0
    data = {
        **fetch_all(),
        "deals": fetch_deals(),
        "slack_notes": fetch_slack_notes(),
    }
    narrative = synthesize(data, is_monday=is_monday)
    html = render(data, narrative, is_monday=is_monday)
    subject = build_subject(is_monday)
    send(html, subject)
```

Errors in individual collectors are caught and logged; a missing data source produces a "data unavailable" placeholder rather than crashing the run.

### .github/workflows/daily-report.yml

```yaml
schedule:
  - cron: '0 13 * * 1-5'   # 7am MDT (UTC-6); runs at 8am in winter (MST)
```

Secrets required: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_WAREHOUSE`, `SLACK_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `SENDGRID_API_KEY`, `EMAIL_TO`, `EMAIL_FROM`.

## Requirements Changes

New additions to `requirements.txt`:
```
anthropic==0.40.0
sendgrid==6.11.0
slack-sdk==3.33.0
```

## Monday vs Daily Mode

| Section | Daily | Monday |
|---|---|---|
| Tab 1 | Full Total Business | Full Total Business |
| Tab 2 TL;DR | Yesterday summary | LW + yesterday summary |
| Tab 2 engagements | Yesterday + 4-week rolling | Yesterday + weekly trend |
| Tab 2 Monday Recap | Hidden | Visible (LW NBE, LW AOV, LW inbound) |
| Synthesizer prompt | Daily mode | Monday mode (adds LW context) |
