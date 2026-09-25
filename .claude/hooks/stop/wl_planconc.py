"""wl_planconc: plan priority order and plan concurrency (agent/plans/PLAN-plan-priority-concurrency.md sections 2-5).

THE ASK (operator, 2026-09-25, section X): "Rank the work, not just order it. [...] The concurrency field is really about files. 'Exclusive' is only needed when two plans touch the same files [...] Declaring the owned paths lets the hook decide instead of relying on a label." The grammar of the three header lines lives in `wl_plandeps` (one grammar); this module is what the lines MEAN.

FOUR THINGS, each a pure function over parsed headers plus one reader of the live world:

  normalize_owns / owns_overlap   section 4: an EXACT, symbolic glob-intersection test. It needs no `git ls-files`
                                  and covers files that do not exist yet, and every "yes" comes with one concrete
                                  witness path, so a refusal can say "both claim .claude/hooks/stop/wl_roster.py".
  item_plan / spawn_plans         section 3: which plan a worklist item, or a writer spawn's prompt, serves.
  live_plans                      section 3: {plan: [holder, ...]} from this session's live writers and every
                                  session's fresh leases. None when it cannot tell (the caller fails open, loudly).
  spawn_verdict                   section 5: the mutex and overlap decision, shared by the pre-agent guard
                                  `block_plan_concurrency.py` and (T8/T9) the roster and the queue lease.
  rank / order_key                section 2: dependencies, then operator priority, then AI priority, then age.

SEALED. Reads no environment variable and imports only the standard library and `wl_plandeps` at import time; `wl_roster`, `wl_leasehelp` and `wl_core` are imported inside `live_plans`, the one function that reads the live world. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`, so an environment read added here is CI red: a knob that retuned what counts as an overlap would be an escape hatch by another name.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
from typing import Any

import wl_plandeps as D

# ---------------------------------------------------------------- the sealed constants

# The most globs one brace pattern may expand to (section 1). More is a typo or a hidden `**`.
BRACE_MAX = 32
# Paths written only through the worklist verbs, append-only and per-session, so two plans that both "touch" them do not collide (section 1, confirmed against `wl_store.store_dir` = agent/worklist/ and the per-session agent/<me>/STATE.md cursor).
IGNORED_GLOBS = ("agent/worklist/**", "agent/*/STATE.md")
# The globs that claim everything: a `parallel` plan declaring one is exclusive in disguise (D15).
UNIVERSAL_GLOBS = frozenset({"**", "*", "**/*", "**/**"})
# What an unparseable or missing Owns is read as once the fields are mandatory: fail closed, toward refusal.
FAIL_CLOSED_GLOB = "**"
# How much of a plan's head the spawn-path reader parses. The X window is 12 lines; a plan's first 12 lines never approach this.
HEAD_BYTES = 16384
# An item that no plan claims ranks as an AI P2 (decision D3): ad-hoc fixes are neither starved behind every P3 plan nor jump past P0/P1 plans.
UNLINKED_RANK = (4, 2)
# The rank of a plan whose Priority is missing or malformed.
UNRANKED = (4, 4)

PLAN_LINE_RE = re.compile(r"^Plan:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
PROMPT_OWNS_RE = re.compile(r"^Owns:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
BASENAME_RE = re.compile(r"^(?:.*/)?(PLAN-[A-Za-z0-9._-]+\.md)$")


# ---------------------------------------------------------------- globs: normalisation


def expand_braces(glob: str, limit: int = BRACE_MAX) -> list[str]:
    """Every expansion of `{a,b}` groups, nested groups included, in order. ValueError past `limit` or on an unbalanced brace."""
    out = [""]
    i = 0
    while i < len(glob):
        ch = glob[i]
        if ch == "}":
            raise ValueError("an unbalanced `}` in %r" % glob)
        if ch != "{":
            out = [o + ch for o in out]
            i += 1
            continue
        depth, j, parts, cur = 1, i + 1, [], []
        while j < len(glob) and depth:
            c = glob[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if not depth:
                    break
            if c == "," and depth == 1:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(c)
            j += 1
        if depth:
            raise ValueError("an unbalanced `{` in %r" % glob)
        parts.append("".join(cur))
        alts: list[str] = []
        for part in parts:
            alts.extend(expand_braces(part, limit))
        out = [o + a for o in out for a in alts]
        if len(out) > limit:
            raise ValueError("%r expands to more than %d globs" % (glob, limit))
        i = j + 1
    return out


def glob_problem(glob: str) -> str:
    """Why one raw glob is refused (section 1), or ""."""
    if not glob:
        return "an empty glob"
    if glob.startswith("/"):
        return "%r is absolute; Owns globs are relative to the repo root" % glob
    if glob.startswith("!"):
        return "%r is a negation; Owns lists what a plan edits, never what it does not" % glob
    if "\\" in glob:
        return "%r carries a backslash; write `/`-separated repo paths" % glob
    if ".." in glob.split("/"):
        return "%r climbs out with `..`" % glob
    return ""


def normalize_owns(globs, root=None) -> tuple[list[str], list[str]]:
    """(normalised globs, problems). Refusal rules first, then brace expansion (at most BRACE_MAX per glob), then `dir/` and a wildcard-free existing directory become `dir/**` (the latter only when `root` is given). A leading `./` and doubled slashes are dropped."""
    out: list[str] = []
    problems: list[str] = []
    for raw in globs or ():
        glob = str(raw).strip()
        why = glob_problem(glob)
        if why:
            problems.append(why)
            continue
        try:
            expanded = expand_braces(glob)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        for raw_g in expanded:
            g = re.sub(r"/{2,}", "/", raw_g)
            while g.startswith("./"):
                g = g[2:]
            if g.endswith("/"):
                g = g.rstrip("/") + "/**"
            elif root is not None and not _has_wild(g) and (pathlib.Path(root) / g).is_dir():
                g += "/**"
            why = glob_problem(g)
            if why:
                problems.append(why)
                continue
            if g and g not in out:
                out.append(g)
    return out, problems


def _has_wild(glob: str) -> bool:
    return any(c in glob for c in "*?[")


def is_universal(glob: str) -> bool:
    return glob in UNIVERSAL_GLOBS


def is_ignored(glob: str) -> bool:
    """True when every path `glob` can name lies in IGNORED_GLOBS' verb-written state."""
    if glob.startswith("agent/worklist/"):
        return True
    segs = glob.split("/")
    return len(segs) == 3 and segs[0] == "agent" and segs[2] == "STATE.md" and "**" not in segs[1]


