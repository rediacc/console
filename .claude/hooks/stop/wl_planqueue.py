"""wl_planqueue: the format of `agent/plans/QUEUE.md` and the render of its generated half (operator rulings, /ask 2026-10-02, worklist #0f45b81d).

THE FILE HAS TWO LISTS.
`## Promoted` is the operator's hand-ordered list: it comes first, in its own order, and no tool adds, reorders or edits its entries. The ONE exception is retirement (worklist #7b9fe4f1): when `check_plan_folders.py --move` moves a plan into `_done/` or `_removed/`, `retire_promoted` removes that plan's entry and renumbers the rest, and `--retire-promoted` does the same for every entry already naming a moved stub; nothing else in the section changes. The one generated part of that section is the progress block between PROGRESS_BEGIN and PROGRESS_END directly under its heading (operator 2026-10-08, worklist #1420d4b8): an overall line and a done/total box ratio per entry, keyed by the entry's own number, so the hand-written lines are never touched and `entries` never reads a progress row. `## Generated` sits between GEN_BEGIN and GEN_END and is rendered here from the canonical plan order, so the loop always has a next plan even when nobody has promoted one. `rediacc_hooks.plan_gate.queue` reads Promoted, then Generated, through `entries`; this module is the one place that
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
import importlib
import importlib.util
import pathlib
import re

import wl_effort

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
# The generated progress block under `## Promoted`. Its rows are table lines, never numbered entries, and `promoted_text` drops the whole block before any entry is read.
PROGRESS_BEGIN = "<!-- queue:progress:begin -->"
PROGRESS_END = "<!-- queue:progress:end -->"
_PROG_BLOCK = re.compile(
    r"(?ms)^%s[ \t]*$\n?(.*?)^%s[ \t]*$" % (re.escape(PROGRESS_BEGIN), re.escape(PROGRESS_END))
)


def promoted_text(text: str) -> str:
    """The body of the `## Promoted` section: from its heading to the next `## ` heading or the generated block, "" when there is no such heading."""
    m = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    if not m:
        return ""
    rest = _PROG_BLOCK.sub("", text[m.end() :])
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
# agent/plans/PLAN-stop-hook-turbo.md D1/D2: `## Settings` above `## Promoted` holds ONE fenced block, info string `stop-hook`, of `key: value` lines with an optional ` -- <note>`. It is the single switchboard for the Stop hook; a reader that doubts anything falls back to the fail-safe value of the key.
#
# agent/plans/PLAN-stop-hook-effort.md: the block names ONE `effort` level, and every other value resolves as effort -> that level's bundle in .claude/config/effort.json (`wl_effort.bundle`) -> an explicit line in the fence, which wins. A missing or bad `effort:` line is `high` (wl_effort.FAILSAFE): every check, as before the dial existed. There is no off switch; `effort: quiet` keeps only the FLOOR (wl_floor).

SETTINGS_HEADING = "## Settings"
SETTINGS_FENCE = "stop-hook"
EFFORT_KEY = "effort"
BOOL_KEYS = ("turbo", "cadence", "agent_hint", "agent_pushback")
INT_KEYS = ("batch_size", "plan_concurrency", "writer_cap", "commit_remind_min", "backup_push_h")
# Integer keys for which 0 is a value (it turns the feature off) rather than a typo.
ZERO_OK_KEYS = ("backup_push_h",)
# Keys whose value is one word from a fixed set (agent/plans/PLAN-turbo-local-first.md LF-W1; the effort plan's levels and judge modes).
CHOICE_KEYS = {
    EFFORT_KEY: wl_effort.LEVELS,
    "turbo_push": ("batch-end", "pr"),
    "judge": wl_effort.JUDGE_MODES,
}
# The fence keys, in the render order of a new block and of the in-flight mode line: the level, then the switches a level's bundle sets that the operator overrides in practice. A literal tuple: check:ci-scope-mirrors reads it as the oracle of CLAUDE.md's `pr.queue-switches` list.
SETTINGS_KEYS = (
    "effort",
    "turbo",
    "turbo_push",
    "batch_size",
    "plan_concurrency",
    "writer_cap",
    "commit_remind_min",
    "backup_push_h",
    "judge",
)
# Bundle switches that are no longer fence keys of their own and survive only as an explicit override line: the level decides them.
OVERRIDE_ONLY_KEYS = ("cadence", "agent_hint", "agent_pushback")
KNOWN_KEYS = SETTINGS_KEYS + OVERRIDE_ONLY_KEYS
NOTE_SEP = " -- "
_FIELD_NOTE = re.compile(r"[ \t]--[ \t]")
_SOLO = re.compile(r"[ \t]--[ \t]+solo[ \t]*$")


@dataclasses.dataclass(frozen=True)
class Settings:
    """The effective switches, resolved from the effort level, its bundle and the fence's overrides. `notes` maps a key to the note after ` -- ` on its line. The field defaults are the `high` bundle, the fail-safe level."""

    effort: str = wl_effort.FAILSAFE
    turbo: bool = False
    # Under turbo, when the batch is pushed (agent/plans/PLAN-turbo-local-first.md): `batch-end` holds every commit locally until the batch completes, then pushes and opens the PR once; `pr` is the earlier behaviour, a PR open while the batch fills. Read only when turbo is on.
    turbo_push: str = "batch-end"
    batch_size: int = 1
    plan_concurrency: int = 1
    writer_cap: int = 4
    # Minutes without a commit, with this session's own edits still uncommitted, before the commit reminder speaks (PLAN-fast-loop.md Part 2). A reminder, never a block.
    commit_remind_min: int = 15
    # Hours the oldest unpushed commit may age before the hook advises a backup push with no PR (PLAN-turbo-local-first.md D4); 0 turns the advisory off.
    backup_push_h: int = 4
    # `off`, `core` (the judge without riders: no regression sweep, deferral audit, settle or admission sections) or `full`.
    judge: str = "full"
    cadence: bool = True
    agent_hint: bool = True
    agent_pushback: bool = True
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
        floor = 0 if key in ZERO_OK_KEYS else 1
        if not re.fullmatch(r"[0-9]+", raw) or int(raw) < floor:
            raise ValueError("%s: expected an integer >= %d, got %r" % (key, floor, raw))
        return int(raw)
    if key in CHOICE_KEYS:
        if raw not in CHOICE_KEYS[key]:
            raise ValueError("%s: expected %s, got %r" % (key, "|".join(CHOICE_KEYS[key]), raw))
        return raw
    raise ValueError("unknown key %r (known: %s)" % (key, ", ".join(KNOWN_KEYS)))


