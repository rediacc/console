#!/usr/bin/env python3
"""An in-script kill timer above its own job's ceiling is dead code in CI.

WHY THIS EXISTS, and it is a defect this repository actually shipped for a few hours on 2026-09-08. `check:ci-pytest` carries its own `RUN_TIMEOUT_S`, raised to 3600s so a long suite would be KILLED with a named cause rather than crash. It runs as the `Python package tests` step of `quality-security` in `ci-quality.yml`, and that job declares `timeout-minutes: 20`. 3600 > 1200, so
the timer could never fire: GitHub cancels the job at twenty minutes, and a cancelled job's only clue is

    The operation was canceled.

No verdict, no KILLED line, no cause -- exactly the chain `check_job_timeout_headroom.py` documents, one level down. Seven gates were green over that raise. They could not see it: the number is legal Python, the suite passes locally where no ceiling applies, and nothing compared the two.

WHY THE HEADROOM GATE DOES NOT COVER IT. `check:ci-timeout-headroom` asks whether a JOB's declared `timeout-minutes` clears its OBSERVED worst case. That is the outer dimension and a different question, and its baseline names two jobs (`Validate Promotion`, `Stage Artifacts`), both in `ci.yml`. It never reads a script, so an in-script timer is invisible to it in every workflow.

WHAT THIS ASSERTS. For every registered gate that declares a `*_TIMEOUT_S` constant and runs as a CI step, that timer must be STRICTLY BELOW its job's `timeout-minutes`. Equal is a finding too: a timer that fires at the same instant the job dies is a race, not a diagnostic.

WHAT IT DOES NOT ASSERT. Not that the number is big enough -- that is a measurement, and it belongs with the suite that measures. Only that the smaller of the two guards is the one that can actually speak.

---- gate ---- step: Inner kill timers are reachable needs: none selftest: true lane: quality-code why: A gate's own kill timer must sit below its job's timeout-minutes, or CI
     cancels the job first and the gate's diagnostic never prints -- the failure
     shape reads as an unexplained cancel rather than as a named verdict.
---- end gate ----
"""

import json
import pathlib
import re
import sys

import _cipath  # noqa: F401
from rediacc_ci.controls import Controls, plant

LOCK_REL = "scripts/ci-runner/gates.lock.json"

# A module-level constant naming seconds. Anchored at column 0 so a timer discussed in a comment or held in a string fixture is not mistaken for one that is declared -- the same trap `check_pytest.py`'s corpus counter fell into.
TIMER_RE = re.compile(r"^([A-Z][A-Z0-9_]*_TIMEOUT_S)\s*=.*?(\d{2,})", re.MULTILINE)


def job_ceilings(workflow_text: str) -> dict[str, int]:
    """`{job id: timeout-minutes}` for one workflow.

    Read with a line scanner rather than a YAML parser on purpose: this gate must run with no third-party import, and the two shapes it needs -- a job key at two spaces, its `timeout-minutes` at four -- are pinned by the repo's own workflow lint. A job with no declared ceiling is simply absent, which the caller reports rather than treats as infinity.
    """
    out: dict[str, int] = {}
    current = None
    for line in workflow_text.splitlines():
        key = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if key:
            current = key.group(1)
        cap = re.match(r"^    timeout-minutes:\s*(\d+)\s*$", line)
        if cap and current:
            out[current] = int(cap.group(1))
    return out


def inner_timers(source: str) -> list[tuple[str, int]]:
    return [(name, int(value)) for name, value in TIMER_RE.findall(source)]


def findings(
    timers: list[tuple[str, int]], ceiling_minutes: int | None, gate_id: str, leaf: str
) -> list[str]:
    """One line per timer that cannot fire. An absent ceiling is NOT a pass."""
    out = []
    for name, seconds in timers:
        if ceiling_minutes is None:
            out.append(
                "%s (%s): %s=%ds, but its job declares no timeout-minutes, so nothing "
                "bounds the step and this timer's reachability cannot be established."
                % (gate_id, leaf, name, seconds)
            )
            continue
        ceiling = ceiling_minutes * 60
        if seconds >= ceiling:
            out.append(
                "%s (%s): %s=%ds is at or above its job's ceiling of %ds "
                "(timeout-minutes: %d). CI cancels the job first, so this timer never "
                "fires and the failure arrives as `The operation was canceled.` with no "
                "verdict. Lower the timer below the ceiling, or raise the job."
                % (gate_id, leaf, name, seconds, ceiling, ceiling_minutes)
            )
    return out


