"""`rediacc_ci.ci.ci_diagnose`, driven against the REAL run that motivated it.

Console CI run 36953549081 (PR #591, head a7f30558, attempt 1) was cancelled with nothing failed. The fixtures under `fixtures/ci_diagnose/` are that run's own API answers, trimmed to the fields read and passed through `sanitize()`: the run, its 166 jobs, the head's run list, Watchdog Monitor run 36956399799's job and annotations, and the budget-violating job's log (every line of the failing step, and one line per
30 s outside it, so no silence is manufactured). The four `synthetic_*.log` files are hand-written shapes for the signatures that run does not carry.

HERMETIC. A dict-backed fetcher serves the fixtures and records every path asked for; nothing here reaches GitHub, and a path with no fixture answers an error rather than an empty success, so a read the code did not mean to make fails loudly.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from rediacc_ci.ci import ci_diagnose as D

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "ci_diagnose"
RUN = 36953549081
JOB = 110673642600
HEAD = "a7f305585530b61da88faf297b9d5805e5eb2b98"
BUDGET_JOB = "Tests + Infra / E2E Workers (fedora-43, 1/8)"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeFetch:
    """Answers from a {path-prefix: payload} table and records every call."""

    def __init__(self, routes, texts=None):
        self.routes = routes
        self.texts = texts or {}
        self.calls = []

    def json(self, path):
        self.calls.append(path)
        for prefix, payload in self.routes.items():
            if path == prefix or path.startswith(prefix + "?"):
                return payload, ""
        return None, "no fixture for %s" % path

    def text(self, path):
        self.calls.append(path)
        if path in self.texts:
            return self.texts[path], ""
        return None, "no fixture for %s" % path


def real_routes(**over):
    jobs = _load("jobs_36953549081_attempt1.json")
    routes = {
        "actions/runs/%s/attempts/1" % RUN: _load("run_36953549081_attempt1.json"),
        "actions/runs/%s/attempts/1/jobs" % RUN: jobs,
        "actions/runs": _load("runs_head_a7f30558.json"),
        "actions/runs/36956399799/jobs": _load("watchdog_jobs_36956399799.json"),
        "check-runs/110680194371/annotations": _load("annotations_110680194371.json"),
        "check-runs/%s/annotations" % JOB: _load("annotations_110673642600.json"),
    }
    routes.update(over)
    return routes


def real_texts():
    return {
        "actions/jobs/%s/logs" % JOB: (FIX / "job_110673642600.log").read_text(encoding="utf-8")
    }


def the_job():
    return next(j for j in _load("jobs_36953549081_attempt1.json")["jobs"] if j["id"] == JOB)


# ---- the real run ---------------------------------------------------------------


def test_the_real_run_reads_cancelled_by_the_watchdog_budget(tmp_path):
    fetch = FakeFetch(real_routes(), real_texts())
    d = D.diagnose(fetch, RUN, attempt=1, cache_dir=tmp_path)
    assert d["schema"] == "ci-verdict/v1"
    assert d["verdict"] == "cancelled"
    assert d["head_sha"] == HEAD
    cause = d["cause"]
    assert cause["kind"] == "watchdog-budget", cause
    assert cause["job"] == BUDGET_JOB
    assert cause["minutes"] == 20.1
    assert cause["budget_min"] == 20
    assert cause["watchdog_run"] == 36956399799
    ff = d["first_failure"]
    assert ff["job_id"] == JOB
    assert ff["step"] == "Run E2E Tests (Workers)"
    assert ff["category"] == "infra-likely"
    assert ff["signature"] == "slow-setup"
    assert ff["p90_s"] == 540, "the job's recorded p90 (9.0m) must be quoted beside its 1069 s step"
    assert any("(916s)" in ln for ln in ff["excerpt"]), ff["excerpt"]
    assert d["next"] == ".ci/scripts/ci/ci-trace.py --job %s --errors" % JOB


def test_the_real_run_names_the_900_second_silence(tmp_path):
    """The whole log never went quiet for more than ~500 s; rediacc11's own stream did, for ~950 s."""
    d = D.diagnose(FakeFetch(real_routes(), real_texts()), RUN, attempt=1, cache_dir=tmp_path)
    top = d["gaps"][0]
    assert top["stream"] == "rediacc11", d["gaps"]
    assert 900 <= top["s"] <= 1000, d["gaps"]
    assert all(g["s"] < 600 for g in d["gaps"] if g["stream"] == ""), d["gaps"]


