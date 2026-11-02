"""Refuse an Edit, Write, MultiEdit or NotebookEdit of the live-proof ledger, `agent/ledgers/live-proof.jsonl`.

WHY (agent/plans/PLAN-tested-on-bench.md box V10; review findings 2a2941c4.1 and 2a2941c4.5). CI judges the ledger with no secrets and no network, and the gate's LP5 checks only that a row's `id` hashes to its content, so a hand-written row with a recomputed id and `status: VERIFIED` passes it. The one writer is the recorder, `python3 -m rediacc_ci.ops.live_proof record --write`, which
appends a row only after the run it describes: identity, the VM ladder, the deploy record, the steps, live confirmation and the secret scan, and it keeps the run's log whose digest the row carries and `verify` re-reads. The recorder writes through Python, which no tool guard sees; every tool write is a hand write and is refused.

THE SHELL HALF is `block_live_proof_ledger_shell_write` (pre-bash): redirections, `tee`, `sed -i`, copies onto the ledger, `truncate`, `dd of=`, any output word of a command that is not a known reader, and interpreter code that opens the ledger for writing or drives the recorder in-process. A guard declares one chain, so the plan's single guard is two modules, the shape
`block_review_file_edit` and `block_review_file_shell_write` set.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_live_proof_ledger_write.py` beside it and against its own DEFECT, never against a golden.
"""

import re

from rediacc_hooks import hookio

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 17

# The path test is the whole guard: with it gone the ledger is editable by hand.
DEFECT = ("if LEDGER_PATH.search(path) is None:", "if True:")

LEDGER_REL = "agent/ledgers/live-proof.jsonl"
LEDGER_PATH = re.compile(r"(\A|/)agent/ledgers/live-proof\.jsonl\Z")

RECORDER = "PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger --check <id> --write"

MESSAGE = (
    "BLOCKED: %s of the live-proof ledger (%s).\n"
    "\n"
    "CI trusts agent/ledgers/live-proof.jsonl without re-running anything, so a row is written\n"
    "only by the recorder, after the live run it describes; a hand-written row with a recomputed\n"
    "id is the forgery this guard exists to stop.\n"
    "\n"
    "  record a receipt:  " + RECORDER + "\n"
    "  judge the ledger:  PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify\n"
)

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


def run(ev):
    given = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not given or given == "null":
        return hookio.ALLOW
    # Judged where the write LANDS (`hookio.landing`, the reading every pre-edit guard shares): a symlink to the ledger, or `agent/x/../ledgers/live-proof.jsonl`, is the ledger.
    landed, judged, shown = hookio.landing(given, ev.field("cwd") or None)
    path = judged if LEDGER_PATH.search(judged) else landed
    if LEDGER_PATH.search(path) is None:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % (ev.field("tool_name") or "a write", shown))
    return hookio.DENY
