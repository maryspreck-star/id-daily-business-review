# Daily Business Review — Synthesis & Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything after the Snowflake data layer — deals/CVR collector, Slack closing notes, Claude narrative synthesis, HTML email renderer, SendGrid delivery, main orchestrator, and GitHub Actions cron.

**Architecture:** `fetch_all()` + `fetch_deals()` + `fetch_slack_notes()` feed a Claude API synthesizer that writes narrative HTML snippets; a renderer assembles those snippets plus the data into a two-tab HTML email; SendGrid delivers it to your inbox at 7am MT weekdays. Monday mode adds a last-week recap section.

**Tech Stack:** Python 3.14, `anthropic==0.40.0`, `sendgrid==6.11.0`, `slack-sdk==3.33.0`, `pytest`, existing `snowflake-connector-python` + `pandas` + `python-dotenv`

---

## File map

| File | Purpose |
|---|---|
| `requirements.txt` | Add anthropic, sendgrid, slack-sdk |
| `src/collectors/deals.py` | Snowflake queries against STG_DEAL for CVR/inbound metrics |
| `src/collectors/slack_notes.py` | Read last 24h of #id--retail-closing-notes |
| `src/synthesizer.py` | Call Claude API → return tldr/story/watch_items as HTML strings |
| `src/renderer.py` | Build complete two-tab HTML email from data + narrative |
| `src/email_sender.py` | Send via SendGrid |
| `src/main.py` | Orchestrate all pieces, detect Monday mode |
| `.github/workflows/daily-report.yml` | Cron at 7am MT weekdays |
| `tests/test_deals.py` | deals.py unit tests (mocked _query) |
| `tests/test_slack_notes.py` | slack_notes.py tests (mocked Slack SDK) |
| `tests/test_synthesizer.py` | synthesizer.py tests (mocked anthropic) |
| `tests/test_renderer.py` | renderer.py tests (assert key values in output HTML) |
| `tests/test_email_sender.py` | email_sender.py tests (mocked SendGrid) |
| `tests/test_main.py` | main.py integration test (all dependencies mocked) |

---

## Task 1: Dependencies and .env

**Files:**
- Modify: `requirements.txt`
- Modify: `.env` (add missing keys)
- Modify: `.env.example`

- [ ] **Step 1: Update requirements.txt**

Replace the contents of `requirements.txt` with:
```
snowflake-connector-python==3.12.4
pandas==2.2.3
python-dotenv==1.0.1
pytest==8.3.5
anthropic==0.40.0
sendgrid==6.11.0
slack-sdk==3.33.0
```

- [ ] **Step 2: Install new dependencies**

```bash
cd /Users/mc.spreck/mary-claire-daily-business-review
source venv/bin/activate
pip install -r requirements.txt
```

Expected: installs `anthropic`, `sendgrid`, `slack-sdk` without errors.

- [ ] **Step 3: Add missing keys to .env.example**

Append to `.env.example`:
```
ANTHROPIC_API_KEY=your_anthropic_api_key
SENDGRID_API_KEY=your_sendgrid_api_key
EMAIL_TO=mary.spreck@interiordefine.com
EMAIL_FROM=reports@interiordefine.com
```

- [ ] **Step 4: Add missing keys to .env**

Add the same four keys to `.env` with real values. ANTHROPIC_API_KEY can be found at console.anthropic.com. SENDGRID_API_KEY from SendGrid dashboard.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add anthropic, sendgrid, slack-sdk dependencies"
```

---

## Task 2: HubSpot deals collector

**Files:**
- Create: `src/collectors/deals.py`
- Create: `tests/test_deals.py`

Queries `PROD.ID_WAREHOUSE.STG_DEAL`. Key pre-calculated columns: `IS_CONVERTED` (1=closed won), `"14_DAY_CONVERTED"` (note: must be quoted in SQL — starts with digit), `MEANINGFUL_CONTACT`, `CREATE_DATE`, `DEAL_OWNER_EMAIL`, `STUDIO_NAME`, `DEAL_AMOUNT`.

Excludes internal staff (`@interiordefine.com`) and applies Denver timezone to `CREATE_DATE`.

- [ ] **Step 1: Create tests/test_deals.py with failing tests**

```python
import datetime
import pandas as pd
import pytest
from unittest.mock import patch


def test_fetch_deals_returns_required_keys():
    """fetch_deals() returns all required top-level keys."""
    from src.collectors.deals import fetch_deals

    overview_df = pd.DataFrame([{
        "inbound_total": 210, "closed_won": 28,
        "mature_cohort": 180, "mature_14day_converted": 22,
        "meaningful_total": 95, "meaningful_converted": 18,
        "inbound_yesterday": 12,
    }])
    studio_df = pd.DataFrame([
        {"studio_name": "Website", "inbound": 120, "closed_won": 18},
        {"studio_name": "CHI-Armitage", "inbound": 15, "closed_won": 3},
    ])
    rep_df = pd.DataFrame([
        {"rep": "alice@interiordefine.com", "inbound": 42, "closed_won": 8},
    ])

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        if call_count == 1: return overview_df
        if call_count == 2: return studio_df
        return rep_df

    with patch("src.collectors.deals._query", side_effect=mock_query):
        result = fetch_deals()

    assert "inbound_mtd" in result
    assert "inbound_yesterday" in result
    assert "cvr_14day_mtd" in result
    assert "cvr_meaningful_mtd" in result
    assert "by_studio" in result
    assert "by_rep" in result


def test_fetch_deals_cvr_calculation():
    """fetch_deals() computes 14-day and meaningful CVR correctly."""
    from src.collectors.deals import fetch_deals

    overview_df = pd.DataFrame([{
        "inbound_total": 100, "closed_won": 15,
        "mature_cohort": 80, "mature_14day_converted": 12,
        "meaningful_total": 60, "meaningful_converted": 9,
        "inbound_yesterday": 8,
    }])
    studio_df = pd.DataFrame([], columns=["studio_name", "inbound", "closed_won"])
    rep_df = pd.DataFrame([], columns=["rep", "inbound", "closed_won"])

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        if call_count == 1: return overview_df
        if call_count == 2: return studio_df
        return rep_df

    with patch("src.collectors.deals._query", side_effect=mock_query):
        result = fetch_deals()

    assert result["cvr_14day_mtd"]     == pytest.approx(12 / 80)
    assert result["cvr_meaningful_mtd"] == pytest.approx(9 / 60)
    assert result["inbound_mtd"]        == 100
    assert result["inbound_yesterday"]  == 8


