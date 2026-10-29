# Instamart Customer Intelligence & Support Copilot

**Repository branch:** `main`

## Reproduce

Run these commands from the repository root in Windows PowerShell. The helper files `generate_data.py` and `mock_llm.py` are used as supplied and must remain unmodified.

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Install the pinned libraries:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Generate the deterministic raw data:

   ```powershell
   .\.venv\Scripts\python.exe .\generate_data.py
   ```

4. Audit the raw data:

   ```powershell
   .\.venv\Scripts\python.exe .\src\audit_data.py
   ```

5. Clean customers:

   ```powershell
   .\.venv\Scripts\python.exe .\src\clean_customers.py
   ```

6. Clean orders and write the clean products table:

   ```powershell
   .\.venv\Scripts\python.exe .\src\clean_orders.py
   ```

7. Build the SQLite database:

   ```powershell
   .\.venv\Scripts\python.exe .\src\build_database.py
   ```

8. Validate the cleaned data and database:

   ```powershell
   .\.venv\Scripts\python.exe .\src\validate_data.py
   ```

   Expected output:

   ```text
   ALL CHECKPOINTS PASSED
   ```

9. Run the seven SQL queries:

   ```powershell
   .\.venv\Scripts\python.exe .\src\run_sql_analysis.py
   ```

10. Run the pandas cross-check
11. Build the RFM table: `.\.venv\Scripts\python.exe .\src\build_rfm.py`
12. Compare clusters: `.\.venv\Scripts\python.exe .\src\cluster_customers.py`
13. Export customer segments: `.\.venv\Scripts\python.exe .\src\export_customer_segments.py`
14. Build lapse features and labels: `.\.venv\Scripts\python.exe .\src\build_lapse_dataset.py`
15. Tune and evaluate lapse models: `.\.venv\Scripts\python.exe .\src\train_lapse_models.py`
16. Run the class-balance experiment: `.\.venv\Scripts\python.exe .\src\class_balance_experiment.py`
17. Save and check the selected model 
18. Run ticket triage: `.\.venv\Scripts\python.exe .\src\ticket_triage.py` and retention list: `.\.venv\Scripts\python.exe .\src\finalize_lapse_model.py` and exploratory analysis:

    ```powershell
    .\.venv\Scripts\python.exe .\src\pandas_analysis.py
    ```

## Part A — Data Foundation

The raw CSV files are retained in `data/raw/`. Cleaned CSV files are written to `data/clean/`, and the SQLite database is `data/instamart.db`.

### Raw-data audit

Missing percentages are calculated per column. Blank CSV fields are read as missing values.

| Table | Shape | Column | Data type | Missing count | Missing percent |
|---|---:|---|---|---:|---:|
| customers | 1,200 × 5 | customer_id | str | 0 | 0.00% |
| customers | 1,200 × 5 | city | str | 0 | 0.00% |
| customers | 1,200 × 5 | signup_date | str | 0 | 0.00% |
| customers | 1,200 × 5 | age | float64 | 61 | 5.08% |
| customers | 1,200 × 5 | gender | str | 30 | 2.50% |
| products | 40 × 4 | product_id | str | 0 | 0.00% |
| products | 40 × 4 | product_name | str | 0 | 0.00% |
| products | 40 × 4 | category | str | 0 | 0.00% |
| products | 40 × 4 | price_inr | int64 | 0 | 0.00% |
| orders | 13,084 × 9 | order_id | str | 0 | 0.00% |
| orders | 13,084 × 9 | customer_id | str | 0 | 0.00% |
| orders | 13,084 × 9 | product_id | str | 0 | 0.00% |
| orders | 13,084 × 9 | quantity | int64 | 0 | 0.00% |
| orders | 13,084 × 9 | order_ts | str | 0 | 0.00% |
| orders | 13,084 × 9 | status | str | 0 | 0.00% |
| orders | 13,084 × 9 | discount_pct | int64 | 0 | 0.00% |
| orders | 13,084 × 9 | order_amount | str | 53 | 0.41% |
| orders | 13,084 × 9 | delivery_minutes | float64 | 2,541 | 19.42% |

Specific raw audit figures:

