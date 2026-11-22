"""wl_prscope: where the one-plan-per-PR loop stands, computed once per stop (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 1, box SC2).

THE RULING. The Stop hook blocks only on the live PR's plan set, that PR's CI and reviews, the worklist items attached to that set's epics, and the loop's own duties (operator ruling 2026-10-03). Everything else is one queued line. After the PR merges, the hook holds the turn until the next branch, plan and PR exist. `loop_state` answers the questions both halves need: which PR, which plans, which items, what comes next.

ONE READER EACH. The PR is read once, through `wl_ci.pr_link` (the read focus mode also ends on). The plan set is `plan_gate.pr_plan_set`, the function the merge gate and P-A1 call, so the hook, CI and the merge cannot disagree about which plans a PR owns (ruling 7: the PR's `Plan:` plans plus every unfinished plan they depend on, prerequisites first). The queue is `plan_gate.queue`, the branch rules are `commit_policy`'s. The epic-to-plan link is `wl_epic.plan_epics` (box SC3), imported lazily; a `wl_epic` that does not carry it yet reads as no items.

KINDS. `live` (an MMDD-N branch with an OPEN PR), `no-pr` (such a branch, no PR yet, or only closed ones), `merged` (its newest PR MERGED, none open), `on-main` (main, no live branch), `off-loop` (any other branch, detached HEAD, a submodule, or not a git checkout), `unreadable` (the PR read failed; the plans fall back to the queue head's set, so item scope survives a gh outage).

TWO TREES (agent/plans/PLAN-two-track-merge-dev.md LT5). With a landing record (`commit_policy.landing_record`, LT1: `{path, branch}` in the common git dir) the checkout is one of two trees, each holding its own live MMDD-N branch. The tree at the record's path is `landing`: it works the open PR's babysit and merge loop, so the queue is not read there (no queue head, no next plan, no next branch), and its item scope is the items added on its own branch plus the items that carry no branch. Every other tree of the repository is `development`: it works the queue and the draft PR, the record's branch never counts as a second live branch on `main`, and the items added on the landing branch are out of its scope. `tree_parks` names the checks each tree reports instead of blocking on. Without a record `role` is "", nothing is excluded or parked, and every other field is what it was.

THE LANDING STATE MACHINE (agent/plans/PLAN-simple-two-tree-loop.md D1, box B2). In the landing tree `landing_loop` reads one of seven states from the world on every stop -- L-CI (the PR's checks in flight), L-FIX (a required check red), L-REVIEW (CI Complete SUCCESS, boxes or reviews still open), L-MERGE (all clear), L-RELEASE (merged, the release at the merged sha in flight), L-HOTFIX (that release red on main), L-IDLE (no open PR, or a merged PR whose release is green) -- and names one step; L-IDLE blocks on nothing. The PR is read on the record's branch, so a detached HEAD on origin/main during a hotfix still finds the merged PR. The release is Console CI and CD - Release to Edge at the merged sha (`read_release`, gh run list). The development tree reads the same release (`landing_released`): a merged landing PR with a green release is its cue to promote. No event stores the state, so a restart resumes where the world is.

`today` is the MMDD the next branch is named for. It defaults to LOCAL time, the clock `block_second_branch` names branches with, so the name printed here is the one that guard admits.

Reads no environment variable of its own; gh is reached through `wl_ci`, `commit_policy` and, for the merge and release reads, `wl_gh.call`.
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib.util
import pathlib
from typing import Any


def _hooks_pkg():
    """(plan_gate, commit_policy) from `.claude/rediacc_hooks`, reached through the canonical sys.path hop (`.claude/rediacc_hooks/syspath.py`), loaded by file because this module lives outside that package."""
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % helper)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import commit_policy, plan_gate

    return plan_gate, commit_policy


LANDING = "landing"
DEVELOPMENT = "development"
# The checks a tree reports instead of blocking on (`tree_parks`): the queue's arms in the landing tree, the PR's babysit arms in the development tree. wl_checks holds `ci-red` before its block budget is spent (wl_ci.ci_trouble `hold`) and moves the others to the advisory queue under their own key.
LANDING_PARKS = frozenset({"idle-capacity", "queue-slot"})
DEVELOPMENT_PARKS = frozenset({"ci-red", "pr-review", "pr-finish"})
TREE_PARK_NOTE = (
    "Reported, not blocking: the %s tree parks `%s` (agent/plans/PLAN-two-track-merge-dev.md LT5)."
)
DRAFT_CI_NOTE = (
    "CI on PR #%s is red on %d job(s): %s. Reported, not blocking: this is the development "
    "tree's draft PR, and the landing tree's stop babysits the PR being landed."
)
# `loop_state`'s `landing` default: read the record through commit_policy.
_READ = object()

LIVE = "live"
NO_PR = "no-pr"
MERGED = "merged"
ON_MAIN = "on-main"
OFF_LOOP = "off-loop"
UNREADABLE = "unreadable"
KINDS = (LIVE, NO_PR, MERGED, ON_MAIN, OFF_LOOP, UNREADABLE)


@dataclasses.dataclass(frozen=True)
class LoopState:
    """Where the loop stands. `plans` is ordered prerequisites first; `prereqs` names the members that are not the PR's own `Plan:` plans; `stale_promoted` is the queue head's path when it has no open box left (a finished Promoted entry nobody removed), else "". `role` is `landing`, `development` or "" (no landing record), `landing_branch` the record's branch, `foreign_items` the item ids outside this tree's scope (see TWO TREES), `landing_open` True in the development tree while the landing branch's PR is open, and `landing_released` the landing PR's number in the development tree once that PR is merged and its release is fully green (D3: the cue to promote), else 0."""

    kind: str
    branch: str = ""
    pr: int = 0
    plans: tuple[str, ...] = ()
    prereqs: tuple[str, ...] = ()
    epic_items: frozenset[str] = frozenset()
    next_plan: str = ""
    queue_head: str = ""
    stale_promoted: str = ""
    next_branch: str = ""
    reason: str = ""
    role: str = ""
    landing_branch: str = ""
    foreign_items: frozenset[str] = frozenset()
    landing_open: bool = False
    landing_released: int = 0


def _plan_epics(rel):
    import wl_epic

    return wl_epic.plan_epics(rel)


def epic_items(plans, epics=None):
    """The union of the item ids of every epic whose `plan` is in `plans`. `epics` overrides the reader (rel -> ids); the default is `wl_epic.plan_epics`, and a wl_epic without it yields nothing."""
    reader = epics or _plan_epics
    out = set()
    for rel in plans:
        try:
            out |= set(reader(rel) or ())
        except AttributeError:
            return frozenset()
    return frozenset(out)


def _open_count(plan_gate, root, rel):
    opened, _done, why = plan_gate.open_boxes(str(root), rel)
    return -1 if why else opened


def next_queued(root, exclude=()):
    """(rel, problem): the plan the loop starts next. The first `plan_gate.queue` entry that exists, is not in `exclude` and has an open box, replaced by its deepest unfinished prerequisite when it has one (so the loop never starts a plan whose dependency is open); "" when the queue holds none. `problem` carries a cycle or an unresolvable dependency of the chosen entry."""
    plan_gate, _cp = _hooks_pkg()
    root = str(root)
    skip = set(exclude)
    for rel in plan_gate.queue(root):
        if rel in skip or not (pathlib.Path(root) / rel).is_file():
            continue
        if _open_count(plan_gate, root, rel) <= 0:
            continue
        members, problems = plan_gate.pr_plan_set(root, "Plan: %s" % rel)
        pick = next((m for m in members if m not in skip), rel)
        return pick, "; ".join(problems)
    return "", ""


def landing_record(commit_policy, top):
    """The landing record `{path, branch}` of `top`'s repository, or None. None also while commit_policy carries no `landing_record` (LT1 not landed), which keeps every tree on today's behaviour."""
    reader = getattr(commit_policy, "landing_record", None)
    if reader is None:
        return None
    got = reader(str(top))
    return got if isinstance(got, dict) and got.get("path") else None


def tree_role(record, top):
    """`landing` when `top` is the record's tree, `development` for any other tree of a repository with a record, "" without one. Compared on resolved paths."""
    if not record:
        return ""
    same = pathlib.Path(str(record["path"])).resolve() == pathlib.Path(str(top)).resolve()
    return LANDING if same else DEVELOPMENT


