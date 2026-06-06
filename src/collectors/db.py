import os
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()


def _connect():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ.get("SNOWFLAKE_DATABASE", "PROD"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "ID_WAREHOUSE"),
    )


def _query(sql: str) -> pd.DataFrame:
    conn = _connect()
    try:
        df = pd.read_sql(sql, conn)
        df.columns = [c.lower() for c in df.columns]
        return df
    finally:
        conn.close()
