"""Port of `.ci/scripts/quality/announce-gate-skips.sh`.

Announces, loudly, which gates a CI-control label removed from a run. The twin's own header carries the WHY and it is worth restating because it is the reason this file is not just a `case` statement: the repo's label opt-outs are STEP-level `if:` conditions, and a skipped step leaves the job `success` and prints NOTHING. A run whose media gates were all removed by
`no-media-quality` therefore looks exactly like a run where they all passed. The announcer runs UNCONDITIONALLY, outside that `if:`, so the hold is visible in the log.

NOT A REGISTERED GATE, so there is no `package.json:<line>` to cite the way the `check:ci-*` ports do. `grep -n announce-gate-skips package.json` matches nothing; it is a plain workflow step, invoked at `ci-quality.yml:1313` (`no-media-quality check:ci-tutorial-casts check:ci-tutorial-parity`) and `ci-quality.yml:1644` (`no-media-quality check:ci-i18n-media`). Its own coverage
lives in the gate test `.ci/rediacc_ci/tests/gates/test_gate_gate_skip_announcer.py`, which ALSO reads those two workflow lines back and checks that every gate behind a `no-media-quality` `if:` is named in an announcer call. Its own bash twin was retired in W7 P5 census batch A8, so that test drives this port alone.

THE FOUR STATES, reproduced exactly, and the two refusals are the interesting half:

  hard   one line naming how many gates ARE enforced. Exit 0. This is the
         proof the announcer ran at all, because a silent instrument and a
         missing instrument look identical.
  skip   a `::warning::`, two `gate-skips:` lines, and a step summary naming
         every held gate. Exit 0.
  unset  treated as hard. A wiring break must never read as "gates removed".
  other  REFUSE, exit 2. The step `if:` treats an unrecognised mode as "run",
         which is fail-closed but completely silent; this is the only place a
         typo'd mode string is ever reported.

ZERO GATE NAMES IS A REFUSAL TOO (`$# -lt 2`, exit 2): an announcer with nothing to announce is a miswired announcer, not a clean run. That is the anti-vacuity rule of this script and it is carried across unchanged.

ONE DIVERGENCE, IN ONE STRING. The usage line interpolates `$0`, the path the shell was handed. `sys.argv[0]` is the same idea and resolves to this module's own file under `python3 -m`, so the two sides print different program names on that line and nowhere else. Reproducing bash's `$0` exactly is not possible for a module invoked by name, and hardcoding the twin's `.sh` path would
print a path that did not run. The differential masks the program token and compares the rest byte for byte.

EVERYTHING ELSE IS BYTE-IDENTICAL, including the step-summary block: `$*` joins with a single space (IFS's first character, unmodified here), the markdown uses backticks the twin escaped for bash, and the summary is APPENDED, never truncated, because GITHUB_STEP_SUMMARY accumulates across steps.

K=5 LEDGER: `.ci/shadow/w7p6-announce-gate-skips.observations.jsonl`.
"""

from __future__ import annotations

import os
import sys

MODES = ("hard", "skip")


def main(argv: list[str]) -> int:
    # `${GATE_SKIP_MODE:-hard}`: an EMPTY value falls back to hard as well,
    # which is the fail-closed direction and the twin's.
    mode = os.environ.get("GATE_SKIP_MODE") or "hard"

    if len(argv) < 2:
        print(
            "usage: GATE_SKIP_MODE=hard|skip %s <label> <gate...>" % sys.argv[0],
            file=sys.stderr,
        )
        return 2

    label = argv[0]
    gates = argv[1:]
    joined = " ".join(gates)
    count = len(gates)

    if mode not in MODES:
        print(
            "announce-gate-skips: unknown GATE_SKIP_MODE '%s' (expected hard|skip)" % mode,
            file=sys.stderr,
        )
        return 2

    if mode == "hard":
        print(
            "gate-skips: none. %d gate(s) enforced in this job (label '%s' not applied): %s"
            % (count, label, joined)
        )
        return 0

    print("::warning::label '%s' removed %d gate(s) from this job: %s" % (label, count, joined))
    print(
        "gate-skips: %d gate(s) NOT run in this job because the PR carries '%s': %s"
        % (count, label, joined)
    )
    print("gate-skips: this is a temporary hold. Remove the label to restore them.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Gates skipped by `%s` (%d in this job)\n" % (label, count))
            fh.write("\n")
            fh.writelines("- `%s` -- did NOT run\n" % gate for gate in gates)
            fh.write("\n")
            fh.write("These gates are held, not exempt. Remove the `%s` label as\n" % label)
            fh.write("soon as the work it is waiting on lands, and let the run go red\n")
            fh.write("if the underlying defect is still there.\n")
            fh.write("See docs/agent-reference/ci-gates.md.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