# ---------------------------------------------------------------- globs: the intersection engine

_STAR, _ANY, _LIT, _CLS = "star", "any", "lit", "cls"


def _tokens(seg: str) -> list[tuple]:
    """One path segment as tokens: ('star',), ('any',), ('lit', ch), ('cls', frozenset, negated). An unterminated `[` is a literal."""
    out: list[tuple] = []
    i = 0
    while i < len(seg):
        c = seg[i]
        if c == "*":
            if not out or out[-1] != (_STAR,):
                out.append((_STAR,))
            i += 1
        elif c == "?":
            out.append((_ANY,))
            i += 1
        elif c == "[":
            j = i + 1
            neg = j < len(seg) and seg[j] in "!^"
            if neg:
                j += 1
            start = j
            if j < len(seg) and seg[j] == "]":
                j += 1
            while j < len(seg) and seg[j] != "]":
                j += 1
            if j >= len(seg):
                out.append((_LIT, c))
                i += 1
                continue
            body, members = seg[start:j], set()
            k = 0
            while k < len(body):
                if k + 2 < len(body) and body[k + 1] == "-":
                    members.update(chr(x) for x in range(ord(body[k]), ord(body[k + 2]) + 1))
                    k += 3
                else:
                    members.add(body[k])
                    k += 1
            out.append((_CLS, frozenset(members), neg))
            i = j + 1
        else:
            out.append((_LIT, c))
            i += 1
    return out


