#!/usr/bin/env python3
"""ci_diagnose: why a Console CI run is red, cancelled or slow, in a dozen lines instead of dozens of raw `gh` reads.

WHY THIS EXISTS. On 2026-10-02 Console CI run 36953549081 (PR #591, head a7f30558) was cancelled with 104 jobs green, 33 skipped, 29 cancelled and nothing failed. The cause lived on a DIFFERENT run: Watchdog Monitor run 36956399799 annotated `CI BUDGET VIOLATION: 'Tests + Infra / E2E Workers (fedora-43, 1/8)' ran 20.1m (budget 20m)`, and the job's own log showed why: renet's `essentials`
setup phase took 416 s and 916 s on two VMs and logged nothing meanwhile. Reconstructing that took dozens of hand-written `gh api` calls. Every step of that reconstruction is a function here, so the tracer (`.ci/scripts/ci/ci-trace.py`) and the CI-side publisher (`rediacc_ci.ci.publish_ci_verdict`) answer from ONE implementation.

STDLIB ONLY AT IMPORT TIME, NO rediacc_ci IMPORTS. The one exception is `_gh_retry()`, which reaches `rediacc_ci.core.gh_retry` lazily, on the first retried read, so the retry policy has a single home. ci-trace.py loads this file by path (it has no `.ci` hop), and the Stop hook's wl_ci.py loads it lazily for cancel attribution, so an import of the package would break both.

THE FETCH IS INJECTED. Every network-reading function takes a fetcher as its first argument: `GhFetcher` shells out to `gh api` on a workstation, `HttpFetcher` speaks REST with a token on a runner, and the tests pass a dict-backed fake. Nothing in here reaches the network on its own.

THE SCHEMA, `ci-verdict/v1`, is the contract with the publisher and with every session that reads the `CI Verdict` check-run; `diagnose()` builds it and `render()` prints it.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

SCHEMA = "ci-verdict/v1"
GENERATOR = "rediacc_ci.ci.ci_diagnose"
CHECK_NAME = "CI Verdict"
PUBLISH_JOB_NAME = "Publish CI Verdict"
# The PR review's checks (PLAN-github-pr-review-restore): "Claude Review" runs the review, "Review Status" posts the "Review Complete" check-run.
REVIEW_CONTEXTS = ("Review Complete", "Review Status", "Claude Review")
# The review's jobs, which report through Review Complete (a review error reaches the head as its failed-run token) and are never a result of their own. "Review Complete" itself is a required check on main again (operator ruling 2026-10-03), so it is blocking.
REVIEW_JOB_CONTEXTS = ("Review Status", "Claude Review")
# Never a CI result, whatever their conclusion. "CI Verdict" is this module's own published diagnosis, "Publish CI Verdict" is the job that posts it, and REVIEW_JOB_CONTEXTS report through Review Complete. Exact names, never substrings, so Console CI's own "Review Gate" stays blocking.
NONBLOCKING_CONTEXTS = frozenset({CHECK_NAME, PUBLISH_JOB_NAME, *REVIEW_JOB_CONTEXTS})
# The watchdog's own exclusions (WATCHDOG_EXCLUDE_PATTERNS in .github/workflows/watchdog-monitor.yml): aggregators and observers, never the first failure of a Console CI run. All of REVIEW_CONTEXTS stay here, Review Complete included: the review runs in its own workflows after CI, so it observes a Console CI run rather than belonging to it, and its required-check verdict is read by ci-trace and the Stop hook (wl_ci.py), not by the watchdog. Matched as substrings; none of REVIEW_CONTEXTS is a substring of "Review Gate".
WATCHDOG_EXCLUDED = ("Watchdog", "CI Complete", *REVIEW_CONTEXTS)
# DOWNSTREAM OF A VERDICT, never the cause of one. Console CI jobs that read another job's result and fail BECAUSE it failed: every job whose `needs:` holds `ci-complete` in .github/workflows/ci.yml (Pipeline Sentinel, Finalize Release Sentinel, PR Labels) and the install legs' own roll-up. Main push run 37394654719 attempt 2 (2026-10-06) had exactly two failures, CI Complete and Pipeline Sentinel, both reporting a
# Validate Promotion that hit its 15 min timeout, and `--why` named Pipeline Sentinel as the first failure. test_ci_diagnose pins this list against ci.yml's `needs:` graph, so a new downstream job cannot slip in as a root cause. Matched as substrings, like WATCHDOG_EXCLUDED.
DOWNSTREAM_JOBS = (
    "Pipeline Sentinel",
    "Finalize Release Sentinel",
    "PR Labels",
    "Install Methods Complete",
)
AGGREGATORS = (*WATCHDOG_EXCLUDED, *DOWNSTREAM_JOBS)
CAUSE_KINDS = (
    "watchdog-budget",
    "watchdog-failure",
    "superseded",
    "timeout-kill",
    "runner-not-acquired",
    "manual",
    "unknown",
)
# `watchdog-cancel` and `timeout-cancel` name a job that was STOPPED rather than one that failed: the Watchdog Monitor's enforced budget (its `CI BUDGET VIOLATION: '<job>' ran <m>m (budget <b>m)` annotation) or GitHub's own `timeout-minutes` kill (`The job has exceeded the maximum execution time`). They are read from cancel_cause's evidence, and only when the job's log carries no infra or code signature of
# its own, since a log that says WHY the job ran long (a slow renet setup phase) is the deeper answer.
CATEGORIES = (
    "infra-likely",
    "code-likely",
    "watchdog-cancel",
    "timeout-cancel",
    "manual-cancel",
    "unknown",
)
CANCEL_CATEGORIES = {
    "watchdog-budget": "watchdog-cancel",
    "timeout-kill": "timeout-cancel",
    # GitHub never gave the job a runner (PR run 37361706365 on 2026-10-05, during an Actions incident): nothing in the code ran, so it is infrastructure.
    "runner-not-acquired": "infra-likely",
}
# A RUN-LEVEL CANCEL prints the runner's shutdown-signal message into every job it stops, exactly as a lost runner does (Quality / Static job 112840911365, run 37633980671: the watchdog cancelled the run for Quality / Submodule Branches and the job read `runner-lost`). A job whose log ends on that message is therefore a lost runner only when no run-level cancel is attributed; with one, the cancel is the answer.
RUN_CANCEL_CATEGORIES = {
    "watchdog-budget": "watchdog-cancel",
    "watchdog-failure": "watchdog-cancel",
    "manual": "manual-cancel",
}
FAIL_CONCLUSIONS = ("failure", "timed_out", "startup_failure")
# A root cause may be a job that was stopped: a cancelled job is never green, and on a main push run it is often the only non-aggregator that did not pass.
ROOT_CONCLUSIONS = (*FAIL_CONCLUSIONS, "cancelled")
# Earlier attempts summarised beside a re-run's verdict; a bound keeps the reads finite.
MAX_ATTEMPTS_SUMMARISED = 4
TRACE_CMD = ".ci/scripts/ci/ci-trace.py"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LANE_DURATIONS = REPO_ROOT / ".ci" / "config" / "lane-durations.json"

# The ENFORCED budget text from watchdog-monitor.cjs (`CI BUDGET VIOLATION: '<job>' ran <m>m (budget <b>m)`). The report-only form reads `CI BUDGET VIOLATION (report-only): ...` and deliberately does not match: a report-only line cancelled nothing.
BUDGET_RE = re.compile(r"CI BUDGET VIOLATION: '(.+?)' ran ([\d.]+)m \(budget (\d+)m\)")
WATCHDOG_TITLE_RE = "Watchdog: run %s ("
TIMEOUT_RE = re.compile(r"has exceeded the maximum execution time(?: of (\S+))?")
FORCED_RE = re.compile(r"canceled forcefully by @([\w-]+(?:\[bot\])?)")
NOT_ACQUIRED_RE = re.compile(r"was not acquired by Runner")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TS_RE = re.compile(r"^\ufeff?(\d{4}-\d\d-\d\dT(\d\d:\d\d:\d\d))(\.\d+)?Z ?")
STREAM_RE = re.compile(r"\bvm=(\S+)\s*$")

# SIGNATURES: (id, category, pattern, label, minimum seconds or 0). Infra rows are checked before code rows, so a test that failed BECAUSE a mirror was down reads as infra. Order inside a category matters too: a Bitwarden 503 must not read as a registry 503.
SIGNATURES = (
    (
        "bitwarden-5xx",
        "infra",
        re.compile(r"(?i)\b(?:bitwarden|bws)\b.*\b5\d\d\b"),
        "Bitwarden secrets fetch hit a 5xx",
        0,
    ),
    (
        "registry-refused",
        "infra",
        re.compile(
            r"\b(?:403 Forbidden|503 Service Unavailable|429 Too Many Requests)\b|toomanyrequests"
            r"|unexpected status(?: code)?:? (?:403|429|503)\b"
        ),
        "registry/CDN refused a pull",
        0,
    ),
    (
        "runner-lost",
        "infra",
        re.compile(
            r"runner has received a shutdown signal|lost communication with the server"
            r"|hosted runner encountered an error"
        ),
        "the runner went away",
        0,
    ),
    # GitHub's own API answered 5xx to a `gh` call. Quality / Security job 112158906504 (run 37429940875) failed on `budget_report: gh api ... exited 1 [failed]: gh: Server Error (HTTP 502)` and read `category: unknown`. Not the Bitwarden row: that one needs `bws-secrets`/Received error message in the line.
    (
        "github-api-5xx",
        "infra",
        re.compile(
            r"\bServer Error \(HTTP 5\d\d\)|\bgh: .*\(HTTP 5\d\d\)"
            r"|\bgh: (?:Bad Gateway|Service Unavailable|Gateway Timeout)\b"
        ),
        "GitHub's API answered 5xx to a gh call",
        0,
    ),
    (
        "pkg-mirror",
        "infra",
        re.compile(
            r"Curl error \(\d+\)|repomd\.xml|Failed to download metadata"
            r"|Failed to fetch https?://|Hash Sum mismatch"
        ),
        "a package mirror failed",
        0,
    ),
    (
        "network",
        "infra",
        re.compile(
            r"\bECONNRESET\b|\bETIMEDOUT\b|\bECONNREFUSED\b|[Nn]etwork is unreachable"
            r"|Could not resolve host|TLS handshake timeout"
        ),
        "a network call failed",
        0,
    ),
    (
        "slow-setup",
        "infra",
        re.compile(r"\[setup\] (\S+) end \d+ \((\d+)s\)"),
        "a renet setup phase ran long",
        300,
    ),
    ("go-fail", "code", re.compile(r"^--- FAIL: "), "a Go test failed", 0),
    # This repo's gates print `::finding::<rule>:<hash>` beside the finding they report (Quality / Branch on run 36974364712: `::finding::P-A1:...` under "P-A1 OPEN BOXES").
    ("gate-finding", "code", re.compile(r"^::finding::\S"), "a repo gate reported a finding", 0),
    ("pytest-failed", "code", re.compile(r"^FAILED \S+::"), "a pytest case failed", 0),
    ("assertion", "code", re.compile(r"\bAssertionError\b"), "an assertion failed", 0),
    ("playwright-fail", "code", re.compile(r"\u2718"), "a Playwright test failed", 0),
    ("panic", "code", re.compile(r"\bpanic: "), "a Go panic", 0),
    (
        "error",
        "code",
        re.compile(r"(?<![\w\]])Error: (?!Process completed with exit code)"),
        "an error was raised",
        0,
    ),
    # A step's OWN `##[error]` message, not the runner's exit line or its cancel notice. Quality / Security on nightly run 36827121342 printed `##[error]Production vulnerabilities: 1 critical, ...` and `--why` still said `category: unknown`.
    (
        "step-error",
        "code",
        re.compile(
            r"##\[error\](?!Process completed with exit code|The operation was canceled"
            r"|The job has exceeded the maximum execution time)\S"
        ),
        "the step reported an error",
        0,
    ),
    # This repo's checks end on an upper-case FAILED verdict line (Quality / Content on nightly run 37273046804: `Dependency check FAILED: 2 must upgrade, ...`), which no other row matched.
    (
        "check-failed",
        "code",
        re.compile(r"\b[A-Za-z][\w-]* FAILED\b"),
        "a repo check reported FAILED",
        0,
    ),
)

SECRET_RES = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),
)


def sanitize(text):
    """`text` with token- and key-shaped substrings replaced by [REDACTED].

    GitHub masks registered secrets as *** in logs, but a value nobody registered (a token minted mid-job, a URL with credentials in it) prints in clear. Anything this module hands to a check-run passes through here.
    """
    out = str(text or "")
    for rx in SECRET_RES:
        out = rx.sub("[REDACTED]", out)
    return out


# ---- fetchers ---------------------------------------------------------------


def _full(repo, path):
    path = str(path).lstrip("/")
    if path.startswith(("repos/", "search/")):
        return path
    return "repos/%s/%s" % (repo, path)


def _gh_retry():
    """`rediacc_ci.core.gh_retry`, imported on first use. This module is loaded by path (no `.ci` on sys.path), so `.ci` is put there through the canonical resolver, `rediacc_ci.paths.on_sys_path`, itself loaded by file: importing it by name would already need the hop (test_canonical_sys_path_hop)."""
    import importlib.util  # noqa: PLC0415 - only this lookup needs it

    ci_root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "_rediacc_ci_paths", ci_root / "rediacc_ci" / "paths.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % (ci_root / "rediacc_ci" / "paths.py"))
    paths_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paths_mod)
    paths_mod.on_sys_path(ci_root)
    from rediacc_ci.core import gh_retry  # noqa: PLC0415

    return gh_retry


class GhFetcher:
    """Reads through the local `gh` CLI. Never raises: every error comes back as a string.

    A TRANSIENT fault (a 5xx or a dropped connection, per gh_retry.is_transient) is retried; a 4xx, a timeout and any other failure come back at once. `attempts` and `pause` bound the wait: the defaults are gh_retry's policy (three attempts, 5 s then 15 s), and the Stop hook passes `attempts=2, pause=2` so a blip costs it two seconds, not twenty. Live: `ci-trace.py --run 37507913738` read "HTTP 502" twice on 2026-10-06 and gave up on the first.
    """

    def __init__(self, repo, cwd=None, timeout=60, attempts=None, pause=None, sleep=None):
        self.repo = repo
        self.cwd = str(cwd) if cwd else None
        self.timeout = timeout
        self.attempts = attempts
        self.pause = pause
        self.sleep = sleep

    def _once(self, args):
        try:
            out = subprocess.run(
                ["gh", "api", *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.cwd,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, str(exc)[:200]
        if out.returncode != 0:
            return None, (
                (out.stderr or out.stdout or "").strip() or "gh exited %d" % out.returncode
            )[-200:]
        return out.stdout, ""

    def _run(self, args):
        retry = _gh_retry()
        nap = self.sleep or time.sleep
        return retry.retry_transient(
            lambda: self._once(args),
            lambda r: None if r[0] is not None else (r[1] or "failed"),
            attempts=self.attempts or retry.ATTEMPTS,
            sleep=(lambda _scheduled: nap(self.pause)) if self.pause is not None else nap,
        )

    def json(self, path):
        raw, err = self._run([_full(self.repo, path)])
        if raw is None:
            return None, err
        try:
            return json.loads(raw), ""
        except ValueError:
            return None, "non-JSON from %s: %r" % (path, raw[:80])

    def text(self, path):
        # --allow-escape-sequences IS REQUIRED: job logs carry ANSI colour, and without it gh writes nothing to stdout and exits 1 (measured 2026-08-28 and again 2026-10-02 on job 110680194371).
        return self._run([_full(self.repo, path), "--allow-escape-sequences"])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def _gh_api_base():
    """WK_GH_API_BASE from the literal registry. Loaded by file because this module is itself loaded by path from ci-trace, which puts no `.ci` on sys.path."""
    import importlib.util  # noqa: PLC0415 - only this lookup needs it

    path = pathlib.Path(__file__).resolve().parents[1] / "well_known.py"
    spec = importlib.util.spec_from_file_location("rediacc_ci_ci_diagnose_well_known", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GH_API_BASE


class HttpFetcher:
    """Reads the REST API with a token, for a runner where `gh` is absent or unauthenticated."""

    def __init__(self, repo, token, api=None, timeout=60):
        self.repo = repo
        self.token = token
        self.api = (api or _gh_api_base()).rstrip("/")
        self.timeout = timeout

    def _open(self, url, auth, follow):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if auth:
            headers["Authorization"] = "Bearer %s" % self.token
        # Only https: the API base is a constructor argument and a log redirect comes from the API's own Location header, so refuse anything else rather than open a file: or custom scheme.
        if not url.startswith("https://"):
            raise urllib.error.URLError("refusing a non-https URL: %s" % url[:80])
        req = urllib.request.Request(url, headers=headers)  # noqa: S310 -- https enforced above
        opener = (
            urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
        )
        return opener.open(req, timeout=self.timeout)

    def _get(self, path):
        url = "%s/%s" % (self.api, _full(self.repo, path))
        try:
            with self._open(url, True, False) as resp:
                return resp.read().decode("utf-8", "replace"), ""
        except urllib.error.HTTPError as exc:
            location = exc.headers.get("Location") if exc.code in (301, 302, 303, 307) else None
            if not location:
                return None, "HTTP %s for %s" % (exc.code, path)
        except (urllib.error.URLError, OSError) as exc:
            return None, "%s for %s" % (str(exc)[:160], path)
        # A log download redirects to signed blob storage. The token must NOT follow it there.
        try:
            with self._open(location, False, True) as resp:
                return resp.read().decode("utf-8", "replace"), ""
        except (urllib.error.URLError, OSError) as exc:
            return None, "%s for the %s redirect" % (str(exc)[:160], path)

    def json(self, path):
        raw, err = self._get(path)
        if raw is None:
            return None, err
        try:
            return json.loads(raw), ""
        except ValueError:
            return None, "non-JSON from %s" % path

    def text(self, path):
        return self._get(path)


# ---- small helpers ----------------------------------------------------------


def _epoch(iso):
    """Seconds since the epoch from an ISO-8601 UTC stamp, or None."""
    if not iso:
        return None
    text = str(iso).strip().replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _span(start, end):
    a, b = _epoch(start), _epoch(end)
    if a is None or b is None:
        return None
    return round(b - a)


def _p90_table():
    try:
        data = json.loads(LANE_DURATIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    table = data.get("job_p90_minutes")
    return table if isinstance(table, dict) else {}


def _blocking(name):
    """Whether a job's result counts toward the CI verdict at all."""
    return str(name or "") not in NONBLOCKING_CONTEXTS


