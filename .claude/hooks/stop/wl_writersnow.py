"""wl_writersnow: the /writers-now round record, its half-hourly cadence check and the self-review seeds a repeat round hands its survey (agent/plans/PLAN-writers-now-cadence.md WN1-WN3, operator ruling #ac2de21f).

THE ROUND RECORD (WN1). `worklist.py --writers-now-start <me> <survey>` appends one JSON line to `agent/ledgers/writers-now-rounds.jsonl` at the start of every round: the round id, the session, the UTC start, the survey path, the seeds path and the seed count. Nothing else writes the ledger, and nothing rewrites a line.

THE CADENCE (WN2). `writers-now-due` (effort.json: blocks at `high`, advises at `smart`) fires when this session has no COUNTING round younger than WINDOW_MIN minutes while the Promoted queue holds an open box. A row alone is not a round (operator report 2026-11-24: five hourly rows each copied the first round's survey with `cp` and ran none): a round counts once its survey file exists, was last written after the round's start, and differs from the previous round's survey, and a round whose survey is still missing counts as in progress for SURVEY_GRACE_MIN minutes, then stops counting (`judge_round`). `--writers-now-start` refuses a survey path that already holds the previous round's survey bytes, so the copy fails at the source. It stands down in the landing tree, whose babysit and merge phases work the one open PR and read no queue, in the merge phase of the development tree (the loop state `merged`, where the hook names the next branch first), and inside the window.

THE CAPACITY REFILL (operator asks 2026-11-25 and 2026-11-26). The clock alone left writer capacity idle for most of each window. `capacity` reads the newest round's survey (its section 4 `### Startable now` clusters, the CODE work presumed independent unless their file lists overlap), drops the clusters a box tick or an open, deferred or leased item of this session already covers, and `assess` turns that into one of two messages under the same `writers-now-due` key: REFILL (start a writer on EVERY free cluster from the existing survey, no new survey) while the roster counts fewer than CAPACITY_FLOOR live writers and a free cluster remains, whatever the clock says; and a new round due, by the clock above, or once a survey at least REFRESH_GAP_MIN minutes old has no free cluster left or REFRESH_TICKS of its boxes were ticked. A clock-due round below the floor also names the free slots and the current survey's unstaffed clusters (`short`), so writers start from the old survey while the new one runs.

THE LIVE STAFFING (operator order 2026-11-27). Rounds r77 to r81 each ended "no startable cluster" over 230 startable live boxes with no runner staffed for six hours, because the check read only the CODE clusters. `capacity` also counts each live target's startable boxes from the survey's section 1 rows (or its `## Staffing` table) and reads the worklist tokens `runner:<target>` (staffed) and `runner-hold:<target> -- <reason>` (held, for HOLD_MAX_MIN minutes after the item's last update), target one of bench, hostinger, vm, prod; `assess` orders STAFF RUNNERS for every unstaffed target ahead of any new survey. A cluster of a "blocked behind" subsection whose named blocker boxes have all closed joins the free clusters.

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
import subprocess

import wl_core as C

LEDGER_REL = "agent/ledgers/writers-now-rounds.jsonl"
# The cadence: a round at least this often while Promoted boxes are open (operator ruling #ac2de21f set once per hour; operator request 2026-11-26 halved it, "make writers-now 2x more aggressive"; a second request the same day asked for 1.5x more, "Increase the writers-now pushing 1.5 times more").
WINDOW_MIN = 20
# How long a round whose survey file does not exist yet still counts with no liveness witness: 15 minutes at the 20-minute window (it was 50 at the hour window, 25 at the half-hour one, and shrank with each request, not by a fixed ratio), and a survey agent the hook sees running keeps its round counting up to SURVEY_LIVE_MAX_MIN.
SURVEY_GRACE_MIN = 15
# The most a liveness witness extends a missing survey: a surveyor measured at 21 to 48 minutes, so a task still naming the file after this long is a watcher or a reader, not the producer.
SURVEY_LIVE_MAX_MIN = 180
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
# A matched line that is a markdown heading or ends with a colon (a trailing `**` allowed) introduces a list; BULLET_RE is one item of it.
REPORT_HEAD_RE = re.compile(r"^\s*#{1,6}\s|:\s*(?:\*\*|__)?\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
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


def _names_file(name, text) -> bool:
    """True when `text` names the file `name` as a whole file name: not as the tail or head of a longer one (`s-r4.md` inside `s-r40.md`, or `my-s.md` for `s.md`). A task that merely reads the survey still matches, which SURVEY_LIVE_MAX_MIN bounds (review ec1021d6.4)."""
    return re.search(r"(?<![\w.-])%s(?![\w-])" % re.escape(name), text) is not None


def survey_live(row, prompts, items, live_worker_ids) -> bool:
    """True when something verifiably live is still producing `row`'s survey.

    Two witnesses, either enough: a live task whose first prompt (an agent) or description (a shell) names the survey file, matched on its basename so a relative and an absolute spelling both hit; or a `[>]` item leased to a live worker whose text, last note or lease note names the round id. `prompts` is {task_id: text} for the live tasks of this session, every agent type included (the survey agent is read-only by brief), `items` the worklist fold's records.
    """
    name = pathlib.Path(str(row.get("survey") or "")).name
    if name and any(_names_file(name, str(text or "")) for text in (prompts or {}).values()):
        return True
    rid = str(row.get("round") or "")
    if not rid:
        return False
    live = set(live_worker_ids or ())
    for rec in items or ():
        if rec.get("state") != ">" or rec.get("worker") not in live:
            continue
        if any(rid in str(rec.get(k) or "") for k in ("text", "lastnote", "lease_note")):
            return True
    return False


def judge_round(root, row, prev, now, survey_live=False) -> str:
    """Why `row` does not count toward the cadence, or "" when it counts. `prev` is this session's round before it (or None). A missing survey counts while `survey_live` holds for up to SURVEY_LIVE_MAX_MIN minutes (a live agent or a live-leased item is still producing it), and otherwise for SURVEY_GRACE_MIN minutes after the start, then stops; a survey last written at or before the start is a copy; a survey with the previous round's bytes is a copy.

    Liveness first, the timer as fallback: surveys were measured at 21 to 48 minutes, so a 50-minute grace left a 2-minute margin over a load-dependent duration, and a slower survey fired the check while its agent was visibly working (agent/plans/PLAN-stop-hook-retro-20261125.md friction 3).
    """
    path = survey_file(root, row["survey"])
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        age = (now - C.parse_stamp(row["at"])).total_seconds() / 60.0
        if survey_live and age < SURVEY_LIVE_MAX_MIN:
            return ""
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
    """Append one round row and return it. One `os.write` of one line onto an O_APPEND handle, so two sessions starting rounds at once each keep their own line whenever the write goes down whole. Only a SHORT write (a disk filling mid-line) is continued with further writes, and a second session's append may land between those, so that one row can come out split across lines; `read_rounds` then skips both fragments, the same as any torn line (review 66ac6d0f.1)."""
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