def resolve(level: str, overrides: dict) -> tuple[Settings, list[str]]:
    """(settings, problems) for `level` with `overrides` ({key: typed value}) on top of its bundle. A bundle value that does not type-check is dropped with a problem, so the field keeps the fail-safe default."""
    problems: list[str] = []
    table, why = wl_effort.load()
    if why:
        problems.append(why)
    values: dict = {}
    for key, raw in wl_effort.bundle(level, table).items():
        if key not in KNOWN_KEYS or key == EFFORT_KEY:
            problems.append("%s: bundle %s sets unknown key %r" % (wl_effort.TABLE_REL, level, key))
            continue
        shown = ("on" if raw else "off") if isinstance(raw, bool) else str(raw)
        try:
            values[key] = _value(key, shown)
        except ValueError as exc:
            problems.append("%s: bundle %s: %s" % (wl_effort.TABLE_REL, level, exc))
    values.update(overrides)
    values[EFFORT_KEY] = level
    return dataclasses.replace(_DEFAULTS, **values), problems


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
        if key not in KNOWN_KEYS:
            problems.append("unknown key %r (known: %s)" % (key, ", ".join(KNOWN_KEYS)))
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
    effort_set = EFFORT_KEY in values
    level = values.pop(EFFORT_KEY, wl_effort.FAILSAFE)
    got, resolved = resolve(level, values)
    present = set(values) | ({EFFORT_KEY} if effort_set else set())
    return dataclasses.replace(got, notes=notes), problems + resolved, present


def settings(text: str) -> tuple[Settings, list[str]]:
    """The effective settings of a QUEUE.md text and the problems found. A missing section is all defaults and no problem; a bad key or value falls back to that key's default and the rest still parse."""
    got, problems, _set = _parse(text)
    return got, ["%s: %s" % (QUEUE_REL, p) for p in problems]


def sources(text: str) -> dict[str, str]:
    """Per key, where its value came from: `QUEUE.md` when the block sets it validly, `effort <level>` when the level's bundle does, else `default`."""
    got, _problems, present = _parse(text)
    bundled = wl_effort.bundle(got.effort)
    return {
        k: "QUEUE.md" if k in present else "effort %s" % got.effort if k in bundled else "default"
        for k in KNOWN_KEYS
    }