_PICK = "xyzabcdefghijklmnopqrstuvw0123456789_-."


def _meet(a: tuple, b: tuple) -> str | None:
    """A character both single-character tokens accept, or None."""

    def accepts(tok, ch):
        if tok[0] == _LIT:
            return tok[1] == ch
        if tok[0] == _ANY:
            return ch != "/"
        return (ch in tok[1]) != tok[2]

    cands: list[str] = []
    for tok in (a, b):
        if tok[0] == _LIT:
            cands.append(tok[1])
        elif tok[0] == _CLS and not tok[2]:
            cands.extend(sorted(tok[1]))
    cands.extend(_PICK)
    for ch in cands:
        if ch != "/" and accepts(a, ch) and accepts(b, ch):
            return ch
    return None


def seg_intersect(p: str, q: str) -> str | None:
    """A string both segment patterns match, or None when they share none. Exact over `*`, `?`, literals and classes; a class-vs-class meet is searched over the classes' own members and a fixed alphabet, which can only err toward "overlap" when a negated class excludes that whole alphabet."""
    tp, tq = _tokens(p), _tokens(q)
    memo: dict[tuple[int, int], str | None] = {}

    def go(i: int, j: int) -> str | None:
        key = (i, j)
        if key in memo:
            return memo[key]
        memo[key] = None  # cycle guard: a star absorbing nothing twice is never progress
        res: str | None = None
        if i == len(tp) and j == len(tq):
            res = ""
        else:
            a = tp[i] if i < len(tp) else None
            b = tq[j] if j < len(tq) else None
            if a == (_STAR,):
                res = go(i + 1, j)
                if res is None and b is not None and b != (_STAR,):
                    ch = _meet(b, b)
                    rest = go(i, j + 1)
                    res = None if ch is None or rest is None else ch + rest
            if res is None and b == (_STAR,):
                res = go(i, j + 1)
                if res is None and a is not None and a != (_STAR,):
                    ch = _meet(a, a)
                    rest = go(i + 1, j)
                    res = None if ch is None or rest is None else ch + rest
            if res is None and a is not None and b is not None and _STAR not in (a[0], b[0]):
                ch = _meet(a, b)
                if ch is not None:
                    rest = go(i + 1, j + 1)
                    res = None if rest is None else ch + rest
        memo[key] = res
        return res

    got = go(0, 0)
    if got == "":
        # Two all-star patterns meet on the empty string, which is no path segment; "x" is one both accept.
        return "x" if tp and tq else ("" if not tp and not tq else None)
    return got


def path_intersect(p: str, q: str) -> str | None:
    """A concrete path both globs match, or None. `**` spans zero or more whole segments; every other segment is matched by `seg_intersect`."""
    sp = [s for s in p.split("/") if s]
    sq = [s for s in q.split("/") if s]
    memo: dict[tuple[int, int], list[str] | None] = {}

    def go(i: int, j: int) -> list[str] | None:
        key = (i, j)
        if key in memo:
            return memo[key]
        memo[key] = None
        res: list[str] | None = None
        if i == len(sp) and j == len(sq):
            res = []
        else:
            a = sp[i] if i < len(sp) else None
            b = sq[j] if j < len(sq) else None
            if a == "**":
                res = go(i + 1, j)
                if res is None and b is not None:
                    if b == "**":
                        res = go(i, j + 1)
                    else:
                        w = seg_intersect(b, b)
                        rest = go(i, j + 1)
                        res = None if w is None or rest is None else [w, *rest]
            if res is None and b == "**":
                res = go(i, j + 1)
                if res is None and a is not None and a != "**":
                    w = seg_intersect(a, a)
                    rest = go(i + 1, j)
                    res = None if w is None or rest is None else [w, *rest]
            if res is None and a is not None and b is not None and "**" not in (a, b):
                w = seg_intersect(a, b)
                if w is not None:
                    rest = go(i + 1, j + 1)
                    res = None if rest is None else [w, *rest]
        memo[key] = res
        return res

    got = go(0, 0)
    if got is None:
        return None
    return "/".join(got) if got else "x"


