#!/usr/bin/env python3
"""Control harness for block_lease_boundary and its git-level arms, driven through the dispatcher and through real `git` subprocesses.

    python3 .claude/rediacc_hooks/guards/test-block_lease_boundary.py                 rc 0
    python3 .claude/rediacc_hooks/guards/test-block_lease_boundary.py --plant-defect  rc 1: every row runs against a copy with the declared DEFECT

The fixture is the shape W0 decided: a console with a submodule, linked trees below `.claude/worktrees`, and each submodule tree linked from its module store. Nothing here touches the live checkout: every repository sits under the run directory, and the real hooks are reached through `core.hooksPath` in the fixture's own config.

`block_worktree_add` refuses this file while it is untracked or differs from HEAD, so it runs from a committed copy.
"""

import ast
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = HERE.parent
DISPATCH = str(HOOKS / "dispatch.py")
STEM = "block_lease_boundary"
GUARD = HERE / ("%s.py" % STEM)
REPO_ROOT = HERE.parents[2]
MESSAGE_MARK = "ASKED:2026-11-04T10:15Z"
PLANT = "--plant-defect" in sys.argv[1:]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("%s: %s is missing" % (__file__, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtmp = _load("runtmp", REPO_ROOT / ".ci" / "rediacc_ci" / "runtmp.py")
policy = _load("commit_policy_under_test", HOOKS / "commit_policy.py")
TMP = pathlib.Path(os.path.realpath(runtmp.run_dir("guard-lease-boundary-")))

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.pop("COMMIT_POLICY_OK", None)
GIT_ENV.update(
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

failures: list[str] = []


def _git(*argv, cwd, env=None):
    proc = subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=env or GIT_ENV,
    )
    if proc.returncode != 0:
        raise SystemExit("fixture: git %s failed in %s: %s" % (" ".join(argv), cwd, proc.stderr))
    return proc.stdout.strip()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


REMOTE = TMP / "remote.git"
SUB_SOURCE = TMP / "sub-source"
SUB_REMOTE = TMP / "sub-remote.git"
MAIN = TMP / "main"
HOLDER = MAIN / ".claude" / "worktrees"
SUBPATH = "private/sub"

_git("init", "-q", "--bare", str(REMOTE), cwd=TMP)
_git("init", "-q", "--bare", str(SUB_REMOTE), cwd=TMP)
SUB_SOURCE.mkdir()
_git("init", "-q", "--initial-branch=main", cwd=SUB_SOURCE)
_write(SUB_SOURCE / "a.txt", "a\n")
_git("add", "--", "a.txt", cwd=SUB_SOURCE)
_git("commit", "-q", "-m", "seed", cwd=SUB_SOURCE)

MAIN.mkdir()
_git("init", "-q", "--initial-branch=main", cwd=MAIN)
_write(MAIN / "src" / "x.ts", "x\n")
_write(MAIN / "agent" / "plans" / "keep.md", "keep\n")
_git("add", "--", "src", "agent", cwd=MAIN)
_git("commit", "-q", "-m", "seed", cwd=MAIN)
_git(
    "-c",
    "protocol.file.allow=always",
    "submodule",
    "add",
    "-q",
    str(SUB_SOURCE),
    SUBPATH,
    cwd=MAIN,
)
_git("commit", "-q", "-m", "submodule", cwd=MAIN)
_git("remote", "add", "origin", str(REMOTE), cwd=MAIN)
_git("switch", "-q", "-c", "1104-1", cwd=MAIN)
_git("commit", "-q", "--allow-empty", "-m", "live", cwd=MAIN)
_git("push", "-q", "origin", "main", "1104-1", cwd=MAIN)
_git("remote", "set-url", "origin", str(SUB_REMOTE), cwd=MAIN / SUBPATH)
_git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=MAIN / SUBPATH)
with (MAIN / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
    handle.write("/.claude/worktrees/\n")
SUB_STORE = MAIN / ".git" / "modules" / SUBPATH
GITLINK = _git("rev-parse", "HEAD", cwd=MAIN / SUBPATH)


def _lease(name):
    """One console tree and its submodule tree, the way W0's candidate A builds them."""
    tree = HOLDER / name
    _git("worktree", "add", "-q", "--detach", str(tree), "HEAD", cwd=MAIN)
    (tree / SUBPATH).mkdir(parents=True, exist_ok=True)
    _git("worktree", "add", "-q", "--detach", str(tree / SUBPATH), GITLINK, cwd=SUB_STORE)
    return tree


LEASE = _lease("w")
SUB_LEASE = LEASE / SUBPATH

# Modified, not staged: the row that commits it by pathspec is the allowed one.
_write(LEASE / "src" / "x.ts", "changed\n")

STAGED_AGENT = _lease("staged-agent")
_write(STAGED_AGENT / "agent" / "plans" / "x.md", "x\n")
_git("add", "--", "agent/plans/x.md", cwd=STAGED_AGENT)
_write(STAGED_AGENT / "src" / "x.ts", "changed\n")

STAGED_LINK = _lease("staged-link")
_git("commit", "-q", "--allow-empty", "-m", "moved", cwd=STAGED_LINK / SUBPATH)
_git("add", "--", SUBPATH, cwd=STAGED_LINK)

MOVED_LINK = _lease("moved-link")
_git("commit", "-q", "--allow-empty", "-m", "moved", cwd=MOVED_LINK / SUBPATH)

# Not leases: the same path with no link, and a linked tree of another repository.
OTHER_MAIN = TMP / "other"
OTHER_MAIN.mkdir()
_git("init", "-q", "--initial-branch=main", cwd=OTHER_MAIN)
_git("commit", "-q", "--allow-empty", "-m", "seed", cwd=OTHER_MAIN)
PLAIN_UNDER_HOLDER = TMP / "holderless" / ".claude" / "worktrees" / "plain"
PLAIN_UNDER_HOLDER.mkdir(parents=True)
_git("init", "-q", "--initial-branch=main", cwd=PLAIN_UNDER_HOLDER)
_git("commit", "-q", "--allow-empty", "-m", "seed", cwd=PLAIN_UNDER_HOLDER)
STRANGER = HOLDER / "stranger"
_git("worktree", "add", "-q", "--detach", str(STRANGER), "HEAD", cwd=OTHER_MAIN)
OPERATOR_TREE = MAIN / ".worktrees" / "0128-1"
_git("worktree", "add", "-q", "--detach", str(OPERATOR_TREE), "HEAD", cwd=MAIN)

print("== the fixture is the shape it claims")
FACTS = [
    ("the lease is a lease", policy.lease_root(str(LEASE)), str(LEASE)),
    ("a subdirectory answers the lease", policy.lease_root(str(LEASE / "src")), str(LEASE)),
    ("the submodule tree answers the lease", policy.lease_root(str(SUB_LEASE)), str(LEASE)),
    ("the main checkout is none", policy.lease_root(str(MAIN)), ""),
    ("the main submodule is none", policy.lease_root(str(MAIN / SUBPATH)), ""),
    ("the holder itself is none", policy.lease_root(str(HOLDER)), ""),
    ("an operator's tree is none", policy.lease_root(str(OPERATOR_TREE)), ""),
    ("a plain repository at a holder is none", policy.lease_root(str(PLAIN_UNDER_HOLDER)), ""),
    ("another repository's tree is none", policy.lease_root(str(STRANGER)), ""),
    ("no directory is none", policy.lease_root(""), ""),
    ("a missing path is none", policy.lease_root(str(HOLDER / "absent")), ""),
]
for fact_name, fact_got, fact_want in FACTS:
    if fact_got != fact_want:
        failures.append(fact_name)
        print("*** FAIL *** %s: got %r, want %r" % (fact_name, fact_got, fact_want))
print("%d facts read" % len(FACTS))

# The main checkout pays for no subprocess: git-level hooks run this on every commit.
real_run = policy.subprocess.run


def _no_subprocess(*_args, **_kwargs):
    raise AssertionError("lease_root started a subprocess outside the holder")


policy.subprocess.run = _no_subprocess
try:
    outside = policy.lease_root(str(MAIN))
except AssertionError as exc:
    outside = str(exc)
finally:
    policy.subprocess.run = real_run
if outside != "":
    failures.append("lease_root fast path")
    print("*** FAIL *** lease_root from the main checkout: %r" % outside)

SHA = _git("rev-parse", "main", cwd=MAIN)

# Refused in a lease tree, row by row.
REFUSED = [
    ("push to the live branch", "git push origin HEAD:1104-1"),
    ("push of a pin", "git push origin refs/worktrees/x"),
    ("push onto a pin", "git push origin HEAD:refs/worktrees/x"),
    ("gh pr create", "gh pr create --title x --body y"),
    ("git switch main", "git switch main"),
    ("git switch -c", "git switch -c x"),
    ("git checkout of the live branch", "git checkout 1104-1"),
    ("git cherry-pick", "git cherry-pick %s" % SHA),
    ("git cherry-pick, bare", "git cherry-pick"),
    # Spellings of the same acts.
    ("a global option before push", "git -c a=b push origin HEAD:1104-1"),
    ("a bare push", "git push"),
    ("a chain", "true && git push origin HEAD:1104-1"),
    ("a sh -c wrapper", "sh -c 'git push origin HEAD:1104-1'"),
    ("a -C from inside", "git -C . switch main"),
    ("a bundle", "git checkout -qb x"),
    ("git checkout --detach", "git checkout --detach %s" % SHA),
    ("git checkout of a commit", "git checkout %s" % SHA),
    ("git checkout, the previous tip", "git checkout -"),
    ("a name git may turn into a branch", "git checkout not-a-branch-yet"),
    ("git branch <new>", "git branch x"),
    ("git branch -f", "git branch -f 1104-1 HEAD"),
    ("git branch -m", "git branch -m 1104-1 x"),
    ("git branch -M", "git branch -M 1104-1 x"),
    ("git branch -c", "git branch -c 1104-1 x"),
    ("git branch -C", "git branch -C 1104-1 x"),
    ("git branch -d", "git branch -d 1104-1"),
    ("git rebase", "git rebase main"),
    ("git merge", "git merge main"),
    ("git pull", "git pull origin main"),
    ("git am", "git am x.patch"),
    ("git worktree list", "git worktree list"),
    ("git update-ref", "git update-ref refs/heads/x HEAD"),
    ("git symbolic-ref with a target", "git symbolic-ref HEAD refs/heads/1104-1"),
    ("gh pr, a read", "gh pr view 1"),
    ("gh pr, a global flag", "gh pr -R o/r create --title x --body y"),
    ("gh api, writing", "gh api -X POST repos/o/r/pulls -f title=x"),
]

# In another lease, whose index holds the row's state.
REFUSED_ELSEWHERE = [
    ("a staged gitlink, no pathspec", "git commit -F m", STAGED_LINK),
    ("a staged gitlink by pathspec", "git commit -F m -- %s" % SUBPATH, STAGED_LINK),
    ("a gitlink moved and -a", "git commit -a -F m", MOVED_LINK),
    ("a gitlink moved and a dot", "git commit -F m -- .", MOVED_LINK),
    ("staged agent/plans/x.md", "git commit -F m", STAGED_AGENT),
    ("agent/plans/x.md by pathspec", "git commit -F m -- agent/plans/x.md", STAGED_AGENT),
    ("agent/ by directory", "git commit -F m -- agent", STAGED_AGENT),
    ("a dot holding agent/**", "git commit -F m -- .", STAGED_AGENT),
    ("from a subdirectory", "git commit -F m -- ../agent/plans/x.md", STAGED_AGENT / "src"),
    # The submodule tree of a lease is the same lease.
    ("push from the submodule tree", "git push origin HEAD:main", SUB_LEASE),
    ("switch from the submodule tree", "git switch main", SUB_LEASE),
    ("gh pr create from the submodule tree", "gh pr create --title x --body y", SUB_LEASE),
    ("cherry-pick from the submodule tree", "git cherry-pick HEAD", SUB_LEASE),
    # The directory is the command's, not the shell's.
    ("-C into the lease", "git -C %s switch main" % LEASE, MAIN),
    ("cd into the lease", "cd %s && git push origin HEAD:1104-1" % LEASE, MAIN),
    ("-C into its submodule tree", "git -C %s push" % SUBPATH, LEASE),
    ("cd into its submodule tree", "cd %s && git switch main" % SUBPATH, LEASE),
]

ALLOWED = [
    ("the pathspec commit", "git commit -F m -- src/x.ts"),
    ("git status", "git status"),
    ("git log", "git log"),
    ("git diff", "git diff"),
    ("git add", "git add -- src/x.ts"),
    ("git rev-parse", "git rev-parse HEAD"),
    ("a checkout of a path", "git checkout -- src/x.ts"),
    ("a checkout of a path from a tree", "git checkout HEAD -- src/x.ts"),
    ("a checkout of a lone path", "git checkout src/x.ts"),
    ("a bare checkout", "git checkout"),
    ("git branch, listing", "git branch --list"),
    ("git branch, the current one", "git branch --show-current"),
    ("git symbolic-ref, a read", "git symbolic-ref -q HEAD"),
    ("git fetch", "git fetch origin"),
    ("gh run list", "gh run list"),
    ("gh api, reading", "gh api repos/o/r/pulls"),
    ("gh pr --help", "gh pr --help"),
    ("git push in prose", "echo git push origin HEAD:1104-1"),
    ("git switch in a heredoc", "cat > n.md <<'EOF'\ngit switch main\nEOF"),
    ("no git at all", "ls -la"),
    ("an empty command", ""),
]

ALLOWED_ELSEWHERE = [
    ("a pathspec beside a staged agent path", "git commit -F m -- src/x.ts", STAGED_AGENT),
    ("a directory holding no agent path", "git commit -F m -- src", STAGED_AGENT),
    ("a pathspec beside a moved gitlink", "git commit -F m -- src", MOVED_LINK),
    ("the submodule tree's status", "git status", SUB_LEASE),
    ("the submodule tree's commit", "git commit -F m -- a.txt", SUB_LEASE),
    # Not leases.
    ("a linked tree that is an operator's", "git switch main", OPERATOR_TREE),
    ("a plain repository at a holder", "git push origin HEAD:x", PLAIN_UNDER_HOLDER),
    ("another repository's tree", "git switch main", STRANGER),
    ("the main submodule", "git switch main", MAIN / SUBPATH),
    ("-C out to the main checkout", "git -C %s switch main" % MAIN, LEASE),
]

# Every refused row, verbatim, from the main checkout: not this guard's business.
MAIN_ROWS = [row for row in REFUSED if "cd " not in row[1]]


def _payload(command, cwd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


# The declared DEFECT applied to a copy, the whole guard otherwise unchanged.
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
    for node in ast.parse(GUARD.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "DEFECT" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit("%s declares no DEFECT" % GUARD)


DEFECT_PAIR = _declared_defect()
ENV = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(MAIN))


def run_guard(command, cwd, defect=None):
    payload = _payload(command, cwd)
    if defect is not None:
        code = BROKEN_RUNNER % (str(HOOKS.parent), str(GUARD), defect, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=ENV, cwd=str(MAIN)
    )
    if proc.returncode not in (0, 2):
        print("*** CRASH *** rc=%d %r\n%s" % (proc.returncode, command, proc.stderr[-800:]))
        failures.append("crash: %s" % command)
    return proc.returncode, proc.stderr


def check(name, want_blocked, command, cwd):
    rc, err = run_guard(command, cwd, defect=DEFECT_PAIR if PLANT else None)
    blocked = rc == 2
    fine = blocked == want_blocked
    if blocked and MESSAGE_MARK not in err:
        fine = False
    if not want_blocked and err:
        fine = False
    print(
        "%-46s want=%-8s got=%-8s %s"
        % (
            name[:46],
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if blocked else "allowed",
            "ok" if fine else "*** FAIL ***",
        )
    )
    if not fine:
        failures.append(name)
        print("    command: %r\n    stderr: %s" % (command, err.strip()[:400]))


print("== refused in the lease (%d rows)" % len(REFUSED))
for row_name, row_command in REFUSED:
    check(row_name, True, row_command, LEASE)

print("== refused with the row's own state (%d rows)" % len(REFUSED_ELSEWHERE))
for row_name, row_command, row_cwd in REFUSED_ELSEWHERE:
    check(row_name, True, row_command, row_cwd)

print("== allowed in the lease (%d rows)" % len(ALLOWED))
for row_name, row_command in ALLOWED:
    check(row_name, False, row_command, LEASE)

print("== allowed with the row's own state (%d rows)" % len(ALLOWED_ELSEWHERE))
for row_name, row_command, row_cwd in ALLOWED_ELSEWHERE:
    check(row_name, False, row_command, row_cwd)

print("== the same commands from the main checkout (%d rows)" % len(MAIN_ROWS))
for row_name, row_command in MAIN_ROWS:
    check("main: %s" % row_name, False, row_command, MAIN)
for row_name, row_command, _row_cwd in REFUSED_ELSEWHERE[:8]:
    check("main: %s" % row_name, False, row_command, MAIN)

if PLANT:
    print("\n%d rows failed with the DEFECT planted" % len(failures))
    sys.exit(1 if failures else 0)

print("== the chain carries it")
listing = subprocess.run(
    [sys.executable, DISPATCH, "--list"], capture_output=True, text=True, check=False, env=ENV
)
listed = [line for line in listing.stdout.splitlines() if STEM in line]
if not (listed and listed[0].split()[0] == "pre-bash"):
    failures.append("not on the pre-bash chain")
    print("*** FAIL *** %s is not listed on pre-bash: %r" % (STEM, listed))
else:
    print("listed: %s" % " ".join(listed[0].split()))
chain = subprocess.run(
    [sys.executable, DISPATCH, "--chain", "pre-bash"],
    input=_payload("git switch main", LEASE),
    capture_output=True,
    text=True,
    check=False,
    env=ENV,
    cwd=str(MAIN),
)
if chain.returncode != 2 or MESSAGE_MARK not in chain.stderr:
    failures.append("chain did not refuse")
    print("*** FAIL *** the chain answered rc=%d: %s" % (chain.returncode, chain.stderr[-400:]))
else:
    print("chain: refused by this guard, rc=2")

print("== the DEFECT control")
ALL_REFUSED = [(n, c, LEASE) for n, c in REFUSED] + REFUSED_ELSEWHERE
kept_refused = [n for n, c, where in ALL_REFUSED if run_guard(c, where, defect=DEFECT_PAIR)[0] != 0]
if kept_refused:
    failures.append("defect control")
    print("*** FAIL *** with %r planted these still refuse: %r" % (DEFECT_PAIR, kept_refused[:5]))
else:
    print("planted %r: all %d refusals flipped" % (DEFECT_PAIR[0], len(ALL_REFUSED)))
planted = subprocess.run(
    [sys.executable, __file__, "--plant-defect"], capture_output=True, text=True, check=False
)
if planted.returncode != 1:
    failures.append("the planted suite stayed green")
    print("*** FAIL *** the suite with the DEFECT planted exited %d" % planted.returncode)
else:
    print("the whole suite with the DEFECT planted: rc=1")

# --------------------------------------------------------------------------- git-level arms ---------------------------------------------------------------------------

print("== the git-level arms, through the real shims")
GIT_HOOKS = str(HOOKS / "git")
_git("config", "core.hooksPath", GIT_HOOKS, cwd=MAIN)
_git("config", "core.hooksPath", GIT_HOOKS, cwd=SUB_STORE)
_git("update-ref", "refs/worktrees/x", "HEAD", cwd=MAIN)
# A lease commit also names a declared epic (bd540a13c: the lease `commit-msg` hook judges `PR-TASK` against the MAIN checkout's `agent/pr/<live branch>.md` united with the ledger), so the main checkout declares one and the message names it. Untracked, so no lease above sees it.
FIXTURE_EPIC = "f1c7a5e0"
_write(MAIN / "agent" / "pr" / "1104-1.md", "`PR-TASK: %s`\n" % FIXTURE_EPIC)
_write(
    TMP / "m",
    "chore: fixture\n\nPR-TASK: %s\nPlan-Box: none -- fixture commit of the boundary control\n"
    % FIXTURE_EPIC,
)
MESSAGE_FILE = str(TMP / "m")


def _remote_has(ref, remote=REMOTE):
    return (
        subprocess.run(
            ["git", "show-ref", "--verify", "-q", ref],
            cwd=str(remote),
            check=False,
            env=GIT_ENV,
        ).returncode
        == 0
    )


def _shim(name, want_rc_zero, argv, cwd, stderr_has="", env=None):
    proc = subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        env=env or GIT_ENV,
    )
    fine = (proc.returncode == 0) == want_rc_zero
    if stderr_has and stderr_has not in proc.stderr:
        fine = False
    print(
        "%-46s want=%-8s rc=%-4d %s"
        % (
            name[:46],
            "passes" if want_rc_zero else "refused",
            proc.returncode,
            "ok" if fine else "*** FAIL ***",
        )
    )
    if not fine:
        failures.append("shim: %s" % name)
        print("    stderr: %s" % proc.stderr.strip()[-500:])


# Each refused pin names a ref the remote must still lack.
PIN = "refs/worktrees/"
for shim_name, shim_where, shim_spec, shim_ref in (
    ("pin from the lease", LEASE, "refs/worktrees/x", "refs/worktrees/x"),
    ("HEAD onto a pin from the lease", LEASE, "HEAD:refs/worktrees/y", "refs/worktrees/y"),
    ("pin from the main checkout", MAIN, "refs/worktrees/x", "refs/worktrees/x"),
    ("HEAD onto a pin from the main checkout", MAIN, "HEAD:refs/worktrees/y", "refs/worktrees/y"),
    ("pin under a branch name", MAIN, "refs/worktrees/x:refs/heads/z", "refs/heads/z"),
):
    _shim(shim_name, False, ["push", "origin", shim_spec], shim_where, stderr_has=PIN)
    if _remote_has(shim_ref):
        failures.append("shim landed: %s" % shim_name)
        print("*** FAIL *** %s reached the remote" % shim_ref)

_shim(
    "any push from the lease",
    False,
    ["push", "origin", "HEAD:refs/heads/z"],
    LEASE,
    stderr_has="lease tree",
)
_shim(
    "any push from the submodule tree",
    False,
    ["push", "origin", "HEAD:refs/heads/z"],
    SUB_LEASE,
    stderr_has="lease tree",
)
if _remote_has("refs/heads/z"):
    failures.append("a lease push landed")
    print("*** FAIL *** a lease push reached the remote")

_shim(
    "a staged agent path from the lease",
    False,
    ["commit", "-q", "-F", MESSAGE_FILE],
    STAGED_AGENT,
    stderr_has="agent/plans/x.md",
)
_shim(
    "a staged gitlink from the lease",
    False,
    ["commit", "-q", "-F", MESSAGE_FILE],
    STAGED_LINK,
    stderr_has="a gitlink",
)
_shim(
    "a gitlink by pathspec from the lease",
    False,
    ["commit", "-q", "-F", MESSAGE_FILE, "--", SUBPATH],
    MOVED_LINK,
    stderr_has="a gitlink",
)
_shim(
    "a pathspec beside a staged agent path",
    True,
    ["commit", "-q", "-F", MESSAGE_FILE, "--", "src/x.ts"],
    STAGED_AGENT,
)
_shim(
    "the pathspec commit from the lease",
    True,
    ["commit", "-q", "-F", MESSAGE_FILE, "--", "src/x.ts"],
    LEASE,
)
_shim(
    "a commit in the submodule tree",
    True,
    ["commit", "-q", "--allow-empty", "-F", MESSAGE_FILE],
    SUB_LEASE,
)

# The arms judge a lease and a pin, not every commit and push.
_write(MAIN / "agent" / "plans" / "main.md", "main\n")
_git("add", "--", "agent/plans/main.md", cwd=MAIN)
_shim("an agent path from the main checkout", True, ["commit", "-q", "-F", MESSAGE_FILE], MAIN)
_shim("the live branch from the main checkout", True, ["push", "origin", "1104-1"], MAIN)

# With the override the pin lands, so the refusals above were the hook's.
_shim(
    "a pin with the override",
    True,
    ["push", "origin", "refs/worktrees/x"],
    MAIN,
    env=dict(GIT_ENV, COMMIT_POLICY_OK="1"),
)
if not _remote_has("refs/worktrees/x"):
    failures.append("the override control did not land")
    print("*** FAIL *** the override push left no pin on the remote")

if failures:
    print("\n%d FAILED: %s" % (len(failures), ", ".join(failures[:25])))
    sys.exit(1)
print(
    "\nOK: %d refused, %d allowed, %d facts, chain, DEFECT and git-level controls held"
    % (len(ALL_REFUSED), len(ALLOWED) + len(ALLOWED_ELSEWHERE) + len(MAIN_ROWS), len(FACTS))
)
