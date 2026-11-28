"""wl_schedred: a red scheduled workflow on main reaches an agent session, and exactly one session owns it (agent/plans/PLAN-scheduled-red-detector.md, Part A).

WHY THIS EXISTS. Console CI's nightly went red five nights running and Housekeeping four, and no agent saw either: the mail a human gets reaches nobody else, the CI-read guards refuse every raw read of the runs list, and `ci-trace.py` listed only Console CI runs. The red held the stable promotion (the promote-stable soak counts only scheduled runs) while every session stopped clean.

WHAT IT READS, AND HOW OFTEN.
- `scheduled_workflows(root)` discovers the workflows from `.github/workflows/*.y*ml`: any uncommented `schedule:` key with `cron:` entries. Never a hardcoded list, so a sixth scheduled workflow is watched the day it lands.
- `refresh()` makes ONE `actions/runs?event=schedule&branch=main` call for the newest page of scheduled runs, one per-workflow fallback call for a workflow missing from that page (the monthly vm-bake), and one `jobs` call per red run, cached per (run, attempt) so a red that sits for a week costs its jobs read once.
- The page is read WITHOUT a `status=completed` filter, which is the one departure from the plan's sketch: an unfiltered page is what lets a re-run attempt that is still in progress be reported as `in_flight` instead of vanishing, and the verdict still comes from the newest COMPLETED run. The fallback call keeps the filter, because there only the verdict is wanted.

THE VERDICT. The newest completed `event == schedule` run per workflow, at its latest attempt (the runs API already reports the latest attempt's conclusion). Only `success` is green; `cancelled`, `timed_out`, `startup_failure`, `skipped` and anything else are red, because each one is a night the scheduled run did not prove main healthy. A green `workflow_dispatch` run never clears a red, since the soak counts only scheduled runs and the read filters on `event=schedule`; a green re-run attempt of the red run does clear it.

THE CACHE IS SHARED. `<worklist>.schedred` beside the worklist, written atomically, read by every session in the repo, by SessionStart (cache only, zero network) and by `ci-trace.py --scheduled` (which forces a refresh and so writes it for everyone). TTL `WORKLIST_SCHED_RED_TTL_S` (900 s); an unreadable result is cached for ERROR_TTL_S so a GitHub outage costs one call per five minutes, not one per stop. With no origin slug the state is `unset`, and with no scheduled workflow discovered the answer is an empty `ok`; both make ZERO calls, which is what keeps the Stop fixtures offline.

OWNERSHIP, without a message bus. An open `[ ]`/`[>]`/`[?]` item that `tracks()` the red belongs to its owner, and the `open-items` blocker already holds that owner. With no such item, a claim file (`<worklist>.schedred-claim-<stem>`, created with O_EXCL) picks ONE session to be blocked; every other session gets a once-per-run advisory. A claim goes stale when its run id is not the current red's, or when its claimant's session brief is older than SESSION_BRIEF_STALE_MIN, so a dead claimant hands the red on after 90 minutes.

Never raises into the Stop hook: every read failure is an `unreadable` answer, because a GitHub outage is not a reason to wedge a stop.

CONSOLE CI'S NEWEST PUSH RUN ON MAIN IS WATCHED THE SAME WAY (`doc["push"]`). PR #595 merged as 185fde683 on 2026-10-06 and Console CI on main (run 37394654719) then went red twice: Validate Promotion stopped at its 15 min budget, CI Complete and Pipeline Sentinel failing behind it. The merging session's only record was a release item that named the run id beside "then Release to Edge", nothing at the Stop hook read
main's push runs, and the operator found the reds by opening GitHub. Every CI read in the hook is scoped to a PR head, and main after a merge is on no PR, so the push run is read here with the scheduled ones: one `actions/workflows/ci.yml/runs?event=push&branch=main` call under the same TTL, the same claim, the same block. A red row carries its ROOT CAUSE from `ci_diagnose.diagnose` (the job to read, its
cancel cause and category, read once per run attempt and cached), so the block names Validate Promotion and `timeout-cancel`, never the sentinel. Its tracking token is `push:ci` or `run:<id>`; a BARE run id does not track it, because the release item that named run 37394654719 in passing would otherwise have silenced exactly the red it was blind to.
"""

import contextlib
import datetime
import json
import os
import pathlib
import re
import time

import wl_ci
import wl_core as C
import wl_gh

