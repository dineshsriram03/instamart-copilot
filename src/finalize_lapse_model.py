from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "outputs" / "lapse_dataset.csv"
OUTPUTS = ROOT / "outputs"
FOREST_FILE = OUTPUTS / "random_forest_model.joblib"
LOGISTIC_FILE = OUTPUTS / "logistic_model.joblib"
FINAL_MODEL_FILE = OUTPUTS / "lapse_model.joblib"
SEGMENTS_FILE = OUTPUTS / "customer_segments.csv"
RETENTION_FILE = OUTPUTS / "retention_list.csv"

NUMERIC_FEATURES = [
    "recency",
    "frequency",
    "monetary",
    "average_discount_pct",
    "cancellation_rate",
    "average_delivery_minutes",
    "age",
    "tenure_days",
]
CATEGORICAL_FEATURES = ["city", "gender", "favorite_category"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

data = pd.read_csv(DATA_FILE)
X = data.set_index("customer_id")[FEATURES]
y = data.set_index("customer_id")["lapsed"].astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    stratify=y,
    random_state=42,
)

forest_model = joblib.load(FOREST_FILE)
logistic_model = joblib.load(LOGISTIC_FILE)

# Report the five strongest Random Forest features.
forest_preprocessor = forest_model.named_steps["preprocess"]
forest_feature_names = forest_preprocessor.get_feature_names_out()
forest_classifier = forest_model.named_steps["classifier"]
forest_importance = pd.Series(
    forest_classifier.feature_importances_,
    index=forest_feature_names,
).sort_values(ascending=False)

print("=== RANDOM FOREST: TOP FIVE FEATURES ===")
print(forest_importance.head(5).to_string(float_format=lambda value: f"{value:.4f}"))

# Report three Logistic Regression coefficients with the largest absolute values.
logistic_preprocessor = logistic_model.named_steps["preprocess"]
logistic_feature_names = logistic_preprocessor.get_feature_names_out()
logistic_classifier = logistic_model.named_steps["classifier"]
logistic_coefficients = pd.Series(
    logistic_classifier.coef_[0],
    index=logistic_feature_names,
)
top_coefficients = logistic_coefficients.loc[
    logistic_coefficients.abs().sort_values(ascending=False).head(3).index
]

print("\n=== LOGISTIC REGRESSION: THREE LARGEST COEFFICIENTS ===")
for feature, coefficient in top_coefficients.items():
    print(f"{feature}: {coefficient:+.4f}")

# The Random Forest had the higher lapsed-class test F1, so persist it.
joblib.dump(forest_model, FINAL_MODEL_FILE)
reloaded_model = joblib.load(FINAL_MODEL_FILE)

original_predictions = forest_model.predict(X_test)
reloaded_predictions = reloaded_model.predict(X_test)
predictions_match = np.array_equal(original_predictions, reloaded_predictions)
assert predictions_match, "Reloaded model predictions differ from the original."
print(f"\nReloaded model predictions match exactly: {predictions_match}")
print(f"Saved selected model: {FINAL_MODEL_FILE}")

# Premium is a post-hoc whole-window segment label, used only to filter the
# already-created test set for the illustrative retention list.
segments = pd.read_csv(SEGMENTS_FILE)
premium_mask = segments["is_premium"].astype("string").str.lower().eq("true")
premium_ids = set(segments.loc[premium_mask, "customer_id"])
premium_test_ids = [customer_id for customer_id in X_test.index if customer_id in premium_ids]
premium_test = X_test.loc[premium_test_ids]

lapse_probability = reloaded_model.predict_proba(premium_test)[:, 1]
retention = pd.DataFrame(
    {
        "customer_id": premium_test.index,
        "lapse_probability": lapse_probability,
        "actually_lapsed": y_test.loc[premium_test.index].to_numpy(),
    }
)
retention = retention.sort_values(
    "lapse_probability",
    ascending=False,
).head(10)

retention = retention[
    ["customer_id", "lapse_probability", "actually_lapsed"]
]
retention.to_csv(RETENTION_FILE, index=False)

print(f"\nPremium customers in test set: {len(premium_test)}")
print(f"Retention-list rows: {len(retention)}")
print(f"Actually lapsed on retention list: {int(retention['actually_lapsed'].sum())}")
print(f"Saved retention list: {RETENTION_FILE}")
print("\nRetention list:")
print(retention.to_string(index=False))