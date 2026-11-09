"""wl_boxready: which open `[writer]` boxes a writer could start right now, and the IDLE CAPACITY block that names them when writer slots sit free (agent/plans/PLAN-idle-writer-capacity.md D1, D4, D5).

WHY. On 2026-11-09 the Stop hook printed "no queued plan is eligible for a free writer slot" for hours while 17 of 25 writer slots were free and PLAN-enterprise-isolation.md had `[writer]` boxes a writer could take. The turbo picker works in whole plans and its ceiling counted live-only plans; nothing looked at boxes. The operator ruled (2026-11-09, R1-R4): a block that names the ready boxes and the spawn command, never an auto-spawn; only boxes explicitly tagged `[writer]` count; a box's own `Depends on:` line judges it, and a plan-level edge gates only the boxes that state none.

THE TAG GRAMMAR LIVES HERE, ONCE. The first bracketed tag after a box's id (`S2 [writer] ...`, `V1 [live, post-merge] ...`), split into lowercase words. `plan_gate.writer_startable` (the turbo ceiling and pick) reads the same functions, so the two readings of "a writer can do this box" cannot drift. The grammar functions import nothing outside the standard library; `post_merge` loads `wl_planenforce.AFTER_MERGE` on first use.

READY (D4). An open box is ready when it is writer-tagged and not post-merge; its plan is not held, not finished and has no `Writers: none` header; `wl_plandeps.Graph.box_blockers` finds nothing unresolved, where a LIVE plan-level edge is cleared for a writer box when the prerequisite's remaining open boxes (or the one box a task edge names) are all non-writer or post-merge, because a writer box builds on the prerequisite's code and code is writer work (an untagged open box of the prerequisite still holds it, failing closed); no open, deferred or leased worklist item names the plan and the box; and its `Owns:` line overlaps no box in flight, no other plan a live writer serves, and no box named before it.

NEVER RAISES INTO A STOP from the grammar; `ready_boxes` and `idle_capacity_text` may raise, and the hook's arm reports that as a hook bug.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re

# The first bracketed tag after the box's id, on a raw box line or a parsed body. `- [ ] V1 [live] x`, `V1 [live] x`, `- [ ] [live] x` all read `live`; a box whose second token is not a bracket has no tag.
TAG_RE = re.compile(r"^\s*(?:[-*+]\s+\[[ xX?>]\]\s+)?(?:\*\*)?(?:[^\s\[]+\s+)?\[([^\]\n]{1,60})\]")
WRITER = "writer"
POST_MERGE = "post-merge"
# A tag word that names work no writer agent does: a live system, the operator, the lead, a machine or fleet, a drill, a date.
NON_WRITER_WORDS = frozenset(
    {"live", "operator", "lead", "hostinger", "fleet", "ops", "drill", "deadline", "bench", "local"}
)
# `Writers: none -- <reason>` in a plan header: no open box of it is a writer's.
WRITERS_NONE_RE = re.compile(r"^Writers:\s*none\b", re.IGNORECASE | re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\[[ xX?>]\]\s+")
_OWNS_LINE_RE = re.compile(r"^\s*Owns:\s*(.+?)\s*$", re.MULTILINE)
# How many boxes the block lists before it says "and N more".
LIST_MAX = 10


def tag_words(line: str) -> tuple[str, ...]:
    """The lowercase words of the box's first bracketed tag, () when it has none."""
    m = TAG_RE.match(re.sub(r"[`]+", "", line or ""))
    if not m:
        return ()
    return tuple(w for w in re.split(r"[,\s/]+", m.group(1).strip().lower()) if w)


def writer_tagged(line: str) -> bool:
    """True when the box is explicitly tagged `[writer]` (ruling R3)."""
    return WRITER in tag_words(line)


def non_writer(line: str) -> bool:
    """True when the box's tag names work no writer does (`[live]`, `[operator window]`, `[hostinger rollout]`, ...) and does not also say `writer`."""
    words = tag_words(line)
    return WRITER not in words and any(w in NON_WRITER_WORDS for w in words)


def post_merge(line: str) -> bool:
    """True when the box waits for the merge: a `post-merge` tag word, or its own `Depends on:` clause naming a merge (`wl_planenforce.AFTER_MERGE`)."""
    if POST_MERGE in tag_words(line):
        return True
    try:
        import wl_planenforce
    except ImportError:
        return False
    return wl_planenforce.after_merge(line)


