#!/usr/bin/env python3
"""Controls for the Stop hook per tree (agent/plans/PLAN-two-track-merge-dev.md LT5).

    python3 .claude/hooks/stop/test-landing-scope.py

Two trees of one repository: the main checkout on the development branch and a sibling linked tree on the PR's branch, named by a landing record. Every case runs over real temporary repositories; the PR read (`wl_ci.pr_link`) is a stub answering per branch, and the landing record reaches `wl_prscope.loop_state` through its `landing` seam, since commit_policy's reader is LT1's. The real Stop hook then runs over a red CI read from a copy of the hooks whose commit_policy carries a stand-in for that reader. Each fire case has a control without the record, which must read exactly as before.

A landing stop sees only the PR branch's items and no queue; a development stop sees the queue and its draft, parks the draft's CI, review and finish line, and is never offered the merge; on `main` the landing branch is no second live branch; the landing tree is absent from the unlanded-lease survey, and a lease cut in the landing tree is judged against that tree's own HEAD.
"""

import dataclasses
import importlib.util
import os
import pathlib
import subprocess
import sys

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"
sys.path.insert(0, str(_REAL.parent))


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded by file, as test-wl_worktrees.py does."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")
T = controls.Controls("landing-scope", floor=64)
check = T.check

ME = "cafe0000"
SID = ME + "-0000-4000-8000-000000000000"
PR_BRANCH = "1120-1"
DEV_BRANCH = "1120-2"
GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(cwd, *args):
    done = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *map(str, args)],
        cwd=cwd,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit("fixture: git %s: %s" % (" ".join(map(str, args)), done.stderr))
    return done.stdout.strip()


def plan(opened):
    boxes = "- [x] D0 a ticked box sits here\n"
    boxes += "".join("- [ ] O%d an open box sits here\n" % i for i in range(opened))
    return (
        "# PLAN\nStatus: approved\nDepends-On: no-dep -- a standalone fixture plan\n"
        "Priority: P2 -- seed\n\n## Boxes\n%s" % boxes
    )


def rel(name):
    return "agent/plans/PLAN-%s.md" % name


def two_trees(tmp, name, dev_branch=DEV_BRANCH):
    """(main checkout, landing tree): plans pr, q, n (open) and done (finished), q and n promoted; the landing tree holds PR_BRANCH, the main checkout `dev_branch` (stays on main when "")."""
    main = tmp / name / "console"
    (main / "agent" / "plans").mkdir(parents=True)
    git(main, "init", "-q", "-b", "main")
    for plan_name, opened in (("pr", 1), ("q", 1), ("n", 1), ("done", 0)):
        (main / rel(plan_name)).write_text(plan(opened), encoding="utf-8")
    (main / "agent/plans/QUEUE.md").write_text(
        "# Plan queue\n\n## Promoted\n\n1. %s\n2. %s\n" % (rel("q"), rel("n")), encoding="utf-8"
    )
    (main / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "fixture")
    git(main, "branch", PR_BRANCH)
    landing = tmp / name / "console-landing"
    git(main, "worktree", "add", "-q", landing, PR_BRANCH)
    if dev_branch:
        git(main, "switch", "-q", "-c", dev_branch)
    return main, landing


def node(number, body, draft=False):
    return {"number": number, "state": "OPEN", "body": body, "isDraft": draft}


def loop(wl_prscope, wl_ci, tree, record, nodes, branches=None, settings=None, gh=True):
    """`loop_state` for `tree` with the PR read stubbed from `nodes` (branch -> node list)."""
    real = wl_ci.pr_link
    wl_ci.pr_link = lambda _top, _wl, _sid, branch: (list(nodes.get(branch, ())), "")
    try:
        return wl_prscope.loop_state(
            tree,
            tree / "agent" / "worklist.md",
            SID,
            today="1120",
            epics=lambda _rel: (),
            gh=gh,
            settings=settings,
            landing=record,
            branches=branches,
        )
    finally:
        wl_ci.pr_link = real


ITEMS = {"aaaa0001": PR_BRANCH, "bbbb0002": DEV_BRANCH, "cccc0003": "", "dddd0004": "1119-3"}


