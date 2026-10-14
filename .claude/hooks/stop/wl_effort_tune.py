"""wl_effort_tune: the effort table tunes itself from measured outcomes (agent/plans/PLAN-stop-hook-effort-tuning.md T2-T6).

THE ASK (operator 2026-10-14): make `smart` "smarter/auto-improved by the AI contexts ... for all the sessions for the future contexts as well". wl_outcomes records what followed each check; this module turns those rows into a reviewed change to `.claude/config/effort.json`, and nothing else edits the table for tuning.

  PROPOSALS (T2)  `worklist.py --effort-propose <me> <key> <block|advise|off>@<level> <evidence>`: a row in agent/ledgers/effort-proposals.jsonl, refused unless the evidence cites outcome rows of that key by id (`eo-xxxxxxxx`) with a count.
  THE CORE (T3)   `stats` (per-key precision over a window), `candidates` (demotions, promotions, re-promotions), `dead_keys`, `replay` (which recorded stops would decide differently under the candidate table), written by `run` as a git-apply patch with an evidence table.
  THE TRIGGER (T4) at ctx_budget.TUNE_FRACTION of the auto-compact threshold, once per context epoch, the Stop hook queues the request (`request_due`); `brief` hands the session's context to the `effort-tuner` agent (.claude/agents/effort-tuner.md), whose run lands under agent/<me8>/effort-tune/e<epoch>/ and survives compaction.
  TRUST (T5)      `apply`: a promotion (stricter) is written at once with a report line; demotions wait for ONE batched /ask (`ask.json`, the diff as each option's preview) and `--effort-answer`, which records each answer so it is not asked again. The FLOOR (wl_floor.FLOOR) is never tuned, and the effort-table rule refuses a `tuned` row for a FLOOR key (`tuned_problems`). Every tuned key carries `tuned_at` and `review_after`; a demoted key that stayed quiet before a CI red or a review finding (a `miss` row) is promoted back.
  JUDGE ERRORS (T6) `judge_shapes`: recurring judge-error shapes among the `judge` rows become a proposed rule with its test.

The operator's rulings are binding: the tuner runs near compaction through a sub-agent; demotions reach the operator as one /ask with the diff as preview and recorded answers; `work` is wl_outcomes' 3-stop rule; promotions auto-apply and report. Reads no environment variable.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import difflib
import json
import pathlib
import re
import sys
from typing import Any

import wl_effort
import wl_floor
import wl_outcomes as O
import wl_retro

WINDOW_DAYS = 14
# Fewer rows than this for the verdict being changed is no evidence at all.
MIN_ROWS = 5
# A verdict whose rows led to work less often than this is demoted; at least this often, promoted.
DEMOTE_BELOW = 0.2
PROMOTE_AT = 0.6
REVIEW_DAYS = 14
# A key is called dead only when the window holds at least this many recorded stops.
DEAD_MIN_STOPS = 20
# A judge-error shape needs this many rows to become a proposed rule.
JUDGE_SHAPE_MIN = 3
# `quiet` is the FLOOR alone, so a tuned threshold never goes below `low`.
LOWEST = "low"
ASK_OPTIONS = 4
ASK_QUESTIONS = 4
RUN_DIR = "effort-tune"

_ROW_ID = re.compile(r"\beo-[0-9a-f]{8}\b")
_COUNT = re.compile(r"\b\d+\s*/\s*\d+\b|\bn\s*=\s*\d+\b|\b\d+\s+of\s+\d+\b")
_SPEC = re.compile(r"^(block|advise|off)@(quiet|low|smart|high|ultra)$")


def _now():
    return datetime.datetime.now(datetime.UTC)


def _stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp):
    try:
        return datetime.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        return None


def table_path(root):
    return pathlib.Path(root) / wl_effort.TABLE_REL


def read_table(root):
    """(table, text) of `root`'s effort.json, else of the table the hook itself reads (wl_effort.TABLE_PATH, for a project with none of its own); (None, "") when unreadable. Writes always go to `root`'s."""
    path = table_path(root)
    if not path.is_file():
        path = wl_effort.TABLE_PATH
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text), text
    except (OSError, ValueError):
        return None, ""


def render(table):
    """effort.json's own formatting (two-space JSON, a trailing newline), so a tuned table diffs only where it changed."""
    return json.dumps(table, indent=2, ensure_ascii=False) + "\n"


def write_table(root, table):
    table_path(root).write_text(render(table), encoding="utf-8")
    wl_effort._CACHE.clear()


# ---- levels -------------------------------------------------------------------------------------


def _step(level, by):
    at = wl_effort.rank(level) + by
    lo = wl_effort.rank(LOWEST)
    return wl_effort.LEVELS[max(lo, min(at, len(wl_effort.LEVELS) - 1))]


def demote(entry):
    """One step quieter: a blocking key blocks one level later (then advises one level later at ultra); an advisory-only key advises one level later."""
    new = dict(entry)
    if "block" in new and new["block"] != "ultra":
        new["block"] = _step(new["block"], 1)
    else:
        new["advise"] = _step(new["advise"], 1)
    return new


def promote(entry):
    """One step stricter: a blocking key blocks one level sooner (dragging `advise` along when they meet), never below LOWEST; an advisory-only key advises one level sooner."""
    new = dict(entry)
    if "block" in new:
        if wl_effort.rank(new["block"]) > wl_effort.rank(new["advise"]):
            new["block"] = _step(new["block"], -1)
        else:
            new["block"] = new["advise"] = _step(new["advise"], -1)
    else:
        new["advise"] = _step(new["advise"], -1)
    return new