def settings_for(root, rev: str = "") -> tuple[Settings, list[str]]:
    """`settings` over the working tree's QUEUE.md, or over `git show <rev>:agent/plans/QUEUE.md`. An absent working-tree file is all defaults (fixtures, other checkouts); an unreadable file or an unreadable rev is defaults and a problem."""
    root = pathlib.Path(root)
    if rev:
        import subprocess

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
    """`text` with `updates` ({key: raw value}) written into the settings fence. Only the fence's lines change: an updated key's line is replaced (later duplicates of it dropped), a key the block lacks is appended, every other byte stays. An EMPTY value removes the key's line, so the level's bundle decides it again. An absent section is created above `## Promoted` with the `effort` line and the updated keys.

    `note` is attached to every updated key. Without it, an updated key keeps its note when its value is unchanged and loses it when the value changes (a stale reason is worse than none). ValueError, nothing written, for an unknown key, a bad value, a multi-line note, or a structurally broken block (section below Promoted, a second or unclosed fence)."""
    drop = {k for k, v in updates.items() if not str(v).strip()}
    for key in drop:
        if key not in KNOWN_KEYS:
            raise ValueError("unknown key %r (known: %s)" % (key, ", ".join(KNOWN_KEYS)))
    typed = {k: _value(k, v) for k, v in updates.items() if k not in drop}
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
        merged = dict(typed)
        merged.setdefault(EFFORT_KEY, wl_effort.FAILSAFE)
        lines = [
            _line(k, merged[k], note_for(k) if k in typed else None)
            for k in KNOWN_KEYS
            if k in merged
        ]
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
        if row is not None and row[0] in drop:
            continue
        if row is not None and row[0] in typed:
            if row[0] not in done:
                done.add(row[0])
                out.append(_line(row[0], typed[row[0]], note_for(row[0])) + "\n")
            continue
        out.append(line)
    out.extend(
        _line(key, typed[key], note_for(key)) + "\n"
        for key in KNOWN_KEYS
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
    import wl_planfile

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parsed_open, parsed_done = wl_planfile.plan_boxes(text)
    raw_open, raw_done = wl_planfile.raw_box_counts(text)
    return max(len(parsed_open), raw_open), max(len(parsed_done), raw_done)


def parent_of(rel: str, graph) -> str | None:
    """The live plan a sub-plan belongs to: `PLAN-<parent>.<suffix>.md` is a part of `PLAN-<parent>.md`, the longest such parent first. None for a plan that is no part."""
    import wl_plandeps as D

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
    import heapq

    import wl_planconc as X
    import wl_plandeps as D
    import wl_planfile
    import wl_store

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
    """(on-disk text, rendered text): the generated block and the Promoted progress block both rendered. An absent file renders from SKELETON."""
    path = pathlib.Path(root) / QUEUE_REL
    try:
        got = path.read_text(encoding="utf-8")
    except OSError:
        got = ""
    return got, render(with_fresh_progress(root, got or SKELETON), live_plans(root))


def refresh(root) -> bool:
    """Rewrite the generated block of an EXISTING queue file; True when it changed. A root with no queue file is left without one (fixtures, other checkouts)."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return False
    got, new = want(root)
    if got == new:
        return False
    import wl_planrec as R

    R.write_atomic(path, new)
    return True


def problems(root, update: bool = False) -> list[str]:
    """The freshness check: [] when the file equals its render. `update` writes the render (creating the file from SKELETON when absent) instead of reporting."""
    got, new = want(root)
    if got == new:
        return []
    if update:
        import wl_planrec as R

        R.write_atomic(pathlib.Path(root) / QUEUE_REL, new)
        print("✓ wrote %s" % QUEUE_REL)
        return []
    if not got:
        what = "is absent"
    else:
        stale = []
        if progress_text(got) != progress_text(new):
            stale.append(
                "a Promoted progress block that disagrees with the plans' boxes (a box was ticked or reopened, an entry was added or removed, or the block was edited by hand)"
            )
        if generated_text(got) != generated_text(new):
            stale.append(
                "a generated section that differs from the render (the plan order changed)"
            )
        what = "has " + " and ".join(stale or ["a rendered part that differs from the render"])
    return [
        "%s %s. Regenerate and commit it:\n"
        "      npm run check:ci-plan-record -- --update\n"
        "      git add %s" % (QUEUE_REL, what, QUEUE_REL)
    ]


# ------------------------------------------------------------ the Promoted progress block
# Operator order 2026-10-08 (worklist #1420d4b8): the `## Promoted` section shows the general progress of all its plans and a completed/all box ratio per plan, and the Stop hook keeps it current. The block sits directly under the `## Promoted` heading, between PROGRESS_BEGIN and PROGRESS_END: one overall line, then one table row per numbered entry carrying that entry's own number, its
# done/total box ratio and its state. Every count is read from the plan files by `rediacc_hooks.plan_gate.open_boxes`, the merge gate's rule (parser count against raw line count, a `Moved-To:` stub followed); an entry whose file is gone is looked for under `agent/plans/_done/`, the rule `block_turbo_early_push` uses. `.ci/config/plan-boxes.json` is the committed second reading of the same boxes and
# check:ci-plan-boxes holds it equal to the files, so the block cannot disagree with the registry without one of the two gates going red.
#
# A LEDGER, NOT RUNTIME STATE. Its inputs are tracked files, so a clean CI checkout reproduces it: `want` renders it and `problems` (check:ci-plan-record RQ) compares it, so a hand edit or a missed render is a finding. It self-heals locally: `refresh` (the plan verbs, through `wl_planrec.refresh_index`) and `refresh_inflight` (every Stop-hook run, `--queue-set` and `--phase`) both re-render it.

PROGRESS_DONE_DIR = "agent/plans/_done/"


@dataclasses.dataclass(frozen=True)
class EntryProgress:
    """One numbered Promoted entry: its number as written, its plan path, its open and done box counts, and `why` ("" when the counts are real, else why they could not be read)."""

    num: str
    rel: str
    opened: int
    done: int
    why: str = ""

    @property
    def total(self) -> int:
        return self.opened + self.done

    @property
    def finished(self) -> bool:
        """Every box ticked. A plan with no box is not finished: nothing proves it."""
        return not self.why and self.opened == 0 and self.done > 0


_ENTRY_NUM = re.compile(r"^[ \t]*(\d+)[.)]")


def promoted_numbered(text: str) -> list[tuple[str, str]]:
    """[(entry number as written, plan path)] of the Promoted entries in file order."""
    out = []
    for m in ENTRY.finditer(promoted_text(text)):
        num = _ENTRY_NUM.match(m.group(0))
        out.append((num.group(1) if num else "?", m.group(1)))
    return out


def _plan_gate():
    """`rediacc_hooks.plan_gate`, reached through the canonical `.claude` sys.path hop (`.claude/rediacc_hooks/syspath.py`, loaded by file because this module lives outside that package)."""
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if spec is None or spec.loader is None:
        msg = "cannot load %s" % helper
        raise ImportError(msg)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    return importlib.import_module("rediacc_hooks.plan_gate")


def entry_counts(root, rel: str, gate=None) -> tuple[int, int, str]:
    """(open, done, why) for one Promoted plan by `plan_gate.open_boxes`, with the `_done/` fallback for an entry whose file was moved out of agent/plans. A plan with no boxes reads as (0, 0, "") so it renders as "no boxes", not as unreadable."""
    pg = gate or _plan_gate()
    opened, done, why = pg.open_boxes(str(root), rel)
    if why and not (pathlib.Path(root) / rel).is_file():
        moved = PROGRESS_DONE_DIR + rel.rsplit("/", 1)[-1]
        if (pathlib.Path(root) / moved).is_file():
            opened, done, why = pg.open_boxes(str(root), moved)
    if why and "has no boxes" in why:
        return 0, 0, ""
    return opened, done, why


def promoted_progress(root, text: str) -> tuple[EntryProgress, ...]:
    """The progress of every numbered Promoted entry of `text`, counted against the plan files under `root`."""
    numbered = promoted_numbered(text)
    if not numbered:
        return ()
    gate = _plan_gate()
    cache: dict[str, tuple[int, int, str]] = {}
    out = []
    for num, rel in numbered:
        if rel not in cache:
            cache[rel] = entry_counts(root, rel, gate)
        opened, done, why = cache[rel]
        out.append(EntryProgress(num, rel, opened, done, why))
    return tuple(out)


def _state(row: EntryProgress) -> str:
    if row.why:
        return "unreadable: %s" % row.why.replace("|", "/")
    if row.total == 0:
        return "no boxes"
    if row.opened == 0:
        return "done"
    return "%d open" % row.opened


def render_progress(rows) -> str:
    """The lines between the progress markers: the overall line, then one table row per entry. Each plan counts once in the overall line, however many entries name it."""
    rows = tuple(rows)
    if not rows:
        return "Promoted: no entries.\n"
    unique: dict[str, EntryProgress] = {}
    for row in rows:
        unique.setdefault(row.rel, row)
    plans_done = sum(1 for r in unique.values() if r.finished)
    boxes_done = sum(r.done for r in unique.values() if not r.why)
    boxes_all = sum(r.total for r in unique.values() if not r.why)
    pct = "%d%%" % (boxes_done * 100 // boxes_all) if boxes_all else "no boxes"
    out = [
        "Promoted: %d of %d plans done, %d of %d boxes done (%s).\n"
        % (plans_done, len(unique), boxes_done, boxes_all, pct),
        "\n",
        "| # | Plan | Boxes done | State |\n",
        "|---|---|---|---|\n",
    ]
    for row in rows:
        ratio = "-" if row.why else "%d/%d" % (row.done, row.total)
        out.append(
            "| %s | %s | %s | %s |\n" % (row.num, row.rel.rsplit("/", 1)[-1], ratio, _state(row))
        )
    return "".join(out)


def progress_text(text: str) -> str | None:
    """The text between the progress markers, None when the block is absent."""
    m = _PROG_BLOCK.search(text)
    return m.group(1) if m else None


def with_progress(text: str, body: str) -> str:
    """`text` with its progress block holding `body`. A file without the block gains it directly under `## Promoted`, followed by one blank line; a file without that heading is returned unchanged. Every byte outside the block is kept, the hand-written entries included."""
    block = "%s\n%s%s" % (PROGRESS_BEGIN, body, PROGRESS_END)
    m = _PROG_BLOCK.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    h = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    if not h:
        return text
    tail = text[h.end() :]
    # Drop only the heading's own line break and the one blank line the block replaces: any further blank line belongs to the hand-written list.
    rest = tail[min(len(tail) - len(tail.lstrip("\n")), 2) :]
    return text[: h.end()] + "\n\n" + block + "\n" + ("\n" + rest if rest else "")


def without_progress(text: str) -> str:
    """`text` with its progress block and the blank line after it removed: the inverse of `with_progress`'s insertion, so the hand-written remainder can be compared byte for byte."""
    m = _PROG_BLOCK.search(text)
    if not m:
        return text
    end = m.end()
    end += 2 if text[end : end + 2] == "\n\n" else (1 if text[end : end + 1] == "\n" else 0)
    return text[: m.start()] + text[end:]


def with_fresh_progress(root, text: str) -> str:
    """`text` with its progress block re-rendered from the plan files under `root`."""
    if not re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text):
        return text
    return with_progress(text, render_progress(promoted_progress(root, text)))