def owns_overlap(a, b) -> list[tuple[str, str, str]]:
    """[(glob of a, glob of b, witness path)] for every pair of normalised globs that share a path, IGNORED_GLOBS excluded. Both sides are normalised first; a refused glob on either side is skipped here (it is D14's finding, not an overlap)."""
    na, _pa = normalize_owns(a)
    nb, _pb = normalize_owns(b)
    out = []
    for ga in na:
        if is_ignored(ga):
            continue
        for gb in nb:
            if is_ignored(gb):
                continue
            w = path_intersect(ga, gb)
            if w is not None:
                out.append((ga, gb, w))
    return out


_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def glob_regex(glob: str) -> re.Pattern[str]:
    """One normalised glob as an anchored regex over a repo-relative path: `**` spans segments, `*` and `?` stay inside one, `[...]` is a class. For materialising a glob against a file list, where the symbolic `path_intersect` would be one DP per file."""
    got = _REGEX_CACHE.get(glob)
    if got is not None:
        return got
    parts: list[str] = []
    segs = glob.split("/")
    for n, seg in enumerate(segs):
        last = n == len(segs) - 1
        if seg == "**":
            parts.append(".*" if last else "(?:[^/]*/)*")
            continue
        body = []
        for tok in _tokens(seg):
            if tok[0] == _STAR:
                body.append("[^/]*")
            elif tok[0] == _ANY:
                body.append("[^/]")
            elif tok[0] == _LIT:
                body.append(re.escape(tok[1]))
            else:
                chars = "".join(re.escape(c) for c in sorted(tok[1]))
                body.append("[%s%s]" % ("^" if tok[2] else "", chars))
        parts.append("".join(body) + ("" if last else "/"))
    got = re.compile("^" + "".join(parts) + "$")
    _REGEX_CACHE[glob] = got
    return got


def materialise(globs, files) -> list[str]:
    """The members of `files` (repo-relative paths) any of the normalised `globs` names, in `files` order."""
    pats = [glob_regex(g) for g in globs]
    return [f for f in files if any(p.match(f) for p in pats)]


# ---------------------------------------------------------------- the X verdict on one header


@dataclasses.dataclass(frozen=True)
class XFinding:
    """One D10-D16 finding. `missing` marks "the field is absent", which `wl_plandeps.X_FIELDS_REQUIRED` decides whether to enforce; every other finding is a malformed line that is present."""

    code: str
    message: str
    missing: bool = False


_SPINE_KEYS = ("Status", "Owner", "Full-Text", "Full-Text-Blob", "Record-Sig")


