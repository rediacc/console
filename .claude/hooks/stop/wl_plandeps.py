"""wl_plandeps: the one home of the plan-header grammar that orders plans (`Depends-On:`), and of the graph built from it.

WHY ONE MODULE. Three enforcement points read the same line: the pre-edit guard `block_plan_without_depends.py` (write time), the CI gate `.ci/scripts/quality/check_plan_deps.py` (merge time) and the worklist verbs and Stop hook (start time, PLAN-plan-dependencies.md T6-T8). A second parser anywhere is a second grammar, so all three import this file. The design is agent/plans/PLAN-plan-dependencies.md sections 1 and 2.

THE FIELD. One anchored line inside the first `HEADER_LINES` lines, one spelling, no markdown emphasis:

    Depends-On: PLAN-a.md, PLAN-b.md
    Depends-On: PLAN-a.md, PLAN-y.md#T3 -- <optional note>
    Depends-On: no-dep -- <reason, one line, 12+ chars>

Tokens are bare basenames, because every plan moves once at close and a path would go stale on the day the dependency finishes. `PLAN-y.md#<ref>` is a TASK edge (operator ruling 2026-09-24): it is parsed here and resolved at plan level; box-level completion and the D9 reworded-box finding are T12's. A list may carry a trailing ` -- <note>`, the same optional-reason shape PLAN-plan-priority-concurrency.md gives Priority and Concurrency; `no-dep` must carry one.

EXTENSIBLE BY TABLE. `FIELD_SPECS` maps a header field to (window, parser). `parse_header` runs every spec it holds, so PLAN-plan-priority-concurrency.md T1 adds `Priority`, `Concurrency` and `Owns` as three entries with their own window (`X_HEADER_LINES = 12`) and needs no change to the scan, the duplicate rule or the outside-window rule.

THE X FIELDS (PLAN-plan-priority-concurrency.md section 1), one anchored line each:

    Priority: P0|P1|P2|P3 [(operator)] [-- <reason>]
    Concurrency: parallel [-- <reason>]
    Concurrency: exclusive -- <reason, 12+ chars>
    Owns: <glob>[ (<note>)], <glob>, ...
    Owns: none -- <reason, 12+ chars>

`(operator)` is the only marker, and an operator-set Priority is never changed by the AI (the pre-edit guard freezes it, CI D17 backstops it). An Owns item may carry a trailing parenthesised note (`routes/index.ts (one mount line)`), because the live corpus already narrows claims that way; the note is kept for the reader and the glob is judged whole, which over-claims toward refusal, the safe side. The glob refusal rules (absolute, `..`, `!`, backslash, more than 32 brace expansions) and the overlap engine live in `wl_planconc`.

`X_FIELDS_REQUIRED` is the one switch between "optional until the migration" and "mandatory". It is False until PLAN-plan-priority-concurrency.md T11 writes the three lines into every required plan, and T11 flips it in the same commit. While False, the gate reports X findings without failing and the guard refuses only NEW ones (the plan-deps ratchet shape); the operator freeze (D17 and the guard's freeze) is enforced either way.

STDLIB ONLY AT IMPORT. The guard runs this in the pre-edit chain on every plan edit. `wl_planfile` (for `FINISHED_STATES`) is imported lazily inside `finished_states`, so a broken sibling module costs the guard its completeness answer, never its import. Reads no environment variable.

NEVER RAISES ON THE READ PATH. `Graph.load` skips an unreadable file rather than failing the stop or the edit; the gate's vacuity floor (D8) is what notices a corpus that stopped loading.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import pathlib
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# The window a field must sit in. Ten is the smallest header window among the readers (wl_checks, wl_planrec, wl_backlog, plan_lifecycle), so a field inside it is visible to all of them.
HEADER_LINES = 10
# The window `Status:` is read in: plan_lifecycle.HEADER_LINES, which is the widest reader and the one the folder gate classifies with.
STATUS_LINES = 12
# How much of a plan the header scan reads. The largest plan is ~650 KB and only its head is needed; the outside-window scan stops at the first structural line long before this.
HEAD_BYTES = 65536

PLANS_DIR = "agent/plans"
DONE_DIR = "agent/plans/_done"
REMOVED_DIR = "agent/plans/_removed"
PLAN_DIRS = (PLANS_DIR, DONE_DIR, REMOVED_DIR)
INDEX_REL = "agent/INDEX.md"

# The X fields' window: plan_lifecycle.HEADER_LINES, wider than HEADER_LINES because `set_x` appends them AFTER the existing header block so no spine field (Status, Owner, Depends-On, a record's Full-Text*/Record-Sig) moves.
X_HEADER_LINES = 12
PRIORITY = "Priority"
CONCURRENCY = "Concurrency"
OWNS = "Owns"
X_FIELDS = (PRIORITY, CONCURRENCY, OWNS)
# See the module docstring. PLAN-plan-priority-concurrency.md T11 sets this to True in the migration commit.
X_FIELDS_REQUIRED = True
OPERATOR_MARK = "operator"
PARALLEL = "parallel"
EXCLUSIVE = "exclusive"
OWNS_NONE = "none"

FIELD = "Depends-On"
NO_DEP = "no-dep"
REASON_MIN = 12
# Words that say nothing about WHY a plan stands alone. Compared after lowercasing and stripping punctuation.
VAGUE_REASONS = frozenset({"none", "n/a", "na", "tbd", "nothing", "no", "nil", "-", "todo"})

STUB_STATUS = "moved"
REMOVED_STATUS = "removed"

STATUS_RE = re.compile(r"^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)", re.MULTILINE)
MOVED_TO_RE = re.compile(r"^Moved-To:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
# A plan basename, optionally with a task ref. The ref is a stable box id (`T3`, `R20260925.5`) or an 8-hex box signature.
TOKEN_RE = re.compile(r"^(PLAN-[A-Za-z0-9._-]+\.md)(?:#([A-Za-z0-9._-]+))?$")
# The separator between a value and its reason: `--` or an em dash, each surrounded by whitespace.
REASON_SPLIT_RE = re.compile(r"\s+(?:--|\u2014)\s+")
NO_DEP_RE = re.compile(r"^no-dep(?:\s+(?:--|\u2014)(?:\s+(.*))?)?$")
# The X value grammars, applied to the text after `Key: ` (PLAN-plan-priority-concurrency.md section 1).
PRIORITY_VALUE_RE = re.compile(r"^(P[0-3])(?: \((operator)\))?(?: (?:--|\u2014) (\S.*))?$")
CONCURRENCY_VALUE_RE = re.compile(r"^(parallel|exclusive)(?: (?:--|\u2014) (\S.*))?$")
OWNS_NONE_RE = re.compile(r"^none(?:\s+(?:--|\u2014)(?:\s+(.*))?)?$")
# An Owns item's optional trailing note: `path (new)`, `file.ts (one mount line)`.
OWNS_NOTE_RE = re.compile(r"^(\S+)(?:\s+\(([^()]*)\))?$")
# A worklist item implements a plan box when the plan's basename is IMMEDIATELY followed by ` [<8hex>]`, the existing `PLAN-x.md [41f56150]` convention. A bare mention links nothing.
LINK_RE = re.compile(r"(PLAN-[A-Za-z0-9._-]+\.md) \[([0-9a-f]{8})\]")
PLAN_CITE_RE = re.compile(r"\bPLAN-[A-Za-z0-9._-]+\.md\b")
# A mirror of plan_lifecycle.TOMBSTONE_ROW_RE: that module lives under `.ci` and this one must import with `.claude` alone. test_gate_plan_deps.py compares the two.
TOMBSTONE_ROW_RE = re.compile(
    r"^\|[ \t]*`(?P<rel>[^`]+)`[ \t]*\|(?P<title>[^|]*)\|(?P<seen>[^|]*)\|"
    r"(?P<expired>[^|]*)\|[ \t]*`(?P<blob>[0-9a-f]{40})`[ \t]*\|[ \t]*$",
    re.MULTILINE,
)
# Lines that end the header block for the outside-window scan: a section heading, a fence or a checkbox. A `Depends-On:` quoted in the body (this plan's own section 1 does it in a fence) is not a header line.
_BODY_START_RE = re.compile(r"^(?:## |```|~~~|\s*- \[)")

# Finding codes shared by the gate and the guard. D8 (vacuity) is the gate's alone; D9 (a task edge whose box no longer exists) is T12's.
D_MISSING = "D1"
D_MALFORMED = "D2"
D_DANGLING = "D3"
D_WITHDRAWN = "D4"
D_SELF = "D5"
D_CYCLE = "D6"
D_AMBIGUOUS = "D7"
# The X findings (PLAN-plan-priority-concurrency.md section 6b). D8 is the gate's vacuity floor; D17 (an operator Priority removed or demoted since the merge-base) is the gate's alone, because only it can see the base.
D_PRIORITY_MISSING = "D10"
D_PRIORITY_MALFORMED = "D11"
D_CONCURRENCY = "D12"
D_OWNS = "D13"
D_OWNS_GLOB = "D14"
D_UNIVERSAL = "D15"
D_WINDOW = "D16"
D_OPERATOR_DEMOTED = "D17"

# Resolution states of one token.
LIVE = "live"
COMPLETE = "complete"
WITHDRAWN = "withdrawn"
DANGLING = "dangling"
AMBIGUOUS = "ambiguous"

_OPEN_ITEM_STATES = (" ", ">", "?")


# --------------------------------------------------------------------------- The grammar.


@dataclasses.dataclass(frozen=True)
class Edge:
    """One `Depends-On:` token. `task` is None for a whole-plan edge."""

    plan: str
    task: str | None = None

    def __str__(self) -> str:
        return self.plan if self.task is None else "%s#%s" % (self.plan, self.task)


@dataclasses.dataclass(frozen=True)
class DependsOn:
    """A parsed `Depends-On:` value. `no_dep` is the reason when the plan declared none, else ""."""

    edges: tuple[Edge, ...] = ()
    no_dep: str = ""
    note: str = ""


@dataclasses.dataclass(frozen=True)
class Field:
    """One header field as found: 1-based line, raw value, parsed value (None when malformed) and its errors."""

    name: str
    lineno: int
    value: str
    parsed: Any
    errors: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class FieldSpec:
    """How to read one header field. `parse(value) -> (parsed, [error, ...])`."""

    name: str
    window: int
    parse: Callable[[str], tuple[Any, list[str]]]


@dataclasses.dataclass(frozen=True)
class Header:
    """Every declared field of one plan's header. `errors` holds (field, message) pairs for shapes no single value explains: a second line, a line outside the window, an emphasised key."""

    status: str
    moved_to: str
    fields: dict[str, Field]
    errors: tuple[tuple[str, str], ...]

    def get(self, name: str) -> Field | None:
        return self.fields.get(name)

    @property
    def depends(self) -> DependsOn | None:
        """The parsed Depends-On value, or None when absent or malformed."""
        f = self.fields.get(FIELD)
        return f.parsed if f is not None else None

    @property
    def priority(self) -> Priority | None:
        f = self.fields.get(PRIORITY)
        return f.parsed if f is not None else None

    @property
    def concurrency(self) -> Concurrency | None:
        f = self.fields.get(CONCURRENCY)
        return f.parsed if f is not None else None

    @property
    def owns(self) -> Owns | None:
        f = self.fields.get(OWNS)
        return f.parsed if f is not None else None

    def field_errors(self, name: str) -> list[str]:
        """Every error for one field: its value's and the structural ones."""
        out = [msg for fname, msg in self.errors if fname == name]
        f = self.fields.get(name)
        if f is not None:
            out.extend(f.errors)
        return out


