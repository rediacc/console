"""wl_writersnow: the /writers-now round record, its hourly cadence check and the self-review seeds a repeat round hands its survey (agent/plans/PLAN-writers-now-cadence.md WN1-WN3, operator ruling #ac2de21f).

THE ROUND RECORD (WN1). `worklist.py --writers-now-start <me> <survey>` appends one JSON line to `agent/ledgers/writers-now-rounds.jsonl` at the start of every round: the round id, the session, the UTC start, the survey path, the seeds path and the seed count. Nothing else writes the ledger, and nothing rewrites a line.

THE CADENCE (WN2). `writers-now-due` (effort.json: blocks at `high`, advises at `smart`) fires when this session has no COUNTING round younger than WINDOW_MIN minutes while the Promoted queue holds an open box. A row alone is not a round (operator report 2026-11-24: five hourly rows each copied the first round's survey with `cp` and ran none): a round counts once its survey file exists, was last written after the round's start, and differs from the previous round's survey, and a round whose survey is still missing counts as in progress for SURVEY_GRACE_MIN minutes, then stops counting (`judge_round`). `--writers-now-start` refuses a survey path that already holds the previous round's survey bytes, so the copy fails at the source. It stands down in the landing tree, whose babysit and merge phases work the one open PR and read no queue, in the merge phase of the development tree (the loop state `merged`, where the hook names the next branch first), and inside the window.

THE SEEDS (WN3). A repeat round re-surveys the same plan text, so work that surfaced only in this session's own records stays invisible to it. `collect_seeds` lists, since the previous round of this session (or LOOKBACK_H hours without one): the open items this session added or updated (not the ones a worker holds), the `BLOCKED_BY:` items whose every blocker is now closed (at any age), the per-commit review findings still open that were reviewed in the window, and the "owed", "outside Owns" and "for the lead" lines of the sub-agent reports `wl_report` captured for this session in the window. `--writers-now-start` writes them to `<survey stem>-seeds.md`, and the skill hands that file to the survey agent, which classifies every seed.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets

import wl_core as C

LEDGER_REL = "agent/ledgers/writers-now-rounds.jsonl"
# The cadence: a round at least this often while Promoted boxes are open (operator ruling #ac2de21f: at least once per hour).
WINDOW_MIN = 60
# How long a round whose survey file does not exist yet still counts: the survey agent is running.
SURVEY_GRACE_MIN = 50
# Why a round does not count toward the cadence (judge_round), shown in the writers-now-due message.
WHY_COPIED_OLD = "its survey was written before the round started (a copied survey is not a round)"
WHY_COPIED_SAME = (
    "its survey has the same content as the previous round's (a copied survey is not a round)"
)
WHY_NEVER_WRITTEN = "survey never written within %d min of the start" % SURVEY_GRACE_MIN
WHY_TOO_OLD = "older than %d min" % WINDOW_MIN
COPIED_SURVEY_REFUSED = (
    "--writers-now-start: a copied survey is not a round. %(survey)s already holds the same bytes "
    "as the previous round's survey %(prev)s (sha256 %(digest)s). The writers-now-due check counts "
    "a round only once its survey agent writes a fresh survey after the start; name a new survey "
    "path and run the survey.\n"
)


class CopiedSurveyError(ValueError):
    """`--writers-now-start` was handed a survey path that already holds the previous round's survey."""


# The loop states the cadence stands down in (wl_prscope.LANDING and wl_prscope.MERGED, restated so this module imports no loop resolver).
LANDING_ROLE = "landing"
MERGED_KIND = "merged"
# How far back the seeds reach when this session has no earlier round.
LOOKBACK_H = 12
# Bounds on the seeds file, so one chatty report cannot bury the rest, and one source cannot bury the other two: past KIND_MAX a source gives one `more` seed naming how many it held back and where they are read.
REPORT_LINES_MAX = 8
KIND_MAX = 40
# Where the held-back seeds of each source are read in full.
MORE_WHERE = {
    "armed": "worklist.py --armed-list <me>",
    "report": "worklist.py --reports --list --all",
    "item": "worklist.py --list --open <me>",
    "unblocked": "worklist.py --list --open <me>",
    "review": "worklist.py --review-mark <me>",
}
SEED_TEXT_MAX = 240

