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
    """fetch_yesterday_orders() returns nbe/orders/aov for B2C, Trade, Havenly."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",     7_100_000.0, 2482, 2864.0),
        ("Trade",   1_900_000.0,  590, 3226.0),
        ("Havenly",   629_000.0,  205, 3068.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["customer_group", "nbe", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["nbe_b2c"]     == pytest.approx(7_100_000.0)
    assert result["nbe_trade"]   == pytest.approx(1_900_000.0)
    assert result["nbe_havenly"] == pytest.approx(629_000.0)
    assert result["nbe_total"]   == pytest.approx(9_629_000.0)
    assert result["orders_b2c"]  == 2482
    assert result["aov_b2c"]     == pytest.approx(2864.0)
    assert result["aov_trade"]   == pytest.approx(3226.0)
    # blended AOV = total NBE / total orders
    assert result["aov_blended"] == pytest.approx(9_629_000.0 / 3277, rel=0.01)


def test_fetch_yesterday_orders_missing_segment():
    """fetch_yesterday_orders() returns 0 for a missing segment (e.g. no Havenly orders)."""
    from src.collectors.snowflake import fetch_yesterday_orders

    rows = [
        ("B2C",   300_000.0, 105, 2857.0),
        ("Trade",  85_000.0,  27, 3148.0),
    ]
    mock_df = pd.DataFrame(rows, columns=["customer_group", "nbe", "order_count", "aov"])

    with patch("src.collectors.snowflake._query", return_value=mock_df):
        result = fetch_yesterday_orders()

    assert result["nbe_havenly"]    == 0.0
    assert result["orders_havenly"] == 0


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