def x_findings(header: D.Header, text: str = "") -> list[XFinding]:
    """D10-D16 for one plan's header (section 6b). Requiredness is the caller's question. `text` enables the D16 spine check (a Status/Owner/record field pushed past line 10)."""
    out: list[XFinding] = []
    window = "outside the %d-line header window" % D.X_HEADER_LINES
    codes = {D.PRIORITY: D.D_PRIORITY_MALFORMED, D.CONCURRENCY: D.D_CONCURRENCY, D.OWNS: D.D_OWNS}
    for name in D.X_FIELDS:
        structural = [msg for fname, msg in header.errors if fname == name]
        out.extend(
            XFinding(D.D_WINDOW if window in msg else codes[name], "%s: %s" % (name, msg))
            for msg in structural
        )
        f = header.get(name)
        if f is None:
            if not structural:
                code = D.D_PRIORITY_MISSING if name == D.PRIORITY else codes[name]
                out.append(
                    XFinding(
                        code,
                        "no `%s:` line in the first %d lines" % (name, D.X_HEADER_LINES),
                        missing=True,
                    )
                )
            continue
        out.extend(XFinding(codes[name], "%s: %s" % (name, e)) for e in f.errors)
    owns = header.owns
    if owns is not None and owns.globs:
        norm, problems = normalize_owns(owns.globs)
        out.extend(XFinding(D.D_OWNS_GLOB, "Owns: %s" % p) for p in problems)
        conc = header.concurrency
        if conc is not None and not conc.exclusive:
            wide = [g for g in norm if is_universal(g)]
            if wide:
                out.append(
                    XFinding(
                        D.D_UNIVERSAL,
                        "a `parallel` plan claims %s, which is every file: exclusive in disguise. "
                        "Narrow Owns, or declare `Concurrency: exclusive -- <reason>`"
                        % ", ".join(wide),
                    )
                )
    if text:
        lines = text.splitlines(keepends=True)
        try:
            end = D.header_block_end(lines)
        except ValueError:
            end = 0
        for idx in range(D.HEADER_LINES, end):
            m = re.match(r"^([A-Za-z][A-Za-z-]*):", lines[idx])
            if m and m.group(1) in _SPINE_KEYS:
                out.append(
                    XFinding(
                        D.D_WINDOW,
                        "`%s:` sits at line %d, past the %d-line window every header reader uses"
                        % (m.group(1), idx + 1, D.HEADER_LINES),
                    )
                )
    return out


# ---------------------------------------------------------------- which plan an item or a spawn serves


def _base(token: str) -> str | None:
    m = BASENAME_RE.match((token or "").strip())
    return m.group(1) if m else None


def item_plan(rec: dict) -> str | None:
    """Section 3: the `PLAN-x.md [<8hex>]` link in the item's own text first, then a `plan-subagent` triage's recorded plan, else None."""
    if not isinstance(rec, dict):
        return None
    got = D.linked_plan(str(rec.get("basetext") or rec.get("text") or ""))
    if got:
        return got
    tri = rec.get("triage") or {}
    if isinstance(tri, dict) and tri.get("v") == "plan-subagent":
        return _base(str(tri.get("plan") or ""))
    return None


def spawn_plans(text: str, by_id: dict | None = None) -> set[str]:
    """Section 3: the plans a spawn's prompt+description serves. An explicit `Plan: PLAN-x.md[, PLAN-y.md]` line wins; else every `#<id>` that names an item linked to a plan; else every bare `PLAN-x.md [<8hex>]` token."""
    text = str(text or "")
    out: set[str] = set()
    for m in PLAN_LINE_RE.finditer(text):
        for tok in m.group(1).split(","):
            b = _base(tok.split(" -- ")[0])
            if b:
                out.add(b)
    if out:
        return out
    if by_id:
        import wl_leasehelp as LH  # noqa: PLC0415 -- pure, but kept off the import path of the sealed module

        for ref in LH.item_refs(text):
            rid = LH.resolve(ref, by_id)
            plan = item_plan(by_id[rid]) if rid is not None else None
            if plan:
                out.add(plan)
        if out:
            return out
    return {m.group(1) for m in D.LINK_RE.finditer(text)}


def declared_owns(text: str) -> tuple[str, ...] | None:
    """A planless spawn's own `Owns: <globs>` line (decision D4), or None when it declares none. A malformed line reads as none."""
    m = PROMPT_OWNS_RE.search(str(text or ""))
    if not m:
        return None
    owns, errors = D.parse_owns(m.group(1))
    if errors or owns is None:
        return None
    return owns.globs


# ---------------------------------------------------------------- reading plan headers on the spawn path


