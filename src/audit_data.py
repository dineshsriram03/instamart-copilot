from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

tables = {
    "customers": pd.read_csv(RAW / "customers.csv"),
    "products": pd.read_csv(RAW / "products.csv"),
    "orders": pd.read_csv(RAW / "orders.csv"),
}

# Show each table's size, column types, and missing values.
for name, df in tables.items():
    print(f"\n=== {name.upper()} ===")
    print(f"Shape: {df.shape}")
    print("Data types:")
    print(df.dtypes.to_string())
    print("Missing values (count and percent):")
    for column in df.columns:
        count = int(df[column].isna().sum())
        percent = df[column].isna().mean() * 100
        print(f"  {column}: {count} ({percent:.2f}%)")

orders = tables["orders"]
customers = tables["customers"]

amount_numeric = pd.to_numeric(orders["order_amount"], errors="coerce")
delivery_numeric = pd.to_numeric(orders["delivery_minutes"], errors="coerce")
age_numeric = pd.to_numeric(customers["age"], errors="coerce")
raw_gender = customers["gender"].fillna("").astype(str)

print("\n=== REQUIRED RAW AUDIT FIGURES ===")
print(f"Raw orders rows: {len(orders)}")
print(f"Exact duplicate order rows: {int(orders.duplicated().sum())}")
print(
    "Pending order rows: "
    f"{int(orders['status'].astype(str).str.strip().str.lower().eq('pending').sum())}"
)
print(f"Distinct order IDs: {int(orders['order_id'].nunique())}")
print(f"Non-numeric order amounts: {int(amount_numeric.isna().sum())}")
print(f"Negative delivery times: {int(delivery_numeric.lt(0).sum())}")
print(
    "Blank delivery times: "
    f"{int(orders['delivery_minutes'].astype('string').fillna('').str.strip().eq('').sum())}"
)
print(
    "Blank customer ages: "
    f"{int(customers['age'].astype('string').fillna('').str.strip().eq('').sum())}"
)
print(
    "Ages outside 10-100: "
    f"{int((age_numeric.notna() & (age_numeric.lt(10) | age_numeric.gt(100))).sum())}"
)
print(f"Distinct raw city spellings: {int(customers['city'].nunique())}")
print(
    "Distinct non-blank raw gender spellings: "
    f"{int(customers.loc[raw_gender.str.strip().ne(''), 'gender'].nunique())}"
)
print(f"Blank genders: {int(raw_gender.str.strip().eq('').sum())}")