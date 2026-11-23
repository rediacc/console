"""Refuse an Edit, Write, MultiEdit or NotebookEdit of the live-proof ledger, `agent/ledgers/live-proof.jsonl`.

WHY (agent/plans/PLAN-tested-on-bench.md box V10; review findings 2a2941c4.1 and 2a2941c4.5). CI judges the ledger with no secrets and no network, and the gate's LP5 checks only that a row's `id` hashes to its content, so a hand-written row with a recomputed id and `status: VERIFIED` passes it. The one writer is the recorder, `python3 -m rediacc_ci.ops.live_proof record --write`, which
appends a row only after the run it describes: identity, the VM ladder, the deploy record, the steps, live confirmation and the secret scan, and it keeps the run's log whose digest the row carries and `verify` re-reads. The recorder writes through Python, which no tool guard sees; every tool write is a hand write and is refused.

THE SHELL HALF is `block_live_proof_ledger_shell_write` (pre-bash): redirections, `tee`, `sed -i`, copies onto the ledger, `truncate`, `dd of=`, any output word of a command that is not a known reader, and interpreter code that opens the ledger for writing or drives the recorder in-process. A guard declares one chain, so the plan's single guard is two modules, the shape
`block_review_file_edit` and `block_review_file_shell_write` set.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_live_proof_ledger_write.py` beside it and against its own DEFECT, never against a golden.
"""

from rediacc_hooks.guards import _write_rules, tables

__getattr__ = tables("block_live_proof_ledger_write", "EDGE_CASES")

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 17

# The row is the whole guard: with the row no path matches, the ledger is editable by hand.
DEFECT = ('RULE = _write_rules.ROWS["live_proof_ledger"]', "RULE = _write_rules.NOTHING")

# The path, the refusal and the recorder are one row of `_write_rules.ROWS`, shared with the shell half.
RULE = _write_rules.ROWS["live_proof_ledger"]
LEDGER_REL = "agent/ledgers/live-proof.jsonl"
LEDGER_PATH = RULE.path
RECORDER = _write_rules.LEDGER_RECORDER
MESSAGE = RULE.message[0]


def run(ev):
    return _write_rules.edit_run(ev, RULE)