# Fifteen minutes: a scheduled run lands at most a few times a day, and a red that is minutes old costs one stop of delay at worst.
TTL_S = int(os.environ.get("WORKLIST_SCHED_RED_TTL_S", "900"))
# An unreadable answer is cached too, shorter: blindness is reported, never re-paid on every stop.
ERROR_TTL_S = 300
# SessionStart marks a cache older than this as stale rather than presenting a six-hour-old verdict as current.
SESSION_START_STALE_S = 6 * 3600
MAX_JOBS_SHOWN = 6
# 50, not 100: GitHub answers HTTP 502 after about 11 s when it builds a 100-job page of a large run (measured 2026-10-19 on Console CI runs of 141 and 179 jobs), and one page also dropped every job past it.
PAGE = 50
MAX_PAGES = 20
# gh's stderr for a workflow file the per-workflow runs endpoint does not know; it counts as not-on-main only when GitHub's registered-workflow list lacks the file too.
NOT_ON_MAIN_MARK = "(HTTP 404)"
WORKFLOW_DIR = pathlib.Path(".github") / "workflows"

# The tracking vocabulary. A display name counts only beside one of these words, so "fix Console CI lint" (a PR red) never reads as tracking the nightly.
_SCHED_WORDS = re.compile(r"\b(?:nightly|scheduled|schedule)\b", re.IGNORECASE)
_RUN_TOKEN = re.compile(r"(?<!\d)(\d{6,})(?!\d)")
_OPEN_STATES = (" ", ">", "?")

# What a red blocks, by workflow stem: the weekly fleet run is the test evidence the stable promotion waives its soak on; every other scheduled workflow is main's own hygiene.
_BLOCKS = {
    "ci": "the weekly fleet run (the 5-OS stock-image fleet and the full union), which is the test evidence the stable promotion waives its soak on",
}
_BLOCKS_DEFAULT = "main hygiene (this workflow's scheduled job is not running clean)"

# Console CI's push runs on main: the run every merge starts, which the release (CD) waits on.
PUSH_FILE = "ci.yml"
PUSH_STEM = "ci-push"
PUSH_MARK = "push:ci"
PUSH_PAGE = 5
_BLOCKS_PUSH = (
    "the release of the merged commit (CD promotes only after Console CI on main is green), "
    "and every later merge lands on a red main"
)


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


def read_cache(worklist):
    """The shared cache document, or None when absent or corrupt. No network, by contract."""
    doc = wl_gh.cache_load(cache_path(worklist))
    if doc is None or not isinstance(doc.get("workflows"), list):
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


_NAMED_RUN = re.compile(r"\brun:(\d{6,})")


def _newer_than_named(run_id, text):
    """True when `run_id` is the newest of every `run:<id>` the item names, or newer (or it names none). EQUAL counts: a re-attempt keeps its run id, so the named red turning green on attempt 2 is that run's own green.

    ONLY A NEWER GREEN ENDS A RED (operator ruling 2026-10-04). GitHub run ids only grow, so this needs no extra read. On 2026-10-06 at 13:48Z GitHub answered the newest-completed-scheduled-run query for ops-housekeeping.yml with run 29228880755, a green of 2026-07-13, while its real newest run 37446403488 was red, and the hook offered that July green as the tick evidence for #5f43e8c8 (`run:37111522524`).
    """
    named = [int(m) for m in _NAMED_RUN.findall(text or "")]
    rid = _int_or_none(run_id)
    return not named or (rid is not None and rid >= max(named))


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
    """([failed job name, ...], error), across every page; a job is failed when it completed with anything but success, skipped or neutral."""
    out = []
    seen = 0
    for page in range(1, MAX_PAGES + 1):
        data, err = wl_gh.call(
            [
                "api",
                "repos/%s/%s/actions/runs/%s/jobs?per_page=%d&page=%d"
                % (owner, name, run_id, PAGE, page),
            ],
            cwd=root,
        )
        if err or not isinstance(data, dict):
            return [], err or "no jobs document"
        batch = data.get("jobs") or []
        seen += len(batch)
        for job in batch:
            c = job.get("conclusion")
            if c and c not in ("success", "skipped", "neutral"):
                out.append(str(job.get("name") or "?"))
        total = data.get("total_count")
        if isinstance(total, int) and seen >= total:
            return out, ""
        if len(batch) < PAGE:
            # A short page is the end only when the API names no larger total (review 4cfc4023.1).
            if isinstance(total, int):
                return [], "jobs of run %s: page %d was short at %d of %d" % (
                    run_id,
                    page,
                    seen,
                    total,
                )
            return out, ""
    # The walk ran out of pages before the list did: a partial answer is an error, not a verdict (review a3aea1df.2).
    return [], "more than %d jobs in run %s; the walk stopped at %d pages" % (
        PAGE * MAX_PAGES,
        run_id,
        MAX_PAGES,
    )