def _stricter(old, new):
    """True when `new` blocks or advises at a lower level than `old` anywhere."""
    for field in ("block", "advise"):
        if (
            field in old
            and field in new
            and wl_effort.rank(new[field]) < wl_effort.rank(old[field])
        ):
            return True
    return False


def tunable(key, table):
    """True for a key the tuner may touch: a table row with levels, never a FLOOR key."""
    entry = ((table or {}).get("checks") or {}).get(key)
    return key not in wl_floor.FLOOR and isinstance(entry, dict)


# ---- T3: per-key precision ----------------------------------------------------------------------


def _blank():
    return {
        "rows": 0,
        "work": 0,
        "paperwork": 0,
        "overruled": 0,
        "expired": 0,
        "strong": 0,
        "ids": [],
    }


def stats(rows, now=None, window_days=WINDOW_DAYS, table=None):
    """{key: {"block": counts, "advise": counts, "off": counts, "miss_quiet": n, "miss_ids": [...]}} over the outcome rows decided inside the window. `judge` rows are the judge's, not a table key's, and are left to judge_shapes.

    With `table`, a row counts toward its verdict only while `table` still gives that verdict at the row's level: evidence gathered under a threshold the table has since moved says nothing about the new one, and without this rule one accepted demotion would propose the next from the same rows. The miss count reads the recorded verdict either way."""
    now = now or _now()
    since = now - datetime.timedelta(days=window_days)
    out: dict[str, dict] = {}
    for row in rows:
        if row.get("kind") != "outcome" or row.get("outcome") not in O.OUTCOMES:
            continue
        when = _parse(row.get("decided") or row.get("at"))
        if when is None or when < since:
            continue
        key = wl_floor.base(row.get("key") or "")
        if not key or key == "judge":
            continue
        slot = out.setdefault(
            key,
            {
                "block": _blank(),
                "advise": _blank(),
                "off": _blank(),
                "miss_quiet": 0,
                "miss_ids": [],
            },
        )
        verdict = row.get("verdict") if row.get("verdict") in ("block", "advise", "off") else "off"
        if row.get("miss") and verdict != "block":
            slot["miss_quiet"] += 1
            slot["miss_ids"].append(str(row.get("id") or ""))
        if (
            table is not None
            and row.get("level") in wl_effort.LEVELS
            and wl_effort.verdict(key, row["level"], table) != verdict
        ):
            continue
        c = slot[verdict]
        c["rows"] += 1
        c[row["outcome"]] += 1
        c["strong"] += 1 if row.get("strong") and row["outcome"] == "overruled" else 0
        c["ids"].append(str(row.get("id") or ""))
    return out


def precision(counts):
    """work / rows, a strong (operator) overrule counted twice. None for no rows."""
    denom = counts["rows"] + counts["strong"]
    return counts["work"] / denom if denom else None


def candidates(table, st, now=None):
    """The changes the evidence supports, one per key at most: a re-promotion when a demoted key stayed quiet before a miss, else a demotion of a blocking verdict that rarely led to work, else a promotion of an advisory that usually did."""
    now = now or _now()
    tuned = (table or {}).get("tuned") or {}
    out = []
    for key in sorted(st):
        if not tunable(key, table):
            continue
        entry = table["checks"][key]
        slot = st[key]
        prior = tuned.get(key) if isinstance(tuned.get(key), dict) else None
        if prior and prior.get("direction") == "demote" and slot["miss_quiet"]:
            back = prior.get("from")
            if isinstance(back, dict) and back != entry:
                out.append(
                    _change(
                        key,
                        "promote",
                        entry,
                        back,
                        "re-promotion: demoted %s, then quiet before %d miss(es) (a CI red or a review finding)"
                        % (prior.get("tuned_at"), slot["miss_quiet"]),
                        slot["miss_ids"],
                        None,
                    )
                )
                continue
        blk, adv = slot["block"], slot["advise"]
        p_blk, p_adv = precision(blk), precision(adv)
        if blk["rows"] >= MIN_ROWS and p_blk is not None and p_blk < DEMOTE_BELOW:
            new = demote(entry)
            if new != entry:
                out.append(
                    _change(
                        key,
                        "demote",
                        entry,
                        new,
                        "blocked %d time(s), %d/%d led to work (%d paperwork, %d overruled, %d expired)"
                        % (
                            blk["rows"],
                            blk["work"],
                            blk["rows"],
                            blk["paperwork"],
                            blk["overruled"],
                            blk["expired"],
                        ),
                        blk["ids"],
                        p_blk,
                    )
                )
                continue
        if adv["rows"] >= MIN_ROWS and p_adv is not None and p_adv >= PROMOTE_AT:
            new = promote(entry)
            if new != entry:
                out.append(
                    _change(
                        key,
                        "promote",
                        entry,
                        new,
                        "advised %d time(s), %d/%d led to work"
                        % (adv["rows"], adv["work"], adv["rows"]),
                        adv["ids"],
                        p_adv,
                    )
                )
    return out


def _change(key, direction, old, new, reason, ids, prec):
    return {
        "key": key,
        "direction": direction,
        "from": old,
        "to": new,
        "reason": reason,
        "ids": [i for i in ids if i][:12],
        "precision": None if prec is None else round(prec, 3),
    }


