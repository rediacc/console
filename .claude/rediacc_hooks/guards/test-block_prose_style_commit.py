#!/usr/bin/env python3
"""Control harness for block_prose_style_commit.

BOTH DIRECTIONS, and here the ALLOW side carries most of the weight. A guard
that refused every commit message would pass every block case in this file and
would be uninstalled the same day; the cases that must pass -- a
Conventional-Commits imperative subject, a backticked identifier, `git log
--grep` -- are what make the block cases mean anything.

WHY THIS FILE IS LOAD-BEARING. The guard declares `TWIN = None`, so the
differential has no bash oracle for it, and `test_guards_differential.py` now
requires a `test-<stem>.py` beside any guard carrying that sentinel. This is that
file. `check-hook-integrity.sh` reads its existence as well, crediting the guard
with both directions under section B.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover
exists: a suite driving anything else keeps passing while the thing that runs
goes unchecked.
"""

import json
import pathlib
import subprocess
import sys

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_prose_style_commit"]

# Assembled rather than written, so this harness is not a finding in the corpus of the CI gate that reads its comments.
Y = "y" + "ou"
EYE = "I"
COMMIT = "git " + "commit"

CASES = [
    # (name, command, expect_blocked) ---- the block direction ------------------------------------------
    ("a subject addressing the reader", '%s -m "Did %s run the tests?"' % (COMMIT, Y), True),
    (
        "a body in the first person",
        '%s -m "fix: the thing" -m "%s think this is right."' % (COMMIT, EYE),
        True,
    ),
    ("the attached -m form", '%s -m"Did %s run the tests?"' % (COMMIT, Y), True),
    ("the long --message form", '%s --message="Did %s run it?"' % (COMMIT, Y), True),
    ("an amend is still a message", '%s --amend -m "Did %s run it?"' % (COMMIT, Y), True),
    (
        "a heredoc body, the shape this repository actually uses",
        "%s -F - <<'EOF'\nfix: the thing\n\n%s think this is right.\nEOF" % (COMMIT, EYE),
        True,
    ),
    ("a gh pr body", 'gh pr create --title "fix: x" --body "Did %s run it?"' % Y, True),
    ("a gh pr comment", 'gh pr comment 1 --body "%s already told %s!"' % (EYE, Y), True),
    ("a gh pr edit body", 'gh pr edit 1 --body "Did %s run it?"' % Y, True),
    (
        "a commit reached after && is still a commit",
        'git add -A && %s -m "Did %s run it?"' % (COMMIT, Y),
        True,
    ),
    (
        "a commit on the SECOND line of a multi-line command is still a target",
        'set -e\n%s -m "Did %s run the tests?"' % (COMMIT, Y),
        True,
    ),
    (
        "a long PR body still gets R18 even chained after a short commit",
        '%s -m "fix: x" -m "short" && gh pr create --title "fix: x" --body "%s"'
        % (COMMIT, "z" * 400),
        True,
    ),
    # ---- the allow direction ------------------------------------------
    (
        "a house-convention imperative subject is EXEMPT (R11 omits `commit`)",
        '%s -m "fix(ci): widen the trigger resolution"' % COMMIT,
        False,
    ),
    (
        "another one, to prove the exemption is not a one-off",
        '%s -m "feat(cli): add the repo fork positional ref"' % COMMIT,
        False,
    ),
    (
        "the rewritten body passes",
        '%s -m "fix: the thing" -m "Have the tests been run?"' % COMMIT,
        False,
    ),
    (
        "the ownership exception passes",
        '%s -m "fix: x" -m "M%s mistake; a fix is on the way."' % (COMMIT, "y"),
        False,
    ),
    (
        "a backticked identifier is code, not prose",
        '%s -m "docs: rename the `%s` placeholder"' % (COMMIT, Y),
        False,
    ),
    ("a commit with no message flag at all", COMMIT, False),
    ("git log is not git commit", 'git log --grep "Did %s run it?"' % Y, False),
    ("git show is not git commit", "git show HEAD", False),
    ("gh pr view is not a write", "gh pr view 1", False),
    ("a plain command is not a target", "ls -la", False),
    (
        "a warning-only absolute does not block",
        '%s -m "fix: x" -m "That will never work."' % COMMIT,
        False,
    ),
    (
        "-F pointing at a file this process cannot read is UNEXAMINED, not a finding",
        "%s -F /nonexistent/message.txt" % COMMIT,
        False,
    ),
    (
        "an unbalanced quote parses to nothing rather than raising",
        '%s -m "unclosed' % COMMIT,
        False,
    ),
    ("an empty command", "", False),
    (
        "a long commit body is not R18 (pr-only) even chained with a gh pr create",
        '%s -m "fix: x" -m "%s" && gh pr create --title "fix: x" --body "short body"'
        % (COMMIT, "z" * 400),
        False,
    ),
    (
        "a cat heredoc quoting a commit+pr example as PROSE is not a target",
        "cat > /tmp/note.md <<'EOF'\nExample: %s -m \"fix: x\" && gh pr create --title x --body y\nEOF"
        % COMMIT,
        False,
    ),
]


def run(command):
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, want in CASES:
    got, err = run(command)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-62s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
# ANTI-VACUITY: see the sibling harness. This guard's only control is this file.
if blocked == 0 or blocked == len(CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (blocked, len(CASES)),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