def control_loop_state(tmp, wl_prscope, wl_ci, wl_checks):
    main, landing = two_trees(tmp, "loop")
    record = {"path": str(landing), "branch": PR_BRANCH}
    nodes = {
        PR_BRANCH: [node(7, "Plan: %s" % rel("pr"))],
        DEV_BRANCH: [node(8, "Plan: %s" % rel("q"), draft=True)],
    }

    # The development tree: the queue and its draft, the landing branch's items out of scope.
    dev = loop(wl_prscope, wl_ci, main, record, nodes, branches=ITEMS)
    check("development: the role", dev.role, wl_prscope.DEVELOPMENT)
    check("development: the draft PR is live", (dev.kind, dev.pr), (wl_prscope.LIVE, 8))
    check("development: the queue head is read", dev.queue_head, rel("q"))
    check("development: the next plan is read", dev.next_plan, rel("n"))
    check("development: the landing branch is named", dev.landing_branch, PR_BRANCH)
    check("development: the landing branch's items are foreign", dev.foreign_items, {"aaaa0001"})
    bare = loop(wl_prscope, wl_ci, main, None, nodes, branches=ITEMS)
    check("CONTROL development, no record: no role", bare.role, "")
    check("CONTROL development, no record: nothing foreign", bare.foreign_items, frozenset())
    check(
        "CONTROL development, no record: every other field is unchanged",
        dataclasses.replace(
            dev, role="", landing_branch="", foreign_items=frozenset(), landing_open=False
        ),
        bare,
    )

    # The landing tree: the PR's babysit and merge loop, no queue, only its own branch's items.
    on = dataclasses.replace(wl_prscope._hooks_pkg()[0].settings_at(str(landing))[0], turbo=True)
    land = loop(wl_prscope, wl_ci, landing, record, nodes, branches=ITEMS, settings=on)
    check("landing: the role", land.role, wl_prscope.LANDING)
    check("landing: the PR is live", (land.kind, land.pr), (wl_prscope.LIVE, 7))
    check("landing: the PR's plan set", land.plans, (rel("pr"),))
    check("landing: no queue head", land.queue_head, "")
    check("landing: no next plan", land.next_plan, "")
    check("landing: turbo is off", land.turbo, False)
    check(
        "landing: every item of another branch is foreign",
        land.foreign_items,
        {"bbbb0002", "dddd0004"},
    )
    # A detached landing tree (mid-rebase, a bisect): its own branch is the record's, so the PR's items stay in scope.
    git(landing, "switch", "-q", "--detach")
    try:
        detached = loop(wl_prscope, wl_ci, landing, record, nodes, branches=ITEMS, settings=on)
    finally:
        git(landing, "switch", "-q", PR_BRANCH)
    check(
        "landing, detached: the PR branch's items stay in scope",
        detached.foreign_items,
        {"bbbb0002", "dddd0004"},
    )
    lbare = loop(wl_prscope, wl_ci, landing, None, nodes, branches=ITEMS, settings=on)
    check("CONTROL landing, no record: the queue head", lbare.queue_head, rel("q"))
    check("CONTROL landing, no record: the next plan", lbare.next_plan, rel("q"))
    check("CONTROL landing, no record: turbo stays on", lbare.turbo, True)
    check("CONTROL landing, no record: nothing foreign", lbare.foreign_items, frozenset())

    # The merge offer: the landing tree's, never the development tree's draft.
    done_nodes = {
        PR_BRANCH: [node(7, "Plan: %s" % rel("done"))],
        DEV_BRANCH: [node(8, "Plan: %s" % rel("done"), draft=True)],
    }
    ddone = loop(wl_prscope, wl_ci, main, record, done_nodes, branches={})
    text, block = wl_checks.loop_next_text(ddone, str(main), {}, False)
    check("development: the landing PR is read open", ddone.landing_open, True)
    check("development: a finished draft is not offered the merge", "/pr-merge here" in text, True)
    check("development: the merge wait does not block", block, False)
    text, block = wl_checks.loop_next_text(
        dataclasses.replace(ddone, role=""), str(main), {}, False
    )
    check("CONTROL no record: a finished PR is offered the merge", block, True)
    ldone = loop(wl_prscope, wl_ci, landing, record, done_nodes, branches={})
    text, block = wl_checks.loop_next_text(ldone, str(landing), {}, False)
    check("landing: a finished PR is offered the merge", block, True)
    check("landing: the merge names its PR", "PR #7's plan set" in text, True)


