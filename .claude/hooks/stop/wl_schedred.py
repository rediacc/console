"""wl_schedred: a red scheduled workflow on main reaches an agent session, and exactly one session owns it (agent/plans/PLAN-scheduled-red-detector.md, Part A).

WHY THIS EXISTS. Console CI's nightly went red five nights running and Housekeeping four, and no agent saw either: the rolling `nightly-red` issue and the budget-check comment reach a human, the CI-read guards refuse every raw read of the runs list, and `ci-trace.py` listed only Console CI runs. The red held the stable promotion (the promote-stable soak counts only scheduled runs) while every session stopped clean.

WHAT IT READS, AND HOW OFTEN.
- `scheduled_workflows(root)` discovers the workflows from `.github/workflows/*.y*ml`: any uncommented `schedule:` key with `cron:` entries. Never a hardcoded list, so a sixth scheduled workflow is watched the day it lands.
- `refresh()` makes ONE `actions/runs?event=schedule&branch=main` call for the newest page of scheduled runs, one per-workflow fallback call for a workflow missing from that page (the monthly vm-bake), and one `jobs` call per red run, cached per (run, attempt) so a red that sits for a week costs its jobs read once.
- The page is read WITHOUT a `status=completed` filter, which is the one departure from the plan's sketch: an unfiltered page is what lets a re-run attempt that is still in progress be reported as `in_flight` instead of vanishing, and the verdict still comes from the newest COMPLETED run. The fallback call keeps the filter, because there only the verdict is wanted.

THE VERDICT. The newest completed `event == schedule` run per workflow, at its latest attempt (the runs API already reports the latest attempt's conclusion). Only `success` is green; `cancelled`, `timed_out`, `startup_failure`, `skipped` and anything else are red, because each one is a night the scheduled run did not prove main healthy. A green `workflow_dispatch` run never clears a red, since the soak counts only scheduled runs and the read filters on `event=schedule`; a green re-run attempt of the red run does clear it.

THE CACHE IS SHARED. `<worklist>.schedred` beside the worklist, written atomically, read by every session in the repo, by SessionStart (cache only, zero network) and by `ci-trace.py --scheduled` (which forces a refresh and so writes it for everyone). TTL `WORKLIST_SCHED_RED_TTL_S` (900 s); an unreadable result is cached for ERROR_TTL_S so a GitHub outage costs one call per five minutes, not one per stop. With no origin slug the state is `unset`, and with no scheduled workflow discovered the answer is an empty `ok`; both make ZERO calls, which is what keeps the Stop fixtures offline.

OWNERSHIP, without a message bus. An open `[ ]`/`[>]`/`[?]` item that `tracks()` the red belongs to its owner, and the `open-items` blocker already holds that owner. With no such item, a claim file (`<worklist>.schedred-claim-<stem>`, created with O_EXCL) picks ONE session to be blocked; every other session gets a once-per-run advisory. A claim goes stale when its run id is not the current red's, or when its claimant's session brief is older than SESSION_BRIEF_STALE_MIN, so a dead claimant hands the red on after 90 minutes.

Never raises into the Stop hook: every read failure is an `unreadable` answer, because a GitHub outage is not a reason to wedge a stop.
"""

import contextlib
import datetime
import json
import os
import pathlib
import re
import tempfile
import time

import wl_ci
import wl_core as C

# Fifteen minutes: a scheduled run lands at most a few times a day, and a red that is minutes old costs one stop of delay at worst.
TTL_S = int(os.environ.get("WORKLIST_SCHED_RED_TTL_S", "900"))
# An unreadable answer is cached too, shorter: blindness is reported, never re-paid on every stop.
ERROR_TTL_S = 300
# SessionStart marks a cache older than this as stale rather than presenting a six-hour-old verdict as current.
SESSION_START_STALE_S = 6 * 3600
MAX_JOBS_SHOWN = 6
PAGE = 100
WORKFLOW_DIR = pathlib.Path(".github") / "workflows"

