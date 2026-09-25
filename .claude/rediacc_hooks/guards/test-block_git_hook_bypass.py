#!/usr/bin/env python3
"""Control harness for block_git_hook_bypass, the git-level hooks it protects, and the setup phase that installs them.

THREE PARTS, ONE FILE, because the three are one mechanism (the commit-policy plan in agent/plans, T8) and this is the suite `test_hooks_delegates.py` discovers beside the guard:

  1. THE GUARD, driven through the dispatcher: every way around the hooks is refused, reads are not, and the declared DEFECT planted in a copy flips at least one fire case to allowed.
  2. THE GIT HOOKS (`.claude/rediacc_hooks/git/`), exercised by REAL git in throwaway repositories whose `core.hooksPath` points at them: `commit-msg`, `reference-transaction` and `pre-push`, each refusal and its inverse, a real submodule for the coordinated-name rule, and the `COMMIT_POLICY_OK=1` override. Nothing here touches this checkout's own config.
  3. THE SETUP PHASE (`.ci/rediacc_ci/setup/githooks.py`), run against a synthetic console: it points the console and each checked-out submodule at the hooks, a second run does nothing, and a missing hook file is a failure rather than a silent install of nothing.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_git_hook_bypass"
GUARD = HERE / ("%s.py" % STEM)
REPO_ROOT = HERE.parents[2]
HOOKS = HERE.parent / "git"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("%s: %s is missing" % (__file__, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtmp = _load("runtmp", REPO_ROOT / ".ci" / "rediacc_ci" / "runtmp.py")
setup_githooks = _load("setup_githooks", REPO_ROOT / ".ci" / "rediacc_ci" / "setup" / "githooks.py")
RUN_TMP = runtmp.run_dir("guard-hook-bypass-")

BASE_ENV = {k: v for k, v in os.environ.items() if k != "COMMIT_POLICY_OK"}
GIT_ENV = dict(
    BASE_ENV,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

failures: list[str] = []


def report(name, want, got, detail=""):
    ok = want == got
    if not ok:
        failures.append(name)
    print(
        "%-58s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and detail:
        print("    %s" % detail.strip().splitlines()[:4])


# --------------------------------------------------------------------------- 1. the guard ---------------------------------------------------------------------------

GUARD_CASES = [
    # (name, command, expect_blocked)
    ("commit --no-verify", "git commit --no-verify -m x -- a", True),
    ("commit -n", "git commit -n -m x -- a", True),
    ("a bundled -n", "git commit -anm x", True),
    ("-c core.hooksPath=/dev/null", "git -c core.hooksPath=/dev/null commit -m x -- a", True),
    ("-c with the key in another case", "git -c core.hookspath=/x commit -m x -- a", True),
    ("config core.hooksPath <value>", "git config core.hooksPath /tmp/x", True),
    ("config --local core.hooksPath <value>", "git config --local core.hooksPath x", True),
    ("config --unset core.hooksPath", "git config --unset core.hooksPath", True),
    ("config unset core.hooksPath", "git config unset core.hooksPath", True),
    ("push --no-verify", "git push --no-verify origin 0923-1", True),
    ("merge --no-verify", "git merge --no-verify x", True),
    ("the override on a commit", "COMMIT_POLICY_OK=1 git commit -m x -- a", True),
    ("the override exported", "export COMMIT_POLICY_OK=1; git push", True),
    ("config by environment", "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/x'\" git commit", True),
    ("config --get is a read", "git config --get core.hooksPath", False),
    ("config with no value is a read", "git config core.hooksPath", False),
    ("log -n is not a commit", "git log -n 5", False),
    ("push -n is a dry run", "git push -n origin 0923-1", False),
    ("an ordinary commit", "git commit -F m -- a", False),
    ("prose naming the flag", "echo 'never git commit --no-verify'", False),
    ("prose naming the override", "echo 'the override is COMMIT_POLICY_OK=1'", False),
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


def run_guard(command, broken=False):
    env = dict(BASE_ENV, CLAUDE_PROJECT_DIR=str(REPO_ROOT))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True, check=False, env=env)
    if broken and proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


print("== the guard")
guard_blocked = 0
for name, command, want in GUARD_CASES:
    got, err = run_guard(command)
    guard_blocked += got
    report(name, want, got, err)
flipped = [n for n, c, want in GUARD_CASES if want and not run_guard(c, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped, e.g. %r"
        % (DEFECT[0], len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every fire case still refused" % (DEFECT,))
    failures.append("control")
if guard_blocked in (0, len(GUARD_CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    failures.append("control")


# --------------------------------------------------------------------------- 2. the git hooks ---------------------------------------------------------------------------


def git(repo, *args, env=None, check=True):
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        env=env or GIT_ENV,
    )
    if check and proc.returncode != 0:
        raise SystemExit("fixture git %s failed in %s: %s" % (args, repo, proc.stderr))
    return proc


def make_repo(branch="main", extra=(), hooks=True, at=None):
    path = pathlib.Path(at) if at else pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "--initial-branch=main")
    git(path, "commit", "-q", "--allow-empty", "-m", "seed")
    for name in extra:
        git(path, "branch", name)
    if branch != "main":
        git(path, "checkout", "-q", "-b", branch)
    if hooks:
        git(path, "config", "core.hooksPath", str(HOOKS))
    return path


def refused(repo, *args, override=False):
    env = dict(GIT_ENV, COMMIT_POLICY_OK="1") if override else GIT_ENV
    proc = git(repo, *args, env=env, check=False)
    return proc.returncode != 0, proc.stderr


def stage(repo, *rels):
    for rel in rels:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    git(repo, "add", "--", *rels)


print("\n== the git hooks (core.hooksPath -> %s)" % HOOKS)
for name in setup_githooks.HOOK_NAMES:
    if not os.access(HOOKS / name, os.X_OK):
        print("*** FAIL *** %s is not executable" % (HOOKS / name))
        failures.append("control")

EVIDENCE = "fix(ci): x [hotfix]\n\nHotfix-Evidence: 18012345678"

main_repo = make_repo()
got, err = refused(main_repo, "commit", "-q", "--allow-empty", "-m", "feat: x")
report("commit-msg: a plain commit on main", True, got, err)
got, err = refused(main_repo, "commit", "-q", "--allow-empty", "-m", EVIDENCE)
report("commit-msg: a valid [hotfix] on main", False, got, err)
got, err = refused(main_repo, "commit", "-q", "--allow-empty", "-m", "fix: x [hotfix]")
report("commit-msg: a [hotfix] with no evidence", True, got, err)
got, err = refused(main_repo, "commit", "-q", "--allow-empty", "-m", "feat: x", override=True)
report("commit-msg: COMMIT_POLICY_OK=1 on main", False, got, err)

feature = make_repo("0923-1")
got, err = refused(feature, "commit", "-q", "--allow-empty", "-m", "chore: x [skip ci]")
report("commit-msg: a skip token", True, got, err)
got, err = refused(feature, "commit", "-q", "--allow-empty", "-m", EVIDENCE)
report("commit-msg: [hotfix] off main", True, got, err)
stage(feature, "src/a.ts")
got, err = refused(feature, "commit", "-q", "-m", "docs: x [no-review]")
report("commit-msg: [no-review] on code", True, got, err)
got, err = refused(feature, "commit", "-q", "-m", "feat: x")
report("commit-msg: a plain commit on the branch", False, got, err)
stage(feature, "docs/y.md")
got, err = refused(feature, "commit", "-q", "-m", "docs: y [no-review]")
report("commit-msg: [no-review] on writing", False, got, err)

got, err = refused(feature, "branch", "0925-1")
report("reference-transaction: a second branch from a branch", True, got, err)
got, err = refused(feature, "branch", "0925-1", override=True)
report("reference-transaction: the same, COMMIT_POLICY_OK=1", False, got, err)
got, err = refused(feature, "branch", "-m", "0923-1", "0925-2")
report("reference-transaction: a rename is not a creation", False, got, err)

main_live = make_repo(extra=("0923-1",))
got, err = refused(main_live, "switch", "-q", "-c", "0925-1")
report("reference-transaction: on main beside a live branch", True, got, err)
main_clean = make_repo()
got, err = refused(main_clean, "switch", "-q", "-c", "feature/x")
report("reference-transaction: a name that is not MMDD-N", True, got, err)
got, err = refused(main_clean, "switch", "-q", "-c", "0925-1")
report("reference-transaction: on main, nothing live", False, got, err)

# A live branch whose upstream is GONE (its PR merged and GitHub deleted the head) no longer counts.
origin = pathlib.Path(tempfile.mkdtemp(prefix="origin-", dir=RUN_TMP))
git(origin, "init", "-q", "--bare", "--initial-branch=main")
gone = make_repo(extra=("0923-1",), hooks=False)
git(gone, "remote", "add", "origin", str(origin))
git(gone, "push", "-q", "-u", "origin", "0923-1")
git(gone, "push", "-q", "origin", "--delete", "0923-1")
git(gone, "fetch", "-q", "--prune", "origin")
git(gone, "config", "core.hooksPath", str(HOOKS))
got, err = refused(gone, "switch", "-q", "-c", "0925-3")
report("reference-transaction: a merged branch (upstream gone)", False, got, err)

# A real submodule: its branch must carry the console's name.
sub_src = make_repo(hooks=False)
console = make_repo("0923-1")
git(
    console,
    "-c",
    "protocol.file.allow=always",
    "submodule",
    "add",
    "-q",
    str(sub_src),
    "private/sub",
)
sub = console / "private" / "sub"
git(sub, "config", "core.hooksPath", str(HOOKS))
got, err = refused(sub, "checkout", "-q", "-b", "0925-9")
report("reference-transaction: a submodule branch off the console's", True, got, err)
got, err = refused(sub, "checkout", "-q", "-b", "0923-1")
report("reference-transaction: a submodule branch named for it", False, got, err)

bare = pathlib.Path(tempfile.mkdtemp(prefix="origin-", dir=RUN_TMP))
git(bare, "init", "-q", "--bare", "--initial-branch=main")
pusher = make_repo("0923-1")
git(pusher, "remote", "add", "origin", str(bare))
got, err = refused(pusher, "push", "-q", "origin", "0923-1")
report("pre-push: the one branch", False, got, err)
got, err = refused(pusher, "push", "-q", "origin", "HEAD:0925-1")
report("pre-push: a second remote branch", True, got, err)
got, err = refused(pusher, "push", "-q", "origin", "HEAD:main")
report("pre-push: straight to main", True, got, err)
got, err = refused(pusher, "push", "-q", "origin", "HEAD:main", override=True)
report("pre-push: straight to main, COMMIT_POLICY_OK=1", False, got, err)


# --------------------------------------------------------------------------- 3. the setup phase ---------------------------------------------------------------------------

print("\n== the setup phase (.ci/rediacc_ci/setup/githooks.py)")
fake = make_repo("0923-1", hooks=False)
fake_hooks = setup_githooks.hooks_dir(fake)
fake_hooks.mkdir(parents=True)
for name in setup_githooks.HOOK_NAMES:
    shutil.copy2(HOOKS / name, fake_hooks / name)
(fake / ".gitmodules").write_text(
    '[submodule "private/a"]\n\tpath = private/a\n[submodule "private/absent"]\n\tpath = private/absent\n',
    encoding="utf-8",
)
make_repo(hooks=False, at=fake / "private" / "a")
said: list[str] = []
rc = setup_githooks.install(fake, say=said.append)
values = [setup_githooks.current(fake), setup_githooks.current(fake / "private" / "a")]
ok = rc == 0 and values == [str(fake_hooks)] * 2 and len(said) == 2
if not ok:
    failures.append("setup")
print(
    "install points the console and the checked-out submodule: %s"
    % ("ok" if ok else "*** FAIL *** rc=%s %s %s" % (rc, values, said))
)
said = []
rc = setup_githooks.install(fake, say=said.append)
ok = rc == 0 and said == [] and setup_githooks.check_row(fake)[1] is False
if not ok:
    failures.append("setup")
print(
    "a second run does nothing, and --check reports nothing pending: %s"
    % ("ok" if ok else "*** FAIL *** %s" % said)
)
git(fake, "config", "core.hooksPath", "/elsewhere")
row, pending = setup_githooks.check_row(fake)
ok = pending and "NOT installed" in row
if not ok:
    failures.append("setup")
print(
    "--check names a repository pointing elsewhere: %s" % ("ok" if ok else "*** FAIL *** %r" % row)
)
(fake_hooks / "pre-push").unlink()
said = []
rc = setup_githooks.install(fake, say=said.append)
ok = rc == 1 and setup_githooks.current(fake) == "/elsewhere"
if not ok:
    failures.append("setup")
print(
    "a missing hook file fails the phase and installs nothing: %s"
    % ("ok" if ok else "*** FAIL *** rc=%s" % rc)
)

print()
print("%d guard case(s), %d blocked" % (len(GUARD_CASES), guard_blocked))
print("FAILURES: %d" % len(failures))
sys.exit(1 if failures else 0)