def control_on_main(tmp, wl_prscope, wl_ci):
    main, landing = two_trees(tmp, "main", dev_branch="")
    record = {"path": str(landing), "branch": PR_BRANCH}
    got = loop(wl_prscope, wl_ci, main, record, {}, branches={}, gh=False)
    check("on main: the landing branch is no second live branch", got.kind, wl_prscope.ON_MAIN)
    check("on main: the development role", got.role, wl_prscope.DEVELOPMENT)
    bare = loop(wl_prscope, wl_ci, main, None, {}, branches={}, gh=False)
    check(
        "CONTROL on main, no record: the PR branch is live elsewhere",
        bare.kind,
        wl_prscope.OFF_LOOP,
    )
    git(main, "branch", "1120-3")
    third = loop(wl_prscope, wl_ci, main, record, {}, branches={}, gh=False)
    check("on main: a third branch is still live", third.kind, wl_prscope.OFF_LOOP)
    check("on main: the third branch is the one named", "1120-3" in third.reason, True)
    check("on main: the landing branch is not named", PR_BRANCH in third.reason, False)


def control_item_branches(tmp, wl_prscope, wl_ci):
    """The default branch reader: each item's add event, the event's own `br`."""
    main, landing = two_trees(tmp, "items")
    store = tmp / "items" / "store"
    store.mkdir()
    import wl_store

    bare = tmp / "items" / "bare"
    bare.mkdir()
    worklist = tmp / "items" / "wl.md"
    prior = os.environ.get("WORKLIST_STORE_DIR")
    os.environ["WORKLIST_STORE_DIR"] = str(store)
    try:
        ids = {
            "a": wl_store.add_item(worklist, ME, "a", root=landing),
            "b": wl_store.add_item(worklist, ME, "b", root=main),
            "c": wl_store.add_item(worklist, ME, "c", root=bare),
        }
        later = '{"ev": "update", "id": "%s", "at": "2999-01-01T00:00:00Z", "br": "%s"}\n'
        (store / "later.jsonl").write_text(later % (ids["a"], DEV_BRANCH), encoding="utf-8")
        got = wl_prscope.item_branches(worklist, main)
        record = {"path": str(landing), "branch": PR_BRANCH}
        land = loop(wl_prscope, wl_ci, landing, record, {})
        dev = loop(wl_prscope, wl_ci, main, record, {})
    finally:
        if prior is None:
            del os.environ["WORKLIST_STORE_DIR"]
        else:
            os.environ["WORKLIST_STORE_DIR"] = prior
    check(
        "the caller's store directory comes back as it was",
        os.environ.get("WORKLIST_STORE_DIR"),
        prior,
    )
    check(
        "the add event's branch, never a later event's",
        got,
        {ids["a"]: PR_BRANCH, ids["b"]: DEV_BRANCH, ids["c"]: ""},
    )
    check(
        "landing reads the store: the development item is foreign",
        land.foreign_items,
        {ids["b"]},
    )
    check(
        "development reads the store: the landing item is foreign",
        dev.foreign_items,
        {ids["a"]},
    )


