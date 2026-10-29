from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ORDERS_FILE = ROOT / "data" / "clean" / "orders.csv"
OUTPUT_FILE = ROOT / "outputs" / "rfm.csv"
SNAPSHOT = pd.Timestamp("2025-10-01 00:00:00")

orders = pd.read_csv(ORDERS_FILE)
completed = orders.loc[orders["status"].eq("completed")].copy()
completed["order_ts"] = pd.to_datetime(completed["order_ts"])

rfm = (
    completed.groupby("customer_id")
    .agg(
        last_order_ts=("order_ts", "max"),
        frequency=("order_id", "nunique"),
        monetary=("order_amount", "sum"),
    )
    .reset_index()
)

rfm["recency"] = (SNAPSHOT - rfm["last_order_ts"]).dt.days
rfm = rfm[["customer_id", "recency", "frequency", "monetary"]]

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
rfm.to_csv(OUTPUT_FILE, index=False)

print(f"RFM customers: {len(rfm)}")
print(
    f"Recency days: median={rfm['recency'].median():.0f}, "
    f"min={rfm['recency'].min()}, max={rfm['recency'].max()}"
)
print(
    f"Frequency: mean={rfm['frequency'].mean():.2f}, "
    f"max={rfm['frequency'].max()}"
)
print(
    f"Monetary: mean=INR {rfm['monetary'].mean():.2f}, "
    f"max=INR {rfm['monetary'].max():.2f}"
)
print(f"Saved: {OUTPUT_FILE}")