def _aggregator(name):
    """Whether a job only aggregates, observes or reports on others (CI Complete, the watchdog, the sentinels downstream of CI Complete), so it is never a ROOT cause."""
    return any(p in str(name or "") for p in AGGREGATORS)


def _strip_ts(line):
    m = TS_RE.match(line)
    return (m.group(2) + " " + line[m.end() :]) if m else line.lstrip("\ufeff")


def _clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 3] + "..."


def _job_cmd(job_id, verb="--errors"):
    return "%s --job %s %s" % (TRACE_CMD, job_id, verb)


# ---- reads ------------------------------------------------------------------


def run_info(fetch, run_id, attempt=None):
    """(run, error): the REST run object, attempt-scoped when `attempt` is given."""
    path = "actions/runs/%s" % run_id
    if attempt:
        path += "/attempts/%s" % attempt
    data, err = fetch.json(path)
    if not isinstance(data, dict) or not data.get("id"):
        return None, err or "run %s: empty payload" % run_id
    return data, ""


def run_jobs(fetch, run_id, attempt=None):
    """(jobs, error): every job of that attempt, steps included, across pages."""
    base = (
        "actions/runs/%s/attempts/%s/jobs" % (run_id, attempt)
        if attempt
        else "actions/runs/%s/jobs" % run_id
    )
    jobs: list[dict] = []
    page = 1
    while page <= 10:
        data, err = fetch.json("%s?per_page=100&page=%d" % (base, page))
        if not isinstance(data, dict):
            return jobs, err or "jobs page %d unreadable" % page
        batch = data.get("jobs") or []
        jobs.extend(batch)
        total = data.get("total_count") or 0
        if len(batch) < 100 or len(jobs) >= total:
            break
        page += 1
    return jobs, ""