# ------------------------------------------------------------ retiring a moved plan's Promoted entry
# Worklist #7b9fe4f1: `check_plan_folders.py --move` moved finished plans into `_done/` and left their numbered entries behind, so 13 of 17 Promoted entries named stubs, their notes still promising to leave "when PR #600 merges" after it had. A plan that has moved is finished or withdrawn, so its entry has nothing left to order. This is the ONE write any tool makes to the Promoted entries: an entry whose plan file is a moved stub (`wl_store.plan_stub_target`, both halves of
# the stub header) is removed, its indented continuation lines with it, and the entries left are renumbered 1..n in file order. Every other byte stays. `--move` calls it for the one plan it moved, `check_plan_folders.py --retire-promoted` for every stub entry, and check:ci-plan-record RQ-MOVED (`moved_problems`) refuses a queue that still holds one.

RETIRE_VERB = "python3 .ci/scripts/quality/check_plan_folders.py --retire-promoted"
_CONTINUATION = re.compile(r"^[ \t]+\S")
_NUMBER_NOTE = re.compile(r"\bentr(?:y|ies)[ \t]+\d+", re.IGNORECASE)


def _promoted_bounds(text: str) -> tuple[int, int] | None:
    """(start, end) of the Promoted section's body in `text` itself (the progress block included), None without the heading. The same stops as `promoted_text`: the next `## ` heading or the generated block."""
    m = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    if not m:
        return None
    rest = text[m.end() :]
    stops = [s.start() for s in (_HEADING.search(rest), re.search(re.escape(GEN_BEGIN), rest)) if s]
    return m.end(), m.end() + (min(stops) if stops else len(rest))


