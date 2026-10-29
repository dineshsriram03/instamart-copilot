from itertools import combinations
from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
DATABASE = ROOT / "data" / "instamart.db"

orders = pd.read_csv(CLEAN / "orders.csv")
customers = pd.read_csv(CLEAN / "customers.csv")
products = pd.read_csv(CLEAN / "products.csv")

completed = orders.loc[orders["status"].eq("completed")].copy()

# Add city and product category for the pivot and city summaries.
analysis = completed.merge(
    customers[["customer_id", "city"]],
    on="customer_id",
    how="left",
    validate="many_to_one",
).merge(
    products[["product_id", "category"]],
    on="product_id",
    how="left",
    validate="many_to_one",
)

# Rebuild the SQL city/category revenue table with a grand-total margin.
pivot = pd.pivot_table(
    analysis,
    index="city",
    columns="category",
    values="order_amount",
    aggfunc="sum",
    fill_value=0,
    margins=True,
    margins_name="All",
)

with sqlite3.connect(DATABASE) as connection:
    sql_total = pd.read_sql_query(
        """
        SELECT SUM(order_amount) AS total_revenue
        FROM orders
        WHERE status = 'completed'
        """,
        connection,
    ).loc[0, "total_revenue"]

pivot_total = pivot.loc["All", "All"]
print("=== Q2 PANDAS CROSS-CHECK ===")
print(pivot.to_string(float_format=lambda value: f"{value:,.2f}"))
print(f"\nSQL total: INR {sql_total:.2f}")
print(f"Pivot-table grand total: INR {pivot_total:.2f}")
print(f"Totals match: {round(sql_total, 2) == round(pivot_total, 2)}")

# Completed-order amount summary by city.
city_summary = analysis.groupby("city").agg(
    sum=("order_amount", "sum"),
    mean=("order_amount", "mean"),
    count=("order_amount", "count"),
)
print("\n=== COMPLETED ORDER AMOUNT BY CITY ===")
print(city_summary.to_string(float_format=lambda value: f"{value:,.2f}"))

# Distribution statistics and 1.5-IQR outlier fences.
amount = completed["order_amount"]
q1 = amount.quantile(0.25)
median = amount.median()
q3 = amount.quantile(0.75)
iqr = q3 - q1
lower_fence = q1 - 1.5 * iqr
upper_fence = q3 + 1.5 * iqr
outliers_below = int(amount.lt(lower_fence).sum())
outliers_above = int(amount.gt(upper_fence).sum())

print("\n=== COMPLETED ORDER AMOUNT DISTRIBUTION ===")
print(f"Mean: INR {amount.mean():.2f}")
print(f"Median: INR {median:.2f}")
print(f"Skewness: {amount.skew():.2f}")
print(f"Q1: INR {q1:.2f}")
print(f"Q3: INR {q3:.2f}")
print(f"Lower 1.5-IQR fence: INR {lower_fence:.2f}")
print(f"Upper 1.5-IQR fence: INR {upper_fence:.2f}")
print(f"Outliers below lower fence: {outliers_below}")
print(f"Outliers above upper fence: {outliers_above}")

# Correlations among the four fields required by the brief.
correlation_columns = [
    "order_amount",
    "discount_pct",
    "quantity",
    "delivery_minutes",
]
correlations = completed[correlation_columns].corr()
pairs = [
    (left, right, correlations.loc[left, right])
    for left, right in combinations(correlation_columns, 2)
]
largest_pair = max(pairs, key=lambda item: abs(item[2]))

print("\n=== CORRELATION MATRIX ===")
print(correlations.to_string(float_format=lambda value: f"{value:.3f}"))
print(
    "\nLargest absolute correlation: "
    f"{largest_pair[0]} and {largest_pair[1]} "
    f"({largest_pair[2]:+.3f})"
)