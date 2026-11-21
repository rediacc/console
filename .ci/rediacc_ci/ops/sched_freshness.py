"""Scheduled-run freshness: did GitHub's scheduler fire each scheduled workflow on main recently enough (operator ruling 2026-11-21, worklist #5eb28959).

WHY THIS EXISTS. Between 2026-10-30T13:14Z and 2026-11-18T15:20Z rediacc/console ran NO workflow at all: not one schedule, push, workflow_run or dispatch run in nineteen days, while every workflow in the registry still read `active`. The red reader (`.claude/hooks/stop/wl_schedred.py`) judges the newest scheduled run, so a scheduler that stops firing leaves the last verdict standing forever and nothing says the nights are missing. Nobody noticed for nineteen days. The
ruling: detect it with NO notification to the operator; the session that notices finds the cause and fixes it.

THE VERDICT, per scheduled workflow on main (the file GitHub schedules is main's, never the branch's: on 2026-11-21 the live branch had renamed eight scheduled workflows and moved Console CI's cron from daily to weekly, so a branch-side read judged the wrong files on the wrong period):
- `fresh`       a scheduled run exists newer than the window.
- `stale`       the newest scheduled run (any status, any conclusion: the subject is the scheduler, not the result) is older than the window, or the workflow has never run and was registered longer ago than the window.
- `disabled`    the registry says the workflow is not `active` (`disabled_inactivity`, the 60-day rule; `disabled_manually`; ...). Actionable whatever its last run says.
- `waiting`     never ran, registered inside the window: a new workflow's first night has not come yet. Not a finding.
- `unregistered` main has the file and GitHub's registry does not, so nothing will ever schedule it.
- `bad-cron`    no cron expression of the file parses, so the period is unknown. Reported, never folded into fresh.
- `unreadable`  the read failed. Reported as unchecked, never folded into fresh.

THE WINDOW. `max(48 h, longest gap between two firings + 24 h)`. A daily cron gets 48 h, which is the ruling's number; a six-hourly one also gets 48 h, a weekly one 8 days and a monthly one 32 days (the 31-day month plus a day of grace), so a weekly or monthly workflow is judged on its own period and one dropped firing of it is caught.

THIS MODULE IS PURE. Cron arithmetic, the judgement over already-read data, the reads behind an injected `call(argv) -> (data, error)` and the advisory text. The Stop hook passes `wl_gh.call`, so every `gh` spawn under `.claude/hooks/stop` still goes through its one layer; discovery (main's workflow files, through git) and the shared cache are `wl_schedred`'s. It reads no environment variable.
"""

from __future__ import annotations

import calendar
import datetime
import itertools
from collections.abc import Callable
from typing import Any

HOUR_S = 3600
DAY_S = 24 * HOUR_S
FLOOR_S = 48 * HOUR_S
GRACE_S = 24 * HOUR_S
# Four years from a leap year's start: every month length, both February lengths and every weekday alignment of a day-of-month occur, so a `29 2` cron or a `1 * 1` one is measured on its real worst gap.
HORIZON_START = datetime.date(2024, 1, 1)
HORIZON_DAYS = 4 * 366 + 1
RUNS_PAGE = 100

Call = Callable[[list[str]], tuple[Any, str]]

VERDICTS = ("fresh", "stale", "disabled", "waiting", "unregistered", "bad-cron", "unreadable")
# The verdicts that ask the session to act; `unreadable` is reported separately as blindness.
ACTIONABLE = ("stale", "disabled", "unregistered", "bad-cron")

_FIELDS = (
    ("minute", 0, 59, {}),
    ("hour", 0, 23, {}),
    ("day of month", 1, 31, {}),
    (
        "month",
        1,
        12,
        {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m},
    ),
    (
        "day of week",
        0,
        7,
        {d: i for i, d in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))},
    ),
)


# --------------------------------------------------------------------------- cron


def _value(token: str, low: int, high: int, names: dict, what: str) -> int:
    v = names.get(token.lower()) if names else None
    if v is None:
        if not token.isdigit():
            raise ValueError("%s: %r is not a number" % (what, token))
        v = int(token)
    if not low <= v <= high:
        raise ValueError("%s: %d is outside %d-%d" % (what, v, low, high))
    return v