def without_promoted(text: str, rels) -> tuple[str, list[str]]:
    """(text, removed): `text` with every numbered Promoted entry whose plan path is in `rels` removed, with any indented continuation line directly under it, and the remaining entries renumbered 1..n. The progress block, prose lines and everything outside the section are copied through byte for byte; with nothing to remove the text comes back unchanged and unrenumbered."""
    rels = set(rels or ())
    bounds = _promoted_bounds(text) if rels else None
    if not bounds:
        return text, []
    start, end = bounds
    out: list[str] = []
    removed: list[str] = []
    kept = 0
    in_block = dropping = False
    for line in text[start:end].splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if bare.rstrip() == PROGRESS_BEGIN:
            in_block = True
        if in_block:
            out.append(line)
            in_block = bare.rstrip() != PROGRESS_END
            continue
        m = ENTRY.match(bare)
        if m and m.group(1) in rels:
            removed.append(m.group(1))
            dropping = True
            continue
        if m:
            kept += 1
            num = _ENTRY_NUM.match(line)
            out.append(line[: num.start(1)] + str(kept) + line[num.end(1) :] if num else line)
            dropping = False
            continue
        if dropping and _CONTINUATION.match(bare):
            continue
        dropping = False
        out.append(line)
    if not removed:
        return text, []
    return text[:start] + "".join(out) + text[end:], removed


def moved_entries(root, text: str) -> list[tuple[str, str, str]]:
    """[(number as written, plan path, Moved-To target)] of the Promoted entries whose plan file under `root` is a moved stub. A missing file is not a stub: the progress block already names it unreadable."""
    import wl_store

    out = []
    for num, rel in promoted_numbered(text):
        target = wl_store.plan_stub_target(pathlib.Path(root) / rel)
        if target:
            out.append((num, rel, target))
    return out


def number_notes(text: str) -> list[str]:
    """The Promoted plan paths whose note cites an entry by number ("depends on entry 14"): renumbering cannot fix prose, so a retirement names them for a reader to check."""
    out = []
    for m in ENTRY.finditer(promoted_text(text)):
        note = m.group(0).split(NOTE_SEP, 1)[1] if NOTE_SEP in m.group(0) else ""
        if _NUMBER_NOTE.search(note):
            out.append(m.group(1))
    return out


def retire_promoted(root, rels=None) -> list[tuple[str, str]]:
    """Remove the Promoted entries of an EXISTING queue file whose plan is a moved stub, renumber the rest and re-render the progress block; [(plan path, Moved-To target)] retired, [] when nothing was written. `rels` limits it to those plan paths (a named plan that is not a stub stays); None retires every stub entry. Re-reads the file just before replacing it and starts over (once) when another writer changed it in between, as `refresh_inflight` does, so a concurrent in-flight render is not undone by a stale copy."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return []
    import wl_planrec as R

    for _attempt in range(2):
        got = path.read_text(encoding="utf-8")
        moved = [
            (rel, target)
            for _num, rel, target in moved_entries(root, got)
            if rels is None or rel in rels
        ]
        if not moved:
            return []
        new, _removed = without_promoted(got, {rel for rel, _t in moved})
        if progress_text(new) is not None:
            new = with_fresh_progress(root, new)
        if path.read_text(encoding="utf-8") == got:
            R.write_atomic(path, new)
            return list(dict.fromkeys(moved))
    raise QueueContendedError(
        "%s changed under both reads; no Promoted entry was retired" % QUEUE_REL
    )


class QueueContendedError(RuntimeError):
    """retire_promoted gave up: another writer changed the queue file between its read and its write, twice. Raised rather than returning [] so a caller cannot report "retired 0" while stub entries remain (review 5d1b9889.2)."""


def moved_problems(root) -> list[str]:
    """check:ci-plan-record RQ-MOVED: one finding per Promoted entry whose plan is a moved stub. [] without a queue file (RQ already names that)."""
    try:
        text = (pathlib.Path(root) / QUEUE_REL).read_text(encoding="utf-8")
    except OSError:
        return []
    return [
        "RQ-MOVED: %s Promoted entry %s names %s, a stub moved to %s; a moved plan has nothing "
        "left to order, so its entry leaves the list. Retire it (the rest renumber, the progress "
        "block re-renders):\n      %s\n      git add %s"
        % (QUEUE_REL, num, rel, target, RETIRE_VERB, QUEUE_REL)
        for num, rel, target in moved_entries(root, text)
    ]


# ------------------------------------------------------------ the in-flight block
# Operator order 2026-10-06: "agent/plans/QUEUE.md should show the plans for the current 'working on it' ... valid for focus, turbo and other modes as well." `## In flight` sits between `## Settings` and `## Promoted` and answers what the loop is doing NOW: the effective switches, every active focus, the live branch and its PR, the PR's plan set with box progress and how
# each plan got there, the branch's work that belongs to no plan in that set, live writers and leased items, and the next plan with the reason it is next.
#
# RUNTIME STATE, NOT A LEDGER. Its inputs (the PR, the focus events, the roster, the leases) live outside the tracked tree, so a clean CI checkout cannot reproduce it, and it is never compared: `render` copies every byte outside the generated block, so `problems` and `--update` neither read nor rewrite this one (`test_inflight_block_is_never_compared_by_the_queue_gate` in .claude/rediacc_hooks/tests/test_wl_queue_settings.py proves both). `refresh_inflight` is its only writer: the Stop hook
# (`wl_checks.run_stop`) and the verbs that change a mode (`worklist.py --queue-set`, `--phase`) call it, and a merge or a branch cut is picked up by the stop that follows it. The block carries no clock, so a stop that changed nothing writes nothing. A stop renders its own session's writers; leases and focus events are read for every session.

INFLIGHT_HEADING = "## In flight"
INF_BEGIN = "<!-- queue:inflight:begin -->"
INF_END = "<!-- queue:inflight:end -->"
_INF_BLOCK = re.compile(
    r"(?ms)^%s[ \t]*$\n?(.*?)^%s[ \t]*$" % (re.escape(INF_BEGIN), re.escape(INF_END))
)
INFLIGHT_INTRO = (
    "What the loop is working on now, rendered between the markers by `.claude/hooks/stop/wl_planqueue.py` (`refresh_inflight`) on every stop and on every `worklist.py --queue-set` or `--phase`. "
    "It is runtime state: rewritten only when it changes, never compared by `npm run check:ci-plan-record`, and a committed copy is a snapshot from its commit."
)
# The labels the mode line is read back by (`inflight_mode`).
MODE_LABEL = "- Mode: "
FOCUS_LABEL = "- Phase: "
_LIST_MAX = 12


@dataclasses.dataclass(frozen=True)
class PlanLine:
    """A plan the live PR works: its path, how it joined the set, and its box counts (`total` is -1 when the plan could not be read)."""

    rel: str
    source: str
    done: int = 0
    total: int = 0


@dataclasses.dataclass(frozen=True)
class EpicLine:
    """An epic with work on this branch outside the PR's plan set. `plan` is "" when the epic names none."""

    id: str
    title: str
    plan: str = ""
    commits: int = 0
    open_items: int = 0