def _reason_errors(reason: str, what: str, why: str = "say WHY the plan stands alone") -> list[str]:
    reason = (reason or "").strip()
    if not reason:
        return ["%s needs a reason after `--`" % what]
    errors = []
    if len(reason) < REASON_MIN:
        errors.append("%s reason %r is under %d characters; %s" % (what, reason, REASON_MIN, why))
    if reason.lower().strip(" .,;:!?`'\"") in VAGUE_REASONS:
        errors.append("%s reason %r is a placeholder, not a reason" % (what, reason))
    return errors


def parse_depends(value: str) -> tuple[DependsOn | None, list[str]]:
    """(DependsOn, []) for a valid value, (None, [error, ...]) otherwise. Every malformed sub-shape of section 1 has its own message."""
    value = (value or "").strip()
    if not value:
        return None, ["the value is empty; write a list of plans or `no-dep -- <reason>`"]
    m = NO_DEP_RE.match(value)
    if m:
        errors = _reason_errors(m.group(1) or "", "`no-dep`")
        return (None, errors) if errors else (DependsOn(no_dep=m.group(1).strip()), [])
    parts = REASON_SPLIT_RE.split(value, maxsplit=1)
    listed = parts[0]
    note = parts[1].strip() if len(parts) > 1 else ""
    errors = []
    edges: list[Edge] = []
    seen = set()
    for raw in listed.split(","):
        tok = raw.strip()
        if not tok:
            errors.append("an empty token (a leading, trailing or doubled comma)")
            continue
        if tok.lower().startswith(NO_DEP):
            errors.append("`no-dep` mixed with a list; a plan either depends or does not")
            continue
        if "/" in tok and TOKEN_RE.match(tok.rsplit("/", 1)[-1]):
            errors.append(
                "%r is a path; name the bare basename %r, which survives the move at close"
                % (tok, tok.rsplit("/", 1)[-1])
            )
            continue
        tm = TOKEN_RE.match(tok)
        if not tm:
            errors.append(
                "%r is not a plan basename (`PLAN-<slug>.md`, optionally `#<task>`)" % tok
            )
            continue
        edge = Edge(tm.group(1), tm.group(2))
        if edge in seen:
            errors.append("%s is listed twice" % edge)
            continue
        seen.add(edge)
        edges.append(edge)
    if errors:
        return None, errors
    return DependsOn(edges=tuple(edges), note=note), []


