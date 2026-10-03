#!/usr/bin/env python3
"""Control harness for block_push_to_protected_branch.

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True` (it was never bash: no direct-push-to-main guard existed before this incident), so it has no golden either and `test_guards_differential.py` instead REQUIRES a `test-<stem>.py` beside it -- see `test_every_port_has_goldens`. This is that file, and `check-hook-integrity.sh` credits the
guard with coverage under both directions because of it.

TWO REAL REPOS, ON DISK, BUILT ONCE. Half this guard's cases depend on which branch the checkout is ON (the implicit forms: a bare `git push`, `git push origin`, `git push origin HEAD`), and that is not something a fixed payload can encode -- it has to come from an actual `git symbolic-ref` read against an actual working tree. `MAIN_REPO` and `FEATURE_REPO` are built fresh in a
temp directory the first time this module runs, exactly the shape `test_guards_differential.py`'s own named git fixtures use (`git-main`, `git-ahead`) for the same reason, just not shared with that file: this guard's own suite owns its worlds.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that actually runs goes unchecked.

THE FAST-FORWARD FALLBACK (box M2 of PLAN-plan-per-pr-loop, operator ruling 2026-10-02) needs a third kind of world: a console-shaped checkout on its live branch with a real bare `origin` (so `origin/<branch>` and `origin/main` are real refs), and a `gh` stub on PATH that answers both reads the guard makes, `gh pr view` and the GraphQL rollup `.ci/scripts/ci/ci-trace.py` sends. The stub's answers come from `FX_*` variables per case: the PR head, the CI Complete conclusion, the PR body, no PR, gh down. ci-trace itself runs for real; only GitHub is faked.

THE GIT-LEVEL TWIN is driven here too, with real `git push` into throwaway bare origins whose clones point `core.hooksPath` at `.claude/rediacc_hooks/git/`: the same fallback admitted, and every other push to `main` (a delete included) refused.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import typing

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")

# ONE PID-STAMPED RUN DIRECTORY holds both fixture repos, and the next run sweeps it when this one was killed before `atexit` could fire: 114 `guard-push-main-*` repos had leaked into /tmp by 2026-09-24. See `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop, which test_canonical_sys_path_hop.py freezes; it is stdlib-only for exactly this reason.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)

RUN_TMP = runtmp.run_dir("guard-push-main-")
GUARD_ARGV = [sys.executable, DISPATCH, "block_push_to_protected_branch"]

_FIXTURE_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _make_repo(branch):
    d = tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP)
    subprocess.run(
        ["git", "init", "-q", "-b", branch, d], check=True, capture_output=True, env=_FIXTURE_ENV
    )
    subprocess.run(
        ["git", "-C", d, "commit", "-q", "--allow-empty", "-m", "seed"],
        check=True,
        capture_output=True,
        env=_FIXTURE_ENV,
    )
    return d


MAIN_REPO = _make_repo("main")
FEATURE_REPO = _make_repo("0914-1")

HOOKS = pathlib.Path(__file__).resolve().parents[1] / "git"


def _git(repo, *args, env=None, check=True):
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
        env=env or _FIXTURE_ENV,
    )
    if check and proc.returncode != 0:
        raise SystemExit("fixture git %s failed in %s: %s" % (args, repo, proc.stderr))
    return proc


# The plan gate's worlds (box L2): plans committed on the live branch, so the gate reads them at the pushed sha. `PLAN_WT` is ticked only in the working tree, never committed, which the gate must not count.
PLAN_DONE = "agent/plans/PLAN-fx-done.md"
PLAN_OPEN = "agent/plans/PLAN-fx-open.md"
PLAN_NOBOX = "agent/plans/PLAN-fx-nobox.md"
PLANS = {
    PLAN_DONE: "# PLAN-fx-done\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [x] B the second box is finished and ticked\n",
    PLAN_OPEN: "# PLAN-fx-open\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [ ] B the second box is still open on this branch\n",
    PLAN_NOBOX: "# PLAN-fx-nobox\nStatus: approved\n\nProse only, no boxes at all.\n",
}


def _make_live(branch="0914-1", unpushed=False, main_moved=False, hooks=False):
    """A console-shaped checkout on `branch`, pushed to a real bare origin, one commit ahead of main.

    `unpushed` adds a local commit `origin/<branch>` never saw; `main_moved` lands a commit on origin's main that the branch does not contain (a fast-forward is then impossible); `hooks` points `core.hooksPath` at the git-level hooks AFTER the fixture is built.
    """
    bare = pathlib.Path(tempfile.mkdtemp(prefix="origin-", dir=RUN_TMP))
    _git(bare, "init", "-q", "--bare", "--initial-branch=main")
    d = pathlib.Path(tempfile.mkdtemp(prefix="live-", dir=RUN_TMP))
    _git(d, "init", "-q", "--initial-branch=main")
    _git(d, "remote", "add", "origin", str(bare))
    _git(d, "commit", "-q", "--allow-empty", "-m", "seed")
    _git(d, "push", "-q", "origin", "main")
    _git(d, "checkout", "-q", "-b", branch)
    for rel, text in PLANS.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    _git(d, "add", "--", *PLANS)
    _git(d, "commit", "-q", "-m", "work")
    _git(d, "push", "-q", "origin", branch)
    if main_moved:
        other = pathlib.Path(tempfile.mkdtemp(prefix="other-", dir=RUN_TMP))
        _git(other, "clone", "-q", str(bare), ".")
        _git(other, "commit", "-q", "--allow-empty", "-m", "elsewhere")
        _git(other, "push", "-q", "origin", "main")
    _git(d, "fetch", "-q", "origin")
    if unpushed:
        _git(d, "commit", "-q", "--allow-empty", "-m", "local only")
    if hooks:
        _git(d, "config", "core.hooksPath", str(HOOKS))
    return d


def _tip(repo, ref):
    return _git(repo, "rev-parse", ref).stdout.strip()


LIVE = _make_live()
LIVE_AHEAD = _make_live(unpushed=True)
LIVE_BEHIND = _make_live(main_moved=True)
LIVE_SHA = _tip(LIVE, "origin/0914-1")

# `gh` for the fallback's two reads: `gh pr view <b> --json ...` and ci-trace's `gh api graphql` rollup (the PR query names `pullRequests(`, the branch fallback names `ref(`). Every answer comes from an FX_* variable the case sets.
GH_STUB = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
mode = os.environ.get("FX_GH", "ok")
head = os.environ.get("FX_HEAD", "")
ci = os.environ.get("FX_CI", "SUCCESS")
body = os.environ.get("FX_BODY", "Operational-Reason: GitHub cannot rebase this PR")
if mode == "down":
    sys.stderr.write("gh: could not connect\n")
    sys.exit(1)
if a[:2] == ["pr", "view"]:
    if mode == "nopr":
        sys.stderr.write('no pull requests found for branch "%s"\n' % a[2])
        sys.exit(1)
    pr = {"number": 7, "state": "OPEN", "headRefOid": head, "body": body}
    if mode == "nobody":
        del pr["body"]
    if mode == "nonumber":
        del pr["number"]
    print(json.dumps(pr))
    sys.exit(0)
if a[:2] == ["api", "graphql"]:
    query = " ".join(a)
    if "pullRequests(" in query:
        if mode == "nopr":
            print(json.dumps({"data": {"repository": {"pullRequests": {"nodes": []}}}}))
            sys.exit(0)
        done = ci != "IN_PROGRESS"
        ctx = {
            "__typename": "CheckRun",
            "name": "CI Complete",
            "status": "COMPLETED" if done else "IN_PROGRESS",
            "conclusion": ci if done else None,
            "databaseId": 1,
            "detailsUrl": "",
            "checkSuite": {"workflowRun": {"databaseId": 9}},
        }
        nodes = [ctx]
        extra = os.environ.get("FX_EXTRA", "")
        if extra:
            # A failing context no workflow on the head defines, as main's retired review-status.yml posted on #591.
            nodes.append({"__typename": "StatusContext", "context": extra, "state": "FAILURE", "targetUrl": ""})
        commit = {
            "oid": head,
            "statusCheckRollup": {
                "state": "PENDING" if not done else "FAILURE" if (ci != "SUCCESS" or extra) else "SUCCESS",
                "contexts": {
                    "totalCount": len(nodes),
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": nodes,
                },
            },
        }
        pr = {"number": 7, "url": "u", "isDraft": False, "commits": {"nodes": [{"commit": commit}]}}
        print(json.dumps({"data": {"repository": {"pullRequests": {"nodes": [pr]}}}}))
        sys.exit(0)
    print(json.dumps({"data": {"repository": {"pushedAt": None, "ref": None}}}))
    sys.exit(0)
print("[]")
"""
STUB_DIR = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
(STUB_DIR / "gh").write_text(GH_STUB, encoding="utf-8")
(STUB_DIR / "gh").chmod(0o755)


