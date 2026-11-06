"""wl_planbox: the one grammar module of tick tracking (agent/plans/PLAN-tick-tracking.md Design 1, 2 and 5).

Three readers live here and nowhere else, so the land refusal (T2), the lease commit-msg hook (T3), `land --ticks` (T4), report capture (T6) and the progress ledger (T8) cannot disagree about a spelling.

THE API (later boxes import exactly these names):

- `parse_plan_box(message) -> PlanBoxResult`: the `Plan-Box:` trailers of one commit message.
  `result.boxes` is a tuple of `PlanBox(plan, sig, clauses, line)`, where `plan` is a basename (`PLAN-x.md`), `sig` 8 lowercase hex, and `clauses` is the string `"all"` or a tuple of clause ids.
  `result.none_reason` is the reason of a `Plan-Box: none -- <reason>` trailer, or None.
  `result.errors` is a tuple of refusal lines, each naming `GRAMMAR`. `result.missing` is true when the trailer block holds no `Plan-Box:` line at all (its error is `NO_PLAN_BOX`), and `result.ok` is true when there is no error.
- `parse_tick(body) -> list[TickRow]`: the boxes one writer report names. A `TickRow` carries `plan`, `sig`, `state`, `commits` (lease shas), `landed` (`"all"` or clause ids), `owed` ((clause, half) pairs), `close`, `legacy` and `line`.
  The TICK line grammar is `TICK_GRAMMAR`. A body with no line in the TICK grammar's shape falls back to the legacy prose reader (below), whose rows carry `legacy=True`; a grammar-shaped line that fails the grammar yields no row and no fallback.
- `landed_map(root, lease_shas, rev="HEAD", since=None) -> dict | None`: {lease sha, lowercased and stripped: landed full sha}, read from the `(cherry picked from commit <sha>)` line that `git cherry-pick -x` writes. A lease sha with no landed commit is absent from the map; None means git could not answer.

GRAMMAR AND TREE ARE SEPARATE. `parse_plan_box` is grammar only and needs nothing but text. The tree checks are `message_problems(root, message)` and `box_problems`: the plan exists under `agent/plans/` (a `Moved-To:` stub followed), the sig names an OPEN box (`wl_planrec.open_boxes`), and each named clause exists in the box's clause map (the latest `define` row of `agent/ledgers/plan-box-progress.jsonl`; a box with no map takes only `clauses=all`). `land` (T2) and the lease commit-msg hook (T3, through `main`, run as a process) both call `message_problems`, so the two refusals cannot disagree. The tree modules are imported inside those functions, so the grammar readers stay import-light.

THE TRAILER BLOCK ONLY. A `Plan-Box:` line counts only in the message's last paragraph, which is where git keeps trailers and where `cherry-pick -x` appends its line. A commit that DESCRIBES the trailer in its body (T2's own message will) is not read as naming a box. When the last paragraph holds only `-x` lines (git separates them by a blank line from a message that ends in prose), the paragraph before it is read too.

THE LEGACY READER covers the prose TICK blocks of round 1104-1, written before the TICK line existed. Its unit is a REGION: from a line holding the word `TICK` to the next such line. Inside a region, a plan path (`agent/plans/PLAN-x.md`) sets the plan, ``box `<sig8>` `` (with or without the colon and backticks) opens a row, and every 7-to-12-hex token after it, up to the next box, is a lease sha.
A sha token holds at least one digit (an all-letter token such as `deadbeef` or `effaced` is an English word far more often than a sha), and a token glued to `-`, `#`, `.` or `/` (the `lp-decf11520448` row id, a `#sig`) is not a sha. The box's own sig is never its sha. The region rule is what keeps a review id or a PR-TASK id mentioned earlier in the prose out of the row.
The row's state is the word after the sig (`7692f2db partial`, `afa91934 H2 partial`) anywhere in the body, else `unknown`; `owed` is `(("*", "live"),)` when the region names a live half and the state is not `done`, which is all a prose block can honestly say.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TRAILER_KEY = "Plan-Box"
GRAMMAR = "Plan-Box: <PLAN-file>.md#<sig8> clauses=<C1,C2,...|all>  or  Plan-Box: none -- <reason, at least 12 characters>"
NO_PLAN_BOX = "no Plan-Box trailer (%s)" % GRAMMAR
NONE_REASON_MIN = 12
TICK_STATES = ("done", "present", "partial", "untouched", "blocked")
HALVES = ("code", "live", "operator")
TICK_GRAMMAR = "TICK <PLAN-file>.md#<sig8> <done|present|partial|untouched|blocked> commits=<lease shas|-> landed=<C1,C2|all|-> owed=<C3:live,C4:operator|->"
PICKED_LINE = "(cherry picked from commit %s)"
PICKED_PREFIX = "(cherry picked from commit "
GIT_TIMEOUT_S = 30

_KEY_RE = re.compile(r"^\s*plan-box\s*:(.*)$", re.IGNORECASE)
_PICKED_RE = re.compile(r"^\(cherry picked from commit ([0-9a-f]{7,40})\)\s*$")
_PLAN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
_SIG_RE = re.compile(r"^[0-9a-f]{8}$")
_CLAUSE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.]*$")
_NONE_RE = re.compile(r"^none\s+--\s*(.*)$")
# Seven hex is git's own shortest abbreviation and the `-x` reader's floor; four matched many lease shas at once (review 39bfb45b.3).
_HEX_ARG_RE = re.compile(r"^[0-9a-f]{7,40}$")
# A line in the TICK grammar's shape (`TICK <plan>.md#<sig8> ...`) that fails it is a malformed TICK, never legacy prose (review 39bfb45b.1).
_TICK_SHAPE_RE = re.compile(r"^\s*TICK\s+\S+?\.md#[0-9a-f]{8}(?![0-9a-z])")
# The folders a plan path given to `open_box` may name: the live folder and the two terminal ones a stub points into.
PLAN_FOLDERS = ("", "agent/plans", "agent/plans/_done", "agent/plans/_removed")

_TICK_LINE_RE = re.compile(
    r"^\s*TICK\s+(?P<plan>\S+?\.md)#(?P<sig>[0-9a-f]{8})\s+(?P<state>[a-z]+)"
    r"\s+commits=(?P<commits>\S+)\s+landed=(?P<landed>\S+)\s+owed=(?P<owed>\S+)\s*$"
)
_CLOSE_RE = re.compile(r"^\s+close:\s*(.*\S)\s*$")
_LEGACY_ANCHOR_RE = re.compile(r"\bTICK\b")
_LEGACY_PLAN_RE = re.compile(r"(?:agent/plans/(?:_done/|_removed/)?)?(PLAN-[A-Za-z0-9._-]+?\.md)\b")
_LEGACY_BOX_RE = re.compile(r"\bbox\b:?\s*`?([0-9a-f]{8})`?(?![0-9a-z])")
_LEGACY_SHA_RE = re.compile(r"(?<![\w#./-])([0-9a-f]{7,12})(?![\w-])")
_LEGACY_LIVE_RE = re.compile(r"\blive\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlanBox:
    plan: str
    sig: str
    clauses: object  # "all", or a tuple of clause ids
    line: str


@dataclass(frozen=True)
class PlanBoxResult:
    boxes: tuple
    none_reason: str | None
    errors: tuple
    missing: bool

    @property
    def ok(self):
        return not self.errors


@dataclass(frozen=True)
class TickRow:
    plan: str
    sig: str
    state: str
    commits: tuple
    landed: object  # "all", or a tuple of clause ids
    owed: tuple  # ((clause, half), ...)
    close: str | None
    legacy: bool
    line: int


# ---- the Plan-Box trailer -----------------------------------------------------


def trailer_block(message):
    """The lines of the message's trailer paragraph, `-x` lines included."""
    paras: list[list[str]] = []
    cur: list[str] = []
    for raw in (message or "").splitlines():
        if raw.strip():
            cur.append(raw.rstrip())
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    if not paras:
        return []
    block = paras[-1]
    if len(paras) > 1 and all(_PICKED_RE.match(x.strip()) for x in block):
        block = paras[-2] + block
    return block