def read_header(root, base: str) -> tuple[str, D.Header] | None:
    """(rel, header) for one plan basename, looked up in agent/plans, then _done and _removed; None when no file carries it."""
    for folder in D.PLAN_DIRS:
        path = pathlib.Path(root) / folder / base
        try:
            with path.open("rb") as fh:
                text = fh.read(HEAD_BYTES).decode("utf-8", errors="replace")
        except OSError:
            continue
        return "%s/%s" % (folder, base), D.parse_header(text)
    return None


def exclusive_plans(root) -> set[str]:
    """Every top-level plan whose header declares `Concurrency: exclusive`. Cheap (heads only), so the spawn guard can skip the store read when no mutex exists anywhere."""
    out: set[str] = set()
    try:
        names = sorted(p.name for p in (pathlib.Path(root) / D.PLANS_DIR).glob("PLAN-*.md"))
    except OSError:
        return out
    for name in names:
        got = read_header(root, name)
        if got is None:
            continue
        conc = got[1].concurrency
        if conc is not None and conc.exclusive and not D.is_stub_header(got[1]):
            out.add(name)
    return out


@dataclasses.dataclass(frozen=True)
class PlanX:
    """What spawn_verdict needs of one plan. `owns` is the normalised glob list, `()` for `Owns: none`, and None when the field is missing or malformed."""

    base: str
    exclusive: bool = False
    reason: str = ""
    owns: tuple[str, ...] | None = None
    owns_none: bool = False
    found: bool = True


def plan_x(root, base: str) -> PlanX:
    got = read_header(root, base)
    if got is None:
        return PlanX(base, found=False)
    header = got[1]
    conc = header.concurrency
    owns = header.owns
    norm: tuple[str, ...] | None = None
    if owns is not None:
        globs, problems = normalize_owns(owns.globs, root)
        norm = None if problems else tuple(globs)
    return PlanX(
        base,
        exclusive=bool(conc and conc.exclusive),
        reason=conc.reason if conc else "",
        owns=norm,
        owns_none=bool(owns is not None and not owns.globs),
    )


# ---------------------------------------------------------------- the live world


def live_plans(cwd, session_id, fold, now=None) -> dict[str, list[str]] | None:
    """Section 3: {plan basename: [holder, ...]} for every plan a live writer serves, or None when it cannot tell.

    This session: each live writer row (`wl_roster.live_estimate`), resolved through its first prompt with `spawn_plans`, plus any fresh lease to that writer on a plan-linked item. Other sessions: every fresh lease on a plan-linked item whose worker is neither `queue` nor `lead`. None only when the writer estimate is blind AND no cross-session lease is visible; the caller fails open on None and the Stop hook recounts.
    """
    import wl_core as C  # noqa: PLC0415 -- the live world is read only here
    import wl_leasehelp as LH  # noqa: PLC0415
    import wl_roster  # noqa: PLC0415

    rows, metas = wl_roster.live_estimate(cwd, session_id, now=now)
    items = list(getattr(fold, "items", None) or [])
    by_id = {r["id"]: r for r in items if isinstance(r, dict) and r.get("id")}
    holders: dict[str, list[str]] = {}
    live_ids: set[str] = set()
    for row in rows or []:
        if not row.get("writer"):
            continue
        live_ids.add(row["id"])
        meta = metas.get(row["id"]) or {}
        prompt = LH.first_prompt(meta.get("jsonl")) if meta.get("jsonl") else ""
        for plan in sorted(spawn_plans("%s\n%s" % (row.get("desc") or "", prompt), by_id)):
            holders.setdefault(plan, []).append(
                "writer %s (%s)" % (row["id"], row.get("type") or "?")
            )
    peers = 0
    for rec in items:
        if rec.get("state") != ">":
            continue
        worker = str(rec.get("worker") or "")
        if not worker or worker in (LH.QUEUE_WORKER, LH.LEAD_WORKER):
            continue
        if C.lease_state(str(rec.get("line") or "")) != "fresh":
            continue
        plan = item_plan(rec)
        if not plan:
            continue
        mine = C.owned_by_me(rec.get("owner"), session_id)
        if mine and not any(
            worker == w or w.startswith(worker) or worker.startswith(w) for w in live_ids
        ):
            continue
        if not mine:
            peers += 1
        label = "lease #%s worker:%s%s" % (
            rec["id"],
            worker,
            "" if mine else " (session %s)" % str(rec.get("owner") or "?")[:8],
        )
        if label not in holders.get(plan, []):
            holders.setdefault(plan, []).append(label)
    if rows is None and not peers:
        return None
    return holders


