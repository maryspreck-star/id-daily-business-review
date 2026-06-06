from src.collectors.db import _query


_ORDER_FILTER = "ORDER_TYPE = 'standard' AND CANCELLATION = 'F'"

_DENVER_DATE = """
    CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE
""".strip()


def fetch_yesterday_orders() -> dict:
    """Discounted revenue, order count, and AOV by segment for yesterday (Denver time)."""
    df = _query(f"""
        SELECT
            CUSTOMER_GROUP,
            SUM(subtotal - ABS(discount_amount) + shipping_amount)                         AS revenue,
            COUNT(*)                                                                        AS order_count,
            SUM(subtotal - ABS(discount_amount) + shipping_amount) / NULLIF(COUNT(*), 0)  AS aov
        FROM PROD.ID_WAREHOUSE.ORDERS
        WHERE {_ORDER_FILTER}
          AND {_DENVER_DATE}
              = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
        GROUP BY CUSTOMER_GROUP
    """)

    seg = {row["customer_group"]: row for _, row in df.iterrows()}

    def _rev(g):    return float(seg[g]["revenue"])    if g in seg else 0.0
    def _orders(g): return int(seg[g]["order_count"])  if g in seg else 0
    def _aov(g):    return float(seg[g]["aov"])        if g in seg else 0.0

    revenue_total = _rev("B2C") + _rev("Trade") + _rev("Havenly")
    orders_total  = _orders("B2C") + _orders("Trade") + _orders("Havenly")

    return {
        "revenue_b2c":    _rev("B2C"),
        "revenue_trade":  _rev("Trade"),
        "revenue_havenly": _rev("Havenly"),
        "revenue_total":  revenue_total,
        "orders_b2c":     _orders("B2C"),
        "orders_trade":   _orders("Trade"),
        "orders_havenly": _orders("Havenly"),
        "orders_total":   orders_total,
        "aov_b2c":        _aov("B2C"),
        "aov_trade":      _aov("Trade"),
        "aov_blended":    revenue_total / orders_total if orders_total else 0.0,
    }


def fetch_yesterday_assisted() -> dict:
    """Assisted sales % and UPT for yesterday."""
    df = _query(f"""
        SELECT
            COUNT(*)                                                        AS total_orders,
            SUM(CASE WHEN INDIVIDUAL IS NOT NULL AND INDIVIDUAL != ''
                     THEN 1 ELSE 0 END)                                     AS assisted_orders,
            (SELECT COUNT(*) FROM PROD.ID_WAREHOUSE.ORDER_ITEMS oi
             JOIN PROD.ID_WAREHOUSE.ORDERS o2 ON oi.ORDER_ID = o2.ORDER_ID
             WHERE {_ORDER_FILTER}
               AND {_DENVER_DATE.replace('ORDER_CREATED_AT', 'o2.ORDER_CREATED_AT')}
                   = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
            )                                                               AS total_items
        FROM PROD.ID_WAREHOUSE.ORDERS
        WHERE {_ORDER_FILTER}
          AND {_DENVER_DATE}
              = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
    """)

    row = df.iloc[0]
    total  = int(row["total_orders"])
    items  = int(row["total_items"])

    return {
        "assisted_pct": int(row["assisted_orders"]) / total if total else 0.0,
        "upt":          items / total if total else 0.0,
    }


def fetch_mtd_orders() -> dict:
    """MTD discounted revenue + order counts for TY and LY (same calendar days last year)."""
    _mtd_filter = f"""
        {_ORDER_FILTER}
        AND {_DENVER_DATE} >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
        AND {_DENVER_DATE} <  CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE
    """
    _ly_filter = f"""
        {_ORDER_FILTER}
        AND {_DENVER_DATE} >= DATEADD('year', -1, DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE))
        AND {_DENVER_DATE} <  DATEADD('year', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
    """

    def _segment_totals(filter_clause) -> dict:
        df = _query(f"""
            SELECT
                CUSTOMER_GROUP,
                SUM(subtotal - ABS(discount_amount) + shipping_amount) AS revenue,
                COUNT(*)                                               AS order_count
            FROM PROD.ID_WAREHOUSE.ORDERS
            WHERE {filter_clause}
            GROUP BY CUSTOMER_GROUP
        """)
        seg = {row["customer_group"]: row for _, row in df.iterrows()}
        def _rev(g):    return float(seg[g]["revenue"]) if g in seg else 0.0
        def _cnt(g):    return int(seg[g]["order_count"]) if g in seg else 0
        rev = _rev("B2C") + _rev("Trade") + _rev("Havenly")
        cnt = _cnt("B2C") + _cnt("Trade") + _cnt("Havenly")
        return {"revenue_b2c": _rev("B2C"), "revenue_trade": _rev("Trade"),
                "revenue_havenly": _rev("Havenly"), "revenue_total": rev,
                "orders_total": cnt}

    ty = _segment_totals(_mtd_filter)
    ly = _segment_totals(_ly_filter)

    return {
        **ty,
        "revenue_total_ly": ly["revenue_total"],
        "orders_total_ly":  ly["orders_total"],
    }


