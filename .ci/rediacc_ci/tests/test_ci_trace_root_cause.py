"""ci-trace.py names a red run's ROOT CAUSE on every read path, not the aggregator that reports it.

Main push run 37394654719 (PR #595's merge e6fc817f6, 2026-10-06) went red twice: Validate Promotion was stopped (the watchdog's 15 min budget in attempt 1, GitHub's `timeout-minutes: 15` in attempt 2), and CI Complete and Pipeline Sentinel failed reporting it. Before this file every reader got it wrong in its own way:

- `--run <id> [--wait]` listed `failed: CI Complete` / `failed: Pipeline Sentinel`, never the cancelled job, and printed its RED verdict on stderr under poll lines on stdout;
- `--ref main` said the cancelled job was collateral ("watchdog killed the run for the failure above") when the failures were aggregators reporting IT, and its `why:` line pointed at the current branch's PR;
- `--job <cancelled job> --errors` said `step: '?'` and `category: unknown`.

Hermetic: the run's own recorded answers (fixtures/ci_diagnose) served by the dict-backed fetcher from test_ci_diagnose; nothing reaches GitHub.
"""

import contextlib
import datetime
import importlib.util
import io
import re
import time

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.test_ci_diagnose import MAIN_RUN, VP_A2, FakeFetch, _load, main_routes

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")


@pytest.fixture
def ct(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ci_trace_root_cause_under_test", TRACE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    setattr(mod, "_GH_NOTE_OFF", True)  # noqa: B010 -- a module loaded by path is typed ModuleType
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    return mod


def _jobs_a2():
    return _load("jobs_37394654719_attempt2.json")["jobs"]


def _capture(fn, *args, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*args, **kw)
    return rc, out.getvalue(), err.getvalue()


def _trace(ct, monkeypatch, routes=None):
    monkeypatch.setattr(
        ct,
        "_run_snapshot",
        lambda _root, _rid: ("completed", "cancelled", _jobs_a2(), "Console CI"),
    )
    monkeypatch.setattr(
        ct, "_fetcher", lambda _root: FakeFetch(main_routes() if routes is None else routes)
    )
    return _capture(ct._trace_run, ct.REPO_ROOT, MAIN_RUN, False, 1, False)


# ---- --run <id> ---------------------------------------------------------------------


def test_run_red_lists_the_cancelled_root_first_and_explains_it_on_stdout(ct, monkeypatch):
    rc, out, err = _trace(ct, monkeypatch)
    assert rc == ct.EXIT_RED
    lines = out.splitlines()
    assert lines[0] == "RED  run %s -> cancelled" % MAIN_RUN
    assert lines[1].split() == ["cancelled", "Validate", "Promotion"], lines[1]
    assert "CI Complete  [aggregator]" in lines[2]
    assert "Pipeline Sentinel  [aggregator]" in lines[3]
    assert any(ln.startswith("  why: RED  Console CI run %s attempt 2" % MAIN_RUN) for ln in lines)
    assert "  category: timeout-cancel" in lines
    assert "RED" not in err, "the verdict is stdout, like GREEN"


def test_planted_failure_only_listing_hides_the_root(ct, monkeypatch):
    """PLANTED RED: the pre-fix listing (`conclusion == "failure"` only) drops Validate Promotion, which is what the test above guards."""
    monkeypatch.setattr(
        ct,
        "_not_passed",
        lambda jobs: [("failure", j["name"]) for j in jobs if j.get("conclusion") == "failure"],
    )
    _rc, out, _err = _trace(ct, monkeypatch)
    assert "cancelled Validate Promotion" not in " ".join(out.splitlines()[:4])


def test_run_red_survives_an_unreadable_diagnosis(ct, monkeypatch):
    rc, out, _err = _trace(ct, monkeypatch, routes={})
    assert rc == ct.EXIT_RED
    assert "why: UNKNOWN" in out, out
    assert "cancelled Validate Promotion" in " ".join(out.split())


# ---- --ref main (the branch read) ------------------------------------------------------


def _ctx(name, conclusion="SUCCESS", job=7):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "databaseId": job,
        "checkSuite": {"workflowRun": {"databaseId": MAIN_RUN}},
    }


def _snap(ct, monkeypatch, contexts):
    info = {
        "owner": "rediacc",
        "name": "console",
        "source": "branch",
        "pr": None,
        "sha": "e6fc817f6696f56511d73223d4be30b3c64d0ab1",
        "rollup": "FAILURE",
        "total": len(contexts),
        "contexts": contexts,
        "foreign": 0,
        "truncated": False,
    }
    cause = {
        "kind": "timeout-kill",
        "detail": "'Validate Promotion' hit its timeout-minutes (15m0s)",
        "job": "Validate Promotion",
        "watchdog_run": None,
    }
    monkeypatch.setattr(ct.wl_ci, "ci_rollup", lambda *_a, **_k: ("ok", info))
    monkeypatch.setattr(ct.wl_ci, "ci_steps", lambda *_a, **_k: None)
    monkeypatch.setattr(ct.wl_ci, "ci_cancel_cause", lambda *_a, **_k: cause)
    payload, _err = ct._snapshot(ct.REPO_ROOT, "main", {}, allow_branch=True, seen={})
    _rc, out, _e = _capture(ct._emit, payload, False)
    return payload, out


