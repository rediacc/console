"""wl_planorder: the ONE plan order and the ONE concurrency hold every "next item" picker reads (agent/plans/PLAN-plan-priority-concurrency.md T7-T9).

THE ASK (operator, 2026-09-25, section X): "Rank the work, not just order it. Depends-On: says what must come first. It doesn't say which of two ready plans matters more. That's why the stop hook kept naming whatever item was oldest in the queue." `wl_planconc` owns what the three header lines MEAN (`order_key`, `spawn_verdict`); this module is the glue its pickers share, so the
guide, the open-items list, queue-slot, the backlog nomination and the plan-unimplemented named box can never disagree about which item comes first or which one is held back:

  context(root)             the OrderCtx, built once per process and rebuilt only when a plan file changes (a stat signature)
  item_key(ctx, age)        a sort key over worklist records: `wl_planconc.order_key`, or the pre-plan age order without a ctx
  item_tag / plan_tag       the guide's `[P1 op]` display (`wl_planconc.rank_label`)
  plan_key / plan_why       (blocked, op, ai) for one plan FILE, for the pickers that rank plans rather than items
  holders(...)              {plan: [holder]} from the roster's AUTHORITATIVE live writers plus every session's fresh leases
  hold(rec, live, xinfo)    the verdict a writer spawn for this item would get, when it is a HOLD (a mutex or an overlap)
  conflicts(...)            live writers of this session whose plans already break the mutex or overlap (`roster-concurrency`)

WHY `holders` RESTATES `wl_planconc.live_plans`' LEASE HALF. `live_plans` reads this session's writers through `wl_roster.live_estimate`, which is what a PreToolUse guard or a CLI verb can see. The Stop hook has something better, the harness's own event, and the plan (section 5c) orders the roster to judge against that. The lease half below is the same rule over the same fold, kept
line for line so the guard and the roster agree; `test_wl_plan_priority.py` pins the two against one fixture.

A HOLD IS ONLY A MUTEX OR AN OVERLAP (section 5b: "step 3, 4 or 5 of spawn_verdict"). `no-owns` and `owns-none` are defects in a plan's header, not a holder to wait for, so an item they refuse is named by queue-slot and the spawn guard prints the fix; hiding it as "held" would park it forever behind nothing.

SEALED. Reads no environment variable; `.ci/policy/worklist-env-registry.json` lists it under `sealed_modules`. A variable that decided what counts as held would be the escape hatch `wl_planconc`'s own seal rules out.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any

import wl_planconc as X
import wl_plandeps as D

# The verdict kinds that mean "wait for the holder", never "fix the header".
HOLD_KINDS = frozenset({"mutex", "mutex-own", "overlap"})
# A holder line of `spawn_verdict`: "<plan> is exclusive -- <why> and live (<holders>)" or "<plan> is parallel and live (<holders>)".
_HOLDER_LINE = re.compile(r"^(PLAN-[A-Za-z0-9._-]+\.md) is (?:exclusive|parallel)\b.* and live \(")
# The longest hold reason one guide or queue-slot line carries.
REASON_MAX = 300

_MEMO: dict[str, tuple[tuple, X.OrderCtx]] = {}


def _signature(root: pathlib.Path) -> tuple:
    """Every plan file's (folder, name, mtime_ns, size), plus agent/INDEX.md's: what Graph.load reads. A change to any of them rebuilds the ctx."""
    sig: list[tuple] = []
    for folder in D.PLAN_DIRS:
        try:
            with os.scandir(root / folder) as it:
                for entry in it:
                    if entry.name.startswith("PLAN-") and entry.name.endswith(".md"):
                        st = entry.stat()
                        sig.append((folder, entry.name, st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    try:
        st = (root / D.INDEX_REL).stat()
        sig.append(("", D.INDEX_REL, st.st_mtime_ns, st.st_size))
    except OSError:
        pass
    return tuple(sorted(sig))


def context(root) -> tuple[X.OrderCtx | None, str]:
    """(ctx, problem). ctx is None only when the plans could not be read, and `problem` then says why: the pickers fall back to age order and the guide PRINTS the problem, so a blind order is never a silent one."""
    if root is None:
        return None, "no project root"
    root = pathlib.Path(root)
    try:
        sig = _signature(root)
        hit = _MEMO.get(str(root))
        if hit is not None and hit[0] == sig:
            return hit[1], ""
        ctx = X.order_ctx(D.Graph.load(root))
        _MEMO[str(root)] = (sig, ctx)
        return ctx, ""
    except Exception as exc:  # noqa: BLE001 -- an order is never worth a crashed stop; the caller prints the problem
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def item_key(ctx: X.OrderCtx | None, age=None):
    """A sort key over worklist records. `age(rec)` replaces the item's `first` stamp for a picker with its own age term (the queue's lease time). Without a ctx every item is an unlinked AI P2, which leaves the age order exactly as it was before plans had a rank."""

    def key(rec: dict) -> tuple:
        got = age(rec) if age is not None else None
        if ctx is None:
            return (0, *X.UNLINKED_RANK, str(rec.get("first") or "") if got is None else got)
        return X.order_key(rec, ctx, got)

    return key


def _tag(key: tuple[int, int, int]) -> str:
    blocked, op, ai = key
    label = X.rank_label(op, ai)
    return label[:-1] + ", dep-blocked]" if blocked else label


def item_tag(rec: dict, ctx: X.OrderCtx | None) -> str:
    """`[P1 op]`, `[P3]`, `[P-]` (a plan with no Priority yet), with `, dep-blocked` when a dependency is still open; "" for an item linked to no live plan, which ranks as an AI P2 and needs no tag to say so."""
    if ctx is None:
        return ""
    rel = ctx.rel_of(X.item_plan(rec))
    return _tag(ctx.plan_key(rel)) if rel else ""


def _plan_rel(ctx: X.OrderCtx | None, rel: str) -> str | None:
    return ctx.rel_of(os.path.basename(str(rel or ""))) if ctx is not None else None


def plan_key(ctx: X.OrderCtx | None, rel: str) -> tuple[int, int, int]:
    """(blocked, op_rank, ai_rank) for one plan file; an unknown or unreadable plan is unranked and unblocked."""
    live = _plan_rel(ctx, rel)
    if ctx is None or live is None:
        return (0, *X.UNRANKED)
    return ctx.plan_key(live)


def plan_tag(ctx: X.OrderCtx | None, rel: str) -> str:
    return _tag(plan_key(ctx, rel))


def plan_why(ctx: X.OrderCtx | None, rel: str) -> str:
    """The backlog's first WHY line: the rank that put this plan first, then the mtime rule that breaks ties."""
    blocked, op, ai = plan_key(ctx, rel)
    live = _plan_rel(ctx, rel)
    header = ctx.graph.plans[live].header if ctx is not None and live is not None else None
    pr = header.priority if header is not None else None
    if op < 4:
        head = "Priority P%d (operator)" % op
    elif ai < 4:
        head = "Priority P%d" % ai
    else:
        head = "No `Priority:` yet, so it ranks after every ranked plan"
    if pr is not None and X.own_rank(header) != (op, ai):
        head += ", inherited from a plan that depends on it"
    elif pr is not None and pr.reason:
        head += " -- %s" % pr.reason
    return "%s%s; then NEWEST first (DESC by file mtime)." % (
        head,
        " (a dependency is still open)" if blocked else "",
    )