@dataclasses.dataclass(frozen=True)
class Priority:
    """A parsed `Priority:`. `level` 0 is most urgent; `operator` is True only for the `(operator)` marker."""

    level: int
    operator: bool = False
    reason: str = ""

    def __str__(self) -> str:
        out = "P%d" % self.level
        if self.operator:
            out += " (%s)" % OPERATOR_MARK
        return out + (" -- %s" % self.reason if self.reason else "")


@dataclasses.dataclass(frozen=True)
class Concurrency:
    mode: str
    reason: str = ""

    @property
    def exclusive(self) -> bool:
        return self.mode == EXCLUSIVE


@dataclasses.dataclass(frozen=True)
class Owns:
    """A parsed `Owns:`. `globs` is empty exactly when the plan declared `none -- <reason>`, and `none` holds that reason. `notes` maps a glob to its parenthesised note."""

    globs: tuple[str, ...] = ()
    none: str = ""
    notes: tuple[tuple[str, str], ...] = ()


def parse_priority(value: str) -> tuple[Priority | None, list[str]]:
    value = (value or "").strip()
    m = PRIORITY_VALUE_RE.match(value)
    if not m:
        return None, [
            "%r is not `P0`-`P3`, optionally ` (operator)`, optionally ` -- <reason>`" % value
        ]
    return Priority(int(m.group(1)[1]), bool(m.group(2)), (m.group(3) or "").strip()), []


