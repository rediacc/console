"""wl_prscope: where the one-plan-per-PR loop stands, computed once per stop (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 1, box SC2).

THE RULING. The Stop hook blocks only on the live PR's plan set, that PR's CI and reviews, the worklist items attached to that set's epics, and the loop's own duties (operator ruling 2026-10-03). Everything else is one queued line. After the PR merges, the hook holds the turn until the next branch, plan and PR exist. `loop_state` answers the questions both halves need: which PR, which plans, which items, what comes next.

ONE READER EACH. The PR is read once, through `wl_ci.pr_link` (the read focus mode also ends on). The plan set is `plan_gate.pr_plan_set`, the function the merge gate and P-A1 call, so the hook, CI and the merge cannot disagree about which plans a PR owns (ruling 7: the PR's `Plan:` plans plus every unfinished plan they depend on, prerequisites first). The queue is `plan_gate.queue`, the branch rules are `commit_policy`'s. The epic-to-plan link is `wl_epic.plan_epics` (box SC3), imported lazily; a `wl_epic` that does not carry it yet reads as no items.

KINDS. `live` (an MMDD-N branch with an OPEN PR), `no-pr` (such a branch, no PR yet, or only closed ones), `merged` (its newest PR MERGED, none open), `on-main` (main, no live branch), `off-loop` (any other branch, detached HEAD, a submodule, or not a git checkout), `unreadable` (the PR read failed; the plans fall back to the queue head's set, so item scope survives a gh outage).

`today` is the MMDD the next branch is named for. It defaults to LOCAL time, the clock `block_second_branch` names branches with, so the name printed here is the one that guard admits.

Reads no environment variable of its own; gh is reached through `wl_ci` and `commit_policy`.
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib.util
import pathlib


def _hooks_pkg():
    """(plan_gate, commit_policy) from `.claude/rediacc_hooks`, reached through the canonical sys.path hop (`.claude/rediacc_hooks/syspath.py`), loaded by file because this module lives outside that package."""
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    syspath = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(syspath)  # type: ignore[union-attr]
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import commit_policy, plan_gate  # noqa: PLC0415

    return plan_gate, commit_policy


LIVE = "live"
NO_PR = "no-pr"
MERGED = "merged"
ON_MAIN = "on-main"
OFF_LOOP = "off-loop"
UNREADABLE = "unreadable"
KINDS = (LIVE, NO_PR, MERGED, ON_MAIN, OFF_LOOP, UNREADABLE)


@dataclasses.dataclass(frozen=True)
class LoopState:
    """Where the loop stands. `plans` is ordered prerequisites first; `prereqs` names the members that are not the PR's own `Plan:` plans; `stale_promoted` is the queue head's path when it has no open box left (a finished Promoted entry nobody removed), else ""."""

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


def _plan_epics(rel):
    import wl_epic  # noqa: PLC0415 -- SC3 adds plan_epics in parallel; absent reads as empty

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


def _console_top(commit_policy, root):
    top = commit_policy.toplevel(str(root))
    if not top or commit_policy.superproject(top):
        return ""
    return top


def loop_state(root, worklist, session_id, today=None, epics=None, gh=True):
    """The `LoopState` for the checkout at `root`. `today` (MMDD) and `epics` (rel -> item ids) are the test seams; `gh=False` skips the next-branch name's PR-head read."""
    import wl_ci  # noqa: PLC0415 -- the one PR read

    plan_gate, commit_policy = _hooks_pkg()
    top = _console_top(commit_policy, root)
    if not top:
        return LoopState(OFF_LOOP, reason="not a console checkout")
    branch = commit_policy.current_branch(top)
    head = plan_gate.queue_head(top)
    stale = head if head and _open_count(plan_gate, top, head) == 0 else ""
    day = today or datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- block_second_branch's clock

    def done(kind, pr=0, body=None, reason="", next_branch=""):
        plans: tuple[str, ...] = ()
        prereqs: tuple[str, ...] = ()
        notes = [reason] if reason else []
        if kind in (LIVE, UNREADABLE):
            plans, problems = plan_gate.pr_plan_set(top, body)
            notes.extend(problems)
            own = set(plan_gate.body_plans(body) if body else ()) or {head}
            prereqs = tuple(p for p in plans if p not in own)
        nxt, problem = next_queued(top, exclude=plans)
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
        )

    def branch_name():
        try:
            return commit_policy.next_branch_name(top, day, gh=gh)
        except commit_policy.GhUnavailableError:
            return ""

    if branch == "main":
        try:
            others = commit_policy.live_branches(top, gh=gh)
        except commit_policy.GhUnavailableError as exc:
            return done(UNREADABLE, reason="the live-branch read failed: %s" % exc)
        if others:
            return LoopState(
                OFF_LOOP,
                branch=branch,
                queue_head=head,
                stale_promoted=stale,
                reason="on main while %s is live" % ", ".join(others),
            )
        return done(ON_MAIN, next_branch=branch_name())
    if not branch or not commit_policy.BRANCH_SHAPE.match(branch):
        return LoopState(
            OFF_LOOP,
            branch=branch,
            queue_head=head,
            stale_promoted=stale,
            reason="detached HEAD" if not branch else "`%s` is not an MMDD-N branch" % branch,
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


__all__ = ["KINDS", "LoopState", "epic_items", "loop_state", "next_queued"]
