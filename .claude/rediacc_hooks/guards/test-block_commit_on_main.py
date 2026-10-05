#!/usr/bin/env python3
"""Control harness for block_commit_on_main (OWN_SUITE: never bash, so no golden).

REAL REPOSITORIES under a `rediacc_ci.runtmp` run directory: a checkout on `main`, a feature checkout on `0923-1`, a console on `0923-1` holding a nested repository on `main` at `private/account` (the `git -C private/account commit` case), and a repository on `main` outside every console (the `/tmp` exemption). Each case drives the live guard through the dispatcher.

THE DEFECT CONTROL plants the guard's own declared `DEFECT` in a copy and requires at least one fire case to flip to allowed. The CONFIG CONTROL holds `.ci/config/commit-policy.json` and `commit_policy.DEFAULTS` to one set of values, the promise `commit_policy`'s docstring makes: a guard that fell back to defaults must not quietly enforce a different policy from the file.
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
STEM = "block_commit_on_main"
GUARD = HERE / ("%s.py" % STEM)
REPO = HERE.parents[2]

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", REPO / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-commit-main-")

# `commit_message_text` imports `rediacc_hooks.shellscan` inside the function, so the package root has to be importable: the canonical hop, through rediacc_hooks/syspath.py loaded by file.
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
_syspath.on_sys_path(str(HERE.parents[1]))
_POLICY = importlib.util.spec_from_file_location("commit_policy", HERE.parent / "commit_policy.py")
if _POLICY is None or _POLICY.loader is None:
    raise SystemExit("%s: commit_policy.py is missing" % __file__)
commit_policy = importlib.util.module_from_spec(_POLICY)
_POLICY.loader.exec_module(commit_policy)

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, env=GIT_ENV)


def make_repo(branch, at=None):
    path = pathlib.Path(at) if at else pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "--initial-branch=main")
    git(path, "commit", "-q", "--allow-empty", "-m", "seed")
    if branch != "main":
        git(path, "checkout", "-q", "-b", branch)
    return path


MAIN = make_repo("main")
FEATURE = make_repo("0923-1")
CONSOLE = make_repo("0923-1")
make_repo("main", at=CONSOLE / "private" / "account")
OUTSIDE = make_repo("main")

EVIDENCE = "\n\nHotfix-Evidence: 18012345678"
HOTFIX = 'git commit -m "fix(ci): x [hotfix]%s" -- a.ts' % EVIDENCE

CASES = [
    # (name, command, root, expect_blocked) ---- fire -----------------------------------------
    ("on main, no [hotfix]", 'git commit -m "feat: x" -- a.ts', MAIN, True),
    (
        "a [hotfix] with 6 files",
        'git commit -m "fix: x [hotfix]%s" -- a b c d e f' % EVIDENCE,
        MAIN,
        True,
    ),
    ("a [hotfix] with no Hotfix-Evidence", 'git commit -m "fix: x [hotfix]" -- a.ts', MAIN, True),
    ("a [hotfix] on a feature branch", HOTFIX, FEATURE, True),
    (
        "a submodule on its own main",
        'git -C private/account commit -m "feat: x" -- a.ts',
        CONSOLE,
        True,
    ),
    ("a heredoc message on main", "git commit -F - -- a <<'EOF'\nfeat: x\nEOF", MAIN, True),
    ("an unreadable message on main", "cat m | git commit -F - -- a", MAIN, True),
    ("a wrapper on main", "sh -c 'git commit -m \"feat: x\" -- a'", MAIN, True),
    # A `cd` bash cannot perform leaves git in this checkout, so the commit lands on main (#5810a9f3 class sweep: run_repo answered "" and the guard skipped it).
    (
        "a failed cd still commits on main",
        'cd /nonexistent-zz9; git commit -m "feat: x" -- a.ts',
        MAIN,
        True,
    ),
    # #64c3e990: only the heredoc feeding the commit's own stdin is its message.
    (
        "a hotfix-shaped python heredoc before a plain commit",
        "python3 - <<'EOF'\nfix: x [hotfix]%s\nEOF\ngit commit -F - -- a <<'EOF'\nfeat: x\nEOF"
        % EVIDENCE,
        MAIN,
        True,
    ),
    # ---- inverse -----------------------------------------------------------------------------
    ("the same commit on a feature branch", 'git commit -m "feat: x" -- a.ts', FEATURE, False),
    ("a valid hotfix", HOTFIX, MAIN, False),
    (
        "a valid -F - hotfix after an unrelated python heredoc",
        "python3 - <<'EOF'\nfeat: y\nEOF\ngit commit -F - -- a <<'EOF'\nfix: x [hotfix]%s\nEOF"
        % EVIDENCE,
        MAIN,
        False,
    ),
    (
        "a valid hotfix piped from a cat heredoc",
        "cat <<'EOF' | git commit -F - -- a\nfix: x [hotfix]%s\nEOF" % EVIDENCE,
        MAIN,
        False,
    ),
    (
        "a valid hotfix with ASKED evidence",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: ASKED:2026-09-25T10:00Z" -- a',
        MAIN,
        False,
    ),
    (
        "a repository outside the checkout",
        'git -C %s commit -m "feat: x" -- a' % OUTSIDE,
        FEATURE,
        False,
    ),
    ("prose about committing on main", "echo 'git commit on main'", MAIN, False),
    ("git log", "git log -n 3", MAIN, False),
    ("an empty command", "", MAIN, False),
]

# #9888de00: a `-F <file>` that an earlier clause of the SAME command writes. The guard runs once, before that clause, so the file on disk is an earlier command's: a stale well-formed hotfix used to admit a plain commit onto `main`. Each fire case is REFUSED naming the write (`commit_policy.written_message_refusal`); each stale file is shaped so a guard that reads it anyway ALLOWS, which the MUTANT control below proves. The CONTROLs keep a `-F` file nothing in the command writes READ and judged. (name, command, root, expect_blocked, stderr needle)
(MAIN / "hf.txt").write_text("fix(ci): x [hotfix]%s\n" % EVIDENCE, encoding="utf-8")
(MAIN / "plain.txt").write_text("feat: x\n", encoding="utf-8")
(FEATURE / "m").write_text("feat: x\n", encoding="utf-8")
WRITTEN_NEEDLE = "nothing in this command ran, including"
WRITTEN = [
    (
        "on main, a plain message over a stale hotfix file",
        "printf 'feat: x' > hf.txt && git commit -F hf.txt -- a",
        MAIN,
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "on main, written through tee",
        "printf 'feat: x' | tee hf.txt && git commit -F hf.txt -- a",
        MAIN,
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "on main, written by absolute path, read relative",
        "printf 'feat: x' > %s/hf.txt; git commit --file=hf.txt -- a" % MAIN,
        MAIN,
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "off main, printf 'x [hotfix]' > m && git commit -F m",
        "printf 'x [hotfix]' > m && git commit -F m",
        FEATURE,
        True,
        WRITTEN_NEEDLE,
    ),
    (
        "CONTROL: an unwritten -F hotfix file is read",
        "git commit -F hf.txt -- a",
        MAIN,
        False,
        "",
    ),
    (
        "CONTROL: another file written, the -F file still read",
        "printf 'x' > other.txt && git commit -F plain.txt -- a",
        MAIN,
        True,
        "it is not a `[hotfix]`",
    ),
]

# THE MUTANT bypasses the shared helper: `written_message_files` answers [] everywhere, so the guard reads the written file off disk again, as it did before #9888de00.
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
    " if not any(n.lineno <= i <= n.end_lineno for n in cut))\n"
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


def run(command, root, broken=False, mutant=False, agent=None, defect=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    doc = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent:
        doc.update(agent_id="a0123456789abcdef", agent_type=agent)
    payload = json.dumps(doc)
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), defect or DEFECT, str(GUARD))
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
for name, command, root, want in CASES:
    got, err = run(command, root)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-44s want=%-8s got=%-8s %s"
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
flipped = [n for n, c, r, want in CASES if want and not run(c, r, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped, e.g. %r"
        % (DEFECT[0], len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every fire case still refused" % (DEFECT,))
    fails += 1

print()
for name, command, root, want, needle in WRITTEN:
    got, err = run(command, root)
    mut, _ = run(command, root, mutant=True)
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

# WRITERS NEVER COMMIT (section 3.2): the same commands with a sub-agent payload. `agent_id` and `agent_type` arrive only on a sub-agent's call, so the main-loop CASES above are the inverse of every fire case here. (name, command, root, agent_type, expect_blocked)
AGENT_NEEDLE = "writers never commit"
AGENT_CASES = [
    (
        "a writer commits on the feature branch",
        'git commit -m "feat: x" -- a.ts',
        FEATURE,
        "general-purpose",
        True,
    ),
    ("a writer commits a valid hotfix on main", HOTFIX, MAIN, "sonnet-writer", True),
    ("a fork commits", 'git commit -m "feat: x" -- a.ts', FEATURE, "fork", True),
    (
        "a writer commits through a wrapper",
        "sh -c 'git commit -m \"feat: x\" -- a'",
        FEATURE,
        "general-purpose",
        True,
    ),
    (
        "the pr-babysitter loop commits (no exemption, operator 2026-10-04)",
        'git commit -m "feat: x" -- a.ts',
        FEATURE,
        "pr-babysitter",
        True,
    ),
    ("a writer reads the log", "git log -n 3", FEATURE, "general-purpose", False),
    (
        "a writer commits outside the checkout",
        'git -C %s commit -m "feat: x" -- a' % OUTSIDE,
        FEATURE,
        "general-purpose",
        False,
    ),
]
# The planted defect removes the arm; every fire case on the feature branch must then flip to allowed.
AGENT_DEFECT = ('if ev.field("agent_id"):', "if False:")
print()
for name, command, root, agent, want in AGENT_CASES:
    got, err = run(command, root, agent=agent)
    ok = got == want and (AGENT_NEEDLE in err) == want
    fails += not ok
    print(
        "%-56s want=%-8s got=%-8s %s"
        % (
            "agent: " + name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])
agent_flipped = [
    n
    for n, c, r, a, want in AGENT_CASES
    if want and r == FEATURE and not run(c, r, broken=True, agent=a, defect=AGENT_DEFECT)[0]
]
agent_fire = [n for n, c, r, a, want in AGENT_CASES if want and r == FEATURE]
if agent_flipped != agent_fire:
    print(
        "*** FAIL *** agent DEFECT control: with %r planted, only %r flipped"
        % (AGENT_DEFECT, agent_flipped)
    )
    fails += 1
else:
    print(
        "agent DEFECT control: planted %r; %d fire case(s) flipped"
        % (AGENT_DEFECT[0], len(agent_flipped))
    )

# commit_message_text, driven directly (#64c3e990): a heredoc is a commit's message only when it feeds THAT commit's stdin -- attached to it, or on a `cat` piped into it -- and the commit reads stdin. Before the fix every heredoc in the command was read as the message, so a `python3 - <<EOF` edit chained first became part of it.
(MAIN / "msgfile").write_text("feat: from the file\n", encoding="utf-8")
MESSAGE_CASES = [
    (
        "a python heredoc chained before -F - yields only the commit's own body",
        "python3 - <<'EOF'\nprint('PR-TASK: deadbeef')\nEOF\ngit commit -F - -- a <<'EOF'\nfeat: x\nEOF",
        "feat: x",
    ),
    (
        "a cat heredoc piped into -F - is the message",
        "cat <<'EOF' | git commit -F -\nfeat: y\nEOF",
        "feat: y",
    ),
    (
        "-F <file> with an unrelated heredoc earlier yields the file",
        "cat > other.md <<'EOF'\nnot the message\nEOF\ngit commit -F msgfile -- a",
        "feat: from the file",
    ),
    (
        "-F /dev/stdin is stdin, never the hook's own",
        "git commit -F /dev/stdin <<'EOF'\nfeat: d\nEOF",
        "feat: d",
    ),
    ("a here-string on -F -", "git commit -F - <<< 'feat: hs'", "feat: hs"),
    (
        "-F <file> ignores its own stray heredoc",
        "git commit -F msgfile <<'EOF'\nnoise\nEOF",
        "feat: from the file",
    ),
    (
        "CONTROL: the plain -F - heredoc shape",
        "git commit -F - -- a <<'EOF'\nfeat: x\nEOF",
        "feat: x",
    ),
    ("CONTROL: a piped stdin stays opaque", "printf 'feat: p' | git commit -F -", ""),
    # #9888de00: the bytes on disk are an earlier command's, so the file is never read.
    (
        "-F <file> this same command writes first is not read",
        "printf 'feat: new' > msgfile && git commit -F msgfile -- a",
        "",
    ),
    (
        "CONTROL: -F <file> after a write to another file is read",
        "printf 'x' > other.md && git commit -F msgfile -- a",
        "feat: from the file",
    ),
]
for name, command, expect in MESSAGE_CASES:
    text = commit_policy.commit_message_text(command, str(MAIN))
    ok = text == expect
    fails += not ok
    print(
        "%-72s %s"
        % ("message: " + name, "ok" if ok else "*** FAIL *** got %r want %r" % (text, expect))
    )
TWO = "git commit -F - <<'A'\none\nA\ngit commit -F - <<'B'\ntwo\nB"
per_run = [
    commit_policy.commit_message_text(TWO, str(MAIN), run=r)
    for r in commit_policy.git_runs(TWO, "commit")
]
if per_run != ["one", "two"]:
    print("*** FAIL *** two commits in one command read %r, want ['one', 'two']" % per_run)
    fails += 1
else:
    print("%-72s ok" % "message: two -F - commits each read their own heredoc")

on_disk = commit_policy.load_config(REPO)
if on_disk != commit_policy.DEFAULTS:
    print("*** FAIL *** .ci/config/commit-policy.json and commit_policy.DEFAULTS disagree:")
    for key in sorted(commit_policy.DEFAULTS):
        if on_disk.get(key) != commit_policy.DEFAULTS[key]:
            print(
                "    %s: file %r, defaults %r"
                % (key, on_disk.get(key), commit_policy.DEFAULTS[key])
            )
    fails += 1
else:
    print(
        "config control: .ci/config/commit-policy.json == commit_policy.DEFAULTS (%d keys)"
        % len(on_disk)
    )
raw = json.loads((REPO / ".ci" / "config" / "commit-policy.json").read_text(encoding="utf-8"))
unread = sorted(k for k in raw if not k.startswith("$") and k not in commit_policy.DEFAULTS)
if unread:
    print("*** FAIL *** config keys nothing reads: %s" % unread)
    fails += 1

if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