def _field(text: str, low: int, high: int, names: dict, what: str) -> set[int]:
    out: set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError("%s: empty list item in %r" % (what, text))
        base, _, step_text = part.partition("/")
        step = 1
        if step_text:
            if not step_text.isdigit() or int(step_text) == 0:
                raise ValueError("%s: bad step %r" % (what, step_text))
            step = int(step_text)
        if base == "*":
            lo, hi = low, high
        elif "-" in base:
            a, _, b = base.partition("-")
            lo, hi = _value(a, low, high, names, what), _value(b, low, high, names, what)
            if lo > hi:
                raise ValueError("%s: range %r runs backwards" % (what, base))
        else:
            lo = _value(base, low, high, names, what)
            hi = high if step_text else lo
        out.update(range(lo, hi + 1, step))
    return out


def parse_cron(expr: str) -> dict:
    """{minute, hour, dom, month, dow (sets), dom_any, dow_any} for a five-field POSIX cron. Raises ValueError naming the field that does not parse."""
    parts = str(expr or "").split()
    if len(parts) != 5:
        raise ValueError("%r has %d fields, not 5" % (expr, len(parts)))
    sets = [
        _field(text, low, high, names, what)
        for text, (what, low, high, names) in zip(parts, _FIELDS, strict=True)
    ]
    dow = {0 if d == 7 else d for d in sets[4]}
    return {
        "minute": sets[0],
        "hour": sets[1],
        "dom": sets[2],
        "month": sets[3],
        "dow": dow,
        "dom_any": parts[2] == "*",
        "dow_any": parts[4] == "*",
    }


def _day_matches(spec: dict, day: datetime.date) -> bool:
    if day.month not in spec["month"]:
        return False
    dom_ok = day.day in spec["dom"]
    # date.weekday() is Monday=0; cron is Sunday=0.
    dow_ok = (day.weekday() + 1) % 7 in spec["dow"]
    # Vixie cron: with both day fields restricted, EITHER matching fires the job.
    if not spec["dom_any"] and not spec["dow_any"]:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def max_gap_s(crons: list[str]) -> int:
    """The longest interval, in seconds, between two consecutive firings of the union of `crons` over the horizon. Raises ValueError when no cron parses or nothing fires in the horizon."""
    specs = []
    errors = []
    for expr in crons or ():
        try:
            specs.append(parse_cron(expr))
        except ValueError as exc:
            errors.append(str(exc))
    if not specs:
        raise ValueError("no cron parses: %s" % ("; ".join(errors) or "none declared"))
    firings: list[int] = []
    for offset in range(HORIZON_DAYS):
        day = HORIZON_START + datetime.timedelta(days=offset)
        minutes: set[int] = set()
        for spec in specs:
            if _day_matches(spec, day):
                minutes.update(h * 60 + m for h in spec["hour"] for m in spec["minute"])
        base = offset * 1440
        firings.extend(base + m for m in sorted(minutes))
    if len(firings) < 2:
        raise ValueError("fires fewer than twice in %d days" % HORIZON_DAYS)
    return max(b - a for a, b in itertools.pairwise(firings)) * 60


def window_s(crons: list[str]) -> int:
    """The staleness window for these crons: max(48 h, longest gap + 24 h). Raises ValueError like max_gap_s."""
    return max(FLOOR_S, max_gap_s(crons) + GRACE_S)


# --------------------------------------------------------------------------- time


def parse_iso(text: Any) -> float | None:
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(str(text)).timestamp()
    except ValueError:
        return None