# ---------------------------------------------------------------- the spawn verdict


@dataclasses.dataclass(frozen=True)
class Verdict:
    """`allow` is the answer. `kind` names the rule that decided it; `lines` are the reader-facing facts (holder, globs, witness); `note` is a stderr line for an ALLOW that is worth saying."""

    allow: bool
    kind: str
    lines: tuple[str, ...] = ()
    note: str = ""


def _owns_of(x: PlanX, required: bool) -> tuple[str, ...] | None:
    """A plan's Owns for overlap: its globs, `()` for none, FAIL_CLOSED_GLOB when missing and the fields are mandatory, None (unknown, not judged) when missing before the migration."""
    if x.owns is not None:
        return x.owns
    return (FAIL_CLOSED_GLOB,) if required else None


def spawn_verdict(serving, live, xinfo, declared=None, required=None) -> Verdict:
    """Section 5a steps 2-6 as one pure decision.

    `serving` is the set of plan basenames the spawn serves; `live` is live_plans' map; `xinfo(base) -> PlanX`; `declared` is a planless spawn's own Owns globs or None; `required` defaults to `wl_plandeps.X_FIELDS_REQUIRED`. Before the migration a missing Owns is UNKNOWN and not judged (the spawn is allowed with a note); after it, a missing Owns fails closed as `**`.
    """
    required = D.X_FIELDS_REQUIRED if required is None else required
    serving = set(serving or ())
    others = {p: h for p, h in (live or {}).items() if p not in serving and h}
    notes: list[str] = []
    xs = {p: xinfo(p) for p in serving}
    xl = {p: xinfo(p) for p in others}

    def holder(p):
        x = xl[p]
        return "%s is %s and live (%s)" % (
            p,
            "exclusive -- %s" % x.reason if x.exclusive else "parallel",
            "; ".join(others[p][:3]),
        )

    for s, x in sorted(xs.items()):
        if x.owns_none:
            return Verdict(
                False,
                "owns-none",
                ("%s declares `Owns: none`, so a writer serving it is a contradiction" % s,),
            )
        if x.owns is None and required:
            return Verdict(
                False,
                "no-owns",
                ("%s declares no valid Owns; add it with `check_plan_deps.py --set-x`" % s,),
            )
        if x.owns is None:
            notes.append(
                "%s declares no Owns yet (optional until the migration), so its overlap is not judged"
                % s
            )
    for p in sorted(xl):
        if xl[p].exclusive:
            return Verdict(False, "mutex", (holder(p),))
    if serving and others:
        for s in sorted(xs):
            if xs[s].exclusive:
                return Verdict(
                    False,
                    "mutex-own",
                    (
                        "%s is exclusive -- %s, and it cannot start while other plans are live"
                        % (s, xs[s].reason),
                        *(holder(p) for p in sorted(xl)),
                    ),
                )
    mine: tuple[str, ...] | None
    if serving:
        union: list[str] = []
        unknown = False
        for s in sorted(xs):
            got = _owns_of(xs[s], required)
            if got is None:
                unknown = True
            else:
                union.extend(got)
        mine = None if unknown and not union else tuple(union)
    else:
        mine = tuple(declared) if declared is not None else None
    if mine is None:
        if not serving:
            notes.append(
                "a planless writer spawn declares no `Owns:` line, so its files are not checked against live plans"
            )
        return Verdict(True, "unjudged", (), "; ".join(notes))
    for p in sorted(xl):
        theirs = _owns_of(xl[p], required)
        if theirs is None:
            continue
        hits = owns_overlap(mine, theirs)
        if hits:
            ga, gb, w = hits[0]
            return Verdict(
                False,
                "overlap",
                (
                    holder(p),
                    "this spawn claims `%s` and %s claims `%s`; both claim `%s`" % (ga, p, gb, w),
                ),
            )
    return Verdict(True, "ok", (), "; ".join(notes))


