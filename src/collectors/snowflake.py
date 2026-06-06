from src.collectors.db import _query


_ORDER_FILTER = "ORDER_TYPE = 'standard' AND CANCELLATION = 'F'"

_DENVER_DATE = """
    CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE
""".strip()


def fetch_yesterday_orders() -> dict:
    """NBE, order count, and AOV by segment for yesterday (Denver time)."""
    df = _query(f"""
        SELECT
            CUSTOMER_GROUP,
            SUM(NET_BOOKINGS_ESTIMATED)                         AS nbe,
            COUNT(*)                                            AS order_count,
            SUM(NET_BOOKINGS_ESTIMATED) / NULLIF(COUNT(*), 0)  AS aov
        FROM PROD.ID_WAREHOUSE.ORDERS
        WHERE {_ORDER_FILTER}
          AND {_DENVER_DATE}
              = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
        GROUP BY CUSTOMER_GROUP
    """)

    seg = {row["customer_group"]: row for _, row in df.iterrows()}

    def _nbe(g):    return float(seg[g]["nbe"])       if g in seg else 0.0
    def _orders(g): return int(seg[g]["order_count"]) if g in seg else 0
    def _aov(g):    return float(seg[g]["aov"])       if g in seg else 0.0

    nbe_total    = _nbe("B2C") + _nbe("Trade") + _nbe("Havenly")
    orders_total = _orders("B2C") + _orders("Trade") + _orders("Havenly")

    return {
        "nbe_b2c":        _nbe("B2C"),
        "nbe_trade":      _nbe("Trade"),
        "nbe_havenly":    _nbe("Havenly"),
        "nbe_total":      nbe_total,
        "orders_b2c":     _orders("B2C"),
        "orders_trade":   _orders("Trade"),
        "orders_havenly": _orders("Havenly"),
        "orders_total":   orders_total,
        "aov_b2c":        _aov("B2C"),
        "aov_trade":      _aov("Trade"),
        "aov_blended":    nbe_total / orders_total if orders_total else 0.0,
    }
