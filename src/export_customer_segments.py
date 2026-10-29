from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = ROOT / "outputs" / "rfm_clusters.csv"
OUTPUT_FILE = ROOT / "outputs" / "customer_segments.csv"

segment_names = {
    0: "Occasional Shoppers",
    1: "Premium Customers",
    2: "Loyal Regulars",
    3: "At-Risk Customers",
}

recommended_actions = {
    0: "Send relevant bundles to encourage another purchase.",
    1: "Offer tailored loyalty rewards to retain high-value customers.",
    2: "Promote replenishment reminders and relevant add-ons.",
    3: "Send a focused win-back offer.",
}

segments = pd.read_csv(INPUT_FILE)

# Mark as Premium the segment with the highest mean monetary value.
premium_id = int(segments.groupby("segment_id")["monetary"].mean().idxmax())

segments["segment_name"] = segments["segment_id"].map(segment_names)
segments["is_premium"] = segments["segment_id"].eq(premium_id)

print("=== SEGMENT PROFILE AND ACTIONS ===")
profile = segments.groupby("segment_id").agg(
    size=("customer_id", "count"),
    mean_recency=("recency", "mean"),
    mean_frequency=("frequency", "mean"),
    mean_monetary=("monetary", "mean"),
    segment_name=("segment_name", "first"),
    is_premium=("is_premium", "first"),
)

for segment_id, row in profile.iterrows():
    print(
        f"\n{segment_id}: {row['segment_name']} "
        f"(Premium: {row['is_premium']})"
    )
    print(
        f"  Size: {int(row['size'])}; "
        f"mean recency: {row['mean_recency']:.2f}; "
        f"mean frequency: {row['mean_frequency']:.2f}; "
        f"mean monetary: INR {row['mean_monetary']:.2f}"
    )
    print(f"  Action: {recommended_actions[segment_id]}")

columns = [
    "customer_id",
    "recency",
    "frequency",
    "monetary",
    "segment_id",
    "segment_name",
    "is_premium",
]
segments[columns].sort_values("customer_id").to_csv(OUTPUT_FILE, index=False)

print(f"\nPremium segment ID: {premium_id}")
print(f"Premium customers: {int(segments['is_premium'].sum())}")
print(f"Saved: {OUTPUT_FILE}")