def _registered_files(root, owner, name):
    """The set of workflow files GitHub has registered for the repo, or None when the list cannot be read. It is read through the Actions permission the runs read already holds, once per refresh, so it can neither be denied where the runs read was allowed (review bebb89ad.1) nor cost one call per workflow (bebb89ad.2)."""
    docs, err = wl_gh.call_list(
        ["api", "repos/%s/%s/actions/workflows?per_page=100" % (owner, name)],
        cwd=root,
    )
    if err or docs is None:
        return None
    files = set()
    for doc in docs:
        for wf in (doc or {}).get("workflows") or []:
            files.add(pathlib.PurePosixPath(str(wf.get("path") or "")).name)
    return files


def undeclared_rows(by_file, declared_files):
    """One informational row per workflow file that has a scheduled run on main and no uncommented `schedule:` in the tree: its newest scheduled run, `undeclared: True`, never red. A schedule deleted from the tree leaves its old runs on main until they age off the page, so this is how the absence is read through the sanctioned verb (`ci-trace.py --scheduled --json`, box L2 of PLAN-retire-nightlies-and-mentions) instead of a raw runs read. `by_file` maps a workflow file name to its scheduled runs."""
    out = []
    for file in sorted(by_file):
        runs = by_file[file]
        if not file or file in declared_files or not runs:
            continue
        newest = _newest(runs)
        stem = pathlib.PurePosixPath(file).stem
        wf = {"stem": stem, "file": file, "name": newest.get("name") or stem, "crons": []}
        row = _run_row(wf, newest if newest.get("status") == "completed" else None, False)
        row["undeclared"] = True
        row["red"] = False
        out.append(row)
    return out


def _fetch(root, owner, name, workflows, jobs_cache):
    """(rows, error, jobs_cache, undeclared). An error string means the verdict could not be read at all."""
    data, err = wl_gh.call(
        [
            "api",
            "repos/%s/%s/actions/runs?event=schedule&branch=main&per_page=%d" % (owner, name, PAGE),
        ],
        cwd=root,
    )
    if err or not isinstance(data, dict):
        return [], err or "no runs document", jobs_cache, []
    by_file: dict[str, list[dict]] = {}
    for run in data.get("workflow_runs") or []:
        if run.get("event") not in (None, "schedule"):
            continue
        by_file.setdefault(_file_of(run), []).append(run)
    rows = []
    new_jobs = {}
    registered = None
    for wf in workflows:
        runs = by_file.get(wf["file"], [])
        done = [r for r in runs if r.get("status") == "completed"]
        if not done:
            # Missing from the page (a monthly workflow), or only in flight there: one narrow call for its newest completed scheduled run.
            more, ferr = wl_gh.call(
                [
                    "api",
                    "repos/%s/%s/actions/workflows/%s/runs?event=schedule&status=completed&per_page=1"
                    % (owner, name, wf["file"]),
                ],
                cwd=root,
            )
            if ferr and NOT_ON_MAIN_MARK in ferr:
                if registered is None:
                    registered = _registered_files(root, owner, name)
                absent = registered is not None and wf["file"] not in registered
            else:
                absent = False
            if absent:
                # A scheduled workflow added on the live branch is not registered on main yet, so it has no scheduled run there; one such file must not blind the whole read (2026-10-24, ops-cf-usage-report.yml hid five red Console CI nightlies).
                row = _run_row(wf, None, False)
                row["not_on_main"] = True
                rows.append(row)
                continue
            if ferr:
                return [], ferr, jobs_cache, []
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
    return rows, "", new_jobs, undeclared_rows(by_file, {wf["file"] for wf in workflows})


