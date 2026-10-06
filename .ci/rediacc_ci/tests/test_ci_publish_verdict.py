"""`rediacc_ci.ci.publish_ci_verdict` and the non-blocking exclusions of the `CI Verdict` context (agent/plans/PLAN-ci-verdict.md, box D).

NO NETWORK. The publisher's four GitHub calls go through an injectable object (`FakeGh` below), and `ci_diagnose` is injected through `main(loader=...)`, so these tests neither need W1's module to exist nor reach GitHub. The exclusion tests read the REAL tracked files (watchdog-monitor.yml, report-nightly-status.cjs, budget_report.py) and drive the real `evaluateBudget` under node, so a context added to one list and forgotten in another fails here.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import types

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import budget_report
from rediacc_ci.ci import publish_ci_verdict as pub
from rediacc_ci.core import gh_retry, ghx
from rediacc_ci.well_known import GH_REPO

# Built at runtime so the file itself holds no token-shaped string (check:ci-tracked-credentials scans tracked text).
FAKE_TOKEN = "ghp" + "_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

REPO = GH_REPO
SHA = "a7f305585530b61da88faf297b9d5805e5eb2b98"
RUN = "36953549081"
JOB = "Tests + Infra / E2E Workers (fedora-43, 1/8)"


def budget_verdict(attempt: int = 1) -> dict:
    """The 2026-10-02 shape: cancelled by the watchdog's job budget, no failed job."""
    return {
        "schema": "ci-verdict/v1",
        "generator": "ci_diagnose",
        "generated_at": "2026-10-02T02:40:00Z",
        "head_sha": SHA,
        "run_id": int(RUN),
        "attempt": attempt,
        "workflow": "Console CI",
        "conclusion": "cancelled",
        "verdict": "red",
        "cause": {
            "kind": "watchdog-budget",
            "detail": "job budget",
            "job": JOB,
            "minutes": 20.1,
            "budget_min": 20,
            "watchdog_run": 36953700000,
        },
        "first_failure": None,
        "gaps": [{"job": JOB, "after": "[setup] essentials", "seconds": 916}],
        "next": "ci-trace.py --watchdog %s" % RUN,
    }


def green_verdict(attempt: int = 2) -> dict:
    d = budget_verdict(attempt)
    d.update(conclusion="success", verdict="green", cause=None, gaps=[], next="")
    return d


def stub_loader(
    verdict: dict | None = None, *, raises: Exception | None = None, render_raises: bool = False
):
    calls: list = []

    def diagnose(fetch, run_id, attempt=None, pr_head=None):
        calls.append((fetch.kind, run_id, attempt, pr_head))
        if raises is not None:
            raise raises
        return json.loads(json.dumps(verdict))

    def render(d, budget_lines=12):
        assert budget_lines == pub.RENDER_BUDGET_LINES
        if render_raises:
            raise RuntimeError("render broke")
        head = "%s  Console CI run %s attempt %s" % (
            str(d.get("verdict")).upper(),
            d.get("run_id"),
            d.get("attempt"),
        )
        return "\n".join([head, "  cause: " + str((d.get("cause") or {}).get("kind"))])

    def fetcher(kind):
        return lambda repo, token=None: types.SimpleNamespace(kind=kind, repo=repo, token=token)

    mod = types.SimpleNamespace(
        diagnose=diagnose, render=render, HttpFetcher=fetcher("http"), GhFetcher=fetcher("gh")
    )
    return (lambda: mod), calls


class FakeGh:
    """Records every call; answers GETs from a dict of path-prefix -> body."""

    def __init__(
        self,
        existing: list | None = None,
        run: dict | None = None,
        lookup_fails: bool = False,
        write_rc: int = 0,
    ) -> None:
        self.existing = existing or []
        self.run = run or {
            "run_attempt": 1,
            "head_sha": SHA,
            "conclusion": "cancelled",
            "pull_requests": [],
        }
        self.lookup_fails = lookup_fails
        self.write_rc = write_rc
        self.gets: list[str] = []
        self.writes: list[tuple[str, str, dict]] = []

    def get(self, path: str):
        self.gets.append(path)
        if "/check-runs" in path:
            if self.lookup_fails:
                raise ghx.GhError(["gh", "api", path], 1, "HTTP 502", "unknown")
            return {"check_runs": self.existing}
        if "/actions/runs/" in path:
            return self.run
        raise AssertionError("unexpected GET %s" % path)

    def write(self, method: str, path: str, payload: dict) -> int:
        self.writes.append((method, path, payload))
        return self.write_rc


