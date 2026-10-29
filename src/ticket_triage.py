import json
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mock_llm


TICKETS_FILE = ROOT / "data" / "raw" / "tickets.csv"
SEGMENTS_FILE = ROOT / "outputs" / "customer_segments.csv"
OUTPUTS = ROOT / "outputs"

ALLOWED_CATEGORIES = ["billing", "delivery", "technical", "fraud"]
MAX_INPUT_TOKENS = 400
MAX_RETRIES = 3
BASE_DELAY = 0.05

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
ORDER_ID_RE = re.compile(r"ORD-\d{6}")
PII_PATTERNS = [EMAIL_RE, PHONE_RE, ORDER_ID_RE]

ZERO_SHOT_PROMPT = """
You are a support ticket classifier. CLASSIFY the user message into exactly one category.
Allowed categories: billing, delivery, technical, fraud.
Reply with JSON only, using this form: {"category": "...", "reason": "..."}.
"""

FEW_SHOT_PROMPT = """
You are a support ticket classifier. CLASSIFY the user message into exactly one category.
Allowed categories: billing, delivery, technical, fraud.
Reply with JSON only, using this form: {"category": "...", "reason": "..."}.
EXAMPLES:
Ticket: I was charged twice for my order.
Label: {"category": "billing", "reason": "The customer reports a duplicate charge."}
Ticket: Someone hacked my account and placed an order I did not make.
Label: {"category": "fraud", "reason": "The customer reports unauthorized account activity."}
"""

assert "EXAMPLES:" not in ZERO_SHOT_PROMPT
assert "EXAMPLES:" in FEW_SHOT_PROMPT
assert "CLASSIFY" in ZERO_SHOT_PROMPT and "CLASSIFY" in FEW_SHOT_PROMPT


def redact_text(text):
    text, email_count = EMAIL_RE.subn("[EMAIL]", text)
    text, phone_count = PHONE_RE.subn("[PHONE]", text)
    text, order_count = ORDER_ID_RE.subn("[ORDER_ID]", text)
    return text, {
        "emails": email_count,
        "phones": phone_count,
        "order_ids": order_count,
    }


def contains_pii(text):
    return any(pattern.search(text) for pattern in PII_PATTERNS)


def classify_reply(reply_text):
    try:
        parsed = json.loads(reply_text)
    except (json.JSONDecodeError, TypeError):
        words = re.findall(r"[a-z]+", (reply_text or "").lower())
        found = [category for category in ALLOWED_CATEGORIES if category in words]
        if len(found) == 1:
            return found[0], "classified_keyword"
        return "", "flagged_invalid_output"

    if isinstance(parsed, dict) and parsed.get("category") in ALLOWED_CATEGORIES:
        return parsed["category"], "classified_json"

    return "", "flagged_invalid_output"


def choose_route(status, category, is_premium):
    human_statuses = {
        "skipped_empty",
        "flagged_long",
        "flagged_invalid_output",
        "budget_exhausted",
        "permanent_error",
    }
    if status in human_statuses:
        return "NORMAL", "human_review"
    if category == "fraud":
        return "HIGH", "security_team"
    if is_premium:
        return "HIGH", "premium_desk"
    return "NORMAL", "support_queue"


def call_with_retries(ticket_id, messages, token_budget, running_tokens):
    retries = 0
    failures = 0

    while True:
        # Check the budget before every model call, including retries.
        if token_budget is not None and running_tokens >= token_budget:
            return None, "budget_exhausted", retries, failures

        try:
            response = mock_llm.chat(messages)
            return response, "", retries, failures
        except mock_llm.TransientLLMError:
            failures += 1
            if retries >= MAX_RETRIES:
                return None, "permanent_error", retries, failures

            wait = BASE_DELAY * (2**retries) * random.uniform(0.9, 1.15)
            print(
                f"Retry ticket {ticket_id}: retry number {retries}, "
                f"wait {wait:.4f}s"
            )
            time.sleep(wait)
            retries += 1


def run_pipeline(tickets, redacted_texts, segment_lookup, system_prompt, token_budget=None):
    # Reset immediately before each independent full run.
    mock_llm.reset()
    random.seed(42)

    running_tokens = 0
    retry_errors = 0
    records = []

    for position, ticket in enumerate(tickets.to_dict("records")):
        text = ticket["text"]
        redacted_text = redacted_texts[position]
        ticket_id = ticket["ticket_id"]
        customer_id = ticket["customer_id"]

        segment_name, is_premium = segment_lookup.get(customer_id, ("", False))
        category = ""
        tokens_used = 0

        if not text.strip():
            status = "skipped_empty"
        elif mock_llm.est_tokens(text) > MAX_INPUT_TOKENS:
            status = "flagged_long"
        else:
            # The user message is exactly the redacted ticket text.
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": redacted_text},
            ]
            assert messages[-1]["content"] == redacted_text
            assert all(not contains_pii(message["content"]) for message in messages)

            response, call_status, _, failures = call_with_retries(
                ticket_id,
                messages,
                token_budget,
                running_tokens,
            )
            retry_errors += failures

            if response is None:
                status = call_status
            else:
                tokens_used = int(response.usage.total_tokens)
                running_tokens += tokens_used
                reply_text = response.choices[0].message.content or ""
                category, status = classify_reply(reply_text)

        priority, route = choose_route(status, category, is_premium)
        records.append(
            {
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "status": status,
                "category": category,
                "segment_name": segment_name,
                "priority": priority,
                "route": route,
                "tokens_used": tokens_used,
                "true_category": ticket["true_category"],
            }
        )

    result = pd.DataFrame(records)
    assert len(result) == len(tickets)
    assert not result["status"].eq("permanent_error").any()

    classified = result["status"].isin(["classified_json", "classified_keyword"])
    classified_count = int(classified.sum())
    correct_count = int(
        result.loc[classified, "category"].eq(
            result.loc[classified, "true_category"]
        ).sum()
    )
    accuracy = correct_count / classified_count if classified_count else 0.0

    return result, running_tokens, retry_errors, classified_count, correct_count, accuracy