def test_render_is_bounded_and_names_cause_gap_and_next(tmp_path):
    d = D.diagnose(FakeFetch(real_routes(), real_texts()), RUN, attempt=1, cache_dir=tmp_path)
    text = D.render(d)
    lines = text.splitlines()
    assert len(lines) <= 12, text
    assert len(text) <= 1500, text
    assert lines[0].startswith("CANCELLED  Console CI run %s attempt 1 @ a7f30558" % RUN)
    assert "watchdog-budget" in text
    assert "ran 20.1m (budget 20m)" in text
    assert "947s silent on vm=rediacc11" in text
    assert "newer push" not in text
    assert lines[-1] == "  next: .ci/scripts/ci/ci-trace.py --job %s --errors" % JOB


def test_render_budget_holds_on_a_huge_excerpt():
    d = {
        "verdict": "red",
        "run_id": 1,
        "first_failure": {"name": "x" * 400, "excerpt": ["y" * 400] * 50, "job_id": 2},
        "gaps": [{"s": 999, "stream": "", "at": "00:00:00", "before": "z" * 400}] * 3,
        "next": "n" * 400,
        "cause": {"kind": "unknown", "detail": "d" * 400},
    }
    text = D.render(d)
    assert len(text.splitlines()) <= 12
    assert len(text) <= 1500


def test_the_watchdog_read_is_bounded():
    fetch = FakeFetch(real_routes(), real_texts())
    D.cancel_cause(
        fetch,
        _load("run_36953549081_attempt1.json"),
        jobs=_load("jobs_36953549081_attempt1.json")["jobs"],
    )
    assert len(fetch.calls) <= 4, fetch.calls


# ---- cancel attribution: controls ----------------------------------------------


def test_superseded_when_the_pr_head_moved():
    routes = real_routes(**{"actions/runs/36956399799/jobs": {"jobs": []}})
    run = _load("run_36953549081_attempt1.json")
    cause = D.cancel_cause(FakeFetch(routes), run, pr_head="b" * 40, jobs=[])
    assert cause["kind"] == "superseded"
    assert "bbbbbbbb" in cause["detail"]


def test_unknown_when_nothing_proves_a_cause():
    routes = real_routes(**{"actions/runs": {"workflow_runs": []}})
    cause = D.cancel_cause(
        FakeFetch(routes), _load("run_36953549081_attempt1.json"), pr_head=HEAD, jobs=[]
    )
    assert cause["kind"] == "unknown"
    assert "not proven superseded" in cause["detail"]


def test_timeout_kill_without_watchdog_evidence():
    routes = real_routes(**{"actions/runs": {"workflow_runs": []}})
    cause = D.cancel_cause(
        FakeFetch(routes), _load("run_36953549081_attempt1.json"), jobs=[the_job()]
    )
    assert cause["kind"] == "timeout-kill", cause
    assert cause["job"] == BUDGET_JOB, cause


def test_manual_cancel_by_a_person_and_not_by_a_bot():
    run = _load("run_36953549081_attempt1.json")
    job = dict(the_job(), id=7)
    base: dict[str, object] = {"actions/runs": {"workflow_runs": []}}
    person = [{"title": "", "message": "The run was canceled forcefully by @someone."}]
    bot = [{"title": "", "message": "The run was canceled forcefully by @github-actions[bot]."}]
    got = D.cancel_cause(
        FakeFetch(dict(base, **{"check-runs/7/annotations": person})), run, jobs=[job]
    )
    assert got["kind"] == "manual"
    assert "@someone" in got["detail"]
    got = D.cancel_cause(
        FakeFetch(dict(base, **{"check-runs/7/annotations": bot})), run, jobs=[job]
    )
    assert got["kind"] == "unknown"