# The report lines a seed is made from: an owed half (a TICK line's `owed=` that is not `-` counts, `owed=-` does not), an edit outside the writer's Owns, and anything addressed to the lead.
REPORT_SEED_RE = re.compile(
    r"\bowed=(?!-)|\boutside\s+(?:\w+\s+)?owns\b|\bfor\s+the\s+lead\b", re.IGNORECASE
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
    """The newest row of `session`, or None. A row counts when its session prefix-matches either way (wl_core.same_session) or names a proven pre-compaction id of this session (wl_core.owned_by_me), so a compaction does not make the hour's round vanish."""
    mine = [
        r
        for r in rows
        if C.same_session(str(r["session"]), str(session))
        or C.owned_by_me(str(r["session"]), str(session))
    ]
    return max(mine, key=lambda r: C.parse_stamp(r["at"])) if mine else None


def seeds_path_for(survey) -> pathlib.Path:
    """`<survey stem>-seeds.md` beside the survey: `/tmp/writers-now/<branch>-<stamp>.md` gives `/tmp/writers-now/<branch>-<stamp>-seeds.md`."""
    p = pathlib.Path(survey)
    return p.with_name(p.stem + "-seeds.md")


def survey_file(root, survey) -> pathlib.Path:
    """The survey path of a round row, a relative one read against the project root."""
    p = pathlib.Path(str(survey))
    return p if p.is_absolute() else pathlib.Path(root) / p


def survey_digest(path) -> str | None:
    """The sha256 of a survey file's bytes, or None when it does not exist. Any other read failure raises."""
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _mine(rows, session) -> list[dict]:
    """The rows of `session` (prefix match either way, or a proven pre-compaction id), oldest first."""
    return sorted(
        (
            r
            for r in rows
            if C.same_session(str(r["session"]), str(session))
            or C.owned_by_me(str(r["session"]), str(session))
        ),
        key=lambda r: C.parse_stamp(r["at"]),
    )


def _started(row) -> float:
    """The round's start as an epoch float: the exact `started` the verb records, else the second-resolution `at`."""
    got = row.get("started")
    if isinstance(got, (int, float)):
        return float(got)
    return C.parse_stamp(row["at"]).timestamp()


def _prev_digest(root, row, prev) -> str | None:
    """The previous round's survey digest: the one recorded at this round's start, else the previous survey file read now (rows written before the digest was recorded)."""
    got = row.get("prev_survey_digest")
    if got:
        return str(got)
    if prev is None:
        return None
    return survey_digest(survey_file(root, prev["survey"]))


def judge_round(root, row, prev, now) -> str:
    """Why `row` does not count toward the cadence, or "" when it counts. `prev` is this session's round before it (or None). A missing survey counts for SURVEY_GRACE_MIN minutes after the start, then stops; a survey last written at or before the start is a copy; a survey with the previous round's bytes is a copy."""
    path = survey_file(root, row["survey"])
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        age = (now - C.parse_stamp(row["at"])).total_seconds() / 60.0
        return "" if age < SURVEY_GRACE_MIN else WHY_NEVER_WRITTEN
    if mtime <= _started(row):
        return WHY_COPIED_OLD
    prev_digest = _prev_digest(root, row, prev)
    if prev_digest and survey_digest(path) == prev_digest:
        return WHY_COPIED_SAME
    return ""


def new_round_id() -> str:
    return secrets.token_hex(4)


def append_round(root, session, survey, now, round_id=None, **extra) -> dict:
    """Append one round row and return it. One `os.write` of one line onto an O_APPEND handle (continued only after a short write), so two sessions starting rounds at once each keep their own line."""
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
        # A short write (a disk filling mid-line) would leave the line unterminated and join the next append onto it, so the rest is written until the whole line is down.
        pending = (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
        while pending:
            pending = pending[os.write(fd, pending) :]
    finally:
        os.close(fd)
    return row


# ---- the cadence check (WN2) ------------------------------------------------------


def stand_down(loop) -> str:
    """Why the cadence is silent for this loop state (a wl_prscope.LoopState or None), or "": the landing tree, or the merge phase."""
    if loop is None:
        return ""
    if getattr(loop, "role", "") == LANDING_ROLE:
        return "the landing tree"
    if getattr(loop, "kind", "") == MERGED_KIND:
        return "the merge phase"
    return ""


def due(rows, session, now, open_boxes, loop=None, root=None) -> tuple[bool, dict]:
    """(fires, facts) for `writers-now-due`: fires when `open_boxes` (the Promoted queue's open boxes) is above zero, no stand-down applies, and this session has no round younger than WINDOW_MIN minutes that counts (judge_round; survey paths read against `root`, default the project root). `facts` carries the newest round, its age in minutes (None without one), why it does not count (`not_counted`), the open count and the stand-down reason."""
    if root is None:
        root = C.project_root(C.project_start()) or os.getcwd()
    root = pathlib.Path(root)
    mine = _mine(rows, session)
    last = mine[-1] if mine else None
    age = None if last is None else (now - C.parse_stamp(last["at"])).total_seconds() / 60.0
    facts = {
        "last": last,
        "age": age,
        "open": int(open_boxes),
        "why": stand_down(loop),
        "not_counted": "",
    }
    if facts["why"] or open_boxes <= 0:
        return False, facts
    if last is None:
        return True, facts
    # Newest first, only the rounds inside the window: the first that counts clears the check.
    for i in range(len(mine) - 1, -1, -1):
        row = mine[i]
        if (now - C.parse_stamp(row["at"])).total_seconds() / 60.0 >= WINDOW_MIN:
            break
        why = judge_round(root, row, mine[i - 1] if i else None, now)
        if not why:
            return False, facts
        if row is last:
            facts["not_counted"] = why
    if not facts["not_counted"]:
        facts["not_counted"] = WHY_TOO_OLD
    return True, facts


def promoted_open(root) -> int:
    """The open boxes of the Promoted entries of agent/plans/QUEUE.md, each plan counted once (wl_planqueue.promoted_progress). A plan whose counts cannot be read adds nothing; a QUEUE.md that cannot be read raises."""
    import wl_planqueue as PQ

    text = (pathlib.Path(root) / PQ.QUEUE_REL).read_text(encoding="utf-8")
    seen: dict[str, int] = {}
    for row in PQ.promoted_progress(root, text):
        if not row.why:
            seen.setdefault(row.rel, row.opened)
    return sum(seen.values())


def due_fields(facts, me8) -> dict:
    """The fields of worklist_messages.V_WRITERS_NOW_DUE for a firing `due`."""
    last = facts["last"]
    if last is None:
        shown = "none this session"
    else:
        shown = "round %s at %s, %d min ago, not counted: %s" % (
            last.get("round"),
            last["at"],
            int(facts["age"]),
            facts.get("not_counted") or WHY_TOO_OLD,
        )
    return {"last": shown, "open": facts["open"], "window": WINDOW_MIN, "who": me8}


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


def armed_seeds(items, session, since) -> list[dict]:
    """Seeds from this session's armed actions that are due (latched, not started) and whose `fired_at` is later than `since`: the hold's event happened, so the prepared action is the first work of the round (kind `armed`). An arm fired at or before `since` was already offered to the previous round."""
    import wl_armed as A

    out = []
    for r in items:
        if not C.owned_by_me(r.get("owner"), session):
            continue
        arm = r.get("arm")
        if not isinstance(arm, dict) or not A.due(arm):
            continue
        fired = _at(arm.get("fired_at"))
        if fired is None or fired <= since:
            continue
        out.append(
            {
                "kind": "armed",
                "ref": "#%s" % r["id"],
                "text": _clip(
                    "%s on %s: %s"
                    % (arm.get("verdict"), " ".join(arm.get("when") or ()), r.get("text"))
                ),
            }
        )
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
    """Every seed, armed actions first (their event already happened), then reports (the source the survey cannot otherwise see), then items, then review findings. Each source gives at most KIND_MAX seeds, then one `more` seed counting the rest and naming where they are read (MORE_WHERE)."""
    out: list[dict] = []
    for group in (
        armed_seeds(items, session, since),
        report_seeds(reports, session, since),
        item_seeds(items, session, since),
        review_seeds(review_records, since),
    ):
        out.extend(group[:KIND_MAX])
        # item_seeds mixes `unblocked` and `item` kinds in one group, so the overflow is counted per kind.
        held: dict[str, int] = {}
        for seed in group[KIND_MAX:]:
            held[seed["kind"]] = held.get(seed["kind"], 0) + 1
        for kind, count in held.items():
            out.append(
                {
                    "kind": "more",
                    "ref": kind,
                    "text": "%d more %s seed(s) past the cap of %d; read them with %s"
                    % (count, kind, KIND_MAX, MORE_WHERE[kind]),
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
    mine = _mine(rows, session)
    prev = mine[-1] if mine else None
    prev_digest = None if prev is None else survey_digest(survey_file(root, prev["survey"]))
    # A survey path that already holds a previous round's bytes is a copy: refused before anything is written.
    known = {str(r["prev_survey_digest"]) for r in mine if r.get("prev_survey_digest")}
    if prev_digest:
        known.add(prev_digest)
    here = survey_digest(survey_file(root, survey))
    if here and here in known:
        raise CopiedSurveyError(
            COPIED_SURVEY_REFUSED
            % {"survey": survey, "prev": prev["survey"] if prev else "?", "digest": here[:12]}
        )
    since = window_start(rows, session, now)
    seeds = collect_seeds(items, review_records, reports_since(since), session, since)
    path = seeds_path_for(survey)
    round_id = new_round_id()
    text = render_seeds(seeds, round_id, session, since)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    row = append_round(
        root,
        session,
        survey,
        now,
        round_id,
        seeds=str(path),
        seed_count=len(seeds),
        started=now.timestamp(),
        prev_survey_digest=prev_digest,
    )
    return row, text