def item_branches(worklist, root):
    """{item id: the branch its `add` event was written on}, "" for an add that carries none. An item only the markdown mirror holds has no add event and is absent."""
    import wl_store

    out = {}
    for ev in wl_store._read_events(worklist, root):
        if ev.get("ev") == "add" and ev.get("id"):
            out[str(ev["id"])] = str(ev.get("br") or "")
    return out


def foreign_items(role, branch, landing_branch, branches):
    """The item ids outside this tree's scope. Landing: every item added on a branch other than its own, the record's `landing_branch` (HEAD's `branch` only when the record names none). Development: every item added on `landing_branch`. No role: none. An item with no branch stays in scope in both trees. The stored branch is wl_core.git_branch's slug, which equals the name for an MMDD-N branch."""
    if role == LANDING:
        # The record names the landing tree's branch; HEAD's name is "" on a detached HEAD, which would make the PR's own items foreign.
        own = landing_branch or branch
        return frozenset(i for i, b in branches.items() if b and b != own)
    if role == DEVELOPMENT and landing_branch:
        return frozenset(i for i, b in branches.items() if b == landing_branch)
    return frozenset()


def with_tree_scope(in_scope, state):
    """The stop's item predicate with `state`'s foreign items taken out. `in_scope` is the loop's predicate or None (everything in scope); it comes back unchanged when the tree excludes nothing."""
    foreign = getattr(state, "foreign_items", None) or frozenset()
    if not foreign:
        return in_scope
    if in_scope is None:
        return lambda rec: rec["id"] not in foreign
    return lambda rec: rec["id"] not in foreign and in_scope(rec)