def due(rows, session, now, open_boxes, loop=None, root=None, live=None) -> tuple[bool, dict]:
    """(fires, facts) for `writers-now-due`: fires when `open_boxes` (the Promoted queue's open boxes) is above zero, no stand-down applies, and this session has no round younger than WINDOW_MIN minutes that counts (judge_round; survey paths read against `root`, default the project root). `live`, when given, is a callable row -> bool (survey_live bound to the stop's live tasks and fold); without it every round falls back to the timer. `facts` carries the newest round, its age in minutes (None without one), why it does not count (`not_counted`), the open count and the stand-down reason."""
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
        why = judge_round(
            root, row, mine[i - 1] if i else None, now, bool(live(row)) if live else False
        )
        if not why:
            return False, facts
        if row is last:
            facts["not_counted"] = why
    if not facts["not_counted"]:
        facts["not_counted"] = WHY_TOO_OLD
    return True, facts


def promoted_open(root) -> int:
    """The open boxes of the Promoted entries of agent/plans/QUEUE.md, each plan counted once (wl_planqueue.promoted_progress). A QUEUE.md that cannot be read raises, and so does a Promoted plan whose counts cannot be read (ValueError naming each): a plan that adds 0 would let the cadence stay silent over open boxes, and the callers send a raise to the read-failure note (review bd9a688e.1)."""
    import wl_planqueue as PQ

    text = (pathlib.Path(root) / PQ.QUEUE_REL).read_text(encoding="utf-8")
    seen: dict[str, int] = {}
    unreadable: dict[str, str] = {}
    for row in PQ.promoted_progress(root, text):
        if row.why:
            unreadable.setdefault(row.rel, row.why)
        else:
            seen.setdefault(row.rel, row.opened)
    if unreadable:
        raise ValueError(
            "Promoted plan counts cannot be read: %s"
            % "; ".join("%s (%s)" % (rel, why) for rel, why in sorted(unreadable.items()))
        )
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


def refresh_fields(facts, cap, why, me8) -> dict:
    """The fields of worklist_messages.V_WRITERS_NOW_REFRESH for a round due by `assess`'s survey rules (exhaustion or ticks), where the newest round still counts: `last` names it and its survey's age, without a `not counted` reason."""
    last = facts.get("last") or {}
    return {
        "last": "round %s at %s, survey %d min old"
        % (cap.get("round"), last.get("at", "?"), int(cap.get("age") or 0)),
        "open": facts["open"],
        "who": me8,
        "reason": why,
    }


# ---- the capacity refill -------------------------------------------------------
#
# WHY (operator ask 2026-11-25: many writers started in the last round, and almost all had already finished). Writers finish in 5 to 25 minutes, so a clock that asks for a round only once per window leaves capacity idle for most of it. The survey a round already wrote still names startable clusters nobody took; `capacity` reads them, and the check asks for writers from that survey (REFILL) before it asks for a new survey. Operator request 2026-11-26 ("we still have hundreds of waiting tasks ... they're mostly independent already") raised the floor from 6 to 8, made the refill staff every free cluster rather than only up to the floor, and cut the refresh numbers from 15 boxes and 15 minutes to 8 and 8. The request of the same day asking for 1.5 times more pushing then moved the floor to 12 (CAPACITY_FLOOR), the refresh numbers to 5 boxes and 5 minutes (REFRESH_TICKS, REFRESH_GAP_MIN) and the window to 20 minutes.

