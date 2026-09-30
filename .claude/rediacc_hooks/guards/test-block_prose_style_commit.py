#!/usr/bin/env python3
"""Control harness for block_prose_style_commit.

BOTH DIRECTIONS, and here the ALLOW side carries most of the weight. A guard that refused every commit message would pass every block case in this file and would be uninstalled the same day; the cases that must pass -- a Conventional-Commits imperative subject, a backticked identifier, `git log --grep` -- are what make the block cases mean anything.

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True`, so it has
no golden either, and `test_guards_differential.py` requires a `test-<stem>.py` beside any guard carrying that sentinel. This is that file. `check-hook-integrity.sh` reads its existence as well, crediting the guard
with both directions under section B.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that runs goes unchecked.
"""

import atexit
import json
import os
import pathlib
import shutil
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
# `delete=False` is what lets the guard reopen the file by name, so removing it is this suite's job, done at exit rather than never.
atexit.register(pathlib.Path(BODY_FILE_PATH).unlink, missing_ok=True)

# R18 is a FLOOR since the 2026-09-22 rewrite (prose_style.py:_sentence_break_offset): a line past the floor is only a finding when a genuine sentence-ending period sat at or before that floor. A run of one repeated character has no such break and is legal at any length, so a case meant to exercise R18 needs an early period followed by a long tail.
#
# THE FLOOR DOUBLED FROM 384 TO 768 the same day (commit 5c879581e, prose-style-rules.json's `max_line_length`), and that commit's own fixture sweep touched three cases in .ci/rediacc_ci/tests/test_quality_prose_style.py but not this file's -- this fixture sat at 537 characters, comfortably past the old floor and comfortably under the new one, so R18 silently stopped firing on
# it. 150 repeats clears 768 with margin rather than sitting flush against it, so a future floor nudge in either direction has room before this needs touching again.
R18_VIOLATION = "This starts with one short sentence. " + ("word " * 150)

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
        "CONTROL: a commit body with no sentence break stays allowed past the floor, same as a PR body",
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
    # `-F $VAR/...` with the variable assigned EARLIER IN THE SAME COMMAND (#09fd19cd). Before the fix the path was read literally, the message came back empty, and the violation in the file went unseen; BLOCKED here proves the file was read.
    (
        "-F through a same-command $VAR reads the file",
        "D=%s; %s -F $D/%s -- README.md"
        % (pathlib.Path(BODY_FILE_PATH).parent, COMMIT, pathlib.Path(BODY_FILE_PATH).name),
        True,
    ),
    (
        "--file=${VAR}/... reads the file too",
        "D=%s; %s --file=${D}/%s"
        % (pathlib.Path(BODY_FILE_PATH).parent, COMMIT, pathlib.Path(BODY_FILE_PATH).name),
        True,
    ),
    # A message file the SAME command writes before the verb (#9ec22810). The guard runs before the command, so the file still holds an EARLIER command's bytes -- here, the planted violation. #9ec22810 stopped judging those bytes and passed the commit unexamined; since #c56b63bd it is REFUSED unread, naming the write (the WRITTEN cases below pin the message and the mutant).
    (
        "a -F file this command writes first is refused, not judged on its old bytes",
        "D=%s; printf 'fix: the thing\\n' > $D/%s; %s -F $D/%s"
        % (
            pathlib.Path(BODY_FILE_PATH).parent,
            pathlib.Path(BODY_FILE_PATH).name,
            COMMIT,
            pathlib.Path(BODY_FILE_PATH).name,
        ),
        True,
    ),
    (
        "the same with a literal path and a heredoc cat",
        "cat > %s <<'EOF'\nfix: the thing\nEOF\n%s -F %s"
        % (BODY_FILE_PATH, COMMIT, BODY_FILE_PATH),
        True,
    ),
    (
        "INVERSE: a write to a DIFFERENT file leaves the -F file judged",
        "printf x > %s.other; %s -F %s" % (BODY_FILE_PATH, COMMIT, BODY_FILE_PATH),
        True,
    ),
    (
        "-F through a variable never assigned stays unexamined (fails open)",
        "%s -F $NEVER_SET_HERE/%s" % (COMMIT, pathlib.Path(BODY_FILE_PATH).name),
        False,
    ),
    # A heredoc is the message only when it feeds THIS command's stdin (#91c4716c). On 2026-09-26 a `python3 - <<'EOF'` edit chained before a `-F msg` commit was refused for R19 on the Python source; each ALLOW case below has a BLOCKED twin carrying the same text through the stdin shape.
    (
        "a python3 heredoc chained before a -F <file> commit is not the message",
        "python3 - <<'EOF'\n%s\nEOF\n%s -F /nonexistent/msg -- p" % (R19_VIOLATION, COMMIT),
        False,
    ),
    (
        "the same python3 heredoc chained with && is not the message either",
        "python3 - <<'EOF' && %s -F /nonexistent/msg -- p\n%s\nEOF" % (COMMIT, R19_VIOLATION),
        False,
    ),
    (
        "a cat > file heredoc beside the commit is not the message",
        "cat > /tmp/notes.txt <<'EOF'\n%s think this is right.\nEOF\n%s -m 'fix: x' -- p"
        % (EYE, COMMIT),
        False,
    ),
    (
        "CONTROL: the same R19 text in the commit's own -F - heredoc is refused",
        "%s -F - <<'EOF'\nfix: the thing\n\n%s\nEOF" % (COMMIT, R19_VIOLATION),
        True,
    ),
    (
        "CONTROL: -F /dev/stdin fed by a heredoc is the message",
        "%s -F /dev/stdin -- p <<'EOF'\nfix: the thing\n\n%s think this is right.\nEOF"
        % (COMMIT, EYE),
        True,
    ),
    (
        "CONTROL: gh pr create --body-file - with a heredoc is still linted",
        "gh pr create --title 'fix: x' --body-file - <<EOF\n%s think this is right.\nEOF" % EYE,
        True,
    ),
    (
        "CONTROL: a cat heredoc piped into commit -F - is the message",
        "cat <<'EOF' | %s -F -\nfix: the thing\n\n%s think this is right.\nEOF" % (COMMIT, EYE),
        True,
    ),
    (
        "CONTROL: a -m $(cat <<EOF) body is still linted",
        "%s -m \"$(cat <<'EOF'\nfix: the thing\n\n%s think this is right.\nEOF\n)\" -- p"
        % (COMMIT, EYE),
        True,
    ),
    # The -m / -F flag arms are scoped the same way: another command's flags are not the commit's.
    (
        "a grep -m chained beside a commit is not a message",
        "grep -m 1 '%s think' README.md; %s -m 'fix: x' -- p" % (EYE, COMMIT),
        False,
    ),
    (
        "a tail -F on a file carrying a violation is not a message",
        "tail -F %s & %s -m 'fix: x' -- p" % (BODY_FILE_PATH, COMMIT),
        False,
    ),
    (
        "CONTROL: the commit's own -F on that same file still reads it",
        "tail -n1 README.md; %s -F %s -- p" % (COMMIT, BODY_FILE_PATH),
        True,
    ),
]


