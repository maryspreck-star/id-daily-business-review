import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def _mock_conn(rows, columns):
    """Build a mock connection that returns `rows` for any read_sql call."""
    mock_conn = MagicMock()
    mock_df = pd.DataFrame(rows, columns=columns)
    with patch("pandas.read_sql", return_value=mock_df):
        yield mock_conn


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
