from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
RFM_FILE = ROOT / "outputs" / "rfm.csv"
OUTPUT_FILE = ROOT / "outputs" / "rfm_clusters.csv"

rfm = pd.read_csv(RFM_FILE)
features = ["recency", "frequency", "monetary"]

scaler = StandardScaler()
scaled_rfm = scaler.fit_transform(rfm[features])

# Compare inertia and silhouette for K values 2 through 8.
metrics = []
for k in range(2, 9):
    model = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = model.fit_predict(scaled_rfm)
    metrics.append(
        {
            "K": k,
            "inertia": model.inertia_,
            "silhouette": silhouette_score(scaled_rfm, labels),
        }
    )

print("=== K-MEANS COMPARISON ===")
print(pd.DataFrame(metrics).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

# Use K=4, then inspect the unscaled RFM averages for each segment.
chosen_k = 4
final_model = KMeans(n_clusters=chosen_k, n_init=10, random_state=42)
rfm["segment_id"] = final_model.fit_predict(scaled_rfm)

profile = rfm.groupby("segment_id").agg(
    size=("customer_id", "count"),
    mean_recency=("recency", "mean"),
    mean_frequency=("frequency", "mean"),
    mean_monetary=("monetary", "mean"),
)

print("\n=== K=4 SEGMENT PROFILE ===")
print(profile.to_string(float_format=lambda x: f"{x:.2f}"))

# Report the first two principal components' explained variance.
pca = PCA(n_components=2)
pca.fit(scaled_rfm)
print("\n=== PCA ===")
print(f"Explained variance ratios: {pca.explained_variance_ratio_}")
print(f"Total explained variance: {pca.explained_variance_ratio_.sum():.3f}")

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
rfm.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved: {OUTPUT_FILE}")