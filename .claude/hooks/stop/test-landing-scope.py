#!/usr/bin/env python3
"""Controls for the Stop hook per tree (agent/plans/PLAN-two-track-merge-dev.md LT5).

    python3 .claude/hooks/stop/test-landing-scope.py

Two trees of one repository: the main checkout on the development branch and a sibling linked tree on the PR's branch, named by a landing record. Every case runs over real temporary repositories; the PR read (`wl_ci.pr_link`) is a stub answering per branch, and the landing record reaches `wl_prscope.loop_state` through its `landing` seam, since commit_policy's reader is LT1's. Each fire case has a control without the record, which must read exactly as before.

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
T = controls.Controls("landing-scope", floor=45)
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
        dataclasses.replace(dev, role="", landing_branch="", foreign_items=frozenset()),
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
    check("development: a finished draft is not offered the merge", (text, block), ("", False))
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
    lines = [
        '{"ev": "add", "id": "aaaa0001", "at": "2026-11-20T10:00:00Z", "o": "%s", "t": "a", "br": "%s"}'
        % (ME, PR_BRANCH),
        '{"ev": "add", "id": "bbbb0002", "at": "2026-11-20T10:00:01Z", "o": "%s", "t": "b", "br": "%s"}'
        % (ME, DEV_BRANCH),
        '{"ev": "add", "id": "cccc0003", "at": "2026-11-20T10:00:02Z", "o": "%s", "t": "c"}' % ME,
        '{"ev": "update", "id": "aaaa0001", "at": "2026-11-20T10:00:03Z", "br": "%s"}' % DEV_BRANCH,
    ]
    (store / "w.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["WORKLIST_STORE_DIR"] = str(store)
    try:
        got = wl_prscope.item_branches(tmp / "items" / "wl.md", main)
        record = {"path": str(landing), "branch": PR_BRANCH}
        land = loop(wl_prscope, wl_ci, landing, record, {})
        dev = loop(wl_prscope, wl_ci, main, record, {})
    finally:
        del os.environ["WORKLIST_STORE_DIR"]
    check(
        "the add event's branch, never a later event's",
        got,
        {"aaaa0001": PR_BRANCH, "bbbb0002": DEV_BRANCH, "cccc0003": ""},
    )
    check(
        "landing reads the store: the development item is foreign", land.foreign_items, {"bbbb0002"}
    )
    check(
        "development reads the store: the landing item is foreign", dev.foreign_items, {"aaaa0001"}
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
    T.exit()


if __name__ == "__main__":
    main()
