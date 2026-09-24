"""wl_backlog: the ONE next plan this session should implement, newest-first, validated against other sessions.

WHY THIS EXISTS. The operator's own words: "The stop hook should help you to pick next plan for implementation! What happens is this, we plan but don't implement. Let's fix that and implementation could be in DESC order of course with validation since other sessions may access/continue to implementations."  # style-ok
Measured against this tree the day this was written: 24 plan files were non-finished and carried at least one open box, 278 open boxes total, four written by the SAME session that reported the list to the operator and asked which to implement -- nothing in the Stop battery had asked. Four existing mechanisms sit close to this question and each answers a different one:
`plan_drift_rows` asks whether a plan fell BEHIND work already done (a fresh draft is by definition not behind); `plans_block` is a SessionStart/PostCompact census, once per session, gating nothing; `wl_planfile.plan_rows` asks whether a plan's boxes are TRACKED, not whether they are IMPLEMENTED; `wl_store.plan_candidates` is the exact mirror image ("what has a DEAD PEER left
undone", for `--migrate`) and excludes everything THIS session owns by one line (`if owner in mine: continue`). This module is that line inverted, plus the validation the operator asked for. Full design: agent/plans/PLAN-stop-hook-plan-backlog-nudge.md.

MECHANICAL, not judged: ordering by recency, ownership and claim state is arithmetic over file metadata and the worklist event stream, with nothing to calibrate and nothing a control could pin better than a plant.

ADVISORY, never a `vadd`: see NEVER-GOALS below. A blocking tier over a standing backlog nobody here created would wall every session behind work it did not cause, the same shape `wl_planfile`'s design note 1 already refuses at 24x smaller scale.

NEVER-GOALS, stated once so a future edit does not reintroduce them by accident:
  - NEVER starts an implementation. Starting a 20-box plan unattended has no basis for the judgement and is exactly the kind of irreversible, high-blast-radius action CLAUDE.md's rule against unilateral descoping mirrors in the other direction.
  - NEVER writes a plan file, and NEVER flips `Status:`. Status is a claim made by whoever is executing; a hook that wrote `executing` into 24 headers would manufacture 24 false claims.
  - NEVER blocks. No `vadd`, no verdict flip -- pinned by a control at the call site, same shape `test-planfile.py` uses to pin `plan-tasks`.
  - NEVER migrates a peer's plan. That act is `worklist.py --migrate --plan`, typed by a session that decided to take it; this module only counts and names the newest idle-owned candidate.

`recs` and `plan_owner` are passed in rather than imported, matching `wl_planfile.plan_rows`'s own reason: this module must never import `wl_checks`, which imports `wl_planfile` and would import this module too, and the injection is what lets the selftest drive it with fixtures instead of a real `agent/` tree.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any

import wl_core as C
import wl_planfile as F
import wl_planindex as PI
import wl_store as S

# The per-session cap on how many nominations this module will push in one session, before it goes quiet rather than repeating itself at a declining session. Counts ADDS, never absorbed calls -- see agent_hint_queue's own reasoning, which this mirrors: counting an outq_add call that outq_add itself absorbed (unchanged content, still inside its refresh window) would spend the
# budget on a line nobody ever saw.
WORKLIST_BACKLOG_MAX_PER_SESSION = int(os.environ.get("WORKLIST_BACKLOG_MAX_PER_SESSION", "3"))

# `Depends-On:` is a new, OPTIONAL header. No convention for it existed anywhere in this repo's 108 plans at design time -- grepped, zero hits -- so this is free to define rather than obliged to match something already written. Shape mirrors wl_checks.PLAN_OWNER_RE: optional markdown emphasis, header block only.
DEPENDS_ON_RE = re.compile(r"^\*{0,2}Depends-On\*{0,2}:\s*(.+)$", re.MULTILINE)
# Duplicated from wl_checks.PLAN_HEADER_LINES rather than imported, for the same import-cycle reason recs/plan_owner are injected above: this module must not import wl_checks. Both constants must move together if the header convention's window ever changes.
_HEADER_LINES = 10
# The three worklist states that mean "still outstanding" -- wl_checks and wl_planfile both use this exact triple, spelled independently in each module for the same reason PLAN_HEADER_LINES is: no cross-import back to wl_checks.
_OPEN_ITEM_STATES = (" ", ">", "?")


def _plan_text(root, rel):
    """A plan's raw text, or None on any read failure. NEVER raises: this runs on the Stop path."""
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def plan_depends_on(root, rel):
    """[dep_rel, ...] parsed from `rel`'s own header block, resolved relative to the directory `rel` lives in when a token carries no slash of its own.

    [] on any read failure or an absent header -- absence is not a finding here, it is the common case.
    """
    text = _plan_text(root, rel)
    if text is None:
        return []
    head = "\n".join(text.splitlines()[:_HEADER_LINES])
    m = DEPENDS_ON_RE.search(head)
    if not m:
        return []
    base_dir = pathlib.Path(rel).parent
    out = []
    for tok in m.group(1).split(","):
        name = tok.strip().strip("`'\"")
        if not name:
            continue
        out.append(name if "/" in name else str(base_dir / name))
    return out