def dead_keys(table, rows, now=None, window_days=WINDOW_DAYS):
    """Table keys (FLOOR aside) with no outcome row at all in a window that recorded at least DEAD_MIN_STOPS stops; [] when the window is too thin to say."""
    now = now or _now()
    since = now - datetime.timedelta(days=window_days)
    stops, seen = set(), set()
    for row in rows:
        if row.get("kind") != "outcome":
            continue
        when = _parse(row.get("decided") or row.get("at"))
        if when is None or when < since:
            continue
        stops.add((row.get("session"), row.get("epoch"), row.get("stop")))
        seen.add(wl_floor.base(row.get("key") or ""))
    if len(stops) < DEAD_MIN_STOPS:
        return []
    return sorted(
        k for k in ((table or {}).get("checks") or {}) if tunable(k, table) and k not in seen
    )


def review_due(table, now=None):
    """Tuned keys whose `review_after` has passed."""
    now = now or _now()
    out = []
    for key, rec in sorted(((table or {}).get("tuned") or {}).items()):
        when = _parse((rec or {}).get("review_after")) if isinstance(rec, dict) else None
        if when is not None and when <= now:
            out.append(key)
    return out


def apply_changes(table, changes, now=None):
    """A deep copy of `table` with each change written to `checks` and stamped under `tuned`."""
    now = now or _now()
    new = copy.deepcopy(table)
    tuned = new.setdefault("tuned", {})
    for ch in changes:
        if not tunable(ch["key"], new):
            raise ValueError("%s is not tunable (a FLOOR key or not a table row)" % ch["key"])
        new["checks"][ch["key"]] = _ordered(ch["to"], new["checks"][ch["key"]])
        tuned[ch["key"]] = {
            "direction": ch["direction"],
            "from": _ordered(ch["from"], ch["from"]),
            "tuned_at": _stamp(now),
            "review_after": _stamp(now + datetime.timedelta(days=REVIEW_DAYS)),
            "evidence": ", ".join(ch.get("ids") or ())[:200],
        }
    return new


def _ordered(entry, like):
    """`entry` with its fields in `like`'s order, then `block` before `advise` as the table writes them, so a tuned row diffs only in its values."""
    order = [k for k in like if k in entry] if isinstance(like, dict) else []
    rest = [k for k in ("block", "advise") if k in entry and k not in order]
    return {k: entry[k] for k in [*order, *rest]}


def diff(old_text, new_text):
    """A `git apply` patch of effort.json from `old_text` to `new_text`, "" when they are equal."""
    if old_text == new_text:
        return ""
    rel = wl_effort.TABLE_REL
    body = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            "a/" + rel,
            "b/" + rel,
        )
    )
    return "diff --git a/%s b/%s\n%s" % (rel, rel, body)


def replay(rows, old, new):
    """Every recorded emission whose verdict at its own level differs between `old` and `new`: (session, epoch, stop, key, level, old verdict, new verdict, outcome, row id), in stop order."""
    out = []
    for row in rows:
        if row.get("kind") != "outcome" or row.get("key") == "judge":
            continue
        level = row.get("level")
        if level not in wl_effort.LEVELS:
            continue
        was = wl_effort.verdict(row["key"], level, old)
        now = wl_effort.verdict(row["key"], level, new)
        if was != now:
            out.append(
                (
                    row.get("session"),
                    row.get("epoch"),
                    row.get("stop"),
                    row["key"],
                    level,
                    was,
                    now,
                    row.get("outcome"),
                    row.get("id"),
                )
            )
    out.sort(key=lambda r: (str(r[0]), int(r[1] or 0), int(r[2] or 0), r[3]))
    return out


# ---- T6: judge-error shapes ---------------------------------------------------------------------

_STATUS = r"(?i)\b(?:## Remaining|status table|the (?:message|status|report|table) omits|by id|loop schedule|restate)"
_RULE = r"(?i)\b(?:ask the operator|git (?:stash|checkout|restore|clean)|--no-verify|second branch|worktree add|commit permission)"
JUDGE_SHAPES: tuple[dict[str, Any], ...] = (
    {
        "shape": "reraised-finished",
        "what": "a continue that orders work already ticked",
        "where": "wl_judge: a settle rule beside settle_closed_reraise, applied to the reason as well as the order",
        "source": (
            'import re\n\n_REF = re.compile(r"#([0-9a-f]{6,12})\\b")\n\n\n'
            "def matches(reason, closed_ids=()):\n"
            '    """True when every item the judge names is already closed."""\n'
            "    refs = set(_REF.findall(reason))\n"
            "    return bool(refs) and refs <= set(closed_ids)\n"
        ),
        "control": ("Finish #0badc0de first.", ()),
    },
    {
        "shape": "status-table",
        "what": "a continue that demands a status table rather than work",
        "where": "wl_judge: an ADVICE_RULES entry, or `basis: out-of-sync` in the judge prompt",
        "source": "import re\n\n_STATUS = re.compile(%r)\n\n\ndef matches(reason, closed_ids=()):\n    del closed_ids\n    return bool(_STATUS.search(reason))\n"
        % _STATUS,
        "control": ("Fix the failing assertion in wl_x.py and rerun the suite.", ()),
    },
    {
        "shape": "rule-breaking",
        "what": "advice a repo rule forbids",
        "where": "wl_judge: a FORBIDDEN_ORDERS entry",
        "source": "import re\n\n_RULE = re.compile(%r)\n\n\ndef matches(reason, closed_ids=()):\n    del closed_ids\n    return bool(_RULE.search(reason))\n"
        % _RULE,
        "control": ("Commit the verified unit with its PR-TASK trailer.", ()),
    },
)


