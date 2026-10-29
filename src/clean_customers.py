from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

customers = pd.read_csv(RAW / "customers.csv")

# Standardize city names.
customers["city"] = customers["city"].astype("string").str.strip().str.title()

# Normalize gender spellings, then map them to the three required values.
gender = (
    customers["gender"]
    .fillna("")
    .astype("string")
    .str.strip()
    .str.casefold()
)
gender_map = {
    "male": "male",
    "m": "male",
    "female": "female",
    "f": "female",
}
customers["gender"] = gender.map(gender_map).fillna("unknown")

# Convert age to numbers, mark values outside 10-100 as missing,
# and fill missing ages with the median for that customer's city.
customers["age"] = pd.to_numeric(customers["age"], errors="coerce")
customers.loc[~customers["age"].between(10, 100), "age"] = pd.NA
city_medians = customers.groupby("city")["age"].transform("median")
customers["age"] = customers["age"].fillna(city_medians)

# Convert signup_date to a real date.
customers["signup_date"] = pd.to_datetime(customers["signup_date"])

# Save the cleaned table without changing the raw input.
CLEAN.mkdir(parents=True, exist_ok=True)
customers.to_csv(CLEAN / "customers.csv", index=False)

print("City counts:")
print(customers["city"].value_counts().to_string())
print("\nGender counts:")
print(customers["gender"].value_counts().to_string())
print(f"\nMissing ages: {int(customers['age'].isna().sum())}")
print(f"Age range: {customers['age'].min():.0f} to {customers['age'].max():.0f}")
print(f"\nSaved: {CLEAN / 'customers.csv'}")