def tree_parks(state):
    """The check keys this tree reports instead of blocking on: LANDING_PARKS in the landing tree, DEVELOPMENT_PARKS in the development tree, none without a record. The tree role alone decides (agent/plans/PLAN-simple-two-tree-loop.md B2): a `--phase` declaration no longer overrides it, since the landing tree is the one that lands the PR."""
    role = getattr(state, "role", "") if state is not None else ""
    if not role:
        return frozenset()
    return LANDING_PARKS if role == LANDING else DEVELOPMENT_PARKS


# ---- THE LANDING STATE MACHINE (agent/plans/PLAN-simple-two-tree-loop.md D1, box B2) ----
# The landing tree's stop reads one state from the world (the landing PR, its checks, the merge, main's workflow runs) and names the one next step. No event stores the state, so a restart resumes where the world is.
L_CI = "L-CI"
L_FIX = "L-FIX"
L_REVIEW = "L-REVIEW"
L_MERGE = "L-MERGE"
L_RELEASE = "L-RELEASE"
L_HOTFIX = "L-HOTFIX"
L_IDLE = "L-IDLE"
LANDING_STATES = (L_CI, L_FIX, L_REVIEW, L_MERGE, L_RELEASE, L_HOTFIX, L_IDLE)
# The PR head's CI verdict, as `landing_step` reads it: CI Complete SUCCESS, a required check red, anything else (in flight, not registered yet, or unreadable).
CI_GREEN = "green"
CI_RED = "red"
CI_PENDING = "pending"
# The two workflows whose runs at the merged sha make the release (D3): Console CI on main and the edge deploy.
RELEASE_WORKFLOWS = (("Console CI", "ci.yml"), ("CD - Release to Edge", "cd-release-edge.yml"))
RUN_RED = frozenset({"failure", "timed_out", "cancelled", "startup_failure", "action_required"})
# How many recent main runs of each workflow are read: the merged sha's run and any hotfix run after it sit in the newest few.
RELEASE_RUNS = 20