MAIN_CONTEXTS = [
    _ctx("Quality / Code"),
    _ctx("Validate Promotion", "CANCELLED", VP_A2),
    _ctx("Pipeline Sentinel", "FAILURE", 112065879532),
    _ctx("CI Complete", "FAILURE", 112065832113),
]


def test_branch_read_calls_the_cancellation_the_cause_when_every_failure_is_an_aggregator(
    ct, monkeypatch
):
    payload, out = _snap(ct, monkeypatch, MAIN_CONTEXTS)
    assert payload["verdict"] == "red"
    assert "the cancellation is the cause" in payload["detail"]
    assert "Validate Promotion" in payload["detail"]
    assert "for the failure above" not in payload["detail"]
    assert payload["cause"]["kind"] == "timeout-kill"
    assert [r["name"] for r in payload["failing"]] == ["Pipeline Sentinel", "CI Complete"]
    assert "why: .ci/scripts/ci/ci-trace.py --run %s --why" % MAIN_RUN in out


def test_branch_read_control_a_real_failure_keeps_the_cancelled_job_collateral(ct, monkeypatch):
    contexts = [*MAIN_CONTEXTS, _ctx("Quality / Static", "FAILURE", 5)]
    payload, _out = _snap(ct, monkeypatch, contexts)
    assert "cancelled alongside" in payload["detail"]
    assert payload["cause"] is None
    assert payload["failing"][0]["name"] == "Quality / Static", "root causes before aggregators"


# ---- --job <cancelled job> --errors ------------------------------------------------------


def test_job_errors_on_a_timeout_killed_job_names_the_cause_and_category(ct, monkeypatch):
    job = next(j for j in _jobs_a2() if j["id"] == VP_A2)
    routes = main_routes(**{"actions/jobs/%s" % VP_A2: dict(job, run_id=MAIN_RUN, run_attempt=2)})
    log = "2026-10-06T01:26:08.0Z ✓ Copying rpm/edge/ -> rpm/edge-promoted/ (server-side)\n"
    fetch = FakeFetch(routes, {"actions/jobs/%s/logs" % VP_A2: log})
    monkeypatch.setattr(ct, "_fetcher", lambda _root: fetch)
    rc, out, _err = _capture(ct.verb_job, ct.REPO_ROOT, VP_A2, "errors", False)
    assert rc == 0
    assert "  step: none failed or was cancelled" in out
    assert "  cause: timeout-kill: 'Validate Promotion' hit its timeout-minutes (15m0s)" in out
    assert "  category: timeout-cancel" in out
    # Control: the same job with no readable run has no cause to read, and says `unknown` rather than guessing.
    bare = FakeFetch(
        {"actions/jobs/%s" % VP_A2: dict(job, run_id=MAIN_RUN, run_attempt=2)},
        {"actions/jobs/%s/logs" % VP_A2: log},
    )
    monkeypatch.setattr(ct, "_fetcher", lambda _root: bare)
    _rc, out, _err = _capture(ct.verb_job, ct.REPO_ROOT, VP_A2, "errors", False)
    assert "  category: unknown" in out


# ---- --runs --ref main ---------------------------------------------------------------------

RUNS_MAIN = "runs_main_ci_20261006.json"


def test_runs_ref_main_lists_every_run_the_api_returned_newest_first(ct, monkeypatch):
    """`--runs --ref main` printed one stale 2026-10-01 schedule run where HEAD's tracer printed today's push runs (2026-10-06). The fixture is the five newest Console CI runs on main, in the API's shape."""
    payload = _load(RUNS_MAIN)
    paths = []

    class Fetch:
        def json(self, path):
            paths.append(path)
            return payload, ""

    monkeypatch.setattr(ct, "_fetcher", lambda _root: Fetch())
    rc, out, _err = _capture(ct.verb_runs, ct.REPO_ROOT, "main", False)
    assert rc == 0
    assert "branch=main&" in paths[0]
    ids = [ln.split()[0] for ln in out.splitlines()[1:]]
    assert ids == [
        "37437282770",
        "37437281526",
        "37428263878",
        "37394654719",
        "37273046804",
    ], out
    assert "00db8bed  push  2026-10-06T08:36:50Z" in out
    assert "36827121342" not in out


