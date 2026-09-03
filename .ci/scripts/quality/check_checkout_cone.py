#!/usr/bin/env python3
"""check:ci-checkout-cone -- a step may not run a file its job never checked out.

WHY THIS EXISTS, and it cost a CI cycle on 2026-09-03. `Stripe Sandbox` failed with

    .ci/scripts/ci/shadow-compare.sh: No such file or directory

The compare logic used to be 18 inline lines and needed no file on disk. Extracting
it to a script -- which check:ci-workflows was right to demand -- silently broke every
job whose sparse-checkout cone stopped at `.ci/config`. Three jobs were affected and
nothing in the tree could see it: the cone was well-formed, the script existed, the
step was correctly written. Each fact was true and the combination was not.

THAT IS THE CLASS. Existing gates check that a cone is well-formed and that a script
exists; none corroborates the static claim ("this job checks out X") against what the
job actually RUNS. This one does, and it generalises past shadow-compare to every
repo-relative path any `run:` step invokes.

WHAT IT DELIBERATELY DOES NOT DO. It resolves only paths that look like a script
INVOCATION at the start of a command or after a pipe/`&&` -- not every string that
happens to look like a path. A mention inside an echo, a heredoc, or an argument is
not an invocation, and flagging those would produce the kind of noise that gets a gate
suppressed. Under-reporting is the safe direction here: a missed path fails loudly in
CI with the exact message above, while a false positive blocks a correct workflow.

Exit 1 on any uncovered invocation, 2 on a failed control.
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
MIN_JOBS = 60

# A path at the start of a command, or right after a pipe / && / ; / `then`.
INVOKE = re.compile(
    r"(?:^|\||&&|;|\bthen\b|\bdo\b|\bexec\b|\bbash\b|\bsh\b|\bsudo\b)\s*"
    r"((?:\./)?(?:\.ci|scripts|\.github)/[\w./-]+\.(?:sh|py|cjs|mjs|js|ts))",
    re.MULTILINE,
)


def cone_of(job: dict) -> list[list[str] | None]:
    """The cone in effect after each step, in order. None means a FULL checkout."""
    out: list[list[str] | None] = []
    cur: list[str] | None = []  # nothing checked out yet
    for st in job.get("steps") or []:
        if isinstance(st, dict) and "actions/checkout@" in (st.get("uses") or ""):
            sc = (st.get("with") or {}).get("sparse-checkout")
            if sc is None:
                cur = None  # full checkout: everything is present
            else:
                add = [
                    ln.strip()
                    for ln in str(sc).splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                cur = None if cur is None else sorted(set(cur) | set(add))
        out.append(cur)
    return out


def covered(path: str, cone: list[str] | None) -> bool:
    if cone is None:
        return True
    # removeprefix, NOT lstrip: lstrip takes a CHARACTER SET, so
    # ".ci/scripts/x.sh".lstrip("./") is "ci/scripts/x.sh" -- the leading dot is
    # eaten and every cone comparison then fails. This gate's own control caught
    # it on the first run, which is the entire argument for writing controls first;
    # the same mistake in a resolver that reports LESS would have been silent.
    p = path.removeprefix("./")
    return any(p == c or p.startswith(c.rstrip("/") + "/") for c in cone)


def findings() -> tuple[list[str], int]:
    probs: list[str] = []
    njobs = 0
    for f in sorted(WF.glob("*.yml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        for jn, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict) or not job.get("steps"):
                continue
            njobs += 1
            cones = cone_of(job)
            for i, st in enumerate(job["steps"]):
                if not isinstance(st, dict):
                    continue
                run = st.get("run")
                if not isinstance(run, str):
                    continue
                for m in INVOKE.findall(run):
                    if not (ROOT / m.removeprefix("./")).is_file():
                        continue  # not a real path in this tree; not this gate's business
                    if not covered(m, cones[i]):
                        probs.append(
                            "%s: job `%s` runs `%s`, which its checkout cone does not "
                            "include (%s). The step is correct, the script exists, and "
                            "the file will still be missing at runtime."
                            % (f.name, jn, m, ", ".join(cones[i]) or "nothing")
                        )
    return probs, njobs


def selftest() -> int:
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print(
            "  %s  %s%s"
            % ("PASS" if ok else "FAIL", name, "\n        " + detail if detail and not ok else "")
        )
        if not ok:
            bad += 1

    # THE PLANT is the historical defect: a cone that stops at .ci/config, and a step
    # that runs .ci/scripts/ci/shadow-compare.sh.
    check(
        "PLANT: a cone stopping at .ci/config does NOT cover .ci/scripts/ci/x.sh",
        not covered(".ci/scripts/ci/shadow-compare.sh", [".github/actions", ".ci/config"]),
    )
    check(
        "CONTROL: adding .ci/scripts covers it",
        covered(
            ".ci/scripts/ci/shadow-compare.sh", [".github/actions", ".ci/config", ".ci/scripts"]
        ),
    )
    check("CONTROL: a FULL checkout covers everything", covered("anything/at/all.sh", None))
    check(
        "CONTROL: a sibling prefix is not a cone match (.ci/script must not cover .ci/scripts)",
        not covered(".ci/scripts/x.sh", [".ci/script"]),
    )
    # The matcher: an invocation is a command, not a mention.
    check(
        "an invocation at the start of a line is found",
        INVOKE.findall(".ci/scripts/ci/shadow-compare.sh") == [".ci/scripts/ci/shadow-compare.sh"],
    )
    check(
        "and after a pipe or &&",
        len(INVOKE.findall("true && .ci/scripts/a.sh | scripts/b.py")) == 2,
    )
    check(
        "CONTROL: a MENTION inside an echo is not an invocation",
        not INVOKE.findall('echo "see .ci/scripts/ci/shadow-compare.sh for details"'),
    )
    return bad


def main() -> int:
    print("checkout cone: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2
    probs, njobs = findings()
    if njobs < MIN_JOBS:
        print(
            "VACUOUS INPUT: %d job(s) parsed, floor %d. The enumeration lost the corpus."
            % (njobs, MIN_JOBS),
            file=sys.stderr,
        )
        return 1
    if probs:
        print("✗ checkout cone (%d finding(s)):" % len(probs), file=sys.stderr)
        for p in probs:
            print("    %s" % p, file=sys.stderr)
        print("  Fix: add the path's top directory to that job's sparse-checkout.", file=sys.stderr)
        return 1
    print("✓ checkout cone: %d job(s); every script a step runs is inside its own checkout" % njobs)
    print("  Blind spot: only paths that look like an INVOCATION are resolved -- a script")
    print("  reached through a variable or a wrapper is not seen. Under-reporting is the")
    print("  safe direction: a miss fails loudly in CI, a false positive blocks a good job.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