def _resolve_dep(token, recs_by_rel):
    """The `recs_by_rel` key a Depends-On token names, or None when nothing matches.

    Exact relpath first; a bare basename falls back to a unique match, since a plan naming `PLAN-x.md` should not have to spell the folder it happens to sit in today.
    """
    if token in recs_by_rel:
        return token
    base = os.path.basename(token)
    hits = [r for r in recs_by_rel if os.path.basename(r) == base]
    return hits[0] if len(hits) == 1 else None


def _open_boxes(root):
    """{rel: (open, status)} for every plan, sourced from wl_planindex's own census -- index_census when fresh, its census_rows fallback otherwise.

    Never a third scan: plan_drift_rows, plans_block and plan_candidates all trust this same pair, in this same order.
    """
    rows, state, _detail = PI.index_census(root)
    if state != PI.CENSUS_FRESH:
        rows = PI.census_rows(root)
    return {rel: (open_n, status) for rel, status, _lines, open_n, _ticked, _size in rows}


def _claimed(rel, fold):
    """True when SOME worklist item, ANY owner, in ANY open state, carries this plan's basename in its base text.

    ANY owner, deliberately: a peer already tracking the implementation is tracking it, the same reasoning wl_planfile.item_rows gives for its own claim check. Basename containment, not token similarity -- the filename is an exact, unambiguous token and fuzzy matching would buy nothing here but false positives.
    """
    base = os.path.basename(rel)
    if not base:
        return False
    for r in list(getattr(fold, "items", None) or []):
        if not isinstance(r, dict):
            continue
        if str(r.get("state") or " ") not in _OPEN_ITEM_STATES:
            continue
        text = str(r.get("basetext") or "").strip()
        if not text:
            text = str(r.get("text") or "").strip().split("  ", 1)[0]
        if base in text:
            return True
    return False


def _redirect(root, rel, recs_by_rel, boxes, fold, unresolved):
    """The plan that must land BEFORE `rel`, walking `Depends-On:` edges, or `rel` itself when nothing blocks.

    Semantics: an edge blocks only while its target is neither FINISHED nor CLAIMED -- not "until finished", which would serialize the whole backlog into one chain. `unresolved` collects (citing_rel, token) pairs for a target this cannot find, reported by the caller rather than silently ignored. A cycle is detected by a visited set and resolved by returning `rel` itself, falling
    back to plain mtime order for that one plan rather than going silent on it.
    """
    visited = set()
    cur = rel
    while True:
        visited.add(cur)
        target = None
        for tok in plan_depends_on(root, cur):
            resolved = _resolve_dep(tok, recs_by_rel)
            if resolved is None:
                unresolved.append((cur, tok))
                continue
            status = recs_by_rel[resolved][0]
            finished = str(status or "").strip().lower() in F.FINISHED_STATES
            open_n = boxes.get(resolved, (0, None))[0]
            if not finished and open_n > 0 and not _claimed(resolved, fold):
                target = resolved
                break
        if target is None:
            return cur
        if target in visited:
            return rel
        cur = target