def report_run(name, result, total_tokens, retry_errors, classified_count, correct_count, accuracy):
    print(f"\n=== {name} ===")
    print("Status counts:")
    print(result["status"].value_counts().sort_index().to_string())
    print(f"Classified: {classified_count}")
    print(f"Accuracy on classified tickets: {accuracy:.1%} ({correct_count}/{classified_count})")
    print(f"Total response tokens: {total_tokens}")
    print(
        "Tokens per classified ticket: "
        f"{total_tokens / classified_count:.2f}"
    )
    print(f"Transient errors recovered by retries: {retry_errors}")


def main():
    tickets = pd.read_csv(TICKETS_FILE, keep_default_na=False)
    segments = pd.read_csv(SEGMENTS_FILE)
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    premium_values = segments["is_premium"].astype("string").str.lower().eq("true")
    segment_lookup = {
        row["customer_id"]: (row["segment_name"], bool(row["is_premium"]))
        for _, row in segments.assign(is_premium=premium_values).iterrows()
    }

    redacted_texts = []
    substitution_totals = {"emails": 0, "phones": 0, "order_ids": 0}
    for text in tickets["text"].tolist():
        redacted_text, counts = redact_text(text)
        redacted_texts.append(redacted_text)
        for name, count in counts.items():
            substitution_totals[name] += count

    remaining_pii = {
        name: sum(bool(pattern.search(text)) for text in redacted_texts)
        for name, pattern in [
            ("emails", EMAIL_RE),
            ("phones", PHONE_RE),
            ("order_ids", ORDER_ID_RE),
        ]
    }
    assert sum(remaining_pii.values()) == 0

    print("=== REDACTION ===")
    print(f"Email substitutions: {substitution_totals['emails']}")
    print(f"Phone substitutions: {substitution_totals['phones']}")
    print(f"Order ID substitutions: {substitution_totals['order_ids']}")
    print(f"Total substitutions: {sum(substitution_totals.values())}")
    print(f"PII matches remaining after re-check: {sum(remaining_pii.values())}")

    zero, zero_tokens, zero_retries, zero_n, zero_correct, zero_accuracy = run_pipeline(
        tickets, redacted_texts, segment_lookup, ZERO_SHOT_PROMPT
    )
    report_run("ZERO-SHOT, NO BUDGET", zero, zero_tokens, zero_retries, zero_n, zero_correct, zero_accuracy)

    confusion = pd.crosstab(
        zero.loc[zero["status"].isin(["classified_json", "classified_keyword"]), "true_category"],
        zero.loc[zero["status"].isin(["classified_json", "classified_keyword"]), "category"],
    ).reindex(
        index=ALLOWED_CATEGORIES,
        columns=ALLOWED_CATEGORIES,
        fill_value=0,
    )
    print("\nZero-shot confusion table:")
    print(confusion.to_string())

    few, few_tokens, few_retries, few_n, few_correct, few_accuracy = run_pipeline(
        tickets, redacted_texts, segment_lookup, FEW_SHOT_PROMPT
    )
    report_run("FEW-SHOT, NO BUDGET", few, few_tokens, few_retries, few_n, few_correct, few_accuracy)
    print(
        "Extra few-shot tokens per classified ticket: "
        f"{(few_tokens / few_n) - (zero_tokens / zero_n):.2f}"
    )

    demo_budget = 6000
    demo, demo_tokens, demo_retries, demo_n, demo_correct, demo_accuracy = run_pipeline(
        tickets,
        redacted_texts,
        segment_lookup,
        ZERO_SHOT_PROMPT,
        token_budget=demo_budget,
    )
    exhausted = int(demo["status"].eq("budget_exhausted").sum())

    if exhausted == 0:
        demo_budget = 5000
        demo, demo_tokens, demo_retries, demo_n, demo_correct, demo_accuracy = run_pipeline(
            tickets,
            redacted_texts,
            segment_lookup,
            ZERO_SHOT_PROMPT,
            token_budget=demo_budget,
        )
        exhausted = int(demo["status"].eq("budget_exhausted").sum())

    demo.drop(columns=["true_category"]).to_csv(
        OUTPUTS / "triage_budget_demo.csv",
        index=False,
    )
    print(f"\nBudget demo limit: {demo_budget}")
    print(f"Budget-exhausted tickets: {exhausted}")
    print(f"Saved: {OUTPUTS / 'triage_budget_demo.csv'}")
    assert exhausted > 0

    final, final_tokens, final_retries, final_n, final_correct, final_accuracy = run_pipeline(
        tickets,
        redacted_texts,
        segment_lookup,
        FEW_SHOT_PROMPT,
        token_budget=100000,
    )
    report_run(
        "FINAL FEW-SHOT, BUDGET 100000",
        final,
        final_tokens,
        final_retries,
        final_n,
        final_correct,
        final_accuracy,
    )
    final_output = final.drop(columns=["true_category"])
    final_output.to_csv(OUTPUTS / "triage_results.csv", index=False)
    print(f"Final output rows: {len(final_output)}")
    print(f"Saved: {OUTPUTS / 'triage_results.csv'}")


if __name__ == "__main__":
    main()