# ---------------------------------------------------------------- ranking


def own_rank(header: D.Header | None) -> tuple[int, int]:
    """(op_rank, ai_rank): `Pn (operator)` is (n, 4), `Pn` is (4, n), missing or malformed is (4, 4)."""
    pr = header.priority if header is not None else None
    if pr is None:
        return UNRANKED
    return (pr.level, 4) if pr.operator else (4, pr.level)


def _dependents(graph: D.Graph) -> dict[str, set[str]]:
    """Reverse edges: target rel -> the rels whose Depends-On names it, among plans that are not finished."""
    rev: dict[str, set[str]] = {}
    for rel in graph.plans:
        if graph.plans[rel].stub or not graph.is_required(rel):
            continue
        for _edge, target in graph._succ(rel):
            rev.setdefault(target, set()).add(rel)
    return rev


def rank(rel: str, graph: D.Graph, _rev: dict[str, set[str]] | None = None) -> tuple[int, int]:
    """Section 2 with dependency inheritance (decision D6): the most urgent (op, ai) among the plan and every live plan that depends on it, directly or transitively. Cycle-safe."""
    rev = _dependents(graph) if _rev is None else _rev
    best = own_rank(graph.plans[rel].header if rel in graph.plans else None)
    seen = {rel}
    stack = list(rev.get(rel, ()))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        best = min(best, own_rank(graph.plans[cur].header))
        stack.extend(rev.get(cur, ()))
    return best


class OrderCtx:
    """Built once per stop: the graph, its reverse edges, and memoised ranks and blockers."""

    def __init__(self, graph: D.Graph):
        self.graph = graph
        self._rev = _dependents(graph)
        self._ranks: dict[str, tuple[int, int]] = {}
        self._blocked: dict[str, int] = {}

    def rel_of(self, base: str | None) -> str | None:
        """The live plan file a basename names, or None (unknown, finished or withdrawn plans rank as unlinked)."""
        if not base:
            return None
        t = self.graph.resolve(base)
        return t.rel if t.state == D.LIVE else None

    def plan_key(self, rel: str) -> tuple[int, int, int]:
        """(blocked, op_rank, ai_rank) for one live plan."""
        if rel not in self._ranks:
            self._ranks[rel] = rank(rel, self.graph, self._rev)
            self._blocked[rel] = 1 if self.graph.roots(rel) else 0
        return (self._blocked[rel], *self._ranks[rel])


def order_ctx(graph: D.Graph) -> OrderCtx:
    return OrderCtx(graph)


def order_key(rec: dict, ctx: OrderCtx, age: Any = None) -> tuple:
    """Section 2: (blocked, op_rank, ai_rank, age). `age` defaults to the item's `first` stamp (ascending, oldest first); a picker with its own age term (the queue's `lease_at`, the backlog's mtime) passes it. An unlinked item is an AI P2 (decision D3)."""
    age = str(rec.get("first") or "") if age is None else age
    rel = ctx.rel_of(item_plan(rec))
    if rel is None:
        return (0, *UNLINKED_RANK, age)
    return (*ctx.plan_key(rel), age)


def rank_label(op: int, ai: int) -> str:
    """`[P1 op]`, `[P3]`, or `[P-]` for an unranked plan: the guide's display tag (section 8, o5)."""
    if op < 4:
        return "[P%d op]" % op
    if ai < 4:
        return "[P%d]" % ai
    return "[P-]"