def test_watchdog_failure_cancel_without_a_budget_line():
    ann = [
        {
            "title": "Watchdog: pipeline-cancelled",
            "message": "Pipeline cancelled by the watchdog: Quality / Static failed",
        }
    ]
    routes = real_routes(**{"check-runs/110680194371/annotations": ann})
    cause = D.cancel_cause(FakeFetch(routes), _load("run_36953549081_attempt1.json"), jobs=[])
    assert cause["kind"] == "watchdog-failure"
    assert "Quality / Static" in cause["detail"]


def test_report_only_budget_line_is_not_a_cause():
    ann = [
        {
            "title": "",
            "message": "CI BUDGET VIOLATION (report-only): 'whole pipeline' at 37.8m, budget 35m",
        }
    ]
    routes = real_routes(
        **{
            "check-runs/110680194371/annotations": ann,
            "actions/runs/36956399799/jobs": _load("watchdog_jobs_36956399799.json"),
        }
    )
    cause = D.cancel_cause(
        FakeFetch(routes), _load("run_36953549081_attempt1.json"), pr_head=HEAD, jobs=[]
    )
    assert cause["kind"] != "watchdog-budget"


def test_a_watchdog_run_from_a_later_attempt_is_not_this_attempts_evidence():
    run = dict(
        _load("run_36953549081_attempt1.json"),
        run_started_at="2026-10-02T05:54:59Z",
        updated_at="2026-10-02T06:30:00Z",
    )
    cause = D.cancel_cause(FakeFetch(real_routes()), run, pr_head=HEAD, jobs=[])
    assert cause["kind"] != "watchdog-budget", cause


# ---- the rest of the verdict -----------------------------------------------------


def test_a_failed_job_is_red_and_never_a_nonblocking_one():
    jobs = [
        {
            "id": 1,
            "name": "Publish CI Verdict",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 2,
            "name": "CI Verdict",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:00:01Z",
        },
        {
            "id": 3,
            "name": "Quality / Static",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:05:00Z",
        },
        {
            "id": 4,
            "name": "Quality / Code",
            "conclusion": "timed_out",
            "completed_at": "2026-01-01T00:03:00Z",
        },
    ]
    assert D.first_failure(jobs)["id"] == 4
    assert D.first_failure(jobs[:2]) is None


def test_the_advisory_pr_review_is_never_the_first_failure():
    # PLAN-github-pr-review-restore GR4: the PR review is advisory, so its three check names never become a red verdict's cause, while Review Gate (a Console CI job) still does.
    jobs = [
        {
            "id": 1,
            "name": "Review Complete",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 2,
            "name": "Review Status",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:00:01Z",
        },
        {
            "id": 3,
            "name": "Claude Review",
            "conclusion": "timed_out",
            "completed_at": "2026-01-01T00:00:02Z",
        },
    ]
    assert D.first_failure(jobs) is None
    gate = {
        "id": 4,
        "name": "Review Gate",
        "conclusion": "failure",
        "completed_at": "2026-01-01T00:00:03Z",
    }
    assert D.first_failure([*jobs, gate])["id"] == 4
    for name in ("Review Complete", "Review Status", "Claude Review"):
        assert not D._blocking(name), name
        assert D._aggregator(name), name
    # The aggregator match is a substring match, so none of the three may hide inside Review Gate.
    assert not D._aggregator("Review Gate")


def test_green_run_has_no_next_and_unreadable_run_says_why():
    run = {
        "id": 5,
        "name": "Console CI",
        "status": "completed",
        "conclusion": "success",
        "head_sha": HEAD,
        "run_attempt": 1,
    }
    jobs = {"total_count": 1, "jobs": [{"id": 9, "name": "Build", "conclusion": "success"}]}
    d = D.diagnose(FakeFetch({"actions/runs/5": run, "actions/runs/5/attempts/1/jobs": jobs}), 5)
    assert d["verdict"] == "green"
    assert d["next"] == ""
    assert d["cause"] is None
    d = D.diagnose(FakeFetch({}), 6)
    assert d["verdict"] == "unknown"
    assert "could not read run 6" in d["next"]