def first_failure(jobs):
    """The earliest-finishing blocking job that genuinely failed, or None."""
    failed = [
        j
        for j in jobs or []
        if (j.get("conclusion") or "") in FAIL_CONCLUSIONS
        and _blocking(j.get("name"))
        and not _aggregator(j.get("name"))
    ]
    if not failed:
        return None
    return min(
        failed, key=lambda j: (_epoch(j.get("completed_at")) or float("inf"), j.get("id") or 0)
    )


def root_cause(jobs):
    """The earliest-finishing blocking, non-aggregator job that failed OR was cancelled, or None.

    An aggregator's failure is a report of another job's result, so it never outranks the job it reports: on main push run 37394654719 attempt 2 CI Complete and Pipeline Sentinel failed because Validate Promotion was cancelled at its timeout, and the cancelled job is the one to read.
    """
    roots = [
        j
        for j in jobs or []
        if (j.get("conclusion") or "") in ROOT_CONCLUSIONS
        and _blocking(j.get("name"))
        and not _aggregator(j.get("name"))
    ]
    if not roots:
        return None
    return min(
        roots, key=lambda j: (_epoch(j.get("completed_at")) or float("inf"), j.get("id") or 0)
    )


def job_counts(jobs):
    """{conclusion: n} over the blocking jobs that did not pass, aggregators included: the honest count beside GitHub's single run-level conclusion."""
    out: dict[str, int] = {}
    for j in jobs or []:
        c = j.get("conclusion") or ""
        if c and c not in ("success", "skipped", "neutral") and _blocking(j.get("name")):
            out[c] = out.get(c, 0) + 1
    return out