| Measure | Result |
|---|---:|
| Raw order rows | 13,084 |
| Exact duplicate order rows | 119 |
| Pending order rows | 656 |
| Distinct order IDs | 12,309 |
| Unparseable or blank order amounts | 120 |
| Negative delivery times | 106 |
| Blank delivery times | 2,541 |
| Blank customer ages | 61 |
| Customer ages outside 10–100 | 6 |
| Distinct raw city spellings | 24 |
| Distinct non-blank raw gender spellings | 10 |
| Blank genders | 30 |

### Cleaning rules and results

**Customers**

- Standardized city values across the 1,200 customer rows by trimming whitespace and applying title case. The 24 raw spellings became six cities: Pune 227, Delhi 210, Bengaluru 197, Chennai 191, Hyderabad 191, and Mumbai 184.
- Mapped the 1,200 gender values from 10 raw spellings to `male`, `female`, or `unknown`. The 30 blank genders became `unknown`. Final counts: female 610, male 560, unknown 30.
- Set the 61 blank ages and 6 ages outside 10–100 to missing, then filled those 67 ages with the median age of the customer's city using `groupby` and `transform`. The cleaned table has no missing ages; ages range from 18 to 60.
- Converted all 1,200 `signup_date` values to datetimes.

**Orders**

- Parsed the 13,084 raw `order_ts` values as datetimes.
- Removed 119 exact duplicate rows.
- Kept the latest record for each `order_id`, removing 656 superseded records after exact-duplicate removal. The cleaned table has one row per order ID.
- The raw audit found 120 order amounts that were blank or could not be parsed as numbers. After deduplication, remaining missing amounts were filled using `round(price_inr × quantity × (1 − discount_pct / 100), 2)`. The cleaned table has no missing order amounts.
- Set negative delivery times to missing. The raw audit found 106 negative and 2,541 blank delivery times. Missing times for completed orders were filled with the median for the order's product category. Cancelled orders were left without a delivery time.
- The cleaned orders table has 12,309 rows: 11,110 completed and 1,199 cancelled. No pending rows remain. Completed orders have no missing delivery times; all 1,199 cancelled orders do.
- The sum of completed-order amounts is INR 2,998,668.80.

**Products**

- The 40-row product table had no missing values or cleaning rules to apply. It was copied to `data/clean/products.csv`.

### Storage and validation

The clean tables are stored as CSV files in `data/clean/` and as SQLite tables named `customers`, `products`, and `orders` in `data/instamart.db`. The `orders.order_ts` database column is stored as text in `YYYY-MM-DD HH:MM:SS` format.

The validation script checks the reference customer and order results and database row counts. It prints `ALL CHECKPOINTS PASSED`.

### SQL analysis results

All seven queries are saved in `sql/queries.sql` and run from Python using `pandas.read_sql_query`.

| Query | Result |
|---|---|
| Q1 — WHERE then HAVING | 30 customers |
| Q2 — Three-table join | 30 city/category rows; revenue total INR 2,998,668.80; largest cell Bengaluru / Electronics at INR 233,909.45 |
| Q3 — Scalar subquery | 11 products priced above the catalogue average |
| Q4 — LEFT JOIN | 25 customers with no completed order |
| Q5 — CTE | 550 customers above average completed spend; average INR 2,552.06 |
| Q6 — Ranking windows | Top customers shown below; 8 rows have `RANK()` different from `ROW_NUMBER()` |
| Q7 — Running total | 183 daily rows; final cumulative revenue INR 2,998,668.80 |

`RANK()` assigns the same rank to tied spend values and skips the next rank, while `ROW_NUMBER()` assigns each row a unique sequential number; ties therefore make the results differ.

| City | Top customer | Completed spend |
|---|---|---:|
| Bengaluru | C0082 | INR 12,856.20 |
| Chennai | C0930 | INR 10,151.40 |
| Delhi | C0291 | INR 13,742.60 |
| Hyderabad | C0743 | INR 12,730.05 |
| Mumbai | C0693 | INR 14,766.55 |
| Pune | C0426 | INR 10,377.10 |

### pandas cross-check and exploratory analysis

The pandas pivot table reproduced Q2's 30 city/category revenue cells. Its grand total, INR 2,998,668.80, matches the SQL total.

| City | Completed amount sum | Mean | Count |
|---|---:|---:|---:|
| Bengaluru | INR 523,643.40 | INR 276.47 | 1,894 |
| Chennai | INR 463,629.15 | INR 272.72 | 1,700 |
| Delhi | INR 502,829.80 | INR 243.62 | 2,064 |
| Hyderabad | INR 528,589.90 | INR 284.95 | 1,855 |
| Mumbai | INR 479,058.50 | INR 297.00 | 1,613 |
| Pune | INR 500,918.05 | INR 252.48 | 1,984 |