# The live-writer floor: below it, every unstaffed startable cluster of the current survey is named to start, clock or no clock. A trigger, not a ceiling: there is no writer limit (agent/plans/PLAN-unlimited-writers.md).
CAPACITY_FLOOR = 12
# Boxes ticked in the Promoted plans since the newest survey was written that make it stale enough to re-survey before the window closes (was 15).
REFRESH_TICKS = 5
# How long a survey stands before its exhaustion or its tick count asks for the next one (was 15): without the floor, a survey whose every startable cluster is already staffed or blocked would ask for a new survey at every stop.
REFRESH_GAP_MIN = 5
# How many free clusters one message lists before it says how many more the survey holds.
REFILL_LIST_MAX = 16
# The survey's cluster section and the bullets of its startable run (`- **CL-<id> (...)**: <plan> <BOX> <sig8> + ... Files: ...`).
CLUSTERS_HEAD_RE = re.compile(r"^## 4\. CODE boxes clustered by shared files", re.MULTILINE)
STARTABLE_HEAD = "### Startable now"
CLUSTER_RE = re.compile(r"^- \*\*(CL-[A-Za-z0-9_-]+)[^*]*\*\*:\s*(.*)$")
# A box row of the survey's plan tables, whose first cell is the box sig.
TABLE_SIG_RE = re.compile(r"^\|\s*([0-9a-f]{8})\s*\|", re.MULTILINE)
# An 8-hex token; a `#` in front makes it an item id, not a box sig.
SIG_TOKEN_RE = re.compile(r"(?<![#0-9A-Za-z])([0-9a-f]{8})(?![0-9A-Za-z])")
# The item states that staff a cluster: open, deferred and leased.
STAFFING_STATES = (" ", "?", ">")
CLUSTER_HEAD_MAX = 140
WHY_EXHAUSTED = "the survey of round %s has no unstaffed startable cluster left"
WHY_TICKED = "%d box(es) ticked in the Promoted plans since round %s's survey (refresh at %d)"
WHY_CLOCK = "no counting round in the last %d minutes" % WINDOW_MIN


def parse_survey(text) -> tuple[list[dict] | None, set[str]]:
    """(startable clusters, box sigs of the plan tables) of one survey.

    The clusters are the `CL-` bullets of `### Startable now` under section 4, up to the first bold paragraph (the review-finding, in-flight and lead blocks) or the next heading. Each carries its id, the sigs named before `Files:` that a plan table lists (so a commit sha or a date is never read as a box), and that head clipped. None when the section or its startable heading is missing: an unreadable layout is unknown, never an empty survey.
    """
    text = text or ""
    sigs = set(TABLE_SIG_RE.findall(text))
    m = CLUSTERS_HEAD_RE.search(text)
    if not m:
        return None, sigs
    lines = text[m.end() :].splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == STARTABLE_HEAD), None)
    if start is None:
        return None, sigs
    clusters = []
    for ln in lines[start + 1 :]:
        if ln.startswith(("#", "**")):
            break
        got = CLUSTER_RE.match(ln)
        if not got:
            continue
        head = got.group(2).split("Files:", 1)[0].strip()
        named = list(dict.fromkeys(t for t in SIG_TOKEN_RE.findall(head) if t in sigs))
        if named:
            clusters.append({"id": got.group(1), "sigs": named, "head": _clip_to(head)})
        elif REVIEW_BOX_RE.search(head):
            # A review-finding cluster (`box none`) names no plan sig; it is staffed by an item naming its id (see `capacity`).
            clusters.append(
                {"id": got.group(1), "sigs": [], "head": _clip_to(head), "review": True}
            )
    return clusters, sigs


REVIEW_BOX_RE = re.compile(r"\bbox none\b", re.IGNORECASE)


def review_staffed(items, session, since) -> list[str]:
    """The text, one string per item, of this session's items of any state first written at or after `since` (the round's start): a review cluster an item of the round names is staffed or done, never free."""
    out = []
    for rec in items or ():
        if not C.owned_by_me(rec.get("owner"), session):
            continue
        first = C.parse_stamp(rec.get("first"))
        if first is None or first < since:
            continue
        out.append(" ".join(str(rec.get(k) or "") for k in ("text", "lastnote", "lease_note")))
    return out


def _id_re(raw, extendable=False):
    """A pattern for the cluster id `raw` in any spelling (`CL-W-CI`, `CL W CI`, `cl_w_ci`): its alphanumeric tokens in order, any run of other characters between them, and no letter or digit on either side. Unless `extendable`, an id continued by a hyphen or underscore and one more token (`CL-W-CI` inside `CL-W-CI-PY-1`) is the start of a longer id and does not match."""
    tokens = re.findall(r"[A-Za-z0-9]+", str(raw or ""))
    tail = r"(?![A-Za-z0-9])" + ("" if extendable else r"(?![-_][A-Za-z0-9])")
    return re.compile(
        r"(?<![A-Za-z0-9])" + r"[^A-Za-z0-9]+".join(map(re.escape, tokens)) + tail, re.IGNORECASE
    )


def _names_cluster(texts, own, all_review) -> bool:
    """Whether one of `texts` (the text of one item each) names the review cluster id `own`. An occurrence of `own` that continues into a longer id does not name it: by a hyphen or underscore and another token (`CL-W-CI-PY-1` beside `CL-W-CI`, whether or not the survey lists the longer one, ac243a48.2), or by the spelling of a longer survey cluster id (`CL W CI PY 1`). Another occurrence in the same text still names it (`CL-W-CI and CL-W-CI-PY-1`, ac243a48.3). A longer id is one `own` begins at the start of, with whole tokens only (f6904b91.1)."""
    own_tokens = re.findall(r"[A-Za-z0-9]+", str(own or ""))
    if not own_tokens:
        return False
    longer = [
        _id_re(o, extendable=True)
        for o in all_review
        if o != own and re.findall(r"[A-Za-z0-9]+", str(o))[: len(own_tokens)] == own_tokens
    ]
    pattern = _id_re(own)
    for text in texts:
        for hit in pattern.finditer(text):
            if not any(m.start() == hit.start() for rx in longer for m in rx.finditer(text)):
                return True
    return False


