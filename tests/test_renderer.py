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
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html


def test_render_contains_both_tabs():
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert "Total Business" in html
    assert "Sales Team" in html


def test_render_contains_revenue_total():
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert "320" in html


def test_render_contains_narrative():
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE)
    assert "Strong Friday" in html


def test_render_monday_mode_includes_recap():
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE, is_monday=True)
    assert "Last Week" in html or "last week" in html.lower()


def test_render_non_monday_omits_recap():
    from src.renderer import render
    html = render(_SAMPLE_DATA, _SAMPLE_NARRATIVE, is_monday=False)
    assert "Last Week Recap" not in html