def test_failing_step_slice_picks_the_cancelled_step():
    log = (FIX / "job_110673642600.log").read_text(encoding="utf-8")
    step, lines = D.failing_step_slice(log, the_job())
    assert step == "Run E2E Tests (Workers)"
    assert lines
    assert all(ln >= "2026-10-02T02:22:5" for ln in lines), lines[:2]
    # The Bitwarden 503 at 02:20:44 was retried and passed; it sits OUTSIDE the slice and must not classify the job.
    assert not any("bws-secrets" in ln for ln in lines)
    assert D.classify(log.splitlines())[1] == "bitwarden-5xx"
    assert D.classify(lines) == ("infra-likely", "slow-setup")


def test_job_log_is_cached_once_complete(tmp_path):
    fetch = FakeFetch({}, {"actions/jobs/1/logs": "\x1b[36mhello\x1b[0m\n"})
    assert D.job_log(fetch, 1, cache_dir=tmp_path) == ("hello\n", "")
    assert D.job_log(fetch, 1, cache_dir=tmp_path) == ("hello\n", "")
    assert fetch.calls == ["actions/jobs/1/logs"]
    live = FakeFetch({}, {"actions/jobs/2/logs": "x\n"})
    D.job_log(live, 2, completed=False, cache_dir=tmp_path)
    D.job_log(live, 2, completed=False, cache_dir=tmp_path)
    assert len(live.calls) == 2
    assert not (tmp_path / "2.log").exists()


# ---- gaps: anti-vacuity ------------------------------------------------------------


def test_log_gaps_min_s_is_load_bearing():
    log = (FIX / "job_110673642600.log").read_text(encoding="utf-8")
    assert D.log_gaps(log, min_s=120)
    assert D.log_gaps(log, min_s=2000) == []
    tiny = "2026-01-01T00:00:00.0Z a\n2026-01-01T00:01:59.0Z b\n2026-01-01T00:04:00.0Z c\n"
    assert [g["s"] for g in D.log_gaps(tiny, min_s=120)] == [121]


# ---- signatures: a hit and a near miss for every row ------------------------------

SIG_CASES = {
    "bitwarden-5xx": (
        "bws-secrets: attempt 4 of 4 failed (Received error message from server: [502 Bad Gateway])",
        "bws-secrets: fetch succeeded on attempt 2 of 4",
    ),
    "registry-refused": (
        "Error response from daemon: unexpected status code 403 Forbidden for https://x",
        "served 403 requests from the Forbidden City cache",
    ),
    "runner-lost": (
        "The runner has received a shutdown signal. This can happen when ...",
        "Runner shutdown hooks registered",
    ),
    "pkg-mirror": (
        "Curl error (28): Timeout was reached for https://mirror/repodata/repomd.xml",
        "Metadata cache created.",
    ),
    "network": (
        "read tcp 10.0.0.1:443: read: ECONNRESET",
        "ECONNRESETS_TOTAL=0 counter exported",
    ),
    "slow-setup": (
        'level=info msg="[setup] essentials end 1790908732 (916s)" vm=rediacc11',
        'level=info msg="[setup] essentials end 1790907838 (23s)" vm=rediacc1',
    ),
    "go-fail": ("--- FAIL: TestPkgInstallRetry (0.50s)", "--- PASS: TestPkgInstallRetry (0.50s)"),
    "gate-finding": (
        "::finding::P-A1:b7ac548bf529",
        "findings: 0 (::finding:: lines would appear here)",
    ),
    "pytest-failed": (
        "FAILED tests/test_x.py::test_y - AssertionError",
        "collected 3 items; 0 FAILED",
    ),
    "assertion": ("AssertionError: expected 2, got 3", "assertions: 12 passed"),
    "playwright-fail": (
        "  ✘  1 [chromium] login.spec.ts:3:1 logs in (5.2s)",
        "  ✓  1 [chromium] login.spec.ts",
    ),
    "panic": ("panic: runtime error: index out of range", "panicked=false; no panics recorded"),
    "error": ("Error: Cannot find module 'x'", "##[error]Process completed with exit code 1."),
}


def test_every_signature_has_a_case():
    assert {row[0] for row in D.SIGNATURES} == set(SIG_CASES)


@pytest.mark.parametrize("sid", sorted(SIG_CASES))
def test_signature_hit_and_near_miss(sid):
    hit, miss = SIG_CASES[sid]
    got = D._sig_hit("2026-01-01T00:00:00.0000000Z " + hit)
    assert got is not None, sid
    assert got[0] == sid, (sid, got)
    near = D._sig_hit("2026-01-01T00:00:00.0000000Z " + miss)
    assert near is None or near[0] != sid, (sid, near)


