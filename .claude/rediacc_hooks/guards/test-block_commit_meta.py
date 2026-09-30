#!/usr/bin/env python3
"""Written-message control harness for block_commit_meta (#c56b63bd).

The guard's differential golden covers its ordinary verdicts; this suite covers one shape the golden cannot hold, because it needs files on disk and a mutant: a `git commit -F <file>` whose file an earlier clause of the SAME command writes. The guard runs once, before that clause, so the bytes on disk are an earlier command's. Before #c56b63bd the guard skipped such a file and judged only a footer spelled out in the command itself, so a trailer that reached the file any other way (a `%s` argument, a `tee` from another file, a heredoc expanding a variable) was committed unjudged.

Each fire case writes a trailer into a stale CLEAN file and must be REFUSED naming the write (`commit_policy.written_message_refusal`). THE MUTANT answers `written_message_files` with [] everywhere and must flip every fire case to allowed; the CONTROLs (an unwritten `-F` file read both ways, and a `gh pr create --body-file` the helper does not govern) must not move.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, and the mutant through the same guard source with `.claude` on `PYTHONPATH`, so no hand-written path hop is needed.
"""

import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CLAUDE_DIR = HERE.parents[1]
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_commit_meta"
GUARD = HERE / ("%s.py" % STEM)

# Assembled, so no source line here is itself a trailer or a footer.
TRAILER = "Co-" + "Authored-By: Bot <bot@example.invalid>"
COMMIT = "git " + "commit"

WORK = pathlib.Path(tempfile.mkdtemp(prefix="commit-meta-written-"))
atexit.register(shutil.rmtree, WORK, ignore_errors=True)
(WORK / "clean.txt").write_text("fix: x\n", encoding="utf-8")
(WORK / "trailer.txt").write_text("fix: x\n\n%s\n" % TRAILER, encoding="utf-8")
(WORK / "src.txt").write_text("fix: x\n\n%s\n" % TRAILER, encoding="utf-8")

NEEDLE = "nothing in this command ran, including"
REFUSED = "Do not add Co-Authored-By"

# (name, command, expect_blocked, stderr needle)
CASES = [
    (
        "printf spells the trailer through a %s argument",
        "printf 'fix: x\\n\\n%%s-Authored-By: b <b@c>\\n' Co > clean.txt && %s -F clean.txt -- a"
        % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "tee copies a trailer from another file, read by --file=",
        "cat src.txt | tee clean.txt && %s --file=clean.txt -- a" % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "a heredoc expands a variable into the trailer",
        "P=Co-; cat > clean.txt <<EOF\nfix: x\n\n${P}Authored-By: b <b@c>\nEOF\n%s -F clean.txt -- a"
        % COMMIT,
        True,
        NEEDLE,
    ),
    (
        "the redirect by absolute path, the -F relative",
        "cat src.txt > %s/clean.txt; %s -F clean.txt -- a" % (WORK, COMMIT),
        True,
        NEEDLE,
    ),
    ("CONTROL: an unwritten clean -F file is read", "%s -F clean.txt -- a" % COMMIT, False, ""),
    (
        "CONTROL: another file written, the unwritten -F file still read",
        "printf x > other.txt && %s -F trailer.txt -- a" % COMMIT,
        True,
        REFUSED,
    ),
    (
        "CONTROL: a gh body file this command writes is not a commit",
        "printf 'prose\\n' > body.md; gh pr create --title t --body-file body.md",
        False,
        "",
    ),
]

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


def run(command, mutant=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(WORK))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if mutant:
        argv = [sys.executable, "-c", MUTANT_RUNNER % (str(GUARD), str(GUARD))]
        env["PYTHONPATH"] = str(CLAUDE_DIR)
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(WORK)
    )
    if mutant and proc.returncode not in (0, 2):
        raise SystemExit("mutant runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, want, needle in CASES:
    got, err = run(command)
    mut, _ = run(command, mutant=True)
    blocked += got
    control = name.startswith("CONTROL")
    ok = got == want and needle in err and (mut == got if control else mut != got)
    fails += not ok
    print(
        "%-66s want=%-8s got=%-8s mutant=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "BLOCKED" if mut else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case", file=sys.stderr)
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