# #c56b63bd: a `-F <file>` that an earlier clause of the SAME command writes. The guard runs once, before that clause, so the file on disk is an earlier command's; the guard used to skip it and pass the commit unexamined. Each fire case is REFUSED naming the write (`commit_policy.written_message_refusal`), over a stale CLEAN file, so a guard that reads it anyway or skips it ALLOWS, which the MUTANT column proves. The CONTROLs keep a `-F` file nothing in the command writes READ and judged both ways. (name, command, expect_blocked, stderr needle)
WRITTEN_DIR = pathlib.Path(tempfile.mkdtemp(prefix="prose-written-"))
atexit.register(shutil.rmtree, WRITTEN_DIR, ignore_errors=True)
CLEAN_MSG = WRITTEN_DIR / "clean.txt"
CLEAN_MSG.write_text("fix: the thing\n", encoding="utf-8")
DIRTY_MSG = WRITTEN_DIR / "dirty.txt"
DIRTY_MSG.write_text("fix: the thing\n\n%s think this is right.\n" % EYE, encoding="utf-8")
WRITTEN_NEEDLE = "nothing in this command ran, including"
WRITTEN = [
    (
        "printf writes the violation into a stale clean file",
        "printf 'fix: x\\n\\n%s think this is right.\\n' > %s && %s -F %s -- p"
        % (EYE, CLEAN_MSG, COMMIT, CLEAN_MSG),
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "tee writes it, read by --file=",
        "printf 'Did %s run it?' | tee %s && %s --file=%s -- p" % (Y, CLEAN_MSG, COMMIT, CLEAN_MSG),
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "a cat heredoc writes it on the line before the commit",
        "cat > %s <<'EOF'\nfix: x\n\n%s think this is right.\nEOF\n%s -F %s -- p"
        % (CLEAN_MSG, EYE, COMMIT, CLEAN_MSG),
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "CONTROL: an unwritten clean -F file is read",
        "%s -F %s -- p" % (COMMIT, CLEAN_MSG),
        False,
        "",
    ),
    (
        "CONTROL: another file written, the unwritten -F file still read",
        "printf 'x' > %s/other.txt && %s -F %s -- p" % (WRITTEN_DIR, COMMIT, DIRTY_MSG),
        True,
        "house writing style",
    ),
]

# THE MUTANT bypasses the shared helper: `written_message_files` answers [] everywhere, so the guard is back to skipping the written file, as it did before #c56b63bd. `PYTHONPATH` puts `.claude` on the path, so the runner needs no hand-written hop.
MUTANT_RUNNER = (
    "import sys\n"
    "from rediacc_hooks import commit_policy, hookio\n"
    "commit_policy.written_message_files = lambda *a, **k: []\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "ns = {'__name__': 'mutant', '__file__': %r}\n"
    "exec(compile(src, 'mutant', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)
GUARD_PATH = str(pathlib.Path(DISPATCH).parent / "guards" / "block_prose_style_commit.py")


def run(command, mutant=False):
    argv = GUARD_ARGV
    env = None
    if mutant:
        argv = [sys.executable, "-c", MUTANT_RUNNER % (GUARD_PATH, GUARD_PATH)]
        env = dict(os.environ, PYTHONPATH=str(pathlib.Path(DISPATCH).parents[1]))
    proc = subprocess.run(
        argv,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if mutant and proc.returncode not in (0, 2):
        raise SystemExit("mutant runner crashed: %s" % proc.stderr[-800:])
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
for name, command, want, needle in WRITTEN:
    got, err = run(command)
    mut, _ = run(command, mutant=True)
    # A fire case must flip under the mutant (the stale file is clean, or skipped); a CONTROL must not move.
    control = name.startswith("CONTROL")
    ok = got == want and needle in err and (mut == got if control else mut != got)
    fails += not ok
    print(
        "%-62s want=%-9s got=%-9s mutant=%-9s %s"
        % (
            "written: " + name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "BLOCKED" if mut else "allowed",
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
