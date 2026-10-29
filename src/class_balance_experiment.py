from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "outputs" / "lapse_dataset.csv"
OUTPUTS = ROOT / "outputs"

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

# Keep all original training rows and add sampled lapsed rows until balanced.
training = X_train.copy()
training["lapsed"] = y_train

lapsed_rows = training.loc[training["lapsed"].eq(1)]
not_lapsed_count = int(training["lapsed"].eq(0).sum())
lapsed_count = len(lapsed_rows)
extra_needed = not_lapsed_count - lapsed_count

extra_lapsed = lapsed_rows.sample(
    n=extra_needed,
    replace=True,
    random_state=42,
)
balanced_training = pd.concat([training, extra_lapsed], ignore_index=True)
balanced_training = balanced_training.sample(
    frac=1,
    random_state=42,
).reset_index(drop=True)

X_balanced = balanced_training[FEATURES]
y_balanced = balanced_training["lapsed"].astype(int)

# Reuse the best C from the unbalanced logistic regression grid search.
unbalanced_model = joblib.load(OUTPUTS / "logistic_model.joblib")
best_c = unbalanced_model.named_steps["classifier"].C

preprocessing = ColumnTransformer(
    transformers=[
        ("numeric", StandardScaler(), NUMERIC_FEATURES),
        (
            "categorical",
            OneHotEncoder(drop="first", handle_unknown="ignore"),
            CATEGORICAL_FEATURES,
        ),
    ]
)
balanced_model = Pipeline(
    steps=[
        ("preprocess", preprocessing),
        ("classifier", LogisticRegression(C=best_c, max_iter=1000)),
    ]
)

# Fit on balanced training rows; evaluate on the original, unchanged test rows.
balanced_model.fit(X_balanced, y_balanced)

def metrics(model, features):
    predictions = model.predict(features)
    return {
        "precision": precision_score(
            y_test, predictions, pos_label=1, zero_division=0
        ),
        "recall": recall_score(
            y_test, predictions, pos_label=1, zero_division=0
        ),
        "f1": f1_score(
            y_test, predictions, pos_label=1, zero_division=0
        ),
    }

unbalanced_metrics = metrics(unbalanced_model, X_test)
balanced_metrics = metrics(balanced_model, X_test)

print(f"Balanced training rows: {len(balanced_training)}")
print("Training class counts:")
print(balanced_training["lapsed"].value_counts().sort_index().to_string())
print("\nUnbalanced logistic model on unchanged test set:")
print(unbalanced_metrics)
print("\nBalanced logistic model on unchanged test set:")
print(balanced_metrics)

changes = {
    name: abs(balanced_metrics[name] - unbalanced_metrics[name])
    for name in ["precision", "recall", "f1"]
}
largest_change = max(changes, key=changes.get)
print(
    f"\nLargest metric change: {largest_change} "
    f"({unbalanced_metrics[largest_change]:.3f} to "
    f"{balanced_metrics[largest_change]:.3f})"
)