# The tracking vocabulary. A display name counts only beside one of these words, so "fix Console CI lint" (a PR red) never reads as tracking the nightly.
_SCHED_WORDS = re.compile(r"\b(?:nightly|scheduled|schedule)\b", re.IGNORECASE)
_RUN_TOKEN = re.compile(r"(?<!\d)(\d{6,})(?!\d)")
_OPEN_STATES = (" ", ">", "?")

# What a red blocks, by workflow stem: the nightly CI run is the soak the stable promotion counts; every other scheduled workflow is main's own hygiene.
_BLOCKS = {
    "ci": "the stable promotion (promote-stable counts only green scheduled Console CI runs)"
}
_BLOCKS_DEFAULT = "main hygiene (this workflow's scheduled job is not running clean)"


# --------------------------------------------------------------------------- discovery


def _strip_comment(line):
    """`line` without a YAML comment. A `#` starts a comment at the line start or after whitespace; cron values never contain one."""
    m = re.search(r"(^|\s)#", line)
    return line[: m.start()] if m else line


def _parse_workflow(text):
    """(display name or "", [cron, ...]) from one workflow file. Line-based on purpose: the hooks do not depend on PyYAML, and the shape read here (`schedule:` with a `- cron:` list under it) is the one every workflow in this repo uses."""
    name, crons = "", []
    lines = text.splitlines()
    sched_indent = None
    for raw in lines:
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and not name:
            m = re.match(r"name:\s*(.+)$", line)
            if m:
                name = m.group(1).strip().strip("'\"")
        if sched_indent is not None:
            if indent <= sched_indent:
                sched_indent = None
            else:
                m = re.match(r"\s*-?\s*cron:\s*['\"]?([^'\"]+?)['\"]?\s*$", line)
                if m:
                    crons.append(m.group(1).strip())
                continue
        if indent > 0 and re.match(r"\s+['\"]?schedule['\"]?:\s*$", line):
            sched_indent = indent
    return name, crons


