#!/usr/bin/env python3
"""Control harness for block_prose_style_commit.

BOTH DIRECTIONS, and here the ALLOW side carries most of the weight. A guard that refused every commit message would pass every block case in this file and would be uninstalled the same day; the cases that must pass -- a Conventional-Commits imperative subject, a backticked identifier, `git log --grep` -- are what make the block cases mean anything.

WHY THIS FILE IS LOAD-BEARING. The guard declares `TWIN = None`, so the
differential has no bash oracle for it, and `test_guards_differential.py` now requires a `test-<stem>.py` beside any guard carrying that sentinel. This is that file. `check-hook-integrity.sh` reads its existence as well, crediting the guard
with both directions under section B.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that runs goes unchecked.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_prose_style_commit"]

# Assembled rather than written, so this harness is not a finding in the corpus of the CI gate that reads its comments.
Y = "y" + "ou"
EYE = "I"
COMMIT = "git " + "commit"

# A REAL file on disk, for the `-F body=@<file>` case: `_read_file` genuinely
# reads it, so the case proves the whole path, not just the inline-value arm.
with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as _body_file:
    _body_file.write("Did %s run the tests?" % Y)
BODY_FILE_PATH = _body_file.name

# R18 is a FLOOR since the 2026-09-22 rewrite (prose_style.py:_sentence_break_offset): a line past 384 chars is only a finding when a genuine sentence-ending period sat at or before that floor. A run of one repeated character has no such break and is legal at any length, so a case meant to exercise R18 needs an early period followed by a long tail.
R18_VIOLATION = "This starts with one short sentence. " + ("word " * 100)

# R19 fires on a paragraph of 3+ lines hard-wrapped at a uniform width well under the limit -- the shape a heredoc body typed with manual line breaks produces. Since 2026-09-22 this also covers "commit" scope, matching R18: the same duplicated hardcoded scope check (prose_style.py's `underwrap_findings`) that would have left R18's fix vacuous for commit bodies if left
# unfixed applies here too, so this case is the class-sweep proof that R19 was fixed alongside it, not left as the other half of the same gap.
R19_VIOLATION = "This is a line that is deliberately\nkept narrow so that joining works\nas the paragraph intent shows here."

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
        "the SANCTIONED gh api PATCH form for a PR body, inline",
        'gh api repos/o/r/pulls/589 -X PATCH -F body="Did %s run the tests?"' % Y,
        True,
    ),
    (
        "the SANCTIONED gh api PATCH form for a PR body, from a file",
        "gh api repos/o/r/pulls/589 -X PATCH -F body=@%s" % BODY_FILE_PATH,
        True,
    ),
    (
        "the SANCTIONED gh api PATCH form, flags in the OTHER order",
        'gh api -X PATCH repos/o/r/pulls/589 -F body="Did %s run the tests?"' % Y,
        True,
    ),
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
        % (COMMIT, R18_VIOLATION),
        True,
    ),
    (
        "a long commit body gets R18 too, since 2026-09-22, even chained after a short PR body",
        '%s -m "fix: x" -m "%s" && gh pr create --title "fix: x" --body "short body"'
        % (COMMIT, R18_VIOLATION),
        True,
    ),
    (
        "a heredoc commit body gets R19 too, since 2026-09-22, same as a PR body",
        "%s -F - <<'EOF'\nfix: the thing\n\n%s\nEOF" % (COMMIT, R19_VIOLATION),
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
    (
        "gh api on pulls/<n> with GET is not a write",
        'gh api repos/o/r/pulls/589 -X GET -F body="Did %s run it?"' % Y,
        False,
    ),
    (
        "gh api PATCH on a non-pulls endpoint is not this guard's business",
        'gh api repos/o/r/issues/589 -X PATCH -F body="Did %s run it?"' % Y,
        False,
    ),
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
        "CONTROL: a commit body with no sentence break stays allowed past 384 chars, same as a PR body",
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