def control_scope_and_parks(wl_prscope, wl_checks):
    land = wl_prscope.LoopState(
        wl_prscope.LIVE, role=wl_prscope.LANDING, foreign_items=frozenset({"x"})
    )
    dev = wl_prscope.LoopState(wl_prscope.LIVE, role=wl_prscope.DEVELOPMENT)
    bare = wl_prscope.LoopState(wl_prscope.LIVE)
    pred = wl_prscope.with_tree_scope(None, land)
    check("off the loop: a foreign item is out of scope", pred({"id": "x"}), False)
    check("CONTROL off the loop: any other item is in scope", pred({"id": "y"}), True)
    loop_pred = wl_prscope.with_tree_scope(lambda rec: rec["id"] in {"x", "y"}, land)
    check("on the loop: a foreign epic item is out of scope", loop_pred({"id": "x"}), False)
    check("CONTROL on the loop: an epic item stays in scope", loop_pred({"id": "y"}), True)
    check("on the loop: a non-epic item stays out", loop_pred({"id": "z"}), False)
    check(
        "no record: the predicate comes back unchanged",
        wl_prscope.with_tree_scope(None, bare),
        None,
    )

    check("landing parks the queue's arms", wl_prscope.tree_parks(land), wl_prscope.LANDING_PARKS)
    check(
        "development parks the draft's arms",
        wl_prscope.tree_parks(dev),
        wl_prscope.DEVELOPMENT_PARKS,
    )
    check("CONTROL no record parks nothing", wl_prscope.tree_parks(bare), frozenset())
    check(
        "CONTROL a focus parks nothing",
        wl_prscope.tree_parks(dev, {"mode": "babysit"}),
        frozenset(),
    )
    check("development parks ci-red", "ci-red" in wl_prscope.DEVELOPMENT_PARKS, True)
    check("landing parks turbo-next", "turbo-next" in wl_prscope.LANDING_PARKS, True)

    advised = []
    violations = [
        ("pr-review", False, "answer the review"),
        ("pr-finish", True, "THIS IS A HOOK BUG"),
        ("open-items", False, "open"),
    ]
    kept = wl_checks.park_tree_keys(
        violations,
        wl_prscope.tree_parks(dev),
        dev.role,
        lambda key, text: advised.append((key, text)),
    )
    check(
        "a parked finding leaves the violations",
        [k for k, _a, _t in kept],
        ["pr-finish", "open-items"],
    )
    check(
        "a parked finding rides the advisory queue under its key",
        [k for k, _t in advised],
        ["pr-review"],
    )
    check("the advisory says which tree parked it", "development tree parks" in advised[0][1], True)
    check(
        "the advisory keeps the finding's text", advised[0][1].endswith("answer the review"), True
    )
    check(
        "CONTROL no parks: the violations come back as they were",
        wl_checks.park_tree_keys(violations, frozenset(), "", lambda *_a: advised.append(_a)),
        violations,
    )
    check("CONTROL no parks: nothing is advised", len(advised), 1)


