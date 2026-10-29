from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

orders = pd.read_csv(RAW / "orders.csv")
products = pd.read_csv(RAW / "products.csv")

# Convert timestamps first, then remove exact duplicate rows.
orders["order_ts"] = pd.to_datetime(orders["order_ts"])
orders = orders.drop_duplicates()

# For repeated order IDs, keep the record with the latest timestamp.
orders = orders.sort_values(["order_id", "order_ts"], kind="mergesort")
orders = orders.drop_duplicates(subset="order_id", keep="last").copy()

# Add product price and category temporarily for the cleaning rules below.
orders = orders.merge(
    products[["product_id", "price_inr", "category"]],
    on="product_id",
    how="left",
    validate="many_to_one",
)

# Convert amounts to numbers. Fill missing amounts using price, quantity, and discount.
orders["order_amount"] = pd.to_numeric(orders["order_amount"], errors="coerce")
fallback_amount = (
    orders["price_inr"]
    * orders["quantity"]
    * (1 - orders["discount_pct"] / 100)
).round(2)
orders["order_amount"] = orders["order_amount"].fillna(fallback_amount)

# Treat negative delivery times as missing.
orders["delivery_minutes"] = pd.to_numeric(
    orders["delivery_minutes"], errors="coerce"
)
orders.loc[orders["delivery_minutes"] < 0, "delivery_minutes"] = pd.NA

# Fill missing delivery times only for completed orders,
# using the median for that product category.
completed = orders["status"].astype("string").str.strip().str.lower().eq("completed")
category_medians = (
    orders.loc[completed]
    .groupby("category")["delivery_minutes"]
    .transform("median")
)
orders.loc[completed, "delivery_minutes"] = (
    orders.loc[completed, "delivery_minutes"].fillna(category_medians)
)

# Remove the temporary product lookup columns.
orders = orders.drop(columns=["price_inr", "category"])

# Store timestamps in the required text format.
orders["order_ts"] = orders["order_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")

# Save clean orders and a clean copy of the products table.
CLEAN.mkdir(parents=True, exist_ok=True)
orders.to_csv(CLEAN / "orders.csv", index=False)
products.to_csv(CLEAN / "products.csv", index=False)

cancelled = orders["status"].astype("string").str.strip().str.lower().eq("cancelled")

print(f"Order rows: {len(orders)}")
print("Status counts:")
print(orders["status"].value_counts().to_string())
print(f"Pending rows: {int(orders['status'].eq('pending').sum())}")
print(f"Missing order amounts: {int(orders['order_amount'].isna().sum())}")
print(
    "Missing delivery times among completed orders: "
    f"{int(orders.loc[completed, 'delivery_minutes'].isna().sum())}"
)
print(
    "Missing delivery times among cancelled orders: "
    f"{int(orders.loc[cancelled, 'delivery_minutes'].isna().sum())}"
)
completed_sum = orders.loc[completed, "order_amount"].sum()
print(f"Completed order amount total: INR {completed_sum:.2f}")
print(f"\nSaved clean files to: {CLEAN}")