def attempts_summary(fetch, run_id, current, latest):
    """[{attempt, conclusion, root, root_conclusion}] for every attempt of the run except `current`, newest first, at most MAX_ATTEMPTS_SUMMARISED.

    A re-run's verdict used to describe its own attempt only, so a job cancelled in BOTH attempts of run 37394654719 read as a one-off. One run read and one jobs read per attempt.
    """
    out: list[dict] = []
    try:
        current, latest = int(current or 0), int(latest or 0)
    except (TypeError, ValueError):
        return out
    for n in range(latest, 0, -1):
        if n == current:
            continue
        if len(out) >= MAX_ATTEMPTS_SUMMARISED:
            break
        run, _err = run_info(fetch, run_id, n)
        jobs, _jerr = run_jobs(fetch, run_id, n)
        root = root_cause(jobs)
        out.append(
            {
                "attempt": n,
                "conclusion": (run or {}).get("conclusion") or "unreadable",
                "root": (root or {}).get("name"),
                "root_conclusion": (root or {}).get("conclusion"),
            }
        )
    return out


def _annotations(fetch, check_run_id):
    data, _err = fetch.json("check-runs/%s/annotations?per_page=100" % check_run_id)
    return data if isinstance(data, list) else []


def _watchdog_evidence(fetch, run, runs, since=None):
    """(kind, cause-fields) from the Watchdog Monitor runs that watched `run`, or (None, {}). `since` is an earlier start (ISO) to widen the window to: a job a rerun carried over into attempt N ran, and was cancelled, in the attempt before it, so the watchdog that cancelled it predates attempt N's own start."""
    run_id = run.get("id")
    title = WATCHDOG_TITLE_RE % run_id
    lo = _epoch(run.get("run_started_at") or run.get("created_at")) or 0
    early = _epoch(since) if since else None
    if early:
        lo = min(lo, early)
    hi = _epoch(run.get("updated_at")) if run.get("status") == "completed" else None
    watchers = []
    for r in runs:
        name = r.get("display_title") or r.get("name") or ""
        if not name.startswith(title):
            continue
        t = _epoch(r.get("created_at")) or 0
        if t < lo or (hi is not None and t > hi):
            continue
        watchers.append((t, r))
    watchers.sort(key=lambda x: x[0], reverse=True)
    for _t, w in watchers[:4]:
        data, _err = fetch.json("actions/runs/%s/jobs?per_page=100" % w.get("id"))
        wjobs = (data.get("jobs") or []) if isinstance(data, dict) else []
        for job in wjobs:
            notes = _annotations(fetch, job.get("id"))
            cancelled_msg = ""
            budget = None
            for a in notes:
                msg = str(a.get("message") or "")
                m = BUDGET_RE.search(msg)
                if m and budget is None:
                    budget = m
                if "pipeline-cancelled" in str(a.get("title") or ""):
                    cancelled_msg = msg
            if budget is not None:
                return "watchdog-budget", {
                    "detail": "'%s' ran %sm (budget %sm)"
                    % (budget.group(1), budget.group(2), budget.group(3)),
                    "job": budget.group(1),
                    "minutes": float(budget.group(2)),
                    "budget_min": int(budget.group(3)),
                    "watchdog_run": w.get("id"),
                }
            if cancelled_msg:
                return "watchdog-failure", {
                    "detail": "watchdog cancelled the run: %s"
                    % _clip(sanitize(cancelled_msg), 240),
                    "job": None,
                    "minutes": None,
                    "budget_min": None,
                    "watchdog_run": w.get("id"),
                }
    return None, {}