def _mtime_cluster(root, rel):
    """(cluster_size, runner_up_rel) when `rel` shares its exact mtime with 2+ other plans, else None.

    Bulk git operations (a checkout, a mass reflow) rewrite mtime identically across many files, which can promote a hundred old plans above genuinely new work with no commit to explain it -- measured on this tree at design time: five plans sharing one mtime, five sharing another, nine sharing a third. This does not correct the ordering -- mtime stays the DESC key, ties still
    break on path -- it only names the signature so a reader sees a bulk-touch cluster rather than trusting a number a checkout produced.
    """
    stats = PI.plan_stats(root)
    by_rel = {r: mt for r, _size, mt in stats}
    mt = by_rel.get(rel)
    if mt is None:
        return None
    sharing = sorted(r for r, m in by_rel.items() if m == mt and r != rel)
    if len(sharing) < 2:
        return None
    return len(sharing), sharing[0]


def _dead_peer(root, recs, boxes, plan_owner, session_id, worklist, projects_dir, events):
    """A COUNT, never a nomination: the newest eligible plan owned by a peer this machine reads as anything but live/unknown, plus how many others share that fate. None when there are none.

    Peer-owned plans are counted, not nominated -- implementing one without `worklist.py --migrate --plan` first would produce a committed document that contradicts who did the work, which is precisely the double-implementation this whole validation exists to prevent.
    """
    idle = []
    for rel, status, _n in recs:
        if str(status or "").strip().lower() in F.FINISHED_STATES:
            continue
        open_n = boxes.get(rel, (0, None))[0]
        if open_n <= 0:
            continue
        owner = plan_owner(root, rel)
        if not owner or C.owned_by_me(owner, session_id):
            continue
        verdict, _why = S.session_liveness(worklist, owner, projects_dir, events)
        if verdict in ("live", "unknown"):
            continue
        idle.append((rel, open_n, owner))
    if not idle:
        return None
    rel, open_n, owner = idle[0]  # recs is already newest-mtime-first
    return {"count": len(idle), "rel": rel, "open": open_n, "owner": owner}


def next_plan(
    root, recs, fold, session_id, plan_owner, worklist, state_doc, projects_dir=None, events=None
):
    """(candidate, reason, stats).

    `candidate` is a dict (`rel`, `status`, `open`, `why`, `passed_over`, `dead_peer`, `unresolved`) or None. `reason` is always one of four distinguishable strings even when `candidate` is None -- "found nothing" and "could not see" must never render alike: `no-plans` (the corpus itself is empty), `all-finished` (every plan in scope is history), `all-claimed` (every eligible
    plan already has a worklist item on it), `capped` (this session's own per-session budget is spent). `stats` always carries `scanned` and `eligible` counts, the second, dumber number that makes a `None` auditable instead of indistinguishable from a broken filter.
    """
    boxes = _open_boxes(root)
    scanned = len(recs)
    recs_by_rel = {rel: (status, _n) for rel, status, _n in recs}

    eligible = []
    for (
        rel,
        status,
        _n,
    ) in recs:  # recs is already newest-mtime-first; this function re-derives nothing about order
        st = str(status or "").strip().lower()
        if st in F.FINISHED_STATES:
            continue
        open_n = boxes.get(rel, (0, None))[0]
        if open_n <= 0:
            continue
        owner = plan_owner(root, rel)
        if not C.owned_by_me(owner, session_id):
            continue
        eligible.append((rel, status, open_n))

    if not eligible:
        return (
            None,
            ("all-finished" if scanned else "no-plans"),
            {"scanned": scanned, "eligible": 0},
        )

    cap = state_doc.get("backlog_nominated")
    if isinstance(cap, dict) and len(cap) >= WORKLIST_BACKLOG_MAX_PER_SESSION:
        return None, "capped", {"scanned": scanned, "eligible": len(eligible)}

    unresolved: list[Any] = []
    passed_over = []
    dead_peer = _dead_peer(
        root, recs, boxes, plan_owner, session_id, worklist, projects_dir, events
    )

    for rel, status, open_n in eligible:
        if _claimed(rel, fold):
            passed_over.append(
                (rel, open_n, "CLAIMED by an open worklist item -- another context is on it")
            )
            continue
        target = _redirect(root, rel, recs_by_rel, boxes, fold, unresolved)
        if target != rel:
            t_status, _t_n = recs_by_rel.get(target, (None, None))
            t_open = boxes.get(target, (0, None))[0]
            why = [
                "NEWEST first (DESC by file mtime), which is the ordering rule.",
                "Owned by this session.",
                "NOT started: no worklist item names this file.",
                "Blocked by `Depends-On:` on `%s`, which lands first." % rel,
            ]
            return (
                {
                    "rel": target,
                    "status": t_status,
                    "open": t_open,
                    "why": why,
                    "passed_over": passed_over,
                    "dead_peer": dead_peer,
                    "unresolved": unresolved,
                    "mtime_cluster": _mtime_cluster(root, target),
                },
                "nominated",
                {"scanned": scanned, "eligible": len(eligible)},
            )
        why = [
            "NEWEST first (file mtime), which is the DESC rule.",
            "Owned by this session.",
            "NOT started: no worklist item in any open state names this file.",
            "No `Depends-On:` header, so nothing has to land before it."
            if not plan_depends_on(root, rel)
            else "Its `Depends-On:` target is finished or already claimed, so it does not block.",
        ]
        return (
            {
                "rel": rel,
                "status": status,
                "open": open_n,
                "why": why,
                "passed_over": passed_over,
                "dead_peer": dead_peer,
                "unresolved": unresolved,
                "mtime_cluster": _mtime_cluster(root, rel),
            },
            "nominated",
            {"scanned": scanned, "eligible": len(eligible)},
        )

    return None, "all-claimed", {"scanned": scanned, "eligible": len(eligible)}