def test_fetch_deals_zero_cohort():
    """fetch_deals() returns 0.0 CVR when cohort is empty (no mature deals yet)."""
    from src.collectors.deals import fetch_deals

    overview_df = pd.DataFrame([{
        "inbound_total": 5, "closed_won": 0,
        "mature_cohort": 0, "mature_14day_converted": 0,
        "meaningful_total": 0, "meaningful_converted": 0,
        "inbound_yesterday": 5,
    }])
    empty = pd.DataFrame([], columns=["studio_name", "inbound", "closed_won"])

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        if call_count == 1: return overview_df
        return empty

    with patch("src.collectors.deals._query", side_effect=mock_query):
        result = fetch_deals()

    assert result["cvr_14day_mtd"]     == 0.0
    assert result["cvr_meaningful_mtd"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/mc.spreck/mary-claire-daily-business-review
source venv/bin/activate
pytest tests/test_deals.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.collectors.deals'`

- [ ] **Step 3: Create src/collectors/deals.py**

```python
import datetime
from src.collectors.db import _query

_DENVER_NOW = "CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE"
_DEAL_DATE  = "CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(CREATE_DATE AS TIMESTAMP_NTZ))::DATE"
_STAFF_EXCL = "(DEAL_OWNER_EMAIL NOT LIKE '%@interiordefine.com%' OR DEAL_OWNER_EMAIL IS NULL)"


def fetch_deals() -> dict:
    """MTD deal/CVR metrics from STG_DEAL. Excludes staff-owned deals."""
    today      = datetime.date.today()
    yesterday  = today - datetime.timedelta(days=1)
    month_start = today.replace(day=1)
    mature_cutoff = today - datetime.timedelta(days=14)

    overview = _query(f"""
        SELECT
            COUNT(*)                                                                   AS inbound_total,
            SUM(IS_CONVERTED)                                                          AS closed_won,
            SUM(CASE WHEN {_DEAL_DATE} < '{mature_cutoff}' THEN 1 ELSE 0 END)         AS mature_cohort,
            SUM(CASE WHEN {_DEAL_DATE} < '{mature_cutoff}'
                          AND "14_DAY_CONVERTED" = 1 THEN 1 ELSE 0 END)               AS mature_14day_converted,
            SUM(CASE WHEN MEANINGFUL_CONTACT = 1 THEN 1 ELSE 0 END)                   AS meaningful_total,
            SUM(CASE WHEN MEANINGFUL_CONTACT = 1
                          AND IS_CONVERTED = 1 THEN 1 ELSE 0 END)                     AS meaningful_converted,
            SUM(CASE WHEN {_DEAL_DATE} = '{yesterday}' THEN 1 ELSE 0 END)             AS inbound_yesterday
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND {_STAFF_EXCL}
    """)

    by_studio = _query(f"""
        SELECT
            STUDIO_NAME                AS studio_name,
            COUNT(*)                   AS inbound,
            SUM(IS_CONVERTED)          AS closed_won
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND {_STAFF_EXCL}
          AND STUDIO_NAME IS NOT NULL
        GROUP BY STUDIO_NAME
        ORDER BY inbound DESC
    """)

    by_rep = _query(f"""
        SELECT
            DEAL_OWNER_EMAIL           AS rep,
            COUNT(*)                   AS inbound,
            SUM(IS_CONVERTED)          AS closed_won
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND DEAL_OWNER_EMAIL IS NOT NULL
          AND DEAL_OWNER_EMAIL NOT LIKE '%@interiordefine.com%'
        GROUP BY DEAL_OWNER_EMAIL
        ORDER BY inbound DESC
        LIMIT 20
    """)

    row = overview.iloc[0]
    mature   = int(row["mature_cohort"])
    meaningful = int(row["meaningful_total"])

    def _studio_list(df):
        return [
            {
                "studio":     r["studio_name"],
                "inbound":    int(r["inbound"]),
                "closed_won": int(r["closed_won"]),
                "cvr":        int(r["closed_won"]) / int(r["inbound"]) if int(r["inbound"]) else 0.0,
            }
            for _, r in df.iterrows()
        ]

    def _rep_list(df):
        return [
            {
                "rep":        r["rep"],
                "inbound":    int(r["inbound"]),
                "closed_won": int(r["closed_won"]),
                "cvr":        int(r["closed_won"]) / int(r["inbound"]) if int(r["inbound"]) else 0.0,
            }
            for _, r in df.iterrows()
        ]

    return {
        "inbound_mtd":       int(row["inbound_total"]),
        "inbound_yesterday": int(row["inbound_yesterday"]),
        "cvr_14day_mtd":     int(row["mature_14day_converted"]) / mature if mature else 0.0,
        "cvr_meaningful_mtd": int(row["meaningful_converted"]) / meaningful if meaningful else 0.0,
        "by_studio":         _studio_list(by_studio),
        "by_rep":            _rep_list(by_rep),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_deals.py -v
```

Expected: 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/collectors/deals.py tests/test_deals.py
git commit -m "feat: fetch_deals — MTD inbound, 14-day CVR, meaningful CVR, by-studio, by-rep"
```

---

## Task 3: Slack closing notes collector

**Files:**
- Create: `src/collectors/slack_notes.py`
- Create: `tests/test_slack_notes.py`

Channel: `#id--retail-closing-notes`, ID `C08MYB2S3DH`. Uses `slack-sdk`. Token from `SLACK_BOT_TOKEN` env var. Returns last 24h of messages as plain text strings. Non-fatal — returns empty list if channel unreachable.

- [ ] **Step 1: Create tests/test_slack_notes.py with failing tests**

```python
import datetime
import pytest
from unittest.mock import MagicMock, patch


def test_fetch_slack_notes_returns_message_texts():
    """fetch_slack_notes() returns list of message text strings."""
    from src.collectors.slack_notes import fetch_slack_notes

    mock_response = {
        "messages": [
            {"text": "Chicago had a strong day — closed 3 big Trade orders", "ts": "1749168000.000"},
            {"text": "NYC slow morning but picked up after noon", "ts": "1749164400.000"},
        ],
        "has_more": False,
    }

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = mock_response

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["channel"] == "#id--retail-closing-notes"
    assert len(result["messages"]) == 2
    assert "Chicago" in result["messages"][0]


def test_fetch_slack_notes_empty_channel():
    """fetch_slack_notes() returns empty messages list when channel has no messages."""
    from src.collectors.slack_notes import fetch_slack_notes

    mock_client = MagicMock()
    mock_client.conversations_history.return_value = {"messages": [], "has_more": False}

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["messages"] == []


def test_fetch_slack_notes_handles_api_error():
    """fetch_slack_notes() returns empty messages when Slack API fails (non-fatal)."""
    from src.collectors.slack_notes import fetch_slack_notes
    from slack_sdk.errors import SlackApiError

    mock_client = MagicMock()
    mock_client.conversations_history.side_effect = SlackApiError(
        "channel_not_found", {"error": "channel_not_found"}
    )

    with patch("src.collectors.slack_notes.WebClient", return_value=mock_client):
        result = fetch_slack_notes()

    assert result["messages"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_slack_notes.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.collectors.slack_notes'`

- [ ] **Step 3: Create src/collectors/slack_notes.py**

```python
import datetime
import os
import time
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

_CHANNEL_ID   = "C08MYB2S3DH"
_CHANNEL_NAME = "#id--retail-closing-notes"


def fetch_slack_notes() -> dict:
    """Read last 24h of messages from #id--retail-closing-notes. Non-fatal on error."""
    oldest = time.time() - 86400  # 24 hours ago

    try:
        client   = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        response = client.conversations_history(
            channel=_CHANNEL_ID,
            oldest=str(oldest),
            limit=50,
        )
        messages = [m["text"] for m in response["messages"] if m.get("text")]
    except (SlackApiError, KeyError):
        messages = []

    return {
        "channel":  _CHANNEL_NAME,
        "messages": messages,
        "date":     datetime.date.today(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_slack_notes.py -v
```

Expected: 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/collectors/slack_notes.py tests/test_slack_notes.py
git commit -m "feat: fetch_slack_notes — last 24h of #id--retail-closing-notes"
```

---

## Task 4: Claude synthesizer

**Files:**
- Create: `src/synthesizer.py`
- Create: `tests/test_synthesizer.py`

Calls `claude-sonnet-4-6` via Anthropic SDK. System prompt is cached. Returns a dict with `tldr`, `yesterday_story`, and `watch_items` as HTML strings. Uses JSON output mode for reliable parsing.

- [ ] **Step 1: Create tests/test_synthesizer.py with failing tests**

```python
import pytest
from unittest.mock import MagicMock, patch


_SAMPLE_DATA = {
    "report_date": "2026-06-06",
    "yesterday": {"revenue_total": 320000, "orders_total": 112, "aov_blended": 2857,
                  "revenue_b2c": 235000, "revenue_trade": 72000, "revenue_havenly": 13000,
                  "assisted_pct": 0.67, "upt": 2.15},
    "mtd": {"revenue_total": 4200000, "revenue_total_ly": 4800000, "orders_total": 1480},
    "engagements": {"yesterday": 315, "yesterday_ly": 323, "weekly_rolling": []},
    "swatches": {"mtd_orders": 8200, "mtd_customers": 6900, "monthly_rolling": []},
}

_SAMPLE_OUTPUT = '{"tldr": "<p>Solid Friday.</p>", "yesterday_story": "<p>NBE <strong>$320K</strong>.</p>", "watch_items": [{"tag": "AOV", "text": "Soft at $2,718"}]}'


def test_synthesize_returns_required_keys():
    """synthesize() returns dict with tldr, yesterday_story, watch_items."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        result = synthesize(_SAMPLE_DATA)

    assert "tldr" in result
    assert "yesterday_story" in result
    assert "watch_items" in result
    assert isinstance(result["watch_items"], list)


def test_synthesize_monday_mode_passes_flag():
    """synthesize() includes Monday context in prompt when is_monday=True."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        synthesize(_SAMPLE_DATA, is_monday=True)

    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "Monday" in user_content or "monday" in user_content.lower()


def test_synthesize_passes_slack_notes():
    """synthesize() includes Slack notes in prompt when provided."""
    from src.synthesizer import synthesize

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_SAMPLE_OUTPUT)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    data_with_notes = {**_SAMPLE_DATA, "slack_notes": {"messages": ["Chicago closed 3 big ones"]}}

    with patch("src.synthesizer.anthropic.Anthropic", return_value=mock_client):
        synthesize(data_with_notes)

    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "Chicago" in user_content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_synthesizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.synthesizer'`