LANDING_STEP_TEXT = {
    L_CI: (
        "LANDING %(state)s: PR #%(pr)s's checks are in flight on its head. Watch them through the "
        "ci-watch skill (one `ci-trace.py --wait --until-final` shell), never a hand-rolled gh loop."
    ),
    L_FIX: (
        "LANDING %(state)s: a required check of PR #%(pr)s is red%(detail)s. Diagnose it through "
        "the ci-watch skill, fix it in this tree (the freeze admits `fix` commits, and a writer's "
        "brief carries `focus-fix:#<id>` for an item with `pr:%(pr)s`), push, and stop. The "
        "long-red rules (agent/plans/PLAN-simple-two-tree-loop.md D4) run here."
    ),
    L_REVIEW: (
        "LANDING %(state)s: CI Complete is SUCCESS on PR #%(pr)s's head. Clear what the merge "
        "still waits on: per-commit reviews clean (`worklist.py --review-run <me>`, "
        "`wl_review.py --check` rc 0), the PR review answered with wl_prreview.py, its threads "
        "resolved, and every plan box ticked%(detail)s. The open live boxes (bench, hostinger, VM) "
        "run in this tree before the merge."
    ),
    L_MERGE: (
        "LANDING %(state)s: every box of PR #%(pr)s's plan set is ticked, CI Complete is SUCCESS "
        "and the reviews are clean. Merge it, submodule PRs first, then the console PR:\n"
        "    gh pr merge %(pr)s --rebase --auto"
    ),
    L_RELEASE: (
        "LANDING %(state)s: PR #%(pr)s merged at %(sha)s. Watch the release at that sha through "
        "the ci-watch skill: Console CI on main and CD - Release to Edge%(detail)s. A main-only "
        "red there is a hotfix in this tree; a green release is the development session's cue to "
        "promote."
    ),
    L_HOTFIX: (
        "LANDING %(state)s: PR #%(pr)s merged at %(sha)s and the release is red on main"
        "%(detail)s. Hotfix in this tree on main:\n"
        "    git switch --detach origin/main\n"
        "then a commit whose subject ends in `[hotfix]`, with a `Hotfix-Evidence:` trailer naming "
        "the red run and at most 5 files. The operator pushes main "
        "(`! COMMIT_POLICY_OK=1 git push origin main`); the stop then watches the release again."
    ),
    L_IDLE: (
        "LANDING %(state)s: no landing PR is open%(detail)s. Nothing blocks; the next PR opens when "
        "the development session promotes (`./run.sh worktree landing --promote`)."
    ),
}
LANDING_UNREADABLE = (
    "LANDING: the landing state could not be read (%s). Reported, not blocking: the next stop "
    "reads again."
)


@dataclasses.dataclass(frozen=True)
class LandingStep:
    """One landing stop's reading: `state` is one of LANDING_STATES ("" when the world could not be read), `text` the one step it names, `blocks` False only for L-IDLE and an unreadable world. `release` is True when the merged PR's release is fully green (L-IDLE after a merge), which is when the development session is told `cd-done`."""

    state: str
    text: str
    blocks: bool
    pr: int = 0
    sha: str = ""
    release: bool = False


def _run_verdict(run):
    """`green`, `red` or `pending` for one `gh run list` row."""
    if str(run.get("status") or "").lower() != "completed":
        return CI_PENDING
    conclusion = str(run.get("conclusion") or "").lower()
    if conclusion == "success":
        return CI_GREEN
    return CI_RED if conclusion in RUN_RED else CI_PENDING


def release_verdict(runs_by_workflow, sha):
    """(verdict, detail) of the release at merged `sha`: `green` when every RELEASE_WORKFLOWS run reads success, `red` when any reads red, else `pending`. `runs_by_workflow` maps a workflow name to its main runs, newest first. A run of that workflow created after the merged sha's run (a hotfix on main) supersedes it, so a fixed main reads green again; without a run at `sha` or after it the workflow is pending."""
    verdicts: list[tuple[str, str, dict[str, Any] | None]] = []
    for name, _file in RELEASE_WORKFLOWS:
        runs = [r for r in (runs_by_workflow.get(name) or []) if isinstance(r, dict)]
        at = [r for r in runs if str(r.get("headSha") or "") == sha]
        if not at:
            verdicts.append((name, CI_PENDING, None))
            continue
        merged_at = str(at[-1].get("createdAt") or "")
        newest = runs[0] if str(runs[0].get("createdAt") or "") >= merged_at else at[0]
        verdicts.append((name, _run_verdict(newest), newest))
    reds = [(n, r) for n, v, r in verdicts if v == CI_RED and r is not None]
    if reds:
        detail = ", ".join(
            "%s run %s (%s)" % (n, r.get("databaseId") or "?", r.get("conclusion") or "red")
            for n, r in reds
        )
        return CI_RED, detail
    pend = [n for n, v, _r in verdicts if v != CI_GREEN]
    if pend:
        return CI_PENDING, "still waiting on " + ", ".join(pend)
    return CI_GREEN, ""