def fx(**over):
    """The environment one fallback case runs in: the stub first on PATH, the PR head at the live tip."""
    env = {"PATH": "%s:%s" % (STUB_DIR, os.environ["PATH"]), "FX_HEAD": LIVE_SHA}
    env.update({"FX_" + k.upper(): v for k, v in over.items()})
    return env


# Assembled rather than written, so a mention of the destination this guard exists to protect never itself reads as a call site the prose-style scan has to reason about.
MAIN = "m" + "ain"
BRANCH = "0914-1"

CASES = [
    # (name, command, cwd-or-None, expect_blocked) ---- explicit destinations ---------------
    ("the incident's own shape", "git push origin HEAD:%s" % MAIN, None, True),
    ("a bare destination name", "git push origin %s" % MAIN, None, True),
    ("an explicit source, destination main", "git push origin %s:%s" % (BRANCH, MAIN), None, True),
    ("the refs-qualified long form", "git push origin refs/heads/%s" % MAIN, None, True),
    ("the empty-source delete form", "git push origin :%s" % MAIN, None, True),
    ("the flagged delete form", "git push origin --delete %s" % MAIN, None, True),
    ("--all pushes every branch, main included", "git push --all origin", None, True),
    ("a wrapper payload is still scanned", 'eval "git push origin %s"' % MAIN, None, True),
    (
        "explicit destination wins regardless of the checkout's own branch",
        "git push origin %s" % MAIN,
        FEATURE_REPO,
        True,
    ),
    # ---- implicit destinations: depend on the checkout ------------------------------------
    ("a bare push while checked out on main", "git push", MAIN_REPO, True),
    ("a remote with no refspec while on main", "git push origin", MAIN_REPO, True),
    ("HEAD with no colon while on main", "git push origin HEAD", MAIN_REPO, True),
    ("a bare push while NOT on main", "git push", FEATURE_REPO, False),
    ("a remote with no refspec while NOT on main", "git push origin", FEATURE_REPO, False),
    ("HEAD with no colon while NOT on main", "git push origin HEAD", FEATURE_REPO, False),
    # ---- the allow direction ----------------------------------------------------------------
    ("an ordinary push to a feature branch", "git push origin %s" % BRANCH, None, False),
    ("a branch merely prefixed with main", "git push origin %s-2" % MAIN, None, False),
    ("a branch merely suffixed onto main", "git push origin not-%s" % MAIN, None, False),
    (
        "an explicit non-main destination overrides ambiguity even while on main",
        "git push origin feature-x",
        MAIN_REPO,
        False,
    ),
    ("a dry run publishes nothing", "git push --dry-run origin %s" % MAIN, MAIN_REPO, False),
    (
        "tags only, no branch ref moves, even while on main",
        "git push --tags origin",
        MAIN_REPO,
        False,
    ),
    ("prose about pushing is not a push", "echo 'never push straight to %s'" % MAIN, None, False),
    ("git pull is not git push", "git pull --rebase", None, False),
    (
        "cd into a submodule pushing its own feature branch",
        "cd private/renet && git push origin %s" % BRANCH,
        None,
        False,
    ),
    ("an empty command", "", None, False),
    ("git log mentioning push is not a push", "git log --grep push", None, False),
    # ---- the global-option hole, measured 2026-10-02 at rc 0 ------------------------------
    ("-C before push, destination main", "git -C . push origin HEAD:%s" % MAIN, None, True),
    ("-c before push, destination main", "git -c a=b push origin %s" % MAIN, None, True),
    (
        "--no-pager before push, the delete form",
        "git --no-pager push origin :%s" % MAIN,
        None,
        True,
    ),
    (
        "a dry run beside a real push to main",
        "git push --dry-run origin x; git push origin HEAD:%s" % MAIN,
        None,
        True,
    ),
    # ---- M2: the fast-forward fallback, admitted -----------------------------------------
    ("M2 ff of the live branch", "git push origin 0914-1:%s" % MAIN, LIVE, False, fx()),
    ("M2 ff of origin/<live>", "git push origin origin/0914-1:%s" % MAIN, LIVE, False, fx()),
    ("M2 ff of the tip sha", "git push origin %s:%s" % (LIVE_SHA, MAIN), LIVE, False, fx()),
    (
        "M2 ff, refs spellings both sides",
        "git push origin refs/remotes/origin/0914-1:refs/heads/%s" % MAIN,
        LIVE,
        False,
        fx(),
    ),
    # Operator ruling 2026-10-03: CI Complete decides, not the tracer's whole verdict. A failing context beside a green CI Complete (main's retired "Review Complete" on #591) does not refuse.
    (
        "M2 ff admitted with CI Complete green beside a failing non-required context",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        False,
        fx(extra="Review Complete"),
    ),
    # ---- M2: refused, one condition at a time --------------------------------------------
    ("M2 CI Complete failed", "git push origin 0914-1:%s" % MAIN, LIVE, True, fx(ci="FAILURE")),
    (
        "M2 CI Complete still running",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(ci="IN_PROGRESS"),
    ),
    (
        "M2 the sha is not the PR head",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(head="f" * 40),
    ),
    ("M2 no PR for the branch", "git push origin 0914-1:%s" % MAIN, LIVE, True, fx(gh="nopr")),
    ("M2 gh cannot answer", "git push origin 0914-1:%s" % MAIN, LIVE, True, fx(gh="down")),
    (
        "M2 no Operational-Reason line",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Plan boxes: see the plan."),
    ),
    # ---- L2: the plan gate, the fallback's last condition ----------------------------------
    (
        "L2 open boxes and no Operational-Reason",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Plan: %s" % PLAN_OPEN),
    ),
    (
        "L2 open boxes with an Operational-Reason",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        False,
        fx(body="Plan: %s\nOperational-Reason: the remaining box is M7's live run" % PLAN_OPEN),
    ),
    (
        "L2 every box ticked",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        False,
        fx(body="Some prose.\n\nPlan: `%s`\n" % PLAN_DONE),
    ),
    (
        "L2 no Plan line and no Operational-Reason",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Some prose about the work."),
    ),
    (
        "L2 the body cannot be read",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(gh="nobody"),
    ),
    (
        "L2 two plans and no Operational-Reason",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Plan: %s\nPlan: %s" % (PLAN_DONE, PLAN_DONE.replace("done", "done2"))),
    ),
    (
        "L2 the named plan does not exist at the pushed sha",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Plan: agent/plans/PLAN-fx-missing.md"),
    ),
    (
        "L2 a plan with no boxes proves nothing",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(body="Plan: %s" % PLAN_NOBOX),
    ),
    (
        "L2 an Operational-Reason inside a generated block does not count",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(
            body="Plan: %s\n<!-- pushed-head:begin -->\nOperational-Reason: x\n<!-- pushed-head:end -->"
            % PLAN_OPEN
        ),
    ),
    # 65f2a27e.2: a PR answer missing a field is refused by that field's name, not as "PR #None".
    (
        "M2 the PR answer has no number",
        "git push origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(gh="nonumber"),
        "`number`",
    ),
    (
        "M2 a local commit origin never saw",
        "git push origin 0914-1:%s" % MAIN,
        LIVE_AHEAD,
        True,
        fx(head=_tip(LIVE_AHEAD, "0914-1")),
    ),
    (
        "M2 main moved: not a fast-forward",
        "git push origin 0914-1:%s" % MAIN,
        LIVE_BEHIND,
        True,
        fx(head=_tip(LIVE_BEHIND, "0914-1")),
    ),
    ("M2 HEAD as the source", "git push origin HEAD:%s" % MAIN, LIVE, True, fx()),
    ("M2 --force", "git push --force origin 0914-1:%s" % MAIN, LIVE, True, fx()),
    (
        "M2 --force-with-lease",
        "git push --force-with-lease origin 0914-1:%s" % MAIN,
        LIVE,
        True,
        fx(),
    ),
    ("M2 a plus refspec", "git push origin +0914-1:%s" % MAIN, LIVE, True, fx()),
    ("M2 two refspecs", "git push origin 0914-1:%s 0914-1" % MAIN, LIVE, True, fx()),
    ("M2 --follow-tags", "git push --follow-tags origin 0914-1:%s" % MAIN, LIVE, True, fx()),
    ("M2 --tags beside it", "git push --tags origin 0914-1:%s" % MAIN, LIVE, True, fx()),
    ("M2 another remote", "git push upstream 0914-1:%s" % MAIN, LIVE, True, fx()),
    ("M2 another branch's tip", "git push origin %s:%s" % (MAIN, MAIN), LIVE, True, fx()),
    ("M2 the delete form", "git push origin --delete %s" % MAIN, LIVE, True, fx()),
    (
        "M2 two pushes to main",
        "git push origin 0914-1:%s && git push origin 0914-1:%s" % (MAIN, MAIN),
        LIVE,
        True,
        fx(),
    ),
    (
        "M2 from a checkout on main",
        "git push origin %s:%s" % (MAIN, MAIN),
        MAIN_REPO,
        True,
        fx(),
    ),
]