- [ ] **Step 3: Create src/synthesizer.py**

```python
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """You are writing the Interior Define Daily Business Review — a morning email that gives the GM a fast read on yesterday's performance and what to watch.

Output ONLY valid JSON with these exact keys:
- "tldr": 1-2 sentence HTML string (may use <strong>) summarizing the day vs expectations
- "yesterday_story": 2-4 sentence HTML prose about yesterday — be specific with numbers, highlight what drove performance
- "watch_items": array of {"tag": string, "text": string} objects — 2-3 items flagging anomalies or trends to monitor

Rules:
- Use actual numbers from the data (revenue, orders, AOV, CVR, engagements)
- Frame YoY comparisons when data is available (▲/▼ language)
- watch_items tags are short labels like "AOV", "CVR", "Trade", "Engagements"
- Do not make up data not present in the input
- Closing notes from Slack (if present) may surface qualitative context"""


def synthesize(data: dict, is_monday: bool = False) -> dict:
    """Call Claude API to generate narrative HTML snippets from the data dict."""
    client = anthropic.Anthropic()

    slack_notes = data.get("slack_notes", {}).get("messages", [])
    notes_section = ""
    if slack_notes:
        notes_section = "\n\nClosing notes from #id--retail-closing-notes:\n" + "\n".join(f"- {m}" for m in slack_notes[:10])

    monday_note = "\nThis is a MONDAY report — include last-week context in the tldr and yesterday_story.\n" if is_monday else ""

    user_content = (
        f"{monday_note}"
        f"Data (JSON):\n{json.dumps(data, indent=2, default=str)}"
        f"{notes_section}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
    )

    return json.loads(response.content[0].text)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_synthesizer.py -v
```

Expected: 3 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesizer — Claude API narrative for TL;DR, yesterday story, watch items"
```

---

## Task 5: HTML email renderer

**Files:**
- Create: `src/renderer.py`
- Create: `tests/test_renderer.py`

Builds the complete two-tab HTML email using Python f-strings. CSS is a constant extracted from the existing mockup. Helper functions produce reusable HTML components. The mockup at `id-email-template-two-tabs.html` is the style reference — match its visual design.

- [ ] **Step 1: Create tests/test_renderer.py with failing tests**

```python
import datetime
import pytest

