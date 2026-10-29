from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT_FILE = ROOT / "outputs" / "lapse_dataset.csv"
CUTOFF = pd.Timestamp("2025-09-01 00:00:00")
SEPTEMBER_END = pd.Timestamp("2025-10-01 00:00:00")

orders = pd.read_csv(DATA / "clean" / "orders.csv")
customers = pd.read_csv(DATA / "clean" / "customers.csv")
products = pd.read_csv(DATA / "clean" / "products.csv")

orders["order_ts"] = pd.to_datetime(orders["order_ts"])
customers["signup_date"] = pd.to_datetime(customers["signup_date"])

# Only orders before the cutoff are used to build features.
pre_cutoff = orders.loc[orders["order_ts"] < CUTOFF].copy()
completed_pre = pre_cutoff.loc[pre_cutoff["status"].eq("completed")].copy()

# The cohort includes customers with at least one completed pre-cutoff order.
cohort_ids = completed_pre["customer_id"].unique()

features = (
    completed_pre.groupby("customer_id")
    .agg(
        last_order_ts=("order_ts", "max"),
        frequency=("order_id", "nunique"),
        monetary=("order_amount", "sum"),
        average_discount_pct=("discount_pct", "mean"),
        average_delivery_minutes=("delivery_minutes", "mean"),
    )
    .reset_index()
)
features["recency"] = (CUTOFF - features["last_order_ts"]).dt.days

# Find each customer's most frequently ordered product category.
completed_with_category = completed_pre.merge(
    products[["product_id", "category"]],
    on="product_id",
    how="left",
    validate="many_to_one",
)
category_counts = (
    completed_with_category.groupby(["customer_id", "category"])
    .size()
    .reset_index(name="order_count")
    .sort_values(
        ["customer_id", "order_count", "category"],
        ascending=[True, False, True],
    )
)
favorite_category = (
    category_counts.drop_duplicates("customer_id")
    [["customer_id", "category"]]
    .rename(columns={"category": "favorite_category"})
)

# Cancellation rate uses completed and cancelled final-status orders before cutoff.
final_pre = pre_cutoff.loc[
    pre_cutoff["status"].isin(["completed", "cancelled"])
]
cancellation = final_pre.groupby("customer_id").agg(
    cancelled_count=("status", lambda values: values.eq("cancelled").sum()),
    final_order_count=("status", "size"),
)
cancellation["cancellation_rate"] = (
    cancellation["cancelled_count"] / cancellation["final_order_count"]
)
cancellation = cancellation[["cancellation_rate"]].reset_index()

# Add customer details, category preference, and cancellation rate.
dataset = (
    customers.loc[
        customers["customer_id"].isin(cohort_ids),
        ["customer_id", "city", "age", "gender", "signup_date"],
    ]
    .merge(features, on="customer_id", how="inner", validate="one_to_one")
    .merge(favorite_category, on="customer_id", how="left", validate="one_to_one")
    .merge(cancellation, on="customer_id", how="left", validate="one_to_one")
)
dataset["tenure_days"] = (CUTOFF - dataset["signup_date"]).dt.days

# September completed orders are used only for the target label.
september_completed = orders.loc[
    orders["status"].eq("completed")
    & orders["order_ts"].ge(CUTOFF)
    & orders["order_ts"].lt(SEPTEMBER_END),
    "customer_id",
].unique()
dataset["lapsed"] = (~dataset["customer_id"].isin(september_completed)).astype(int)

feature_columns = [
    "recency",
    "frequency",
    "monetary",
    "average_discount_pct",
    "cancellation_rate",
    "average_delivery_minutes",
    "favorite_category",
    "city",
    "age",
    "gender",
    "tenure_days",
]
assert not dataset[feature_columns].isna().any().any(), (
    "A lapse-model feature contains a missing value."
)

dataset = dataset.sort_values("customer_id").reset_index(drop=True)
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
dataset.to_csv(OUTPUT_FILE, index=False)

lapsed_count = int(dataset["lapsed"].sum())
print(f"Cohort customers: {len(dataset)}")
print(f"Lapsed customers: {lapsed_count} ({lapsed_count / len(dataset):.2%})")
print(f"Not-lapsed customers: {len(dataset) - lapsed_count}")
print(f"Feature columns: {len(feature_columns)}")
print("Missing feature values: 0")
print(f"Saved: {OUTPUT_FILE}")