def _clip_to(text, limit=CLUSTER_HEAD_MAX) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= limit else one[: limit - 3] + "..."


def named_sigs(items, session) -> set[str]:
    """The 8-hex tokens of this session's open, deferred and leased items (text, last note, lease note): a cluster whose sig one of them names is staffed."""
    out: set[str] = set()
    for rec in items or ():
        if rec.get("state") not in STAFFING_STATES or not C.owned_by_me(rec.get("owner"), session):
            continue
        for k in ("text", "lastnote", "lease_note"):
            out.update(SIG_TOKEN_RE.findall(str(rec.get(k) or "")))
    return out


def promoted_box_sigs(root) -> tuple[set[str], set[str]]:
    """(done, open): the sigs of every ticked box of the Promoted plans (a plan moved to `_done/` is read there) minus any sig still open in one of them, and the sigs still open in one of them.

    Boxes with identical text in two plans (the `LP-bench [live]` receipts) share one sig: ticked in one plan and open in another, it is not done, and counting it as done made every survey that lists the open one read as "ticked since". A QUEUE.md that cannot be read raises; a plan file that is gone adds nothing.
    """
    import wl_planqueue as PQ
    import wl_planrec as PR

    root = pathlib.Path(root)
    text = (root / PQ.QUEUE_REL).read_text(encoding="utf-8")
    done: set[str] = set()
    still_open: set[str] = set()
    for rel in dict.fromkeys(rel for _num, rel in PQ.promoted_numbered(text)):
        path = root / rel
        if not path.is_file():
            path = root / PQ.PROGRESS_DONE_DIR / path.name
        if path.is_file():
            body = path.read_text(encoding="utf-8")
            done.update(sig for _i, _l, _b, sig in PR.done_boxes(body))
            still_open.update(sig for _i, _l, _b, sig in PR.open_boxes(body))
    return done - still_open, still_open


def promoted_done_sigs(root) -> set[str]:
    """The ticked sigs of `promoted_box_sigs`: what a survey's table sig counts as ticked since."""
    return promoted_box_sigs(root)[0]


def promoted_open_sigs(root) -> set[str]:
    """The open sigs of `promoted_box_sigs`: what a held cluster's blocker counts as still open (`held_clusters`)."""
    return promoted_box_sigs(root)[1]


# ---- the live staffing and the held clusters ------------------------------------
#
# WHY (operator order 2026-11-27T03:3xZ, "fix the writers-now for also future sessions so when we have hundreds of boxes, we should not make the same mistake(s)"). The Promoted queue held 347 open boxes, 56 of them CODE and every CODE cluster held, 104 LIVE-BENCH, 52 LIVE-VM, 40 LIVE-HOSTINGER and 34 LIVE-PROD. The check read only the CODE clusters, so rounds r77 to r81 each closed as "no startable cluster" and ordered another survey while no live runner had been staffed for about six hours, and the box count did not move. Held clusters stayed held round after round because each survey copied the table forward and nothing re-checked whether the blocker had closed. So the live targets are first-class here: a target with startable boxes that no runner item staffs and no fresh hold holds orders STAFF RUNNERS ahead of any new survey, and a held cluster whose every named blocker box has closed counts as free.

