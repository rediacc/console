"""The test tables of `block_live_proof_ledger_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

from rediacc_hooks.guards import block_live_proof_ledger_write as EDIT

LEDGER_REL = EDIT.LEDGER_REL


EDGE_CASES = [
    ("append a row", "echo '{}' >> " + LEDGER_REL),
    # #4e20f8c5: the refused PLAN edit. The ledger's path is text being replaced inside the PLAN, and the PLAN is the file written.
    (
        "python edits a PLAN line naming the ledger",
        "python3 - <<'PY'\nimport pathlib\np = pathlib.Path('agent/plans/PLAN-backup-program.md')\n"
        "s = p.read_text()\ns = s.replace('Owns: x, "
        + LEDGER_REL
        + "', 'Owns: x')\np.write_text(s)\nPY",
    ),
    ("the recorder", "PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --write"),
    ("read the ledger", "jq . " + LEDGER_REL),
    ("tee the ledger", "printf x | tee -a " + LEDGER_REL),
    ("stage the ledger", "git add -- " + LEDGER_REL),
]
