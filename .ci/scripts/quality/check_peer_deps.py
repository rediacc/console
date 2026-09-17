#!/usr/bin/env python3
"""Entry point for the ported peer-dependency-conflict gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.peer_deps`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below, for the measurement taken on this tree that licences the flip.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.peer_deps` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. That shortness is the twin's shape, not an omission: the batch before this one lost `emit: false` and a blocker off a header and SEVEN GATES
PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran and still agreed.

`selftest: true` IS INERT HERE and is carried anyway. `headerLines` only emits that field for `.ts` (`gate-bind.ts:598`, `selftestIsReal`), so for a `.py` gate it decides nothing; the registered command stays the bare path. It is copied because the twin declared it and because it happens to be TRUE of this port: `peer_deps.main(["--selftest"])` runs a real control battery.

THE RESOLVED NEED SET DOES NOT MOVE. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin inferred nothing (`npm ls` is not one of the runtime patterns) while this two-import entry point also infers nothing, so both sides resolve to the empty set that `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY:

    .ci/scripts/quality/check-peer-deps.sh    -> exit 0
    .ci/scripts/quality/check_peer_deps.py    -> exit 0
    stdout: byte-identical (EMPTY on both sides)

The empty stdout is exactly why the streams are captured apart: this gate puts its whole clean verdict on stderr, so a merged comparison would have compared the log lines and a stdout-only comparison of merged output would have compared nothing. The stderr lines deliberately DIFFER: the port's pass line carries the shape (`npm ls` exit status and the line count it scanned) where
the twin's says only that it found nothing, which is the anti-vacuity rule applied to a gate whose green used to be indistinguishable from an empty haystack.

DRIVEN RED AS WELL, which for this pair is the load-bearing half because the clean stdout is empty and an empty comparison proves only that neither side crashed. An `npm` shim ahead of the real one on PATH printed one `npm error invalid: ...` line to STDERR and exited 1, reproducing both halves of the twin's contract at once (the `2>&1` merge and the `|| true`). Both sides exit 1
and print the same three-line stdout block, sha256 10eaeecd8b8bcaa38d75ae1ced463b52b5beade1d5a3e312efdc1784da70131a on both, and their stderr is identical too.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-peer-deps.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Verify no peer dependency conflicts needs: none selftest: true lane: quality-code ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import peer_deps

if __name__ == "__main__":
    raise SystemExit(peer_deps.main(sys.argv[1:]))
