import datetime
from src.collectors.db import _query

_DENVER_NOW   = "CONVERT_TIMEZONE('UTC', 'America/Denver', CURRENT_TIMESTAMP())::DATE"
_DEAL_DATE    = "CONVERT_TIMEZONE('UTC', 'America/Denver', CAST(CREATE_DATE AS TIMESTAMP_NTZ))::DATE"
_STAFF_EXCL   = "(DEAL_OWNER_EMAIL NOT LIKE '%@interiordefine.com%' OR DEAL_OWNER_EMAIL IS NULL)"


def fetch_deals() -> dict:
    """MTD deal/CVR metrics from STG_DEAL. Excludes staff-owned deals."""
    today         = datetime.date.today()
    yesterday     = today - datetime.timedelta(days=1)
    month_start   = today.replace(day=1)
    mature_cutoff = today - datetime.timedelta(days=14)

    overview = _query(f"""
        SELECT
            COUNT(*)                                                                   AS inbound_total,
            SUM(IS_CONVERTED)                                                          AS closed_won,
            SUM(CASE WHEN {_DEAL_DATE} < '{mature_cutoff}' THEN 1 ELSE 0 END)         AS mature_cohort,
            SUM(CASE WHEN {_DEAL_DATE} < '{mature_cutoff}'
                          AND "14_DAY_CONVERTED" = 1 THEN 1 ELSE 0 END)               AS mature_14day_converted,
            SUM(CASE WHEN MEANINGFUL_CONTACT = 1 THEN 1 ELSE 0 END)                   AS meaningful_total,
            SUM(CASE WHEN MEANINGFUL_CONTACT = 1
                          AND IS_CONVERTED = 1 THEN 1 ELSE 0 END)                     AS meaningful_converted,
            SUM(CASE WHEN {_DEAL_DATE} = '{yesterday}' THEN 1 ELSE 0 END)             AS inbound_yesterday
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND {_STAFF_EXCL}
    """)

    by_studio = _query(f"""
        SELECT
            STUDIO_NAME                AS studio_name,
            COUNT(*)                   AS inbound,
            SUM(IS_CONVERTED)          AS closed_won
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND {_STAFF_EXCL}
          AND STUDIO_NAME IS NOT NULL
        GROUP BY STUDIO_NAME
        ORDER BY inbound DESC
    """)

    by_rep = _query(f"""
        SELECT
            DEAL_OWNER_EMAIL           AS rep,
            COUNT(*)                   AS inbound,
            SUM(IS_CONVERTED)          AS closed_won
        FROM PROD.ID_WAREHOUSE.STG_DEAL
        WHERE {_DEAL_DATE} >= '{month_start}'
          AND {_DEAL_DATE} <  '{today}'
          AND DEAL_OWNER_EMAIL IS NOT NULL
          AND DEAL_OWNER_EMAIL NOT LIKE '%@interiordefine.com%'
        GROUP BY DEAL_OWNER_EMAIL
        ORDER BY inbound DESC
        LIMIT 20
    """)

    row        = overview.iloc[0]
    mature     = int(row["mature_cohort"])
    meaningful = int(row["meaningful_total"])

    def _studio_list(df):
        return [
            {
                "studio":     r["studio_name"],
                "inbound":    int(r["inbound"]),
                "closed_won": int(r["closed_won"]),
                "cvr":        int(r["closed_won"]) / int(r["inbound"]) if int(r["inbound"]) else 0.0,
            }
            for _, r in df.iterrows()
        ]

    def _rep_list(df):
        return [
            {
                "rep":        r["rep"],
                "inbound":    int(r["inbound"]),
                "closed_won": int(r["closed_won"]),
                "cvr":        int(r["closed_won"]) / int(r["inbound"]) if int(r["inbound"]) else 0.0,
            }
            for _, r in df.iterrows()
        ]

    return {
        "inbound_mtd":        int(row["inbound_total"]),
        "inbound_yesterday":  int(row["inbound_yesterday"]),
        "cvr_14day_mtd":      int(row["mature_14day_converted"]) / mature if mature else 0.0,
        "cvr_meaningful_mtd": int(row["meaningful_converted"]) / meaningful if meaningful else 0.0,
        "by_studio":          _studio_list(by_studio),
        "by_rep":             _rep_list(by_rep),
    }
