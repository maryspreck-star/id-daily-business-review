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
    """fetch_yesterday_orders() returns revenue/orders/aov for B2C, Trade, Havenly."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",     7_100_000.0, 2482, 2864.0),
        ("Trade",   1_900_000.0,  590, 3226.0),
        ("Havenly",   629_000.0,  205, 3068.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["customer_group", "revenue", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["revenue_b2c"]     == pytest.approx(7_100_000.0)
    assert result["revenue_trade"]   == pytest.approx(1_900_000.0)
    assert result["revenue_havenly"] == pytest.approx(629_000.0)
    assert result["revenue_total"]   == pytest.approx(9_629_000.0)
    assert result["orders_b2c"]  == 2482
    assert result["aov_b2c"]     == pytest.approx(2864.0)
    assert result["aov_trade"]   == pytest.approx(3226.0)
    # blended AOV = total revenue / total orders
    assert result["aov_blended"] == pytest.approx(9_629_000.0 / 3277, rel=0.01)


def test_fetch_yesterday_orders_missing_segment():
    """fetch_yesterday_orders() returns 0 for a missing segment (e.g. no Havenly orders)."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",   300_000.0, 105, 2857.0),
        ("Trade",  85_000.0,  27, 3148.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["customer_group", "revenue", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["revenue_havenly"] == 0.0
    assert result["orders_havenly"]  == 0


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
    ty_df = pd.DataFrame(ty_rows, columns=["customer_group", "revenue", "order_count"])
    ly_df = pd.DataFrame(ly_rows, columns=["customer_group", "revenue", "order_count"])

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
                         columns=["customer_group", "revenue", "order_count"])
    ly_df = pd.DataFrame([], columns=["customer_group", "revenue", "order_count"])

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