def _parse_value(value, line):
    """(PlanBox | None, none_reason | None, error | None) for one trailer value."""
    v = value.strip()
    m = _NONE_RE.match(v)
    if m:
        reason = m.group(1).strip()
        if len(reason) < NONE_REASON_MIN:
            return (
                None,
                None,
                "Plan-Box none reason shorter than %d characters: %r (%s)"
                % (NONE_REASON_MIN, line, GRAMMAR),
            )
        return None, reason, None
    parts = v.split()
    if len(parts) != 2:
        return (
            None,
            None,
            "malformed Plan-Box trailer, want a box and clauses=: %r (%s)" % (line, GRAMMAR),
        )
    ref, cl = parts
    if ref.count("#") != 1:
        return None, None, "Plan-Box trailer needs exactly one '#': %r (%s)" % (line, GRAMMAR)
    plan, sig = ref.split("#")
    if "/" in plan:
        return (
            None,
            None,
            "Plan-Box plan must be a basename under agent/plans/: %r (%s)" % (line, GRAMMAR),
        )
    if not _PLAN_RE.match(plan):
        return None, None, "Plan-Box plan is not a <PLAN-file>.md name: %r (%s)" % (line, GRAMMAR)
    if not _SIG_RE.match(sig):
        return None, None, "Plan-Box sig is not 8 lowercase hex: %r (%s)" % (line, GRAMMAR)
    if not cl.startswith("clauses="):
        return None, None, "Plan-Box trailer needs clauses=<ids|all>: %r (%s)" % (line, GRAMMAR)
    raw = cl[len("clauses=") :]
    if raw == "all":
        return PlanBox(plan, sig, "all", line), None, None
    ids = raw.split(",")
    if not raw or any(not _CLAUSE_RE.match(i) for i in ids) or "all" in ids:
        return (
            None,
            None,
            "Plan-Box clauses= is not a comma list of clause ids or 'all': %r (%s)"
            % (line, GRAMMAR),
        )
    if len(set(ids)) != len(ids):
        return None, None, "Plan-Box clauses= names a clause twice: %r (%s)" % (line, GRAMMAR)
    return PlanBox(plan, sig, tuple(ids), line), None, None