def existing_run(verdict: dict, cid: int = 77, slug: str = "github-actions") -> dict:
    return {"id": cid, "app": {"slug": slug}, "output": {"text": json.dumps(verdict)}}


def run_main(argv, gh, loader):
    out = io.StringIO()
    rc = pub.main(argv, gh=gh, loader=loader, out=out)
    return rc, out.getvalue()


# --------------------------------------------------------------------------- publisher


def test_posts_a_neutral_check_run_whose_title_names_the_watchdog_budget():
    loader, calls = stub_loader(budget_verdict())
    gh = FakeGh()
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    assert calls == [("gh", int(RUN), 1, SHA)], (
        "diagnose reads through gh, which carries the token itself"
    )
    [(method, path, body)] = gh.writes
    assert (method, path) == ("POST", "repos/%s/check-runs" % REPO)
    assert body["name"] == "CI Verdict"
    assert body["head_sha"] == SHA
    assert body["status"] == "completed"
    assert body["conclusion"] == "neutral"
    title = body["output"]["title"]
    assert "watchdog budget" in title
    assert JOB in title
    assert "20.1m" in title
    assert "(budget 20m)" in title
    assert "\n" not in title
    assert len(title) <= pub.TITLE_MAX
    assert body["output"]["summary"].startswith("RED  Console CI run")
    assert json.loads(body["output"]["text"])["cause"]["kind"] == "watchdog-budget"


def test_an_existing_check_run_is_patched_without_head_sha_and_green_overwrites_red():
    loader, _ = stub_loader(green_verdict(attempt=2))
    gh = FakeGh(existing=[existing_run(budget_verdict(attempt=1), cid=91)])
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "2", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    [(method, path, body)] = gh.writes
    assert (method, path) == ("PATCH", "repos/%s/check-runs/91" % REPO)
    assert "head_sha" not in body
    assert body["conclusion"] == "neutral"
    assert json.loads(body["output"]["text"])["verdict"] == "green"
    assert body["output"]["title"] == "GREEN Console CI run %s attempt 2" % RUN, (
        "no cause: the render headline"
    )


def test_an_older_attempt_never_overwrites_a_newer_one():
    loader, _ = stub_loader(budget_verdict(attempt=1))
    gh = FakeGh(existing=[existing_run(green_verdict(attempt=2))])
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    assert gh.writes == []