| Completed order amount statistic | Result |
|---|---:|
| Mean | INR 269.91 |
| Median | INR 135.00 |
| Skewness | 4.61 |
| Q1 | INR 64.80 |
| Q3 | INR 297.00 |
| Lower 1.5-IQR fence | INR -283.50 |
| Upper 1.5-IQR fence | INR 645.30 |
| Outliers below lower fence | 0 |
| Outliers above upper fence | 897 |

The strongest absolute pairwise correlation is between `order_amount` and `discount_pct`, at approximately -0.095. The `order_amount` and `quantity` correlation is approximately +0.087.

**Interpretation**

These records describe completed Instamart orders, including customer cities, product categories, discounts, quantities, and delivery times. Order amounts are strongly right-skewed: the mean (INR 269.91) is above the median (INR 135.00), and skewness is 4.61. The middle half of amounts ranges from INR 64.80 to INR 297.00. The upper 1.5-IQR fence is INR 645.30; 897 orders exceed it and none fall below the lower fence. The strongest pairwise correlation is between order amount and discount percentage (-0.095); order amount and quantity is +0.087. Both relationships are weak. Correlation does not establish causation. Product mix, customer behavior, and other factors may also relate to order amounts.


## Part B — Customer Segments and Lapse Prediction

### RFM table

RFM uses completed orders through the snapshot moment `2025-10-01 00:00:00`.

| Measure | Result |
|---|---:|
| Customers with a completed order | 1,175 |
| Recency, median / minimum / maximum | 19 / 0 / 180 days |
| Frequency, mean / maximum | 9.46 / 33 |
| Monetary, mean / maximum | INR 2,552.06 / INR 14,766.55 |

### K-means and segment profiles

The three RFM columns were standardized with `StandardScaler`. K-means used `n_init=10` and `random_state=42`.

| K | Inertia | Silhouette |
|---:|---:|---:|
| 2 | 1,820.761 | 0.465 |
| 3 | 1,268.235 | 0.445 |
| 4 | 743.071 | 0.526 |
| 5 | 617.367 | 0.480 |
| 6 | 503.171 | 0.482 |
| 7 | 408.460 | 0.416 |
| 8 | 366.503 | 0.412 |

K=4 is selected because it has the strongest silhouette score and a clear elbow in the inertia curve. Inertia falls as K increases because additional centroids bring customers closer to a cluster center; that alone does not justify adding more segments. Four groups also support distinct, practical campaign actions.

| Segment ID | Business name | Size | Mean recency | Mean frequency | Mean monetary | Premium | Recommended action |
|---:|---|---:|---:|---:|---:|---|---|
| 0 | Occasional Shoppers | 436 | 28.86 days | 3.77 | INR 1,057.62 | No | Send relevant bundles to encourage another purchase. |
| 1 | Premium Customers | 138 | 24.12 days | 6.77 | INR 7,129.70 | Yes | Offer tailored loyalty rewards to retain high-value customers. |
| 2 | Loyal Regulars | 419 | 8.77 days | 19.40 | INR 3,410.02 | No | Promote replenishment reminders and relevant add-ons. |
| 3 | At-Risk Customers | 182 | 109.04 days | 2.20 | INR 685.99 | No | Send a focused win-back offer. |

Segment ID is only a cluster label and has no inherent ranking. The segment with the highest mean monetary value, segment 1, is marked Premium.

PCA on the scaled RFM matrix explained 0.634 of variance in component 1 and 0.218 in component 2, for 0.852 combined.

The required segment file is `outputs/customer_segments.csv`, with columns `customer_id`, `recency`, `frequency`, `monetary`, `segment_id`, `segment_name`, and `is_premium`.

### Lapse cohort and features

The cutoff is `2025-09-01`. The cohort contains customers with at least one completed order before the cutoff. A customer is labelled lapsed when they have no completed order during September 2025.

| Measure | Result |
|---|---:|
| Cohort customers | 1,156 |
| Lapsed customers | 443 (38.32%) |
| Training rows | 924 |
| Test rows | 232 |
| Baseline accuracy | 0.616 |
| Baseline lapsed-class F1 | 0.000 |