def control_worktrees(tmp, wl_worktrees):
    main, landing = two_trees(tmp, "leases")
    nobody = {"ids": set(), "trees": set(), "cwd": "", "prompts": []}

    def lease(holder, lease_id):
        path = holder / ".claude" / "worktrees" / lease_id
        path.parent.mkdir(parents=True, exist_ok=True)
        git(holder, "worktree", "add", "-q", "--detach", path, "HEAD")
        store = pathlib.Path(git(main, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        (store / "rediacc-worktrees").mkdir(exist_ok=True)
        (store / "rediacc-worktrees" / ("%s.json" % lease_id)).write_text(
            '{"id": "%s", "path": "%s", "owner": "%s", "agent": "", "base": {}, "created_at": "2026-11-20T10:00:00Z"}'
            % (lease_id, path, ME),
            encoding="utf-8",
        )
        return path

    def commit(tree, name):
        (tree / name).write_text(name + "\n", encoding="utf-8")
        git(tree, "add", "--", name)
        git(tree, "commit", "-q", "-m", name)
        return git(tree, "rev-parse", "HEAD")

    dev_lease = lease(main, "devlease")
    commit(dev_lease, "d.txt")
    got = wl_worktrees.survey(main, SID, [], lambda: nobody, {})
    listed = {row["id"] for row in got["unlanded"]} | set(got["held"]) | set(got["unknown"])
    listed |= {row["id"] for row in got["peers"]} | {lid for lid, _why in got["orphans"]}
    check(
        "development survey: its own lease is unlanded",
        [r["id"] for r in got["unlanded"]],
        ["devlease"],
    )
    check("development survey: the landing tree is nowhere", "console-landing" in str(got), False)
    check("development survey: nothing else is listed", listed, {"devlease"})

    land_lease = lease(landing, "landlease")
    sha = commit(land_lease, "l.txt")
    got = wl_worktrees.survey(landing, SID, [], lambda: nobody, {})
    check(
        "landing survey: its lease is unlanded before the pick",
        [r["id"] for r in got["unlanded"]],
        ["landlease"],
    )
    check("landing survey: the development lease is not its own", "devlease" in str(got), False)
    # A pick without -x: only `git cherry` against the landing tree's own HEAD can read it landed.
    git(landing, "cherry-pick", sha)
    got = wl_worktrees.survey(landing, SID, [], lambda: nobody, {})
    check(
        "landing survey: a lease picked onto the landing branch reads landed", got["unlanded"], []
    )
    got = wl_worktrees.survey(main, SID, [], lambda: nobody, {})
    check(
        "CONTROL development survey: the development lease still reads unlanded",
        [r["id"] for r in got["unlanded"]],
        ["devlease"],
    )


# The real hook's CI read, as test_wl_ci_status.py serves it (that module imports pytest; this file runs under a bare python3).
GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""
CI_FRESH = (
    '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,'
    '"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}\n'
)
CI_JOB = '{"run_id":30514648812,"run_attempt":1,"steps":[{"name":"Shell format","conclusion":"failure"}]}\n'
CI_RED = (
    '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"url":"u",'
    '"commits":{"nodes":[{"commit":{"oid":"deadsha0000","statusCheckRollup":'
    '{"state":"FAILURE","contexts":{"totalCount":1,"pageInfo":{"hasNextPage":false,'
    '"endCursor":null},"nodes":[{"__typename":"CheckRun","name":"Quality / Static",'
    '"status":"COMPLETED","conclusion":"FAILURE","databaseId":90784763855,'
    '"detailsUrl":"https://x/job/90784763855","checkSuite":{"workflowRun":'
    '{"databaseId":30514648812}}}]}}}}]}}]}}}}\n'
)
# LT1's reader, planted in the hook copy's commit_policy until LT1 lands: the record in the common git dir.
LANDING_STAND_IN = '''

def landing_record(repo_root):
    """Stand-in for LT1 (test-landing-scope.py): the common git dir's rediacc-landing.json."""
    import json as _json

    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo_root)
    try:
        with open(os.path.join(common or "", "rediacc-landing.json"), encoding="utf-8") as fh:
            return _json.load(fh)
    except (OSError, ValueError):
        return None
'''


def control_real_hook(tmp):
    """The real Stop hook with CI red on the PR: the development tree reports it, the landing tree and a checkout with no record block on it."""
    import json
    import shutil

    sys.path[:0] = [str(_CI.parent), str(_REAL.parents[2])]
    from rediacc_hooks.tests import wlfix

    fix = wlfix.Fixture(tmp / "hookfix")
    fix.setup()
    fix.brief_now()
    hooks = fix.base / "claude" / "hooks"
    junk = shutil.ignore_patterns("__pycache__", "state")
    shutil.copytree(wlfix.STOP_DIR, hooks / "stop", ignore=junk)
    shutil.copytree(wlfix.STOP_DIR.parent / "context", hooks / "context", ignore=junk)
    shutil.copytree(
        wlfix.STOP_DIR.parents[1] / "rediacc_hooks", hooks.parent / "rediacc_hooks", ignore=junk
    )
    policy = hooks.parent / "rediacc_hooks" / "commit_policy.py"
    if "def landing_record(" not in policy.read_text(encoding="utf-8"):
        with policy.open("a", encoding="utf-8") as fh:
            fh.write(LANDING_STAND_IN)
    (hooks.parents[1] / ".ci").symlink_to(wlfix.STOP_DIR.parents[2] / ".ci")
    fix.hook = hooks / "stop" / "worklist.py"

    fix.git("init", "-q", "-b", "main")
    fix.git("config", "user.email", "t@t")
    fix.git("config", "user.name", "t")
    fix.git("remote", "add", "origin", wlfix.FAKE_ORIGIN)
    (fix.proj / "a.txt").write_text("a\n", encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "base")
    fix.git("update-ref", "refs/remotes/origin/pub", fix.git("rev-parse", "HEAD").stdout.strip())
    (fix.base / "ci-fresh.json").write_text(CI_FRESH, encoding="utf-8")
    (fix.base / "ci-job.json").write_text(CI_JOB, encoding="utf-8")
    (fix.base / "ci-rollup.json").write_text(CI_RED, encoding="utf-8")
    shim = fix.base / "binonly" / "gh"
    shim.write_text(GH_SHIM % {"base": fix.base}, encoding="utf-8")
    shim.chmod(0o755)
    record = fix.proj / ".git" / "rediacc-landing.json"
    # A real linked tree on the PR branch: commit_policy's reader (LT1) binds only an existing tree of this repository at its realpath.
    landing = pathlib.Path(os.path.realpath(fix.base)) / "console-landing"
    added = fix.git("worktree", "add", "-q", "-b", PR_BRANCH, str(landing))
    if added.returncode != 0:
        raise SystemExit("fixture: the landing tree: %s" % added.stderr)

    def stop(landing_path, tree=None):
        tree = tree or fix.proj
        if landing_path is None:
            record.unlink(missing_ok=True)
        else:
            record.write_text(json.dumps({"path": str(landing_path), "branch": PR_BRANCH}), "utf-8")
        fix.stem(".cistate-deadbeef").unlink(missing_ok=True)
        payload = json.dumps(
            {
                "session_id": fix.sid,
                "cwd": str(tree),
                "last_assistant_message": "working\n\n## Remaining\n- nothing",
                "session_crons": [],
                "background_tasks": wlfix.with_waker([], fix.waker),
            }
        )
        env = dict(fix.env)
        env.update(
            PATH="%s:%s" % (fix.base / "binonly", fix.env.get("PATH", "")),
            TMPDIR=str(fix.base / "tmp"),
            CLAUDE_PROJECT_DIR=str(tree),
            WORKLIST_TASKS_DIR=str(fix.base / "tasks"),
            WORKLIST_PUBLISH_REF="pub",
            WORKLIST_JUDGE="off",
            GITHUB_ACTIONS="",
        )
        return fix.python([], stdin=payload, env=env)

    red = "CI IS RED ON PR #543"
    got = stop(None)
    check("CONTROL no record: the red blocks", (red in got.out, got.decision), (True, "block"))
    got = stop(landing)
    check("development: the draft's red is no block", red in got.out, False)
    check(
        "development: the draft's red is reported",
        "this is the development tree's draft PR" in got.out,
        True,
    )
    got = stop(landing, landing)
    check("landing: the PR's red blocks", (red in got.out, got.decision), (True, "block"))

    # An open item added on the landing branch, CI green: it blocks only where it is in scope.
    (fix.base / "ci-rollup.json").write_text(
        CI_RED.replace('"FAILURE"', '"SUCCESS"'), encoding="utf-8"
    )
    probe = "LT5 scope probe on the landing branch (deadbeef)"
    import wl_store

    fix.store_dir.mkdir(parents=True, exist_ok=True)
    prior_store = os.environ.get("WORKLIST_STORE_DIR")
    os.environ["WORKLIST_STORE_DIR"] = str(fix.store_dir)
    try:
        wl_store.add_item(fix.wl, "deadbeef", probe, root=landing)
    finally:
        if prior_store is None:
            del os.environ["WORKLIST_STORE_DIR"]
        else:
            os.environ["WORKLIST_STORE_DIR"] = prior_store
    got = stop(None)
    check("CONTROL no record: the item blocks", (probe in got.out, got.decision), (True, "block"))
    got = stop(landing)
    check("development: the landing branch's item is not shown", probe in got.out, False)
    check("development: the landing branch's item does not block", got.decision, "allow")

    # A live pr-babysit round log on a green PR whose threads box is unticked: the finish line.
    projects = fix.base / "projects"
    (projects / "reports").mkdir(parents=True)
    (projects / "reports" / "pr-babysit-agenttest.md").write_text("# round\n", encoding="utf-8")
    fix.env["WORKLIST_PROJECTS_DIR"] = str(projects)
    finish = "THE WAVE IS NOT FINISHED"
    got = stop(landing, landing)
    check("landing: the finish line blocks", (finish in got.out, got.decision), (True, "block"))
    got = stop(landing)
    check("development: the finish line does not block", got.decision, "allow")


def main():
    tmp = pathlib.Path(runtmp.run_dir("landing-scope-")).resolve()
    import wl_checks
    import wl_ci
    import wl_prscope
    import wl_worktrees

    control_loop_state(tmp, wl_prscope, wl_ci, wl_checks)
    control_on_main(tmp, wl_prscope, wl_ci)
    control_item_branches(tmp, wl_prscope, wl_ci)
    control_scope_and_parks(wl_prscope, wl_checks)
    control_worktrees(tmp, wl_worktrees)
    control_real_hook(tmp)
    T.exit()


if __name__ == "__main__":
    main()
