from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
QUERY_FILE = ROOT / "sql" / "queries.sql"
DATABASE = ROOT / "data" / "instamart.db"

query_text = QUERY_FILE.read_text(encoding="utf-8")
queries = [query.strip() for query in query_text.split(";") if query.strip()]

if len(queries) != 7:
    raise ValueError(f"Expected 7 SQL queries, found {len(queries)}.")

with sqlite3.connect(DATABASE) as connection:
    results = [
        pd.read_sql_query(query, connection)
        for query in queries
    ]

print(f"Q1 customers: {len(results[0])}")

q2 = results[1]
largest_cell = q2.loc[q2["revenue"].idxmax()]
print(f"Q2 rows: {len(q2)}")
print(f"Q2 total revenue: INR {q2['revenue'].sum():.2f}")
print(
    "Q2 largest cell: "
    f"{largest_cell['city']} / {largest_cell['category']} "
    f"at INR {largest_cell['revenue']:.2f}"
)

print(f"Q3 products: {len(results[2])}")
print(f"Q4 customers without completed orders: {len(results[3])}")

q5 = results[4]
print(f"Q5 customers above average spend: {len(q5)}")
print(f"Q5 average customer spend: INR {q5['average_spend'].iloc[0]:.2f}")

q6 = results[5]
print("Q6 top customer in each city:")
print(
    q6.loc[q6["row_number"].eq(1), ["city", "customer_id", "total_spend"]]
    .to_string(index=False)
)
rank_differences = int(q6["spend_rank"].ne(q6["row_number"]).sum())
print(f"Q6 rows where RANK differs from ROW_NUMBER: {rank_differences}")

q7 = results[6]
print(f"Q7 daily rows: {len(q7)}")
print(f"Q7 final cumulative revenue: INR {q7['cumulative_revenue'].iloc[-1]:.2f}")