# The live targets and the survey group each reads; a runner is briefed from the section 5 list of that group.
LIVE_TARGETS = ("bench", "hostinger", "vm", "prod")
TARGET_GROUP = {
    "bench": "LIVE-BENCH",
    "hostinger": "LIVE-HOSTINGER",
    "vm": "LIVE-VM",
    "prod": "LIVE-PROD",
}
GROUP_TARGET = {g: t for t, g in TARGET_GROUP.items()}
# The other spellings a `## Staffing` table's first cell may use.
TARGET_ALIASES = {
    "bench": "bench",
    "hostinger": "hostinger",
    "vm": "vm",
    "vm fleet": "vm",
    "fleet": "vm",
    "prod": "prod",
    "production": "prod",
}
SURVEY_GROUPS = (
    "CODE",
    "PRESENT",
    "LIVE-BENCH",
    "LIVE-VM",
    "LIVE-HOSTINGER",
    "LIVE-PROD",
    "GITHUB",
    "TIME",
    "OPERATOR",
)
# A section 1 row: `| sig8 | box | group | needs | evidence |`; the group and needs cells are read by their first token.
ROW_RE = re.compile(r"^\|\s*([0-9a-f]{8})\s*\|[^|]*\|([^|]*)\|([^|]*)\|", re.MULTILINE)
GROUP_TOKEN_RE = re.compile(r"^\s*(%s)(?![\w-])" % "|".join(re.escape(g) for g in SURVEY_GROUPS))
NEEDS_TOKEN_RE = re.compile(r"^\s*(none|bench-deploy|verified-vmcheck|pushed-head)(?![\w-])")
SECTION1_RE = re.compile(r"^## 1\.[^\n]*$", re.MULTILINE)
STAFFING_HEAD_RE = re.compile(r"^## Staffing\b[^\n]*$", re.MULTILINE)
NEXT_H2_RE = re.compile(r"^## ", re.MULTILINE)
# The worklist tokens (writers-now.md, "An empty round"). `runner:<target>` on an open or leased item of this session staffs the target while its worker is live or the item moved in the last RUNNER_RECENT_MIN minutes; `runner-hold:<target> -- <reason>` on an open, deferred or leased item holds it for HOLD_MAX_MIN minutes after the item's last update, so a hold expires and never parks a target for good.
# A token followed by an item id (`runner:vm #b201a49d`) names another item's runner, as a note citing it does, and staffs nothing (measured on r81: a ci:quick item's note "the VERIFIED vm:check comes from runner:vm #b201a49d" read as a vm runner). The fold keeps an item's text and only its LAST note, so the claim belongs in the `--add` text, where a later note or an auto-lease cannot overwrite it.
RUNNER_TOKEN_RE = re.compile(
    r"(?<![\w-])runner:(bench|hostinger|vm|prod)(?![\w-])(?!\s+#[0-9a-f]{6,})"
)
HOLD_TOKEN_RE = re.compile(
    r"(?<![\w-])runner-hold:(bench|hostinger|vm|prod)\s+--\s+(\S[^\n]*?)(?=\s+runner(?:-hold)?:|$)",
    re.MULTILINE,
)
RUNNER_RECENT_MIN = 45
HOLD_MAX_MIN = 120
RUNNER_STATES = (" ", ">")
HOLD_STATES = (" ", "?", ">")
# Production counts as held unless a standing authorization is readable, and none is: block_unasked_release judges each release command against an ASKED line of the transcript, so no record names a standing one. A `runner:prod` item still staffs it once the lead holds an authorization.
PROD_HELD_DEFAULT = (
    "held by default: no production authorization the hooks can read (block_unasked_release "
    "judges each release command against the transcript's ASKED line); a `runner:prod` item "
    "staffs it under a standing authorization"
)
# A held cluster's blockers: its `BOX:<plan>#<sig8>` tokens when it names any, else its bare 8-hex tokens that are not its own CODE boxes.
BOX_TOKEN_RE = re.compile(r"\bBOX:[^\s#]*#([0-9a-f]{8})(?![0-9A-Za-z])")
HELD_HEAD_RE = re.compile(r"^###\s.*\bblocked behind\b", re.IGNORECASE)
HELD_BULLET_RE = re.compile(r"^- (?:\*\*)?(CL-[A-Za-z0-9_-]+)(.*)$")


def _section(text, head_re) -> str | None:
    """The body of the level-2 section `head_re` opens, up to the next level-2 heading; None when the heading is absent."""
    text = text or ""
    m = head_re.search(text)
    if not m:
        return None
    nxt = NEXT_H2_RE.search(text, m.end())
    return text[m.end() : nxt.start() if nxt else len(text)]


def survey_rows(text) -> dict[str, tuple[str, str]]:
    """{sig: (group, needs)} of the survey's section 1 plan tables (the whole text when the survey has no `## 1.` heading). A row whose group cell names no survey group is not a plan row (the section 4 cluster table shares the first column); a needs cell with no known value reads as "". The first row of a sig wins."""
    body = _section(text, SECTION1_RE)
    if body is None:
        body = text or ""
    out: dict[str, tuple[str, str]] = {}
    for sig, group_cell, needs_cell in ROW_RE.findall(body):
        g = GROUP_TOKEN_RE.match(group_cell)
        if not g or sig in out:
            continue
        n = NEEDS_TOKEN_RE.match(needs_cell)
        out[sig] = (g.group(1), n.group(1) if n else "")
    return out


def startable_for(target, needs, vm_verified) -> bool:
    """Whether a box of `target` whose `Needs:` is `needs` can start now: `none` for every target; `bench-deploy` for bench, whose runner deploys first; `verified-vmcheck` for vm, whose runner runs vm:check first, and for the others once `vm_verified()` answers that a VERIFIED vm:check receipt covers HEAD; `pushed-head` (and an unreadable value) never."""
    if needs == "none":
        return True
    if needs == "bench-deploy":
        return target == "bench"
    if needs == "verified-vmcheck":
        return target == "vm" or bool(vm_verified and vm_verified())
    return False


def target_counts(rows, done, vm_verified=None) -> dict[str, dict[str, int]]:
    """{target: {needs: count}} of the startable live boxes among `rows` (survey_rows), the ticked `done` sigs left out. `vm_verified` is asked at most once, and only for a non-vm `verified-vmcheck` row."""
    cached: dict[str, bool] = {}

    def verified() -> bool:
        if "v" not in cached:
            cached["v"] = bool(vm_verified and vm_verified())
        return cached["v"]

    out: dict[str, dict[str, int]] = {t: {} for t in LIVE_TARGETS}
    for sig, (group, needs) in rows.items():
        target = GROUP_TARGET.get(group)
        if target is None or sig in done:
            continue
        if startable_for(target, needs, verified):
            out[target][needs] = out[target].get(needs, 0) + 1
    return out


def staffing_table(text) -> dict[str, int] | None:
    """{target: startable} of the survey's `## Staffing` table (`target | startable | runner item or hold reason`), or None without the section. Only the startable counts are read: whether a target is staffed or held is always derived from the worklist items, never from a survey that may have copied it forward."""
    body = _section(text, STAFFING_HEAD_RE)
    if body is None:
        return None
    out: dict[str, int] = {}
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip("*` ").lower()
        target = TARGET_ALIASES.get(name) or GROUP_TARGET.get(name.upper())
        num = re.match(r"\d+", cells[1])
        if target and num:
            out[target] = int(num.group(0))
    return out


