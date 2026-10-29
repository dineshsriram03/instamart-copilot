import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from refund_agent import (
    LEDGER_FILE,
    STATE_DIR,
    SimulatedCrash,
    resume_agent,
    run_agent,
)


SCENARIOS_FILE = ROOT / "data" / "raw" / "agent_scenarios.csv"
RUNS_FILE = ROOT / "outputs" / "agent_runs.jsonl"


def write_run(result, run_kind):
    record = {
        "run_kind": run_kind,
        "scenario_id": result["scenario_id"],
        "status": result["status"],
        "final_answer": result["final_answer"],
        "llm_calls": result["llm_calls"],
        "tokens_used": result["tokens_used"],
        "steps": result["steps"],
        "tools_executed": result["tools_executed"],
    }
    with RUNS_FILE.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def refund_amount(result):
    amounts = [
        step["observation"]["refund_inr"]
        for step in result["steps"]
        if isinstance(step.get("observation"), dict)
        and "refund_inr" in step["observation"]
    ]
    return float(amounts[-1]) if amounts else 0.0


def main():
    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Start fresh output logs for this complete reproducible run.
    LEDGER_FILE.write_text("", encoding="utf-8")
    RUNS_FILE.write_text("", encoding="utf-8")

    scenarios = pd.read_csv(SCENARIOS_FILE, keep_default_na=False)
    scenario_results = []

    print("=== SEVEN REFUND SCENARIOS ===")
    for row in scenarios.to_dict("records"):
        result = run_agent(
            user_message=row["message"],
            scenario_id=row["scenario_id"],
            run_id=f"scenario-{row['scenario_id']}",
        )
        amount = refund_amount(result)

        if row["scenario_id"] != "S7":
            assert result["status"] == row["expected_outcome"], (
                f"{row['scenario_id']}: unexpected status {result['status']}"
            )

        expected_amount = float(row["expected_refund_inr"] or 0)
        assert abs(amount - expected_amount) <= 0.01, (
            f"{row['scenario_id']}: expected INR {expected_amount:.2f}, "
            f"got INR {amount:.2f}"
        )

        if row["scenario_id"] == "S1":
            assert result["llm_calls"] == 5
        if row["scenario_id"] == "S7":
            assert result["status"] == "FALLBACK_MAX_ITERATIONS"
            assert result["llm_calls"] == 6
            assert result["tokens_used"] <= 6000

        write_run(result, "scenario")
        scenario_results.append((row["scenario_id"], result, amount))
        print(
            f"{row['scenario_id']}: {result['status']}; "
            f"refund INR {amount:.2f}; calls {result['llm_calls']}; "
            f"tokens {result['tokens_used']}"
        )

    # S1 token-limit fallback demonstration.
    s1 = scenarios.loc[scenarios["scenario_id"].eq("S1")].iloc[0]
    token_demo = run_agent(
        user_message=s1["message"],
        scenario_id="S1",
        token_limit=200,
        run_id="demo-S1-token-limit",
    )
    assert token_demo["status"] == "FALLBACK_TOKEN_LIMIT"
    write_run(token_demo, "token_limit_demo")
    print(
        "\nToken-limit demo: "
        f"{token_demo['status']}; calls {token_demo['llm_calls']}; "
        f"tokens {token_demo['tokens_used']}"
    )

    # Timeout fallback before the first model call.
    timeout_demo = run_agent(
        user_message=s1["message"],
        scenario_id="S1",
        time_limit_seconds=0,
        run_id="demo-S1-timeout",
    )
    assert timeout_demo["status"] == "FALLBACK_TIMEOUT"
    assert timeout_demo["llm_calls"] == 0
    write_run(timeout_demo, "timeout_demo")
    print(
        "\nTimeout demo: "
        f"{timeout_demo['status']}; calls {timeout_demo['llm_calls']}"
    )

    # Simulate a crash immediately after the second tool observation is saved.
    crash_run_id = "demo-S1-crash-resume"
    try:
        run_agent(
            user_message=s1["message"],
            scenario_id="S1_CRASH_RESUME",
            run_id=crash_run_id,
            crash_after_tools=2,
        )
    except SimulatedCrash as error:
        print(f"\nCrash demo: {error}")
    else:
        raise AssertionError("The simulated crash did not occur.")

    resumed = resume_agent(crash_run_id)
    expected_tools = [
        "get_order",
        "search_policy",
        "calculate_refund",
        "issue_refund",
    ]
    assert resumed["tools_executed"] == expected_tools
    assert resumed["status"] == "REFUND"
    assert abs(refund_amount(resumed) - 128.25) <= 0.01
    write_run(resumed, "crash_resume_demo")
    print(f"Tools across crash and resume: {resumed['tools_executed']}")
    print(
        f"Resumed result: {resumed['status']}; "
        f"refund INR {refund_amount(resumed):.2f}; "
        f"calls {resumed['llm_calls']}"
    )

    print(f"\nScenario runs: {len(scenario_results)}")
    print(f"Agent run log: {RUNS_FILE}")
    print(f"Refund ledger: {LEDGER_FILE}")
    print(f"Checkpoints: {STATE_DIR}")


if __name__ == "__main__":
    main()