def _gh_call(argv, cwd):
    import wl_gh

    return wl_gh.call(argv, cwd=cwd)


def read_release(top, sha, gh=None):
    """(verdict, detail, error) of the release at `sha`, read through `gh` (`wl_gh.call`'s shape: argv -> (data, error)); error is "" on a good read."""
    call = gh or _gh_call
    runs = {}
    for name, wf in RELEASE_WORKFLOWS:
        data, err = call(
            [
                "run",
                "list",
                "--branch",
                "main",
                "--workflow",
                wf,
                "--limit",
                str(RELEASE_RUNS),
                "--json",
                "databaseId,headSha,status,conclusion,createdAt",
            ],
            str(top),
        )
        if err or not isinstance(data, list):
            return "", "", err or "`gh run list --workflow %s` answered no list" % wf
        runs[name] = data
    verdict, detail = release_verdict(runs, sha)
    return verdict, detail, ""


def merged_sha(top, pr, gh=None):
    """(sha, error): the commit main carries for merged PR `pr` (`mergeCommit.oid`; for a rebase merge, the last rebased commit)."""
    call = gh or _gh_call
    data, err = call(["pr", "view", str(pr), "--json", "mergeCommit"], str(top))
    if err:
        return "", err
    oid = str(((data or {}).get("mergeCommit") or {}).get("oid") or "")
    return (oid, "") if oid else ("", "PR #%s carries no mergeCommit" % pr)


def landing_step(pr_state, pr, ci, boxes_open, reviews_clean, release="", sha="", detail=""):
    """The D1 state and its step, from facts already read. `pr_state` is the landing PR's state (OPEN, MERGED, or "" for none); `ci` CI_GREEN / CI_RED / CI_PENDING for its head; `boxes_open` the plan set's open box count (-1 unreadable); `reviews_clean` True when no per-commit or PR review finding holds the merge; `release` the merged sha's release verdict. Pure: every gh read happens before it."""

    def step(state, blocks=True, release_green=False, more=""):
        fields = {"state": state, "pr": pr, "sha": (sha or "?")[:12], "detail": more}
        return LandingStep(state, LANDING_STEP_TEXT[state] % fields, blocks, pr, sha, release_green)

    if pr_state == "OPEN":
        if ci == CI_RED:
            return step(L_FIX, more=": %s" % detail if detail else "")
        if ci != CI_GREEN:
            return step(L_CI)
        if boxes_open != 0 or not reviews_clean:
            more = " (%d open box(es))" % boxes_open if boxes_open > 0 else ""
            return step(L_REVIEW, more=more)
        return step(L_MERGE)
    if pr_state == "MERGED":
        if release == CI_RED:
            return step(L_HOTFIX, more=": %s" % detail if detail else "")
        if release != CI_GREEN:
            return step(L_RELEASE, more=" (%s)" % detail if detail else "")
        return step(
            L_IDLE,
            blocks=False,
            release_green=True,
            more=" (PR #%s merged and its release at %s is green)" % (pr, (sha or "?")[:12]),
        )
    return step(L_IDLE, blocks=False)


def landing_pr(nodes):
    """(state, number, body) of the landing branch's PR from `wl_ci.pr_link` nodes: an OPEN one first, else the newest MERGED, else ("", 0, "")."""
    by_state: dict[str, dict] = {}
    for n in nodes or ():
        by_state.setdefault(str(n.get("state") or "").upper(), n)
    for st in ("OPEN", "MERGED"):
        if st in by_state:
            n = by_state[st]
            return st, int(n.get("number") or 0), str(n.get("body") or "")
    return "", 0, ""