def parse_concurrency(value: str) -> tuple[Concurrency | None, list[str]]:
    value = (value or "").strip()
    m = CONCURRENCY_VALUE_RE.match(value)
    if not m:
        return None, ["%r is not `parallel [-- <reason>]` or `exclusive -- <reason>`" % value]
    mode, reason = m.group(1), (m.group(2) or "").strip()
    if mode == EXCLUSIVE:
        errors = _reason_errors(reason, "`exclusive`", "say WHY it stops every other plan")
        if errors:
            return None, errors
    return Concurrency(mode, reason), []


def parse_owns(value: str) -> tuple[Owns | None, list[str]]:
    """The comma list, or `none -- <reason>`. Only the list SHAPE is judged here; whether each glob is legal is `wl_planconc.normalize_owns`' question (finding D14)."""
    value = (value or "").strip()
    if not value:
        return None, ["the value is empty; list the globs this plan edits, or `none -- <reason>`"]
    m = OWNS_NONE_RE.match(value)
    if m:
        errors = _reason_errors(m.group(1) or "", "`none`", "say why the plan edits no file")
        if errors:
            return None, errors
        return Owns(none=m.group(1).strip()), []
    errors = []
    globs: list[str] = []
    notes: list[tuple[str, str]] = []
    for raw in _split_owns(value):
        item = raw.strip()
        if not item:
            errors.append("an empty item (a leading, trailing or doubled comma)")
            continue
        if item.lower().startswith(OWNS_NONE + " "):
            errors.append("`none` mixed with a list; a plan either owns files or owns none")
            continue
        im = OWNS_NOTE_RE.match(item)
        if not im:
            errors.append(
                "%r is not one glob with an optional `(note)`; separate globs with commas" % item
            )
            continue
        glob = im.group(1)
        if glob in globs:
            errors.append("%s is listed twice" % glob)
            continue
        globs.append(glob)
        if im.group(2):
            notes.append((glob, im.group(2).strip()))
    if errors:
        return None, errors
    return Owns(globs=tuple(globs), notes=tuple(notes)), []


def _split_owns(value: str) -> list[str]:
    """Split on commas that are outside `{...}` and `(...)`, so `a/{b,c}.py` and `x.ts (a, b only)` stay whole."""
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in value:
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return out


FIELD_SPECS: dict[str, FieldSpec] = {
    FIELD: FieldSpec(FIELD, HEADER_LINES, parse_depends),
    PRIORITY: FieldSpec(PRIORITY, X_HEADER_LINES, parse_priority),
    CONCURRENCY: FieldSpec(CONCURRENCY, X_HEADER_LINES, parse_concurrency),
    OWNS: FieldSpec(OWNS, X_HEADER_LINES, parse_owns),
}


def _key_re(name: str) -> re.Pattern[str]:
    return re.compile(r"^%s:[ \t]*(.*?)[ \t]*$" % re.escape(name))


def _emph_re(name: str) -> re.Pattern[str]:
    return re.compile(r"^\*{1,2}%s\*{0,2}:|^%s\*{1,2}:" % (re.escape(name), re.escape(name)))