def cancel_cause(fetch, run, pr_head=None, jobs=None, focus=None):
    """Why a run (or its root-cause job `focus`) was cancelled. See CAUSE_KINDS for the order of the evidence; `focus`'s own annotations are read before the longest-running cancelled jobs', because the job that stopped first is rarely the one that ran longest (run 37361706365: Quality / Pytest (2/3) was never given a runner at 25 min, while the E2E legs cancelled behind it ran 55)."""
    cause = {
        "kind": "unknown",
        "detail": "cause unknown; not proven superseded",
        "job": None,
        "minutes": None,
        "budget_min": None,
        "watchdog_run": None,
    }
    run = run or {}
    head = run.get("head_sha") or ""
    data, _err = fetch.json("actions/runs?head_sha=%s&per_page=100" % head) if head else ({}, "")
    runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
    runs = runs if isinstance(runs, list) else []

    # A focus job carried over from an earlier attempt (job 112840911365: started 14:09:48 in attempt 1, listed under attempt 2 which began 14:18:33) was stopped by evidence from that earlier window.
    kind, fields = _watchdog_evidence(
        fetch, run, runs, since=(focus or {}).get("started_at") if focus else None
    )
    if kind:
        cause.update(fields, kind=kind)
        return cause

    if pr_head and head and pr_head != head:
        cause.update(
            kind="superseded",
            detail="superseded: the PR head is now %s, this run was on %s"
            % (pr_head[:8], head[:8]),
        )
        return cause
    created = _epoch(run.get("created_at")) or 0
    for r in runs:
        if (
            r.get("id") != run.get("id")
            and r.get("name") == run.get("name")
            # SAME EVENT ONLY: a nightly `schedule` run on the same head does not supersede a `push` run (live on 37394654719, 2026-10-06: "superseded by run 37428263878", the 07:12 nightly, while the push run's own job had hit its timeout-minutes).
            and r.get("event") == run.get("event")
            and (_epoch(r.get("created_at")) or 0) > created
        ):
            cause.update(
                kind="superseded",
                detail="superseded by run %s of %s on the same head" % (r.get("id"), r.get("name")),
            )
            return cause

    cancelled = [j for j in jobs or [] if j.get("conclusion") == "cancelled"]
    cancelled.sort(
        key=lambda j: _span(j.get("started_at"), j.get("completed_at")) or 0, reverse=True
    )
    candidates = cancelled[:3]
    if focus is not None and focus.get("conclusion") == "cancelled":
        candidates = [focus, *(j for j in candidates if j.get("id") != focus.get("id"))]
    actor = None
    for job in candidates:
        for a in _annotations(fetch, job.get("id")):
            msg = str(a.get("message") or "")
            if NOT_ACQUIRED_RE.search(msg):
                cause.update(
                    kind="runner-not-acquired",
                    detail="'%s' was never given a runner (GitHub: %s)"
                    % (job.get("name"), _clip(sanitize(msg), 120)),
                    job=job.get("name"),
                )
                return cause
            m = TIMEOUT_RE.search(msg)
            if m:
                span = _span(job.get("started_at"), job.get("completed_at"))
                cause.update(
                    kind="timeout-kill",
                    detail="'%s' hit its timeout-minutes%s"
                    % (job.get("name"), " (%s)" % m.group(1) if m.group(1) else ""),
                    job=job.get("name"),
                    minutes=round(span / 60.0, 1) if span else None,
                )
                return cause
            f = FORCED_RE.search(msg)
            if f and actor is None:
                actor = f.group(1)
    if actor and not actor.endswith("[bot]"):
        cause.update(kind="manual", detail="cancelled by @%s" % actor)
    return cause


def _cache_dir(cache_dir=None):
    if cache_dir:
        return pathlib.Path(cache_dir)
    base = os.environ.get("XDG_CACHE_HOME") or str(pathlib.Path.home() / ".cache")
    return pathlib.Path(base) / "ci-trace" / "logs"


def job_log(fetch, job_id, completed=True, cache_dir=None):
    """(log, error): the job's log with ANSI colour stripped, cached on disk once the job is complete."""
    path = _cache_dir(cache_dir) / ("%s.log" % job_id)
    if completed and path.is_file():
        try:
            return path.read_text(encoding="utf-8"), ""
        except OSError:
            pass
    raw, err = fetch.text("actions/jobs/%s/logs" % job_id)
    if raw is None:
        return None, err
    text = ANSI_RE.sub("", raw).lstrip("\ufeff")
    if completed:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return text, ""


def _failing_step(job):
    steps = (job or {}).get("steps") or []
    for want in (FAIL_CONCLUSIONS, ("cancelled",)):
        for s in steps:
            if (s.get("conclusion") or "") in want:
                return s
    return None