# ---------------------------------------------------------------- the live world, from the roster's authoritative writers


def holders(writers, fold, session_id) -> dict[str, list[str]]:
    """{plan basename: [holder, ...]}: `wl_planconc.live_plans` over the roster's own writers instead of the estimate.

    `writers` is `[(agent_id, type, text)]`, `text` being the writer's description plus its first prompt. The lease half is `live_plans`' own, line for line.
    """
    import wl_core as C  # noqa: PLC0415 -- the live world is read only here
    import wl_leasehelp as LH  # noqa: PLC0415

    items = list(getattr(fold, "items", None) or [])
    by_id = {r["id"]: r for r in items if isinstance(r, dict) and r.get("id")}
    out: dict[str, list[str]] = {}
    live_ids: set[str] = set()
    for aid, kind, text in writers:
        live_ids.add(aid)
        for plan in sorted(X.spawn_plans(text, by_id)):
            out.setdefault(plan, []).append("writer %s (%s)" % (aid, kind or "?"))
    for rec in items:
        if rec.get("state") != ">":
            continue
        worker = str(rec.get("worker") or "")
        if not worker or worker in (LH.QUEUE_WORKER, LH.LEAD_WORKER):
            continue
        if C.lease_state(str(rec.get("line") or "")) != "fresh":
            continue
        linked = X.item_plan(rec)
        if not linked:
            continue
        mine = C.owned_by_me(rec.get("owner"), session_id)
        if mine and not any(
            worker == w or w.startswith(worker) or worker.startswith(w) for w in live_ids
        ):
            continue
        label = "lease #%s worker:%s%s" % (
            rec["id"],
            worker,
            "" if mine else " (session %s)" % str(rec.get("owner") or "?")[:8],
        )
        if label not in out.get(linked, []):
            out.setdefault(linked, []).append(label)
    return out


