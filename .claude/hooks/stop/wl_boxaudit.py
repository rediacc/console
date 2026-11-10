"""wl_boxaudit: one verdict per open plan box from five sources (agent/plans/PLAN-tick-tracking.md Design 4, box T9).

THE FIVE SOURCES, read per open box of a live plan:

1. landed commits on HEAD since the merge-base with main whose `Plan-Box:` trailer names the box (`wl_planbox.parse_plan_box`);
2. captured writer reports whose TICK lines name the box (`wl_planbox.parse_tick`, the legacy prose reader included), each named lease sha mapped to its landed sha by the `-x` line (`wl_planbox.landed_map`); a report row whose commits never landed links nothing;
3. VERIFIED rows for the box in `agent/ledgers/live-proof.jsonl` (`wl_liveproof.verified_rows`);
4. the latest investigation row (`wl_planrec.investigation_for`);
5. the `define` and `progress` rows of `agent/ledgers/plan-box-progress.jsonl`.

ONE VERDICT PER BOX, first match wins:

- `tickable-now`: every clause (or `all`) is landed or proved, and a live investigation row exists. The ready `--plan-tick` line is printed.
- `stale-investigation`: work is linked, but the latest row's `head` is unreachable from HEAD with no rebase successor (a commit on the branch with the same author time and subject), or the row was taken before the merge-base (`wl_planpreflight.survey`'s `current` rule).
- `live-owed`: something landed and a live or operator clause is not proved. A box with no clause map owes its live half when its latest report TICK carries a live or operator owed entry, when a progress row records `live-owed`, or when it is an `LP-` box with no VERIFIED row.
- `linked`: work is linked and none of the above holds (a code clause still open, or no investigation row yet). This fifth verdict is the plan's deviation note: Design 4 names four, and a box with landed code, no row and nothing owed live fits none of them.
- `untouched`: nothing linked. A box whose worklist item is leased to a live writer is shown with that lease by the caller.

`investigated` is a separate fact on every row, because `plan-box-owed` (T10) asks exactly "landed work, no investigation row".

REPORT SCOPE. Only reports captured since the merge-base's commit time are read, and a body is parsed only when it holds the word TICK or the index row already carries `boxes` (T6): the store holds every report of every branch, tens of megabytes, and the audit runs inside a Stop hook.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import json
import os
import pathlib
import re
import subprocess
from typing import Any

import wl_planbox as PB

VERDICTS = ("tickable-now", "stale-investigation", "live-owed", "linked", "untouched")
OWED_VERDICTS = ("tickable-now", "live-owed")
LIVE_HALVES = ("live", "operator")
GIT_TIMEOUT_S = 60
SHOWN_LANDED = 4
CACHE_NAME = "box-audit-%s.json"


@dataclasses.dataclass
class BoxAudit:
    plan: str
    sig: str
    body: str
    landed: list = dataclasses.field(default_factory=list)  # [(landed sha, source)]
    reports: list = dataclasses.field(default_factory=list)  # [(report id, TickRow)]
    covered: set = dataclasses.field(default_factory=set)
    owed: list = dataclasses.field(default_factory=list)  # [(clause, half)]
    cmap: Any = None
    inv: Any = None
    lp: list = dataclasses.field(default_factory=list)
    progress: dict = dataclasses.field(default_factory=dict)
    verdict: str = "untouched"
    why: str = ""
    tick: str = ""
    investigate: str = ""

    @property
    def investigated(self):
        return self.inv is not None and not self.inv.get("retro")

    @property
    def linked(self):
        return bool(self.landed or self.lp or self.progress_hits())

    def progress_hits(self):
        return [c for c, (state, _ref) in self.progress.items() if state in ("landed", "proved")]


# ---- git ---------------------------------------------------------------------------


def _git(root, *args):
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def merge_base(root):
    import wl_planpreflight as PP

    return PP.merge_base(root)


def head_of(root):
    rc, out = _git(root, "rev-parse", "HEAD")
    return out.strip() if rc == 0 else ""


def trailer_links(root, base):
    """{(plan basename, sig): [(landed sha, clauses)]} from the Plan-Box trailers of base..HEAD."""
    rng = "%s..HEAD" % base if base else "HEAD"
    rc, out = _git(root, "log", "--format=%H%x00%B%x1e", rng)
    links: dict[tuple[str, str], list[tuple[str, str]]] = {}
    if rc != 0:
        return links
    for rec in out.split("\x1e"):
        sha, _, msg = rec.strip("\n").partition("\x00")
        if not sha or "plan-box" not in msg.lower():
            continue
        for box in PB.parse_plan_box(msg).boxes:
            links.setdefault((box.plan, box.sig), []).append((sha.strip(), box.clauses))
    return links


def _descends(root, older, newer, memo=None):
    """Whether `newer` descends from `older`. `memo` ({(older, newer): bool}, one per audit) keeps a pair already asked off the next `git` call: the receipts of a box share heads and landed commits (review ec1efb0e.3)."""
    if not newer:
        return False
    if memo is not None and (older, newer) in memo:
        return memo[(older, newer)]
    rc, _ = _git(root, "merge-base", "--is-ancestor", older, newer)
    if memo is not None:
        memo[(older, newer)] = rc == 0
    return rc == 0


def _oldest_first(root, landed):
    """`landed` [(sha, source)] in commit order, oldest first, so the last entry is the newest landed commit."""
    if len(landed) < 2:
        return landed
    rc, out = _git(root, "log", "--no-walk", "--format=%H", *[s for s, _src in landed])
    if rc != 0:
        return landed
    order = {s: i for i, s in enumerate(reversed(out.split()))}
    return sorted(landed, key=lambda x: order.get(x[0], -1))


def _commit_time(root, sha):
    rc, out = _git(root, "show", "-s", "--format=%cI", sha)
    return out.strip() if rc == 0 else ""


# ---- reports -------------------------------------------------------------------------


def _utc_stamp(iso):
    """`iso` (git's `%cI`, with its UTC offset) as the `YYYY-MM-DDTHH:MM:SS` UTC second the report index's `at` is written in (`C.stamp_now`), or its first 19 characters when it does not parse. Review ec1efb0e.5: cutting the offset off compared a local wall time with a UTC one."""
    try:
        stamp = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return str(iso or "")[:19]
    if stamp.tzinfo is None:
        return stamp.strftime("%Y-%m-%dT%H:%M:%S")
    return stamp.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _index_since(rp, store, since):
    """The report index rows from `since` (a `_utc_stamp`) on. The index is append-ordered and grows for good, so the tail is read, four times wider until its oldest row reaches back past `since` or the whole file is in hand (review ec1efb0e.4: the audit read it all with `max_bytes=None`)."""
    try:
        size = rp.index_path(store).stat().st_size
    except OSError:
        return []
    limit = rp.INDEX_READ_MAX_BYTES
    while True:
        if not since:
            # No merge-base: every report counts, so read the whole index (review d7a5dc68.1). The audit result is cached on the index's stamp, so the whole read repeats only when a report lands (review 09a7b151.1).
            return rp.read_index(store, max_bytes=None)
        rows = rp.read_index(store, max_bytes=limit)
        if limit >= size:
            return rows
        if rows and str(rows[0].get("at") or "")[:19] < since:
            return rows
        limit *= 4


def report_rows(root, since_iso=""):
    """[(report id, TickRow)] of every captured report since `since_iso` that names a box."""
    import wl_report as RP

    store = RP.store_root(root)
    out: list[Any] = []
    since = _utc_stamp(since_iso) if since_iso else ""
    for entry in _index_since(RP, store, since):
        if since and str(entry.get("at") or "") < since:
            continue
        rid = str(entry.get("id"))
        boxes = entry.get("boxes")
        # A capped list (`boxes_capped`) lost a box or a commit; the body holds them all.
        if isinstance(boxes, list) and boxes and not entry.get("boxes_capped"):
            out.extend((rid, _row_of(b)) for b in boxes if isinstance(b, dict) and b.get("sig"))
            continue
        try:
            body = (store / str(entry.get("body") or "")).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            # An unreadable body must not drop the row: a capped list is still the boxes the index kept (review c44d4b9a.1).
            if isinstance(boxes, list):
                out.extend((rid, _row_of(b)) for b in boxes if isinstance(b, dict) and b.get("sig"))
            continue
        if "TICK" not in body:
            continue
        out += [(rid, row) for row in PB.parse_tick(body)]
    return out


def _row_of(b):
    """A TickRow from an index row's `boxes` entry (T6's shape)."""
    landed = b.get("landed")
    return PB.TickRow(
        str(b.get("plan") or ""),
        str(b.get("sig") or ""),
        str(b.get("state") or "unknown"),
        tuple(b.get("commits") or ()),
        "all" if landed == "all" else tuple(landed or ()),
        tuple(tuple(x) for x in b.get("owed") or ()),
        None,
        bool(b.get("legacy")),
        0,
    )


# ---- the audit -----------------------------------------------------------------------


def open_plan_boxes(root, only=None):
    """[(rel, sig, body)] of every open box of a live plan under agent/plans/ (records and terminal folders excluded)."""
    import wl_checks as CK
    import wl_planrec as R

    out = []
    for rel, status, _n in CK.plan_records(root):
        if status in R.RECORD_STATES or not rel.startswith("agent/plans/PLAN-"):
            continue
        if only and not PB.same_plan(rel, only):
            continue
        try:
            text = pathlib.Path(root, rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out += [(rel, sig, body) for _i, _line, body, sig in R.open_boxes(text)]
    return out


def _stale(root, row, base, head):
    """Why the latest investigation row is stale, or ""."""
    rhead = str(row.get("head") or "").strip()
    if not rhead:
        return ""
    rc, _ = _git(root, "merge-base", "--is-ancestor", rhead, head)
    if rc != 0:
        rc2, info = _git(root, "show", "-s", "--format=%at%x00%s", rhead)
        if rc2 != 0 or not info.strip():
            return "the row's head %s is unknown to this checkout" % rhead[:12]
        when, _, subject = info.strip().partition("\x00")
        rng = "%s..HEAD" % base if base else "HEAD"
        rc3, log = _git(root, "log", "--format=%at%x00%s", rng)
        if rc3 != 0 or ("%s\x00%s" % (when, subject)) not in log.splitlines():
            return (
                "the row's head %s is unreachable from HEAD with no rebase successor" % rhead[:12]
            )
    if base:
        rc4, _ = _git(root, "merge-base", "--is-ancestor", base, rhead)
        if rc4 != 0:
            return "the row's head %s predates the merge-base %s" % (rhead[:12], base[:12])
    return ""


LIVE_ACCEPT_RE = re.compile(
    r"Accept:[^\n]*\b(?:CI run(?: id)?s?|run ids?|nightly (?:runs?|receipts?|proof|verdicts?|green)|live receipts?|live[- ]proof)\b",
    re.IGNORECASE,
)


def _proof_owed(root, a):
    """Whether a box with no clause map still owes proof: its Accept names a CI run id, a nightly or a live receipt (the one caller reaches here only for a box with no live-proof row, `not a.lp`, and the pattern carries no VERIFIED word of its own), or its newest investigation verdict is `partial` and was taken on code that includes the landing. Without this a partial verdict on landed code read as tickable-now (finding #2a4ebecd, box 575e0098)."""
    if LIVE_ACCEPT_RE.search(a.body):
        return True
    inv = a.inv
    if inv is None or str(inv.get("verdict") or "").strip().lower() != "partial":
        return False
    last = a.landed[-1][0] if a.landed else ""
    return not last or _descends(root, last, str(inv.get("head") or ""))


def _judge(root, a, base, head, me):
    ids = [c["id"] for c in a.cmap] if a.cmap else []
    halves = {c["id"]: c.get("half") for c in a.cmap or []}
    proved = {c for c, (state, _ref) in a.progress.items() if state == "proved"}
    for c, (state, _ref) in a.progress.items():
        if state in ("landed", "proved"):
            a.covered.add(c)
    if a.lp:
        live_ids = [i for i in ids if halves.get(i) in LIVE_HALVES]
        a.covered.update(live_ids or ["live"])
        proved.update(live_ids or ["live"])
    if a.cmap:
        owed = [(i, halves[i]) for i in ids if halves.get(i) in LIVE_HALVES and i not in a.covered]
        done = bool(ids) and set(ids) <= a.covered
        code_landed = any(halves.get(i) == "code" for i in a.covered) or "all" in a.covered
    else:
        owed = []
        if not a.lp and "live" not in proved:
            latest = a.reports[-1][1] if a.reports else None
            if latest is not None:
                owed += [(c, h) for c, h in latest.owed if h in LIVE_HALVES]
            owed += [(c, "live") for c, (state, _r) in a.progress.items() if state == "live-owed"]
            if a.body.startswith("LP-") and not owed:
                owed.append(("*", "live"))
            if not owed and _proof_owed(root, a):
                owed.append(("*", "live"))
        done = "all" in a.covered and not owed
        code_landed = bool(a.landed)
    a.owed = owed
    if not a.linked:
        a.verdict, a.why = "untouched", "nothing links work to this box"
        return a
    last = a.landed[-1][0] if a.landed else ""
    if done and a.investigated:
        a.verdict = "tickable-now"
        if a.lp:
            import wl_liveproof as LP

            evidence = LP.evidence(a.lp[-1])
        else:
            evidence = "commit:%s landed for box %s" % (last[:12], a.sig)
        a.tick = "worklist.py --plan-tick %s %s %s '%s' --write" % (me, a.plan, a.sig, evidence)
        stale = _stale(root, a.inv, base, head) if a.inv else ""
        if stale:
            a.verdict, a.why, a.tick = "stale-investigation", stale, ""
        return a
    if a.inv is not None:
        stale = _stale(root, a.inv, base, head)
        if stale:
            a.verdict, a.why = "stale-investigation", stale
            return a
    if code_landed and owed:
        a.verdict = "live-owed"
        a.why = "owed %s" % ",".join("%s:%s" % (c, h) for c, h in owed)
    else:
        a.verdict = "linked"
        if not a.investigated:
            a.why = "no investigation row"
        else:
            a.why = "open clause(s) %s" % (",".join(i for i in ids if i not in a.covered) or "?")
    if not a.investigated and last:
        a.investigate = (
            "worklist.py --plan-investigate %s %s %s %s commit:%s plan:%s -- post-landing: box %s "
            "has landed work in %s and no investigation row; the box text was read against that diff "
            "--write" % (me, a.plan, a.sig, "partial", last[:12], a.plan, a.sig, last[:12])
        )
    return a


def audit(root, me, plan=None, *, reports=True):
    """[BoxAudit] for every open box (of `plan` when given), linked or not, plus `(head, base)`."""
    import wl_liveproof as LP
    import wl_planrec as R

    root = pathlib.Path(root)
    base = merge_base(root) or ""
    head = head_of(root)
    links = trailer_links(root, base)
    rep = report_rows(root, _commit_time(root, base) if base else "") if reports else []
    lease_shas = sorted({s for _rid, row in rep for s in row.commits})
    landed_of = PB.landed_map(root, lease_shas, rev="HEAD", since=base or None) or {}
    progress = PB.read_progress(root)
    inv_rows = R.read_investigations(root)
    lp_rows = LP.verified_rows(root)
    out = []
    descends_memo: dict[tuple[str, str], bool] = {}
    for rel, sig, body in open_plan_boxes(root, plan):
        base_name = rel.rsplit("/", 1)[-1]
        a = BoxAudit(rel, sig, body)
        for sha, clauses in links.get((base_name, sig), []):
            a.landed.append((sha, "trailer"))
            a.covered.update(["all"] if clauses == "all" else clauses)
        for rid, row in rep:
            if row.sig != sig or not PB.same_plan(row.plan, base_name):
                continue
            mapped = [landed_of[c.lower()] for c in row.commits if landed_of.get(c.lower())]
            if not mapped:
                continue
            a.reports.append((rid, row))
            for sha in mapped:
                if sha not in [s for s, _src in a.landed]:
                    a.landed.append((sha, "report:%s" % rid))
            if row.landed == "all" or (row.legacy and row.state in ("done", "present")):
                a.covered.add("all")
            elif row.landed:
                a.covered.update(row.landed)
        a.landed = _oldest_first(root, a.landed)
        a.cmap = PB.clause_map(root, rel, sig, progress)
        a.progress = PB.box_state(root, rel, sig, progress)
        a.inv = R.investigation_for(root, rel, sig, inv_rows)
        # A receipt proves the live half of the code that landed only when it was taken on that code: a VERIFIED row whose head does not descend from every landed commit of the box is an older receipt (7692f2db had 19 of them, all before its landed code).
        a.lp = [
            r
            for r in lp_rows
            if r.get("box") == sig
            and PB.same_plan(r.get("plan"), rel)
            and all(
                _descends(root, s, str(r.get("head") or ""), descends_memo) for s, _src in a.landed
            )
        ]
        out.append(_judge(root, a, base, head, me))
    return out, head, base


# ---- the blocking check `plan-box-owed` (T10) ----------------------------------------------

OWED_STOPS = 3


def uninvestigated(rows):
    """[(key, line, investigate command)] of every open box with a LANDED commit (by trailer or by report TICK) and no investigation row."""
    return [
        ("%s#%s" % (a.plan.rsplit("/", 1)[-1], a.sig), line_of(a), a.investigate)
        for a in rows
        if a.landed and a.inv is None
    ]


def stop_check(memo, current, threshold=OWED_STOPS):
    """`(new memo, blocking rows)`. `memo` is {key: consecutive stops seen}; `current` is `uninvestigated`'s rows for this stop. A key blocks once it has held for `threshold` stops in a row, three being the work window the effort tuner uses; a key absent this stop (its row was written, or the box closed) is dropped and starts over."""
    memo = memo if isinstance(memo, dict) else {}
    new = {}
    blocking = []
    for key, line, cmd in current:
        n = int(memo.get(key) or 0) + 1
        new[key] = n
        if n >= threshold:
            blocking.append((key, line, cmd))
    return new, blocking


def inputs_stamp(root):
    """The cache stamp of everything `audit` reads beside HEAD: `[name, size, mtime_ns]` of the progress, investigation and live-proof ledgers, the report index, and every live plan file under agent/plans/.

    Review 82fd346d.1 and ec1efb0e.2: the stamp held only the progress and investigation ledger sizes, so a box closed by editing its plan, a VERIFIED live-proof row, or a newly captured report at the same HEAD kept answering the old verdict until the next commit. A missing file stamps as -1.
    """
    root = pathlib.Path(root)
    paths = [PB.progress_path(root), root / "agent" / "ledgers" / "plan-investigation.jsonl"]
    # The live-proof and report imports sit inside the suppress: a failing one leaves its file out of the stamp, and the cached verdict is read as it always was, instead of the check raising (review 1a8431fd.2).
    # A failing live-proof import still stamps the ledger by its known path, so a cached verdict misses when that ledger changes (review d7a5dc68.3).
    ledger_rel = "agent/ledgers/live-proof.jsonl"
    with contextlib.suppress(Exception):
        import wl_liveproof as LP

        ledger_rel = LP.LEDGER_REL
    paths.append(root / ledger_rel)
    with contextlib.suppress(Exception):
        import wl_report as RP

        paths.append(RP.index_path(RP.store_root(root)))
    paths += sorted((root / "agent" / "plans").glob("PLAN-*.md"))
    stamp = []
    for path in paths:
        try:
            st = path.stat()
            stamp.append([str(path), st.st_size, st.st_mtime_ns])
        except OSError:
            stamp.append([str(path), -1, -1])
    return stamp


def uninvestigated_cached(root, me):
    """`uninvestigated` over the whole audit, cached per HEAD and per `inputs_stamp` (the cache `owned_owed_cached` keeps, under its own key)."""
    root = pathlib.Path(root)
    head = head_of(root)
    stamp = inputs_stamp(root)
    cache = cache_path(root, "owed-%s" % (head or "nohead"))
    try:
        doc = json.loads(cache.read_text(encoding="utf-8"))
        if doc.get("stamp") == stamp and doc.get("me") == me[:8]:
            return [tuple(x) for x in doc.get("rows") or []]
    except (OSError, ValueError, AttributeError):
        pass
    rows, _head, _base = audit(root, me[:8])
    found = uninvestigated(rows)
    with contextlib.suppress(OSError):
        cache.write_text(
            json.dumps({"stamp": stamp, "me": me[:8], "rows": found}), encoding="utf-8"
        )
    return found


# ---- the live-owed state on release (T11) -----------------------------------------------

_SIG_TOKEN_RE = re.compile(r"(?<![0-9a-z])([0-9a-f]{8})(?![0-9a-z])")


def release_live_owed(root, text, me, item_id):
    """Append one `live-owed` progress row per unproved live or operator clause of each box `text` names, when the audit links landed code to that box (Design 7). Returns the rows appended; [] (and nothing written) when the item names no box, nothing landed, or nothing is owed."""
    named = set(_SIG_TOKEN_RE.findall(text or ""))
    if not named:
        return []
    boxes = [(rel, sig) for rel, sig, _b in open_plan_boxes(root) if sig in named]
    written = []
    for rel in sorted({rel for rel, _sig in boxes}):
        rows, _head, _base = audit(root, me, rel)
        for a in rows:
            if a.sig not in named or not a.landed or not a.owed:
                continue
            clauses = [c for c, _h in a.owed] if a.cmap else ["all"]
            for clause in dict.fromkeys(clauses):
                row = {
                    "kind": "progress",
                    "by": me,
                    "plan": a.plan,
                    "sig": a.sig,
                    "clause": clause,
                    "state": "live-owed",
                    "ref": "released #%s" % item_id,
                }
                stored, fresh = PB.append_progress(root, row)
                if fresh:
                    written.append(stored)
    return written


# ---- rendering -----------------------------------------------------------------------


def line_of(a):
    shas = ",".join(s[:12] for s, _src in a.landed[:SHOWN_LANDED])
    if len(a.landed) > SHOWN_LANDED:
        shas += ",+%d" % (len(a.landed) - SHOWN_LANDED)
    inv = (
        "inv=%s@%s" % (a.inv.get("verdict"), str(a.inv.get("head") or "")[:12])
        if a.inv
        else "inv=none"
    )
    return "%-19s %s#%s landed=%s %s %s -- %s" % (
        a.verdict,
        a.plan.rsplit("/", 1)[-1],
        a.sig,
        shas or "-",
        inv,
        "map=%d" % len(a.cmap) if a.cmap else "map=none",
        a.why or a.body[:60],
    )


def closed_links(root, base, shas):
    """{given sha: [(plan rel or basename, sig, source)]}: the Plan-Box trailers and investigation rows that link each sha to any box, open or closed.

    `audit` judges open boxes only, so a sha whose box is already ticked finds no row there; without this a commit linked to a closed box read as `untouched`, which its own message calls "no trailer, report or ledger row links it" (T9 review ef3c5efa.2, ec099603d and H2).
    """
    import wl_planrec as R

    shas = [g for g in shas if g]  # an empty token would prefix-match every sha (review 014e4b51.3)
    found: dict[str, list[tuple[str, str, str]]] = {g: [] for g in shas}
    for (plan, sig), landed in trailer_links(root, base).items():
        for sha, _clauses in landed:
            for given in shas:
                if sha.lower().startswith(given.lower()):
                    found[given].append((plan, sig, "trailer %s" % sha[:12]))
    for row in R.read_investigations(root):
        # An `absent` row asserts the cited work is NOT in the tree, so it is no evidence that a commit belongs to its box (review 014e4b51.1).
        if str(row.get("verdict") or "").strip().lower() == "absent":
            continue
        cited = [str(t) for k, t in row.get("pointers") or [] if k == "commit"]
        cited += [str(r[2]) for r in row.get("resolved") or [] if len(r) > 2 and r[0] == "commit"]
        for given in shas:
            if any(c.lower().startswith(given.lower()) for c in cited):
                entry = (
                    str(row.get("plan")),
                    str(row.get("sig")),
                    "investigation row %s" % row.get("at", "?"),
                )
                if entry not in found[given]:
                    found[given].append(entry)
    return found


def render(
    rows, head, base, *, shas=None, closed=None, mixed=False, live_owed=False, verbose=False
):
    """`(text, exit code)` of `--box-audit`."""
    out = ["BOX AUDIT @ %s since %s" % (head[:12] or "?", base[:12] or "(no merge-base)")]
    if shas:
        for given in shas:
            hits = [a for a in rows if any(s.startswith(given.lower()) for s, _src in a.landed)]
            if not hits and (closed or {}).get(given):
                for plan, sig, source in closed[given]:
                    out.append(
                        "%s -> closed box %s#%s (%s; no open box left to judge)"
                        % (given, plan, sig, source)
                    )
                continue
            if not hits:
                out.append("%s untouched: no trailer, report or ledger row links it" % given)
            for a in hits:
                out.append("%s -> %s" % (given, line_of(a)))
                out += ["  " + x for x in (a.tick, a.investigate) if x]
        return "\n".join(out) + "\n", 0
    if mixed:
        listed = [a for a in rows if a.landed and not a.cmap]
        out.append("%d open box(es) with landed work and no clause map:" % len(listed))
        for a in listed:
            out.append("  " + line_of(a))
            out.append(
                '    worklist.py --box-clauses <me> %s %s "C1 [code] <text>" "C2 [live] <text>" --write'
                % (a.plan, a.sig)
            )
        return "\n".join(out) + "\n", 1 if listed else 0
    shown = [
        a
        for a in rows
        if (a.verdict == "live-owed" if live_owed else (verbose or a.verdict != "untouched"))
    ]
    counts = {v: sum(1 for a in rows if a.verdict == v) for v in VERDICTS}
    out.append(
        "%d open box(es): %s"
        % (len(rows), ", ".join("%s %d" % (v, n) for v, n in counts.items() if n))
    )
    for a in shown:
        out.append("  " + line_of(a))
        out += ["    " + x for x in (a.tick, a.investigate) if x]
    return "\n".join(out) + "\n", 0


def owed_ticks(rows, owned):
    """The boxes the STATE.md "Owed ticks" section must name: tickable-now and live-owed boxes of plans in `owned`."""
    return [a for a in rows if a.verdict in OWED_VERDICTS and a.plan in owned]


# ---- the per-HEAD cache (T12) ----------------------------------------------------------


def cache_path(root, head):
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]", "_", str(root))[-40:]
    return pathlib.Path(base, CACHE_NAME % ("%s-%s" % (key, head[:12])))


