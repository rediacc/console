#!/usr/bin/env python3
"""Entry point for the ported agent-browser exit-status gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.agent_browser_exit`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.agent_browser_exit` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-agent-browser-exit.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `lane:`, no `emit:`, no `blocker:`, no
`id:`, no `run:`, no `kind:`, no `why:`. The missing `lane:` is the twin's shape and is carried as an absence: the manifest already places this step in `quality-static`, so a `lane:` here would be a new claim.

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-agent-browser-exit`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and because `agent_browser_exit.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. The twin infers `[]` and this entry point infers `[]`; both resolve to the empty set `needs: none` declares.

THIS ENTRY POINT IS INVISIBLE TO THE GATE IT REGISTERS, and that was checked rather than assumed, because a new file landing in the swept directory is exactly how a cutover changes a verdict by accident. The twin's sweep is
`grep -rl --include='*.sh'` (`check-agent-browser-exit.sh:55`), so a `.py` file
in that directory is not enumerated at all. The twin's self-exclusion `grep -vF 'check-agent-browser-exit.sh'` and the port's `SELF_NAME` constant therefore still name only the bash twin, correctly, and neither needs to grow a second entry.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-agent-browser-exit.sh   -> exit 0
    .ci/scripts/quality/check_agent_browser_exit.py   -> exit 0
    stdout: BYTE-IDENTICAL, 368 bytes, sha256 8c4f209925a0a5bb...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE against an unchanged tree to establish byte-stability against itself; it is stable on both streams.

DRIVEN RED AS WELL, AND THE FIRST PLANT DID NOT FIRE. That is worth writing down because the CONTROL was wrong, not the gate, which is the same shape that cost batch 6 two plants. The first probe was a shell script under `.ci/scripts/` containing a bare `agent-browser open "$url"`, and BOTH sides stayed green. The cause is `check-agent-browser-exit.sh:31`: the sweep skips any file
that does not match `^[[:space:]]*set[[:space:]]+-[a-z]*e`, deliberately, because only a script that would DIE on a non-zero status has a load-bearing exit code. The probe had no `set -e`, so it was never a subject. Suspecting the gate at that point would have been wrong in both directions: the gate was right, and the probe was not in its corpus.

The corrected probe carries `set -euo pipefail`, and the control was then proved BEFORE either side ran, on both preconditions separately: the file appears in
the twin's own `grep -rl --include='*.sh' 'agent-browser'` enumeration, AND it
satisfies the `set -e` test the sweep applies next.

    both sides -> exit 1, stdout BYTE-IDENTICAL (270 bytes), stderr
    BYTE-IDENTICAL (511 bytes, sha256 83d08b69154573f2...):

    `agent-browser open` exit status is load-bearing in a `set -e` script:
      .ci/scripts/__gate_probe_abe.sh:4
        agent-browser open "$url"

The plant was removed with `rm` and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-agent-browser-exit.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: agent-browser exit status
needs: none
selftest: true
`slow: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import agent_browser_exit

if __name__ == "__main__":
    raise SystemExit(agent_browser_exit.main(sys.argv[1:]))