@pytest.mark.parametrize(
    ("name", "category", "sid"),
    [
        ("synthetic_cdn_403.log", "infra-likely", "registry-refused"),
        ("synthetic_bitwarden_5xx.log", "infra-likely", "bitwarden-5xx"),
        ("synthetic_runner_shutdown.log", "infra-likely", "runner-lost"),
        ("synthetic_code_failure.log", "code-likely", "go-fail"),
    ],
)
def test_synthetic_logs_classify(name, category, sid):
    lines = (FIX / name).read_text(encoding="utf-8").splitlines()
    assert D.classify(lines) == (category, sid)
    ex = D.excerpt(lines)
    assert ex
    assert len(ex) <= 3 * 8 + 2
    assert all(len(ln) <= 200 for ln in ex)


def test_excerpt_limits():
    lines = [
        "2026-01-01T00:00:%02d.0Z Error: boom %d %s" % (i % 60, i, "x" * 300) for i in range(40)
    ]
    ex = D.excerpt(lines)
    windows = "\n".join(ex).split("\n--\n")
    assert len(windows) <= 3
    assert all(len(w.splitlines()) <= 8 for w in windows)
    assert all(len(ln) <= 200 for ln in ex)


def test_sanitize_redacts_tokens_and_keeps_prose():
    raw = "token ghp_abcdefghijklmnopqrstuvwxyz0123 and https://user:hunter2@example.com/x ok"
    out = D.sanitize(raw)
    assert "ghp_" not in out
    assert "hunter2" not in out
    assert out.endswith("ok")
    assert D.sanitize("The operation was canceled.") == "The operation was canceled."


def test_fixtures_carry_no_secret_shapes():
    for path in sorted(FIX.iterdir()):
        text = path.read_text(encoding="utf-8")
        assert D.sanitize(text) == text, "%s carries a secret-shaped string" % path.name


def test_schema_keys_are_the_contract():
    d = D._blank(1, 1, None)
    assert set(d) == {
        "schema",
        "generator",
        "generated_at",
        "head_sha",
        "run_id",
        "attempt",
        "workflow",
        "conclusion",
        "verdict",
        "cause",
        "first_failure",
        "gaps",
        "next",
    }


def test_the_failing_step_ends_at_its_own_exit_line():
    """Job 110735213399 (Quality / Branch): the next step's opening lines shared the failing step's last second."""
    job = {
        "steps": [
            {
                "name": "Plan implementation clock",
                "conclusion": "failure",
                "started_at": "2026-10-02T06:38:14Z",
                "completed_at": "2026-10-02T06:39:11Z",
            },
        ]
    }
    log = (
        "2026-10-02T06:38:20.0Z   P-A1 OPEN BOXES: 1 plan(s) carry open boxes\n"
        "2026-10-02T06:39:11.2036718Z ::finding::P-A1:b7ac548bf529\n"
        "2026-10-02T06:39:11.2364048Z ##[error]Process completed with exit code 1.\n"
        "2026-10-02T06:39:11.2417592Z ##[group]Run npm run check:ci-plan-record\n"
    )
    step, lines = D.failing_step_slice(log, job)
    assert step == "Plan implementation clock"
    assert lines[-1].endswith("exit code 1.")
    assert D.classify(lines) == ("code-likely", "gate-finding")


def test_history_says_when_a_run_could_not_be_read():
    runs = {
        "workflow_runs": [
            {"id": 1, "head_branch": "b", "head_sha": "a" * 40, "run_attempt": 1},
            {"id": 2, "head_branch": "b", "head_sha": "b" * 40, "run_attempt": 1},
        ]
    }
    jobs = {"total_count": 1, "jobs": [{"id": 9, "name": "J", "conclusion": "success"}]}
    rows = D.history(
        FakeFetch({"actions/workflows/ci.yml/runs": runs, "actions/runs/2/jobs": jobs}), "J"
    )
    assert [r["conclusion"] for r in rows] == ["unreadable", "success"]