def owned_owed_cached(root, me):
    """[(plan, sig, verdict)] of the owed boxes of plans `me` owns, cached per HEAD and per `inputs_stamp`, so a STATE.md write pays the audit once per change of what it reads."""
    import wl_checks as CK

    root = pathlib.Path(root)
    head = head_of(root)
    stamp = inputs_stamp(root)
    cache = cache_path(root, head or "nohead")
    try:
        doc = json.loads(cache.read_text(encoding="utf-8"))
        if doc.get("stamp") == stamp and doc.get("me") == me[:8]:
            return [tuple(x) for x in doc.get("rows") or []]
    except (OSError, ValueError, AttributeError):
        pass
    rows, _head, _base = audit(root, me[:8])
    owned = {a.plan for a in rows if (CK.plan_owner(root, a.plan) or "")[:8] == me[:8]}
    found = [(a.plan, a.sig, a.verdict) for a in owed_ticks(rows, owned)]
    with contextlib.suppress(OSError):
        cache.write_text(
            json.dumps({"stamp": stamp, "me": me[:8], "rows": found}), encoding="utf-8"
        )
    return found


def main(argv, me, root):
    """`--box-audit <me> [plan] [--sha <list>] [--live-owed] [--mixed-unsplit] [--all]`; returns the exit code."""
    rest = list(argv)
    shas = None
    if "--sha" in rest:
        k = rest.index("--sha")
        if k + 1 >= len(rest):
            raise ValueError("--sha takes a comma list of landed shas")
        shas = [s for s in rest[k + 1].split(",") if s]
        rest = rest[:k] + rest[k + 2 :]
    flags = {f for f in rest if f.startswith("--")}
    unknown = flags - {"--live-owed", "--mixed-unsplit", "--all"}
    if unknown:
        raise ValueError("unknown flag(s) %s" % ", ".join(sorted(unknown)))
    plans = [a for a in rest if not a.startswith("--")]
    if len(plans) > 1:
        raise ValueError("name at most one plan")
    rows, head, base = audit(root, me[:8], plans[0] if plans else None)
    text, rc = render(
        rows,
        head,
        base,
        shas=shas,
        closed=closed_links(root, base, shas) if shas else None,
        mixed="--mixed-unsplit" in flags,
        live_owed="--live-owed" in flags,
        verbose="--all" in flags,
    )
    print(text, end="")
    return rc
