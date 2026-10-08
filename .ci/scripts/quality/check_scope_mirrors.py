#!/usr/bin/env python3
"""Entry point for the PR-scope mirror gate. Logic is in `rediacc_ci.quality.scope_mirrors`.

The rule set, the registry and baseline formats, the eleven checks (C0-C10) and the named blind spots are documented on the module; agent/plans/PLAN-scope-mirrors.md is the design. This file exists so the registry can invoke the gate BY PATH (the parity-tokenizer reason in `_cipath`'s docstring), and the `---- gate ----` header is here because `gate-bind` reads the file package.json names.

The `_cipath` import takes a name and uses it, as `check_inline_suppressions.py` does: `CI_DIR` anchors the repository root on this file's own location, so the gate answers the same from any working directory, and no unused-import marker is needed.

Flags: `--selftest`, `--root <dir>` (the gate test runs the entry point against a copied tree), `--repin <id>|--all`, `--write-baseline [--first-seed]`.

---- gate ----
step: PR scope rules agree with their CLAUDE.md source
needs: none
lane: quality-content
selftest: true
why: CLAUDE.md is the one written source of the PR-scope rules, and seven other files
     restate them by hand; a copy nobody re-reads drifts silently. The canonical spans
     are anchored and pinned by sha, every registered mirror is located and judged
     (verbatim or terms), quotes of CLAUDE.md must still be quotes, and an unregistered
     restatement or anchor is red. No `paths`, deliberately: an edit to CLAUDE.md, any
     mirror, or a guard constant can each break agreement, so the gate runs on every change.
---- end gate ----
"""

import sys

from _cipath import CI_DIR
from rediacc_ci.quality import scope_mirrors

if __name__ == "__main__":
    raise SystemExit(scope_mirrors.main(sys.argv[1:], root=CI_DIR.parent))