def landing_loop(top, nodes, ci, reviews_clean, boxes_open=None, gh=None, ci_detail=""):
    """The LandingStep for the landing tree at `top`. `nodes` are the landing branch's PR nodes (`wl_ci.pr_link`, read on the record's branch so a detached hotfix HEAD still finds the merged PR); `ci` the stop's own verdict for the open PR's head; `boxes_open` the plan set's open box count, None to read it from the PR body's plan set; `gh` the `wl_gh.call` seam for the merge and release reads. Never raises: a failed read is an unreadable, non-blocking step."""
    try:
        pr_state, pr, body = landing_pr(nodes)
        if pr_state == "OPEN":
            if boxes_open is None:
                plan_gate, _cp = _hooks_pkg()
                plans, _problems = plan_gate.pr_plan_set(str(top), body)
                counts = [_open_count(plan_gate, top, rel) for rel in plans]
                boxes_open = -1 if any(c < 0 for c in counts) else sum(counts)
            return landing_step(pr_state, pr, ci, boxes_open, reviews_clean, detail=ci_detail)
        if pr_state == "MERGED":
            sha, err = merged_sha(top, pr, gh)
            if err:
                return LandingStep("", LANDING_UNREADABLE % err, False, pr)
            verdict, detail, err = read_release(top, sha, gh)
            if err:
                return LandingStep("", LANDING_UNREADABLE % err, False, pr, sha)
            return landing_step(pr_state, pr, ci, 0, True, verdict, sha, detail)
        return landing_step("", 0, ci, 0, True)
    except Exception as exc:
        return LandingStep("", LANDING_UNREADABLE % ("%s: %s" % (type(exc).__name__, exc)), False)


def landing_pr_open(wl_ci, top, worklist, session_id, landing_branch):
    """True when the landing branch's PR is open, read through the same `wl_ci.pr_link` as the tree's own PR; a failed read or no branch answers False (the development tree then reads today's finish text)."""
    return landing_pr(_landing_nodes(wl_ci, top, worklist, session_id, landing_branch))[0] == "OPEN"


def _landing_nodes(wl_ci, top, worklist, session_id, landing_branch):
    """The landing branch's PR nodes through `wl_ci.pr_link`, [] on a failed read or no branch."""
    if not landing_branch:
        return []
    nodes, err = wl_ci.pr_link(top, worklist, session_id, landing_branch)
    return [] if err else list(nodes or [])


# `landing_released` when the merged sha or its release could not be read from gh (negative, so `> 0` is False: it reads as not released, and callers test `== UNREADABLE_RELEASE` to name the unreadable case).
UNREADABLE_RELEASE = -1


def landing_released(top, nodes, gh=None):
    """The landing PR's number once it is MERGED (and none is open) and its release at the merged sha is fully green (D3), else 0. Read from the development tree, which promotes; a failed read answers `UNREADABLE_RELEASE` (-1), which is not `> 0`, so promote is never named on a guess and the caller can still tell it from 0."""
    state, pr, _body = landing_pr(nodes)
    if state != "MERGED":
        return 0
    sha, err = merged_sha(top, pr, gh)
    if err:
        return UNREADABLE_RELEASE
    verdict, _detail, err = read_release(top, sha, gh)
    if err:
        # An unreadable release is not a pending one (review a77a0f9e.1): the caller names it instead of reading it as "not released yet".
        return UNREADABLE_RELEASE
    return pr if verdict == CI_GREEN else 0


def _console_top(commit_policy, root):
    top = commit_policy.toplevel(str(root))
    if not top or commit_policy.superproject(top):
        return ""
    return top


