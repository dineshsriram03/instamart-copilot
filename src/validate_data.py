from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
DATABASE = ROOT / "data" / "instamart.db"

customers = pd.read_csv(CLEAN / "customers.csv")
products = pd.read_csv(CLEAN / "products.csv")
orders = pd.read_csv(CLEAN / "orders.csv")

# Customer reference checkpoints.
assert customers["city"].value_counts().to_dict() == {
    "Pune": 227,
    "Delhi": 210,
    "Bengaluru": 197,
    "Chennai": 191,
    "Hyderabad": 191,
    "Mumbai": 184,
}, "Customer city counts do not match the brief."

assert customers["gender"].value_counts().to_dict() == {
    "female": 610,
    "male": 560,
    "unknown": 30,
}, "Customer gender counts do not match the brief."

assert customers["age"].notna().all(), "Some customer ages are missing."
assert customers["age"].between(18, 60).all(), "A customer age is outside 18-60."
assert pd.to_datetime(customers["signup_date"], errors="coerce").notna().all(), (
    "Some signup dates could not be parsed."
)

# Order reference checkpoints.
assert len(orders) == 12309, "Clean order row count does not match the brief."
assert orders["order_id"].nunique() == 12309, "Order IDs are not unique."
assert orders["status"].value_counts().to_dict() == {
    "completed": 11110,
    "cancelled": 1199,
}, "Order status counts do not match the brief."
assert not orders["status"].eq("pending").any(), "Pending orders remain."
assert orders["order_amount"].notna().all(), "Some order amounts are missing."

completed = orders["status"].eq("completed")
cancelled = orders["status"].eq("cancelled")

assert orders.loc[completed, "delivery_minutes"].notna().all(), (
    "A completed order is missing its delivery time."
)
assert orders.loc[cancelled, "delivery_minutes"].isna().all(), (
    "A cancelled order has a delivery time."
)
assert round(orders.loc[completed, "order_amount"].sum(), 2) == 2998668.80, (
    "Completed-order total does not match the brief."
)
assert orders["order_ts"].astype("string").str.fullmatch(
    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
).all(), "An order timestamp has the wrong text format."

# Confirm the clean database tables were written.
assert len(products) == 40, "Clean product row count should be 40."

with sqlite3.connect(DATABASE) as connection:
    for table_name, expected_rows in {
        "customers": 1200,
        "products": 40,
        "orders": 12309,
    }.items():
        actual_rows = pd.read_sql_query(
            f"SELECT COUNT(*) AS row_count FROM {table_name}",
            connection,
        ).iloc[0, 0]
        assert actual_rows == expected_rows, (
            f"Database table {table_name} has an unexpected row count."
        )

    timestamp_type = pd.read_sql_query(
        "SELECT typeof(order_ts) AS value_type FROM orders LIMIT 1",
        connection,
    ).iloc[0, 0]
    assert timestamp_type == "text", "Database order_ts values should be text."

print("ALL CHECKPOINTS PASSED")