def parse_plan_box(message):
    """The Plan-Box trailers of one commit message, as a PlanBoxResult (module docstring)."""
    boxes: list[PlanBox] = []
    nones: list[str] = []
    errors: list[str] = []
    seen = 0
    for line in trailer_block(message):
        m = _KEY_RE.match(line)
        if not m:
            continue
        seen += 1
        if not line.startswith(TRAILER_KEY + ": "):
            errors.append(
                "Plan-Box trailer key must be spelled 'Plan-Box: ': %r (%s)" % (line, GRAMMAR)
            )
            continue
        box, reason, err = _parse_value(m.group(1), line)
        if err:
            errors.append(err)
        elif box is not None:
            if any((b.plan, b.sig) == (box.plan, box.sig) for b in boxes):
                errors.append("Plan-Box names %s#%s twice (%s)" % (box.plan, box.sig, GRAMMAR))
            else:
                boxes.append(box)
        else:
            nones.append(reason or "")
    if not seen:
        errors.append(NO_PLAN_BOX)
    if len(nones) > 1:
        errors.append("more than one 'Plan-Box: none' trailer (%s)" % GRAMMAR)
    if nones and boxes:
        errors.append(
            "'Plan-Box: none' beside a box trailer: a commit serves boxes or none (%s)" % GRAMMAR
        )
    return PlanBoxResult(tuple(boxes), nones[0] if nones else None, tuple(errors), not seen)


# ---- the TICK line, and the legacy prose reader ---------------------------------


def _list_field(raw):
    return () if raw == "-" else tuple(x for x in raw.split(",") if x)