def scheduled_workflows(root):
    """Every workflow under `.github/workflows` with an uncommented `schedule:` and at least one cron: [{stem, file, name, crons}], sorted by file."""
    out: list[dict] = []
    wdir = pathlib.Path(root) / WORKFLOW_DIR
    try:
        files = sorted(p for p in wdir.iterdir() if p.suffix in (".yml", ".yaml") and p.is_file())
    except OSError:
        return out
    for path in files:
        try:
            name, crons = _parse_workflow(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if crons:
            out.append(
                {"stem": path.stem, "file": path.name, "name": name or path.stem, "crons": crons}
            )
    return out


# --------------------------------------------------------------------------- cache


def cache_path(worklist):
    return pathlib.Path("%s.schedred" % worklist)


def claim_path(worklist, stem):
    return pathlib.Path("%s.schedred-claim-%s" % (worklist, stem))


def _write_json(path, doc):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_cache(worklist):
    """The shared cache document, or None when absent or corrupt. No network, by contract."""
    doc = _read_json(cache_path(worklist))
    if not isinstance(doc, dict) or not isinstance(doc.get("workflows"), list):
        return None
    return doc


# --------------------------------------------------------------------------- reads


def _file_of(run):
    """The workflow file a runs-API record came from: `path` is `.github/workflows/x.yml`, sometimes suffixed `@refs/...`."""
    return str(run.get("path") or "").split("@", 1)[0].rsplit("/", 1)[-1]


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_row(wf, run, in_flight=False):
    """One workflow's verdict row from its newest completed scheduled run (or None when it never ran)."""
    row = dict(wf)
    row.update(
        {
            "run_id": None,
            "attempt": None,
            "conclusion": None,
            "created_at": None,
            "url": None,
            "failed_jobs": [],
            "red": False,
            "in_flight": bool(in_flight),
        }
    )
    if run:
        conclusion = run.get("conclusion")
        row.update(
            {
                "run_id": _int_or_none(run.get("id")),
                "attempt": _int_or_none(run.get("run_attempt")) or 1,
                "conclusion": conclusion,
                "created_at": run.get("created_at"),
                "url": run.get("html_url"),
                "red": is_red(conclusion),
            }
        )
    return row


def is_red(conclusion):
    """THE RED PREDICATE. Only `success` is green; a completed run with any other conclusion (cancelled included) is red. None (never ran, or still running) is not a verdict."""
    return conclusion is not None and conclusion != "success"


def _newest(runs):
    return max(runs, key=lambda r: (str(r.get("created_at") or ""), _int_or_none(r.get("id")) or 0))


def _failed_jobs(root, owner, name, run_id):
    """([failed job name, ...], error). One call; a job is failed when it completed with anything but success, skipped or neutral."""
    data, err = wl_ci._gh_json(
        root, ["api", "repos/%s/%s/actions/runs/%s/jobs?per_page=%d" % (owner, name, run_id, PAGE)]
    )
    if err or not isinstance(data, dict):
        return [], err or "no jobs document"
    out = []
    for job in data.get("jobs") or []:
        c = job.get("conclusion")
        if c and c not in ("success", "skipped", "neutral"):
            out.append(str(job.get("name") or "?"))
    return out, ""


def _fetch(root, owner, name, workflows, jobs_cache):
    """(rows, error, jobs_cache). An error string means the verdict could not be read at all."""
    data, err = wl_ci._gh_json(
        root,
        [
            "api",
            "repos/%s/%s/actions/runs?event=schedule&branch=main&per_page=%d" % (owner, name, PAGE),
        ],
    )
    if err or not isinstance(data, dict):
        return [], err or "no runs document", jobs_cache
    by_file: dict[str, list[dict]] = {}
    for run in data.get("workflow_runs") or []:
        if run.get("event") not in (None, "schedule"):
            continue
        by_file.setdefault(_file_of(run), []).append(run)
    rows = []
    new_jobs = {}
    for wf in workflows:
        runs = by_file.get(wf["file"], [])
        done = [r for r in runs if r.get("status") == "completed"]
        if not done:
            # Missing from the page (a monthly workflow), or only in flight there: one narrow call for its newest completed scheduled run.
            more, ferr = wl_ci._gh_json(
                root,
                [
                    "api",
                    "repos/%s/%s/actions/workflows/%s/runs?event=schedule&status=completed&per_page=1"
                    % (owner, name, wf["file"]),
                ],
            )
            if ferr:
                return [], ferr, jobs_cache
            done = [
                r
                for r in ((more or {}).get("workflow_runs") or [])
                if r.get("event") in (None, "schedule")
            ]
        newest = _newest(done) if done else None
        in_flight = any(
            r.get("status") != "completed"
            and (
                newest is None
                or str(r.get("created_at") or "") >= str(newest.get("created_at") or "")
            )
            for r in runs
        )
        row = _run_row(wf, newest, in_flight)
        if row["red"] and row["run_id"]:
            key = "%s:%s" % (row["run_id"], row["attempt"])
            if key in jobs_cache:
                row["failed_jobs"] = list(jobs_cache[key])
                new_jobs[key] = jobs_cache[key]
            else:
                failed, jerr = _failed_jobs(root, owner, name, row["run_id"])
                row["failed_jobs"] = failed
                if not jerr:
                    new_jobs[key] = failed
        rows.append(row)
    # Only the jobs of runs that are still somebody's newest red are kept: the map cannot grow without bound.
    return rows, "", new_jobs


def refresh(root, worklist, force=False, now=None):
    """The scheduled-run verdict, from the shared cache inside its TTL, else from GitHub (and the cache rewritten). `force` bypasses the TTL. Never raises."""
    now = time.time() if now is None else now
    root = pathlib.Path(root)
    try:
        owner, name = wl_ci.repo_slug(root)
        if not owner:
            return {"state": "unset", "error": "", "at": now, "workflows": []}
        # Nothing scheduled, nothing to read: a tree with no scheduled workflow (every Stop fixture that has an origin but no `.github/workflows`) costs zero calls, so the CI checks' own zero-call opt-out stays true for it.
        workflows = scheduled_workflows(root)
        if not workflows:
            return {"state": "ok", "error": "", "at": now, "workflows": []}
        cached = read_cache(worklist)
        if cached and not force:
            ttl = ERROR_TTL_S if cached.get("state") == "unreadable" else TTL_S
            if now - float(cached.get("at") or 0) <= ttl:
                return cached
        jobs_cache = (cached or {}).get("jobs") or {}
        if not isinstance(jobs_cache, dict):
            jobs_cache = {}
        rows, err, jobs = _fetch(root, owner, name, workflows, jobs_cache)
        if err:
            doc = {
                "state": "unreadable",
                "error": str(err)[:200],
                "at": now,
                # The last known rows ride along for display only; nothing blocks on an unreadable answer.
                "workflows": (cached or {}).get("workflows") or [],
                "jobs": jobs_cache,
            }
        else:
            doc = {"state": "ok", "error": "", "at": now, "workflows": rows, "jobs": jobs}
        _write_json(cache_path(worklist), doc)
        return doc
    except Exception as exc:  # noqa: BLE001 -- information and a bounded block, never a crash
        return {
            "state": "unreadable",
            "error": "%s: %s" % (type(exc).__name__, str(exc)[:160]),
            "at": now,
            "workflows": [],
        }


def recent_runs(root, stem, limit=5):
    """([run row, ...] newest first, error) for one workflow's scheduled runs, in flight included. `stem` may be a stem or a file name. One call."""
    try:
        root = pathlib.Path(root)
        wf = next(
            (w for w in scheduled_workflows(root) if stem in (w["stem"], w["file"])),
            None,
        )
        if wf is None:
            return [], "unknown scheduled workflow: %s" % stem
        owner, name = wl_ci.repo_slug(root)
        if not owner:
            return [], "no origin remote"
        data, err = wl_ci._gh_json(
            root,
            [
                "api",
                "repos/%s/%s/actions/workflows/%s/runs?event=schedule&per_page=%d"
                % (owner, name, wf["file"], int(limit)),
            ],
        )
        if err or not isinstance(data, dict):
            return [], err or "no runs document"
        out = []
        for run in (data.get("workflow_runs") or [])[: int(limit)]:
            done = run.get("status") == "completed"
            # An in-flight run has no verdict yet: its conclusion is blanked so it never reads as red.
            out.append(
                _run_row(wf, run if done else dict(run, conclusion=None), in_flight=not done)
            )
        return out, ""
    except Exception as exc:  # noqa: BLE001
        return [], "%s: %s" % (type(exc).__name__, str(exc)[:160])


# --------------------------------------------------------------------------- tracking, claims, ownership


def reds(doc):
    """The red rows of an `ok` document; nothing for any other state."""
    if not doc or doc.get("state") != "ok":
        return []
    return [w for w in doc.get("workflows") or [] if w.get("red") and w.get("run_id")]


def _mentions_stem(text, stem):
    return re.search(r"(?<![\w-])sched:%s(?![\w-])" % re.escape(stem), text) is not None


def _mentions_run(text, run_id):
    return run_id is not None and re.search(r"(?<!\d)%d(?!\d)" % int(run_id), text) is not None


def _mentions_name(text, name):
    if not name:
        return False
    return (
        re.search(re.escape(name), text, re.IGNORECASE) is not None
        and _SCHED_WORDS.search(text) is not None
    )


def tracks(text, row):
    """THE TRACKING MATCH. True when `text` carries the whole token `sched:<stem>`, the red run's id (bare or `run:<id>`), or the workflow's display name together with nightly/scheduled/schedule. A bare "Console CI" never counts."""
    text = str(text or "")
    return (
        _mentions_stem(text, row.get("stem") or "")
        or _mentions_run(text, row.get("run_id"))
        or _mentions_name(text, row.get("name") or "")
    )


def tracking_items(items, row):
    """Open (`[ ]`, `[>]`, `[?]`) items that track `row`."""
    return [r for r in items or () if r.get("state") in _OPEN_STATES and tracks(r.get("text"), row)]


def _stamp_epoch(stamp):
    dt = C.parse_stamp(str(stamp or "")) if stamp else None
    return dt.timestamp() if dt is not None else None


def _created_epoch(row):
    try:
        s = str(row.get("created_at") or "").replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s).timestamp() if s else None
    except ValueError:
        return None