def _shape_of(row):
    text = str(row.get("text") or "")
    if row.get("outcome") == "overruled" and str(row.get("why") or "").startswith("refuted:"):
        return "reraised-finished"
    if row.get("outcome") != "work" and re.search(_RULE, text):
        return "rule-breaking"
    if row.get("outcome") in ("paperwork", "expired", "overruled") and re.search(_STATUS, text):
        return "status-table"
    return None


def judge_shapes(rows, minimum=JUDGE_SHAPE_MIN):
    """[{shape, what, where, ids, samples, rule, test}] for every judge-error shape with at least `minimum` rows; `test` is a pytest module that imports nothing from the repo and passes against `rule`."""
    groups: dict[str, list] = {}
    for row in rows:
        if row.get("kind") != "outcome" or row.get("key") != "judge":
            continue
        shape = _shape_of(row)
        if shape:
            groups.setdefault(shape, []).append(row)
    out = []
    for spec in JUDGE_SHAPES:
        got = groups.get(spec["shape"]) or []
        if len(got) < minimum:
            continue
        samples = [
            (str(r.get("text") or ""), list((r.get("subjects") or {}).get("items") or ()))
            for r in got[:8]
        ]
        ids = [str(r.get("id")) for r in got]
        test = (
            '"""Proposed judge rule `%s` (%s), from effort-outcomes rows %s. Generated by wl_effort_tune.judge_shapes."""\n\n'
            "%s\n\nSAMPLES = %r\nCONTROL = %r\n\n\n"
            "def test_the_rule_matches_every_recorded_sample():\n"
            "    for reason, closed in SAMPLES:\n"
            "        assert matches(reason, closed), reason\n\n\n"
            "def test_the_control_stays_unmatched():\n"
            "    assert not matches(*CONTROL)\n"
        ) % (
            spec["shape"],
            spec["what"],
            ", ".join(ids[:6]),
            spec["source"].rstrip("\n"),
            samples,
            spec["control"],
        )
        out.append(
            {
                "shape": spec["shape"],
                "what": spec["what"],
                "where": spec["where"],
                "ids": ids,
                "samples": samples,
                "rule": spec["source"],
                "test": test,
            }
        )
    return out


# ---- T5: the gate's view of `tuned` -------------------------------------------------------------


def tuned_problems(table):
    """Every way the table's `tuned` section is wrong: a FLOOR key tuned, a key that is not a row, a missing or bad `tuned_at` / `review_after` / `direction`."""
    if not isinstance(table, dict) or "tuned" not in table:
        return []
    tuned = table.get("tuned")
    if not isinstance(tuned, dict):
        return ["tuned: expected an object of tuned keys"]
    checks: dict[str, Any] = table["checks"] if isinstance(table.get("checks"), dict) else {}
    out = []
    for key, rec in sorted(tuned.items()):
        if key in wl_floor.FLOOR:
            out.append(
                "tuned: %s is a FLOOR key (wl_floor.FLOOR); the tuner never touches the FLOOR" % key
            )
            continue
        if key not in checks:
            out.append("tuned: %s is not a row of checks" % key)
            continue
        if not isinstance(rec, dict):
            out.append("tuned: %s: expected an object" % key)
            continue
        at, after = _parse(rec.get("tuned_at")), _parse(rec.get("review_after"))
        if at is None or after is None:
            out.append("tuned: %s: tuned_at and review_after must be ISO8601Z stamps" % key)
        elif after <= at:
            out.append("tuned: %s: review_after is not after tuned_at" % key)
        if rec.get("direction") not in ("promote", "demote"):
            out.append("tuned: %s: direction must be promote or demote" % key)
    return out


# ---- the ledgers --------------------------------------------------------------------------------


def outcome_rows(root):
    return O.read_rows(O.ledger_path(root))


def proposal_rows(root):
    return O.read_rows(O.proposals_path(root))


def answered(rows, key, to):
    """The newest answer row for (key, the entry it would become), or None: an answered demotion is not asked again."""
    got = None
    for row in rows:
        if row.get("kind") == "answer" and row.get("key") == key and row.get("to") == to:
            got = row
    return got


# ---- T4: the trigger and the brief --------------------------------------------------------------


def _ctx():
    return wl_retro.ctx()


def run_dir(root, me8, epoch):
    return pathlib.Path(root) / "agent" / me8 / RUN_DIR / ("e%s" % epoch)


REQUEST = (
    "EFFORT TUNER DUE (agent/plans/PLAN-stop-hook-effort-tuning.md T4; context epoch %(epoch)s at "
    "%(pct)d%% of auto-compact, asked once per context): run `python3 .claude/hooks/stop/wl_effort_tune.py "
    "brief %(me8)s`, write the checks this context found useful or useless and why, and any judge "
    "errors, to the observations file it names, then spawn the `effort-tuner` agent on %(dir)s; its "
    "patch and evidence stay there for the next session."
)


