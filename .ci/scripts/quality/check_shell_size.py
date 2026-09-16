#!/usr/bin/env python3
"""Entry point for the ported shell-file-size gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.shell_size`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.shell_size` works but is the wrong registration
because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from
`.ci/scripts/quality/check-shell-size.sh` by an awk range over its
`---- gate ----` block, de-commented, and diffed as an ordered list of whole
lines against the block in this docstring. The twin carried exactly SIX fields
in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. No `id:`,
no `run:`, no `kind:`, no `why:`. All six are here and the `blocker:` is byte for
byte the twin's, because it is a live suppression reason under the BLOCKER
convention and a suppression whose reason went missing in a file move is a quiet
exemption. The pilot lost exactly `emit: false` plus a blocker off a header and
SEVEN GATES PASSED ANYWAY: `emit: false` suppresses only the three
workflow-region checks (`gate-bind.ts:1724`) while the registration assertions
above them still ran and still agreed.

NO `id:` IS CORRECT HERE, checked rather than assumed. `derivedId`
(`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this
basename derives `check:ci-shell-size`, which is the manifest id.

`selftest: true` IS INERT for a `.py` gate (`headerLines` emits that field only
for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and
because it is TRUE of this port: `shell_size.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files
rather than by reading them. `bind()` unions declared needs with
`inferredNeeds(source)`; the twin infers `[]` and this two-import entry point
infers `[]`, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides resolve to the empty set `needs: none`
declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-shell-size.sh   -> exit 0
    .ci/scripts/quality/check_shell_size.py   -> exit 0
    stdout: BYTE-IDENTICAL, 587 bytes, sha256 f36d156d21e45bd8...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE
against an unchanged tree to establish that its own output is byte-stable
against itself; it is, on both streams. Both sides also emit the same ANSI
colour to a redirected stream, so even the escapes match byte for byte.

DRIVEN RED AS WELL, which is the half that matters. The plant is a 5002-line
shell script at `.ci/scripts/__gate_probe_shell_size.sh`, one line over the
5000-line threshold and carrying no `# shellcheck extended-analysis=false`
directive. It is deliberately UNTRACKED, which exercises the half of the twin's
discovery that `git ls-files` alone would miss: the gate unions
`ls-files '*.sh'` with `ls-files --others --exclude-standard '*.sh'` precisely
because a file is being grown before it is committed. THE CONTROL WAS PROVED
BEFORE EITHER SIDE RAN, by running that same union and confirming the plant
appears in it, because a probe the sweep never walks is how a plant fails to
fire for reasons that say nothing about the gate.

    both sides -> exit 1, stdout BYTE-IDENTICAL (607 bytes,
    sha256 3bc1caedc30fead2...), stderr BYTE-IDENTICAL and empty:

    FAIL S1. these will make shellcheck's dataflow analysis explode:
             .ci/scripts/__gate_probe_shell_size.sh (5002 lines)
      ok   S2. 621 shell file(s) actually scanned

The plant was removed with `rm` and `git status --porcelain` diffed against its
pre-plant capture with no difference, because a runner that writes into the real
tree makes twin and port agree by both reading the same corrupted tree.
INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-shell-size.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Shell file size
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import shell_size

if __name__ == "__main__":
    raise SystemExit(shell_size.main(sys.argv[1:]))