def push_workflow(root):
    """The watched push workflow (Console CI, `.github/workflows/ci.yml`) as a row skeleton, or None when the file is absent (every Stop fixture without workflows, so it makes no call)."""
    path = pathlib.Path(root) / WORKFLOW_DIR / PUSH_FILE
    if not path.is_file():
        return None
    try:
        name, _crons = _parse_workflow(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return {
        "stem": PUSH_STEM,
        "file": PUSH_FILE,
        "name": name or "Console CI",
        "crons": [],
        "event": "push",
    }


def _diagnosis(root, owner, name, run_id):
    """({root, root_job, root_conclusion, category, cause, ordered failed_jobs}, ok) for a red push run, through ci_diagnose: the same answer `ci-trace.py --run <id> --why` prints. ok is False when the diagnosis could not be read, so it is not cached."""
    diag = wl_ci._load_diagnose()
    if diag is None:
        return {}, False
    try:
        # The Stop hook's budget: at most two reads and one 2 s pause on a transient 5xx (PLAN-gh-retry G8).
        fetch = diag.GhFetcher(
            "%s/%s" % (owner, name), cwd=str(root), timeout=20, attempts=2, pause=2
        )
        d = diag.diagnose(fetch, run_id)
    except Exception as exc:
        # Not cached (ok False), so the next read tries again; the red's line says why its cause is missing meanwhile.
        return {
            "cause": "the diagnosis could not be read (%s: %s); --why reads it"
            % (type(exc).__name__, str(exc)[:120])
        }, False
    if d.get("verdict") in (None, "unknown"):
        return {}, False
    ff = d.get("first_failure") or {}
    cause = d.get("cause") or {}
    out = {
        "root": ff.get("name") or "",
        "root_job": ff.get("job_id"),
        "root_conclusion": ff.get("conclusion") or "",
        "category": ff.get("category") or "",
        "cause": "%s: %s" % (cause.get("kind"), cause.get("detail"))
        if cause and cause.get("kind") != "unknown"
        else "",
        "verdict": d.get("verdict") or "",
    }
    return out, True


def _fetch_push(root, owner, name, wf, diag_cache):
    """(row or None, error, diag_cache) for Console CI's newest COMPLETED push run on main. One runs call; a red row adds one jobs call and one diagnosis, both cached per (run, attempt)."""
    data, err = wl_gh.call(
        [
            "api",
            "repos/%s/%s/actions/workflows/%s/runs?event=push&branch=main&per_page=%d"
            % (owner, name, wf["file"], PUSH_PAGE),
        ],
        cwd=root,
    )
    if err or not isinstance(data, dict):
        return None, err or "no runs document", diag_cache
    runs = [r for r in data.get("workflow_runs") or [] if r.get("event") in (None, "push")]
    done = [r for r in runs if r.get("status") == "completed"]
    # THE NEWEST COMMIT'S RUNS ARE JUDGED TOGETHER (2026-10-06). One push to main can start two Console CI runs on one SHA, and the later one is a no-op that ends green in about a minute (rediacc_ci.ci.sibling_runs). Taking the newest completed run alone then read that no-op as main's verdict while the original was still running, and kept reading it after the original went red, because the no-op stays the newer run.
    latest = _newest(runs) if runs else None
    sha = str((latest or {}).get("head_sha") or "")
    same = [r for r in runs if sha and str(r.get("head_sha") or "") == sha]
    same_done = [r for r in same if r.get("status") == "completed"]
    same_red = [
        r for r in same_done if r.get("conclusion") not in ("success", "skipped", "neutral")
    ]
    settling = any(r.get("status") != "completed" for r in same)
    cand = _newest(same_done) if same_done else None
    # A still-running run OLDER than the newest completed one is the original the completed no-op stood in for: the SHA is not settled. A running run NEWER than it is the queued duplicate or a retry, and the completed run stands.
    masked = cand is not None and any(
        r.get("status") != "completed"
        and str(r.get("created_at") or "") < str(cand.get("created_at") or "")
        for r in same
    )
    if same_red:
        newest = _newest(same_red)
    elif cand is not None and not masked:
        newest = cand
    else:
        older = [r for r in done if str(r.get("head_sha") or "") != sha]
        newest = _newest(older) if older else (_newest(done) if done and not same else None)
    in_flight = settling or any(
        r.get("status") != "completed"
        and (
            newest is None or str(r.get("created_at") or "") >= str(newest.get("created_at") or "")
        )
        for r in runs
    )
    if newest is None and not runs:
        return None, "", {}
    row = _run_row(wf, newest, in_flight)
    row["sha"] = str((newest or {}).get("head_sha") or "")[:8]
    new_cache = {}
    if row["red"] and row["run_id"]:
        key = "%s:%s" % (row["run_id"], row["attempt"])
        hit = diag_cache.get(key) if isinstance(diag_cache, dict) else None
        if isinstance(hit, dict):
            row.update(hit)
            new_cache[key] = hit
        else:
            failed, _jerr = _failed_jobs(root, owner, name, row["run_id"])
            found, ok = _diagnosis(root, owner, name, row["run_id"])
            found["failed_jobs"] = _roots_first(failed)
            row.update(found)
            if ok:
                new_cache[key] = found
    return row, "", new_cache


def _roots_first(names):
    """Failed job names with aggregators (CI Complete, the sentinels) after the jobs they report on."""
    diag = wl_ci._load_diagnose()
    if diag is None:
        return list(names or [])
    return sorted(names or [], key=lambda n: bool(diag._aggregator(n)))


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
        pushwf = push_workflow(root)
        if not workflows and not pushwf:
            return {"state": "ok", "error": "", "at": now, "workflows": []}
        cached = read_cache(worklist)
        # An unreadable document carries its `error`, so it lives ERROR_TTL_S; an ok one carries "" and lives TTL_S.
        if cached and not force and wl_gh.cache_fresh(cached, TTL_S, ERROR_TTL_S, now):
            return cached
        jobs_cache = (cached or {}).get("jobs") or {}
        if not isinstance(jobs_cache, dict):
            jobs_cache = {}
        rows, err, jobs, undeclared = (
            _fetch(root, owner, name, workflows, jobs_cache) if workflows else ([], "", {}, [])
        )
        if err:
            doc = {
                "state": "unreadable",
                "error": str(err)[:200],
                "at": now,
                # The last known rows ride along for display only; nothing blocks on an unreadable answer.
                "workflows": (cached or {}).get("workflows") or [],
                "undeclared": (cached or {}).get("undeclared") or [],
                "jobs": jobs_cache,
            }
        else:
            doc = {
                "state": "ok",
                "error": "",
                "at": now,
                "workflows": rows,
                "undeclared": undeclared,
                "jobs": jobs,
            }
        # The push read is independent of the scheduled one: either can be unreadable while the other answers.
        doc["push"], doc["push_error"], doc["push_diag"] = None, "", {}
        if pushwf:
            prow, perr, pdiag = _fetch_push(
                root, owner, name, pushwf, (cached or {}).get("push_diag") or {}
            )
            if perr:
                doc["push"] = (cached or {}).get("push")
                doc["push_error"] = str(perr)[:200]
                doc["push_diag"] = (cached or {}).get("push_diag") or {}
            else:
                doc["push"], doc["push_diag"] = prow, pdiag
        wl_gh.cache_write(cache_path(worklist), doc)
        return doc
    except Exception as exc:
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
        data, err = wl_gh.call(
            [
                "api",
                "repos/%s/%s/actions/workflows/%s/runs?event=schedule&per_page=%d"
                % (owner, name, wf["file"], int(limit)),
            ],
            cwd=root,
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
    except Exception as exc:
        return [], "%s: %s" % (type(exc).__name__, str(exc)[:160])


# --------------------------------------------------------------------------- tracking, claims, ownership


def reds(doc):
    """The red rows of an `ok` document; nothing for any other state."""
    if not doc or doc.get("state") != "ok":
        return []
    return [w for w in doc.get("workflows") or [] if w.get("red") and w.get("run_id")]


def _mentions_stem(text, stem):
    if stem == PUSH_STEM:
        return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(PUSH_MARK), text) is not None
    return re.search(r"(?<![\w-])sched:%s(?![\w-])" % re.escape(stem), text) is not None


def _mentions_run_token(text, run_id):
    return (
        run_id is not None and re.search(r"(?<![\w-])run:%d(?!\d)" % int(run_id), text) is not None
    )


def is_push(row):
    return (row or {}).get("event") == "push"


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
    if is_push(row):
        # Only the explicit tokens: a bare run id in a release or watch item is a mention, not ownership of the red (module docstring).
        return _mentions_stem(text, PUSH_STEM) or _mentions_run_token(text, row.get("run_id"))
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
        if (_mentions_run_token if is_push(row) else _mentions_run)(text, row.get("run_id")):
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
        import wl_store as S

        limit = S.SESSION_BRIEF_STALE_MIN * 60.0
        when, _t = S.read_briefs(worklist).get(str(doc["sid8"]), (None, ""))
    # swallowed-failure-ok: False keeps the claim with the session that holds it, the conservative answer when its brief cannot be read; taking a live peer's claim on a guess would race two sessions onto one red.
    except Exception:
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
            doc = wl_gh.load_json(path)
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
    doc = wl_gh.load_json(path)
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


def root_text(row):
    """`<job> (<conclusion>, <category>)` for a push red's root cause, or the failed-job list when no diagnosis was read."""
    if row.get("root"):
        bits = [b for b in (row.get("root_conclusion"), row.get("category")) if b]
        return "%s%s" % (row["root"], " (%s)" % ", ".join(bits) if bits else "")
    return jobs_text(row)


def add_text(row):
    """The worklist line that tracks `row`, single-quote safe for the shell recipe."""
    date = str(row.get("created_at") or "?")[:10]
    if is_push(row):
        text = "%s run:%s -- %s red on main @ %s since %s; root cause: %s" % (
            PUSH_MARK,
            row.get("run_id"),
            row.get("name"),
            row.get("sha") or "?",
            date,
            root_text(row),
        )
        return text.replace("'", "")
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
        "blocks": _BLOCKS_PUSH
        if is_push(row)
        else _BLOCKS.get(row.get("stem") or "", _BLOCKS_DEFAULT),
        "me": me8,
        "add": add_text(row),
        "url": row.get("url") or "",
        "sha": row.get("sha") or "?",
        "root": root_text(row),
        "cause": row.get("cause") or "not attributed; --why reads it",
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
    if not doc:
        return out
    rows = list(doc.get("workflows") or []) if doc.get("state") == "ok" else []
    # The push row is judged on its own read: a scheduled-runs outage does not hide a red main, and an unreadable push read blocks nothing.
    if isinstance(doc.get("push"), dict) and not doc.get("push_error"):
        rows.append(doc["push"])
    for row in rows:
        if not row.get("run_id"):
            continue
        if not row.get("red"):
            if row.get("conclusion") == "success":
                for it in items or ():
                    if (
                        it.get("state") in _OPEN_STATES
                        and C.owned_by_me(it.get("owner"), session_id)
                        and _newer_than_named(row.get("run_id"), str(it.get("text") or ""))
                        and (
                            _mentions_stem(str(it.get("text") or ""), row.get("stem") or "")
                            or (
                                not is_push(row)
                                and _mentions_name(str(it.get("text") or ""), row.get("name") or "")
                            )
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


# --------------------------------------------------------------------------- freshness
# Did GitHub's scheduler FIRE each scheduled workflow on main recently enough (operator ruling 2026-11-21, worklist #5eb28959)? The red verdict above judges the newest run, so a scheduler that stops firing leaves the last verdict standing: rediacc/console ran no workflow at all from 2026-10-30T13:14Z to 2026-11-18T15:20Z and nothing said so. The judgement, the reads and the
# advisory text are `rediacc_ci.ops.sched_freshness` (pure; this module hands it `wl_gh.call`); discovery and the shared cache live here. Its own cache, `<worklist>.schedfresh`, under its own TTL, so the red read's call budget and its tests are untouched.

# An hour: staleness is measured in days, so a fresher read buys nothing.
FRESH_TTL_S = 3600
FRESH_REF = "origin/main"
_DISPATCH_KEY = re.compile(r"\bworkflow_dispatch\b")


def freshness_path(worklist):
    return pathlib.Path("%s.schedfresh" % worklist)


def _git_out(root, args, stdin=None):
    """stdout of `git -C root <args>` (bytes), or None when git fails. Read-only verbs only. A query C.git_cacheable admits is answered from the HEAD-keyed cache."""
    import subprocess

    if stdin is None and C.git_cacheable(args):
        got = C.git_run(root, args, timeout=20)
        return got[1] if got is not None and got[0] == 0 else None

    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            input=stdin,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _wf_entry(path_name, text):
    name, crons = _parse_workflow(text)
    if not crons:
        return None
    stem = path_name.rsplit(".", 1)[0]
    dispatchable = any(_DISPATCH_KEY.search(_strip_comment(ln)) for ln in text.splitlines())
    return {
        "stem": stem,
        "file": path_name,
        "name": name or stem,
        "crons": crons,
        "dispatchable": dispatchable,
    }


def main_scheduled_workflows(root, ref=FRESH_REF):
    """([{stem, file, name, crons, dispatchable}], source) for the scheduled workflows GitHub actually schedules: the files on `ref` (main), read with two git calls (`ls-tree`, then one `cat-file --batch`). With no such ref the working tree stands in and `source` says so, because a branch can rename a workflow or move its cron (2026-11-21: eight renames and Console CI daily -> weekly on the live branch)."""
    listing = _git_out(root, ["ls-tree", ref, "--", str(WORKFLOW_DIR) + "/"])
    if listing is None:
        out = []
        for w in scheduled_workflows(root):
            try:
                text = (pathlib.Path(root) / WORKFLOW_DIR / w["file"]).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            entry = _wf_entry(w["file"], text)
            if entry:
                out.append(entry)
        return out, "working tree (no %s ref)" % ref
    blobs = []
    for line in listing.decode("utf-8", "replace").splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        name = path.rsplit("/", 1)[-1]
        if len(parts) == 3 and parts[1] == "blob" and name.endswith((".yml", ".yaml")):
            blobs.append((name, parts[2]))
    if not blobs:
        return [], ref
    raw = _git_out(
        root, ["cat-file", "--batch"], stdin="".join(s + "\n" for _n, s in blobs).encode()
    )
    if raw is None:
        return [], "%s (cat-file failed)" % ref
    out = []
    pos = 0
    # `cat-file --batch` answers in input order: `<sha> blob <size>` then the bytes and a newline, or `<sha> missing`.
    for name, _sha in blobs:
        nl = raw.index(b"\n", pos)
        header = raw[pos:nl].split()
        if len(header) != 3 or header[1] != b"blob":
            pos = nl + 1
            continue
        size = int(header[2])
        text = raw[nl + 1 : nl + 1 + size].decode("utf-8", "replace")
        pos = nl + 1 + size + 1
        entry = _wf_entry(name, text)
        if entry:
            out.append(entry)
    out.sort(key=lambda w: w["file"])
    return out, ref


def _freshness_module():
    return wl_gh.import_ci("rediacc_ci.ops.sched_freshness")


def read_freshness(worklist):
    """The cached freshness document, or None. Zero network, by contract."""
    doc = wl_gh.cache_load(freshness_path(worklist))
    if doc is None or not isinstance(doc.get("rows"), list):
        return None
    return doc


def refresh_freshness(root, worklist, force=False, now=None):
    """The freshness document, from its cache inside FRESH_TTL_S (an unreadable one inside ERROR_TTL_S), else read from GitHub and cached. `unset` with no origin and an empty `ok` with no scheduled workflow on main, both with zero calls. Never raises: a failure is `unreadable`, never fresh."""
    now = time.time() if now is None else now
    root = pathlib.Path(root)
    try:
        owner, name = wl_ci.repo_slug(root)
        if not owner:
            return {"state": "unset", "error": "", "at": now, "rows": []}
        workflows, source = main_scheduled_workflows(root)
        if not workflows:
            return {"state": "ok", "error": "", "at": now, "rows": [], "source": source}
        cached = read_freshness(worklist)
        if cached and not force and wl_gh.cache_fresh(cached, FRESH_TTL_S, ERROR_TTL_S, now):
            return cached
        fresh_mod = _freshness_module()
        doc = fresh_mod.read(
            lambda argv: wl_gh.call(argv, cwd=root),
            "%s/%s" % (owner, name),
            workflows,
            now,
        )
        doc["source"] = source
        doc["discovered"] = len(workflows)
        wl_gh.cache_write(freshness_path(worklist), doc)
        return doc
    except Exception as exc:
        return {
            "state": "unreadable",
            "error": "%s: %s" % (type(exc).__name__, str(exc)[:160]),
            "at": now,
            "rows": [],
        }


def freshness_advisory(doc, me8="<me>"):
    """The session-addressed advisory for a freshness document ("" when nothing is owed). Never raises."""
    try:
        if not doc or doc.get("state") not in ("ok", "unreadable"):
            return ""
        return _freshness_module().advisory(doc, me8)
    except Exception as exc:
        return (
            "SCHEDULED-RUN FRESHNESS: the advisory could not be rendered (%s: %s); read it by hand: python3 .claude/hooks/stop/wl_schedred.py --freshness"
            % (
                type(exc).__name__,
                str(exc)[:160],
            )
        )


# --------------------------------------------------------------------------- SessionStart


def session_start_line(worklist):
    """One line per red, then the freshness advisory, from the caches alone ("" when there is nothing to say). Zero network calls, by contract."""
    parts = [_red_session_start_line(worklist)]
    try:
        fdoc = read_freshness(worklist)
        if fdoc:
            age_s = max(0.0, time.time() - float(fdoc.get("at") or 0))
            text = freshness_advisory(fdoc)
            if text and age_s > SESSION_START_STALE_S:
                text += "\n  [freshness cache %d h old, stale]" % (age_s // 3600)
            parts.append(text)
    except Exception as exc:
        parts.append("[the freshness cache could not be read (%s: %s)]" % (type(exc).__name__, exc))
    return "\n".join(p for p in parts if p)


def _red_session_start_line(worklist):
    try:
        doc = read_cache(worklist)
    except Exception as exc:
        return (
            "[the scheduled-red cache could not be read (%s: %s), so a red run may be missing here]"
            % (
                type(exc).__name__,
                exc,
            )
        )
    try:
        if not doc:
            return ""
        rows = [w for w in doc.get("workflows") or [] if w.get("red") and w.get("run_id")]
        push = doc.get("push")
        if isinstance(push, dict) and push.get("red") and push.get("run_id"):
            rows.append(push)
        if not rows:
            return ""
        unread = ""
        unread_reason = ""
        try:
            import wl_store as S

            items = S.load(pathlib.Path(worklist), sync=False).items
        except Exception as exc:
            # "untracked" below would be a guess: the line says the worklist went unread.
            items = []
            unread_reason = "%s: %s" % (type(exc).__name__, exc)
            unread = " [the worklist could not be read (%s), so tracked is unknown]" % unread_reason
        age_s = max(0.0, time.time() - float(doc.get("at") or 0))
        stale = unread + (
            " [cache %d h old, stale]" % (age_s // 3600) if age_s > SESSION_START_STALE_S else ""
        )
        import worklist_messages as M

        lines = []
        for row in rows:
            tracked = tracking_items(items, row)
            lines.append(
                (
                    M.CTX_MAIN_PUSH_RED_SESSION_START
                    if is_push(row)
                    else M.CTX_SCHEDULED_RED_SESSION_START
                )
                % dict(
                    fields(row),
                    tracked=(
                        "tracking unknown (worklist unreadable: %s)" % unread_reason
                        if unread_reason
                        else "tracked by #%s" % tracked[0]["id"]
                        if tracked
                        else "untracked"
                    ),
                    stale=stale,
                )
            )
        return "\n".join(lines)
    except Exception as exc:
        return (
            "[the scheduled-red line could not be built from the cache (%s: %s), so a red run may be missing here]"
            % (
                type(exc).__name__,
                exc,
            )
        )


# --------------------------------------------------------------------------- by hand


def _main(argv):
    """`python3 .claude/hooks/stop/wl_schedred.py --freshness [--json]`: a forced freshness read of the repo this file sits in, refreshing the shared cache. Exit 0 every scheduled workflow fresh or waiting, 1 any actionable verdict, 2 unreadable, unset or a blind row."""
    import argparse
    import sys

    ap = argparse.ArgumentParser(prog="wl_schedred.py")
    ap.add_argument("--freshness", action="store_true", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[3]
    doc = refresh_freshness(root, C.worklist_for(root), force=True)
    fresh_mod = _freshness_module()
    rows = doc.get("rows") or []
    if args.json:
        print(json.dumps(doc, indent=2, sort_keys=True))
    else:
        print(
            "Scheduled-run freshness on %s (%s): %d scheduled workflows discovered, %d judged, state %s"
            % (
                doc.get("slug") or "?",
                doc.get("source") or "?",
                int(doc.get("discovered") or 0),
                len(rows),
                doc.get("state"),
            )
        )
        for r in rows:
            last = r.get("last_run_at") or "none"
            print(
                "  %-12s %s (%s)  cron %s  last scheduled run %s  window %s"
                % (
                    r.get("verdict", "?").upper(),
                    r.get("name"),
                    r.get("file"),
                    ", ".join(r.get("crons") or []),
                    last,
                    fresh_mod.age_text(r.get("window_s") or 0) if r.get("window_s") else "?",
                )
            )
        text = freshness_advisory(doc)
        if text:
            print()
            print(text)
    if doc.get("state") != "ok":
        if not args.json:
            print("unreadable: %s" % (doc.get("error") or doc.get("state")), file=sys.stderr)
        return 2
    if fresh_mod.actionable(doc):
        return 1
    if not rows or any(r.get("verdict") == "unreadable" for r in rows):
        return 2
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv[1:]))