def covering_ticks(items, row):
    """Done items that close THIS red: they name its run id, or carry `sched:<stem>` and were ticked after the run was created. A tick from an older red's cycle does not cover a newer red."""
    out = []
    created = _created_epoch(row)
    for r in items or ():
        if r.get("state") != "x":
            continue
        text = str(r.get("text") or "")
        if _mentions_run(text, row.get("run_id")):
            out.append(r)
            continue
        if _mentions_stem(text, row.get("stem") or ""):
            upd = _stamp_epoch(r.get("upd"))
            if created is not None and upd is not None and upd >= created:
                out.append(r)
    return out


def _claim_stale(worklist, doc, run_id, now):
    if not isinstance(doc, dict) or doc.get("run") != run_id or not doc.get("sid8"):
        return True
    try:
        import wl_store as S  # noqa: PLC0415 -- only the claim path needs the briefs

        limit = S.SESSION_BRIEF_STALE_MIN * 60.0
        when, _t = S.read_briefs(worklist).get(str(doc["sid8"]), (None, ""))
    except Exception:  # noqa: BLE001
        return False
    if when is not None:
        return (C.utcnow() - when).total_seconds() > limit
    # No brief at all: the claim's own age stands in, so a claimant that never wrote one is not robbed the moment it claims.
    return now - float(doc.get("at") or 0) > limit