@dataclasses.dataclass(frozen=True)
class FocusLine:
    owner: str
    mode: str
    pr: str
    branch: str
    at: str
    expired: bool = False


@dataclasses.dataclass(frozen=True)
class InFlight:
    """Everything the block shows. `writers` is None when the live writers could not be counted."""

    settings: Settings = dataclasses.field(default_factory=Settings)
    focus: tuple[FocusLine, ...] = ()
    kind: str = ""
    branch: str = ""
    pr: int = 0
    reason: str = ""
    queue_head: str = ""
    plans: tuple[PlanLine, ...] = ()
    epics: tuple[EpicLine, ...] = ()
    session: str = ""
    writers: tuple[str, ...] | None = None
    leases: tuple[tuple[str, str, str], ...] = ()
    next_plan: str = ""
    next_why: str = ""
    next_when: str = ""


def inflight_text(text: str) -> str | None:
    """The text between the in-flight markers, None when the block is absent."""
    m = _INF_BLOCK.search(text)
    return m.group(1) if m else None


def _onoff(value: bool) -> str:
    return "on" if value else "off"


def mode_line(settings: Settings) -> str:
    """`- Mode: effort smart; turbo off; batch_size 3; ...`, every key of `KNOWN_KEYS` in order, as resolved."""
    parts = []
    for key in KNOWN_KEYS:
        value = getattr(settings, key)
        parts.append("%s %s" % (key, _onoff(value) if isinstance(value, bool) else value))
    return MODE_LABEL + "; ".join(parts) + "."


def inflight_mode(text: str) -> dict[str, str]:
    """The mode line of a rendered block read back as {key: value}, {} when there is none. Lets a reader (or a test) check the block against the settings it claims."""
    body = inflight_text(text) or ""
    for line in body.splitlines():
        if line.startswith(MODE_LABEL):
            out = {}
            for part in line[len(MODE_LABEL) :].rstrip(".").split(";"):
                key, _sp, value = part.strip().partition(" ")
                if key:
                    out[key] = value.strip()
            return out
    return {}


def _more(items: list[str], limit: int = _LIST_MAX) -> str:
    shown = ", ".join(items[:limit])
    return shown + (", and %d more" % (len(items) - limit) if len(items) > limit else "")


