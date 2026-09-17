#!/usr/bin/env python3
"""Entry point for the ported devcontainer-script-hygiene gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.devcontainer_scripts`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.devcontainer_scripts` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-devcontainer-scripts.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 8 line(s). The twin carried exactly these fields, in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. NO
`id:`, and that is checked rather than assumed: `derivedId` (`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this basename derives `check:ci-devcontainer-scripts`, which is the manifest id. The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks
(`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides bind to `needs: []`, which is what `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-devcontainer-scripts.sh
      -> exit 0
    .ci/scripts/quality/check_devcontainer_scripts.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 401 bytes, sha256 bf3c6dcf555f23e9...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. The plant is an UNTRACKED `.devcontainer/__gate_probe_devcontainer_scripts.sh` carrying `git clone ... 2>/dev/null`, i.e. rule A's exact shape: a PRIMARY operation whose stderr is discarded. Untracked is the right shape here because the gate's corpus is the glob `"$DC"/*.sh`, not `git ls-files`, so a probe the sweep never walks
would have been a control failure rather than a gate failure. The plant was removed with `rm` and `git status --porcelain` diffed against its pre-plant capture with no difference, because a runner that writes into the real tree makes twin and port agree by both reading the same corrupted tree. Both sides -> exit 1, stdout 314 bytes, sha256 c83e1b98f1ba9d4a..., stderr 232 bytes,
sha256 b47774f79c5278be....

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-devcontainer-scripts.sh` is NOT deleted by this change. It stays on disk as the differential twin that `.ci/rediacc_ci/tests/test_quality_devcontainer_scripts.py` compares this port against, and deleting it is W7 P5's job in a later change.

---- gate ---- step: Devcontainer script stderr visibility emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none selftest: true lane: quality-code ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import devcontainer_scripts

if __name__ == "__main__":
    raise SystemExit(devcontainer_scripts.main(sys.argv[1:]))