def startable(line: str) -> bool:
    """True when a writer could do the box before the merge as far as its tags say: neither non-writer nor post-merge. An untagged box is startable."""
    return not non_writer(line) and not post_merge(line)


@dataclasses.dataclass(frozen=True)
class ReadyBox:
    rel: str
    sig: str
    id: str
    text: str
    owns: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Skip:
    rel: str
    sig: str
    id: str
    why: str


@dataclasses.dataclass(frozen=True)
class _Box:
    rel: str
    sig: str
    id: str
    body: str
    block: str
    owns: tuple[str, ...]
    shown: str


# (path) -> (mtime_ns, size, text): one read per plan per process, re-read when the file changes.
_TEXT_CACHE: dict[str, tuple[int, int, str]] = {}


def _read(root, rel: str) -> str | None:
    path = pathlib.Path(root) / rel
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = str(path)
    hit = _TEXT_CACHE.get(key)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _TEXT_CACHE[key] = (st.st_mtime_ns, st.st_size, text)
    return text


def box_owns(block: str) -> tuple[str, ...]:
    """The globs of a box's own `Owns:` continuation line, `(note)`s and a closing period dropped; () when it states none."""
    import wl_plandeps as D

    m = _OWNS_LINE_RE.search(re.sub(r"[`]+", "", block or ""))
    if not m:
        return ()
    value = m.group(1).rstrip(".").strip()
    owns, errors = D.parse_owns(value)
    if not errors and owns is not None:
        return tuple(owns.globs)
    out = []
    for raw in value.split(","):
        glob = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
        if glob and " " not in glob:
            out.append(glob)
    return tuple(out)


def _promoted(root) -> list[str]:
    import wl_planqueue

    text = _read(root, wl_planqueue.QUEUE_REL)
    if text is None:
        return []
    return wl_planqueue.entries(text)[0]


def _stem_re(rel: str) -> re.Pattern[str]:
    stem = pathlib.Path(rel).name
    stem = stem.removesuffix(".md")
    return re.compile(r"(?<![\w-])%s(?:\.md)?(?![\w-])" % re.escape(stem))


def _names_box(text: str, stem: re.Pattern[str], box: _Box) -> bool:
    if not stem.search(text):
        return False
    if box.sig and box.sig in text:
        return True
    return (
        bool(box.id) and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(box.id), text) is not None
    )


def _open_boxes(rel: str, text: str) -> list[_Box]:
    import wl_plandeps as D
    import wl_planrec as R

    out = []
    for i, raw, body, sig in R.open_boxes(text):
        block = D.box_block(text, i)
        # Shown from the raw line with only the bullet and checkbox dropped: the parsed body strips `_`, which mangles every path and name it carries.
        shown = _BULLET_RE.sub("", raw).strip()
        out.append(_Box(rel, sig, D.box_id(body), body, block, box_owns(block), shown))
    return out


def _writer_clear(root):
    """The predicate `box_blockers` consults for a LIVE plan-level edge of a writer box: True when the prerequisite holds no writer work, i.e. every remaining open box of it (or the one box a task edge names) is non-writer or post-merge."""
    import wl_plandeps as D

    def clear(target, edge) -> bool:
        text = _read(root, target.rel)
        if text is None:
            return False
        if edge.task:
            box = next((b for b in D.plan_boxes(text) if edge.task in (b.id, b.sig)), None)
            if box is None:
                return False
            if box.done:
                return True
            block = D.box_block(text, box.line)
            return non_writer(box.body) or post_merge(block)
        if WRITERS_NONE_RE.search(text):
            return True
        return all(non_writer(b.body) or post_merge(b.block) for b in _open_boxes(target.rel, text))

    return clear