def render(candidate, reason, stats, session_id):
    """The advisory body, or a one-line diagnostic for a None candidate.

    NO LIVE COUNTER anywhere in this text: a body with a minute-precision age re-enqueues on every stop because outq_add's content signature moves, which is exactly the repeated-nag failure this whole mechanism must not become. Counts of boxes and plans are stable between edits and are safe.
    """
    scanned = stats.get("scanned", 0)
    eligible = stats.get("eligible", 0)
    if candidate is None:
        return "NO PLAN NOMINATED (%s). %d plan file(s) scanned, %d eligible." % (
            reason,
            scanned,
            eligible,
        )

    lines = [
        "NEXT PLAN TO IMPLEMENT -- %s" % candidate["rel"],
        "  [Status: %s], %d open box(es)."
        % (candidate.get("status") or "UNKNOWN", candidate["open"]),
        "",
        "  WHY THIS ONE, so the ordering does not have to be argued again:",
    ]
    lines.extend("    - %s" % w for w in candidate.get("why") or [])

    cluster = candidate.get("mtime_cluster")
    if cluster:
        size, runner_up = cluster
        lines.append(
            "    - NOTE: this mtime is shared with %d other plan(s) (e.g. %s) -- likely a bulk "
            "git touch (a checkout, a mass reflow), not %d genuinely simultaneous edits."
            % (size, runner_up, size)
        )

    passed = candidate.get("passed_over") or []
    if passed:
        lines.append("")
        lines.append("  PASSED OVER, and why:")
        for rel, open_n, note in passed:
            lines.append("    %s (%d open) -- %s" % (rel, open_n, note))

    unresolved = candidate.get("unresolved") or []
    if unresolved:
        lines.append("")
        for citing, token in unresolved:
            lines.append(
                "  %s cites Depends-On: %s, which does not resolve to any plan in scope."
                % (citing, token)
            )

    lines.append("")
    lines.append("  Start it by tracking it -- this also settles this advisory:")
    lines.append(
        '    .claude/hooks/stop/worklist.py --add %s "Implement %s: <first open box>"'
        % (session_id[:8], candidate["rel"])
    )
    lines.append("")
    lines.append("  %d plan file(s) scanned, %d eligible, 1 nominated." % (scanned, eligible))

    dp = candidate.get("dead_peer")
    if dp:
        lines.append(
            "  %d eligible plan(s) are owned by sessions this machine reads as idle "
            "(newest: %s, %d open, owner %s). Adopt one before implementing it:"
            % (dp["count"], dp["rel"], dp["open"], dp["owner"])
        )
        lines.append(
            "    .claude/hooks/stop/worklist.py --migrate %s --plan %s"
            % (session_id[:8], dp["rel"])
        )

    lines.append("")
    lines.append("  ADVISORY. Nothing is started, no Status is changed, nothing is blocked.")
    return "\n".join(lines)