def render_inflight(inf: InFlight) -> str:
    """The lines between the in-flight markers."""
    out = [mode_line(inf.settings)]
    if inf.focus:
        out.append(
            FOCUS_LABEL
            + "; ".join(
                "%s on PR #%s (branch %s, session %s, since %s%s)"
                % (
                    f.mode,
                    f.pr or "?",
                    f.branch or "?",
                    f.owner,
                    f.at or "?",
                    ", past its 24-hour limit" if f.expired else "",
                )
                for f in inf.focus
            )
            + "."
        )
    else:
        out.append(FOCUS_LABEL + "build.")
    import wl_prscope as P

    if inf.kind == P.LIVE:
        out.append("- Branch: %s, PR #%d open." % (inf.branch, inf.pr))
    elif inf.kind == P.NO_PR:
        out.append("- Branch: %s, no PR yet." % inf.branch)
    elif inf.kind == P.MERGED:
        out.append(
            "- Branch: %s, PR #%d merged; the next branch is not cut yet." % (inf.branch, inf.pr)
        )
    elif inf.kind == P.ON_MAIN:
        out.append("- Branch: main, no live branch.")
    elif inf.kind == P.UNREADABLE:
        out.append("- Branch: %s, PR state unreadable." % (inf.branch or "?"))
    else:
        out.append("- Branch: %s, off the loop." % (inf.branch or "none"))
    if inf.reason:
        out.append("- Loop note: %s." % inf.reason.rstrip("."))
    if inf.plans:
        out.append("- Plans on the PR (%d):" % len(inf.plans))
        for p in inf.plans:
            boxes = "unreadable" if p.total < 0 else "%d of %d boxes ticked" % (p.done, p.total)
            out.append("  - %s -- %s, %s" % (p.rel, boxes, p.source))
    elif inf.kind == P.NO_PR and inf.queue_head:
        out.append(
            "- Plans on the PR: none yet. The push that opens this branch's PR writes the queue head, %s, as its `Plan:` line unless the body names a plan first."
            % inf.queue_head
        )
    else:
        out.append("- Plans on the PR: none.")
    if inf.epics:
        out.append("- Work outside the PR's plans (%d epic(s)):" % len(inf.epics))
        for e in inf.epics:
            where = "plan %s, outside the set" % e.plan if e.plan else "no plan"
            out.append(
                "  - epic %s, %s, %d commit(s) on the branch, %d open item(s): %s"
                % (e.id, where, e.commits, e.open_items, e.title or "(untitled)")
            )
    else:
        out.append("- Work outside the PR's plans: none.")
    if inf.writers is None:
        out.append("- Writers: not counted at this refresh.")
    else:
        ids = ["worker:%s" % w for w in inf.writers]
        out.append(
            "- Writers: %d live of writer_cap %d (session %s)%s"
            % (
                len(ids),
                inf.settings.writer_cap,
                inf.session or "?",
                ": %s." % _more(ids) if ids else ".",
            )
        )
    leases = ["#%s (worker:%s, %s)" % lease for lease in inf.leases]
    out.append("- Leased items: %d%s" % (len(leases), ": %s." % _more(leases) if leases else "."))
    if inf.next_plan:
        out.append(
            "- Next plan: %s, %s%s."
            % (inf.next_plan, inf.next_why, "; %s" % inf.next_when if inf.next_when else "")
        )
    else:
        out.append("- Next plan: none; the queue holds no plan with an open box.")
    return "\n".join(out) + "\n"


def with_inflight(text: str, body: str) -> str:
    """`text` with its in-flight block holding `body`. A file without the block gains `## In flight` before `## Promoted` (else before `## Generated`, else at the end); every other byte is kept."""
    block = "%s\n%s%s" % (INF_BEGIN, body, INF_END)
    m = _INF_BLOCK.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    section = "%s\n\n%s\n\n%s\n\n" % (INFLIGHT_HEADING, INFLIGHT_INTRO, block)
    for heading in (PROMOTED_HEADING, GENERATED_HEADING):
        h = re.search(r"(?m)^%s[ \t]*$" % re.escape(heading), text)
        if h:
            return text[: h.start()] + section + text[h.start() :]
    sep = "" if text.endswith("\n\n") or not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + section.rstrip("\n") + "\n"


def _plan_source(rel, loop, body, named) -> str:
    """How `rel` joined the live PR's plan set: the `Plan:` line, a turbo batch claim, an `Operational-Reason:` addition, a prerequisite, or the queue head standing in for a body with no `Plan:` line."""
    import wl_prscope as P

    plan_gate, _cp = P._hooks_pkg()
    listed = plan_gate.body_plans(body) if isinstance(body, str) else []
    if rel in loop.prereqs:
        return "a prerequisite pulled in (an unfinished `Depends-On:` of the set)"
    if not listed:
        if loop.kind == P.UNREADABLE:
            return "the queue head, standing in while the PR read fails"
        return "the queue head, standing in while the PR body names no `Plan:` line"
    if rel == listed[0]:
        return "the PR body's `Plan:` line"
    if rel in named:
        return "a turbo batch claim on the `Plan:` line"
    if plan_gate.has_operational_reason(body):
        return "added to the `Plan:` line under `Operational-Reason:`"
    return "the PR body's `Plan:` line"


def _branch_epic_commits(root, kind) -> dict[str, int]:
    """{epic id: commits} from the `PR-TASK:` trailers of the commits this branch adds over origin/main; {} on main, off the loop, or without git."""
    import wl_prscope as P

    if kind not in (P.LIVE, P.NO_PR, P.MERGED, P.UNREADABLE):
        return {}
    _pg, commit_policy = P._hooks_pkg()
    base = commit_policy.git(["merge-base", "origin/main", "HEAD"], cwd=str(root))
    if not base:
        return {}
    log = commit_policy.git(
        [
            "log",
            "--format=%(trailers:key=PR-TASK,valueonly,separator=%x2C)",
            "%s..HEAD" % base.strip(),
        ],
        cwd=str(root),
    )
    counts: dict[str, int] = {}
    for line in (log or "").splitlines():
        for raw in line.split(","):
            eid = raw.strip()
            if re.fullmatch(r"[0-9a-f]{6,32}", eid):
                counts[eid] = counts.get(eid, 0) + 1
    return counts


