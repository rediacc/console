#!/usr/bin/env python3
"""Entry point for the ported cli-doc-coverage gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.cli_doc_coverage`.

CUT OVER FROM BASH 2026-09-07 (W7 P4), on the condition this docstring used to be waiting for. Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-clidoc --assert --k 5
    -> equivalence holds over 7 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and this port exit 0 with byte-identical stdout and byte-identical stderr. The failure direction was driven too, since two greens prove nothing about a gate: a fixture copy of the tree with every mention of `--until-final` stripped out of `.claude/skills/ci-watch/SKILL.md` turns both sides red, exit 1, again
byte
for byte.

WHY AN ENTRY POINT AT ALL, rather than registering the module. Both reasons are measured, and `check_npmrc.py` records them for the pilot:

  1. A port CANNOT be run by path. `python3 .ci/rediacc_ci/quality/...` dies at
     `from rediacc_ci import ...` because nothing put `.ci` on `sys.path`. The
     three-line insert below is what makes a path invocation work.
  2. `python3 -m rediacc_ci.quality.cli_doc_coverage` DOES work and is still
     wrong: `check:ci-parity`'s tokenizer cannot read `-m`, so it resolves the
     leaves to `[python3]`. The registered command is the bare path to this file.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-cli-doc-coverage.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ----
step: CLI docs stay in sync with their scripts' real flags
     # The EXISTING step name, character for character, not a tidier one.
     # gate-bind matches a header against the step that already runs, so
     # renaming a step is a separate change from moving what it invokes.
needs: none
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import cli_doc_coverage

if __name__ == "__main__":
    raise SystemExit(cli_doc_coverage.main(sys.argv[1:]))