def parse_header(text: str, specs: dict[str, FieldSpec] | None = None) -> Header:
    """Every field in `specs` (default `FIELD_SPECS`) read from `text`'s header. Pure: no filesystem.

    A field counts when its line is anchored at column 0 in the first `spec.window` lines. The first occurrence is parsed; a second one anywhere in the header block, one past the window, or an emphasised key (`**Depends-On:**`) is a structural error in `Header.errors`. The header block ends at the first section heading, fence or checkbox.
    """
    specs = FIELD_SPECS if specs is None else specs
    lines = (text or "").splitlines()
    head = "\n".join(lines[:STATUS_LINES])
    sm = STATUS_RE.search(head)
    status = sm.group(1).strip().lower() if sm else ""
    mm = MOVED_TO_RE.search(head)
    moved_to = mm.group(1).strip() if mm else ""
    fields: dict[str, Field] = {}
    errors: list[tuple[str, str]] = []
    for name, spec in specs.items():
        key = _key_re(name)
        emph = _emph_re(name)
        for idx, line in enumerate(lines):
            if _BODY_START_RE.match(line):
                break
            lineno = idx + 1
            if emph.match(line):
                errors.append(
                    (
                        name,
                        "line %d spells the key with emphasis; write a plain `%s:`"
                        % (lineno, name),
                    )
                )
                continue
            km = key.match(line)
            if not km:
                continue
            if lineno > spec.window:
                errors.append(
                    (
                        name,
                        "line %d is outside the %d-line header window; move `%s:` up next to `Status:`"
                        % (lineno, spec.window, name),
                    )
                )
                continue
            if name in fields:
                errors.append(
                    (
                        name,
                        "a second `%s:` line at %d (the first is at %d)"
                        % (name, lineno, fields[name].lineno),
                    )
                )
                continue
            parsed, perrs = spec.parse(km.group(1))
            fields[name] = Field(name, lineno, km.group(1), parsed, tuple(perrs))
    return Header(status=status, moved_to=moved_to, fields=fields, errors=tuple(errors))


def is_stub_header(header: Header) -> bool:
    """A pointer rather than a document: `Status: moved` AND `Moved-To:`, the plan_lifecycle.is_stub rule."""
    return header.status == STUB_STATUS and bool(header.moved_to)


def finished_states() -> frozenset[str]:
    """`wl_planfile.FINISHED_STATES`, imported lazily. ImportError propagates: a caller that cannot tell finished from live must say so, not guess."""
    import wl_planfile  # noqa: PLC0415 -- lazy by design, see the module docstring

    return wl_planfile.FINISHED_STATES


def set_header(text: str, value: str) -> str:
    """`text` with its `Depends-On:` line replaced, or inserted right after `Status:`. ValueError when the header has no `Status:` line to anchor on.

    Every other line keeps its bytes, so on a well-formed header the diff is exactly one added or one changed line; a duplicate, emphasised or out-of-window `Depends-On:` line is removed as part of the fix.
    """
    new_line = "%s: %s" % (FIELD, value.strip())
    lines = text.splitlines(keepends=True)
    key = _key_re(FIELD)
    emph = _emph_re(FIELD)
    hits = []
    for idx, line in enumerate(lines):
        bare = line.rstrip("\r\n")
        if _BODY_START_RE.match(bare):
            break
        if key.match(bare) or emph.match(bare):
            hits.append(idx)
    keep = next((i for i in hits if i < HEADER_LINES), None)
    if keep is not None:
        ending = lines[keep][len(lines[keep].rstrip("\r\n")) :] or "\n"
        lines[keep] = new_line + ending
    # Every other `Depends-On:` line in the header block (a second one, one past the window, an emphasised one) is the malformation being fixed, so it goes.
    for idx in reversed(hits):
        if idx != keep:
            del lines[idx]
    if keep is not None:
        return "".join(lines)
    for idx, line in enumerate(lines[:STATUS_LINES]):
        if STATUS_RE.match(line):
            ending = line[len(line.rstrip("\r\n")) :] or "\n"
            if not line.endswith(("\n", "\r")):
                lines[idx] = line + ending
            lines.insert(idx + 1, new_line + ending)
            return "".join(lines)
    # A STATUS-LESS COMPANION (e.g. PLAN-retire-bash-oracles.A0.md: an HTML provenance comment, then the `# ` title, no header block) is still a required plan, so it anchors on its title instead. Without this the gate required a line the verb refused to write (2026-09-25).
    for idx, line in enumerate(lines[:STATUS_LINES]):
        if line.startswith("# "):
            ending = line[len(line.rstrip("\r\n")) :] or "\n"
            lines.insert(idx + 1, new_line + ending)
            return "".join(lines)
    raise ValueError(
        "no `Status:` line or `# ` title in the first %d lines to insert after" % STATUS_LINES
    )


_HEAD_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z-]*:[ \t]")