def _tick_lines(lines):
    rows: list[TickRow] = []
    for i, raw in enumerate(lines):
        m = _TICK_LINE_RE.match(raw)
        if not m or m.group("state") not in TICK_STATES:
            continue
        plan = m.group("plan").rsplit("/", 1)[-1]
        landed = "all" if m.group("landed") == "all" else _list_field(m.group("landed"))
        owed = []
        for tok in _list_field(m.group("owed")):
            clause, _, half = tok.partition(":")
            # An unknown or missing half is the `?` placeholder, never carried as given (review 39bfb45b.2).
            owed.append((clause, half if half in HALVES else "?"))
        close = None
        if i + 1 < len(lines):
            c = _CLOSE_RE.match(lines[i + 1])
            if c:
                close = c.group(1)
        rows.append(
            TickRow(
                plan,
                m.group("sig"),
                m.group("state"),
                _list_field(m.group("commits")),
                landed,
                tuple(owed),
                close,
                False,
                i + 1,
            )
        )
    return rows


def _legacy_state(body, sig):
    m = re.search(r"\b%s\b(?:\s+[A-Z]+\d+)?\s+(%s)\b" % (sig, "|".join(TICK_STATES)), body)
    return m.group(1) if m else "unknown"


def _legacy(lines, body):
    anchors = [i for i, raw in enumerate(lines) if _LEGACY_ANCHOR_RE.search(raw)]
    order: list[tuple[str, str]] = []
    found: dict[tuple[str, str], dict] = {}
    for n, start in enumerate(anchors):
        end = anchors[n + 1] if n + 1 < len(anchors) else len(lines)
        plan = None
        key = None
        for i in range(start, end):
            raw = lines[i]
            # Every token of the line in reading order: a plan path, a box anchor, or a sha.
            toks = [
                (m.start(), kind, m.group(1))
                for kind, rx in (
                    ("plan", _LEGACY_PLAN_RE),
                    ("box", _LEGACY_BOX_RE),
                    ("sha", _LEGACY_SHA_RE),
                )
                for m in rx.finditer(raw)
            ]
            for _pos, kind, val in sorted(toks):
                if kind == "plan":
                    plan = val
                elif kind == "box":
                    if plan is None:
                        key = None
                        continue
                    key = (plan, val)
                    if key not in found:
                        order.append(key)
                        found[key] = {"commits": [], "line": i + 1, "live": False}
                elif (
                    key is not None
                    and val != key[1]
                    and re.search(r"\d", val)
                    and val not in found[key]["commits"]
                ):
                    found[key]["commits"].append(val)
            if key is not None and _LEGACY_LIVE_RE.search(raw):
                found[key]["live"] = True
    rows = []
    for key in order:
        f = found[key]
        state = _legacy_state(body, key[1])
        owed = (("*", "live"),) if f["live"] and state != "done" else ()
        rows.append(
            TickRow(key[0], key[1], state, tuple(f["commits"]), (), owed, None, True, f["line"])
        )
    return rows


def parse_tick(body):
    """The boxes one writer report names: TICK lines, else the legacy prose reader (module docstring)."""
    text = body or ""
    lines = text.splitlines()
    rows = _tick_lines(lines)
    if rows or any(_TICK_SHAPE_RE.match(raw) for raw in lines):
        return rows
    return _legacy(lines, text)


# ---- lease sha -> landed sha ------------------------------------------------------


def landed_map(root, lease_shas, rev="HEAD", since=None):
    """{lease sha: landed full sha} from the `-x` line on `rev` (module docstring).

    A lease sha may be short; it matches the full sha the `-x` line carries by prefix. When one lease sha was picked twice, the newest landed commit wins (git log order). `since` excludes history below it (a merge-base), which only narrows the search.
    """
    wanted = []
    for given in lease_shas or ():
        s = (given or "").strip().lower()
        if _HEX_ARG_RE.match(s) and s not in wanted:
            wanted.append(s)
    if not wanted:
        return {}
    # The PREFIX of the `-x` line, not PICKED_LINE whole: a short lease sha is followed by more hex, never by the closing parenthesis.
    greps = ["--grep=" + PICKED_PREFIX + s for s in wanted]
    narrow = ["--not", since] if since else []
    try:
        done = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(root),
                "log",
                "-F",
                *greps,
                "--format=%H%x00%B%x1e",
                rev,
                *narrow,
            ],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    out: dict[str, str] = {}
    lease_of: dict[str, str] = {}
    ambiguous: set[str] = set()
    for rec in done.stdout.split("\x1e"):
        landed, _, msg = rec.strip("\n").partition("\x00")
        if not landed:
            continue
        for line in msg.splitlines():
            m = _PICKED_RE.match(line.strip())
            if not m:
                continue
            for s in wanted:
                if not m.group(1).startswith(s):
                    continue
                # A short sha two DIFFERENT lease commits share names neither; one lease commit picked twice is not ambiguous, and its newest landing wins.
                if s in lease_of and not _same_sha(lease_of[s], m.group(1)):
                    ambiguous.add(s)
                elif s not in out:
                    out[s] = landed.strip()
                    lease_of[s] = m.group(1)
    return {s: v for s, v in out.items() if s not in ambiguous}