def loop_state(
    root,
    worklist,
    session_id,
    today=None,
    epics=None,
    gh=True,
    landing=_READ,
    branches=None,
):
    """The `LoopState` for the checkout at `root`. `today` (MMDD) and `epics` (rel -> item ids) are the test seams; `gh=False` skips the next-branch name's PR-head read. `landing` (the record, or None) and `branches` (item id -> branch) are the two-tree seams: by default the record is read through commit_policy, and the branches from the worklist's add events only when a record exists."""
    import wl_ci

    plan_gate, commit_policy = _hooks_pkg()
    top = _console_top(commit_policy, root)
    if not top:
        return LoopState(OFF_LOOP, reason="not a console checkout")
    record = landing_record(commit_policy, top) if landing is _READ else landing
    role = tree_role(record, top)
    landing_branch = str((record or {}).get("branch") or "")
    branch = commit_policy.current_branch(top)
    tree: dict = {}
    if role:
        if branches is None:
            branches = item_branches(worklist, top)
        nodes = (
            _landing_nodes(wl_ci, top, worklist, session_id, landing_branch)
            if role == DEVELOPMENT and gh
            else []
        )
        tree = {
            "role": role,
            "landing_branch": landing_branch,
            "foreign_items": foreign_items(role, branch, landing_branch, branches),
            "landing_open": landing_pr(nodes)[0] == "OPEN",
            "landing_released": landing_released(top, nodes) if nodes else 0,
        }
    head = plan_gate.queue_head(top) if role != LANDING else ""
    stale = head if head and _open_count(plan_gate, top, head) == 0 else ""
    day = today or datetime.datetime.now().astimezone().strftime("%m%d")

    def done(kind, pr=0, body=None, reason="", next_branch=""):
        plans: tuple[str, ...] = ()
        prereqs: tuple[str, ...] = ()
        notes = [reason] if reason else []
        if kind in (LIVE, UNREADABLE):
            plans, problems = plan_gate.pr_plan_set(top, body)
            notes.extend(problems)
            own = set(plan_gate.body_plans(body) if body else ()) or {head}
            prereqs = tuple(p for p in plans if p not in own)
        nxt, problem = next_queued(top, exclude=plans) if role != LANDING else ("", "")
        if problem:
            notes.append("next plan %s: %s" % (nxt, problem))
        return LoopState(
            kind,
            branch=branch,
            pr=pr,
            plans=plans,
            prereqs=prereqs,
            epic_items=epic_items(plans, epics) if plans else frozenset(),
            next_plan=nxt,
            queue_head=head,
            stale_promoted=stale,
            next_branch=next_branch,
            reason="; ".join(notes),
            **tree,
        )

    def branch_name():
        if role == LANDING:
            return ""
        try:
            return commit_policy.next_branch_name(top, day, gh=gh)
        except commit_policy.GhUnavailableError:
            return ""

    if branch == "main":
        try:
            others = commit_policy.live_branches(top, gh=gh)
        except commit_policy.GhUnavailableError as exc:
            return done(UNREADABLE, reason="the live-branch read failed: %s" % exc)
        # The landing tree's branch is that tree's, never a second live branch of this one.
        others = [b for b in others if not (role == DEVELOPMENT and b == landing_branch)]
        if others:
            return LoopState(
                OFF_LOOP,
                branch=branch,
                queue_head=head,
                stale_promoted=stale,
                reason="on main while %s is live" % ", ".join(others),
                **tree,
            )
        return done(ON_MAIN, next_branch=branch_name())
    if not branch or not commit_policy.BRANCH_SHAPE.match(branch):
        return LoopState(
            OFF_LOOP,
            branch=branch,
            queue_head=head,
            stale_promoted=stale,
            reason="detached HEAD" if not branch else "`%s` is not an MMDD-N branch" % branch,
            **tree,
        )
    nodes, err = wl_ci.pr_link(top, worklist, session_id, branch)
    if err:
        return done(UNREADABLE, reason="the PR read failed: %s" % err)
    by_state: dict[str, dict] = {}
    for n in nodes:
        by_state.setdefault(str(n.get("state") or "").upper(), n)
    if "OPEN" in by_state:
        n = by_state["OPEN"]
        return done(LIVE, pr=int(n.get("number") or 0), body=str(n.get("body") or ""))
    if "MERGED" in by_state:
        n = by_state["MERGED"]
        return done(MERGED, pr=int(n.get("number") or 0), next_branch=branch_name())
    closed = by_state.get("CLOSED")
    return done(NO_PR, reason="PR #%s was closed unmerged" % closed.get("number") if closed else "")


__all__ = [
    "CI_GREEN",
    "CI_PENDING",
    "CI_RED",
    "DEVELOPMENT",
    "DEVELOPMENT_PARKS",
    "DRAFT_CI_NOTE",
    "KINDS",
    "LANDING",
    "LANDING_PARKS",
    "LANDING_STATES",
    "LANDING_STEP_TEXT",
    "L_CI",
    "L_FIX",
    "L_HOTFIX",
    "L_IDLE",
    "L_MERGE",
    "L_RELEASE",
    "L_REVIEW",
    "TREE_PARK_NOTE",
    "LandingStep",
    "LoopState",
    "epic_items",
    "foreign_items",
    "item_branches",
    "landing_loop",
    "landing_pr",
    "landing_pr_open",
    "landing_record",
    "landing_released",
    "landing_step",
    "loop_state",
    "merged_sha",
    "next_queued",
    "read_release",
    "release_verdict",
    "tree_parks",
    "tree_role",
    "with_tree_scope",
]