def header_block_end(lines: list[str]) -> int:
    """The index AFTER the last line of the header block: the contiguous non-blank run that starts at `Status:` (or, for a Status-less companion, right after its `# ` title). A wrapped continuation line belongs to the block, so nothing is inserted between a field and its own second line."""
    start = None
    for idx, line in enumerate(lines[:STATUS_LINES]):
        if STATUS_RE.match(line.rstrip("\r\n")):
            start = idx
            break
    if start is None:
        for idx, line in enumerate(lines[:STATUS_LINES]):
            if line.startswith("# "):
                start = idx
                break
    if start is None:
        raise ValueError(
            "no `Status:` line or `# ` title in the first %d lines to anchor on" % STATUS_LINES
        )
    end = start + 1
    while end < len(lines):
        bare = lines[end].rstrip("\r\n")
        if not bare.strip() or bare.startswith("#") or _BODY_START_RE.match(bare):
            break
        end += 1
    return end


def set_x(text: str, fields: dict[str, str]) -> str:
    """`text` with each named X field (`Priority`, `Concurrency`, `Owns`) set to its value. Pure; values are not validated here (the callers run `parse_header` on the result).

    An existing line inside the X window is replaced IN PLACE, and any second, emphasised or out-of-window copy is removed. A missing field is APPENDED directly after the header block (section 1 placement), in the order Priority, Concurrency, Owns, so no existing field changes its line number. ValueError when a field name is not an X field, when there is nothing to anchor on, or when a field would land past `X_HEADER_LINES`.
    """
    unknown = sorted(set(fields) - set(X_FIELDS))
    if unknown:
        raise ValueError("not an X field: %s" % ", ".join(unknown))
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"
    missing = []
    for name in X_FIELDS:
        if name not in fields:
            continue
        new_line = "%s: %s" % (name, fields[name].strip())
        key, emph = _key_re(name), _emph_re(name)
        hits = []
        for idx, line in enumerate(lines):
            bare = line.rstrip("\r\n")
            if _BODY_START_RE.match(bare):
                break
            if key.match(bare) or emph.match(bare):
                hits.append(idx)
        keep = next((i for i in hits if i < X_HEADER_LINES and key.match(lines[i])), None)
        if keep is not None:
            ending = lines[keep][len(lines[keep].rstrip("\r\n")) :] or "\n"
            lines[keep] = new_line + ending
        for idx in reversed(hits):
            if idx != keep:
                del lines[idx]
        if keep is None:
            missing.append(new_line)
    if missing:
        end = header_block_end(lines)
        for offset, new_line in enumerate(missing):
            lines.insert(end + offset, new_line + "\n")
    out = "".join(lines)
    header = parse_header(out)
    late = [n for n in fields if n not in header.fields]
    if late:
        raise ValueError(
            "%s would land past line %d, outside the X window; shorten the header block above it"
            % (", ".join(late), X_HEADER_LINES)
        )
    return out