def _upd_min(rec, now) -> float | None:
    """Minutes since the item's last update (its first write when it has none); None when neither stamp reads."""
    stamp = C.parse_stamp(rec.get("upd")) or C.parse_stamp(rec.get("first"))
    return None if stamp is None else (now - stamp).total_seconds() / 60.0


def runner_status(items, session, now, live_ids=()) -> dict[str, tuple[str, str]]:
    """{target: (state, note)} from this session's items: ("staffed", "#<id>") for a `runner:<target>` item open or leased whose worker is live or which moved in the last RUNNER_RECENT_MIN minutes, else ("held", "#<id>: <reason>") for a `runner-hold:<target> -- <reason>` item open, deferred or leased that moved in the last HOLD_MAX_MIN minutes. A target with neither is absent. Staffed wins over held, and an item carrying the token in its own text is named before one carrying it only in a note.

    The item's own text is `basetext` (the fold's `text` of a leased item has the lease note appended), then the last note, then the lease note, each on its own line so a hold's reason ends with its line.
    """
    live = set(live_ids or ())
    staffed: dict[str, tuple[int, str]] = {}
    held: dict[str, str] = {}
    for rec in items or ():
        if not C.owned_by_me(rec.get("owner"), session):
            continue
        state = rec.get("state")
        own = str(rec.get("basetext") or rec.get("text") or "")
        notes = "\n".join(str(rec.get(k) or "") for k in ("lastnote", "lease_note"))
        age = _upd_min(rec, now)
        if state in RUNNER_STATES:
            fresh = age is not None and age < RUNNER_RECENT_MIN
            alive = state == ">" and rec.get("worker") in live
            if fresh or alive:
                for rank, part in ((0, own), (1, notes)):
                    for target in RUNNER_TOKEN_RE.findall(part):
                        if target not in staffed or rank < staffed[target][0]:
                            staffed[target] = (rank, "#%s" % rec.get("id"))
        if state in HOLD_STATES and age is not None and age < HOLD_MAX_MIN:
            for target, reason in HOLD_TOKEN_RE.findall(own + "\n" + notes):
                held.setdefault(target, "#%s: %s" % (rec.get("id"), _clip_to(reason, 100)))
    out = {t: ("held", n) for t, n in held.items()}
    out.update({t: ("staffed", n) for t, (_rank, n) in staffed.items()})
    return out


def live_targets(text, done, items, session, now, live_ids=(), vm_verified=None) -> list[dict]:
    """One row per live target, in LIVE_TARGETS order: `target`, `startable` (the `## Staffing` table's count when the survey has one, else the section 1 rows counted by `target_counts`), `needs` (the per-value counts, {} when the table decided), `state` (`staffed`, `held` or `unstaffed`; prod is `held` by default with PROD_HELD_DEFAULT unless a runner item staffs it) and `note`."""
    table = staffing_table(text)
    counts = target_counts(survey_rows(text), done, vm_verified) if table is None else None
    status = runner_status(items, session, now, live_ids)
    out = []
    for target in LIVE_TARGETS:
        if counts is None:
            needs: dict[str, int] = {}
            startable = (table or {}).get(target, 0)
        else:
            needs = counts[target]
            startable = sum(needs.values())
        state, note = status.get(target, ("unstaffed", ""))
        if target == "prod" and state == "unstaffed":
            state, note = "held", PROD_HELD_DEFAULT
        out.append(
            {"target": target, "startable": startable, "needs": needs, "state": state, "note": note}
        )
    return out


def unstaffed(cap) -> list[dict]:
    """The live targets of `cap` with startable boxes that are neither staffed nor held."""
    return [
        t
        for t in (cap or {}).get("targets") or ()
        if t["startable"] > 0 and t["state"] == "unstaffed"
    ]


def held_clusters(text, rows) -> list[dict]:
    """The clusters of section 4's "blocked behind" subsections (any `###` heading naming "blocked behind"): each carries its id, `own` (the sigs it names that section 1 lists as CODE), `blockers` (its `BOX:<plan>#<sig8>` tokens when it names any, else every other 8-hex token it names before `Files:`) and its head clipped. A bullet may be bold or plain (`- **CL-X**: ...` or `- CL-X: ...`)."""
    body = _section(text, CLUSTERS_HEAD_RE)
    if body is None:
        return []
    out = []
    inside = False
    for ln in body.splitlines():
        if ln.startswith("#"):
            inside = bool(HELD_HEAD_RE.match(ln))
            continue
        got = HELD_BULLET_RE.match(ln) if inside else None
        if not got:
            continue
        head = got.group(2).split("Files:", 1)[0]
        tokens = list(dict.fromkeys(SIG_TOKEN_RE.findall(head)))
        own = [t for t in tokens if rows.get(t, ("", ""))[0] == "CODE"]
        boxed = list(dict.fromkeys(BOX_TOKEN_RE.findall(head)))
        blockers = [b for b in (boxed or tokens) if b not in own]
        out.append(
            {
                "id": got.group(1),
                "own": own,
                "blockers": blockers,
                "head": _clip_to(head.lstrip("*: ")),
            }
        )
    return out


def blocker_open(blockers, opened) -> bool:
    """True while one of `blockers` is still an open box (`opened`): the one clause that keeps a held cluster held."""
    return any(b in opened for b in blockers)


