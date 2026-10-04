"""wl_planqueue: the format of `agent/plans/QUEUE.md` and the render of its generated half (operator rulings, /ask 2026-10-02, worklist #0f45b81d).

THE FILE HAS TWO LISTS. `## Promoted` is the operator's hand-ordered list: it comes first, in its own order, and no tool ever writes it. `## Generated` sits between GEN_BEGIN and GEN_END and is rendered here from the canonical plan order, so the loop always has a next plan even when nobody has promoted one. `rediacc_hooks.plan_gate.queue` reads Promoted, then Generated, through `entries`; this module is the one place that
knows the headings, the markers and the entry shape.

THE RENDER REPLACES ONLY THE MARKED BLOCK. Every byte outside GEN_BEGIN..GEN_END is copied through unchanged, which is how the Promoted list and the header prose survive every regeneration. A file without the markers gets a `## Generated` section appended, never a rewrite of what is already there.

THE ORDER (operator rulings 2026-10-02). A plan with no open box is never queued: a fully ticked plan is closed, not worked, and a plan with no box has nothing to work yet, so both are named under `### Not queued` inside the block, which `entries` does not read. The rest are ordered HELD LAST (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 6, worklist #93798daa): a `Status: held` plan after every unheld one, then by PROGRESS: in progress (a ticked box and an open one) before not started. A plan never precedes an unfinished plan it
needs, directly or transitively: a `Depends-On:` edge (a task ref `PLAN-x.md#T3` counts as its plan, `wl_plandeps.Graph.resolve`), or a sub-plan, `PLAN-<parent>.<suffix>.md`, which its parent needs first (`parent_of`; no other module models the relation). A prerequisite inherits the least-held value, the best tier and the best rank (`wl_planconc.rank`, given the sub-plan edges too) of everything that needs it, so it is pulled ahead of unrelated plans. A dependency cycle is broken at its
best-keyed member and named under `### Not queued`. Ties go to operator Priority, then AI Priority, then the path: this file is compared for equality in a clean CI checkout, where every mtime is the checkout's.

THE SUBJECTS are live plans directly under agent/plans (Status not in `wl_planfile.FINISHED_STATES`, not `removed`, stubs excluded), TRACKED ONLY: the file is a committed render, so another session's untracked draft must not enter it (`wl_store.agent_plan_files(root, tracked_only=True)`, the rule 9100e89f0 set for agent/INDEX.md). The dependency graph drops the same untracked files, so a draft cannot move a tracked plan's rank either.

Reads no environment variable. Heavy imports are lazy so `plan_gate` can read the format on the post-push path without loading the plan graph.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

QUEUE_REL = "agent/plans/QUEUE.md"
PROMOTED_HEADING = "## Promoted"
GENERATED_HEADING = "## Generated"
GEN_BEGIN = "<!-- queue:generated:begin -->"
GEN_END = "<!-- queue:generated:end -->"
# The list of live plans the render leaves out, inside the generated block. Its lines are bullets, never numbered entries, and `entries` stops reading at the heading.
NOT_QUEUED_HEADING = "### Not queued"
ALL_TICKED = "all boxes ticked: close it"
NO_BOXES = "no boxes yet: add boxes"
NOT_READ = "the plan file could not be read"
CYCLE = "dependency cycle %s: broken at %s, queued ahead of the rest of the cycle; fix the Depends-On lines"

# A queue entry: a numbered list item whose whole text is one plan path, optionally followed by ` -- <note>`. Prose lines naming a plan are not entries.
ENTRY = re.compile(
    r"^[ \t]*\d+[.)][ \t]+`?(agent/plans/PLAN-[A-Za-z0-9._-]+\.md)`?(?:[ \t]+--[ \t].*)?[ \t]*$",
    re.MULTILINE,
)
_HEADING = re.compile(r"(?m)^## ")
_BLOCK = re.compile(
    r"(?ms)^%s[ \t]*$\n?(.*?)^%s[ \t]*$" % (re.escape(GEN_BEGIN), re.escape(GEN_END))
)


def promoted_text(text: str) -> str:
    """The body of the `## Promoted` section: from its heading to the next `## ` heading or the generated block, "" when there is no such heading."""
    m = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    if not m:
        return ""
    rest = text[m.end() :]
    stops = [s.start() for s in (_HEADING.search(rest), re.search(re.escape(GEN_BEGIN), rest)) if s]
    return rest[: min(stops)] if stops else rest


def generated_text(text: str) -> str | None:
    """The text between the markers, None when the block is absent."""
    m = _BLOCK.search(text)
    return m.group(1) if m else None


def entries(text: str) -> tuple[list[str], list[str]]:
    """(promoted, generated) plan paths in file order. Numbered entries outside both sections are not read."""
    promoted = [m.group(1) for m in ENTRY.finditer(promoted_text(text))]
    block = (generated_text(text) or "").split(NOT_QUEUED_HEADING, 1)[0]
    generated = [m.group(1) for m in ENTRY.finditer(block)]
    return promoted, generated


def ordered(text: str) -> list[str]:
    """Promoted first, then Generated, each path once."""
    promoted, generated = entries(text)
    out: list[str] = []
    for rel in promoted + generated:
        if rel not in out:
            out.append(rel)
    return out


# ------------------------------------------------------------ the settings block
# agent/plans/PLAN-stop-hook-turbo.md D1/D2: `## Settings` above `## Promoted` holds ONE fenced block, info string `stop-hook`, of `key: value` lines with an optional ` -- <note>`. It is the single switchboard for the Stop hook; a reader that doubts anything falls back to the fail-safe value of the key (hook on, turbo off).

SETTINGS_HEADING = "## Settings"
SETTINGS_FENCE = "stop-hook"
BOOL_KEYS = ("stop_hook", "turbo", "cadence", "agent_hint", "agent_pushback", "judge")
INT_KEYS = ("batch_size", "plan_concurrency", "writer_cap")
# The render order of a new block.
SETTINGS_KEYS = (
    "stop_hook",
    "turbo",
    "batch_size",
    "plan_concurrency",
    "writer_cap",
    "cadence",
    "agent_hint",
    "agent_pushback",
    "judge",
)
NOTE_SEP = " -- "
_FIELD_NOTE = re.compile(r"[ \t]--[ \t]")
_SOLO = re.compile(r"[ \t]--[ \t]+solo[ \t]*$")


@dataclasses.dataclass(frozen=True)
class Settings:
    """The effective switches. `notes` maps a key to the note after ` -- ` on its line."""

    stop_hook: bool = True
    turbo: bool = False
    batch_size: int = 1
    plan_concurrency: int = 1
    writer_cap: int = 4
    cadence: bool = True
    agent_hint: bool = True
    agent_pushback: bool = True
    judge: bool = True
    notes: dict = dataclasses.field(default_factory=dict)


_DEFAULTS = Settings()


def _value(key: str, raw: str):
    """The typed value of `raw` for `key`; ValueError names what was expected."""
    raw = raw.strip()
    if key in BOOL_KEYS:
        if raw not in ("on", "off"):
            raise ValueError("%s: expected on|off, got %r" % (key, raw))
        return raw == "on"
    if key in INT_KEYS:
        if not re.fullmatch(r"[0-9]+", raw) or int(raw) < 1:
            raise ValueError("%s: expected an integer >= 1, got %r" % (key, raw))
        return int(raw)
    raise ValueError("unknown key %r (known: %s)" % (key, ", ".join(SETTINGS_KEYS)))


def _split_line(line: str) -> tuple[str, str, str | None] | None:
    """(key, value, note) of one fence line; None for a blank line or a line without a colon."""
    body = line.strip()
    if not body:
        return None
    note = None
    m = _FIELD_NOTE.search(body)
    if m:
        body, note = body[: m.start()], body[m.end() :].strip()
    if ":" not in body:
        return None
    key, _sep, value = body.partition(":")
    return key.strip(), value.strip(), note


def _scan(text: str):
    """(block, structural problems). `block` is (body_start, body_end) as character offsets of the lines between the fences of the one accepted `stop-hook` fence, or None; `body_start` of an absent section is None too.

    Structural problems: the section below `## Promoted`, a second `stop-hook` fence anywhere, an unterminated fence, a section with no fence."""
    problems: list[str] = []
    head = re.search(r"(?m)^%s[ \t]*$" % re.escape(SETTINGS_HEADING), text)
    prom = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    lo = hi = -1
    if head:
        if prom and head.start() > prom.start():
            problems.append(
                "`%s` sits below `%s`; move it above" % (SETTINGS_HEADING, PROMOTED_HEADING)
            )
        else:
            rest = text[head.end() :]
            stops = [
                x.start()
                for x in (_HEADING.search(rest), re.search(re.escape(GEN_BEGIN), rest))
                if x
            ]
            lo, hi = head.end(), head.end() + (min(stops) if stops else len(rest))
    blocks: list[
        tuple[int, int, int]
    ] = []  # (fence line start, body start, body end), in file order
    pos = 0
    opened: tuple[str, int, int] | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if opened is None and stripped.startswith("```"):
            opened = (stripped[3:].strip(), pos, pos + len(line))
        elif opened is not None and stripped == "```":
            if opened[0] == SETTINGS_FENCE:
                blocks.append((opened[1], opened[2], pos))
            opened = None
        pos += len(line)
    if opened is not None and opened[0] == SETTINGS_FENCE:
        problems.append("a `%s` fence is not closed" % SETTINGS_FENCE)
    inside = [b for b in blocks if lo >= 0 and lo <= b[0] < hi]
    outside = [b for b in blocks if b not in inside]
    if outside:
        problems.append(
            "a `%s` fence outside `%s` is ignored; the block belongs in that section"
            % (SETTINGS_FENCE, SETTINGS_HEADING)
        )
    if len(inside) > 1:
        problems.append(
            "a second `%s` fence in `%s` is ignored; one block only"
            % (SETTINGS_FENCE, SETTINGS_HEADING)
        )
    if lo >= 0 and not inside:
        problems.append("`%s` has no `%s` fence" % (SETTINGS_HEADING, SETTINGS_FENCE))
    block = (inside[0][1], inside[0][2]) if inside else None
    return block, problems


def _parse(text: str) -> tuple[Settings, list[str], set[str]]:
    """(settings, problems, the keys the block set validly)."""
    block, problems = _scan(text)
    problems = list(problems)
    found: dict[str, list[tuple[str, str | None]]] = {}
    if block:
        for line in text[block[0] : block[1]].splitlines():
            row = _split_line(line)
            if row is None:
                if line.strip():
                    problems.append("not a `key: value` line: %r" % line.strip())
                continue
            found.setdefault(row[0], []).append((row[1], row[2]))
    values: dict = {}
    notes: dict = {}
    for key, rows in found.items():
        if key not in SETTINGS_KEYS:
            problems.append("unknown key %r (known: %s)" % (key, ", ".join(SETTINGS_KEYS)))
        elif len(rows) > 1:
            problems.append("%s: set %d times; the default is used" % (key, len(rows)))
        else:
            try:
                values[key] = _value(key, rows[0][0])
            except ValueError as exc:
                problems.append(str(exc))
                continue
            if rows[0][1]:
                notes[key] = rows[0][1]
    return dataclasses.replace(_DEFAULTS, notes=notes, **values), problems, set(values)


def settings(text: str) -> tuple[Settings, list[str]]:
    """The effective settings of a QUEUE.md text and the problems found. A missing section is all defaults and no problem; a bad key or value falls back to that key's default and the rest still parse."""
    got, problems, _set = _parse(text)
    return got, ["%s: %s" % (QUEUE_REL, p) for p in problems]