_SAMPLE_DATA = {
    "report_date": datetime.date(2026, 6, 6),
    "yesterday": {
        "revenue_total": 320000.0, "revenue_b2c": 235000.0,
        "revenue_trade": 72000.0, "revenue_havenly": 13000.0,
        "orders_total": 112, "orders_b2c": 84, "orders_trade": 22, "orders_havenly": 6,
        "aov_blended": 2857.14, "aov_b2c": 2797.62, "aov_trade": 3272.73,
        "assisted_pct": 0.67, "upt": 2.15,
    },
    "mtd": {
        "revenue_total": 4_200_000.0, "revenue_b2c": 3_100_000.0,
        "revenue_trade": 820_000.0, "revenue_havenly": 280_000.0,
        "orders_total": 1480, "revenue_total_ly": 4_800_000.0, "orders_total_ly": 1690,
        "repeat_pct": 0.316,
    },
    "engagements": {"yesterday": 315, "yesterday_ly": 323, "weekly_rolling": [
        {"week_start": datetime.date(2026, 5, 11), "count": 285},
        {"week_start": datetime.date(2026, 5, 18), "count": 312},
        {"week_start": datetime.date(2026, 5, 25), "count": 298},
        {"week_start": datetime.date(2026, 6, 1), "count": 341},
    ]},
    "swatches": {"mtd_orders": 1718, "mtd_customers": 1492, "monthly_rolling": []},
    "merch_mix": {
        "product_contribution": [
            {"name": "Sectionals", "pct": 0.30},
            {"name": "Sofas", "pct": 0.22},
        ],
        "collection": [{"name": "Sloan", "pct": 0.14}],
        "fabric": [{"name": "Velvet", "pct": 0.54}],
    },
    "by_studio": [
        {"studio": "Website", "revenue": 955000.0, "orders": 344},
        {"studio": "BOS-Newbury", "revenue": 52000.0, "orders": 16},
    ],
    "deals": {
        "inbound_mtd": 320, "inbound_yesterday": 42,
        "cvr_14day_mtd": 0.138, "cvr_meaningful_mtd": 0.189,
        "by_studio": [], "by_rep": [],
    },
    "slack_notes": {"messages": [], "channel": "#id--retail-closing-notes"},
}

_SAMPLE_NARRATIVE = {
    "tldr": "<p>Strong Friday led by Trade activity. AOV slightly soft at $2,857.</p>",
    "yesterday_story": "<p>NBE <strong>$320K</strong> on 112 orders. Trade +18% vs LY.</p>",
    "watch_items": [{"tag": "AOV", "text": "Blended soft — sectional mix at 30%"}],
}


def test_render_returns_html_string():
    """render() returns a non-empty string starting with DOCTYPE."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html


def test_render_contains_both_tabs():
    """render() output contains both Total Business and Sales Team tab labels."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert "Total Business" in html
    assert "Sales Team" in html


def test_render_contains_revenue_total():
    """render() output contains the revenue total formatted as currency."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    # $320K or $320,000 — either format is acceptable
    assert "320" in html


def test_render_contains_narrative():
    """render() output contains the synthesizer TL;DR text."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert "Strong Friday" in html


def test_render_monday_mode_includes_recap():
    """render() Monday mode includes 'Last Week Recap' section."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE, is_monday=True)
    assert "Last Week" in html or "last week" in html.lower()


def test_render_non_monday_omits_recap():
    """render() non-Monday mode does not include the Monday recap section."""
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE, is_monday=False)
    # Monday recap section should be absent (or hidden)
    assert "Last Week Recap" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_renderer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.renderer'`

- [ ] **Step 3: Create src/renderer.py**

```python
import datetime


# ── Shared CSS (matches the mockup style) ──────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.tab-radio { display: none; }
.tab-bar { display: flex; background: #fff; border-bottom: 2px solid #e2e8f0; padding: 0 20px;
           position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.tab-bar label { padding: 14px 20px 12px; font-size: 14px; font-weight: 500; color: #64748b;
                 cursor: pointer; border-bottom: 3px solid transparent; margin-bottom: -2px; }
#tab-biz:checked ~ .tab-shell .tab-bar label[for="tab-biz"],
#tab-sales:checked ~ .tab-shell .tab-bar label[for="tab-sales"]
  { color: #6366f1; border-bottom-color: #6366f1; font-weight: 600; }
.tab-content { display: none; }
#tab-biz:checked ~ .tab-shell #content-biz { display: block; }
#tab-sales:checked ~ .tab-shell #content-sales { display: block; }
.page-label { text-align: center; font-size: 11px; font-weight: 700; text-transform: uppercase;
              letter-spacing: 2px; color: #94a3b8; margin: 24px 0 16px; }
.email-wrap { max-width: 680px; margin: 0 auto 48px; background: #fff; border-radius: 8px;
              overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,.10); }
.hdr { background: #0f172a; color: #f1f5f9; padding: 22px 28px; }
.hdr-brand { font-size: 18px; font-weight: 700; }
.hdr-meta { color: #94a3b8; font-size: 12px; margin-top: 5px; }
.hdr-badge { display: inline-block; background: #1e3a5f; color: #93c5fd; font-size: 10px;
             font-weight: 700; text-transform: uppercase; letter-spacing: 1px;
             padding: 2px 8px; border-radius: 3px; margin-left: 8px; }
.section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; }
.section-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 1.2px; color: #64748b; margin-bottom: 12px; }
.kpi-grid { display: flex; gap: 10px; margin-bottom: 14px; }
.kpi { flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 14px; }
.kpi-val { font-size: 20px; font-weight: 800; color: #0f172a; }
.kpi-lbl { font-size: 10px; color: #94a3b8; margin-top: 2px; text-transform: uppercase; }
.kpi-chg { font-size: 11px; font-weight: 600; margin-top: 4px; }
.up { color: #16a34a; } .dn { color: #dc2626; }
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; font-size: 11px; }
.bar-lbl { width: 110px; flex-shrink: 0; color: #475569; }
.bar-track { flex: 1; height: 7px; background: #f1f5f9; border-radius: 2px; max-width: 180px; }
.bar-fill { height: 100%; border-radius: 2px; }
.bar-val { width: 60px; text-align: right; color: #334155; font-weight: 600; }
.bar-pct { font-size: 10px; color: #94a3b8; width: 44px; }
.tldr { background: #eff6ff; border-left: 4px solid #2563eb; padding: 14px 20px; }
.tldr-label { font-size: 10px; font-weight: 800; text-transform: uppercase;
              letter-spacing: 1.5px; color: #1d4ed8; margin-bottom: 5px; }
.tldr p { font-size: 13px; color: #1e3a5f; line-height: 1.7; }
.prose { font-size: 13.5px; color: #1e293b; line-height: 1.85; }
.prose strong { color: #0f172a; }
.watch-section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; background: #fffbeb; }
.watch-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
               letter-spacing: 1.2px; color: #b45309; margin-bottom: 14px; }
.watch-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px;
              font-size: 13px; color: #1e293b; line-height: 1.7; }
.watch-tag { background: #fef3c7; border: 1px solid #fcd34d; border-radius: 4px;
             padding: 2px 8px; font-size: 10px; font-weight: 800; color: #92400e;
             white-space: nowrap; flex-shrink: 0; margin-top: 2px; }
.monday-section { padding: 22px 28px; border-bottom: 1px solid #e2e8f0; background: #f0f9ff; }
.monday-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                letter-spacing: 1.2px; color: #0369a1; margin-bottom: 12px; }
.note { font-size: 11px; color: #64748b; margin-top: 10px; line-height: 1.6; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { padding: 9px 12px; text-align: right; color: #475569; font-weight: 600;
     background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
th:first-child { text-align: left; }
td { padding: 9px 12px; text-align: right; border-bottom: 1px solid #f1f5f9; color: #334155; }
td:first-child { text-align: left; }
.footer { padding: 14px 28px; background: #f8fafc; text-align: center;
          font-size: 12px; color: #64748b; }
"""


