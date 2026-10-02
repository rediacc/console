#!/usr/bin/env python3
"""ci_diagnose: why a Console CI run is red, cancelled or slow, in a dozen lines instead of dozens of raw `gh` reads.

WHY THIS EXISTS. On 2026-10-02 Console CI run 36953549081 (PR #591, head a7f30558) was cancelled with 104 jobs green, 33 skipped, 29 cancelled and nothing failed. The cause lived on a DIFFERENT run: Watchdog Monitor run 36956399799 annotated `CI BUDGET VIOLATION: 'Tests + Infra / E2E Workers (fedora-43, 1/8)' ran 20.1m (budget 20m)`, and the job's own log showed why: renet's `essentials`
setup phase took 416 s and 916 s on two VMs and logged nothing meanwhile. Reconstructing that took dozens of hand-written `gh api` calls. Every step of that reconstruction is a function here, so the tracer (`.ci/scripts/ci/ci-trace.py`) and the CI-side publisher (`rediacc_ci.ci.publish_ci_verdict`) answer from ONE implementation.

STDLIB ONLY, NO rediacc_ci IMPORTS. ci-trace.py loads this file by path (it has no `.ci` hop), and the Stop hook's wl_ci.py loads it lazily for cancel attribution, so an import of the package would break both.

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
import urllib.error
import urllib.request

SCHEMA = "ci-verdict/v1"
GENERATOR = "rediacc_ci.ci.ci_diagnose"
CHECK_NAME = "CI Verdict"
PUBLISH_JOB_NAME = "Publish CI Verdict"
# Never a CI result, whatever their conclusion. "CI Verdict" is this module's own published diagnosis, and "Publish CI Verdict" is the job that posts it. Exact names, never substrings.
NONBLOCKING_CONTEXTS = frozenset({CHECK_NAME, PUBLISH_JOB_NAME})
# The watchdog's own exclusions (WATCHDOG_EXCLUDE_PATTERNS in .github/workflows/watchdog-monitor.yml): aggregators and observers, never the first failure.
WATCHDOG_EXCLUDED = ("Watchdog", "CI Complete")
CAUSE_KINDS = (
    "watchdog-budget",
    "watchdog-failure",
    "superseded",
    "timeout-kill",
    "manual",
    "unknown",
)
CATEGORIES = ("infra-likely", "code-likely", "unknown")
FAIL_CONCLUSIONS = ("failure", "timed_out", "startup_failure")
TRACE_CMD = ".ci/scripts/ci/ci-trace.py"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LANE_DURATIONS = REPO_ROOT / ".ci" / "config" / "lane-durations.json"

# The ENFORCED budget text from watchdog-monitor.cjs (`CI BUDGET VIOLATION: '<job>' ran <m>m (budget <b>m)`). The report-only form reads `CI BUDGET VIOLATION (report-only): ...` and deliberately does not match: a report-only line cancelled nothing.
BUDGET_RE = re.compile(r"CI BUDGET VIOLATION: '(.+?)' ran ([\d.]+)m \(budget (\d+)m\)")
WATCHDOG_TITLE_RE = "Watchdog: run %s ("
TIMEOUT_RE = re.compile(r"has exceeded the maximum execution time(?: of (\S+))?")
FORCED_RE = re.compile(r"canceled forcefully by @([\w-]+(?:\[bot\])?)")
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


class GhFetcher:
    """Reads through the local `gh` CLI. Never raises: every error comes back as a string."""

    def __init__(self, repo, cwd=None, timeout=60):
        self.repo = repo
        self.cwd = str(cwd) if cwd else None
        self.timeout = timeout

    def _run(self, args):
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
    """Whether a job only aggregates or observes others (CI Complete, the watchdog), so it is never a ROOT cause."""
    return any(p in str(name or "") for p in WATCHDOG_EXCLUDED)


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


def _annotations(fetch, check_run_id):
    data, _err = fetch.json("check-runs/%s/annotations?per_page=100" % check_run_id)
    return data if isinstance(data, list) else []


def _watchdog_evidence(fetch, run, runs):
    """(kind, cause-fields) from the Watchdog Monitor runs that watched `run`, or (None, {})."""
    run_id = run.get("id")
    title = WATCHDOG_TITLE_RE % run_id
    lo = _epoch(run.get("run_started_at") or run.get("created_at")) or 0
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


def cancel_cause(fetch, run, pr_head=None, jobs=None):
    """Why a run with nothing failed was cancelled. See CAUSE_KINDS for the order of the evidence."""
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

    kind, fields = _watchdog_evidence(fetch, run, runs)
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
    actor = None
    for job in cancelled[:3]:
        for a in _annotations(fetch, job.get("id")):
            msg = str(a.get("message") or "")
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
        "gaps": [],
        "next": "",
    }


def _focus(fetch, job, cache_dir=None):
    """The first_failure block (minus category defaults) and gaps for one job."""
    jid = job.get("id")
    dur = durations(job)
    block = {
        "job_id": jid,
        "name": job.get("name") or "",
        "step": dur["step"],
        "step_s": dur["step_s"],
        "p90_s": dur["p90_s"],
        "category": "unknown",
        "signature": "",
        "excerpt": [],
    }
    log, _err = job_log(fetch, jid, completed=job.get("status") == "completed", cache_dir=cache_dir)
    gaps = []
    if log:
        step, lines = failing_step_slice(log, job)
        block["step"] = step or block["step"]
        block["category"], block["signature"] = classify(lines)
        block["excerpt"] = excerpt(lines)
        gaps = log_gaps(log)
    return block, gaps


def diagnose(fetch, run_id, attempt=None, pr_head=None, now=None, cache_dir=None):
    """The ci-verdict/v1 dict for one run attempt. Never raises on a read failure: the verdict is `unknown` and `next` says why."""
    d = _blank(run_id, attempt, now)
    run, err = run_info(fetch, run_id, attempt)
    if run is None:
        d["next"] = "could not read run %s: %s" % (run_id, err)
        return d
    d.update(
        head_sha=run.get("head_sha") or "",
        attempt=run.get("run_attempt") or attempt,
        workflow=run.get("name") or "",
        conclusion=run.get("conclusion") or run.get("status") or "",
    )
    jobs, err = run_jobs(fetch, run_id, attempt or run.get("run_attempt"))
    if not jobs and err:
        d["next"] = "could not read the jobs of run %s: %s" % (run_id, err)
        return d
    blocking = [j for j in jobs if _blocking(j.get("name")) and not _aggregator(j.get("name"))]
    failed = first_failure(blocking)
    cancelled = [j for j in blocking if j.get("conclusion") == "cancelled"]
    completed = run.get("status") == "completed"
    focus = None
    if failed:
        d["verdict"] = "red"
        focus = failed
    elif run.get("conclusion") == "cancelled" or (completed and cancelled):
        d["verdict"] = "cancelled"
        d["cause"] = cancel_cause(fetch, run, pr_head, jobs)
        named = (d["cause"] or {}).get("job")
        focus = next((j for j in jobs if j.get("name") == named), None)
        if focus is None and cancelled:
            focus = max(
                cancelled, key=lambda j: _span(j.get("started_at"), j.get("completed_at")) or 0
            )
    elif not completed:
        d["verdict"] = "running"
    elif run.get("conclusion") in ("success", "skipped", "neutral"):
        d["verdict"] = "green"
    else:
        d["verdict"] = "red"
    if focus is not None:
        d["first_failure"], d["gaps"] = _focus(fetch, focus, cache_dir=cache_dir)
        d["next"] = _job_cmd(focus.get("id"))
    elif d["verdict"] in ("red", "running"):
        d["next"] = "%s --run %s --jobs" % (TRACE_CMD, run_id)
    return d


def render(d, budget_lines=12):
    """The verdict in at most `budget_lines` lines and 1,500 characters. Line one is the headline."""
    d = d or {}
    head = "%s  %s run %s attempt %s @ %s -> %s" % (
        str(d.get("verdict") or "unknown").upper(),
        d.get("workflow") or "run",
        d.get("run_id"),
        d.get("attempt") or "?",
        (d.get("head_sha") or "?")[:8],
        d.get("conclusion") or "?",
    )
    fixed = [head]
    cause = d.get("cause") or {}
    if cause:
        extra = " [watchdog run %s]" % cause["watchdog_run"] if cause.get("watchdog_run") else ""
        fixed.append("  cause: %s: %s%s" % (cause.get("kind"), cause.get("detail"), extra))
    ff = d.get("first_failure") or {}
    if ff:
        bits = ["  job: %s (%s)" % (ff.get("name"), ff.get("job_id"))]
        if ff.get("step"):
            bits.append("step %r" % ff["step"])
        if ff.get("step_s") is not None:
            bits.append("%ss" % ff["step_s"])
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