def age_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 2 * HOUR_S:
        return "%d min" % (seconds // 60)
    if seconds < 3 * DAY_S:
        return "%d h" % (seconds // HOUR_S)
    return "%d days" % (seconds // DAY_S)


def _stamp(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%MZ")


# --------------------------------------------------------------------------- judgement


def judge_one(wf: dict, registry: dict | None, last: dict | None, now: float) -> dict:
    """One verdict row. `wf` is {file, name, crons, dispatchable}; `registry` the workflow's registry entry or None when GitHub does not list it; `last` the newest scheduled run ({id, created_at}) or None, or {"error": why} when its read failed."""
    row = {
        "file": wf.get("file") or "?",
        "stem": str(wf.get("file") or "?").rsplit(".", 1)[0],
        "name": wf.get("name") or wf.get("file") or "?",
        "crons": list(wf.get("crons") or []),
        "dispatchable": bool(wf.get("dispatchable")),
        "state": (registry or {}).get("state"),
        "workflow_id": (registry or {}).get("id"),
        "last_run_id": None,
        "last_run_at": None,
        "age_s": None,
        "window_s": None,
        "verdict": "",
        "why": "",
    }
    try:
        row["window_s"] = window_s(row["crons"])
    except ValueError as exc:
        row["verdict"], row["why"] = "bad-cron", str(exc)
        return row
    if registry is None:
        row["verdict"] = "unregistered"
        row["why"] = "main has the file and GitHub's workflow registry does not list it"
        return row
    if row["state"] and row["state"] != "active":
        row["verdict"], row["why"] = "disabled", "registry state %s" % row["state"]
        return row
    if isinstance(last, dict) and last.get("error"):
        row["verdict"], row["why"] = "unreadable", str(last["error"])[:200]
        return row
    created = parse_iso((last or {}).get("created_at"))
    if created is None:
        registered = parse_iso((registry or {}).get("created_at"))
        if registered is not None and now - registered <= row["window_s"]:
            row["verdict"] = "waiting"
            row["why"] = "registered %s ago and its first firing is not due yet" % age_text(
                now - registered
            )
        else:
            row["verdict"], row["why"] = "stale", "no scheduled run on record"
        return row
    row["last_run_id"] = (last or {}).get("id")
    row["last_run_at"] = (last or {}).get("created_at")
    row["age_s"] = int(now - created)
    if row["age_s"] > row["window_s"]:
        row["verdict"] = "stale"
        row["why"] = "newest scheduled run is %s old, past its %s window" % (
            age_text(row["age_s"]),
            age_text(row["window_s"]),
        )
    else:
        row["verdict"] = "fresh"
    return row


def judge(workflows: list[dict], registry: dict, last_runs: dict, now: float) -> list[dict]:
    """Rows for every workflow, in input order. `registry` and `last_runs` are keyed by file name."""
    return [
        judge_one(wf, registry.get(wf.get("file")), last_runs.get(wf.get("file")), now)
        for wf in workflows
    ]


def everything_stale(rows: list[dict]) -> bool:
    """True when at least two workflows were judged and every judged one is stale: the scheduler is off repo-wide, not one workflow."""
    judged = [r for r in rows if r.get("verdict") in ("fresh", "stale")]
    return len(judged) >= 2 and all(r["verdict"] == "stale" for r in judged)


# --------------------------------------------------------------------------- reads


def _file_of(run: dict) -> str:
    return str(run.get("path") or "").split("@", 1)[0].rsplit("/", 1)[-1]


def read(call: Call, slug: str, workflows: list[dict], now: float) -> dict:
    """The freshness document, from GitHub through `call`. Never raises: a failed registry or runs-page read is the whole document `unreadable`; a failed per-workflow fallback makes only that row `unreadable`.

    Calls: one page of the registry (100 workflows; a larger registry is `unreadable`, never half-judged), one page of the newest scheduled runs on main, one fallback per workflow missing from that page (by registry id, so a renamed file cannot 404 it), and one `actions/permissions` read when anything is actionable, which names the repo-wide cause outright."""
    doc: dict[str, Any] = {
        "state": "ok",
        "error": "",
        "at": now,
        "slug": slug,
        "rows": [],
        "actions_enabled": None,
        "actions_error": "",
    }
    try:
        reg_doc, err = call(["api", "repos/%s/actions/workflows?per_page=100" % slug])
        if err or not isinstance(reg_doc, dict):
            return dict(
                doc, state="unreadable", error="workflow registry: %s" % (err or "no document")
            )
        registry = {}
        for entry in reg_doc.get("workflows") or []:
            name = str(entry.get("path") or "").rsplit("/", 1)[-1]
            if name:
                registry[name] = entry
        if int(reg_doc.get("total_count") or 0) > len(reg_doc.get("workflows") or []):
            return dict(
                doc,
                state="unreadable",
                error="workflow registry: %s workflows, one page of 100 read"
                % reg_doc.get("total_count"),
            )
        page, err = call(
            [
                "api",
                "repos/%s/actions/runs?event=schedule&branch=main&per_page=%d" % (slug, RUNS_PAGE),
            ]
        )
        if err or not isinstance(page, dict):
            return dict(
                doc, state="unreadable", error="scheduled runs: %s" % (err or "no document")
            )
        newest: dict[str, dict] = {}
        for run in page.get("workflow_runs") or []:
            if run.get("event") not in (None, "schedule"):
                continue
            f = _file_of(run)
            if f not in newest or str(run.get("created_at") or "") > str(
                newest[f].get("created_at") or ""
            ):
                newest[f] = run
        last_runs: dict[str, dict | None] = {}
        for wf in workflows:
            f = wf.get("file")
            if f in newest:
                last_runs[f] = newest[f]
                continue
            entry = registry.get(f)
            if entry is None:
                last_runs[f] = None
                continue
            more, ferr = call(
                [
                    "api",
                    "repos/%s/actions/workflows/%s/runs?event=schedule&per_page=1"
                    % (slug, entry.get("id") or f),
                ]
            )
            if ferr or not isinstance(more, dict):
                last_runs[f] = {"error": ferr or "no document"}
                continue
            runs = [
                r for r in more.get("workflow_runs") or [] if r.get("event") in (None, "schedule")
            ]
            last_runs[f] = runs[0] if runs else None
        rows = judge(workflows, registry, last_runs, now)
        doc["rows"] = rows
        if any(r["verdict"] in ACTIONABLE for r in rows):
            perm, perr = call(["api", "repos/%s/actions/permissions" % slug])
            if perr or not isinstance(perm, dict) or "enabled" not in perm:
                doc["actions_error"] = str(perr or "no `enabled` field")[:200]
            else:
                doc["actions_enabled"] = bool(perm.get("enabled"))
        return doc
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        # A malformed answer is blindness, never a verdict and never a crash in the Stop hook.
        return dict(doc, state="unreadable", error="%s: %s" % (type(exc).__name__, str(exc)[:160]))


# --------------------------------------------------------------------------- the advisory


def _cron_text(row: dict) -> str:
    return ", ".join(row.get("crons") or []) or "none"


def _row_head(row: dict, now: float) -> str:
    where = "%s (%s), cron %s" % (row["name"], row["file"], _cron_text(row))
    verdict = row["verdict"]
    if verdict == "stale":
        if row.get("last_run_at"):
            return (
                "STALE: %s: no scheduled run on main for %s (window %s; last scheduled run %s, run %s)."
                % (
                    where,
                    age_text(row.get("age_s") or 0),
                    age_text(row.get("window_s") or 0),
                    _stamp(parse_iso(row["last_run_at"]) or now),
                    row.get("last_run_id"),
                )
            )
        return "STALE: %s: no scheduled run on record (window %s)." % (
            where,
            age_text(row.get("window_s") or 0),
        )
    if verdict == "disabled":
        return "DISABLED: %s: GitHub's registry says %s, so its schedule does not fire." % (
            where,
            row.get("state"),
        )
    if verdict == "unregistered":
        return "UNREGISTERED: %s: %s." % (where, row.get("why"))
    if verdict == "bad-cron":
        return "BAD CRON: %s: %s." % (where, row.get("why"))
    return "%s: %s: %s." % (verdict.upper(), where, row.get("why"))


def _row_fix(row: dict, doc: dict) -> list[str]:
    slug = doc.get("slug") or "<owner>/<repo>"
    f = row["file"]
    out = []
    if row["verdict"] == "disabled":
        out.append(
            "    fix: gh workflow enable %s --repo %s (if it was disabled on purpose, the reason is in git log and the worklist; check before enabling)"
            % (f, slug)
        )
    elif row["verdict"] == "unregistered":
        out.append(
            "    find: gh api repos/%s/actions/workflows/%s ; git show origin/main:.github/workflows/%s (a file GitHub cannot parse is not scheduled)"
            % (slug, f, f)
        )
    elif row["verdict"] == "bad-cron":
        out.append(
            "    fix: correct the cron in .github/workflows/%s on main; git show origin/main:.github/workflows/%s shows it"
            % (f, f)
        )
    else:
        out.append(
            "    find, in order: Actions on the repo (above); its registry state %s (disabled_* -> gh workflow enable %s --repo %s); its cron on main (git show origin/main:.github/workflows/%s)"
            % (row.get("state") or "?", f, slug, f)
        )
    if row["verdict"] in ("stale", "disabled") and row.get("dispatchable"):
        out.append(
            "    then run the missed one: gh workflow run %s --repo %s --ref main" % (f, slug)
        )
    return out


def actionable(doc: dict | None) -> list[dict]:
    if not doc or doc.get("state") != "ok":
        return []
    return [r for r in doc.get("rows") or [] if r.get("verdict") in ACTIONABLE]


def advisory(doc: dict | None, me8: str = "<me>", now: float | None = None) -> str:
    """The text the Stop hook (or SessionStart) shows a SESSION: "" when every scheduled workflow is fresh or waiting. An unreadable document is said as unreadable, never as fresh. Addressed to the session that reads it; nothing here notifies the operator."""
    if not doc:
        return ""
    now = float(doc.get("at") or 0) if now is None else now
    slug = doc.get("slug") or "<owner>/<repo>"
    if doc.get("state") == "unreadable":
        return (
            "SCHEDULED-RUN FRESHNESS UNREADABLE (%s): whether GitHub's scheduler is firing is UNCHECKED, not fine. "
            "Read it by hand: python3 .claude/hooks/stop/wl_schedred.py --freshness"
            % (doc.get("error") or "?")
        )
    rows = actionable(doc)
    blind = [r for r in doc.get("rows") or [] if r.get("verdict") == "unreadable"]
    if not rows and not blind:
        return ""
    lines = [
        "SCHEDULED WORKFLOWS NOT FIRING on %s: %d of %d scheduled workflows on main need this session (operator ruling 2026-11-21: the session finds the cause and fixes it; nothing is sent to the operator)."
        % (slug, len(rows), len(doc.get("rows") or []))
    ]
    if rows:
        if doc.get("actions_enabled") is False:
            lines.append(
                "  CAUSE: GitHub Actions is DISABLED for %s (actions/permissions enabled=false), so nothing runs at all."
                % slug
            )
            lines.append(
                "    fix: gh api -X PUT repos/%s/actions/permissions -F enabled=true" % slug
            )
        elif doc.get("actions_enabled") is True:
            lines.append(
                "  Actions on the repo: enabled (actions/permissions read), so the cause is per workflow or account-wide."
            )
        else:
            lines.append(
                "  Actions on the repo: unread (%s); check it first: gh api repos/%s/actions/permissions"
                % (doc.get("actions_error") or "?", slug)
            )
        if everything_stale(doc.get("rows") or []) and doc.get("actions_enabled") is not False:
            lines.append(
                "  EVERY judged workflow is stale at once: the scheduler is off repo-wide, not one file. With Actions enabled, read the account's Actions billing and spending limit (gh api /users/%s/settings/billing/actions or /orgs/%s/settings/billing/actions) and https://www.githubstatus.com."
                % (slug.split("/", 1)[0], slug.split("/", 1)[0])
            )
    for row in rows:
        lines.append("  " + _row_head(row, now))
        lines.extend(_row_fix(row, doc))
    lines.extend(
        "  UNCHECKED: %s (%s): %s" % (row["name"], row["file"], row.get("why")) for row in blind
    )
    lines.append(
        "  Track it: .claude/hooks/stop/worklist.py --add %s 'sched-stale:%s -- scheduled workflows not firing on main: %s'"
        % (
            me8,
            ",".join(r["stem"] for r in rows) or "unread",
            ", ".join(r["file"] for r in rows + blind),
        )
    )
    lines.append("  Re-read: python3 .claude/hooks/stop/wl_schedred.py --freshness")
    return "\n".join(lines)