def fetch_mtd_repeat_pct() -> float:
    """Fraction of MTD orders from customers who ordered before the current month."""
    df = _query(f"""
        WITH mtd_orders AS (
            SELECT ORDER_ID, CUSTOMER_ID
            FROM PROD.ID_WAREHOUSE.ORDERS
            WHERE {_ORDER_FILTER}
              AND {_DENVER_DATE} >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
              AND {_DENVER_DATE} <  CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE
        ),
        first_order_dates AS (
            SELECT CUSTOMER_ID,
                   MIN({_DENVER_DATE}) AS first_order_date
            FROM PROD.ID_WAREHOUSE.ORDERS
            WHERE {_ORDER_FILTER}
            GROUP BY CUSTOMER_ID
        )
        SELECT
            COUNT(*)  AS total_orders,
            SUM(CASE WHEN fo.first_order_date
                          < DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
                     THEN 1 ELSE 0 END) AS repeat_orders
        FROM mtd_orders mo
        JOIN first_order_dates fo ON mo.CUSTOMER_ID = fo.CUSTOMER_ID
    """)

    row = df.iloc[0]
    total = int(row["total_orders"])
    return int(row["repeat_orders"]) / total if total else 0.0


_EXCLUDED_STUDIOS = "('The Inside', 'Burrow', 'General Managers', 'Remote Sales')"


def fetch_engagements() -> dict:
    """Daily B2C inbound engagement counts.

    Matches Looker 1156 'Daily Inbound Engagement' tile:
    - Excludes NOTE and TASK engagement types
    - Uses Denver timezone for day boundaries
    - Returns yesterday + same-DOW last year + rolling 4-week Monday aggregates
    """
    import datetime

    today     = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    ly_date   = yesterday - datetime.timedelta(days=364)  # same day-of-week last year

    # Compute 4 Monday-aligned week starts in Python so SQL IN clause uses exact dates
    this_monday = today - datetime.timedelta(days=today.weekday())
    week_starts = [this_monday - datetime.timedelta(weeks=w) for w in range(1, 5)]

    all_dates = [yesterday, ly_date] + week_starts
    dates_in = ", ".join(f"'{d}'" for d in all_dates)

    df = _query(f"""
        WITH engagements AS (
            SELECT * FROM PROD.ID_WAREHOUSE.STG_HUBSPOT_ENGAGEMENTS_BASE
            WHERE ENGAGEMENT_TYPE <> 'NOTE' AND ENGAGEMENT_TYPE <> 'TASK'
        )
        SELECT
            CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(e.CREATED_AT AS TIMESTAMP_NTZ))::DATE AS day,
            COUNT(DISTINCT c.PRIMARY_HUBSPOT_ID) AS engagements
        FROM engagements e
        JOIN PROD.ID_WAREHOUSE.STG_CONTACTS c
            ON e.CONTACT_ID = c.PRIMARY_HUBSPOT_ID
        WHERE (c.STUDIO_NAME NOT IN {_EXCLUDED_STUDIOS} OR c.STUDIO_NAME IS NULL)
          AND e.ENGAGEMENT_DIRECTION = 'Incoming'
          AND c.CUSTOMER_GROUP = 'B2C'
          AND CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(e.CREATED_AT AS TIMESTAMP_NTZ))::DATE
              IN ({dates_in})
        GROUP BY 1
        ORDER BY 1
    """)

    by_date = dict(zip(df["day"].astype(str), df["engagements"].astype(int)))

    weekly = [
        {"week_start": ws, "count": by_date.get(str(ws), 0)}
        for ws in reversed(week_starts)  # oldest first
    ]

    return {
        "yesterday":      by_date.get(str(yesterday), 0),
        "yesterday_ly":   by_date.get(str(ly_date), 0),
        "weekly_rolling": weekly,
    }