def failing_step_slice(log, job):
    """(step name, the log lines written while that step ran). The whole log when no step can be placed."""
    lines = (log or "").splitlines()
    step = _failing_step(job)
    if not step:
        return "", lines
    lo, hi = _epoch(step.get("started_at")), _epoch(step.get("completed_at"))
    if lo is None:
        return step.get("name") or "", lines
    hi = (hi if hi is not None else float("inf")) + 1.0
    out = []
    for line in lines:
        m = TS_RE.match(line)
        if not m:
            continue
        t = _epoch(m.group(1) + "Z")
        if t is not None and lo - 1.0 <= t <= hi:
            out.append(line)
    # The step's own exit line ends it. Timestamps are whole seconds at the edges, so the next step's opening lines can share the last second; measured on job 110735213399, where `##[group]Run npm run check:ci-plan-record` followed the failing step's exit line within the same second.
    end = next(
        (i for i, ln in enumerate(out) if "##[error]Process completed with exit code" in ln), None
    )
    if end is not None:
        out = out[: end + 1]
    return step.get("name") or "", out or lines


SHORT_TS_RE = re.compile(r"^\d\d:\d\d:\d\d ")


def _sig_hit(line):
    body = SHORT_TS_RE.sub("", TS_RE.sub("", line, count=1), count=1)
    for sid, cat, rx, label, min_s in SIGNATURES:
        m = rx.search(body)
        if not m:
            continue
        if min_s and int(m.group(2)) < min_s:
            continue
        return sid, cat, label, m
    return None


def classify(lines):
    """(category, signature id). Any infra hit wins over any code hit; nothing at all is `unknown`."""
    code = None
    for line in lines or []:
        hit = _sig_hit(line)
        if not hit:
            continue
        if hit[1] == "infra":
            return "infra-likely", hit[0]
        code = code or hit[0]
    return ("code-likely", code) if code else ("unknown", "")


def signature_label(sid):
    for row in SIGNATURES:
        if row[0] == sid:
            return row[3]
    return ""


def excerpt(lines, max_hits=3, context=3, max_lines=8, clip=200):
    """Up to `max_hits` windows around signature hits (first) and `##[error]` lines, each <= `max_lines`."""
    lines = list(lines or [])
    sig_idx = [i for i, ln in enumerate(lines) if _sig_hit(ln)]
    err_idx = [i for i, ln in enumerate(lines) if "##[error]" in ln and i not in sig_idx]
    windows: list[tuple[int, int]] = []
    for i in sig_idx + err_idx:
        if any(a <= i <= b for a, b in windows):
            continue
        a = max(0, i - context)
        b = min(len(lines) - 1, i + context, a + max_lines - 1)
        windows.append((a, b))
        if len(windows) >= max_hits:
            break
    out = []
    for n, (a, b) in enumerate(sorted(windows)):
        if n:
            out.append("--")
        out.extend(_clip(sanitize(_strip_ts(ln)), clip) for ln in lines[a : b + 1])
    return out


def log_gaps(log, min_s=120, top=3):
    """The longest silences in a log: across the whole log, and per `vm=<name>` stream.

    A per-stream gap is the one that names a hung VM. On run 36953549081 the whole log was never silent for more than ~500 s, because the other VMs kept talking, while rediacc11 itself said nothing for ~950 s during its `essentials` phase.
    """
    gaps = []
    last: dict[str, tuple[float, str, str]] = {}
    for line in (log or "").splitlines():
        m = TS_RE.match(line)
        if not m:
            continue
        t = _epoch(m.group(1) + "Z")
        if t is None:
            continue
        sm = STREAM_RE.search(line)
        keys = [""] + ([sm.group(1)] if sm else [])
        for key in keys:
            prev = last.get(key)
            if prev is not None and t - prev[0] >= min_s:
                gaps.append(
                    {
                        "s": round(t - prev[0]),
                        "stream": key,
                        "at": prev[2],
                        "before": _clip(sanitize(_strip_ts(prev[1])[9:]), 140),
                        "after": _clip(sanitize(_strip_ts(line)[9:]), 140),
                    }
                )
            last[key] = (t, line, m.group(2))
    gaps.sort(key=lambda g: g["s"], reverse=True)
    return gaps[:top]


def durations(job, p90_minutes=None):
    """{"job_s", "p90_s", "step", "step_s"} for one job, against the recorded p90 when one exists."""
    table = p90_minutes if p90_minutes is not None else _p90_table()
    p90 = table.get((job or {}).get("name") or "")
    step = _failing_step(job)
    return {
        "job_s": _span((job or {}).get("started_at"), (job or {}).get("completed_at")),
        "p90_s": round(float(p90) * 60) if isinstance(p90, (int, float)) else None,
        "step": (step or {}).get("name") or "",
        "step_s": _span((step or {}).get("started_at"), (step or {}).get("completed_at"))
        if step
        else None,
    }


def history(fetch, job_name, n=5, workflow_file="ci.yml"):
    """The last `n` completed runs of one job by display name, newest first."""
    data, _err = fetch.json(
        "actions/workflows/%s/runs?per_page=20&status=completed" % workflow_file
    )
    runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
    out = []
    for r in runs or []:
        jobs, err = run_jobs(fetch, r.get("id"))
        if err:
            # SAID, NEVER SKIPPED. A run whose jobs could not be read used to drop out silently, and the history then quietly answered from older runs (observed 2026-10-02: five 0923-1 runs listed while five newer 0930-1 runs carried the job).
            out.append(
                {
                    "run_id": r.get("id"),
                    "attempt": r.get("run_attempt"),
                    "branch": r.get("head_branch"),
                    "sha": (r.get("head_sha") or "")[:8],
                    "conclusion": "unreadable",
                    "s": None,
                    "created_at": r.get("created_at"),
                    "job_id": None,
                    "error": err,
                }
            )
            if len(out) >= n:
                break
            continue
        for j in jobs:
            if j.get("name") == job_name:
                out.append(
                    {
                        "run_id": r.get("id"),
                        "attempt": j.get("run_attempt"),
                        "branch": r.get("head_branch"),
                        "sha": (r.get("head_sha") or "")[:8],
                        "conclusion": j.get("conclusion"),
                        "s": _span(j.get("started_at"), j.get("completed_at")),
                        "created_at": r.get("created_at"),
                        "job_id": j.get("id"),
                    }
                )
                break
        if len(out) >= n:
            break
    return out


# ---- the verdict --------------------------------------------------------------