def ready_boxes(root, plans=None, live_plans=(), items=(), graph=None):
    """([ReadyBox], [Skip]) over `plans` (default: the `## Promoted` entries of agent/plans/QUEUE.md), in queue and file order. `live_plans` are the plan basenames live writers serve (the roster's `plan_holders` keys); `items` are worklist records (`id`, `state`, `text`). A skip is listed only for a writer-tagged box."""
    import wl_planconc
    import wl_plandeps as D
    import wl_planenforce

    root = str(root)
    rels = list(plans) if plans is not None else _promoted(root)
    if graph is None:
        graph = D.Graph.load(root)
    finished = D.finished_states() | {"moved", "removed"}
    tracking = [r for r in items or () if r.get("state") in (" ", ">", "?")]
    per_plan: list[tuple[str, list[_Box]]] = []
    for rel in rels:
        text = _read(root, rel)
        if text is None or "[writer" not in text:
            continue
        header = D.parse_header(text)
        if (
            header.status in finished
            or wl_planenforce.plan_held(text)
            or WRITERS_NONE_RE.search(text)
        ):
            continue
        per_plan.append((rel, _open_boxes(rel, text)))
    # Work in flight: every box a leased item names, with its Owns; and the header Owns of each plan a live writer serves.
    busy: list[tuple[str, tuple[str, ...]]] = []
    for rel, boxes in per_plan:
        stem = _stem_re(rel)
        busy.extend(
            ("%s in flight" % (box.id or box.sig), box.owns)
            for box in boxes
            if box.owns
            and any(
                r.get("state") == ">" and _names_box(str(r.get("text") or ""), stem, box)
                for r in tracking
            )
        )
    live = {pathlib.Path(str(p)).name for p in live_plans or ()}
    for base in sorted(live):
        found = next((r for r in graph.by_base.get(base, []) if not graph.plans[r].stub), None)
        owns = graph.plans[found].header.owns if found else None
        if owns is not None and not owns.none:
            busy.append(("%s (a live writer's plan)" % base, tuple(owns.globs)))
    clear = _writer_clear(root)
    ready: list[ReadyBox] = []
    skipped: list[Skip] = []
    for rel, boxes in per_plan:
        stem = _stem_re(rel)
        base = pathlib.Path(rel).name
        for box in boxes:
            if not writer_tagged(box.body):
                continue

            def skip(why, box=box, rel=rel):
                skipped.append(Skip(rel, box.sig, box.id, why))

            if post_merge(box.block):
                skip("post-merge")
                continue
            blockers = graph.box_blockers(rel, box.block, clear=clear) if rel in graph.plans else []
            if blockers:
                skip("waits on %s" % ", ".join("%s (%s)" % (t, why) for t, why in blockers[:3]))
                continue
            holder = next(
                (r for r in tracking if _names_box(str(r.get("text") or ""), stem, box)), None
            )
            if holder is not None:
                skip("tracked by #%s" % holder.get("id"))
                continue
            claims = [*busy, *(("%s named above" % (b.id or b.sig), b.owns) for b in ready)]
            claims = [(w, g) for w, g in claims if not w.startswith(base + " ")]
            clash = next(
                (
                    (who, hits[0][2])
                    for who, globs in claims
                    for hits in [wl_planconc.owns_overlap(box.owns, globs)]
                    if box.owns and hits
                ),
                None,
            )
            if clash is not None:
                skip("Owns overlap with %s at %s" % clash)
                continue
            ready.append(ReadyBox(rel, box.sig, box.id, box.shown, box.owns))
    return ready, skipped


def idle_capacity_text(
    root,
    *,
    free,
    cap,
    phase,
    turbo_picks=(),
    plans=None,
    live_plans=(),
    items=(),
    me8="",
    graph=None,
) -> str:
    """The IDLE CAPACITY block (D5), "" when it stands down: no free writer slot, a babysit or merge phase (`phase`), or no ready box. The plans TURBO NEXT named this stop (`turbo_picks`) are its business: their boxes are left out and each takes one of the free slots, so a single pick never silences twenty idle slots."""
    picked = {pathlib.Path(str(p)).name for p in turbo_picks or ()}
    free = int(free or 0) - len(picked)
    if phase or free < 1:
        return ""
    ready, _skipped = ready_boxes(root, plans, live_plans, items, graph)
    ready = [b for b in ready if pathlib.Path(b.rel).name not in picked]
    if not ready:
        return ""
    import worklist_messages as M

    rows = [
        M.IDLE_CAPACITY_BOX % (pathlib.Path(b.rel).name, b.sig, b.text[:110])
        for b in ready[:LIST_MAX]
    ]
    if len(ready) > LIST_MAX:
        rows.append(M.IDLE_CAPACITY_MORE % (len(ready) - LIST_MAX))
    order = list(dict.fromkeys(pathlib.Path(b.rel).name for b in ready))
    return M.V_IDLE_CAPACITY % {
        "free": int(free),
        "cap": int(cap),
        "n": len(ready),
        "boxes": "\n".join(rows),
        "spawn": "\n".join(M.IDLE_CAPACITY_SPAWN % base for base in order),
        "who": me8,
    }