def sources(text: str) -> dict[str, str]:
    """Per key, `QUEUE.md` when the block sets it validly, else `default`."""
    _got, _problems, present = _parse(text)
    return {k: "QUEUE.md" if k in present else "default" for k in SETTINGS_KEYS}


def settings_for(root, rev: str = "") -> tuple[Settings, list[str]]:
    """`settings` over the working tree's QUEUE.md, or over `git show <rev>:agent/plans/QUEUE.md`. An absent working-tree file is all defaults (fixtures, other checkouts); an unreadable file or an unreadable rev is defaults and a problem."""
    root = pathlib.Path(root)
    if rev:
        import subprocess  # noqa: PLC0415

        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "show", "%s:%s" % (rev, QUEUE_REL)],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _DEFAULTS, ["%s at %s is unreadable: %s" % (QUEUE_REL, rev, exc)]
        if proc.returncode != 0:
            return _DEFAULTS, [
                "%s at %s is unreadable: %s" % (QUEUE_REL, rev, proc.stderr.strip()[:160])
            ]
        return settings(proc.stdout)
    path = root / QUEUE_REL
    if not path.exists():
        return _DEFAULTS, []
    try:
        return settings(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return _DEFAULTS, ["%s is unreadable: %s" % (QUEUE_REL, exc)]


def _line(key: str, value, note: str | None) -> str:
    shown = ("on" if value else "off") if key in BOOL_KEYS else str(value)
    return "%s: %s%s" % (key, shown, (NOTE_SEP + note) if note else "")


def set_settings(text: str, updates: dict[str, str], note: str | None = None) -> str:
    """`text` with `updates` ({key: raw value}) written into the settings fence. Only the fence's lines change: an updated key's line is replaced (later duplicates of it dropped), a key the block lacks is appended, every other byte stays. An absent section is created above `## Promoted` with every key of SETTINGS_KEYS in order.

    `note` is attached to every updated key. Without it, an updated key keeps its note when its value is unchanged and loses it when the value changes (a stale reason is worse than none). ValueError, nothing written, for an unknown key, a bad value, a multi-line note, or a structurally broken block (section below Promoted, a second or unclosed fence)."""
    typed = {k: _value(k, v) for k, v in updates.items()}
    if note is not None:
        note = note.strip()
        if "\n" in note or "\r" in note:
            raise ValueError("a note is one line")
    block, structural = _scan(text)
    if structural:
        raise ValueError("; ".join(structural))
    cur, _problems = settings(text)
    notes = cur.notes

    def note_for(key: str) -> str | None:
        if note is not None:
            return note
        return notes.get(key) if typed[key] == getattr(cur, key) else None

    if block is None:
        merged = {k: typed.get(k, getattr(_DEFAULTS, k)) for k in SETTINGS_KEYS}
        lines = [_line(k, merged[k], note_for(k) if k in typed else None) for k in SETTINGS_KEYS]
        section = "%s\n\n```%s\n%s\n```\n\n" % (SETTINGS_HEADING, SETTINGS_FENCE, "\n".join(lines))
        prom = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
        if prom:
            return text[: prom.start()] + section + text[prom.start() :]
        sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + section.rstrip("\n") + "\n"
    out: list[str] = []
    done: set[str] = set()
    for line in text[block[0] : block[1]].splitlines(keepends=True):
        row = _split_line(line)
        if row is not None and row[0] in typed:
            if row[0] not in done:
                done.add(row[0])
                out.append(_line(row[0], typed[row[0]], note_for(row[0])) + "\n")
            continue
        out.append(line)
    out.extend(
        _line(key, typed[key], note_for(key)) + "\n"
        for key in SETTINGS_KEYS
        if key in typed and key not in done
    )
    return text[: block[0]] + "".join(out) + text[block[1] :]


def solo_plans(text: str) -> set[str]:
    """The Promoted and Generated entries whose note ends with ` -- solo`: such a plan runs alone in its PR under turbo."""
    block = (generated_text(text) or "").split(NOT_QUEUED_HEADING, 1)[0]
    return {
        m.group(1)
        for body in (promoted_text(text), block)
        for m in ENTRY.finditer(body)
        if _SOLO.search(m.group(0))
    }


# ---------------------------------------------------------------- the render


@dataclasses.dataclass(frozen=True)
class Row:
    """One queued plan: its path, Status, `(blocked, held, op, ai)` with the held value and the rank inherited from its dependents, and its box counts."""

    rel: str
    status: str
    key: tuple[int, int, int, int]
    done: int
    opened: int


@dataclasses.dataclass(frozen=True)
class Queue:
    """The render's input: `rows` in queue order, and `skipped`, the `### Not queued` lines as (plan path or "", reason)."""

    rows: tuple[Row, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


def box_counts(path: pathlib.Path) -> tuple[int, int] | None:
    """(open, done) by `rediacc_hooks.plan_gate.open_boxes`' rule: the parser's count against the raw line count, the larger open count wins. None when the file cannot be read."""
    import wl_planfile  # noqa: PLC0415

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parsed_open, parsed_done = wl_planfile.plan_boxes(text)
    raw_open, raw_done = wl_planfile.raw_box_counts(text)
    return max(len(parsed_open), raw_open), max(len(parsed_done), raw_done)


def parent_of(rel: str, graph) -> str | None:
    """The live plan a sub-plan belongs to: `PLAN-<parent>.<suffix>.md` is a part of `PLAN-<parent>.md`, the longest such parent first. None for a plan that is no part."""
    import wl_plandeps as D  # noqa: PLC0415

    stem = rel.rsplit("/", 1)[-1][: -len(".md")]
    while "." in stem:
        stem = stem.rsplit(".", 1)[0]
        target = graph.resolve(stem + ".md")
        if target.state == D.LIVE and target.rel != rel:
            return target.rel
    return None


def _reach(start: str, succ: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(succ.get(start, ()))
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack.extend(succ.get(cur, ()))
    return seen


def _cycle_path(start: str, succ: dict[str, set[str]]) -> list[str]:
    """The shortest closed path start -> ... -> start over `succ`, ties broken by path order."""
    queue = [[start]]
    seen = {start}
    while queue:
        path = queue.pop(0)
        for nxt in sorted(succ.get(path[-1], ())):
            if nxt == start:
                return [*path, start]
            if nxt not in seen:
                seen.add(nxt)
                queue.append([*path, nxt])
    return [start, start]


def break_cycles(prereqs: dict[str, set[str]], key) -> list[tuple[list[str], str]]:
    """Make `prereqs` acyclic IN PLACE. Each strongly connected group loses the in-group edges of its best-keyed member, which is then queued first; repeated until no cycle is left. Returns [(closed cycle path, the member it was broken at)]."""
    broken: list[tuple[list[str], str]] = []
    while True:
        reach = {rel: _reach(rel, prereqs) for rel in prereqs}
        cyclic = sorted((rel for rel in prereqs if rel in reach[rel]), key=key)
        if not cyclic:
            return broken
        brk = cyclic[0]
        group = {rel for rel in reach[brk] if brk in reach[rel]}
        broken.append((_cycle_path(brk, prereqs), brk))
        prereqs[brk] -= group


def live_plans(root) -> Queue:
    """The queue over the tracked live plans: no plan without an open box, a prerequisite before every plan that needs it, then (held, progress tier, op, ai, path)."""
    import heapq  # noqa: PLC0415

    import wl_planconc as X  # noqa: PLC0415
    import wl_plandeps as D  # noqa: PLC0415 -- the graph is loaded only for a render
    import wl_planfile  # noqa: PLC0415
    import wl_store  # noqa: PLC0415

    root = pathlib.Path(root)
    tracked = {
        p.relative_to(root).as_posix() for p in wl_store.agent_plan_files(root, tracked_only=True)
    }
    untracked = {p.relative_to(root).as_posix() for p in wl_store.agent_plan_files(root)} - tracked
    full = D.Graph.load(root)
    graph = D.Graph(
        {r: t for r, t in full.texts.items() if r not in untracked}, full.index_text, root
    )
    found: dict[str, tuple[str, int, int]] = {}
    skipped: list[tuple[str, str]] = []
    for rel, info in graph.plans.items():
        status = info.header.status
        if (
            rel not in tracked
            or info.folder != D.PLANS_DIR
            or info.stub
            or status in wl_planfile.FINISHED_STATES
            or status == D.REMOVED_STATUS
        ):
            continue
        counts = box_counts(root / rel)
        if counts is None:
            skipped.append((rel, NOT_READ))
        elif counts[0] == 0:
            skipped.append((rel, ALL_TICKED if counts[1] else NO_BOXES))
        else:
            found[rel] = (status, counts[1], counts[0])

    # The edges: every Depends-On (a task ref `PLAN-x.md#T3` resolves to its plan, `wl_plandeps.Graph.resolve`) and every sub-plan, which its parent needs first.
    rev = X._dependents(graph)
    parents = {rel: parent_of(rel, graph) for rel in graph.plans if graph.is_required(rel)}
    for sub, parent in parents.items():
        if parent is not None and graph.is_required(parent):
            rev.setdefault(sub, set()).add(parent)
    prereqs: dict[str, set[str]] = {rel: set() for rel in found}
    for prereq, dependents in rev.items():
        for rel in dependents:
            if rel in found and prereq in found:
                prereqs[rel].add(prereq)

    # A prerequisite inherits the least-held value, the best progress tier and the best rank (`wl_planconc.rank`) of everything that needs it, so a held prerequisite of an unheld plan is not pushed behind the unheld plans.
    def tier(rel: str) -> int:
        return 0 if found[rel][1] else 1

    def held(rel: str) -> int:
        return 1 if found[rel][0] == X.HELD_STATUS else 0

    keys: dict[str, tuple] = {}
    for rel in found:
        needs_it = [d for d in _reach(rel, rev) if d in found]
        least_held = min([held(rel)] + [held(d) for d in needs_it])
        best = min([tier(rel)] + [tier(d) for d in needs_it])
        keys[rel] = (least_held, best, *X.rank(rel, graph, rev), rel)
    cycles = break_cycles(prereqs, keys.__getitem__)

    needers: dict[str, set[str]] = {rel: set() for rel in found}
    for rel, pres in prereqs.items():
        for pre in pres:
            needers[pre].add(rel)
    waiting = {rel: set(pres) for rel, pres in prereqs.items()}
    heap = [keys[rel] for rel in found if not waiting[rel]]
    heapq.heapify(heap)
    rows: list[Row] = []
    while heap:
        rel = heapq.heappop(heap)[-1]
        status, done, opened = found[rel]
        is_held, _tier, op, ai, _rel = keys[rel]
        blocked = 1 if graph.roots(rel) or prereqs[rel] else 0
        rows.append(Row(rel, status, (blocked, is_held, op, ai), done, opened))
        for nxt in sorted(needers[rel]):
            waiting[nxt].discard(rel)
            if not waiting[nxt]:
                heapq.heappush(heap, keys[nxt])
    skipped.sort()
    for path, brk in cycles:
        names = " -> ".join(r.rsplit("/", 1)[-1] for r in path)
        skipped.append(("", CYCLE % (names, brk.rsplit("/", 1)[-1])))
    return Queue(tuple(rows), tuple(skipped))


def note(row: Row) -> str:
    """`P1 (operator), approved, in progress (2 of 5 boxes ticked)`, `P3, held, not started`, with `, dep-blocked` while a dependency is still open."""
    blocked, _held, op, ai = row.key
    if op < 4:
        rank = "P%d (operator)" % op
    elif ai < 4:
        rank = "P%d" % ai
    else:
        rank = "P- (no Priority)"
    progress = (
        "in progress (%d of %d boxes ticked)" % (row.done, row.done + row.opened)
        if row.done
        else "not started"
    )
    return "%s, %s, %s%s" % (
        rank,
        row.status or "no Status",
        progress,
        ", dep-blocked" if blocked else "",
    )


def render_block(queue: Queue, exclude) -> str:
    """The numbered lines between the markers, then the `### Not queued` list. Promoted entries are left out of both."""
    skip = set(exclude)
    keep = [r for r in queue.rows if r.rel not in skip]
    out = "".join("%d. %s -- %s\n" % (i, r.rel, note(r)) for i, r in enumerate(keep, 1))
    if not keep:
        out = "(no live plan outside Promoted)\n"
    lines = [
        "- %s -- %s\n" % (rel, why) if rel else "- %s\n" % why
        for rel, why in queue.skipped
        if rel not in skip
    ]
    if lines:
        out += "\n%s\n\n%s" % (NOT_QUEUED_HEADING, "".join(lines))
    return out


def render(text: str, queue: Queue) -> str:
    """`text` with its generated block replaced by the render over `queue`. Every byte outside the block is kept."""
    promoted, _gen = entries(text)
    block = "%s\n%s%s" % (GEN_BEGIN, render_block(queue, promoted), GEN_END)
    m = _BLOCK.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    sep = "" if text.endswith("\n\n") or not text else ("\n" if text.endswith("\n") else "\n\n")
    return "%s%s%s\n\n%s\n" % (text, sep, GENERATED_HEADING, block)


SKELETON = (
    "# Plan queue\n\n"
    "`## Promoted` is hand-ordered and wins; `## Generated` is rendered between the markers.\n\n"
    "%s\n\n" % PROMOTED_HEADING
)


def want(root) -> tuple[str, str]:
    """(on-disk text, rendered text). An absent file renders from SKELETON."""
    path = pathlib.Path(root) / QUEUE_REL
    try:
        got = path.read_text(encoding="utf-8")
    except OSError:
        got = ""
    return got, render(got or SKELETON, live_plans(root))


def refresh(root) -> bool:
    """Rewrite the generated block of an EXISTING queue file; True when it changed. A root with no queue file is left without one (fixtures, other checkouts)."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return False
    got, new = want(root)
    if got == new:
        return False
    import wl_planrec as R  # noqa: PLC0415 -- the one atomic writer

    R.write_atomic(path, new)
    return True


def problems(root, update: bool = False) -> list[str]:
    """The freshness check: [] when the file equals its render. `update` writes the render (creating the file from SKELETON when absent) instead of reporting."""
    got, new = want(root)
    if got == new:
        return []
    if update:
        import wl_planrec as R  # noqa: PLC0415

        R.write_atomic(pathlib.Path(root) / QUEUE_REL, new)
        print("✓ wrote %s" % QUEUE_REL)
        return []
    what = "is absent" if not got else "has a generated section that differs from the render"
    return [
        "%s %s (the plan order changed, or the section was edited by hand). Regenerate and commit it:\n"
        "      npm run check:ci-plan-record -- --update\n"
        "      git add %s" % (QUEUE_REL, what, QUEUE_REL)
    ]
