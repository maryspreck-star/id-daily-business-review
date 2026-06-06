import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def test_query_lowercases_columns():
    """_query() normalises all column names to lowercase."""
    from src.collectors.db import _query

    mock_conn = MagicMock()
    mock_df = pd.DataFrame({"UPPER_COL": [1, 2]})

    with patch("src.collectors.db._connect", return_value=mock_conn), \
         patch("pandas.read_sql", return_value=mock_df):
        result = _query("SELECT 1")

    assert "upper_col" in result.columns
    assert "UPPER_COL" not in result.columns


def test_fetch_yesterday_segments_all_groups():
    """fetch_yesterday_orders() returns revenue/orders/aov for B2C, Trade, B2B."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",   7_100_000.0, 2482, 2864.0),
        ("Trade", 1_900_000.0,  590, 3226.0),
        ("B2B",     629_000.0,  205, 3068.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["segment", "revenue", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["revenue_b2c"]   == pytest.approx(7_100_000.0)
    assert result["revenue_trade"] == pytest.approx(1_900_000.0)
    assert result["revenue_b2b"]   == pytest.approx(629_000.0)
    assert result["revenue_total"] == pytest.approx(9_629_000.0)
    assert result["orders_b2c"]    == 2482
    assert result["aov_b2c"]       == pytest.approx(2864.0)
    assert result["aov_trade"]     == pytest.approx(3226.0)
    assert result["aov_blended"]   == pytest.approx(9_629_000.0 / 3277, rel=0.01)


def test_fetch_yesterday_orders_missing_segment():
    """fetch_yesterday_orders() returns 0 for a missing segment (e.g. no B2B orders)."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",   300_000.0, 105, 2857.0),
        ("Trade",  85_000.0,  27, 3148.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["segment", "revenue", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["revenue_b2b"] == 0.0
    assert result["orders_b2b"]  == 0


def test_fetch_yesterday_assisted_pct():
    """fetch_yesterday_assisted() returns assisted_pct and upt."""
    from src.collectors.snowflake import fetch_yesterday_assisted

    mock_df = pd.DataFrame([{"total_orders": 100, "assisted_orders": 67, "total_items": 215}])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_assisted()

    assert result["assisted_pct"] == pytest.approx(0.67)
    assert result["upt"]          == pytest.approx(2.15)


def test_fetch_yesterday_assisted_zero_orders():
    """fetch_yesterday_assisted() handles zero-order edge case without dividing by zero."""
    from src.collectors.snowflake import fetch_yesterday_assisted

    mock_df = pd.DataFrame([{"total_orders": 0, "assisted_orders": 0, "total_items": 0}])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_assisted()

    assert result["assisted_pct"] == 0.0
    assert result["upt"]          == 0.0


def test_fetch_mtd_returns_totals_and_ly():
    """fetch_mtd_orders() returns this-year and last-year totals."""
    from src.collectors.snowflake import fetch_mtd_orders

    ty_rows = [
        ("B2C",   7_100_000.0, 2482),
        ("Trade", 1_900_000.0,  590),
    ]
    ly_rows = [
        ("B2C",   7_800_000.0, 2700),
        ("Trade", 1_560_000.0,  504),
    ]
    ty_df = pd.DataFrame(ty_rows, columns=["segment", "revenue", "order_count"])
    ly_df = pd.DataFrame(ly_rows, columns=["segment", "revenue", "order_count"])

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        return ty_df if call_count == 1 else ly_df

    with patch("src.collectors.snowflake._query", side_effect=mock_query):
        result = fetch_mtd_orders()

    assert result["revenue_b2c"]      == pytest.approx(7_100_000.0)
    assert result["revenue_total"]    == pytest.approx(9_000_000.0)
    assert result["revenue_total_ly"] == pytest.approx(9_360_000.0)
    assert result["orders_total"]     == 3072
    assert result["orders_total_ly"]  == 3204


def test_fetch_mtd_yoy_zero_ly():
    """fetch_mtd_orders() handles zero LY data gracefully."""
    from src.collectors.snowflake import fetch_mtd_orders

    ty_df = pd.DataFrame([("B2C", 500_000.0, 175)],
                         columns=["segment", "revenue", "order_count"])
    ly_df = pd.DataFrame([], columns=["segment", "revenue", "order_count"])

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        return ty_df if call_count == 1 else ly_df

    with patch("src.collectors.snowflake._query", side_effect=mock_query):
        result = fetch_mtd_orders()

    assert result["revenue_total_ly"] == 0.0
    assert result["orders_total_ly"]  == 0


def test_fetch_mtd_repeat_pct():
    """fetch_mtd_repeat_pct() returns fraction of MTD orders from returning customers."""
    from src.collectors.snowflake import fetch_mtd_repeat_pct

    mock_df = pd.DataFrame([{"total_orders": 1000, "repeat_orders": 316}])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_mtd_repeat_pct()

    assert result == pytest.approx(0.316)


def test_fetch_mtd_repeat_pct_zero():
    """fetch_mtd_repeat_pct() returns 0.0 when no orders."""
    from src.collectors.snowflake import fetch_mtd_repeat_pct

    mock_df = pd.DataFrame([{"total_orders": 0, "repeat_orders": 0}])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_mtd_repeat_pct()

    assert result == 0.0


def test_fetch_engagements_yesterday_and_ly():
    """fetch_engagements() returns yesterday count and same-DOW LY count."""
    from src.collectors.snowflake import fetch_engagements
    import datetime

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    ly_date = yesterday - datetime.timedelta(days=364)  # same DOW last year

    rows = [
        (ly_date, 323),
        (yesterday, 315),
    ]
    mock_df = pd.DataFrame(rows, columns=["day", "engagements"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_engagements()

    assert result["yesterday"]    == 315
    assert result["yesterday_ly"] == 323


def test_fetch_engagements_no_ly_match():
    """fetch_engagements() returns 0 for LY when no matching date exists."""
    from src.collectors.snowflake import fetch_engagements
    import datetime

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    mock_df = pd.DataFrame([(yesterday, 287)], columns=["day", "engagements"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_engagements()

    assert result["yesterday"]    == 287
    assert result["yesterday_ly"] == 0


def test_fetch_engagements_weekly_rolling():
    """fetch_engagements() weekly_rolling contains counts for 4 Monday week starts."""
    from src.collectors.snowflake import fetch_engagements
    import datetime

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    ly_date = yesterday - datetime.timedelta(days=364)
    this_monday = today - datetime.timedelta(days=today.weekday())
    week_starts = [this_monday - datetime.timedelta(weeks=w) for w in range(1, 5)]

    # Return counts for 3 of the 4 week starts (leave one missing to test default 0)
    rows = [
        (yesterday, 315),
        (ly_date,   323),
        (week_starts[0], 341),   # most recent Monday
        (week_starts[1], 298),
        (week_starts[2], 312),
        # week_starts[3] intentionally absent → should be 0
    ]
    mock_df = pd.DataFrame(rows, columns=["day", "engagements"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_engagements()

    rolling = result["weekly_rolling"]
    assert len(rolling) == 4
    # oldest first: index 0 = 4 weeks ago (week_starts[3], absent → 0)
    assert rolling[0]["count"] == 0
    assert rolling[1]["count"] == 312
    assert rolling[2]["count"] == 298
    assert rolling[3]["count"] == 341  # most recent
    # All week_start values are datetime.date objects
    assert all(isinstance(r["week_start"], datetime.date) for r in rolling)


def test_fetch_swatches_mtd_and_rolling():
    """fetch_swatches() returns MTD counts and 6-month rolling list."""
    from src.collectors.snowflake import fetch_swatches
    import datetime

    today = datetime.date.today()
    month_start = today.replace(day=1)

    # Build 6 prior complete months + current partial month
    def prior_month(n):
        d = month_start
        for _ in range(n):
            d = (d - datetime.timedelta(days=1)).replace(day=1)
        return d

    rows = [(prior_month(i), 100 + i * 20, 90 + i * 18) for i in range(6, 0, -1)]
    rows.append((month_start, 250, 210))  # current month
    mock_df = pd.DataFrame(rows, columns=["month", "swatch_orders", "swatch_customers"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_swatches()

    assert result["mtd_orders"]    == 250
    assert result["mtd_customers"] == 210
    assert len(result["monthly_rolling"]) == 6


def test_fetch_swatches_no_mtd():
    """fetch_swatches() returns 0 for MTD when current month has no data."""
    from src.collectors.snowflake import fetch_swatches
    import datetime

    today = datetime.date.today()
    last_month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    mock_df = pd.DataFrame(
        [(last_month, 500, 430)],
        columns=["month", "swatch_orders", "swatch_customers"]
    )

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_swatches()

    assert result["mtd_orders"]    == 0
    assert result["mtd_customers"] == 0


def test_fetch_merch_mix_product_contribution_pcts_sum_to_1():
    """fetch_merch_mix() product_contribution percentages sum to ~1.0."""
    from src.collectors.snowflake import fetch_merch_mix

    class_rows = [
        ("Sectionals", 3_920_000.0),
        ("Sofas",      2_360_000.0),
        ("Chairs",     1_350_000.0),
    ]
    collection_rows = [("Sloan", 2_000_000.0), ("James", 1_500_000.0)]
    fabric_rows = [("Velvet", 5_370_000.0), ("Performance", 3_170_000.0)]

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        cols = ["category", "item_revenue"]
        if call_count == 1: return pd.DataFrame(class_rows, columns=cols)
        if call_count == 2: return pd.DataFrame(collection_rows, columns=cols)
        return pd.DataFrame(fabric_rows, columns=cols)

    with patch("src.collectors.snowflake._query", side_effect=mock_query):
        result = fetch_merch_mix()

    total_pct = sum(item["pct"] for item in result["product_contribution"])
    assert total_pct == pytest.approx(1.0, abs=0.001)
    assert any(item["name"] == "Sectionals" for item in result["product_contribution"])
    assert "collection" in result
    assert "fabric" in result


def test_fetch_merch_mix_fabric_pcts_sum_to_1():
    """fetch_merch_mix() fabric percentages sum to ~1.0."""
    from src.collectors.snowflake import fetch_merch_mix

    class_rows = [("Sectionals", 1_000_000.0)]
    collection_rows = [("Sloan", 800_000.0)]
    fabric_rows = [
        ("Velvet",      530_000.0),
        ("Performance", 310_000.0),
        ("Leather",     160_000.0),
    ]

    call_count = 0
    def mock_query(sql):
        nonlocal call_count
        call_count += 1
        cols = ["category", "item_revenue"]
        if call_count == 1: return pd.DataFrame(class_rows, columns=cols)
        if call_count == 2: return pd.DataFrame(collection_rows, columns=cols)
        return pd.DataFrame(fabric_rows, columns=cols)

    with patch("src.collectors.snowflake._query", side_effect=mock_query):
        result = fetch_merch_mix()

    fabric_total = sum(item["pct"] for item in result["fabric"])
    assert fabric_total == pytest.approx(1.0, abs=0.001)


def test_fetch_by_studio_sorted_by_revenue():
    """fetch_by_studio() returns list sorted highest revenue first."""
    from src.collectors.snowflake import fetch_by_studio

    rows = [
        ("Chicago",     820_000.0, 290),
        ("Los Angeles", 650_000.0, 230),
        ("New York",    580_000.0, 205),
    ]
    mock_df = pd.DataFrame(rows, columns=["studio", "revenue", "orders"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_by_studio()

    assert result[0]["studio"]  == "Chicago"
    assert result[0]["revenue"] == pytest.approx(820_000.0)
    assert result[2]["studio"]  == "New York"


def test_fetch_by_studio_empty():
    """fetch_by_studio() returns empty list when no data."""
    from src.collectors.snowflake import fetch_by_studio

    mock_df = pd.DataFrame([], columns=["studio", "revenue", "orders"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_by_studio()

    assert result == []


def test_fetch_all_returns_full_contract():
    """fetch_all() returns a dict with all required top-level keys."""
    from src.collectors.snowflake import fetch_all
    import datetime

    stubs = {
        "src.collectors.snowflake.fetch_yesterday_orders": {
            "revenue_total": 300_000.0, "orders_total": 105,
            "revenue_b2c": 220_000.0, "revenue_trade": 70_000.0, "revenue_b2b": 10_000.0,
            "orders_b2c": 77, "orders_trade": 22, "orders_b2b": 6,
            "aov_b2c": 2857.0, "aov_trade": 3182.0, "aov_blended": 2857.0,
        },
        "src.collectors.snowflake.fetch_yesterday_assisted":  {"assisted_pct": 0.67, "upt": 2.15},
        "src.collectors.snowflake.fetch_mtd_orders":          {
            "revenue_total": 5_000_000.0, "revenue_b2c": 3_700_000.0,
            "revenue_trade": 900_000.0, "revenue_b2b": 400_000.0,
            "orders_total": 1750, "revenue_total_ly": 5_400_000.0, "orders_total_ly": 1900,
        },
        "src.collectors.snowflake.fetch_mtd_repeat_pct":      0.316,
        "src.collectors.snowflake.fetch_engagements":         {"yesterday": 315, "yesterday_ly": 323, "weekly_rolling": []},
        "src.collectors.snowflake.fetch_swatches":            {"mtd_orders": 8200, "mtd_customers": 6900, "monthly_rolling": []},
        "src.collectors.snowflake.fetch_merch_mix":           {"product_contribution": [], "collection": [], "fabric": []},
        "src.collectors.snowflake.fetch_by_studio":           [],
    }

    patches = [patch(k, return_value=v) for k, v in stubs.items()]
    for p in patches:
        p.start()

    result = fetch_all()

    for p in patches:
        p.stop()

    required_keys = {"report_date", "yesterday", "mtd", "engagements", "swatches", "merch_mix", "by_studio"}
    assert required_keys <= set(result.keys())
    assert isinstance(result["report_date"], datetime.date)
    assert "assisted_pct" in result["yesterday"]
    assert "repeat_pct"   in result["mtd"]
    assert result["mtd"]["repeat_pct"] == pytest.approx(0.316)
