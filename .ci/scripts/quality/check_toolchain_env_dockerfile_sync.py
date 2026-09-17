#!/usr/bin/env python3
"""Entry point for the ported toolchain.env/Dockerfile sync gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.toolchain_env_dockerfile_sync`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.toolchain_env_dockerfile_sync` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 12 line(s). The twin carried exactly these fields, in this order: `step`, `emit`, `blocker`, `needs`, `selftest`,
`why`. NO `id:`: the basename derives `check:ci-toolchain-env-dockerfile-sync`, the manifest id. The `why:` field is FIVE lines of continuation and all five moved
with it, which is the field a line-by-line diff exists to protect.
The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing beyond what it declares from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as
prose (`gate-header.ts:301`). Both sides bind to `needs: ['node']`.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh
      -> exit 0
    .ci/scripts/quality/check_toolchain_env_dockerfile_sync.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 916 bytes, sha256 a5a90daed94641de...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters.
The plant rewrites `GO_VERSION=1.26.6` to `GO_VERSION=9.9.9` in
`.devcontainer/toolchain.env`, leaving the Dockerfile's `ARG GO_VERSION=1.26.6`
untouched, which is the exact divergence this gate exists to catch. THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN: the planted value was read back out of the env file and the Dockerfile's ARG line was printed to confirm it still said 1.26.6, so the two files genuinely disagreed. The file was restored from a `cp` and its sha256 compared with the pre-plant value
(99fa72aa0760f6b6...), identical. Both sides -> exit 1, stdout 724 bytes, sha256 977922f5a3bc2e7a..., stderr 453 bytes, sha256 ca485efa31cb8714....

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh` is NOT deleted by this change. It stays on disk as the differential twin that `.ci/rediacc_ci/tests/test_quality_toolchain_env_dockerfile_sync.py` compares this port against, and deleting it is W7 P5's job in a later change.

---- gate ---- step: Toolchain env/Dockerfile sync emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: node selftest: true why: check-toolchain-pins.sh's A1 deliberately EXEMPTS
GO_VERSION/NODE_VERSION
     from its single-source check (they legitimately appear elsewhere: go.mod,
     third-party action inputs) -- which also removes any check that the TWO
     files meant to carry the identical value on purpose (toolchain.env and the
     Dockerfile's matching ARG) actually do. This is that narrower check.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import toolchain_env_dockerfile_sync

if __name__ == "__main__":
    raise SystemExit(toolchain_env_dockerfile_sync.main(sys.argv[1:]))