def _same_sha(a, b):
    """Whether two hex spellings can name one commit: one is a prefix of the other."""
    return a.startswith(b) or b.startswith(a)


# ---- the tree checks: plan, open box, clause map (T2, T3) -----------------------

PLANS_REL = ("agent", "plans")
PROGRESS_REL = ("agent", "ledgers", "plan-box-progress.jsonl")
STUB_HOPS = 3


def plan_rel_of(plan):
    """`agent/plans/<plan>` for a trailer's basename, the key the investigation ledger uses."""
    return "/".join((*PLANS_REL, plan))


def resolve_plan(root, plan):
    """`(rel, text)` of the plan a trailer basename names under `agent/plans/`, a `Moved-To:` stub followed, or None when no such plan exists."""
    import wl_store as S

    rel = plan_rel_of(plan)
    for _hop in range(STUB_HOPS):
        path = Path(root, rel)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        target = S.stub_target_of_text(text)
        if not target:
            return rel, text
        rel = target.removeprefix("./")
    return None


def progress_path(root):
    return Path(root, *PROGRESS_REL)


def read_progress(root):
    """[row] of `agent/ledgers/plan-box-progress.jsonl`, oldest first, [] when absent. A malformed line is skipped (the investigation ledger's rule)."""
    out: list[dict] = []
    try:
        raw = progress_path(root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _progress_lock(path):
    """The flock sidecar in TMPDIR, not beside the tracked ledger (the investigation ledger's reason, `wl_planrec._investigation_lock`)."""
    import hashlib
    import os

    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(base, "plan-box-progress-%s.lock" % key)


def _identity(rec):
    """Every field of a ledger row except `at` and `by`: the same fact written twice is one fact."""
    return json.dumps({k: v for k, v in rec.items() if k not in ("at", "by")}, sort_keys=True)


def append_progress(root, row):
    """Append ONE row to the progress ledger and return `(row as stored, written)`. A row whose identity (every field but `at` and `by`) equals the latest row of the same kind, box and clause is not appended again; that earlier row is returned with `written=False`. The read and the append sit under one flock. Never commits."""
    import wl_core as C
    import wl_store as S

    path = progress_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(row)
    rec.setdefault("at", C.stamp_now())
    same = _identity(rec)
    with open(_progress_lock(path) + ".dedupe", "a") as guard:
        S._flock(guard, getattr(S.fcntl, "LOCK_EX", 2))
        for prior in reversed(read_progress(root)):
            if (
                prior.get("kind") == rec.get("kind")
                and prior.get("sig") == rec.get("sig")
                and same_plan(prior.get("plan"), rec.get("plan"))
                and prior.get("clause") == rec.get("clause")
            ):
                if _identity(prior) == same:
                    return prior, False
                break
        S._append_lines(str(path), _progress_lock(path), [rec])
    return rec, True


def same_plan(a, b):
    """Two plan spellings (basename or repo-relative path) name the same plan file."""
    return str(a or "").rsplit("/", 1)[-1] == str(b or "").rsplit("/", 1)[-1]


def clause_map(root, plan, sig, rows=None):
    """The clauses of the LATEST `define` row of a box, as [{id, half, text}], or None when the box has no clause map."""
    rows = read_progress(root) if rows is None else rows
    found = None
    for r in rows:
        if r.get("kind") == "define" and r.get("sig") == sig and same_plan(r.get("plan"), plan):
            found = r
    if found is None:
        return None
    return [c for c in found.get("clauses") or [] if isinstance(c, dict) and c.get("id")]


def open_sigs(text):
    import wl_planrec as R

    return {b[3] for b in R.open_boxes(text)}


def box_problems(root, box, rows=None):
    """Why one parsed `PlanBox` cannot be landed against the tree at `root`, one phrase each ([] when it can)."""
    resolved = resolve_plan(root, box.plan)
    if resolved is None:
        return ["Plan-Box names %s, which is no plan under agent/plans/" % box.plan]
    rel, text = resolved
    if box.sig not in open_sigs(text):
        return ["Plan-Box names %s#%s, which is no open box of %s" % (box.plan, box.sig, rel)]
    if box.clauses == "all":
        return []
    cmap = clause_map(root, box.plan, box.sig, rows)
    if cmap is None:
        return [
            "Plan-Box names clauses %s of %s#%s, which has no clause map (write clauses=all, or "
            "define the clauses with worklist.py --box-clauses)"
            % (",".join(box.clauses), box.plan, box.sig)
        ]
    known = {c["id"] for c in cmap}
    unknown = [c for c in box.clauses if c not in known]
    if unknown:
        return [
            "Plan-Box names undefined clause(s) %s of %s#%s (defined: %s)"
            % (",".join(unknown), box.plan, box.sig, ",".join(sorted(known)) or "-")
        ]
    return []


def message_problems(root, message):
    """Every refusal of one commit message: the grammar first, then each box against the tree. [] admits it."""
    parsed = parse_plan_box(message)
    if not parsed.ok:
        return list(parsed.errors)
    rows = read_progress(root)
    out = []
    for box in parsed.boxes:
        out += box_problems(root, box, rows)
    return out


# ---- the clause verbs (T8): `--box-clauses` and `--box-progress` ------------------

PROGRESS_STATES = ("landed", "proved", "live-owed")
_SPEC_RE = re.compile(
    r"^\s*(?P<id>[A-Za-z0-9][A-Za-z0-9_.]*)\s+\[(?P<half>[a-z]+)\]\s+(?P<text>\S.*?)\s*$"
)
CLAUSE_SPEC = '"<id> [code|live|operator] <text>", e.g. "C1 [live] baseline read-only"'


class PlanBoxError(ValueError):
    """A clause verb refused; the message says why. The CLI exits 2 on it."""


def open_box(root, plan, selector):
    """`(rel, sig, body)` of the ONE open box `selector` names in `plan` (a basename or a repo-relative path), through `wl_planrec.open_boxes` and `select_box`. Raises PlanBoxError."""
    import wl_planrec as R

    given = str(plan or "").removeprefix(str(root).rstrip("/") + "/")
    folder, _, base = given.removeprefix("./").rpartition("/")
    # Only the basename resolves, so a path is admitted only where a plan lives: `docs/PLAN-fx.md` silently meant agent/plans/PLAN-fx.md (review 52b4512d.1).
    if folder not in PLAN_FOLDERS:
        raise PlanBoxError("%s is no plan under agent/plans/" % plan)
    resolved = resolve_plan(root, base) if _PLAN_RE.match(base) else None
    if resolved is None:
        raise PlanBoxError("%s is no plan under agent/plans/" % plan)
    rel, text = resolved
    try:
        _i, _line, body, sig = R.select_box(R.open_boxes(text), selector)
    except R.RecordError as exc:
        raise PlanBoxError(str(exc)) from exc
    return rel, sig, body


def parse_clause_specs(specs):
    """[{id, half, text}] from `C1 [code] <text>` strings. Raises PlanBoxError on a bad shape, an unknown half, the id `all` or a repeated id."""
    out: list[dict] = []
    for spec in specs:
        m = _SPEC_RE.match(spec or "")
        if not m:
            raise PlanBoxError("a clause is %s, not %r" % (CLAUSE_SPEC, spec))
        if m.group("half") not in HALVES:
            raise PlanBoxError(
                "clause %s names the half %r; a half is one of %s"
                % (m.group("id"), m.group("half"), ", ".join(HALVES))
            )
        if m.group("id") == "all":
            raise PlanBoxError("`all` is the trailer's word for every clause, never a clause id")
        if any(c["id"] == m.group("id") for c in out):
            raise PlanBoxError("clause %s is named twice" % m.group("id"))
        out.append({"id": m.group("id"), "half": m.group("half"), "text": m.group("text")})
    if not out:
        raise PlanBoxError("name at least one clause: %s" % CLAUSE_SPEC)
    return out


def define_row(root, plan, selector, specs, me):
    """The `define` row `--box-clauses` would append. Writes nothing; raises PlanBoxError."""
    rel, sig, _body = open_box(root, plan, selector)
    return {
        "kind": "define",
        "by": me,
        "plan": rel,
        "sig": sig,
        "clauses": parse_clause_specs(specs),
    }


def progress_row(root, plan, selector, clause, state, ref, me):
    """The `progress` row `--box-progress` would append. Writes nothing; raises PlanBoxError."""
    rel, sig, _body = open_box(root, plan, selector)
    if state not in PROGRESS_STATES:
        raise PlanBoxError("state %r is not one of %s" % (state, ", ".join(PROGRESS_STATES)))
    cmap = clause_map(root, rel, sig)
    known = {c["id"] for c in cmap or []}
    if clause != "all" and clause not in known:
        raise PlanBoxError(
            "clause %r is not defined for %s#%s (defined: %s)"
            % (clause, rel, sig, ",".join(sorted(known)) or "none, so only `all`")
        )
    if not str(ref or "").strip():
        raise PlanBoxError(
            "a progress row needs a ref: a landed sha, a live-proof row id or a note"
        )
    return {
        "kind": "progress",
        "by": me,
        "plan": rel,
        "sig": sig,
        "clause": clause,
        "state": state,
        "ref": str(ref).strip(),
    }


def box_state(root, plan, sig, rows=None):
    """{clause: (state, ref)} of the latest progress row per clause of one box."""
    rows = read_progress(root) if rows is None else rows
    out = {}
    for r in rows:
        if r.get("kind") == "progress" and r.get("sig") == sig and same_plan(r.get("plan"), plan):
            out[r.get("clause")] = (r.get("state"), r.get("ref"))
    return out


def listing(root, kind):
    """The bare-`<me>` listing of `--box-clauses` (kind `define`) or `--box-progress` (kind `progress`)."""
    rows = [r for r in read_progress(root) if r.get("kind") == kind]
    if kind == "define":
        latest = {}
        for r in rows:
            latest[(str(r.get("plan")).rsplit("/", 1)[-1], r.get("sig"))] = r
        out = ["clause maps: %d box(es) in %s" % (len(latest), "/".join(PROGRESS_REL))]
        for (plan, sig), r in sorted(latest.items()):
            out.append(
                "  %s#%s  %s"
                % (
                    plan,
                    sig,
                    " ".join(
                        "%s[%s]" % (c.get("id"), c.get("half")) for c in r.get("clauses") or []
                    ),
                )
            )
        return "\n".join(out) + "\n"
    out = ["box progress: %d row(s) in %s" % (len(rows), "/".join(PROGRESS_REL))]
    for r in rows[-40:]:
        out.append(
            "  %s#%s %s %s %s"
            % (
                str(r.get("plan")).rsplit("/", 1)[-1],
                r.get("sig"),
                r.get("clause"),
                r.get("state"),
                str(r.get("ref"))[:40],
            )
        )
    return "\n".join(out) + "\n"


def main(argv):
    """`wl_planbox.py check --root <dir>`: the commit message on stdin, each refusal on stderr, exit 1 when refused. The lease commit-msg hook runs this as a process, so its sibling imports resolve without a `sys.path` entry in the hook."""
    if len(argv) != 3 or argv[0] != "check" or argv[1] != "--root":
        sys.stderr.write("usage: wl_planbox.py check --root <dir> < message\n")
        return 2
    problems = message_problems(argv[2], sys.stdin.read())
    for p in problems:
        sys.stderr.write(p + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