def request_due(root, session_id):
    """(text, epoch, fraction) when this context has crossed ctx_budget.TUNE_FRACTION and no request was recorded for its epoch; None otherwise, and on any failure."""
    with contextlib.suppress(Exception):
        cb = _ctx()
        state = cb.load_state(session_id)
        frac = cb.used_fraction(state)
        if frac is None or frac < cb.TUNE_FRACTION:
            return None
        me8 = cb.session_slug(session_id)
        epoch = int(state.get("epoch") or 0)
        for row in proposal_rows(root):
            if (
                row.get("kind") == "tuner-request"
                and row.get("session") == me8
                and row.get("epoch") == epoch
            ):
                return None
        text = REQUEST % {
            "epoch": epoch,
            "pct": int(frac * 100),
            "me8": me8,
            "dir": pathlib.PurePosixPath("agent", me8, RUN_DIR, "e%s" % epoch).as_posix(),
        }
        return text, epoch, frac
    return None


def mark_requested(root, session_id, epoch, frac):
    O.append_rows(
        O.proposals_path(root),
        [
            {
                "id": O.new_id("ep"),
                "kind": "tuner-request",
                "session": str(session_id or "")[:8],
                "epoch": epoch,
                "fraction": round(float(frac), 3),
                "at": O.now_stamp(),
            }
        ],
    )


OBSERVATIONS = (
    "# Effort tuner observations, session %s, context epoch %s\n\n"
    "Written by the session before it spawns the effort-tuner agent: the checks this context found\n"
    "useful or useless and why, and any judge errors seen. One line per check key.\n\n"
    "## Useful\n\n## Useless\n\n## Judge errors\n"
)


def brief(root, me8, epoch=None):
    """Create the run directory, write this context's outcome rows to it, and return the brief text."""
    if epoch is None:
        with contextlib.suppress(Exception):
            epoch = int(_ctx().load_state(me8).get("epoch") or 0)
    epoch = int(epoch or 0)
    out = run_dir(root, me8, epoch)
    out.mkdir(parents=True, exist_ok=True)
    mine = [
        r
        for r in outcome_rows(root)
        if r.get("session") == me8 and (r.get("kind") == "operator" or r.get("epoch") == epoch)
    ]
    (out / "context-rows.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in mine), encoding="utf-8"
    )
    obs = out / "observations.md"
    if not obs.is_file():
        obs.write_text(OBSERVATIONS % (me8, epoch), encoding="utf-8")
    per: dict[str, list[str]] = {}
    for r in mine:
        if r.get("kind") == "outcome":
            per.setdefault(r["key"], []).append(r["outcome"])
    rel = out.relative_to(pathlib.Path(root)).as_posix()
    lines = [
        "EFFORT TUNER BRIEF, session %s, context epoch %d: %d outcome row(s) in this context."
        % (me8, epoch, len(mine)),
        *(
            "  %-24s %s" % (k, ", ".join("%s %d" % (o, v.count(o)) for o in O.OUTCOMES if o in v))
            for k, v in sorted(per.items())
        ),
        "Rows:          %s/context-rows.jsonl" % rel,
        "Observations:  %s/observations.md  (write them now, before spawning)" % rel,
        "Spawn:         the `effort-tuner` agent with the prompt `run %s %d` and the observations above."
        % (me8, epoch),
        "It writes %s/effort.json.patch, evidence.md and run.json; then `python3 .claude/hooks/stop/wl_effort_tune.py apply %s %s` applies promotions and prints the one /ask for demotions."
        % (rel, me8, rel),
    ]
    return "\n".join(lines)


# ---- T3/T4: the run -----------------------------------------------------------------------------