def run(command, cwd, extra=None):
    env = dict(os.environ)
    env.update(extra or {})
    if cwd is not None:
        env["CLAUDE_PROJECT_DIR"] = str(cwd)
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for case in CASES:
    name, command, cwd, want = case[:4]
    got, err = run(command, cwd, case[4] if len(case) > 4 else None)
    blocked += got
    ok = got == want
    # A sixth element is text the refusal must carry, for a case whose point is the message.
    if ok and len(case) > 5 and case[5] not in err:
        ok = False
        err = "missing %r in: %s" % (case[5], err)
    fails += not ok
    print(
        "%-72s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])


# ---- the git-level pre-push twin (.claude/rediacc_hooks/git/pre-push) ------------------------
def pushed(repo, *args):
    proc = _git(repo, "push", "-q", *args, check=False)
    return proc.returncode != 0, proc.stderr


GIT_CASES: list[tuple[str, dict[str, typing.Any], tuple[str, ...], bool]] = [
    # (name, fixture kwargs, push args, expect_refused)
    ("git-level: ff of the live branch's pushed tip", {}, ("origin", "0914-1:%s" % MAIN), False),
    ("git-level: ff of origin/<live>", {}, ("origin", "origin/0914-1:%s" % MAIN), False),
    (
        "git-level: a local commit origin never saw",
        {"unpushed": True},
        ("origin", "0914-1:%s" % MAIN),
        True,
    ),
    (
        "git-level: not a fast-forward, forced",
        {"main_moved": True},
        ("--force", "origin", "0914-1:%s" % MAIN),
        True,
    ),
    ("git-level: the delete form", {}, ("origin", ":%s" % MAIN), True),
    (
        "git-level: main beside another ref",
        {},
        ("origin", "0914-1:%s" % MAIN, "0914-1:0914-9"),
        True,
    ),
    ("git-level: from a checkout on main", {"branch": MAIN}, ("origin", "HEAD:%s" % MAIN), True),
]

print()
for name, kwargs, args, want in GIT_CASES:
    if kwargs.get("branch") == MAIN:
        repo = _make_live(hooks=True)
        _git(repo, "checkout", "-q", MAIN)
        # The fixture's own commit on main, past the commit-msg twin with the override (fixture setup, not the push under test).
        _git(
            repo,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "on main",
            env=dict(_FIXTURE_ENV, COMMIT_POLICY_OK="1"),
        )
    else:
        repo = _make_live(hooks=True, **kwargs)
    # The bare origin's HEAD names the live branch, so git's own "refusing to delete the current branch" never answers for the hook.
    bare = _git(repo, "remote", "get-url", "origin").stdout.strip()
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/0914-1")
    got, err = pushed(repo, *args)
    # A refusal counts only when it is the HOOK's: git refusing on its own (a non-fast-forward, a remote rule) proves nothing about pre-push.
    got = got and "commit-policy:" in err
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-72s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])
# A count, not a concatenation: the two case lists carry different tuple shapes.
TOTAL = len(CASES) + len(GIT_CASES)

print()
# ANTI-VACUITY: see the sibling harness. This guard's only control is this file.
if blocked in (0, TOTAL):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (blocked, TOTAL),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (TOTAL, blocked, TOTAL - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
