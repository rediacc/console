#!/usr/bin/env python3
"""Entry point for the inline-suppressions gate: no NEW lint or type suppression marker, anywhere.

Operator ruling 2026-10-08 banned inline suppressions (a Python `noq[a]` comment, `type: ignor[e]`, `@ts-ignor[e]`, `eslint-disabl[e]`, `biome-ignor[e]`, `//nolin[t]`, a shellcheck or hadolint directive). The logic and the marker grammar live in `rediacc_ci.quality.inline_suppressions`, which the pre-edit and pre-bash hooks import too, so the keystroke and CI judge by one rule.

    check_inline_suppressions.py                        the gate: controls first, then the tree against the baseline
    check_inline_suppressions.py --selftest             the controls alone
    check_inline_suppressions.py --write-baseline       record a drain; refuses any growth
    check_inline_suppressions.py --count <path>...      markers under each path prefix; a path with no code file read is refused, never 0

THE `_cipath` IMPORT TAKES A NAME AND USES IT, which is the one difference from every sibling entry point here. They spell it `import _cipath` for the side effect alone, which ruff accepts because `lint.pyflakes.allowed-unused-imports` in pyproject.toml names the module. `CI_DIR` anchors the repository root on this file's own location, so the gate answers the same from any working directory.

`needs: submodules` IS LOAD-BEARING: private/renet and private/account are in scope, and a lane that does not check them out would turn their half of the scan into a refusal (CI) or a silent gap (a lane without the check).

`lane: quality-code` OVERRIDES THE CHEAPEST-LANE INFERENCE, which picks quality-submodule-branches. That lane has no `- id: setup` (so no gate-bind region may hold the step) and checks out with `filter: blob:none`, where reading ~6,000 files would fetch every blob lazily, one round trip each. quality-code checks out the submodules in full and already runs the source-shape gates.

---- gate ----
step: Inline suppression markers
needs: submodules
lane: quality-code
selftest: true
why: inline lint and type suppressions are banned (operator 2026-10-08); the existing ones are a
     shrink-only baseline keyed on file, marker kind and code, so a new one is red and a removed
     one must be drained in the same commit
---- end gate ----
"""

import sys

from _cipath import CI_DIR
from rediacc_ci.quality import inline_suppressions

if __name__ == "__main__":
    raise SystemExit(inline_suppressions.main(sys.argv[1:], root=CI_DIR.parent))