def test_planted_truncated_listing_fails_the_runs_test(ct, monkeypatch):
    """PLANTED RED: a reader that keeps only the last row (the shape of the reported regression) trips the id-list assertion above."""
    payload = _load(RUNS_MAIN)
    kept = dict(payload, workflow_runs=payload["workflow_runs"][-1:])

    class Fetch:
        def json(self, _path):
            return kept, ""

    monkeypatch.setattr(ct, "_fetcher", lambda _root: Fetch())
    _rc, out, _err = _capture(ct.verb_runs, ct.REPO_ROOT, "main", False)
    assert [ln.split()[0] for ln in out.splitlines()[1:]] != [
        "37437282770",
        "37437281526",
        "37428263878",
        "37394654719",
        "37273046804",
    ]


# ---- a RUNNING verdict names the run, its progress and what is still running ------------------

PR_RUN = 37422784744


def _running_jobs(now):
    def job(name, status, conclusion=None, started=None):
        return {
            "id": abs(hash(name)) % 10**9,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "started_at": started,
        }

    began = datetime.datetime.fromtimestamp(now - 305, datetime.UTC)
    return [
        job("Quality / Code", "completed", "success"),
        job("Quality / Static", "completed", "success"),
        job("Build / Docs", "completed", "skipped"),
        job("Stage Artifacts", "in_progress", None, began.strftime("%Y-%m-%dT%H:%M:%SZ")),
        job("CI Complete", "queued"),
    ]


def _running_snap(ct, monkeypatch, jobs):
    def run_ctx(name, status, conclusion=None):
        return {
            "__typename": "CheckRun",
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "databaseId": 9,
            "checkSuite": {"workflowRun": {"databaseId": PR_RUN}},
        }

    contexts = [
        run_ctx("Quality / Code", "COMPLETED", "SUCCESS"),
        run_ctx("Stage Artifacts", "IN_PROGRESS"),
        run_ctx("CI Complete", "QUEUED"),
    ]
    info = {
        "owner": "rediacc",
        "name": "console",
        "source": "pr",
        "pr": 596,
        "draft": False,
        "sha": "00db8bede" + "0" * 31,
        "rollup": "PENDING",
        "total": len(contexts),
        "contexts": contexts,
        "foreign": 0,
        "truncated": False,
    }
    monkeypatch.setattr(ct.wl_ci, "ci_rollup", lambda *_a, **_k: ("ok", info))
    monkeypatch.setattr(ct.D, "_p90_table", lambda: {"Stage Artifacts": 7.3})
    monkeypatch.setattr(
        ct,
        "_fetcher",
        lambda _root: FakeFetch(
            {"actions/runs/%s/jobs" % PR_RUN: {"jobs": jobs, "total_count": 5}}
        ),
    )
    payload, _err = ct._snapshot(ct.REPO_ROOT, "0006-1", {}, seen={})
    _rc, out, _e = _capture(ct._emit, payload, False)
    return payload, out


def test_running_verdict_names_the_run_progress_and_the_slow_job_with_its_p90(ct, monkeypatch):
    payload, out = _running_snap(ct, monkeypatch, _running_jobs(time.time()))
    assert payload["verdict"] == "running"
    assert payload["detail"].startswith("run %s: 3 of 5 job(s) done; still running: " % PR_RUN)
    # The job began 305 s before the snapshot; the read takes a moment, so the seconds are a small range, never a fixed value.
    assert re.search(r"Stage Artifacts 5m(?:0\d|1\d)s \(p90 7m18s\)", payload["detail"]), payload[
        "detail"
    ]
    assert "  " + payload["detail"] in out
    assert "context(s) still running" not in out


def test_running_verdict_without_readable_jobs_keeps_the_context_count(ct, monkeypatch):
    payload, out = _running_snap(ct, monkeypatch, [])
    assert payload["verdict"] == "running"
    assert "context(s) still in flight" in payload["detail"]
    assert "context(s) still running" in out


def test_run_still_queued_names_its_progress_in_the_gh_run_view_shape(ct, monkeypatch):
    """GitHub keeps a run `queued` while a job waits for a runner. `--run` read PR #597's run 37465283674 as "still queued" with 52 jobs passed and 19 running, and `gh run view` spells the start `startedAt`, which left every elapsed time `-`."""
    began = datetime.datetime.fromtimestamp(time.time() - 305, datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    jobs = [
        {"name": "Quality / Code", "status": "completed", "conclusion": "success"},
        {"name": "Stage Artifacts", "status": "in_progress", "conclusion": "", "startedAt": began},
        {"name": "CI Complete", "status": "queued", "conclusion": ""},
    ]
    monkeypatch.setattr(ct, "_run_snapshot", lambda _root, _rid: ("queued", "", jobs, "Console CI"))
    rc, out, err = _capture(ct._trace_run, ct.REPO_ROOT, MAIN_RUN, False, 1, False)
    assert rc == ct.EXIT_NO_VERDICT
    assert out == ""
    assert (
        "run %s still queued; run %s: 1 of 3 job(s) done; still running: "
        % (
            MAIN_RUN,
            MAIN_RUN,
        )
        in err
    )
    assert re.search(r"Stage Artifacts 5m(?:0\d|1\d)s", err), err
    assert "1 not started" in err
