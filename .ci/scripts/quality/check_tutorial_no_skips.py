#!/usr/bin/env python3
"""No tutorial may opt itself out of the sequence.

WHY THIS EXISTS. The rclone retirement left tutorial-backup-restore.sh teaching
a command that now refuses, so a `# TUTORIAL_DRAFT:` marker was added and
run-sequence.sh learned to skip it. That was the wrong repair, and the operator
rejected it: a tutorial is executable documentation, and a skipped one is a
customer-facing page nothing verifies. The marker also had no expiry, so the
skip would have outlived its reason by default rather than by decision.

The right repair is to fix the tutorial. This gate makes the wrong one
impossible to reintroduce quietly.

WHAT IT FORBIDS: any self-exclusion marker in a tutorial script, and any skip
mechanism in the runner that reads one. `TUTORIAL_ONLY` is deliberately NOT
forbidden -- it is an operator-driven subset for local iteration, passed on the
command line, which cannot silently shrink a CI run.

WHAT IT CANNOT SEE. A tutorial that runs but asserts nothing. Coverage of that
belongs to the sequence runner's own exit codes, not here.
"""

import pathlib
import re
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
TUTORIALS = REPO / ".ci" / "tutorials"
RUNNER = TUTORIALS / "run-sequence.sh"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Self-exclusion markers. Named individually rather than by a loose "skip"
# substring, which matched ordinary prose in a tutorial's own comments.
BANNED = re.compile(
    r"^#\s*(TUTORIAL_DRAFT|TUTORIAL_SKIP|TUTORIAL_DISABLED|DRAFT)\s*:", re.MULTILINE
)


def audit(scripts, runner_text):
    findings = []
    for path in sorted(scripts):
        try:
            body = path.read_text(errors="replace")
        except OSError:
            continue
        m = BANNED.search(body)
        if m:
            findings.append(
                (
                    path.name,
                    f"carries a `{m.group(1)}` self-exclusion marker; fix the tutorial instead",
                )
            )
    if BANNED.pattern.split("(")[1].split(")")[0].split("|")[0] in runner_text:
        findings.append(
            ("run-sequence.sh", "still reads a draft marker; the runner must not be able to skip")
        )
    return findings


def run_controls():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        d = pathlib.Path(tmp)
        p = d / "tutorial-planted.sh"

        p.write_text("#!/bin/bash\n# TUTORIAL_DRAFT: cannot run right now\necho hi\n")
        if not audit([p], ""):
            failures.append("a TUTORIAL_DRAFT marker was not caught")

        p.write_text("#!/bin/bash\n# TUTORIAL_SKIP: later\necho hi\n")
        if not audit([p], ""):
            failures.append("a TUTORIAL_SKIP marker was not caught")

        p.write_text(
            "#!/bin/bash\n# this tutorial does not skip any steps\nrun_cmd 'rdc repo list'\n"
        )
        if audit([p], ""):
            failures.append("an ordinary tutorial mentioning the word skip was flagged")

        if not audit([], "if grep -q '^# TUTORIAL_DRAFT:' \"$f\"; then continue; fi"):
            failures.append("a runner that still honours draft markers was not caught")

        if audit([], 'TUTORIAL_ONLY="a b"'):
            failures.append("the operator-driven TUTORIAL_ONLY subset was wrongly forbidden")
    return failures


def main() -> int:
    print("Tutorials: can any of them opt out of the sequence?")
    print("=" * 51)

    control_failures = run_controls()
    if control_failures:
        for f in control_failures:
            print(f"{RED}x{NC} control: {f}")
        print(f"{RED}x{NC} the rule itself is broken, so no verdict it produces means anything.")
        return 1
    print(
        f"{GREEN}v{NC} control fired: markers and a skipping runner are caught, ordinary text is not"
    )

    scripts = list(TUTORIALS.glob("tutorial-*.sh"))
    if not scripts:
        print(
            f"{RED}x{NC} no tutorial scripts found; checking nothing exits 0 exactly like checking everything"
        )
        return 1

    findings = audit(scripts, RUNNER.read_text(errors="replace") if RUNNER.is_file() else "")
    if findings:
        for name, why in findings:
            print(f"{RED}x{NC} {name}: {why}")
        print()
        print(f"{RED}x{NC} {len(findings)} tutorial(s) can be skipped.")
        print("  A tutorial is executable documentation: a skipped one is a customer-facing page")
        print("  that nothing verifies. Fix the tutorial rather than excusing it from the run.")
        return 1

    print(f"{GREEN}v{NC} all {len(scripts)} tutorial(s) run; none can exclude itself")
    return 0


if __name__ == "__main__":
    sys.exit(main())
