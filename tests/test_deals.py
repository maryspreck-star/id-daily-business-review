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

    assert result["cvr_14day_mtd"]      == pytest.approx(12 / 80)
    assert result["cvr_meaningful_mtd"] == pytest.approx(9 / 60)
    assert result["inbound_mtd"]        == 100
    assert result["inbound_yesterday"]  == 8


def test_fetch_deals_zero_cohort():
    """fetch_deals() returns 0.0 CVR when cohort is empty."""
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

    assert result["cvr_14day_mtd"]      == 0.0
    assert result["cvr_meaningful_mtd"] == 0.0