Features are recency, frequency, monetary, average discount percentage, cancellation rate, average delivery time, most frequent product category, city, age, gender, and tenure in days. The feature table contains no missing values.

No order dated on or after `2025-09-01` entered the features. September completed orders were used only to define the label. Segment labels from Part B's clustering were not used as model features.

The numeric scaler's training mean for frequency was 8.115; the full-cohort mean was 8.029. They differ because the scaler was fitted only on training rows, while the cohort mean also includes the held-out test rows.

Nominal columns were one-hot encoded with `drop="first"`. Scaling and encoding were performed inside cross-validation pipelines, fitted on training folds and then refitted on the full training partition. No encoder, scaler, or resampler saw test rows.

### Model tuning and test evaluation

Logistic Regression used `max_iter=1000`, five-fold cross-validation, F1 scoring, and C values 0.01, 0.1, 1, 10, and 100. Random Forest used 100 trees, `random_state=42`, five-fold cross-validation, F1 scoring, maximum depths 3, 5, and 8, and minimum leaf sizes 5, 10, and 20.

| Model | Best parameters | Best cross-validated F1 | Test confusion matrix (true rows 0,1; predicted columns 0,1) | Lapsed precision | Lapsed recall | Lapsed F1 |
|---|---|---:|---|---:|---:|---:|
| Logistic Regression | C=100 | 0.651 | `[[111, 32], [31, 58]]` | 0.644 | 0.652 | 0.648 |
| Random Forest | max depth 8, minimum leaf size 10 | 0.681 | `[[113, 30], [31, 58]]` | 0.659 | 0.652 | 0.655 |

The selected model is the Random Forest. Its test F1 of 0.655 is higher than Logistic Regression's 0.648 and exceeds the required 0.55. Missing a lapsing customer means losing an opportunity to intervene, while wrongly targeting a loyal customer can waste a discount or annoy them. The Random Forest has the same recall as Logistic Regression, slightly higher precision, and two fewer false positives on this test set. This makes it the better balance for targeted retention in this evaluation.

### Class-balance experiment

The training set retained all original rows and oversampled lapsed training rows with replacement, using `random_state=42`, to reach 570 customers in each class. Evaluation used the original, unchanged test set.

| Logistic model | Precision | Recall | F1 |
|---|---:|---:|---:|
| Unbalanced training | 0.644 | 0.652 | 0.648 |
| Balanced training | 0.589 | 0.854 | 0.697 |

Recall changed the most. The balanced model identifies more lapsing customers, but its lower precision means the retention team will also contact more customers who would not lapse.

### Model interpretation and saved outputs

Top five Random Forest feature importances:

| Feature | Importance |
|---|---:|
| Frequency | 0.2796 |
| Monetary | 0.2712 |
| Recency | 0.1151 |
| Average delivery time | 0.0613 |
| Cancellation rate | 0.0523 |

Frequency contributes the largest share of the forest's predictive splits. Monetary is the next strongest signal. Recency captures how recently the customer ordered. Average delivery time and cancellation rate also contribute to the model.

Three largest-magnitude Logistic Regression coefficients:

| Feature | Coefficient sign and value | Business reading |
|---|---:|---|
| Frequency | -1.6982 | Higher frequency is associated with lower lapse log-odds, holding the other features constant. |
| Favourite category: Electronics | -1.1367 | Relative to the encoder's dropped reference category, Electronics is associated with lower lapse log-odds. |
| Favourite category: Grocery | -0.4487 | Relative to the encoder's dropped reference category, Grocery is associated with lower lapse log-odds. |

The selected model is saved to `outputs/lapse_model.joblib`. After reloading, its test predictions matched the original predictions exactly.

The Premium test-set retention list contains the ten highest predicted lapse probabilities among 40 Premium customers in the test set. One of the ten was actually lapsed. The list is saved to `outputs/retention_list.csv` with columns `customer_id`, `lapse_probability`, and `actually_lapsed`.

### Limitations and Next Steps

The Premium flag is a post-hoc whole-window label that includes September, so the retention list is illustrative and not a leakage-free evaluation. The lapse-model features themselves use only pre-cutoff orders; segment labels were excluded from model features, and no encoder, scaler, or resampler saw test rows. For a production retention experiment, define Premium status using data available at the cutoff and evaluate campaign outcomes prospectively.