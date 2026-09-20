#!/usr/bin/env python3
"""Entry point for the ported devbox exec-invocation gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.devbox_exec`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.devbox_exec` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-devbox-exec.sh` with an awk range over its `---- gate ----` block and diffed line by line against this one rather than retyped from memory. The twin carried exactly six fields -- `step`, `emit`, `blocker`, `needs`, `selftest`, `lane` -- and no `id:`, no `run:`, no `kind:`, no `why:`. All six
are here, and the `blocker:` is byte for byte the twin's: it is a live suppression reason under the BLOCKER convention, and a suppression whose reason went missing in a file move is a quiet exemption. The pilot lost exactly `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks
(`gate-bind.ts:1724`) while the registration assertions above them still ran.

NO `id:` IS CORRECT HERE, and it was checked rather than assumed: `derivedId` (`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this basename derives `check:ci-devbox-exec`, which is the manifest id. The sibling `check_silent_failure_patterns.py` in this same batch does NOT have that luck and carries an explicit `id:`.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing and the registered command stays the bare path. It is copied because the twin declared it and because it is TRUE of this port -- `devbox_exec.main(["--selftest"])` runs four real controls and exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions the declared needs with `inferredNeeds(source)`; the twin infers nothing and this two-import entry point infers nothing either, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both sides resolve to the empty set `needs: none`
declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-devbox-exec.sh   -> exit 0
    .ci/scripts/quality/check_devbox_exec.py   -> exit 0
    stderr: byte-identical (EMPTY on both sides)
    stdout: identical after ANSI-strip, sha256 c720b5a26352abfd...

THE ONE RESIDUE, stated rather than smoothed over. The twin assigns its GREEN to a literal ANSI escape UNCONDITIONALLY (`check-devbox-exec.sh:53`, an ESC byte followed by `[0;32m`) and wraps its success marker in it even when stdout is a file; the port prints through the house rule that colour goes only to a tty. So the twin's clean stdout is 661 bytes and the port's is 650, and
the eleven-byte difference is exactly one seven-byte set-green sequence plus one four-byte reset. Named exactly: the ONLY normalisation applied is one sed deleting every CSI SGR sequence, `s/<ESC>[[0-9;]*m//g` with the ESC byte written literally, applied to BOTH sides. Not "fixed" in the port, because the alternative is hard-coding escapes into a redirected stream and abandoning
the tty and NO_COLOR handling `rediacc_ci.log` exists to centralise.

DRIVEN RED AS WELL, which is the half that matters. A `_gate_probe_devbox_exec`
function appended to `.ci/lib/devbox.sh` invoking `"$d" exec -it "$cid" bash` --
the quoted two-word docker command that is this gate's entire subject -- makes BOTH sides exit 1, and both name the same finding at the same line:

    FAIL B1. these invoke a possibly-two-word docker as a single command:
             702:    "$d" exec -it "$cid" bash

ANSI-stripped stdout is identical on the red side too (sha256 86d11e691ed58dc5..., twin 552 bytes to the port's 530, again pure colour), stderr empty on both. The plant was removed by its exact inverse, `.ci/lib/devbox.sh` verified back at sha256 dd63548fda6b1264... and `git status --porcelain` diffed against its pre-plant capture with no difference, because a runner that writes
into the real tree makes twin and port agree by both reading the same corrupted file.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-devbox-exec.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Devbox exec invocation
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import devbox_exec

if __name__ == "__main__":
    raise SystemExit(devbox_exec.main(sys.argv[1:]))