def test_a_check_run_from_another_app_is_not_patched():
    loader, _ = stub_loader(budget_verdict())
    gh = FakeGh(existing=[existing_run(budget_verdict(), slug="someone-else")])
    run_main(["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader)
    assert [w[0] for w in gh.writes] == ["POST"]


def test_a_failed_lookup_posts_rather_than_losing_the_verdict():
    loader, _ = stub_loader(budget_verdict())
    gh = FakeGh(lookup_fails=True)
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    assert [w[0] for w in gh.writes] == ["POST"]


def test_a_failed_diagnose_posts_unknown_instead_of_crashing():
    loader, _ = stub_loader(raises=RuntimeError("logs endpoint 502"))
    gh = FakeGh()
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    [(_m, _p, body)] = gh.writes
    doc = json.loads(body["output"]["text"])
    assert doc["schema"] == "ci-verdict/v1"
    assert doc["verdict"] == "unknown"
    assert "logs endpoint 502" in doc["next"]
    assert body["conclusion"] == "neutral"
    assert body["output"]["title"].startswith("unknown")


def test_a_missing_ci_diagnose_module_posts_unknown():
    def loader():
        raise ModuleNotFoundError("No module named 'rediacc_ci.ci.ci_diagnose'")

    gh = FakeGh()
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader
    )
    assert rc == 0
    assert json.loads(gh.writes[0][2]["output"]["text"])["verdict"] == "unknown"


def test_a_render_failure_keeps_the_verdict_with_a_fallback_summary():
    loader, _ = stub_loader(budget_verdict(), render_raises=True)
    gh = FakeGh()
    run_main(["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader)
    body = gh.writes[0][2]
    assert "watchdog budget" in body["output"]["summary"]
    assert json.loads(body["output"]["text"])["cause"]["kind"] == "watchdog-budget"


def test_excerpts_are_sanitised_before_they_leave():
    d = budget_verdict()
    d["first_failure"] = {
        "job_id": 1,
        "name": "Quality / Static",
        "step": "lint",
        "step_s": 30,
        "p90_s": 20,
        "category": "code-likely",
        "signature": "Error:",
        "excerpt": [
            "\x1b[31mError:\x1b[0m token " + FAKE_TOKEN + " leaked\x07",
            "Authorization: Bearer abc.def.ghi",
            "password=hunter2hunter2",
        ],
    }
    loader, _ = stub_loader(d)
    gh = FakeGh()
    run_main(["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO], gh, loader)
    text = gh.writes[0][2]["output"]["text"]
    assert FAKE_TOKEN[:10] not in text
    assert "abc.def.ghi" not in text
    assert "hunter2" not in text
    assert "\\u001b" not in text
    assert "\\u0007" not in text
    excerpt = json.loads(text)["first_failure"]["excerpt"]
    assert excerpt[0] == "Error: token *** leaked"
    assert excerpt[1] == "Authorization: Bearer ***"


def test_sanitise_leaves_ordinary_log_text_alone():
    line = "--- FAIL: TestSetup (916.02s)\n\tsetup_command.go:257: essentials phase"
    assert pub.sanitise_text(line) == line


def test_the_dispatch_path_resolves_attempt_and_head_from_the_run():
    loader, calls = stub_loader(budget_verdict(attempt=2))
    pr_head = "f" * 40
    gh = FakeGh(
        run={
            "run_attempt": 2,
            "head_sha": SHA,
            "conclusion": "cancelled",
            "pull_requests": [{"head": {"sha": pr_head}}],
        }
    )
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "", "--head-sha", "", "--repo", REPO], gh, loader
    )
    assert rc == 0
    assert any(p.endswith("/actions/runs/%s" % RUN) for p in gh.gets)
    assert calls == [("gh", int(RUN), 2, pr_head)], (
        "superseded attribution needs the PR's head, not the run's"
    )
    assert gh.writes[0][2]["head_sha"] == SHA, "the verdict is posted on the RUN's head"


def test_dry_run_prints_the_payload_and_writes_nothing():
    loader, _ = stub_loader(budget_verdict())
    gh = FakeGh()
    rc, out = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO, "--dry-run"],
        gh,
        loader,
    )
    assert rc == 0
    assert gh.writes == []
    first, rest = out.split("\n", 1)
    assert first == "would POST repos/%s/check-runs" % REPO
    assert json.loads(rest)["output"]["title"].startswith("cancelled by watchdog budget")


def test_a_failed_write_exits_nonzero():
    loader, _ = stub_loader(budget_verdict())
    rc, _ = run_main(
        ["--run-id", RUN, "--attempt", "1", "--head-sha", SHA, "--repo", REPO],
        FakeGh(write_rc=1),
        loader,
    )
    assert rc == 1


def test_a_non_numeric_run_id_is_refused_before_any_call():
    loader, calls = stub_loader(budget_verdict())
    gh = FakeGh()
    rc, _ = run_main(["--run-id", "../x", "--repo", REPO], gh, loader)
    assert rc == 1
    assert gh.gets == []
    assert gh.writes == []
    assert calls == []


def test_an_oversized_document_drops_excerpts_rather_than_emitting_broken_json():
    d = budget_verdict()
    d["first_failure"] = {"name": "x", "excerpt": ["y" * 1000] * 100}
    text = pub.verdict_json(d)
    assert len(text) <= pub.OUTPUT_MAX
    assert json.loads(text)["first_failure"]["excerpt"] == []


# --------------------------------------------------------------------------- the context is non-blocking everywhere


def _root():
    return paths.repo_root()


def test_the_watchdog_excludes_the_verdict_context_and_its_publisher_job():
    yml = (_root() / ".github/workflows/watchdog-monitor.yml").read_text(encoding="utf-8")
    line = next(ln for ln in yml.splitlines() if "WATCHDOG_EXCLUDE_PATTERNS:" in ln)
    patterns = [p.strip() for p in line.split(":", 1)[1].strip().strip("'\"").split(",")]
    for name in ("CI Verdict", "Publish CI Verdict"):
        assert any(p in name for p in patterns), "%r is not excluded by %r" % (name, patterns)


def test_the_nightly_report_excludes_the_verdict_context():
    cjs = (_root() / ".ci/scripts/ci/report-nightly-status.cjs").read_text(encoding="utf-8")
    tail = cjs.split("NIGHTLY_BUDGET_EXCLUDE_PATTERNS ||", 1)[1]
    default = tail.split("'")[1]
    assert "CI Verdict" in default.split(","), default


def test_the_critical_path_skips_the_verdict_context():
    assert "CI Verdict" in budget_report.CRITICAL_PATH_EXCLUDE
    assert "Publish CI Verdict" in budget_report.CRITICAL_PATH_EXCLUDE


NODE = shutil.which("node")

BUDGET_JS = r"""
const m = require(process.argv[1]);
const fx = JSON.parse(process.argv[2]);
const r = m.evaluateBudget({jobs: fx.jobs, run: null, nowMs: fx.now, jobBudgetMin: 15, runBudgetMin: null,
  excludePatterns: fx.patterns, jobMode: 'enforce'});
console.log(JSON.stringify({names: r.jobViolations.map((v) => v.name),
  notes: fx.jobs.map((j) => m.budgetStepNote(j, fx.now))}));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_an_over_budget_verdict_job_never_violates_and_the_note_names_the_live_step():
    yml = (_root() / ".github/workflows/watchdog-monitor.yml").read_text(encoding="utf-8")
    line = next(ln for ln in yml.splitlines() if "WATCHDOG_EXCLUDE_PATTERNS:" in ln)
    patterns = [p.strip() for p in line.split(":", 1)[1].strip().strip("'\"").split(",")]
    now = 1_000_000_000_000
    # now is 2001-09-09T01:46:40Z.
    started = "2001-09-09T01:40:00.000Z"  # now - 6m40s
    old = "2001-09-09T01:13:20.000Z"  # now - 33m20s
    jobs = [
        {"name": "Publish CI Verdict", "status": "in_progress", "started_at": old, "steps": []},
        {"name": "CI Verdict", "status": "in_progress", "started_at": old, "steps": []},
        {
            "name": JOB,
            "status": "in_progress",
            "started_at": old,
            "steps": [
                {"name": "Checkout", "status": "completed", "started_at": old, "completed_at": old},
                {
                    "name": "Run E2E",
                    "status": "in_progress",
                    "started_at": started,
                    "completed_at": None,
                },
            ],
        },
    ]
    script = _root() / ".ci/scripts/ci/watchdog-monitor.cjs"
    assert NODE is not None
    proc = subprocess.run(
        [
            NODE,
            "-e",
            BUDGET_JS,
            str(script),
            json.dumps({"jobs": jobs, "now": now, "patterns": patterns}),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["names"] == [JOB]
    assert got["notes"][2] == " -- in step 'Run E2E' for 6.7m"
    assert got["notes"][0] == ""


def test_github_get_retries_a_transient_5xx_and_not_a_4xx(monkeypatch):
    """The verdict publisher's reads ride gh_retry (sweep of f92f55e63): a 502 is retried, a 404 fails at once."""
    calls: list[list[str]] = []
    answers = [(1, "", "gh: Server Error (HTTP 502)"), (0, '{"ok": true}', "")]

    def runner(args, **_kw):
        calls.append(list(args))
        rc, out, err = answers.pop(0)
        return ghx.GhResult(["gh", *args], rc, out, err)

    monkeypatch.setattr(gh_retry.ghx, "gh", runner)
    monkeypatch.setattr(gh_retry.time, "sleep", lambda _s: None)
    assert pub.GitHub("a/b").get("repos/a/b/x") == {"ok": True}
    assert len(calls) == 2

    calls.clear()
    answers[:] = [(1, "", "gh: Not Found (HTTP 404)")]
    try:
        pub.GitHub("a/b").get("repos/a/b/missing")
    except ghx.GhError:
        pass
    else:
        raise AssertionError("a 404 must raise")
    assert len(calls) == 1