def run(root, me8, epoch, now=None, window_days=WINDOW_DAYS, rows=None, table=None, out=None):
    """Compute the candidate table from the ledger, test it, and write effort.json.patch, evidence.md, run.json and the judge-rule tests under the run directory. Returns run.json's content."""
    now = now or _now()
    if table is None:
        table, old_text = read_table(root)
    else:
        old_text = render(table)
    if table is None:
        raise ValueError("%s is unreadable" % wl_effort.TABLE_REL)
    rows = outcome_rows(root) if rows is None else rows
    out = pathlib.Path(out) if out else run_dir(root, me8, epoch)
    out.mkdir(parents=True, exist_ok=True)
    st = stats(rows, now, window_days, table)
    changes = candidates(table, st, now)
    new = apply_changes(table, changes, now)
    patch = diff(old_text, render(new))
    blocking, advisory = wl_effort.produced_keys()
    gate = wl_effort.table_problems(new, blocking, advisory) + tuned_problems(new)
    moved = replay(rows, table, new)
    shapes = judge_shapes(rows)
    dead = dead_keys(table, rows, now, window_days)
    due = review_due(table, now)
    (out / "effort.json.patch").write_text(patch, encoding="utf-8")
    rules_dir = out / "judge-rules"
    for sh in shapes:
        rules_dir.mkdir(exist_ok=True)
        (rules_dir / ("test_judge_rule_%s.py" % sh["shape"].replace("-", "_"))).write_text(
            sh["test"], encoding="utf-8"
        )
    observations = ""
    with contextlib.suppress(OSError):
        observations = (out / "observations.md").read_text(encoding="utf-8")
    doc = {
        "session": me8,
        "epoch": epoch,
        "at": _stamp(now),
        "window_days": window_days,
        "rows": len(rows),
        "changes": changes,
        "gate": gate,
        "replay": moved,
        "dead": dead,
        "review_due": due,
        "judge_rules": [{k: v for k, v in sh.items() if k != "test"} for sh in shapes],
    }
    (out / "run.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (out / "evidence.md").write_text(evidence_md(doc, st, observations), encoding="utf-8")
    return doc


def _counts(c):
    p = precision(c)
    return "%d (w%d p%d o%d e%d)%s" % (
        c["rows"],
        c["work"],
        c["paperwork"],
        c["overruled"],
        c["expired"],
        " %.2f" % p if p is not None else "",
    )


def evidence_md(doc, st, observations=""):
    lines = [
        "# Effort tuner run, session %s, context epoch %s (%s)"
        % (doc["session"], doc["epoch"], doc["at"]),
        "",
        "Window: %d day(s), %d ledger row(s). Columns: rows (work, paperwork, overruled, expired) precision."
        % (doc["window_days"], doc["rows"]),
        "",
        "| key | block | advise | off | quiet before a miss |",
        "|---|---|---|---|---|",
    ]
    for key in sorted(st):
        s = st[key]
        lines.append(
            "| %s | %s | %s | %s | %d |"
            % (key, _counts(s["block"]), _counts(s["advise"]), _counts(s["off"]), s["miss_quiet"])
        )
    lines += ["", "## Candidate changes", ""]
    for ch in doc["changes"]:
        lines.append(
            "- %s %s: %s -> %s. %s. Rows: %s"
            % (
                ch["direction"],
                ch["key"],
                json.dumps(ch["from"]),
                json.dumps(ch["to"]),
                ch["reason"],
                ", ".join(ch["ids"]),
            )
        )
    if not doc["changes"]:
        lines.append("- none: no key cleared the thresholds")
    lines += ["", "## The candidate table against the effort-table rule", ""]
    lines += ["- %s" % p for p in doc["gate"]] or ["- clean"]
    lines += ["", "## Replay: recorded emissions whose verdict changes", ""]
    lines += [
        "- session %s epoch %s stop %s: %s at %s %s -> %s (was %s, %s)" % r for r in doc["replay"]
    ] or ["- none"]
    lines += ["", "## Dead keys (no row in a window of at least %d stops)" % DEAD_MIN_STOPS, ""]
    lines += ["- %s" % k for k in doc["dead"]] or ["- none, or the window is too thin to say"]
    lines += ["", "## Tuned keys due for review", ""]
    lines += ["- %s" % k for k in doc["review_due"]] or ["- none"]
    lines += ["", "## Proposed judge rules", ""]
    for sh in doc["judge_rules"]:
        lines.append(
            "- %s (%s), %d row(s): %s; test judge-rules/test_judge_rule_%s.py"
            % (sh["shape"], sh["what"], len(sh["ids"]), sh["where"], sh["shape"].replace("-", "_"))
        )
    if not doc["judge_rules"]:
        lines.append("- none")
    if observations.strip():
        lines += ["", "## The session's observations", "", observations.strip()]
    return "\n".join(lines) + "\n"


# ---- T5: apply, ask, answer ---------------------------------------------------------------------


def apply(root, me8, run_path, now=None):
    """Write the run's promotions to effort.json and report each; record its demotions as pending and write ask.json, the one /ask. Returns (report lines, ask payload or None)."""
    now = now or _now()
    run_path = pathlib.Path(run_path)
    if not run_path.is_absolute():
        run_path = pathlib.Path(root) / run_path
    doc = json.loads((run_path / "run.json").read_text(encoding="utf-8"))
    table, _text = read_table(root)
    if table is None:
        raise ValueError("%s is unreadable" % wl_effort.TABLE_REL)
    report, rows = [], []
    promos = [
        c for c in doc["changes"] if c["direction"] == "promote" and _stricter(c["from"], c["to"])
    ]
    live = [
        c for c in promos if tunable(c["key"], table) and table["checks"][c["key"]] == c["from"]
    ]
    if live:
        new = apply_changes(table, live, now)
        problems = _gate(new)
        if problems:
            raise ValueError(
                "the promoted table fails the effort-table rule: %s" % "; ".join(problems[:3])
            )
        write_table(root, new)
        table = new
        for c in live:
            report.append(
                "effort-tune: promoted %s %s -> %s (%s; rows %s)"
                % (
                    c["key"],
                    json.dumps(c["from"]),
                    json.dumps(c["to"]),
                    c["reason"],
                    ", ".join(c["ids"][:6]),
                )
            )
            rows.append(
                {
                    "id": O.new_id("ep"),
                    "kind": "applied",
                    "key": c["key"],
                    "direction": "promote",
                    "from": c["from"],
                    "to": c["to"],
                    "run": run_path.name,
                    "session": me8,
                    "at": _stamp(now),
                }
            )
    prior = proposal_rows(root)
    asks = []
    for c in doc["changes"]:
        if c["direction"] != "demote" or not tunable(c["key"], table):
            continue
        if answered(prior, c["key"], c["to"]):
            report.append(
                "effort-tune: demotion of %s already answered; not asked again" % c["key"]
            )
            continue
        asks.append(c)
        rows.append(
            {
                "id": O.new_id("ep"),
                "kind": "demotion-pending",
                "key": c["key"],
                "from": c["from"],
                "to": c["to"],
                "reason": c["reason"],
                "ids": c["ids"],
                "run": run_path.name,
                "session": me8,
                "at": _stamp(now),
            }
        )
    if rows:
        O.append_rows(O.proposals_path(root), rows)
    payload = ask_payload(asks, run_path, table, me8, now) if asks else None
    if payload:
        (run_path / "ask.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        report.append(
            "effort-tune: %d demotion(s) wait for the operator: ONE /ask, payload %s/ask.json; record each answer with worklist.py --effort-answer %s <key> accept|reject"
            % (len(asks), run_path.as_posix(), me8)
        )
    if not report:
        report.append("effort-tune: nothing to apply")
    return report, payload


def _gate(table):
    blocking, advisory = wl_effort.produced_keys()
    return wl_effort.table_problems(table, blocking, advisory) + tuned_problems(table)


def ask_payload(demotions, run_path, table, me8, now=None):
    """ONE AskUserQuestion call: up to ASK_QUESTIONS questions of up to ASK_OPTIONS demotions each, every option previewing its own diff. A lone demotion is a demote/keep choice; a group is multi-select, and an unselected key is a rejection."""
    old = render(table)

    def preview(c):
        return diff(old, render(apply_changes(table, [c], now))) or "(no change)"

    groups = [demotions[i : i + ASK_OPTIONS] for i in range(0, len(demotions), ASK_OPTIONS)][
        :ASK_QUESTIONS
    ]
    questions = []
    for n, group in enumerate(groups, 1):
        if len(group) == 1:
            c = group[0]
            questions.append(
                {
                    "question": "Demote the effort check %s? %s." % (c["key"], c["reason"]),
                    "header": "Demote %d" % n,
                    "multiSelect": False,
                    "options": [
                        {
                            "label": "Demote %s" % c["key"],
                            "description": "%s -> %s"
                            % (json.dumps(c["from"]), json.dumps(c["to"])),
                            "preview": preview(c),
                        },
                        {
                            "label": "Keep %s" % c["key"],
                            "description": "the threshold stays; the answer is recorded and not asked again",
                            "preview": "(no change)",
                        },
                    ],
                }
            )
        else:
            questions.append(
                {
                    "question": "Which of these effort checks should be demoted? Unselected ones keep their threshold. Diff: %s/effort.json.patch"
                    % run_path.as_posix(),
                    "header": "Demotions %d" % n,
                    "multiSelect": True,
                    "options": [
                        {
                            "label": c["key"],
                            "description": "%s -> %s: %s"
                            % (json.dumps(c["from"]), json.dumps(c["to"]), c["reason"]),
                            "preview": preview(c),
                        }
                        for c in group
                    ],
                }
            )
    return {
        "tool": "AskUserQuestion",
        "questions": questions,
        "record": [
            "worklist.py --effort-answer %s %s accept|reject" % (me8, c["key"])
            for c in demotions[: ASK_OPTIONS * ASK_QUESTIONS]
        ],
    }


def answer(root, me8, key, decision, note="", now=None):
    """Record the operator's answer to a pending demotion of `key`; `accept` writes it to effort.json. Returns the report line."""
    now = now or _now()
    table, _text = read_table(root)
    if table is None:
        raise ValueError("%s is unreadable" % wl_effort.TABLE_REL)
    if key in wl_floor.FLOOR:
        raise ValueError("%s is a FLOOR key; the tuner never touches the FLOOR" % key)
    rows = proposal_rows(root)
    pending = [r for r in rows if r.get("kind") == "demotion-pending" and r.get("key") == key]
    if not pending:
        raise ValueError("no pending demotion of %s; `wl_effort_tune.py apply` records them" % key)
    last = pending[-1]
    if answered(rows, key, last.get("to")):
        raise ValueError(
            "the demotion of %s to %s is already answered" % (key, json.dumps(last.get("to")))
        )
    line = "effort-tune: %s recorded the operator's %s of the demotion of %s" % (me8, decision, key)
    if decision == "accept":
        if table["checks"].get(key) != last.get("from"):
            raise ValueError(
                "%s changed since the run (%s, expected %s); run the tuner again"
                % (key, json.dumps(table["checks"].get(key)), json.dumps(last.get("from")))
            )
        change = _change(
            key,
            "demote",
            last["from"],
            last["to"],
            last.get("reason", ""),
            last.get("ids") or [],
            None,
        )
        new = apply_changes(table, [change], now)
        problems = _gate(new)
        if problems:
            raise ValueError(
                "the demoted table fails the effort-table rule: %s" % "; ".join(problems[:3])
            )
        write_table(root, new)
        line += ": %s -> %s" % (json.dumps(last["from"]), json.dumps(last["to"]))
    O.append_rows(
        O.proposals_path(root),
        [
            {
                "id": O.new_id("ep"),
                "kind": "answer",
                "key": key,
                "to": last.get("to"),
                "decision": decision,
                "note": note[:300],
                "run": last.get("run"),
                "session": me8,
                "at": _stamp(now),
            }
        ],
    )
    return line


# ---- T2: proposals ------------------------------------------------------------------------------


def propose(root, me8, key, spec, evidence, now=None):
    """Append one proposal row. Raises ValueError, naming the defect, for a FLOOR key, an unknown key, a bad spec, or evidence that cites no outcome row of `key` by id or gives no count."""
    key = wl_floor.base(key)
    if key in wl_floor.FLOOR:
        raise ValueError("%s is a FLOOR key (wl_floor.FLOOR): no proposal may tune it" % key)
    table, _text = read_table(root)
    if not tunable(key, table):
        raise ValueError("%s is not a row of %s" % (key, wl_effort.TABLE_REL))
    m = _SPEC.match(spec or "")
    if not m:
        raise ValueError("expected <block|advise|off>@<level>, got %r" % spec)
    cites = sorted(set(_ROW_ID.findall(evidence or "")))
    if not cites:
        raise ValueError(
            "the evidence cites no outcome row: name rows of %s by id (eo-xxxxxxxx) from %s"
            % (key, "/".join(O.LEDGER_REL))
        )
    known = {str(r.get("id")): wl_floor.base(r.get("key") or "") for r in outcome_rows(root)}
    wrong = [c for c in cites if known.get(c) != key]
    if wrong:
        raise ValueError("cited row(s) %s are not outcome rows of %s" % (", ".join(wrong), key))
    if not _COUNT.search(evidence):
        raise ValueError(
            "the evidence gives no count: say how many rows, e.g. `2/14 led to work` or `n=14`"
        )
    row = {
        "id": O.new_id("ep"),
        "kind": "proposal",
        "key": key,
        "to": {"verdict": m.group(1), "level": m.group(2)},
        "evidence": evidence[:600],
        "cites": cites,
        "session": me8,
        "at": _stamp(now or _now()),
    }
    O.append_rows(O.proposals_path(root), [row])
    return row


def summary(root):
    """The listing mode of both verbs: recorded proposals and answers, and the pending demotions."""
    rows = proposal_rows(root)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r.get("kind")] = kinds.get(r.get("kind"), 0) + 1
    pend = [
        r["key"]
        for r in rows
        if r.get("kind") == "demotion-pending" and not answered(rows, r.get("key"), r.get("to"))
    ]
    return (
        "effort proposals: %d recorded, %d answer(s), %d promotion(s) applied; pending demotions: %s"
        % (
            kinds.get("proposal", 0),
            kinds.get("answer", 0),
            kinds.get("applied", 0),
            ", ".join(sorted(set(pend))) or "none",
        )
    )