def gather_inflight(root, worklist, session_id, fold=None, loop=None, writers=None) -> InFlight:
    """The `InFlight` for the checkout at `root`, from the same readers the Stop hook acts on: `wl_prscope.loop_state` (the PR, its plan set via `plan_gate.pr_plan_set`, the next plan), `plan_gate.turbo_named` and the PR body for each plan's source, the focus events and leases of the store's fold, `wl_epic.load_epics` with the branch's `PR-TASK:` trailers.
    `fold` and `loop` are the stop's own when it has them; `writers` is the live writer ids, None when not counted."""
    import wl_ci
    import wl_epic
    import wl_prscope as P
    import wl_standdown
    import wl_store as S

    root = pathlib.Path(root)
    plan_gate, _cp = P._hooks_pkg()
    settings, _problems = settings_for(root)
    if fold is None:
        fold = S.load(worklist, sync=False)
    if loop is None:
        loop = P.loop_state(root, worklist, session_id, settings=settings)
    focus = []
    for owner, ev in sorted((fold.phase or {}).items()):
        if not isinstance(ev, dict) or ev.get("mode") not in wl_standdown.PHASE_MODES:
            continue
        focus.append(
            FocusLine(
                str(owner)[:8],
                str(ev.get("mode")),
                str(ev.get("pr") or ""),
                str(ev.get("branch") or ""),
                str(ev.get("at") or ""),
                bool(wl_standdown.expired(ev)),
            )
        )
    body = None
    if loop.kind == P.LIVE and loop.branch:
        nodes, err = wl_ci.pr_link(str(root), worklist, session_id, loop.branch)
        if not err:
            body = next(
                (
                    str(n.get("body") or "")
                    for n in nodes
                    if str(n.get("state") or "").upper() == "OPEN"
                ),
                None,
            )
    named = plan_gate.turbo_named(str(root), loop.branch) if loop.branch else []

    def plan_line(rel, source):
        opened, done, why = plan_gate.open_boxes(str(root), rel)
        return PlanLine(rel, source, done, -1 if why else opened + done)

    lines = [plan_line(rel, _plan_source(rel, loop, body, named)) for rel in loop.plans]
    if loop.kind in (P.LIVE, P.UNREADABLE):
        for rel in [*named, *loop.turbo_picks]:
            if rel not in loop.plans and all(p.rel != rel for p in lines):
                lines.append(
                    plan_line(
                        rel,
                        "a turbo pick named by the Stop hook, joining the `Plan:` line on the next push",
                    )
                )
    in_set = {p.rel for p in lines}
    # An epic is in flight on this branch when a commit here carries its `PR-TASK:` trailer or one of its items is leased; an epic whose only open items wait unleased is queued work, not this branch's.
    open_ids = {r["id"] for r in fold.items if r.get("state") in (" ", ">", "?")}
    leased_ids = {r["id"] for r in fold.items if r.get("state") == ">"}
    commits = _branch_epic_commits(root, loop.kind)
    epics = []
    for eid, rec in wl_epic.load_epics().items():
        plan = str(rec.get("plan") or "")
        covers = set(rec.get("covers") or ())
        if plan in in_set or (eid not in commits and not covers & leased_ids):
            continue
        n_open = len(open_ids & covers)
        title = " ".join(str(rec.get("title") or "").split())
        epics.append(EpicLine(eid, title, plan, commits.get(eid, 0), n_open))
    leases = tuple(
        sorted(
            (str(r["id"]), str(r.get("worker") or "?"), str(r.get("owner") or "?")[:8])
            for r in fold.items
            if r.get("state") == ">"
        )
    )
    nxt, why, when = loop.next_plan, "", ""
    if nxt:
        text = (
            (root / QUEUE_REL).read_text(encoding="utf-8") if (root / QUEUE_REL).is_file() else ""
        )
        promoted, generated = entries(text)
        if nxt in promoted:
            why = "Promoted entry %d%s" % (
                promoted.index(nxt) + 1,
                " (solo)" if nxt in solo_plans(text) else "",
            )
        elif nxt in generated:
            why = "Generated entry %d (no Promoted entry ahead of it has an open box)" % (
                generated.index(nxt) + 1
            )
        else:
            why = "the deepest unfinished prerequisite of the first open queue entry"
        if loop.kind == P.LIVE:
            when = (
                "a turbo pick joins this PR when a writer slot frees under plan_concurrency %d"
                % settings.plan_concurrency
                if settings.turbo
                else "starts on the next branch after PR #%d merges" % loop.pr
            )
        elif loop.kind == P.NO_PR:
            when = (
                "starts when this branch's PR binds it on its first push"
                if nxt == loop.queue_head
                else "starts after this branch's PR merges"
            )
        elif loop.kind in (P.MERGED, P.ON_MAIN):
            when = "starts on branch %s" % (loop.next_branch or "<next MMDD-N>")
    return InFlight(
        settings=settings,
        focus=tuple(focus),
        kind=loop.kind,
        branch=loop.branch,
        pr=loop.pr,
        reason=loop.reason,
        queue_head=loop.queue_head,
        plans=tuple(lines),
        epics=tuple(epics),
        session=str(session_id or "")[:8],
        writers=None if writers is None else tuple(str(w) for w in writers),
        leases=leases,
        next_plan=nxt,
        next_why=why,
        next_when=when,
    )


def refresh_inflight(root, worklist, session_id, fold=None, loop=None, writers=None) -> bool:
    """Rewrite the in-flight block of an EXISTING queue file, and re-render its existing Promoted progress block from the plan files, when either changed; True when it wrote. A root with no queue file is left without one. The write re-reads the file just before replacing it and starts over (once) when another writer changed it in between, so a concurrent `--update` of the generated block is not undone by a stale copy."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return False
    body = render_inflight(gather_inflight(root, worklist, session_id, fold, loop, writers))
    import wl_planrec as R

    for _attempt in range(2):
        got = path.read_text(encoding="utf-8")
        # The Promoted progress block rides the same write, so every stop re-renders it from the plan files before anything judges the tree. An existing block only: the first insertion is the gate's `--update` or a plan verb's `refresh`, so a stop never adds a section to a file that has none.
        new = with_inflight(got, body)
        if progress_text(new) is not None:
            new = with_fresh_progress(root, new)
        if new == got:
            return False
        if path.read_text(encoding="utf-8") == got:
            R.write_atomic(path, new)
            return True
    return False