def linked_plan(text: str) -> str | None:
    """The plan basename a worklist item implements, from the `PLAN-x.md [<8hex>]` convention (plan-deps section 2c), or None. The first link wins; a bare mention links nothing."""
    m = LINK_RE.search(text or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- The graph.


@dataclasses.dataclass(frozen=True)
class PlanInfo:
    rel: str
    header: Header

    @property
    def base(self) -> str:
        return self.rel.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return self.rel.rsplit("/", 1)[0] if "/" in self.rel else ""

    @property
    def stub(self) -> bool:
        return is_stub_header(self.header)


@dataclasses.dataclass(frozen=True)
class Target:
    """What one token resolves to. `rel` is the real plan file, or the tombstone's recorded path, or ""."""

    token: str
    state: str
    rel: str = ""
    status: str = ""
    detail: str = ""


def _read_head(path: pathlib.Path) -> str | None:
    try:
        with path.open("rb") as fh:
            return fh.read(HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None


class Graph:
    """Every plan under agent/plans, _done and _removed, its header, and the tombstones of agent/INDEX.md.

    Build from disk with `Graph.load(root, override=...)`, or from text with `Graph.from_texts(...)` (the selftest's door: pure, no filesystem). `override` maps a rel path to text that replaces (or adds) that plan, which is how the guard judges the document an edit WOULD produce.
    """

    def __init__(
        self, texts: dict[str, str], index_text: str = "", root: pathlib.Path | None = None
    ):
        self.root = root
        self.texts = dict(texts)
        self.index_text = index_text or ""
        self.plans: dict[str, PlanInfo] = {}
        for rel, text in sorted(self.texts.items()):
            self.plans[rel] = PlanInfo(rel, parse_header(text))
        self.by_base: dict[str, list[str]] = {}
        for rel in self.plans:
            self.by_base.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
        self.tombstones: dict[str, str] = {}
        for m in TOMBSTONE_ROW_RE.finditer(index_text or ""):
            trel = m.group("rel").strip()
            self.tombstones.setdefault(trel.rsplit("/", 1)[-1], trel)
        self._finished: frozenset[str] | None = None

    @classmethod
    def from_texts(cls, texts: dict[str, str], index_text: str = "") -> Graph:
        return cls(texts, index_text)

    @classmethod
    def load(cls, root, override: dict[str, str] | None = None) -> Graph:
        root = pathlib.Path(root)
        texts: dict[str, str] = {}
        for folder in PLAN_DIRS:
            try:
                names = sorted(os.listdir(root / folder))
            except OSError:
                continue
            for name in names:
                if not (name.startswith("PLAN-") and name.endswith(".md")):
                    continue
                text = _read_head(root / folder / name)
                if text is not None:
                    texts["%s/%s" % (folder, name)] = text
        texts.update(override or {})
        try:
            index_text = (root / INDEX_REL).read_text(encoding="utf-8", errors="replace")
        except OSError:
            index_text = ""
        return cls(texts, index_text, root)

    # ---- completeness

    def finished(self) -> frozenset[str]:
        if self._finished is None:
            self._finished = finished_states()
        return self._finished

    def is_required(self, rel: str) -> bool:
        """True for a top-level, non-stub plan whose Status is not finished: the plans that must carry the field. `Status: removed` is terminal too; one sitting outside `_removed/` is check:ci-plan-folders' F2, not a missing field."""
        info = self.plans.get(rel)
        if info is None or info.folder != PLANS_DIR or info.stub:
            return False
        return info.header.status not in self.finished() and info.header.status != REMOVED_STATUS

    def required(self) -> list[str]:
        return [rel for rel in self.plans if self.is_required(rel)]

    # ---- resolution

    def resolve(self, token: str) -> Target:
        """Section 1's order: a real file (ambiguous when two share the basename), a stub followed once, a tombstone, else dangling. `#<task>` is resolved at plan level."""
        base = token.split("#", 1)[0]
        real = [r for r in self.by_base.get(base, []) if not self.plans[r].stub]
        if len(real) > 1:
            return Target(
                token,
                AMBIGUOUS,
                detail="%d files share the name: %s" % (len(real), ", ".join(real)),
            )
        if real:
            return self._judge(token, real[0])
        stubs = [r for r in self.by_base.get(base, []) if self.plans[r].stub]
        for srel in stubs:
            dest = self.plans[srel].header.moved_to
            info = self.plans.get(dest)
            if info is not None and not info.stub:
                return self._judge(token, dest)
        stone = self.tombstones.get(base)
        if stone:
            if stone.startswith(DONE_DIR + "/"):
                return Target(token, COMPLETE, stone, detail="expired from _done/ (tombstone)")
            return Target(token, WITHDRAWN, stone, detail="expired outside _done/ (tombstone)")
        if stubs:
            return Target(
                token,
                DANGLING,
                stubs[0],
                detail="stub points at %r, which is not a plan"
                % self.plans[stubs[0]].header.moved_to,
            )
        return Target(token, DANGLING, detail="no plan, stub or tombstone carries this name")

    def _judge(self, token: str, rel: str) -> Target:
        status = self.plans[rel].header.status
        if rel.startswith(REMOVED_DIR + "/") or status == REMOVED_STATUS:
            return Target(token, WITHDRAWN, rel, status, "withdrawn (_removed/ or Status: removed)")
        if status in self.finished():
            return Target(token, COMPLETE, rel, status)
        return Target(token, LIVE, rel, status)

    def is_complete(self, token: str) -> bool:
        """True when the token's plan is finished (a Status in FINISHED_STATES, folder not consulted) or a `_done/` tombstone. A task edge counts as complete only with its whole plan until T12 teaches box-level completion."""
        return self.resolve(token).state == COMPLETE

    # ---- edges

    def edges(self, rel: str) -> tuple[Edge, ...]:
        info = self.plans.get(rel)
        dep = info.header.depends if info else None
        return dep.edges if dep else ()

    def _succ(self, rel: str) -> list[tuple[Edge, str]]:
        """(edge, target rel) for every edge of `rel` that resolves to a real OTHER plan file. A self edge is D5, not a one-plan cycle."""
        out = []
        for edge in self.edges(rel):
            t = self.resolve(str(edge))
            if t.state in (LIVE, COMPLETE) and t.rel in self.plans and t.rel != rel:
                out.append((edge, t.rel))
        return out

    def cycles(self) -> list[list[str]]:
        """Every elementary cycle among the headers once, as a closed basename path `[A, B, A]`, rotated to start at its smallest member."""
        found: dict[tuple[str, ...], list[str]] = {}
        nodes = sorted(self.plans)
        for start in nodes:
            stack = [(start, [start])]
            while stack:
                node, path = stack.pop()
                for _edge, nxt in self._succ(node):
                    if nxt == start:
                        cyc = path[:]
                        i = cyc.index(min(cyc))
                        rot = tuple(cyc[i:] + cyc[:i])
                        found.setdefault(rot, [r.rsplit("/", 1)[-1] for r in (*rot, rot[0])])
                    elif nxt not in path and nxt > start:
                        stack.append((nxt, [*path, nxt]))
        return [found[k] for k in sorted(found)]

    def roots(self, rel: str) -> list[str]:
        """`dep_roots`: the incomplete dependencies at the bottom of each chain from `rel`, as tokens. An unresolvable token (dangling, withdrawn, ambiguous) is its own root, so a caller fails closed on it. Cycle-safe."""
        out: list[str] = []
        seen = {rel}

        def add(name: str) -> None:
            if name not in out:
                out.append(name)

        def walk(cur: str) -> bool:
            # True when `cur` has at least one incomplete dependency, i.e. something below it blocks. A plan already visited (a diamond, or a cycle) counts as blocking and adds nothing twice; a cycle is reported by `cycles`, and the start-time gate fails closed on it (section 2c).
            blocked = False
            for edge in self.edges(cur):
                t = self.resolve(str(edge))
                if t.state == COMPLETE:
                    continue
                blocked = True
                if t.state != LIVE:
                    add(str(edge))
                    continue
                if t.rel in seen:
                    continue
                seen.add(t.rel)
                if not walk(t.rel):
                    add(t.rel.rsplit("/", 1)[-1])
            return blocked

        walk(rel)
        return out

    def chain(self, rel: str, root: str) -> list[str]:
        """The shortest basename path from `rel` to `root` over incomplete edges, `[X, Y, Z]`, or [] when none."""
        start = rel.rsplit("/", 1)[-1]
        queue = [(rel, [start])]
        seen = {rel}
        while queue:
            cur, path = queue.pop(0)
            for edge in self.edges(cur):
                t = self.resolve(str(edge))
                if t.state == COMPLETE:
                    continue
                name = str(edge) if t.state != LIVE else t.rel.rsplit("/", 1)[-1]
                if name == root or str(edge) == root:
                    return [*path, name]
                if t.state == LIVE and t.rel not in seen:
                    seen.add(t.rel)
                    queue.append((t.rel, [*path, name]))
        return []

    # ---- the shared verdict

    def check(self, rel: str) -> list[tuple[str, str]]:
        """(code, message) for every D1-D7 finding on one plan, cycles limited to those through `rel`. Requiredness is the caller's question."""
        info = self.plans.get(rel)
        if info is None:
            return [(D_MISSING, "%s is not a plan in the graph" % rel)]
        header = info.header
        field = header.get(FIELD)
        structural = [msg for fname, msg in header.errors if fname == FIELD]
        if field is None:
            if structural:
                return [(D_MALFORMED, msg) for msg in structural]
            return [(D_MISSING, "no `%s:` line in the first %d lines" % (FIELD, HEADER_LINES))]
        out = [(D_MALFORMED, msg) for msg in (*structural, *field.errors)]
        dep = header.depends
        if dep is None:
            return out
        for edge in dep.edges:
            if edge.plan == info.base:
                out.append((D_SELF, "%s depends on itself" % edge))
                continue
            t = self.resolve(str(edge))
            if t.state == DANGLING:
                out.append((D_DANGLING, "%s resolves to nothing: %s" % (edge, t.detail)))
            elif t.state == WITHDRAWN:
                out.append((D_WITHDRAWN, "%s is withdrawn: %s" % (edge, t.detail)))
            elif t.state == AMBIGUOUS:
                out.append((D_AMBIGUOUS, "%s is ambiguous: %s" % (edge, t.detail)))
        out.extend(
            (D_CYCLE, "a dependency cycle: %s" % " -> ".join(cyc))
            for cyc in self.cycles()
            if info.base in cyc
        )
        return out

    def citations(self, rel: str) -> list[tuple[str, list[str]]]:
        """[(cited basename, [up to 2 citing lines])] for every OTHER plan named in `rel`'s full text, in first-seen order. For `--draft`; reads the whole file when a root is known."""
        text = self.texts.get(rel, "")
        if self.root is not None:
            with contextlib.suppress(OSError):
                text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
        own = rel.rsplit("/", 1)[-1]
        found: dict[str, list[str]] = {}
        for line in text.splitlines():
            for name in PLAN_CITE_RE.findall(line):
                if name == own:
                    continue
                lines = found.setdefault(name, [])
                if len(lines) < 2 and line.strip() not in lines:
                    lines.append(line.strip())
        return list(found.items())


# --------------------------------------------------------------------------- The worklist link.