def unblocked(held, done, open_sigs, named) -> list[dict]:
    """The held clusters whose blockers have all closed, as free clusters: a cluster with an own CODE sig neither ticked nor named by an item of this session, at least one blocker that is a known box (open or ticked in the Promoted plans), and no blocker still open. `open_sigs` is called once, and only when a cluster has a blocker to judge; without it, or with no known blocker, a cluster stays held."""
    out = []
    opened: set[str] | None = None
    for cl in held:
        left = [s for s in cl["own"] if s not in done]
        if not left or any(s in named for s in cl["own"]) or not cl["blockers"] or not open_sigs:
            continue
        if opened is None:
            opened = set(open_sigs())
        known = [b for b in cl["blockers"] if b in opened or b in done]
        if not known or blocker_open(known, opened):
            continue
        out.append(
            {
                "id": cl["id"],
                "sigs": left,
                "head": _clip_to("(blocker %s closed) %s" % (" ".join(known), cl["head"])),
                "unblocked": known,
            }
        )
    return out


def capacity(
    rows,
    session,
    root,
    items,
    live_writers,
    done_sigs,
    now=None,
    head_time=None,
    live_ids=(),
    open_sigs=None,
    vm_verified=None,
) -> dict:
    """The refill facts of this session's newest round.

    `live_writers` is the count of live writers the roster sees (code writers and live runners alike; None when it cannot count, which never refills). `done_sigs` is a callable returning the Promoted plans' ticked sigs, called only once a survey parses. In the facts, `free` lists the startable clusters with at least one unticked sig and no sig named by an open, deferred or leased item of this session (each carrying only its unticked sigs), `ticked` counts the survey's table sigs ticked since, `age` is the survey file's age in minutes, and `moved` is True when a box was ticked or a HEAD commit is newer than the survey (or git cannot answer); `read` is False when there is no round, no survey file or no parseable cluster section.

    The live half: `targets` holds one `live_targets` row per target whenever the survey file reads, section 4 or not (`live_ids` the live worker ids, `vm_verified` the VERIFIED vm:check probe); and a cluster of a "blocked behind" subsection joins `free` once every blocker it names has closed (`held_clusters`, `unblocked`; `open_sigs` a callable returning the Promoted plans' open sigs, asked only when a held cluster names a blocker).
    """
    now = now or C.utcnow()
    mine = _mine(rows, session)
    last = mine[-1] if mine else None
    facts = {
        "round": None if last is None else last.get("round"),
        "survey": None if last is None else str(last["survey"]),
        "read": False,
        "free": [],
        "live": live_writers,
        "floor": CAPACITY_FLOOR,
        "ticked": 0,
        "age": None,
        "moved": True,
        "targets": [],
    }
    if last is None:
        return facts
    path = survey_file(root, last["survey"])
    try:
        text = path.read_text(encoding="utf-8")
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return facts
    clusters, table = parse_survey(text)
    done = set(done_sigs())
    facts["targets"] = live_targets(text, done, items, session, now, live_ids, vm_verified)
    if clusters is None:
        return facts
    named = named_sigs(items, session)
    facts["read"] = True
    facts["age"] = (now.timestamp() - mtime) / 60.0
    # The survey's plan tables list the OPEN boxes of its round (the /writers-now survey sorts every open box), so a table sig ticked now was ticked after the survey was written, which is what WHY_TICKED and REFRESH_TICKS count (review 7d036d68.1).
    facts["ticked"] = len(table & done)
    # Movement since the survey: a tick, or a commit newer than the survey (a landing brings review findings, which become new clusters). Unknown counts as moved.
    landed = (head_time or (lambda: head_commit_time(root)))()
    facts["moved"] = facts["ticked"] > 0 or landed is None or landed > mtime
    staffed = review_staffed(items, session, C.parse_stamp(last["at"]))
    review_ids = [c["id"] for c in clusters if c.get("review")]
    for cl in clusters:
        if cl.get("review"):
            if not _names_cluster(staffed, cl["id"], review_ids):
                facts["free"].append(cl)
            continue
        left = [s for s in cl["sigs"] if s not in done]
        if left and not any(s in named for s in cl["sigs"]):
            facts["free"].append({**cl, "sigs": left})
    held = held_clusters(text, survey_rows(text))
    facts["free"].extend(unblocked(held, done, open_sigs, named))
    return facts