# ── Formatting helpers ─────────────────────────────────────────────────────

def _currency(v: float) -> str:
    """Format dollar amount: $1.23M, $456K, $1,234."""
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _yoy(current: float, prior: float, positive_is_good: bool = True) -> str:
    if not prior:
        return ""
    delta = (current - prior) / prior
    arrow = "▲" if delta >= 0 else "▼"
    css   = "up" if (delta >= 0) == positive_is_good else "dn"
    return f'<span class="{css}">{arrow} {abs(delta)*100:.0f}%</span> vs {_currency(prior)} LY'


def _kpi(value: str, label: str, change: str = "", accent: str = "") -> str:
    style = f' style="border-left:3px solid {accent};"' if accent else ""
    chg   = f'<div class="kpi-chg">{change}</div>' if change else ""
    return f'<div class="kpi"{style}><div class="kpi-val">{value}</div><div class="kpi-lbl">{label}</div>{chg}</div>'


def _bar(label: str, value: str, pct: float, max_pct: float, color: str, pct_label: str = "") -> str:
    width = int(pct / max_pct * 100) if max_pct else 0
    pct_html = f'<span class="bar-pct">{pct_label}</span>' if pct_label else ""
    return (
        f'<div class="bar-row">'
        f'<span class="bar-lbl">{label}</span>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{width}%;background:{color};"></div></div>'
        f'<span class="bar-val">{value}</span>'
        f'{pct_html}'
        f'</div>'
    )


def _section(icon_label: str, content: str, extra_style: str = "") -> str:
    style = f' style="{extra_style}"' if extra_style else ""
    return (
        f'<div class="section"{style}>'
        f'<div class="section-label">{icon_label}</div>'
        f'{content}'
        f'</div>'
    )


# ── Tab 1: Total Business ──────────────────────────────────────────────────

def _render_total_business(data: dict) -> str:
    d   = data["yesterday"]
    mtd = data["mtd"]
    eng = data["engagements"]
    sw  = data["swatches"]
    mm  = data["merch_mix"]

    report_date = data["report_date"]
    date_str    = report_date.strftime("%b %-d, %Y") if hasattr(report_date, "strftime") else str(report_date)

    # Revenue KPIs
    rev_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_currency(d["revenue_total"]), "Yesterday Revenue",
               _yoy(d["revenue_total"], d["revenue_total"] * 0), "#0d9488")
        + _kpi(_currency(d["aov_blended"]), "Blended AOV")
        + _kpi(str(d["orders_total"]), "Orders")
        + '</div>'
        + '<div class="kpi-grid">'
        + _kpi(_currency(d["aov_b2c"]), "B2C AOV")
        + _kpi(_currency(d["aov_trade"]), "Trade AOV")
        + _kpi(_pct(d["assisted_pct"]), "Assisted Sales %")
        + '</div>'
    )

    # Revenue mix bars
    total_rev   = d["revenue_b2c"] + d["revenue_trade"] + d["revenue_havenly"]
    mix_bars    = ""
    for seg, rev, color in [
        ("B2C",     d["revenue_b2c"],     "#6366f1"),
        ("Trade",   d["revenue_trade"],   "#0d9488"),
        ("Havenly", d["revenue_havenly"], "#a78bfa"),
    ]:
        pct_val = rev / total_rev if total_rev else 0
        mix_bars += _bar(seg, _currency(rev), pct_val, 1.0, color, f"{pct_val*100:.1f}%")

    rev_section = _section("📈 Revenue — Yesterday", rev_kpis + mix_bars)

    # MTD KPIs
    mtd_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_currency(mtd["revenue_total"]), "MTD Revenue",
               _yoy(mtd["revenue_total"], mtd["revenue_total_ly"]))
        + _kpi(str(mtd["orders_total"]), "MTD Orders")
        + _kpi(_pct(mtd["repeat_pct"]), "Repeat Business")
        + '</div>'
    )
    mtd_section = _section("📊 MTD Performance", mtd_kpis)

    # Merch mix
    pc = mm.get("product_contribution", [])
    max_pc_pct = max((x["pct"] for x in pc), default=1)
    merch_bars = "".join(
        _bar(x["name"], _pct(x["pct"]), x["pct"], max_pc_pct, "#0d9488", _pct(x["pct"]))
        for x in pc[:6]
    )
    merch_section = _section("🛋 Product Contribution MTD", merch_bars)

    # Swatch MTD
    sw_kpis = (
        '<div class="kpi-grid">'
        + _kpi(f"{sw['mtd_orders']:,}", "Swatch Orders MTD")
        + _kpi(f"{sw['mtd_customers']:,}", "Unique Customers MTD")
        + '</div>'
    )
    sw_section = _section("🎨 Swatch Performance MTD", sw_kpis)

    # Engagements
    eng_yoy = _yoy(eng["yesterday"], eng["yesterday_ly"])
    eng_kpis = (
        '<div class="kpi-grid">'
        + _kpi(str(eng["yesterday"]), "Inbound Yesterday", eng_yoy)
        + _kpi(str(eng["yesterday_ly"]), "Same Day LY")
        + '</div>'
    )
    eng_section = _section("📞 Inbound Engagements", eng_kpis)

    # Studio table
    studios = data.get("by_studio", [])
    rows = "".join(
        f'<tr><td>{s["studio"]}</td><td>{_currency(s["revenue"])}</td><td>{s["orders"]}</td></tr>'
        for s in studios[:8]
    )
    studio_table = (
        '<table>'
        '<tr><th>Studio</th><th>Revenue MTD</th><th>Orders</th></tr>'
        + rows +
        '</table>'
    )
    studio_section = _section("🏬 Studio Performance MTD", studio_table)

    return f"""
<div class="page-label">Interior Define · Total Business · {date_str}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define <span class="hdr-badge">Total Business</span></div>
    <div class="hdr-meta">Daily Business Review · {date_str}</div>
  </div>
  {rev_section}
  {mtd_section}
  {merch_section}
  {sw_section}
  {eng_section}
  {studio_section}
  <div class="footer">Interior Define Daily Business Review — auto-generated</div>
</div>
"""


