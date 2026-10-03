"""wl_backlog: the next plan the one-plan-per-PR loop starts, read off agent/plans/QUEUE.md (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 5, box SC7).

WHY THE QUEUE AND NOTHING ELSE. Operator ruling 3 (2026-10-03): "Next plan" reads QUEUE.md, Promoted first, then Generated. The plan this advisory names is `wl_prscope.next_queued`'s answer, the reader the merge gate and P-A1 share through `plan_gate.queue`, so the hook, CI and the merge can never disagree about what comes next. The earlier nomination ranked every plan this session owned by Priority and file mtime and capped itself per session; a dry run on PR #592 showed it naming PLAN-config-passkey-optional.md, a plan the queue did not hold. That ranking, the ownership filter and the cap are gone (clean break).

WHAT IT RENDERS. The next plan's queue position ("Promoted 2", "Generated 1", or "prerequisite of <plan>" when the queue entry waits on an unfinished plan), its open box count, its first open box with the box signature, and its rank tag from `wl_planorder`. The PR's own plan set is never named: `next_queued` excludes it.

ADVISORY, never a `vadd`. NEVER blocks, NEVER writes a plan file, NEVER flips `Status:`, NEVER starts an implementation. The loop's own continuation after a merge is `loop-next` in wl_checks, which blocks; this line only says what is queued.

Reads the queue through `wl_planqueue` (its one format reader) and `wl_prscope`; reads no environment variable.
"""

from __future__ import annotations

import pathlib
import re

import wl_planenforce as E
import wl_planorder as PO
import wl_planqueue as Q
import wl_planrec as R

_STATUS = re.compile(r"(?m)^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)")


def _plan_text(root, rel):
    """A plan's raw text, or "" on any read failure. NEVER raises: this runs on the Stop path."""
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def queue_entries(root):
    """(promoted, generated): QUEUE.md's two lists, each in order; ([], []) when the file is absent."""
    try:
        text = (pathlib.Path(root) / Q.QUEUE_REL).read_text(encoding="utf-8")
    except OSError:
        return [], []
    return Q.entries(text)


def queue_position(root, rel, entries=None):
    """`Promoted <n>` or `Generated <n>` (1-based) for a queued plan, "" when the queue does not hold it."""
    promoted, generated = entries if entries is not None else queue_entries(root)
    if rel in promoted:
        return "Promoted %d" % (promoted.index(rel) + 1)
    if rel in generated:
        return "Generated %d" % (generated.index(rel) + 1)
    return ""


def other_plans(root, plans, entries=None):
    """How many queued plans are not in `plans` (the PR's set): the count the queued line reports."""
    promoted, generated = entries if entries is not None else queue_entries(root)
    return len({rel for rel in promoted + generated if rel not in set(plans)})


def next_plan(root, nxt=None, exclude=(), order_ctx=None):
    """(candidate, reason, stats) for the plan the loop starts next.

    `nxt` is the loop state's `next_plan` when the caller has it ("" means the queue holds none); None computes it with `wl_prscope.next_queued(root, exclude)`. `candidate` is a dict (`rel`, `status`, `open`, `position`, `first`, `tag`, `problem`) or None; `reason` is `nominated`, `queue-empty`, or `unreadable` (the plan file did not read); `stats` carries `queued`, the queue's entry count.
    """
    problem = ""
    if nxt is None:
        import wl_prscope  # noqa: PLC0415 -- the one next-plan reader, loaded only when the caller had no loop state

        nxt, problem = wl_prscope.next_queued(root, exclude)
    entries = queue_entries(root)
    stats = {"queued": len(set(entries[0] + entries[1]))}
    if not nxt:
        return None, "queue-empty", stats
    text = _plan_text(root, nxt)
    if not text:
        return None, "unreadable", dict(stats, rel=nxt)
    status = _STATUS.search(text)
    position = queue_position(root, nxt, entries)
    if not position:
        # Not queued itself: next_queued picked it as the unfinished prerequisite of the first queued entry outside `exclude` that has an open box.
        needs = next(
            (
                rel
                for rel in entries[0] + entries[1]
                if rel not in set(exclude) and E.first_box(root, rel)
            ),
            "",
        )
        position = "prerequisite of %s" % needs if needs else "prerequisite"
    if order_ctx is None:
        order_ctx = PO.context(root)[0]
    try:
        n_open = len(R.open_boxes(text))
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        n_open = 0
    return (
        {
            "rel": nxt,
            "status": status.group(1) if status else "",
            "open": n_open,
            "position": position,
            "first": E.first_box(root, nxt),
            "tag": PO.plan_tag(order_ctx, nxt),
            "problem": problem,
        },
        "nominated",
        stats,
    )


def render(candidate, reason, stats):
    """The advisory body, or "" when there is nothing to name. NO LIVE COUNTER: the body moves only when the queue or the plan moves, so the advisory queue's content signature keeps it from repeating."""
    if candidate is None:
        if reason == "unreadable":
            return "NEXT PLAN: %s is queued next but its file does not read." % stats.get("rel")
        return ""
    first = candidate.get("first")
    box = "%s  %s" % (first[0], first[1][:120]) if first else "(no open box found in its text)"
    lines = [
        "NEXT PLAN (QUEUE.md %s): %s%s, [Status: %s], %d open box(es)."
        % (
            candidate["position"],
            candidate["rel"],
            " %s" % candidate["tag"] if candidate.get("tag") else "",
            candidate.get("status") or "UNKNOWN",
            candidate["open"],
        ),
        "  First box: %s" % box,
        "  It starts after the live PR merges (one plan per PR); loop-next names the commands then.",
    ]
    if candidate.get("problem"):
        lines.append("  Its dependencies: %s" % candidate["problem"])
    lines.append(
        "  ADVISORY: nothing is started and nothing blocks. %d plan(s) queued in all; see %s."
        % (int(stats.get("queued") or 0), Q.QUEUE_REL)
    )
    return "\n".join(lines)
