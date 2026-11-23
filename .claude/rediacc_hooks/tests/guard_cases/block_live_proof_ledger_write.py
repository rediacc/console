"""The test tables of `block_live_proof_ledger_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

from rediacc_hooks.guards.block_live_proof_ledger_write import LEDGER_REL

EDGE_CASES = [
    (
        "a Write over the ledger",
        {"tool_name": "Write", "tool_input": {"file_path": LEDGER_REL, "content": "{}\n"}},
    ),
    (
        "an Edit of a row",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/r/" + LEDGER_REL,
                "old_string": '"status":"FAILED"',
                "new_string": '"status":"VERIFIED"',
            },
        },
    ),
    (
        "a MultiEdit of the ledger",
        {"tool_name": "MultiEdit", "tool_input": {"file_path": LEDGER_REL, "edits": []}},
    ),
    (
        "another ledger",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/ledgers/effort-outcomes.jsonl", "content": "x"},
        },
    ),
    (
        "a plan that names the ledger",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/plans/PLAN-x.md", "content": LEDGER_REL},
        },
    ),
    (
        "a sibling with a similar name",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/ledgers/live-proof.jsonl.bak", "content": "x"},
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}),
]