# ── Tab 2: Sales Team ──────────────────────────────────────────────────────

def _render_sales_team(data: dict, narrative: dict, is_monday: bool) -> str:
    d       = data["yesterday"]
    deals   = data.get("deals", {})
    report_date = data["report_date"]
    date_str    = report_date.strftime("%b %-d, %Y") if hasattr(report_date, "strftime") else str(report_date)
    day_name    = report_date.strftime("%A") if hasattr(report_date, "strftime") else ""

    # TL;DR
    tldr_html = (
        f'<div class="tldr">'
        f'<div class="tldr-label">TL;DR</div>'
        f'{narrative.get("tldr", "")}'
        f'</div>'
    )

    # Monday recap (conditional)
    monday_html = ""
    if is_monday:
        monday_html = (
            f'<div class="monday-section">'
            f'<div class="monday-label">📅 Last Week Recap</div>'
            f'<p class="prose">'
            f'Inbound engagements LW: <strong>{data["engagements"]["weekly_rolling"][-1]["count"] if data["engagements"]["weekly_rolling"] else "—"}</strong>. '
            f'MTD revenue: <strong>{_currency(data["mtd"]["revenue_total"])}</strong> '
            f'vs <strong>{_currency(data["mtd"]["revenue_total_ly"])}</strong> LY '
            f'({_yoy(data["mtd"]["revenue_total"], data["mtd"]["revenue_total_ly"])}).'
            f'</p>'
            f'</div>'
        )

    # Yesterday's story
    story_html = _section(
        f"📊 {day_name}'s Story" if day_name else "📊 Yesterday's Story",
        f'<p class="prose">{narrative.get("yesterday_story", "")}</p>'
    )

    # CVR metrics
    cvr_kpis = (
        '<div class="kpi-grid">'
        + _kpi(_pct(deals.get("cvr_14day_mtd", 0)), "14-Day CVR MTD")
        + _kpi(_pct(deals.get("cvr_meaningful_mtd", 0)), "Meaningful Contact CVR")
        + _kpi(str(deals.get("inbound_yesterday", 0)), "Inbound Yesterday")
        + '</div>'
    )
    cvr_section = _section("📈 Conversion Rates MTD", cvr_kpis)

    # Rep performance table
    reps   = deals.get("by_rep", [])[:10]
    rep_rows = "".join(
        f'<tr><td>{r["rep"].split("@")[0]}</td><td>{r["inbound"]}</td>'
        f'<td>{r["closed_won"]}</td><td>{_pct(r["cvr"])}</td></tr>'
        for r in reps
    )
    rep_table = (
        '<table>'
        '<tr><th>Rep</th><th>Inbound</th><th>Won</th><th>CVR</th></tr>'
        + rep_rows +
        '</table>'
    ) if reps else '<p class="note">No rep data available.</p>'
    rep_section = _section("👤 Rep Performance MTD", rep_table)

    # Watch items
    watch_items = narrative.get("watch_items", [])
    watch_html = ""
    if watch_items:
        items = "".join(
            f'<div class="watch-item">'
            f'<span class="watch-tag">{w["tag"]}</span>'
            f'<span>{w["text"]}</span>'
            f'</div>'
            for w in watch_items
        )
        watch_html = (
            f'<div class="watch-section">'
            f'<div class="watch-label">⚠ Watch</div>'
            f'{items}'
            f'</div>'
        )

    return f"""
<div class="page-label">Interior Define · Sales Team · {date_str}</div>
<div class="email-wrap">
  <div class="hdr">
    <div class="hdr-brand">Interior Define · Daily Business Review</div>
    <div class="hdr-meta">{day_name + ", " if day_name else ""}{date_str}{"&nbsp;&nbsp;<span class='hdr-badge'>⚡ Monday Mode</span>" if is_monday else ""}</div>
  </div>
  {tldr_html}
  {monday_html}
  {story_html}
  {cvr_section}
  {rep_section}
  {watch_html}
  <div class="footer">Interior Define Daily Business Review — auto-generated</div>
</div>
"""


# ── Main render function ───────────────────────────────────────────────────

def render(data: dict, narrative: dict, is_monday: bool = False) -> str:
    """Build the complete two-tab HTML email."""
    biz_tab   = _render_total_business(data)
    sales_tab = _render_sales_team(data, narrative, is_monday)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Interior Define — Daily Business Review</title>
<style>{_CSS}</style>
</head>
<body>
<input type="radio" name="tab" id="tab-biz" class="tab-radio" checked>
<input type="radio" name="tab" id="tab-sales" class="tab-radio">
<div class="tab-shell">
  <div class="tab-bar">
    <label for="tab-biz">📊 Total Business</label>
    <label for="tab-sales">👥 Sales Team</label>
  </div>
  <div class="tab-content" id="content-biz">{biz_tab}</div>
  <div class="tab-content" id="content-sales">{sales_tab}</div>
</div>
</body>
</html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_renderer.py -v
```

Expected: 6 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "feat: renderer — two-tab HTML email builder"
```

---

## Task 6: SendGrid email sender

**Files:**
- Create: `src/email_sender.py`
- Create: `tests/test_email_sender.py`

Sends the rendered HTML via SendGrid. Reads `SENDGRID_API_KEY`, `EMAIL_TO`, `EMAIL_FROM` from environment.

- [ ] **Step 1: Create tests/test_email_sender.py with failing tests**

```python
import pytest
from unittest.mock import MagicMock, patch


def test_send_calls_sendgrid_with_html():
    """send() calls SendGrid API with HTML content and correct addresses."""
    from src.email_sender import send

    mock_client = MagicMock()
    mock_client.send.return_value = MagicMock(status_code=202)

    with patch("src.email_sender.SendGridAPIClient", return_value=mock_client), \
         patch.dict("os.environ", {
             "SENDGRID_API_KEY": "test-key",
             "EMAIL_TO": "test@example.com",
             "EMAIL_FROM": "from@example.com",
         }):
        send("<html><body>Test</body></html>", "Test Subject")

    mock_client.send.assert_called_once()
    mail_arg = mock_client.send.call_args[0][0]
    assert mail_arg.subject.subject == "Test Subject"


def test_send_raises_on_non_202():
    """send() raises RuntimeError when SendGrid returns a non-202 status."""
    from src.email_sender import send

    mock_client = MagicMock()
    mock_client.send.return_value = MagicMock(status_code=400, body="Bad Request")

    with patch("src.email_sender.SendGridAPIClient", return_value=mock_client), \
         patch.dict("os.environ", {
             "SENDGRID_API_KEY": "test-key",
             "EMAIL_TO": "test@example.com",
             "EMAIL_FROM": "from@example.com",
         }):
        with pytest.raises(RuntimeError, match="400"):
            send("<html>Test</html>", "Subject")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_email_sender.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.email_sender'`

