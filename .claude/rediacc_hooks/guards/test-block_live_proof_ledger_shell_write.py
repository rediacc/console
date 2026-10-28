#!/usr/bin/env python3
"""Control harness for block_live_proof_ledger_shell_write: the shell half of "the live-proof ledger is written only by the recorder" (agent/plans/PLAN-tested-on-bench.md box V10).

The cases, the scratch world and the runner live in `test-block_live_proof_ledger_write.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions (a planted hand-appended row refused, the recorder's append allowed), then plants the guard's DEFECT and requires the run to fail.

    test-block_live_proof_ledger_shell_write.py
"""

import importlib.util
import pathlib
import sys

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_live_proof_ledger_write.py")


def main():
    spec = importlib.util.spec_from_file_location("test_live_proof_ledger_shared", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("%s is missing" % SHARED)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    return shared.main(("block_live_proof_ledger_shell_write",))


if __name__ == "__main__":
    sys.exit(main())
