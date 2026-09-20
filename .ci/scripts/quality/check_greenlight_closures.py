#!/usr/bin/env python3
"""Entry point for the ported greenlight-closure-path gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.greenlight_closures`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.greenlight_closures` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and no `emit:`, no `blocker:`, no `id:`, no `kind:`, no `lane:`, no `run:`, no `why:`. The absences are carried as deliberately as the presences: an invented `lane:` would pin a placement the derivation currently makes on
its own.

`needs: node` IS LOAD-BEARING AFTER THE MOVE, and this is the pair that proves the rule. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin got `node` for FREE from its own body -- it shells out to `node -e` to require greenlight.cjs and print the closure paths. This two-import entry point runs no node and `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:300`), so it infers NOTHING. Measured on both files rather than assumed: `inferredNeeds(twin)` is `["node"]` and `inferredNeeds(this file)` is
`[]`. Carried whole, both sides still resolve to {node}, and the port still
runs node for the same reason the twin does.

DRIVEN, on this tree, both streams captured SEPARATELY, under `CI=true` so the
twin's own colour switch is off (`if [[ "${CI:-}" == "true" ]]; then GREEN=""`):

    CI=true .ci/scripts/quality/check-greenlight-closures.sh  -> exit 0
    CI=true .ci/scripts/quality/check_greenlight_closures.py  -> exit 0
    stdout: byte-identical, 596 bytes, sha256
      312143c2556ccf1d1c3bef594e09357261c2bfeb408187065e1133fe521b117f
    stderr: empty on both sides

WITHOUT `CI=true` the two stdouts differ by exactly the twin's ANSI wrapper on
its first line and nothing else: identical once the ANSI CSI escapes are stripped from both. That residue is the twin's colour policy, which tests `CI` and neither the tty nor NO_COLOR; the module's own docstring records it as reported-not-reproduced.

THE PORT NEEDED ONE FIX TO REACH THAT PARITY, made here rather than papered over. It sent its headline through `log.info`, which writes to STDERR by design,
while the six indented continuation lines below it went to stdout -- ONE
paragraph split across TWO streams, so a reader piping stdout saw six dangling continuation lines under no heading. The twin echoes all seven to stdout, and `battery_clean_tree` (this same batch) already prints its verdict to stdout for the same reason. Fixed by printing the headline to stdout with the `✓` written out, which is the glyph `log.info` would have prefixed.

DRIVEN RED AS WELL, against a plant in the real tree: one bogus path (`__gate_probe_missing.txt`) added to the `e2e_migrate` closure in `.ci/scripts/ci/greenlight.cjs`. Both sides exit 1, both print an EMPTY stdout and a byte-identical 289-byte stderr naming `__gate_probe_missing.txt -- named by a closure but NOT ON DISK`. The plant was then reverted by its exact inverse and the
file verified byte-identical (sha256 26b3eed64efa3b96c03b6474e142d5f6a96bfb831c74a94d2dec08e2c5cc4a49) to its pre-plant state, with both sides back at exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-greenlight-closures.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Greenlight closure paths
needs: node
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import greenlight_closures

if __name__ == "__main__":
    raise SystemExit(greenlight_closures.main(sys.argv[1:]))