def claim(worklist, stem, run_id, me8, now=None):
    """The session prefix that holds the claim on `stem`'s red `run_id`, taking it for `me8` when it is free or stale. O_EXCL create, then a re-read, so two sessions racing for it agree on one winner."""
    now = time.time() if now is None else now
    path = claim_path(worklist, stem)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            doc = _read_json(path)
            if not _claim_stale(worklist, doc, run_id, now):
                return str(doc.get("sid8"))
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        except OSError:
            return ""
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"run": run_id, "sid8": me8, "at": now}, fh)
        break
    doc = _read_json(path)
    return str((doc or {}).get("sid8") or "")


def _age_text(row, now=None):
    created = _created_epoch(row)
    if created is None:
        return "?"
    minutes = max(0, int(((time.time() if now is None else now) - created) // 60))
    if minutes < 120:
        return "%d min" % minutes
    if minutes < 48 * 60:
        return "%d h" % (minutes // 60)
    return "%d days" % (minutes // 1440)


def jobs_text(row):
    jobs = list(row.get("failed_jobs") or [])
    if not jobs:
        return "(no failed job named; the run's conclusion is the verdict)"
    shown = ", ".join(jobs[:MAX_JOBS_SHOWN])
    if len(jobs) > MAX_JOBS_SHOWN:
        shown += " +%d more" % (len(jobs) - MAX_JOBS_SHOWN)
    return shown


def add_text(row):
    """The worklist line that tracks `row`, single-quote safe for the shell recipe."""
    date = str(row.get("created_at") or "?")[:10]
    text = "sched:%s run:%s -- %s red on main since %s; failed: %s" % (
        row.get("stem"),
        row.get("run_id"),
        row.get("name"),
        date,
        jobs_text(row),
    )
    return text.replace("'", "")


def fields(row, me8="<me>"):
    """The keyed fields every scheduled-red message renders from."""
    return {
        "name": row.get("name") or row.get("stem") or "?",
        "stem": row.get("stem") or "?",
        "file": row.get("file") or "?",
        "run": row.get("run_id") or "?",
        "attempt": row.get("attempt") or "?",
        "conclusion": row.get("conclusion") or "?",
        "age": _age_text(row),
        "jobs": jobs_text(row),
        "blocks": _BLOCKS.get(row.get("stem") or "", _BLOCKS_DEFAULT),
        "me": me8,
        "add": add_text(row),
        "url": row.get("url") or "",
    }


def assess(worklist, items, session_id, doc, now=None):
    """What this stop owes for scheduled runs, as {block: [rows], tick: [(row, item)], peer: [(row, holder or item owner)], green: [(row, item)]}.

    - block: untracked reds this session holds the claim on.
    - tick: reds a tick of THIS session claims to have ended without evidence while the newest run is still red.
    - peer: reds owned elsewhere (a peer's item, a peer's bad tick, a peer's claim); one advisory each.
    - green: this session's open items tracking a workflow whose newest scheduled run is now green; the tick command is owed.
    """
    me8 = (session_id or "")[:8]
    out: dict[str, list] = {"block": [], "tick": [], "peer": [], "green": []}
    if not doc or doc.get("state") != "ok":
        return out
    for row in doc.get("workflows") or []:
        if not row.get("run_id"):
            continue
        if not row.get("red"):
            if row.get("conclusion") == "success":
                for it in items or ():
                    if (
                        it.get("state") in _OPEN_STATES
                        and C.owned_by_me(it.get("owner"), session_id)
                        and (
                            _mentions_stem(str(it.get("text") or ""), row.get("stem") or "")
                            or _mentions_name(str(it.get("text") or ""), row.get("name") or "")
                        )
                    ):
                        out["green"].append((row, it))
            continue
        open_items = tracking_items(items, row)
        if open_items:
            if not any(C.owned_by_me(it.get("owner"), session_id) for it in open_items):
                out["peer"].append((row, str(open_items[0].get("owner") or "?")[:8]))
            continue
        ticks = covering_ticks(items, row)
        if ticks:
            # THE TICK RULE, operator ruling 2026-10-04 ("Require a green run"): only a newer green scheduled run ends a red, and that run would make this row green, so a tick of a workflow whose newest scheduled run is still red is never enough -- not even one citing a fix commit already on origin/main. Every such tick fires.
            bad = ticks[-1]
            if C.owned_by_me(bad.get("owner"), session_id):
                out["tick"].append((row, bad))
            else:
                out["peer"].append((row, str(bad.get("owner") or "?")[:8]))
            continue
        holder = claim(worklist, row.get("stem"), row.get("run_id"), me8, now=now)
        if holder and holder == me8:
            out["block"].append(row)
        else:
            out["peer"].append((row, holder or "?"))
    return out


# --------------------------------------------------------------------------- SessionStart


def session_start_line(worklist):
    """One line per red from the cache alone ("" when there is nothing to say). Zero network calls, by contract."""
    try:
        doc = read_cache(worklist)
        if not doc:
            return ""
        rows = [w for w in doc.get("workflows") or [] if w.get("red") and w.get("run_id")]
        if not rows:
            return ""
        try:
            import wl_store as S  # noqa: PLC0415

            items = S.load(pathlib.Path(worklist), sync=False).items
        except Exception:  # noqa: BLE001
            items = []
        age_s = max(0.0, time.time() - float(doc.get("at") or 0))
        stale = (
            " [cache %d h old, stale]" % (age_s // 3600) if age_s > SESSION_START_STALE_S else ""
        )
        import worklist_messages as M  # noqa: PLC0415 -- the catalogue owns the wording

        lines = []
        for row in rows:
            tracked = tracking_items(items, row)
            lines.append(
                M.CTX_SCHEDULED_RED_SESSION_START
                % dict(
                    fields(row),
                    tracked="tracked by #%s" % tracked[0]["id"] if tracked else "untracked",
                    stale=stale,
                )
            )
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""