def _blank(run_id, attempt, now):
    return {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generated_at": (now or datetime.datetime.now(datetime.UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "head_sha": "",
        "run_id": int(run_id) if str(run_id).isdigit() else run_id,
        "attempt": attempt,
        "workflow": "",
        "conclusion": "",
        "verdict": "unknown",
        "cause": None,
        "first_failure": None,
        "jobs": {},
        "also_failed": [],
        "attempts": [],
        "gaps": [],
        "next": "",
    }


def evidence(log, job):
    """(step, lines, widened): the failing step's log lines, or the whole log up to that step's end when the step itself holds no evidence.

    A step that only RE-RAISES an earlier step's outcome carries nothing but the runner's exit line: Housekeeping run 37294996911 failed in `Fail the job when the budget check failed` (0 s) while the check itself ran, and logged, under `continue-on-error` in an earlier step. Widening to the log before the step's end lets that earlier output be classified and excerpted, and `widened` says so.
    """
    step, lines = failing_step_slice(log, job)
    if any(_sig_hit(ln) for ln in lines) or any(
        "##[error]" in ln and "##[error]Process completed with exit code" not in ln for ln in lines
    ):
        return step, lines, False
    whole = (log or "").splitlines()
    if not lines or len(lines) >= len(whole):
        return step, lines, False
    end = whole.index(lines[-1]) if lines[-1] in whole else len(whole) - 1
    return step, whole[: end + 1], True


def _focus(fetch, job, cache_dir=None, cause=None):
    """The first_failure block and gaps for one job. A cancelled job whose log names no signature takes its category from the cancel `cause` (watchdog-cancel, timeout-cancel)."""
    jid = job.get("id")
    dur = durations(job)
    block = {
        "job_id": jid,
        "name": job.get("name") or "",
        "conclusion": job.get("conclusion") or job.get("status") or "",
        "step": dur["step"],
        "step_s": dur["step_s"],
        "job_s": dur["job_s"],
        "p90_s": dur["p90_s"],
        "category": "unknown",
        "signature": "",
        "excerpt": [],
        "widened": False,
    }
    log, _err = job_log(fetch, jid, completed=job.get("status") == "completed", cache_dir=cache_dir)
    gaps = []
    if log:
        step, lines, widened = evidence(log, job)
        block["step"] = step or block["step"]
        block["category"], block["signature"] = classify(lines)
        block["excerpt"] = excerpt(lines)
        block["widened"] = widened
        gaps = log_gaps(log)
    block["category"], block["signature"] = cancel_reclassify(
        job, cause, block["category"], block["signature"]
    )
    return block, gaps


def cancel_category(job, cause, category):
    """`category` unless it is `unknown` and `job` was cancelled by a cause that names it (or names no job, for a timeout kill read off that job)."""
    if category != "unknown" or (job or {}).get("conclusion") != "cancelled" or not cause:
        return category
    mapped = CANCEL_CATEGORIES.get(cause.get("kind") or "")
    named = cause.get("job")
    if mapped and (not named or named == (job or {}).get("name")):
        return mapped
    return category


def needs_cancel_cause(job, category, sig):
    """True when a cancelled job's category still depends on the run's cancel evidence: nothing recognised, or only the runner-lost message a run cancel also prints."""
    return (job or {}).get("conclusion") == "cancelled" and (
        category == "unknown" or sig == "runner-lost"
    )


def cancel_reclassify(job, cause, category, sig):
    """(category, signature) after the run's cancel evidence. A cancelled job whose only signature is `runner-lost` and whose run was cancelled by the watchdog (or a person) is that cancel, not a lost runner: the signature is dropped so the verdict does not also say the runner went away. Everything else goes through cancel_category."""
    if needs_cancel_cause(job, category, sig) and sig == "runner-lost":
        mapped = RUN_CANCEL_CATEGORIES.get((cause or {}).get("kind") or "")
        if mapped:
            return mapped, ""
    return cancel_category(job, cause, category), sig


def diagnose(fetch, run_id, attempt=None, pr_head=None, now=None, cache_dir=None):
    """The ci-verdict/v1 dict for one run attempt. Never raises on a read failure: the verdict is `unknown` and `next` says why.

    THE VERDICT AND THE ROOT CAUSE ARE SEPARATE QUESTIONS. The verdict is red when any blocking job failed, aggregators included (a red CI Complete IS a red run, whatever GitHub's run-level conclusion says: run 37394654719 concluded `cancelled` with CI Complete failed). The job the reader is sent to is the root cause: the earliest non-aggregator job that failed or was cancelled (`root_cause`), so a sentinel reporting a
    cancelled job never stands in for it. A cancelled root is attributed through cancel_cause on a red verdict too.
    """
    d = _blank(run_id, attempt, now)
    run, err = run_info(fetch, run_id, attempt)
    if run is None:
        d["next"] = "could not read run %s: %s" % (run_id, err)
        return d
    this_attempt = run.get("run_attempt") or attempt
    d.update(
        head_sha=run.get("head_sha") or "",
        attempt=this_attempt,
        workflow=run.get("name") or "",
        conclusion=run.get("conclusion") or run.get("status") or "",
    )
    jobs, err = run_jobs(fetch, run_id, this_attempt)
    if not jobs and err:
        d["next"] = "could not read the jobs of run %s: %s" % (run_id, err)
        return d
    d["jobs"] = job_counts(jobs)
    blocking = [j for j in jobs if _blocking(j.get("name"))]
    any_failed = [j for j in blocking if (j.get("conclusion") or "") in FAIL_CONCLUSIONS]
    roots = [j for j in blocking if not _aggregator(j.get("name"))]
    cancelled = [j for j in roots if j.get("conclusion") == "cancelled"]
    root = root_cause(jobs)
    completed = run.get("status") == "completed"
    focus = None
    if any_failed:
        d["verdict"] = "red"
        focus = (
            root
            or first_failure(any_failed)
            or min(any_failed, key=lambda j: _epoch(j.get("completed_at")) or float("inf"))
        )
    elif run.get("conclusion") == "cancelled" or (completed and cancelled):
        d["verdict"] = "cancelled"
    elif not completed:
        d["verdict"] = "running"
    elif run.get("conclusion") in ("success", "skipped", "neutral"):
        d["verdict"] = "green"
    else:
        d["verdict"] = "red"
    if d["verdict"] == "cancelled" or (
        focus is not None and focus.get("conclusion") == "cancelled"
    ):
        d["cause"] = cancel_cause(fetch, run, pr_head, jobs, focus=root)
        named = (d["cause"] or {}).get("job")
        pick = next((j for j in roots if j.get("name") == named), None)
        if d["verdict"] == "cancelled":
            focus = pick
            if focus is None and cancelled:
                focus = max(
                    cancelled,
                    key=lambda j: _span(j.get("started_at"), j.get("completed_at")) or 0,
                )
        elif pick is not None and pick.get("conclusion") == "cancelled":
            focus = pick
    if focus is not None:
        d["first_failure"], d["gaps"] = _focus(fetch, focus, cache_dir=cache_dir, cause=d["cause"])
        d["next"] = _job_cmd(focus.get("id"))
        d["also_failed"] = [
            j.get("name") or "?"
            for j in roots
            if j is not focus and (j.get("conclusion") or "") in FAIL_CONCLUSIONS
        ]
    elif d["verdict"] in ("red", "running"):
        d["next"] = "%s --run %s --jobs" % (TRACE_CMD, run_id)
    if d["verdict"] not in ("green", "running"):
        latest = run.get("run_attempt")
        if attempt:
            # An explicit attempt may not be the newest; the run without an attempt says how many there are.
            newest, _err = run_info(fetch, run_id)
            latest = (newest or {}).get("run_attempt") or latest
        if (latest or 0) > 1:
            d["attempts"] = attempts_summary(fetch, run_id, this_attempt, latest)
    return d


