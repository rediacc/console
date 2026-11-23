"""wl_writersnow: the /writers-now round record and the self-review seeds a repeat round hands its survey (agent/plans/PLAN-writers-now-cadence.md WN1, WN3, operator ruling #ac2de21f).

THE ROUND RECORD (WN1). `worklist.py --writers-now-start <me> <survey>` appends one JSON line to `agent/ledgers/writers-now-rounds.jsonl` at the start of every round: the round id, the session, the UTC start, the survey path, the seeds path and the seed count. Nothing else writes the ledger, and nothing rewrites a line.

THE SEEDS (WN3). A repeat round re-surveys the same plan text, so work that surfaced only in this session's own records stays invisible to it. `collect_seeds` lists, since the previous round of this session (or LOOKBACK_H hours without one): the open items this session added or updated (not the ones a worker holds), the `BLOCKED_BY:` items whose every blocker is now closed (at any age), the per-commit review findings still open that were reviewed in the window, and the "owed", "outside Owns" and "for the lead" lines of the sub-agent reports `wl_report` captured for this session in the window. `--writers-now-start` writes them to `<survey stem>-seeds.md`, and the skill hands that file to the survey agent, which classifies every seed.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import secrets

import wl_core as C

LEDGER_REL = "agent/ledgers/writers-now-rounds.jsonl"
# How far back the seeds reach when this session has no earlier round.
LOOKBACK_H = 12
# Bounds on the seeds file, so one chatty report cannot bury the rest, and one source cannot bury the other two: past KIND_MAX a source gives one `more` seed naming how many it held back and where they are read.
REPORT_LINES_MAX = 8
KIND_MAX = 40
# Where the held-back seeds of each source are read in full.
MORE_WHERE = {
    "report": "worklist.py --reports --list --all",
    "item": "worklist.py --list --open <me>",
    "unblocked": "worklist.py --list --open <me>",
    "review": "worklist.py --review-mark <me>",
}
SEED_TEXT_MAX = 240

# The report lines a seed is made from: an owed half (a TICK line's `owed=` that is not `-` counts, `owed=-` does not), an edit outside the writer's Owns, and anything addressed to the lead.
REPORT_SEED_RE = re.compile(
    r"\bowed\b(?!=-)|\boutside\s+(?:\w+\s+)?owns\b|\bfor\s+the\s+lead\b", re.IGNORECASE
)
OPEN_FINDING = "open"
# An item a worker holds (`[>]`) is in flight, not missed work; `[ ]` and `[?]` are the open states a seed comes from.
SEED_ITEM_STATES = (" ", "?")


# ---- the round ledger -------------------------------------------------------------


def ledger_path(root) -> pathlib.Path:
    return pathlib.Path(root) / LEDGER_REL


def read_rounds(root) -> list[dict]:
    """Every parseable round row, oldest first. An absent ledger is no round yet ([]); an unparseable line is skipped, as every event-log reader here does; any other read failure raises."""
    path = ledger_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("session") and C.parse_stamp(row.get("at")):
            rows.append(row)
    return rows


def last_round(rows, session) -> dict | None:
    """The newest row of `session` (prefix-matched either way, wl_core.same_session), or None."""
    mine = [r for r in rows if C.same_session(str(r.get("session")), str(session))]
    return max(mine, key=lambda r: C.parse_stamp(r["at"])) if mine else None


def seeds_path_for(survey) -> pathlib.Path:
    """`<survey stem>-seeds.md` beside the survey: `/tmp/writers-now/<branch>-<stamp>.md` gives `/tmp/writers-now/<branch>-<stamp>-seeds.md`."""
    p = pathlib.Path(survey)
    return p.with_name(p.stem + "-seeds.md")


def new_round_id() -> str:
    return secrets.token_hex(4)


def append_round(root, session, survey, now, round_id=None, **extra) -> dict:
    """Append one round row and return it. One `os.write` of one line onto an O_APPEND handle, so two sessions starting rounds at once each keep their own line."""
    row = {
        "round": round_id or new_round_id(),
        "session": str(session),
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "survey": str(survey),
        **extra,
    }
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return row


# ---- the seeds (WN3) --------------------------------------------------------------


def window_start(rows, session, now) -> datetime.datetime:
    """Where the seeds reach back to: the previous round of this session, else LOOKBACK_H hours before `now`."""
    last = last_round(rows, session)
    if last is not None:
        return C.parse_stamp(last["at"])
    return now - datetime.timedelta(hours=LOOKBACK_H)


def _at(stamp):
    """A datetime from an ISO8601Z stamp, with or without seconds or a fraction; None when unreadable."""
    s = str(stamp or "")
    got = C.parse_stamp(s)
    if got is None and len(s) >= 19:
        got = C.parse_stamp(s[:19] + "Z")
    return got


def _clip(text) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= SEED_TEXT_MAX else one[: SEED_TEXT_MAX - 3] + "..."


def item_seeds(items, session, since) -> list[dict]:
    """Seeds from this session's worklist items: an open item whose every BLOCKED_BY blocker is closed (at any age, kind `unblocked`), then an open item added or updated at or after `since` (kind `item`). One seed per item. The token grammar and the blocker lookup are wl_leasehelp's."""
    import wl_leasehelp as LH

    by_id = {str(r.get("id")): r for r in items}
    out = []
    seen = set()
    mine = [
        r
        for r in items
        if r.get("state") in SEED_ITEM_STATES and C.owned_by_me(r.get("owner"), session)
    ]
    for r in mine:
        refs = LH.blocked_by(r.get("text"))
        if not refs:
            continue
        resolved = [LH.resolve(ref, by_id) for ref in refs]
        if all(rid is not None and by_id[rid].get("state") in LH.CLOSED_STATES for rid in resolved):
            out.append(
                {
                    "kind": "unblocked",
                    "ref": "#%s" % r["id"],
                    "text": "blocker %s closed: %s"
                    % (", ".join("#%s" % x for x in resolved), _clip(r.get("text"))),
                }
            )
            seen.add(r["id"])
    for r in mine:
        if r["id"] in seen:
            continue
        stamps = [s for s in (_at(r.get("first")), _at(r.get("upd"))) if s is not None]
        if stamps and max(stamps) >= since:
            out.append({"kind": "item", "ref": "#%s" % r["id"], "text": _clip(r.get("text"))})
    return out


def review_seeds(records, since) -> list[dict]:
    """Seeds from per-commit review records (`wl_review.dir_records` pairs): every finding still `open` on a review written at or after `since`."""
    out = []
    for _path, review in records:
        at = _at(getattr(review, "reviewed_at", ""))
        if at is None or at < since:
            continue
        for f in getattr(review, "findings", None) or ():
            if getattr(f, "resolution", OPEN_FINDING) != OPEN_FINDING:
                continue
            out.append(
                {
                    "kind": "review",
                    "ref": "%s %s" % (str(review.sha)[:8], f.id),
                    "text": _clip("%s %s:%s %s" % (f.severity, f.file, f.line, f.claim)),
                }
            )
    return out


def report_seeds(reports, session, since) -> list[dict]:
    """Seeds from captured sub-agent reports: `reports` is [(index entry, body text)]. A report of `session` captured at or after `since` gives each of its lines that REPORT_SEED_RE matches, at most REPORT_LINES_MAX per report."""
    out = []
    for entry, body in reports:
        if not C.same_session(str(entry.get("session") or ""), str(session)):
            continue
        at = _at(entry.get("at"))
        if at is None or at < since:
            continue
        if body is None:
            out.append(
                {
                    "kind": "report",
                    "ref": "%s (%s)" % (entry.get("agent") or "agent", entry.get("id")),
                    "text": _clip(
                        "body unreadable (%s); read it with worklist.py --reports --show %s"
                        % (entry.get("read_error") or "no body", entry.get("id"))
                    ),
                }
            )
            continue
        n = 0
        for line in str(body).splitlines():
            if n >= REPORT_LINES_MAX:
                break
            if REPORT_SEED_RE.search(line):
                out.append(
                    {
                        "kind": "report",
                        "ref": "%s (%s)" % (entry.get("agent") or "agent", entry.get("id")),
                        "text": _clip(line),
                    }
                )
                n += 1
    return out


def collect_seeds(items, review_records, reports, session, since) -> list[dict]:
    """Every seed, reports first (the source the survey cannot otherwise see), then items, then review findings. Each source gives at most KIND_MAX seeds, then one `more` seed counting the rest and naming where they are read (MORE_WHERE)."""
    out: list[dict] = []
    for group in (
        report_seeds(reports, session, since),
        item_seeds(items, session, since),
        review_seeds(review_records, since),
    ):
        out.extend(group[:KIND_MAX])
        if len(group) > KIND_MAX:
            kind = group[KIND_MAX]["kind"]
            out.append(
                {
                    "kind": "more",
                    "ref": kind,
                    "text": "%d more %s seed(s) past the cap of %d; read them with %s"
                    % (len(group) - KIND_MAX, kind, KIND_MAX, MORE_WHERE[kind]),
                }
            )
    return out


SEEDS_HEAD = (
    "# writers-now seeds: round %(round)s, session %(me)s, since %(since)s\n\n"
    "What this session's own records surfaced since its previous round, which the plan text "
    "alone does not show. The survey classifies EVERY seed below as CODE, LIVE (with its "
    "target), PRESENT or closed, in a `## Seeds` table beside the plan boxes "
    "(`seed | class | plan box or new item | evidence`), and a seed that is real work no "
    "box covers becomes a worklist item.\n\n"
)


def render_seeds(seeds, round_id, session, since) -> str:
    head = SEEDS_HEAD % {
        "round": round_id,
        "me": str(session)[:8],
        "since": since.strftime("%Y-%m-%dT%H:%MZ"),
    }
    if not seeds:
        return head + "(no seed: nothing in the records since the previous round)\n"
    lines = [
        "- [S%d] %s %s: %s\n" % (i, s["kind"], s["ref"], s["text"]) for i, s in enumerate(seeds, 1)
    ]
    return head + "".join(lines)


def gather_reports(start, session, since) -> list[tuple[dict, str]]:
    """[(index entry, body)] of this session's reports captured since `since`, read from the wl_report store. A body that cannot be read comes back as None with the error on the entry (`read_error`), never as an empty report."""
    import wl_report

    store = wl_report.store_root(start)
    out = []
    for entry in wl_report.read_index(store):
        if not C.same_session(str(entry.get("session") or ""), str(session)):
            continue
        at = _at(entry.get("at"))
        if at is None or at < since or not entry.get("body"):
            continue
        try:
            out.append((entry, (store / str(entry["body"])).read_text(encoding="utf-8")))
        except OSError as exc:
            # Named as its own seed by report_seeds, so a pruned or unreadable body is seen, never read as a report with nothing in it.
            out.append(({**entry, "read_error": "%s: %s" % (type(exc).__name__, exc)}, None))
    return out


def gather_reviews(root):
    """The review records of the current branch (`wl_review.dir_records`); [] on a detached HEAD, where no branch directory exists."""
    import wl_review

    branch = C.git_branch(root)
    if not branch:
        return []
    records, _malformed = wl_review.dir_records(wl_review.branch_dir(root, branch))
    return records


def start_round(
    root, session, survey, now, items, review_records, reports_since
) -> tuple[dict, str]:
    """WN1 + WN3: build the seeds since this session's previous round, write the seeds file beside the survey, append the round row. `reports_since(since)` returns the [(index entry, body)] pairs (gather_reports in the verb). Returns (row, seeds text)."""
    rows = read_rounds(root)
    since = window_start(rows, session, now)
    seeds = collect_seeds(items, review_records, reports_since(since), session, since)
    path = seeds_path_for(survey)
    round_id = new_round_id()
    text = render_seeds(seeds, round_id, session, since)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    row = append_round(root, session, survey, now, round_id, seeds=str(path), seed_count=len(seeds))
    return row, text