def xinfo_for(root):
    """`base -> PlanX`, memoised for one pass: every verdict of one stop reads each plan head once."""
    seen: dict[str, X.PlanX] = {}

    def xinfo(base: str) -> X.PlanX:
        if base not in seen:
            seen[base] = X.plan_x(root, base)
        return seen[base]

    return xinfo


def hold(rec: dict, live, xinfo, required=None) -> X.Verdict | None:
    """The refusal a writer spawn for this item would get, when it is a HOLD; None when it could start (or when `live` is unknown).

    The item's own plan is what the spawn serves, which is the plan auto-lease later records. A planless item is judged as a planless spawn with no `Owns:` line: only a live exclusive plan holds it.
    """
    if live is None:
        return None
    plan = X.item_plan(rec)
    got = X.spawn_verdict({plan} if plan else set(), live, xinfo, None, required)
    return got if not got.allow and got.kind in HOLD_KINDS else None


def held_by(verdict: X.Verdict) -> list[str]:
    """The holder plans a HOLD names, in its own order."""
    out: list[str] = []
    for line in verdict.lines:
        m = _HOLDER_LINE.match(line)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def reason(verdict: X.Verdict) -> str:
    """The verdict's lines on one line, at most REASON_MAX characters. The LAST line is kept whole when there are several, because an overlap's last line carries the witness path (`both claim <path>`), the one fact a reader acts on; the holder lines before it are what gets shortened."""
    lines = list(verdict.lines)
    text = "; ".join(lines)
    if len(text) <= REASON_MAX:
        return text
    if len(lines) > 1 and len(lines[-1]) <= REASON_MAX - 40:
        room = REASON_MAX - len(lines[-1]) - 2
        head = "; ".join(lines[:-1])
        return "%s; %s" % (head[: room - 3] + "...", lines[-1])
    return text[: REASON_MAX - 3] + "..."


def conflicts(
    serving: dict[str, set[str]], live, xinfo, required=None
) -> list[tuple[str, X.Verdict]]:
    """[(agent_id, verdict)] for each live writer of THIS session whose plans already break the mutex or overlap ANOTHER live writer of this session's plans.

    Judged against this session's writers only: they are what the harness's own event proves live. A clash with a peer's lease is the spawn guard's and the queue's question, and a stale peer lease must never make this session stop a writer.
    """
    out: list[tuple[str, X.Verdict]] = []
    for aid in sorted(serving):
        mine = serving[aid]
        if not mine:
            continue
        others: dict[str, list[Any]] = {}
        for plan, hs in (live or {}).items():
            keep = [
                h for h in hs if h.startswith("writer ") and not h.startswith("writer %s " % aid)
            ]
            if keep:
                others[plan] = keep
        got = X.spawn_verdict(mine, others, xinfo, None, required)
        if not got.allow and got.kind in HOLD_KINDS:
            out.append((aid, got))
    return out