def cli(argv, root, identity):
    """`--effort-propose <me> [<key> <verdict>@<level> <evidence...>]` and `--effort-answer <me> [<key> accept|reject [note...]]`, dispatched from worklist.py. `identity(me, die)` is worklist.py's identity check. Returns the exit code."""

    def die(msg, rc=2):
        print(msg, file=sys.stderr)
        raise SystemExit(rc)

    verb, rest = argv[0], argv[1:]
    if not rest:
        die("usage: worklist.py %s <me> ..." % verb)
    me = rest[0]
    identity(me, die)
    me8 = me[:8]
    if len(rest) == 1:
        print(summary(root))
        return 0
    try:
        if verb == "--effort-propose":
            if len(rest) < 4:
                die(
                    "usage: worklist.py --effort-propose <me> <key> <block|advise|off>@<level> <evidence...>"
                )
            row = propose(root, me8, rest[1], rest[2], " ".join(rest[3:]))
            print(
                "effort proposal %s: %s -> %s@%s, citing %s"
                % (
                    row["id"],
                    row["key"],
                    row["to"]["verdict"],
                    row["to"]["level"],
                    ", ".join(row["cites"]),
                )
            )
            return 0
        if len(rest) < 3 or rest[2] not in ("accept", "reject"):
            die("usage: worklist.py --effort-answer <me> <key> accept|reject [note...]")
        print(answer(root, me8, rest[1], rest[2], " ".join(rest[3:])))
        return 0
    except ValueError as exc:
        die("refused: %s" % exc, 1)
    return 0