- [ ] **Step 3: Create src/email_sender.py**

```python
import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()


def send(html: str, subject: str) -> None:
    """Send the HTML email via SendGrid. Raises RuntimeError on non-202 response."""
    message = Mail(
        from_email=os.environ["EMAIL_FROM"],
        to_emails=os.environ["EMAIL_TO"],
        subject=subject,
        html_content=html,
    )
    client   = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
    response = client.send(message)

    if response.status_code != 202:
        raise RuntimeError(
            f"SendGrid returned status {response.status_code}: {response.body}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_email_sender.py -v
```

Expected: 2 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/email_sender.py tests/test_email_sender.py
git commit -m "feat: email_sender — SendGrid delivery with status check"
```

---

## Task 7: Main orchestrator

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

Wires all collectors → synthesizer → renderer → sender. Monday mode detected from `datetime.date.today().weekday() == 0`. Collector failures are caught individually — a failed sub-collector produces a partial result rather than crashing the run.

- [ ] **Step 1: Create tests/test_main.py with failing tests**

```python
import datetime
import pytest
from unittest.mock import MagicMock, patch, call


_MOCK_SNOWFLAKE = {
    "report_date": datetime.date(2026, 6, 6),
    "yesterday": {"revenue_total": 320000.0, "orders_total": 112, "aov_blended": 2857.0,
                  "revenue_b2c": 235000.0, "revenue_trade": 72000.0, "revenue_havenly": 13000.0,
                  "orders_b2c": 84, "orders_trade": 22, "orders_havenly": 6,
                  "aov_b2c": 2797.0, "aov_trade": 3272.0, "assisted_pct": 0.67, "upt": 2.15},
    "mtd": {"revenue_total": 4200000.0, "revenue_b2c": 3100000.0, "revenue_trade": 820000.0,
            "revenue_havenly": 280000.0, "orders_total": 1480, "revenue_total_ly": 4800000.0,
            "orders_total_ly": 1690, "repeat_pct": 0.316},
    "engagements": {"yesterday": 315, "yesterday_ly": 323, "weekly_rolling": []},
    "swatches": {"mtd_orders": 1718, "mtd_customers": 1492, "monthly_rolling": []},
    "merch_mix": {"product_contribution": [], "collection": [], "fabric": []},
    "by_studio": [],
}
_MOCK_DEALS = {"inbound_mtd": 320, "inbound_yesterday": 42,
               "cvr_14day_mtd": 0.138, "cvr_meaningful_mtd": 0.189,
               "by_studio": [], "by_rep": []}
_MOCK_SLACK = {"messages": [], "channel": "#id--retail-closing-notes"}
_MOCK_NARRATIVE = {"tldr": "<p>Good day.</p>", "yesterday_story": "<p>Strong.</p>", "watch_items": []}
_MOCK_HTML = "<!DOCTYPE html><html><body>Test</body></html>"


