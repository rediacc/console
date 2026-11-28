#!/usr/bin/env python3
"""Run `rediacc_ci.quality.agent_session_archival_gate` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/agent_session_archival_gate.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import agent_session_archival_gate

if __name__ == "__main__":
    _gate_args.parse(
        "check_agent_session_archival.py",
        sys.argv[1:],
        # `--move` is a switch plus a bare name on purpose: main() reads the target itself and refuses a missing one with its own message ("needs a session directory name"), which test_gate_agent_session_archival pins.
        switches=("--selftest", "--status", "--prune-reviews", "--write", "--force", "--move"),
        valued=("--label",),
        positional="<session-dir>",
    )
    raise SystemExit(agent_session_archival_gate.main(sys.argv[1:]))
