#!/usr/bin/env python3
"""Control harness for block_no_review_ineligible (OWN_SUITE: never bash, so no golden).

`[no-review]` must be refused on a code path, on an agent program under `.claude/`, on CLAUDE.md and on any `[hotfix]`, and allowed on writing (`agent/**`, `docs/**`); an untagged code commit is none of the guard's business. A directory pathspec is expanded to the files git knows under it, so `notes/` with a stray `.ts` beside its markdown is refused too. Each case drives the live guard through the dispatcher against a real repository under a `rediacc_ci.runtmp` run directory.

THE DEFECT CONTROL plants the guard's declared `DEFECT` (eligibility forced true) in a copy and requires at least one fire case to flip to allowed.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_no_review_ineligible"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-no-review-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def make_repo(branch):
    path = pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["checkout", "-q", "-B", branch],
    ):
        subprocess.run(["git", *argv], cwd=str(path), check=True, capture_output=True, env=GIT_ENV)
    return path


REPO = make_repo("0923-1")
OUTSIDE = make_repo("0923-1")
for rel in ("agent/plans/x.md", "docs/y.md", "notes/tool.ts", "notes/z.md"):
    (REPO / rel).parent.mkdir(parents=True, exist_ok=True)
    (REPO / rel).write_text("x\n", encoding="utf-8")

CASES = [
    # (name, command, expect_blocked) ---- fire ----------------------------------------------
    ("a code path", 'git commit -m "feat: x [no-review]" -- src/a.ts', True),
    ("an agent program", 'git commit -m "docs: x [no-review]" -- .claude/commands/x.md', True),
    ("CLAUDE.md is policy", 'git commit -m "docs: x [no-review]" -- CLAUDE.md', True),
    (
        "a hotfix is always reviewed",
        'git commit -m "docs: x [hotfix] [no-review]\n\nHotfix-Evidence: 123456789" -- docs/y.md',
        True,
    ),
    ("a directory hiding code", 'git commit -m "docs: x [no-review]" -- notes/', True),
    ("writing mixed with code", 'git commit -m "docs: x [no-review]" -- docs/y.md a.py', True),
    ("a heredoc message", "git commit -F - -- a.ts <<'EOF'\nfeat: x [no-review]\nEOF", True),
    # ---- inverse -----------------------------------------------------------------------------
    ("writing only", 'git commit -m "docs: x [no-review]" -- agent/plans/x.md docs/y.md', False),
    ("a markdown file outside .claude", 'git commit -m "docs: x [no-review]" -- notes/z.md', False),
    ("an untagged code commit", 'git commit -m "feat: x" -- src/a.ts', False),
    (
        "a repository outside the checkout",
        'git -C %s commit -m "x [no-review]" -- a.ts' % OUTSIDE,
        False,
    ),
    ("prose naming the tag", "echo 'tag it [no-review]'", False),
    ("an empty command", "", False),
]

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "assert old in src, 'DEFECT no longer applies'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared_defect():
    namespace: dict[str, object] = {}
    source = GUARD.read_text(encoding="utf-8")
    start = source.index("DEFECT = ")
    end = source.index(")\n", start) + 1
    exec(source[start:end], namespace)  # noqa: S102 -- the guard's own literal
    return namespace["DEFECT"]


DEFECT = _declared_defect()


def run(command, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(REPO)
    )
    if broken and proc.returncode not in (0, 2):
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
        "%-40s want=%-8s got=%-8s %s"
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
flipped = [n for n, c, want in CASES if want and not run(c, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped, e.g. %r"
        % (DEFECT[0], len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every fire case still refused" % (DEFECT,))
    fails += 1
if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