def main(argv):
    """`brief <me8> [epoch]`, `run <me8> <epoch> [--window-days N]`, `apply <me8> <run dir>`. The root is the repository this file sits in."""
    root = pathlib.Path(__file__).resolve().parents[3]
    if len(argv) >= 2 and argv[0] == "brief":
        print(brief(root, argv[1], int(argv[2]) if len(argv) > 2 else None))
        return 0
    if len(argv) >= 3 and argv[0] == "run":
        days = (
            int(argv[argv.index("--window-days") + 1]) if "--window-days" in argv else WINDOW_DAYS
        )
        doc = run(root, argv[1], int(argv[2]), window_days=days)
        out = run_dir(root, argv[1], int(argv[2])).relative_to(root).as_posix()
        print(
            "effort-tune run: %d change(s) (%d promote, %d demote), gate %s, %d replayed emission(s) change, %d dead key(s), %d judge rule(s). Files: %s/{effort.json.patch,evidence.md,run.json}"
            % (
                len(doc["changes"]),
                sum(c["direction"] == "promote" for c in doc["changes"]),
                sum(c["direction"] == "demote" for c in doc["changes"]),
                "clean" if not doc["gate"] else "%d problem(s)" % len(doc["gate"]),
                len(doc["replay"]),
                len(doc["dead"]),
                len(doc["judge_rules"]),
                out,
            )
        )
        return 1 if doc["gate"] else 0
    if len(argv) >= 3 and argv[0] == "apply":
        report, _payload = apply(root, argv[1], argv[2])
        print("\n".join(report))
        return 0
    print(main.__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
