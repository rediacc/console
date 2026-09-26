#!/usr/bin/env python3
"""Entry point for check:ci-gate-tree-writes. Logic is in `rediacc_ci.quality.gate_tree_writes`.

Same 2-import shape as `check_pool_writer_safety.py`, its sibling: that gate holds GATE TESTS to "a tree writer declares an exclusive tree: claim", this one holds the GATES themselves to it. `--report` prints every site and exits 0; `--selftest` runs the controls alone.

---- gate ----
step: Gates that write the real tree declare it
needs: node
lane: quality-code
selftest: true
why: A gate that writes the shared tree without an exclusive tree: claim runs beside its readers and leaves residue on a hard kill; check:ci-pool-writer-safety only sees gate tests
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import gate_tree_writes

if __name__ == "__main__":
    raise SystemExit(gate_tree_writes.main(sys.argv[1:]))