def test_main_calls_all_components():
    """main() calls all collectors, synthesizer, renderer, and sender."""
    with patch("src.main.fetch_all",         return_value=_MOCK_SNOWFLAKE), \
         patch("src.main.fetch_deals",        return_value=_MOCK_DEALS), \
         patch("src.main.fetch_slack_notes",  return_value=_MOCK_SLACK), \
         patch("src.main.synthesize",         return_value=_MOCK_NARRATIVE), \
         patch("src.main.render",             return_value=_MOCK_HTML), \
         patch("src.main.send")               as mock_send, \
         patch("src.main.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2026, 6, 5)  # Friday
        from src.main import main
        main()

    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert args[0] == _MOCK_HTML
    assert "Interior Define" in args[1]


def test_main_monday_mode():
    """main() passes is_monday=True when today is Monday."""
    with patch("src.main.fetch_all",        return_value=_MOCK_SNOWFLAKE), \
         patch("src.main.fetch_deals",       return_value=_MOCK_DEALS), \
         patch("src.main.fetch_slack_notes", return_value=_MOCK_SLACK), \
         patch("src.main.synthesize",        return_value=_MOCK_NARRATIVE) as mock_synth, \
         patch("src.main.render",            return_value=_MOCK_HTML)       as mock_render, \
         patch("src.main.send"), \
         patch("src.main.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2026, 6, 8)  # Monday
        from src.main import main
        main()

    mock_synth.assert_called_once()
    assert mock_synth.call_args.kwargs.get("is_monday") is True
    mock_render.assert_called_once()
    assert mock_render.call_args.kwargs.get("is_monday") is True


def test_main_deals_failure_does_not_crash():
    """main() completes even when fetch_deals() raises an exception."""
    with patch("src.main.fetch_all",        return_value=_MOCK_SNOWFLAKE), \
         patch("src.main.fetch_deals",       side_effect=Exception("Snowflake timeout")), \
         patch("src.main.fetch_slack_notes", return_value=_MOCK_SLACK), \
         patch("src.main.synthesize",        return_value=_MOCK_NARRATIVE), \
         patch("src.main.render",            return_value=_MOCK_HTML), \
         patch("src.main.send"), \
         patch("src.main.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2026, 6, 5)
        from src.main import main
        main()  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: Create src/main.py**

```python
import datetime
import sys

from src.collectors.snowflake   import fetch_all
from src.collectors.deals       import fetch_deals
from src.collectors.slack_notes import fetch_slack_notes
from src.synthesizer            import synthesize
from src.renderer               import render
from src.email_sender           import send


def _safe(fn, fallback):
    """Call fn(); return fallback if it raises."""
    try:
        return fn()
    except Exception as exc:
        print(f"[warn] {fn.__name__} failed: {exc}", file=sys.stderr)
        return fallback


def main() -> None:
    today      = datetime.date.today()
    is_monday  = today.weekday() == 0

    data = {
        **fetch_all(),
        "deals":       _safe(fetch_deals,       {"inbound_mtd": 0, "inbound_yesterday": 0,
                                                  "cvr_14day_mtd": 0.0, "cvr_meaningful_mtd": 0.0,
                                                  "by_studio": [], "by_rep": []}),
        "slack_notes": _safe(fetch_slack_notes, {"messages": [], "channel": "#id--retail-closing-notes"}),
    }

    narrative = synthesize(data, is_monday=is_monday)
    html      = render(data, narrative, is_monday=is_monday)

    day_label = "Monday Mode — " if is_monday else ""
    subject   = f"Interior Define Daily Review — {day_label}{today.strftime('%a %b %-d, %Y')}"

    send(html, subject)
    print(f"[ok] Report sent: {subject}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — NOTE: must reimport main fresh each test due to module caching**

```bash
pytest tests/test_main.py -v
```

If tests fail with stale imports, add this to the test file top:
```python
import importlib
import sys
# Clear cached main module before each test
```

Or run with: `pytest tests/test_main.py -v --cache-clear`

Expected: 3 tests `PASSED`

- [ ] **Step 5: Run complete test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (19 existing + new tests from Tasks 2–7)

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: main orchestrator — daily and Monday mode, graceful collector failures"
```

---

## Task 8: GitHub Actions cron

**Files:**
- Create: `.github/workflows/daily-report.yml`

Runs at 13:00 UTC (7am MDT) weekdays. All secrets referenced via `${{ secrets.* }}`.

- [ ] **Step 1: Create .github/workflows/daily-report.yml**

```bash
mkdir -p .github/workflows
```

Create `.github/workflows/daily-report.yml`:

```yaml
name: Daily Business Review

on:
  schedule:
    - cron: '0 13 * * 1-5'   # 7am MDT (UTC-6) Mon–Fri; 6am in winter MST
  workflow_dispatch:           # allow manual trigger from GitHub Actions UI

jobs:
  send-report:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run daily report
        env:
          SNOWFLAKE_ACCOUNT:   ${{ secrets.SNOWFLAKE_ACCOUNT }}
          SNOWFLAKE_USER:      ${{ secrets.SNOWFLAKE_USER }}
          SNOWFLAKE_PASSWORD:  ${{ secrets.SNOWFLAKE_PASSWORD }}
          SNOWFLAKE_WAREHOUSE: ${{ secrets.SNOWFLAKE_WAREHOUSE }}
          SNOWFLAKE_DATABASE:  PROD
          SNOWFLAKE_SCHEMA:    ID_WAREHOUSE
          SLACK_BOT_TOKEN:     ${{ secrets.SLACK_BOT_TOKEN }}
          ANTHROPIC_API_KEY:   ${{ secrets.ANTHROPIC_API_KEY }}
          SENDGRID_API_KEY:    ${{ secrets.SENDGRID_API_KEY }}
          EMAIL_TO:            ${{ secrets.EMAIL_TO }}
          EMAIL_FROM:          ${{ secrets.EMAIL_FROM }}
        run: python -m src.main
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/daily-report.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily-report.yml
git commit -m "chore: GitHub Actions cron — 7am MDT weekdays"
```

---

## Task 9: End-to-end local smoke test

**Files:**
- Modify: `scripts/smoke_test.py` (extend for full pipeline test)

Runs the complete pipeline locally: collectors → synthesizer → renderer → saves HTML to disk (does NOT send email). Lets you open the output in a browser to QA the design.

- [ ] **Step 1: Update scripts/smoke_test.py**

Replace the content of `scripts/smoke_test.py` with:

```python
"""End-to-end smoke test: runs full pipeline and saves HTML to disk for browser QA.
Does NOT send email. Open output/report.html in a browser after running.

Usage:
    cd /Users/mc.spreck/mary-claire-daily-business-review
    source venv/bin/activate
    python scripts/smoke_test.py
    open output/report.html
"""
import json
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors.snowflake   import fetch_all
from src.collectors.deals       import fetch_deals
from src.collectors.slack_notes import fetch_slack_notes
from src.synthesizer            import synthesize
from src.renderer               import render


def _serialize(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


if __name__ == "__main__":
    is_monday = "--monday" in sys.argv

    print("Fetching Snowflake data...",   file=sys.stderr)
    snowflake_data = fetch_all()

    print("Fetching deal/CVR metrics...", file=sys.stderr)
    deals_data = fetch_deals()

    print("Fetching Slack notes...",      file=sys.stderr)
    slack_data = fetch_slack_notes()

    data = {**snowflake_data, "deals": deals_data, "slack_notes": slack_data}

    print("Calling Claude synthesizer...", file=sys.stderr)
    narrative = synthesize(data, is_monday=is_monday)

    print("Rendering HTML...",            file=sys.stderr)
    html = render(data, narrative, is_monday=is_monday)

    os.makedirs("output", exist_ok=True)
    with open("output/report.html", "w") as f:
        f.write(html)

    with open("output/data.json", "w") as f:
        json.dump(data, f, indent=2, default=_serialize)

    print("Done. Open output/report.html in a browser.", file=sys.stderr)
    print(f"Narrative preview:\n  TL;DR: {narrative.get('tldr', '')[:80]}...", file=sys.stderr)
```

- [ ] **Step 2: Add output/ to .gitignore**

Append to `.gitignore`:
```
output/
```

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test.py .gitignore
git commit -m "chore: full-pipeline smoke test — saves HTML to output/report.html for browser QA"
```

- [ ] **Step 4: Run the smoke test (requires real credentials)**

```bash
cd /Users/mc.spreck/mary-claire-daily-business-review
source venv/bin/activate
python scripts/smoke_test.py
open output/report.html
```

Expected: browser opens with the two-tab email. Verify numbers match Looker, narrative makes sense, layout looks like the mockup.

---

## Self-Review

**Spec coverage:**
- ✅ `src/collectors/deals.py` — Task 2 (inbound MTD/yesterday, 14-day CVR, meaningful CVR, by-studio, by-rep)
- ✅ `src/collectors/slack_notes.py` — Task 3 (last 24h, non-fatal error handling)
- ✅ `src/synthesizer.py` — Task 4 (Claude API, prompt caching, Monday mode, Slack notes)
- ✅ `src/renderer.py` — Task 5 (two-tab HTML, all data sections, Monday recap conditional)
- ✅ `src/email_sender.py` — Task 6 (SendGrid, status check)
- ✅ `src/main.py` — Task 7 (orchestrates all, Monday detection, graceful failures)
- ✅ `.github/workflows/daily-report.yml` — Task 8 (cron 7am MDT, workflow_dispatch, all secrets)
- ✅ Browser QA path — Task 9 (smoke test saves to output/report.html)
- ✅ New dependencies — Task 1 (anthropic, sendgrid, slack-sdk)

**Placeholder scan:** No TBDs, TODOs, or vague steps found.

**Type consistency:**
- `fetch_deals()` returns dict with `inbound_mtd`, `inbound_yesterday`, `cvr_14day_mtd`, `cvr_meaningful_mtd`, `by_studio`, `by_rep` — matches Task 7 `_safe` fallback keys
- `synthesize()` returns dict with `tldr`, `yesterday_story`, `watch_items` — matches renderer access in Task 5
- `render()` signature `(data, narrative, is_monday=False)` — matches Task 7 call
- `send()` signature `(html, subject)` — matches Task 7 call
