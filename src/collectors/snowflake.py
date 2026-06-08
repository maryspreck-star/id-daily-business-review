from src.collectors.db import _query


_ORDER_FILTER = "ORDER_TYPE = 'standard' AND CANCELLATION = 'F'"

_DENVER_DATE = """
    CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE
""".strip()


def fetch_yesterday_orders() -> dict:
    """Discounted revenue, order count, and AOV by customer segment for yesterday (Denver time).
    Segments: B2C, Trade, Havenly, B2B. Excludes staff (@interiordefine.com) orders.
    """
    df = _query(f"""
        SELECT
            CASE WHEN c.CUSTOMER_ID = 20 THEN 'Havenly'
                 ELSE c.CUSTOMER_GROUP_CLASS END          AS segment,
            SUM(o.subtotal - ABS(o.discount_amount) + o.shipping_amount)               AS revenue,
            COUNT(*)                                                                    AS order_count,
            SUM(o.subtotal - ABS(o.discount_amount) + o.shipping_amount)
                / NULLIF(COUNT(*), 0)                                                  AS aov
        FROM PROD.ID_WAREHOUSE.ORDERS o
        INNER JOIN ID_WAREHOUSE.CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID
        WHERE {_DENVER_DATE}
              = DATEADD('day', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
          AND (c.EMAIL NOT LIKE '%@interiordefine.com%' OR c.EMAIL IS NULL)
        GROUP BY segment
    """)

    seg = {row["segment"]: row for _, row in df.iterrows()}

    def _rev(g):    return float(seg[g]["revenue"])      if g in seg else 0.0
    def _orders(g): return int(seg[g]["order_count"])    if g in seg else 0
    def _aov(g):    return float(seg[g]["aov"])          if g in seg else 0.0

    revenue_total = sum(float(row["revenue"]) for _, row in df.iterrows())
    orders_total  = sum(int(row["order_count"]) for _, row in df.iterrows())

    return {
        "revenue_b2c":     _rev("B2C"),
        "revenue_trade":   _rev("Trade"),
        "revenue_havenly": _rev("Havenly"),
        "revenue_b2b":     _rev("B2B"),
        "revenue_total":   revenue_total,
        "orders_b2c":      _orders("B2C"),
        "orders_trade":    _orders("Trade"),
        "orders_havenly":  _orders("Havenly"),
        "orders_b2b":      _orders("B2B"),
        "orders_total":    orders_total,
        "aov_b2c":         _aov("B2C"),
        "aov_trade":       _aov("Trade"),
        "aov_blended":     revenue_total / orders_total if orders_total else 0.0,
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
    """MTD discounted revenue + order counts for TY and LY (same calendar days last year).
    Segments: B2C, Trade, Havenly, B2B. Excludes staff (@interiordefine.com) orders.
    """
    _mtd_filter = f"""
        {_DENVER_DATE} >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
        AND {_DENVER_DATE} <  CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE
    """
    _ly_filter = f"""
        {_DENVER_DATE} >= DATEADD('year', -1, DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE))
        AND {_DENVER_DATE} <  DATEADD('year', -1, CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
    """

    def _segment_totals(filter_clause) -> dict:
        df = _query(f"""
            SELECT
                CASE WHEN c.CUSTOMER_ID = 20 THEN 'Havenly'
                     ELSE c.CUSTOMER_GROUP_CLASS END AS segment,
                SUM(o.subtotal - ABS(o.discount_amount) + o.shipping_amount) AS revenue,
                COUNT(*) AS order_count
            FROM PROD.ID_WAREHOUSE.ORDERS o
            INNER JOIN ID_WAREHOUSE.CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID
            WHERE {filter_clause}
              AND (c.EMAIL NOT LIKE '%@interiordefine.com%' OR c.EMAIL IS NULL)
            GROUP BY segment
        """)
        seg = {row["segment"]: row for _, row in df.iterrows()}
        def _rev(g): return float(seg[g]["revenue"]) if g in seg else 0.0
        def _cnt(g): return int(seg[g]["order_count"]) if g in seg else 0
        revenue = sum(float(row["revenue"]) for _, row in df.iterrows())
        cnt     = sum(int(row["order_count"]) for _, row in df.iterrows())
        return {
            "revenue_b2c":     _rev("B2C"),
            "revenue_trade":   _rev("Trade"),
            "revenue_havenly": _rev("Havenly"),
            "revenue_b2b":     _rev("B2B"),
            "revenue_total":   revenue,
            "orders_total":    cnt,
        }

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


def fetch_swatches() -> dict:
    """MTD swatch order count + unique customers. Rolling 6-month monthly volumes."""
    import datetime

    today = datetime.date.today()
    month_start = today.replace(day=1)

    df = _query(f"""
        SELECT
            DATE_TRUNC('month', so.CREATED_AT)::DATE AS month,
            COUNT(*)                                  AS swatch_orders,
            COUNT(DISTINCT so.EMAIL)                  AS swatch_customers
        FROM PROD.ID_WAREHOUSE.SWATCH_ORDERS so
        JOIN PROD.ID_WAREHOUSE.STG_CONTACTS c
            ON LOWER(so.EMAIL) = LOWER(c.CONTACT_EMAIL)
        WHERE c.CUSTOMER_GROUP = 'B2C'
          AND so.CREATED_AT >= DATEADD('month', -6, '{month_start}')
          AND so.CREATED_AT < CURRENT_DATE()
        GROUP BY 1
        ORDER BY 1
    """)

    by_month = {str(row["month"]): row for _, row in df.iterrows()}
    current  = by_month.get(str(month_start))

    # 6 prior complete months, oldest first
    rolling = []
    m = month_start
    for _ in range(6):
        m = (m - datetime.timedelta(days=1)).replace(day=1)
        row = by_month.get(str(m), {})
        rolling.append({
            "month":  m,
            "orders": int(row.get("swatch_orders", 0)),
        })
    rolling.reverse()

    return {
        "mtd_orders":      int(current["swatch_orders"])    if current is not None else 0,
        "mtd_customers":   int(current["swatch_customers"]) if current is not None else 0,
        "monthly_rolling": rolling,
    }


def fetch_merch_mix() -> dict:
    """MTD product contribution (by class), collection performance (by name), and fabric mix."""
    _mtd_order_where = f"""
        o.ORDER_TYPE = 'standard' AND o.CANCELLATION = 'F'
        AND CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(o.ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE
            >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
        AND CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(o.ORDER_CREATED_AT AS TIMESTAMP_NTZ))::DATE
            <  CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE
    """

    def _pct_list(df) -> list:
        total = df["item_revenue"].sum()
        if total == 0:
            return []
        return [
            {"name": row["category"], "pct": float(row["item_revenue"]) / total}
            for _, row in df.sort_values("item_revenue", ascending=False).iterrows()
            if row["category"] is not None
        ]

    _item_base = f"""
        FROM PROD.ID_WAREHOUSE.ORDER_ITEMS oi
        JOIN PROD.ID_WAREHOUSE.PRODUCTS p ON oi.CATALOG_PRODUCT_ID = p.CATALOG_PRODUCT_ID
        JOIN PROD.ID_WAREHOUSE.ORDERS o   ON oi.SALES_ORDER_ID = o.SALES_ORDER_ID
        WHERE {_mtd_order_where}
    """

    product_contribution_df = _query(f"""
        SELECT p.CLASS          AS category, SUM(oi.PRICE) AS item_revenue
        {_item_base}
          AND p.CLASS IS NOT NULL
        GROUP BY p.CLASS
    """)

    collection_df = _query(f"""
        SELECT p.COLLECTION     AS category, SUM(oi.PRICE) AS item_revenue
        {_item_base}
          AND p.COLLECTION IS NOT NULL
        GROUP BY p.COLLECTION
    """)

    fabric_df = _query(f"""
        SELECT p.FABRIC_FAMILY  AS category, SUM(oi.PRICE) AS item_revenue
        {_item_base}
          AND p.FABRIC_FAMILY IS NOT NULL
        GROUP BY p.FABRIC_FAMILY
    """)

    return {
        "product_contribution": _pct_list(product_contribution_df),
        "collection":           _pct_list(collection_df),
        "fabric":               _pct_list(fabric_df),
    }


def fetch_by_studio() -> list:
    """MTD discounted revenue and order count by studio (LOCATION), sorted by revenue descending."""
    df = _query(f"""
        SELECT
            LOCATION                                                         AS studio,
            SUM(subtotal - ABS(discount_amount) + shipping_amount)          AS revenue,
            COUNT(*)                                                         AS orders
        FROM PROD.ID_WAREHOUSE.ORDERS
        WHERE {_ORDER_FILTER}
          AND {_DENVER_DATE} >= DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE)
          AND {_DENVER_DATE} <  CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE
          AND LOCATION IS NOT NULL
        GROUP BY LOCATION
        ORDER BY revenue DESC
    """)

    return [
        {"studio": row["studio"], "revenue": float(row["revenue"]), "orders": int(row["orders"])}
        for _, row in df.iterrows()
    ]


def fetch_all() -> dict:
    """Run all collectors and return the full data contract for the email report."""
    import datetime

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    orders   = fetch_yesterday_orders()
    assisted = fetch_yesterday_assisted()
    mtd      = fetch_mtd_orders()
    repeat   = fetch_mtd_repeat_pct()

    return {
        "report_date": yesterday,
        "yesterday": {
            **orders,
            **assisted,
        },
        "mtd": {
            **mtd,
            "repeat_pct": repeat,
        },
        "engagements": fetch_engagements(),
        "swatches":    fetch_swatches(),
        "merch_mix":   fetch_merch_mix(),
        "by_studio":   fetch_by_studio(),
    }


def fetch_forecast(dates: list) -> dict:
    """Pull daily forecast from FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST.

    Used by the Total Business tab (matches Looker's FwUaEg4OKq7RHaff4IXB5A source).
    Sales Team tab uses the Google Sheet forecast instead.

    Args:
        dates: list of 'YYYY-MM-DD' strings to fetch

    Returns:
        {date_str: forecast_amount} for each requested date,
        plus 'yesterday', 'mtd', 'last_week' convenience keys.
    """
    if not dates:
        return {}

    quoted = ", ".join(f"'{d}'" for d in dates)
    df = _query(f"""
        SELECT TO_DATE(Date) AS day, ID_FORECASTED_ADJUSTED_GROSS_BOOKINGS AS forecast
        FROM FIVETRAN_DB.UPLOADS.ALL_COMPANY_DAILY_FORECAST
        WHERE TO_DATE(Date) IN ({quoted})
        ORDER BY 1
    """)

    result = {str(row["day"]): float(row["forecast"]) for _, row in df.iterrows()}
    result["mtd"]       = sum(result.get(d, 0) for d in dates)
    result["last_week"] = result["mtd"]  # convenience alias
    return result
