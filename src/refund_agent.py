from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mock_llm
from policy_rag import retrieve


DATABASE = ROOT / "data" / "instamart.db"
LEDGER_FILE = ROOT / "outputs" / "refund_ledger.jsonl"
STATE_DIR = ROOT / "state"

SYSTEM_PROMPT = """
You are an AGENT handling Instamart refund requests.
Use the provided tools to look up the order, search the refund policy,
calculate the refund, and issue or escalate it. Only completed orders are
eligible. Refund the full amount only when delivery took more than 45 minutes.
Refunds above INR 1000 must be escalated to a human.
"""


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Look up an order in the Instamart database.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "Retrieve policy text relevant to a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_refund",
            "description": "Calculate an eligible refund from order amount and delivery time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_amount": {"type": "number"},
                    "delivery_minutes": {"type": ["number", "null"]},
                },
                "required": ["order_amount", "delivery_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue an eligible refund of INR 1000 or less.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "refund_inr": {"type": "number"},
                },
                "required": ["order_id", "refund_inr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Send an eligible refund above INR 1000 to a human.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "refund_inr": {"type": "number"},
                },
                "required": ["order_id", "refund_inr"],
            },
        },
    },
]


def get_order(order_id):
    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT order_id, status, order_amount, delivery_minutes
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

    if row is None:
        return {"error": "order not found"}
    return dict(row)


def search_policy(query):
    return {"results": retrieve(query, k=3)}


def calculate_refund(order_amount, delivery_minutes):
    if delivery_minutes is None:
        return {"refund_inr": 0.0}

    if float(delivery_minutes) > 45:
        refund = round(float(order_amount), 2)
    else:
        refund = 0.0

    return {"refund_inr": refund}


def _check_action(order_id, refund_inr, action):
    order = get_order(order_id)
    if "error" in order:
        raise ValueError("Cannot process a refund for an unknown order.")
    if order["status"] != "completed":
        raise ValueError("Only completed orders can be refunded.")

    expected = calculate_refund(
        order["order_amount"],
        order["delivery_minutes"],
    )["refund_inr"]

    if abs(float(refund_inr) - expected) > 0.01:
        raise ValueError("Requested refund does not match the refund rules.")

    if action == "issue_refund" and expected > 1000:
        raise ValueError("Refunds above INR 1000 must be escalated.")
    if action == "escalate_to_human" and expected <= 1000:
        raise ValueError("Only refunds above INR 1000 require escalation.")

    return expected


def _append_ledger(tool_name, order_id, refund_inr):
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "order_id": order_id,
        "refund_inr": round(float(refund_inr), 2),
    }
    with LEDGER_FILE.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(entry, ensure_ascii=False) + "\n")


def issue_refund(order_id, refund_inr):
    amount = _check_action(order_id, refund_inr, "issue_refund")
    _append_ledger("issue_refund", order_id, amount)
    return {"refund_inr": amount}


def escalate_to_human(order_id, refund_inr):
    amount = _check_action(order_id, refund_inr, "escalate_to_human")
    _append_ledger("escalate_to_human", order_id, amount)
    return {"refund_inr": amount}


TOOL_MAP = {
    "get_order": get_order,
    "search_policy": search_policy,
    "calculate_refund": calculate_refund,
    "issue_refund": issue_refund,
    "escalate_to_human": escalate_to_human,
}


class SimulatedCrash(Exception):
    """Used only for the required checkpoint-and-resume demonstration."""


def _checkpoint_path(run_id):
    safe_run_id = "".join(
        character for character in run_id
        if character.isalnum() or character in "-_"
    )
    return STATE_DIR / f"{safe_run_id}.json"


def _save_checkpoint(state, start_time):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["elapsed_seconds"] = time.monotonic() - start_time
    _checkpoint_path(state["run_id"]).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _result(state, status, final_answer):
    return {
        "run_id": state["run_id"],
        "scenario_id": state["scenario_id"],
        "status": status,
        "final_answer": final_answer,
        "steps": state["steps"],
        "llm_calls": state["llm_calls"],
        "tokens_used": state["tokens_used"],
        "tools_executed": state["tools_executed"],
    }


def _continue_agent(state, crash_after_tools=None):
    start_time = time.monotonic() - state.get("elapsed_seconds", 0.0)
    run_id = state["run_id"]

    while state["llm_calls"] < state["max_iterations"]:
        elapsed = time.monotonic() - start_time
        if elapsed >= state["time_limit_seconds"]:
            return _result(
                state,
                "FALLBACK_TIMEOUT",
                "FALLBACK_TIMEOUT: Please review this request manually.",
            )

        response = mock_llm.chat(state["messages"], tools=TOOLS_SPEC)
        state["llm_calls"] += 1
        state["tokens_used"] += int(response.usage.total_tokens)

        if state["tokens_used"] > state["token_limit"]:
            return _result(
                state,
                "FALLBACK_TOKEN_LIMIT",
                "FALLBACK_TOKEN_LIMIT: Please review this request manually.",
            )

        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            final_answer = assistant_message.content or ""
            status = final_answer.split(":", 1)[0].strip()
            return _result(state, status, final_answer)

        serialized_calls = []
        for tool_call in tool_calls:
            arguments = tool_call.arguments
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            serialized_calls.append(
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": arguments,
                }
            )

        state["messages"].append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": serialized_calls,
            }
        )

        for tool_call in serialized_calls:
            tool_name = tool_call["name"]
            arguments = tool_call["arguments"]
            if tool_name not in TOOL_MAP:
                raise ValueError(f"Unknown tool requested: {tool_name}")

            observation = TOOL_MAP[tool_name](**arguments)
            observation_text = json.dumps(
                observation,
                ensure_ascii=False,
                sort_keys=True,
            )
            state["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_name,
                    "content": observation_text,
                }
            )

            step = {
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": observation,
            }
            state["steps"].append(step)
            state["tools_executed"].append(tool_name)
            state["step_number"] += 1

            # Save after every observation, before any simulated crash.
            _save_checkpoint(state, start_time)

            if crash_after_tools == state["step_number"]:
                raise SimulatedCrash(
                    f"Simulated crash after tool {state['step_number']}."
                )

    return _result(
        state,
        "FALLBACK_MAX_ITERATIONS",
        "FALLBACK_MAX_ITERATIONS: Please review this request manually.",
    )


def run_agent(
    user_message,
    scenario_id,
    max_iterations=6,
    token_limit=6000,
    time_limit_seconds=10,
    run_id=None,
    crash_after_tools=None,
):
    mock_llm.reset()
    run_id = run_id or f"{scenario_id}-{uuid.uuid4().hex[:8]}"

    state = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "tokens_used": 0,
        "llm_calls": 0,
        "step_number": 0,
        "steps": [],
        "tools_executed": [],
        "max_iterations": max_iterations,
        "token_limit": token_limit,
        "time_limit_seconds": time_limit_seconds,
        "elapsed_seconds": 0.0,
    }
    return _continue_agent(state, crash_after_tools=crash_after_tools)


def resume_agent(run_id):
    path = _checkpoint_path(run_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    return _continue_agent(state)