def _conclusion_text(d):
    """GitHub's run-level conclusion, beside the job counts whenever they say something it does not: run 37394654719 concluded `cancelled` with two jobs failed."""
    concl = d.get("conclusion") or "?"
    counts = d.get("jobs") or {}
    if not counts or set(counts) == {concl}:
        return concl
    parts = ", ".join(
        "%d %s" % (n, k) for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return "run %s; jobs: %s" % (concl, parts)


def _attempts_text(d):
    """One line over every other attempt, ending with whether the root-cause job is the same in all of them (a repeat is not a flake)."""
    rows = d.get("attempts") or []
    bits = [
        "a%s %s%s"
        % (
            r.get("attempt"),
            r.get("conclusion"),
            " (%s %s)" % (r.get("root"), r.get("root_conclusion")) if r.get("root") else "",
        )
        for r in rows
    ]
    mine = (d.get("first_failure") or {}).get("name")
    same = bool(mine) and all(r.get("root") == mine for r in rows)
    return "  other attempts: %s%s" % (
        "; ".join(bits),
        " -- the same job in every attempt, so not a one-off" if same else "",
    )


def render(d, budget_lines=12):
    """The verdict in at most `budget_lines` lines and 1,500 characters. Line one is the headline."""
    d = d or {}
    head = "%s  %s run %s attempt %s @ %s -> %s" % (
        str(d.get("verdict") or "unknown").upper(),
        d.get("workflow") or "run",
        d.get("run_id"),
        d.get("attempt") or "?",
        (d.get("head_sha") or "?")[:8],
        _conclusion_text(d),
    )
    fixed = [head]
    cause = d.get("cause") or {}
    if cause:
        extra = " [watchdog run %s]" % cause["watchdog_run"] if cause.get("watchdog_run") else ""
        fixed.append("  cause: %s: %s%s" % (cause.get("kind"), cause.get("detail"), extra))
    ff = d.get("first_failure") or {}
    if ff:
        concl = ff.get("conclusion")
        bits = [
            "  job: %s (%s)%s" % (ff.get("name"), ff.get("job_id"), " %s" % concl if concl else "")
        ]
        if ff.get("step"):
            bits.append(
                "step %r%s"
                % (ff["step"], " (evidence from earlier steps)" if ff.get("widened") else "")
            )
        if ff.get("step_s") is not None:
            bits.append("%ss" % ff["step_s"])
        elif ff.get("job_s") is not None:
            # No step failed or was cancelled (GitHub's timeout kill on job 112061625885 landed after every step had passed): the job's own run time is the number that matters.
            bits.append("no step failed; job lasted %ss" % ff["job_s"])
        if ff.get("p90_s") is not None:
            bits.append("(job p90 %ss)" % ff["p90_s"])
        fixed.append(" ".join(bits))
        sig = ff.get("signature") or ""
        fixed.append(
            "  category: %s%s"
            % (
                ff.get("category") or "unknown",
                " (%s: %s)" % (sig, signature_label(sig)) if sig else "",
            )
        )
    if d.get("also_failed"):
        also = d["also_failed"]
        fixed.append(
            "  also failed: %s%s"
            % (", ".join(also[:4]), " (+%d more)" % (len(also) - 4) if len(also) > 4 else "")
        )
    if d.get("attempts"):
        fixed.append(_attempts_text(d))
    tail = [
        "  gap: %ss silent%s after %s %r"
        % (
            g.get("s"),
            " on vm=%s" % g["stream"] if g.get("stream") else "",
            g.get("at"),
            g.get("before"),
        )
        for g in (d.get("gaps") or [])[:2]
    ]
    if d.get("next"):
        tail.append("  next: %s" % d["next"])
    room = max(0, budget_lines - len(fixed) - len(tail))
    # The HIT lines first: a window's context lines are for --errors, while the summary has room for only a handful.
    ex = ff.get("excerpt") or []
    hits = [ln for ln in ex if _sig_hit(ln) or "##[error]" in ln]
    body = ["    " + ln for ln in (hits or ex)[:room]]
    lines = [_clip(ln, 180) for ln in fixed + body + tail][:budget_lines]
    text = "\n".join(lines)
    while len(text) > 1500 and len(lines) > 1:
        # Drop excerpt lines first, from the end, so the headline, cause and next survive.
        idx = next((i for i in range(len(lines) - 1, 0, -1) if lines[i].startswith("    ")), None)
        lines.pop(idx if idx is not None else len(lines) - 2)
        text = "\n".join(lines)
    return text
