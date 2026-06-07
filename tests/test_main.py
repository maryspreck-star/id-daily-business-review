import datetime
import pytest
from unittest.mock import MagicMock, patch


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
_MOCK_DEALS     = {"inbound_mtd": 320, "inbound_yesterday": 42,
                   "cvr_14day_mtd": 0.138, "cvr_meaningful_mtd": 0.189,
                   "by_studio": [], "by_rep": []}
_MOCK_SLACK     = {"messages": [], "channel": "#id--retail-closing-notes"}
_MOCK_NARRATIVE = {"tldr": "<p>Good day.</p>", "yesterday_story": "<p>Strong.</p>", "watch_items": []}
_MOCK_HTML      = "<!DOCTYPE html><html><body>Test</body></html>"


def test_main_calls_all_components():
    """main() calls all collectors, synthesizer, renderer, and sender."""
    import importlib
    import sys
    sys.modules.pop("src.main", None)

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
    """main() passes is_monday=True to synthesize and render when today is Monday."""
    import sys
    sys.modules.pop("src.main", None)

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

    assert mock_synth.call_args.kwargs.get("is_monday") is True
    assert mock_render.call_args.kwargs.get("is_monday") is True


def test_main_deals_failure_does_not_crash():
    """main() completes even when fetch_deals() raises an exception."""
    import sys
    sys.modules.pop("src.main", None)

    with patch("src.main.fetch_all",        return_value=_MOCK_SNOWFLAKE), \
         patch("src.main.fetch_deals",       side_effect=Exception("timeout")), \
         patch("src.main.fetch_slack_notes", return_value=_MOCK_SLACK), \
         patch("src.main.synthesize",        return_value=_MOCK_NARRATIVE), \
         patch("src.main.render",            return_value=_MOCK_HTML), \
         patch("src.main.send"), \
         patch("src.main.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2026, 6, 5)
        from src.main import main
        main()  # must not raise