_WF = """\
name: x
jobs:
  quality-code:
    timeout-minutes: 15
    steps: []
  no-ceiling:
    steps: []
"""


def selftest(*, verbose: bool = False) -> bool:
    """Both directions for every rule, before the live scan is believed."""
    c = Controls("inner-timeout-reachable", floor=12, verbose=verbose)

    caps = job_ceilings(_WF)
    c.check("a declared ceiling is read", caps.get("quality-code"), 15)
    c.check("a job without one is ABSENT, not zero and not infinite", "no-ceiling" in caps, False)
    c.check("and an unknown job is absent too", caps.get("nope"), None)

    c.check(
        "a module-level timer is found",
        inner_timers("RUN_TIMEOUT_S = 900\n"),
        [("RUN_TIMEOUT_S", 900)],
    )
    c.check(
        "one wrapped in an env default is found at its default",
        inner_timers('RUN_TIMEOUT_S = int(os.environ.get("X") or 1080)\n'),
        [("RUN_TIMEOUT_S", 1080)],
    )
    # THE TWO A LOOSER PATTERN WOULD GET WRONG.
    c.check(
        "an INDENTED assignment is not a module constant",
        inner_timers("    RUN_TIMEOUT_S = 900\n"),
        [],
    )
    c.check(
        "a timer named in a comment is not a declaration",
        inner_timers("# RUN_TIMEOUT_S = 900\n"),
        [],
    )

    below = [("T_TIMEOUT_S", 600)]
    c.check("a timer below its ceiling is clean", findings(below, 15, "g", "f"), [])
    c.check(
        "one ABOVE it is reported",
        len(findings([("T_TIMEOUT_S", 1800)], 15, "g", "f")),
        1,
    )
    # EQUAL IS A FINDING: firing at the instant the job dies is a race.
    c.check(
        "one EQUAL to it is reported too", len(findings([("T_TIMEOUT_S", 900)], 15, "g", "f")), 1
    )
    c.check("a missing ceiling is reported, never passed", len(findings(below, None, "g", "f")), 1)
    c.check("no timer at all yields nothing to say", findings([], 15, "g", "f"), [])

    # A PLANTED SUBJECT, so the reader is a real one and not the pattern's echo.
    clean = 'RUN_TIMEOUT_S = int(os.environ.get("X") or 600)\n'
    mutant = plant(clean, "600", "9000")
    c.check(
        "PLANT: raising the constant in a real source flips the verdict",
        (
            len(findings(inner_timers(clean), 15, "g", "f")),
            len(findings(inner_timers(mutant), 15, "g", "f")),
        ),
        (0, 1),
    )
    return c.report()


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return 0 if selftest(verbose=True) else 1
    if not selftest():
        print(
            "✗ CONTROL FAILED: this gate's own controls did not pass, so it refuses to "
            "report on the tree.",
            file=sys.stderr,
        )
        return 1

    root = pathlib.Path(__file__).resolve().parents[3]
    lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    workflows: dict[str, dict[str, int]] = {}
    problems: list[str] = []
    examined = 0

    for entry in lock:
        ci = entry.get("ci") or {}
        if ci.get("kind") != "step":
            continue
        wf_rel = ci.get("workflow", "")
        if wf_rel not in workflows:
            try:
                workflows[wf_rel] = job_ceilings((root / wf_rel).read_text(encoding="utf-8"))
            except OSError:
                workflows[wf_rel] = {}
        ceiling = workflows[wf_rel].get(ci.get("job", ""))
        for leaf in entry.get("leaves", []):
            try:
                source = (root / leaf).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            timers = inner_timers(source)
            if not timers:
                continue
            examined += 1
            problems.extend(findings(timers, ceiling, entry.get("id", "?"), leaf))

    # ANTI-VACUITY. Finding no timer anywhere means the reader broke or the convention was renamed, and a green would then mean "checked nothing".
    if examined == 0:
        print(
            "✗ scanned %d registered gate(s) and found NO script declaring a `*_TIMEOUT_S`\n"
            "  constant. At least one exists (check:ci-pytest), so either the lock stopped\n"
            "  naming leaves or the convention was renamed. This gate is checking nothing."
            % len(lock),
            file=sys.stderr,
        )
        return 1

    if problems:
        print("✗ %d in-script kill timer(s) cannot fire:" % len(problems), file=sys.stderr)
        for line in problems:
            print("    %s" % line, file=sys.stderr)
        return 1

    print("✓ %d in-script kill timer(s) sit below their job's ceiling" % examined)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