def head_commit_time(root) -> float | None:
    """The committer time of HEAD in `root` (epoch seconds), or None when git cannot answer."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stdout.strip()
    return float(text) if out.returncode == 0 and text.isdigit() else None


def assess(clock_fires, clock_facts, cap) -> tuple[str, str]:
    """(kind, why) of the writers-now check: ("staff", "") when live runners start from the current survey, ("due", why) when a new round is due, ("refill", "") when writers start from the current survey, ("", "") otherwise.

    STAFF RUNNERS decides first: a live target with startable boxes that no `runner:<target>` item staffs and no fresh `runner-hold:<target>` item holds (`unstaffed`) orders its runner instead of a new survey, the clock's included, because a survey cannot move a live box and rounds r77 to r81 re-surveyed five times over 230 unstaffed live boxes. A new round is therefore due only once every CODE cluster and every live target with startable boxes is staffed or held. The clock (`due`) decides next; its message carries the capacity shortfall (`short`) beside it. A survey at least REFRESH_GAP_MIN minutes old is then due once it has no free cluster left and something `moved` since it was written, or once REFRESH_TICKS of its boxes were ticked. A refill fires when the roster counts fewer than CAPACITY_FLOOR live writers and the survey still holds a free cluster (open CODE work), inside the clock's window or not. A stand-down or an empty Promoted queue (in `clock_facts`) silences all three.
    """
    if not clock_facts or clock_facts.get("why") or int(clock_facts.get("open") or 0) <= 0:
        return "", ""
    if unstaffed(cap):
        return "staff", ""
    if clock_fires:
        return "due", WHY_CLOCK
    if not cap or not cap.get("read"):
        return "", ""
    if (cap.get("age") or 0) >= REFRESH_GAP_MIN:
        if not cap["free"] and cap.get("moved", True):
            return "due", WHY_EXHAUSTED % cap["round"]
        if cap["ticked"] >= REFRESH_TICKS:
            return "due", WHY_TICKED % (cap["ticked"], cap["round"], REFRESH_TICKS)
    if short(cap):
        return "refill", ""
    return "", ""


def short(cap) -> bool:
    """True when the roster counts fewer than CAPACITY_FLOOR live writers and the newest survey still holds a free startable cluster. An uncountable roster (live None) or an unread survey is never short."""
    if not cap or not cap.get("read"):
        return False
    live = cap.get("live")
    return live is not None and live < cap.get("floor", CAPACITY_FLOOR) and bool(cap["free"])


def staff_fields(cap, me8) -> dict:
    """The fields of worklist_messages.V_WRITERS_NOW_STAFF: one row per unstaffed target (its startable count, the per-value split and the survey section to brief from), and one line naming each other target's staffing (the runner item or the hold and its reason) so the order reads whole."""
    rows = []
    for t in unstaffed(cap):
        split = ", ".join("%d needs %s" % (n, k) for k, n in sorted(t["needs"].items()))
        rows.append(
            "  - %s: %d startable box(es)%s; brief from the survey's section 5 `%s` list"
            % (
                t["target"],
                t["startable"],
                " (%s)" % split if split else "",
                TARGET_GROUP[t["target"]],
            )
        )
    others = [
        "%s %s (%d startable%s)"
        % (t["target"], t["state"], t["startable"], ", %s" % t["note"] if t["note"] else "")
        for t in cap.get("targets") or ()
        if t not in unstaffed(cap)
    ]
    return {
        "n": len(rows),
        "round": cap.get("round"),
        "survey": cap.get("survey"),
        "rows": "\n".join(rows),
        "others": "; ".join(others) or "none",
        "recent": RUNNER_RECENT_MIN,
        "hold": HOLD_MAX_MIN,
        "who": me8,
    }


def refill_shown(cap) -> list[dict]:
    """The free clusters a refill names: every one, in survey order, up to REFILL_LIST_MAX. The floor triggers the refill and never caps it, so a free cluster beyond the floor is staffed in the same wave."""
    return cap["free"][:REFILL_LIST_MAX]


def refill_fields(cap, me8) -> dict:
    """The fields of worklist_messages.V_WRITERS_NOW_REFILL and V_WRITERS_NOW_SHORT: the free slots below the floor, and each named cluster as `CL-<id> <sigs>: <head>`, with a closing line counting the free clusters past REFILL_LIST_MAX."""
    shown = refill_shown(cap)
    live = int(cap["live"] or 0)
    floor = int(cap.get("floor", CAPACITY_FLOOR))
    rows = ["  - %s %s: %s" % (cl["id"], " ".join(cl["sigs"]), cl["head"]) for cl in shown]
    if len(cap["free"]) > len(shown):
        rows.append(
            "  - and %d more free cluster(s) in the survey" % (len(cap["free"]) - len(shown))
        )
    return {
        "n": len(cap["free"]),
        "live": live,
        "floor": floor,
        "slots": max(0, floor - live),
        "round": cap["round"],
        "survey": cap["survey"],
        "free": len(cap["free"]),
        "rows": "\n".join(rows),
        "who": me8,
    }


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
        lines = str(body).splitlines()
        i = 0
        while i < len(lines) and n < REPORT_LINES_MAX:
            line = lines[i]
            i += 1
            if not REPORT_SEED_RE.search(line):
                continue
            text = line
            if REPORT_HEAD_RE.search(line):
                # A heading ("Two defects for the lead") or a line ending in a colon owns the bullets under it: they are the content, so they ride the same seed (bounded by SEED_TEXT_MAX through _clip).
                bullets, i = _bullets_after(lines, i)
                text = " ".join([line.strip(), *bullets])
            out.append(
                {
                    "kind": "report",
                    "ref": "%s (%s)" % (entry.get("agent") or "agent", entry.get("id")),
                    "text": _clip(text),
                }
            )
            n += 1
    return out


def _bullets_after(lines, start) -> tuple[list[str], int]:
    """The bullet lines that follow a heading at `lines[start - 1]` (one blank line may sit between), and the index after the last one taken; a non-bullet line ends the run and is not consumed, and neither is a bullet REPORT_SEED_RE matches, which is a seed of its own and would be clipped away inside the heading's (c08df3b0.1)."""
    out: list[str] = []
    i = start
    if i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and BULLET_RE.match(lines[i]) and not REPORT_SEED_RE.search(lines[i]):
        out.append(lines[i].strip())
        i += 1
    return (out, i) if out else ([], start)


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
