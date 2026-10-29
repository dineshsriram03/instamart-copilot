from pathlib import Path
import sqlite3

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "outputs" / "lapse_dataset.csv"
DATABASE = ROOT / "data" / "instamart.db"
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
CATEGORICAL_FEATURES = [
    "city",
    "gender",
    "favorite_category",
]

data = pd.read_csv(DATA_FILE)
feature_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES

X = data.set_index("customer_id")[feature_columns]
y = data.set_index("customer_id")["lapsed"].astype(int)

assert not X.isna().any().any(), "A model feature contains a missing value."

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    stratify=y,
    random_state=42,
)

print(f"Training rows: {len(X_train)}")
print(f"Test rows: {len(X_test)}")

# Baseline: always predict that the customer will not lapse.
baseline_predictions = [0] * len(y_test)
print("\n=== BASELINE ===")
print(f"Accuracy: {accuracy_score(y_test, baseline_predictions):.3f}")
print(
    "Lapsed-class F1: "
    f"{f1_score(y_test, baseline_predictions, pos_label=1, zero_division=0):.3f}"
)

def make_pipeline(classifier):
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
    return Pipeline(
        steps=[
            ("preprocess", preprocessing),
            ("classifier", classifier),
        ]
    )

# Each cross-validation fold fits its own preprocessing on that fold's training rows.
logistic_search = GridSearchCV(
    estimator=make_pipeline(LogisticRegression(max_iter=1000)),
    param_grid={"classifier__C": [0.01, 0.1, 1, 10, 100]},
    cv=5,
    scoring="f1",
    n_jobs=1,
)
logistic_search.fit(X_train, y_train)

forest_search = GridSearchCV(
    estimator=make_pipeline(
        RandomForestClassifier(n_estimators=100, random_state=42)
    ),
    param_grid={
        "classifier__max_depth": [3, 5, 8],
        "classifier__min_samples_leaf": [5, 10, 20],
    },
    cv=5,
    scoring="f1",
    n_jobs=1,
)
forest_search.fit(X_train, y_train)

OUTPUTS.mkdir(parents=True, exist_ok=True)
joblib.dump(logistic_search.best_estimator_, OUTPUTS / "logistic_model.joblib")
joblib.dump(forest_search.best_estimator_, OUTPUTS / "random_forest_model.joblib")

def report_test_metrics(name, model):
    predictions = model.predict(X_test)
    print(f"\n=== {name} TEST RESULTS ===")
    print("Confusion matrix (rows=true 0,1; columns=predicted 0,1):")
    print(confusion_matrix(y_test, predictions, labels=[0, 1]))
    print(
        "Lapsed-class precision: "
        f"{precision_score(y_test, predictions, pos_label=1, zero_division=0):.3f}"
    )
    print(
        "Lapsed-class recall: "
        f"{recall_score(y_test, predictions, pos_label=1, zero_division=0):.3f}"
    )
    print(
        "Lapsed-class F1: "
        f"{f1_score(y_test, predictions, pos_label=1, zero_division=0):.3f}"
    )
    return f1_score(y_test, predictions, pos_label=1, zero_division=0)

print("\n=== LOGISTIC REGRESSION GRID SEARCH ===")
print(f"Best parameters: {logistic_search.best_params_}")
print(f"Best cross-validated F1: {logistic_search.best_score_:.3f}")
logistic_test_f1 = report_test_metrics(
    "LOGISTIC REGRESSION",
    logistic_search.best_estimator_,
)

print("\n=== RANDOM FOREST GRID SEARCH ===")
print(f"Best parameters: {forest_search.best_params_}")
print(f"Best cross-validated F1: {forest_search.best_score_:.3f}")
forest_test_f1 = report_test_metrics(
    "RANDOM FOREST",
    forest_search.best_estimator_,
)

# The fitted scaler saw training rows only; the cohort mean includes the test rows.
fitted_scaler = (
    logistic_search.best_estimator_
    .named_steps["preprocess"]
    .named_transformers_["numeric"]
)
frequency_position = NUMERIC_FEATURES.index("frequency")
print("\n=== TRAINING-ONLY SCALER CHECK ===")
print(f"Scaler training mean for frequency: {fitted_scaler.mean_[frequency_position]:.3f}")
print(f"Full-cohort mean for frequency: {X['frequency'].mean():.3f}")
print(
    "These differ because the scaler was fitted on training rows only, "
    "while the cohort mean also includes held-out test rows."
)