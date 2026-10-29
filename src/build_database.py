from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
DATABASE = ROOT / "data" / "instamart.db"

tables = {
    "customers": pd.read_csv(CLEAN / "customers.csv"),
    "products": pd.read_csv(CLEAN / "products.csv"),
    "orders": pd.read_csv(CLEAN / "orders.csv", dtype={"order_ts": "string"}),
}

DATABASE.parent.mkdir(parents=True, exist_ok=True)

with sqlite3.connect(DATABASE) as connection:
    for table_name, df in tables.items():
        df.to_sql(table_name, connection, if_exists="replace", index=False)

        row_count = pd.read_sql_query(
            f"SELECT COUNT(*) AS row_count FROM {table_name}",
            connection,
        ).iloc[0, 0]
        print(f"{table_name}: {row_count} rows")

print(f"\nSaved database: {DATABASE}")
print(f"SQLite version: {sqlite3.sqlite_version}")