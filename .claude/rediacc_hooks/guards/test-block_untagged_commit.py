#!/usr/bin/env python3
"""Control harness for block_untagged_commit's message scoping (#64c3e990).

The guard's EDGE_CASES golden covers its trailer rules; this file covers WHICH TEXT is the message. A heredoc is a commit's message only when it feeds that commit's stdin (attached, or on a `cat` piped into it) and the commit reads `-F -`; a `python3 - <<'EOF'` chained before the commit is not. Each case drives the live guard through the dispatcher against a real repository whose `agent/pr/<branch>.md` declares one epic, under a `rediacc_ci.runtmp` run directory.

THE DEFECT CONTROL plants the guard's own declared `DEFECT` in a copy and requires at least one fire case to flip to allowed.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_untagged_commit"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-untagged-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

REPO = pathlib.Path(RUN_TMP) / "repo"
REPO.mkdir(parents=True)
for argv in (["init", "-q", "--initial-branch=0831-1"],):
    subprocess.run(["git", *argv], cwd=str(REPO), check=True, capture_output=True, env=GIT_ENV)
(REPO / "agent" / "pr").mkdir(parents=True)
(REPO / "agent" / "pr" / "0831-1.md").write_text(
    "### Port the guards\n\n`PR-TASK: a1b2c3d4`\n", encoding="utf-8"
)
(REPO / "good.txt").write_text("feat: x\n\nPR-TASK: a1b2c3d4\n", encoding="utf-8")
for argv in (["add", "-A"], ["commit", "-q", "-m", "seed"]):
    subprocess.run(["git", *argv], cwd=str(REPO), check=True, capture_output=True, env=GIT_ENV)

# A python heredoc whose body carries a trailer-shaped line of its own.
PY = "python3 - <<'EOF'\ndoc = '''\nPR-TASK: %s\n'''\nEOF\n"

CASES = [
    # (name, command, expect_blocked) ---- fire ----------------------------------------------
    (
        "a trailer only in a python heredoc chained before the commit",
        PY % "a1b2c3d4" + "git commit -F - -- a <<'EOF'\nfeat: x\nEOF",
        True,
    ),
    ("a -F - heredoc with no trailer", "git commit -F - -- a <<'EOF'\nfeat: x\nEOF", True),
    (
        "a cat heredoc piped into -F - with no trailer",
        "cat <<'EOF' | git commit -F -\nfeat: x\nEOF",
        True,
    ),
    # ---- inverse -----------------------------------------------------------------------------
    (
        "the commit's own trailer, a python heredoc naming no epic before it",
        PY % "deadbeef" + "git commit -F - -- a <<'EOF'\nfeat: x\n\nPR-TASK: a1b2c3d4\nEOF",
        False,
    ),
    (
        "a -m trailer, a python heredoc naming no epic before it",
        PY % "deadbeef" + 'git commit -m "feat: x\n\nPR-TASK: a1b2c3d4" -- a',
        False,
    ),
    (
        "a cat heredoc piped into -F - with the trailer",
        "cat <<'EOF' | git commit -F -\nfeat: x\n\nPR-TASK: a1b2c3d4\nEOF",
        False,
    ),
    (
        "-F <file> with a heredoc naming no epic earlier",
        "cat > n.md <<'EOF'\nPR-TASK: deadbeef\nEOF\ngit commit -F good.txt -- a",
        False,
    ),
    (
        "CONTROL: the plain -F - heredoc shape",
        "git commit -F - -- a <<'EOF'\nfeat: x\n\nPR-TASK: a1b2c3d4\nEOF",
        False,
    ),
    (
        "CONTROL: a piped stdin stays opaque, so allowed",
        "printf 'feat: x' | git commit -F -",
        False,
    ),
]

# #9888de00: a `-F <file>` that an earlier clause of the SAME command writes. The guard runs once, before that clause, so the file on disk is an earlier command's. It used to be skipped as unreadable, which ALLOWED the commit unjudged; now it is REFUSED naming the write (`commit_policy.written_message_refusal`), the one behaviour of the four commit-message guards. Each stale file is shaped so a guard that reads it anyway ALLOWS, which the MUTANT control below proves. The CONTROLs keep a `-F` file nothing in the command writes READ and judged. (name, command, expect_blocked, stderr needle)
(REPO / "bad.txt").write_text("feat: x\n", encoding="utf-8")
WRITTEN_NEEDLE = "nothing in this command ran, including"
WRITTEN = [
    (
        "no trailer written over a stale tagged file",
        "printf 'feat: x' > good.txt && git commit -F good.txt -- a",
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "a trailer written by a cat heredoc, read by --file=",
        "cat > fresh.txt <<'EOF'\nfeat: x\n\nPR-TASK: a1b2c3d4\nEOF\ngit commit --file=fresh.txt -- a",
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "CONTROL: an unwritten tagged -F file is read",
        "git commit -F good.txt -- a",
        False,
        "",
    ),
    (
        "CONTROL: another file written, the -F file still read",
        "printf 'x' > other.txt && git commit -F bad.txt -- a",
        True,
        "carries no PR-TASK trailer",
    ),
]

# THE MUTANT bypasses the shared helper: `written_message_files` answers [] everywhere, so the guard reads the written file off disk again.
MUTANT_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
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

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'DEFECT no longer applies outside its own declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared_defect():
    namespace: dict[str, object] = {}
    for line in GUARD.read_text(encoding="utf-8").split("\n"):
        if line.startswith("DEFECT = "):
            exec(line, namespace)  # noqa: S102 -- the guard's own one-line literal
    return namespace["DEFECT"]


DEFECT = _declared_defect()


def run(command, broken=False, mutant=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO))
    # The guard takes its branch from PR_HEAD_REF / GITHUB_HEAD_REF before asking git, so in a PR run it judged the fixture as `0930-1` (no epic file) and the unknown-id probe could never block: green locally, red in CI (#591 run on e532e4ad5). The fixture's branch must come from the fixture. test_guard_chained_state.py scrubs the same names.
    for name in ("PR_HEAD_REF", "GITHUB_HEAD_REF", "GIT_INDEX_FILE", "GIT_DIR"):
        env.pop(name, None)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    elif mutant:
        code = MUTANT_RUNNER % (str(HERE.parents[1]), str(GUARD), str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True, check=False, env=env)
    if (broken or mutant) and proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, want in CASES:
    got, err = run(command)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-70s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:2])

print()
# The DEFECT disables id validation, so the fire cases that flip are the ones whose only fault is an unknown id; a missing trailer stays refused. Plant it on a case of that shape.
PROBE = "git commit -F - -- a <<'EOF'\nfeat: x\n\nPR-TASK: deadbeef\nEOF"
if run(PROBE)[0] and not run(PROBE, broken=True)[0]:
    print("DEFECT control: planted %r; the unknown-id probe flipped to allowed" % (DEFECT[0],))
else:
    print(
        "*** FAIL *** DEFECT control: with %r planted, the unknown-id probe did not flip"
        % (DEFECT,)
    )
    fails += 1

print()
for name, command, want, needle in WRITTEN:
    got, err = run(command)
    mut, _ = run(command, mutant=True)
    # A fire case must flip under the mutant (it reads the stale file, which passes); a CONTROL must not move.
    control = name.startswith("CONTROL")
    ok = got == want and needle in err and (mut == got if control else mut != got)
    fails += not ok
    print(
        "%-56s want=%-8s got=%-8s mutant=%-8s %s"
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
# NO SNAPSHOT: a branch with no agent/pr/<branch>.md is judged against agent/worklist/epics.jsonl, the ledger check:ci-pr-task-trailers reads. On 2026-10-03 the guard judged nothing there, and 41 commits on 1003-1 carrying a worklist item id passed until ci:quick refused them at push time. Runs last: it moves the fixture to a branch with no snapshot.
subprocess.run(
    ["git", "switch", "-q", "-c", "1003-1"],
    cwd=str(REPO),
    check=True,
    capture_output=True,
    env=GIT_ENV,
)
LEDGER_CASES = [
    ("no snapshot, no ledger: nothing to judge, allowed", "a1b2c3d4", False, False),
    ("no snapshot: an id the ledger lacks is refused", "deadbeef", True, True),
    ("CONTROL no snapshot: a ledger epic is allowed", "a1b2c3d4", True, False),
]
for name, epic, with_ledger, want in LEDGER_CASES:
    ledger = REPO / "agent" / "worklist" / "epics.jsonl"
    if with_ledger:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            '{"id":"a1b2c3d4","title":"Port the guards","covers":[]}\nnot json\n', encoding="utf-8"
        )
    got, err = run("git commit -F - -- a <<'EOF'\nfeat: x\n\nPR-TASK: %s\nEOF" % epic)
    ok = got == want
    fails += not ok
    print(
        "%-70s want=%-8s got=%-8s %s"
        % (
            "ledger: " + name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:2])
if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
