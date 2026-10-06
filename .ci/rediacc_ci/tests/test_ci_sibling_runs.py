"""`rediacc_ci.ci.sibling_runs`: the duplicate-run skip and the release gate's sibling check, against a fake GitHub API (no network, no sleep).

The fixtures are shaped on the 2026-10-06 incident: one merge (00db8bed) produced Console CI push runs 37437281526 and 37437282770 on the same sha.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import sibling_runs as sr
from rediacc_ci.core import ghx
from rediacc_ci.well_known import GH_ORIGIN, GH_REPO

if TYPE_CHECKING:
    import pathlib

SHA = "00db8bed" + "0" * 32
REPO = GH_REPO
FIRST = 37437281526
SECOND = 37437282770
SERVER_ERROR = "gh: Server Error (HTTP 502)"
NOT_FOUND = "gh: Not Found (HTTP 404)"


def run(rid: int, status: str = "completed", conclusion: str | None = "success", **kw) -> dict:
    return {
        "id": rid,
        "status": status,
        "conclusion": conclusion,
        "event": kw.get("event", "push"),
        "head_sha": kw.get("sha", SHA),
        "html_url": "%s/%s/actions/runs/%d" % (GH_ORIGIN, REPO, rid),
    }


class FakeApi:
    """A `gh` one-attempt runner answering from a table: runs on the sha, and per-run Initialize conclusions. A missing jobs entry is a 404; `runs=None` makes the listing a 502 on every attempt."""

    def __init__(
        self,
        runs: list[dict] | None,
        initialize: dict[int, str] | None = None,
        jobs: dict[int, list[dict]] | None = None,
    ) -> None:
        self.runs = runs
        self.initialize = initialize or {}
        self.jobs = jobs or {}
        self.calls: list[str] = []

    def __call__(self, args: list[str], **_kw) -> ghx.GhResult:
        path = args[1]
        self.calls.append(path)
        if "/actions/workflows/" in path:
            if self.runs is None:
                return ghx.GhResult(["gh", *args], 1, "", SERVER_ERROR)
            return ghx.GhResult(["gh", *args], 0, json.dumps({"workflow_runs": self.runs}), "")
        match = re.search(r"/runs/(\d+)/jobs", path)
        assert match, path
        rid = int(match.group(1))
        if rid in self.jobs:
            return ghx.GhResult(["gh", *args], 0, json.dumps({"jobs": self.jobs[rid]}), "")
        if rid not in self.initialize:
            return ghx.GhResult(["gh", *args], 1, "", NOT_FOUND)
        body = {"jobs": [{"name": "Build CLI", "conclusion": "success"}]}
        body["jobs"].append({"name": "Initialize", "conclusion": self.initialize[rid]})
        return ghx.GhResult(["gh", *args], 0, json.dumps(body), "")


def drive(
    command: str,
    fake: FakeApi,
    own: int,
    tmp_path: pathlib.Path,
    event: str = "push",
    attempt: int | None = None,
) -> tuple[int, str, str]:
    out, summary = tmp_path / "out", tmp_path / "summary"
    out.write_text("")
    summary.write_text("")
    api = sr.Api(REPO, "ci.yml", runner=fake, sleep=lambda _s: None)
    argv = [command, "--repo", REPO, "--sha", SHA, "--run-id", str(own), "--event", event]
    argv += ["--output", str(out), "--summary", str(summary)]
    if attempt is not None:
        argv += ["--run-attempt", str(attempt)]
    rc = sr.main(argv, api)
    return rc, out.read_text(), summary.read_text()


# ---- rule 1: the duplicate run is a no-op ------------------------------------------------------------------------


def test_the_incidents_second_run_is_a_duplicate_of_the_green_first(tmp_path, capsys):
    fake = FakeApi([run(SECOND, "in_progress", None), run(FIRST)], {FIRST: "success"})
    rc, out, summary = drive("dedupe", fake, SECOND, tmp_path)
    assert rc == 0
    assert out == "duplicate_of=%d\n" % FIRST
    assert str(FIRST) in summary
    assert SHA in summary
    assert "DUPLICATE" in capsys.readouterr().err


def test_a_sibling_still_running_makes_this_run_a_duplicate(tmp_path):
    fake = FakeApi(
        [run(SECOND, "queued", None), run(FIRST, "in_progress", None)], {FIRST: "success"}
    )
    assert drive("dedupe", fake, SECOND, tmp_path)[1] == "duplicate_of=%d\n" % FIRST


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_an_earlier_red_or_cancelled_run_does_not_skip_a_retry(tmp_path, conclusion):
    fake = FakeApi([run(SECOND, "in_progress", None), run(FIRST, conclusion=conclusion)])
    rc, out, summary = drive("dedupe", fake, SECOND, tmp_path)
    assert (rc, out, summary) == (0, "", "")


def test_the_first_run_never_skips_on_a_later_sibling(tmp_path):
    """Only LOWER run ids count, so two runs can never skip each other."""
    fake = FakeApi(
        [run(SECOND, "queued", None), run(FIRST, "in_progress", None)], {SECOND: "success"}
    )
    assert drive("dedupe", fake, FIRST, tmp_path)[1] == ""


def test_this_runs_own_reattempt_is_not_a_sibling(tmp_path):
    """A re-run attempt keeps the run id; the listing shows this run as completed success from attempt 1."""
    fake = FakeApi([run(FIRST)], {FIRST: "success"})
    assert drive("dedupe", fake, FIRST, tmp_path)[1] == ""


def test_a_green_noop_sibling_is_not_an_original(tmp_path):
    """Run 1 failed after run 2 skipped as its duplicate. Run 2's green is empty: run 3 must proceed."""
    third = SECOND + 7
    fake = FakeApi(
        [run(third, "in_progress", None), run(SECOND), run(FIRST, conclusion="failure")],
        {SECOND: "skipped"},
    )
    assert drive("dedupe", fake, third, tmp_path)[1] == ""


def test_a_running_noop_sibling_is_not_an_original(tmp_path):
    """A sibling still running whose Initialize already skipped is itself a duplicate (or a bot push): it will never produce a verdict, so it cannot stand in for one."""
    fake = FakeApi(
        [run(SECOND, "in_progress", None), run(FIRST, "in_progress", None)], {FIRST: "skipped"}
    )
    assert drive("dedupe", fake, SECOND, tmp_path)[1] == ""


def test_a_green_sibling_whose_jobs_cannot_be_read_is_not_counted(tmp_path, capsys):
    fake = FakeApi([run(SECOND, "in_progress", None), run(FIRST)], {})
    assert drive("dedupe", fake, SECOND, tmp_path)[1] == ""
    assert "could not be read" in capsys.readouterr().err


def test_other_shas_and_other_events_are_ignored(tmp_path):
    fake = FakeApi(
        [
            run(SECOND, "in_progress", None),
            run(FIRST, sha="f" * 40),
            run(FIRST - 1, event="workflow_dispatch"),
        ],
        {FIRST: "success", FIRST - 1: "success"},
    )
    assert drive("dedupe", fake, SECOND, tmp_path)[1] == ""


def test_an_unreadable_api_proceeds_and_says_so(tmp_path, capsys):
    fake = FakeApi(None)
    rc, out, _ = drive("dedupe", fake, SECOND, tmp_path)
    assert (rc, out) == (0, "")
    assert "proceeding with full CI, not skipping" in capsys.readouterr().err
    assert len(fake.calls) == 3, "a 502 is transient and must be retried by gh_retry"


def test_a_pull_request_run_never_asks(tmp_path):
    fake = FakeApi([run(FIRST)], {FIRST: "success"})
    assert drive("dedupe", fake, SECOND, tmp_path, event="pull_request")[1] == ""
    assert fake.calls == []


# ---- rule 2: the release gate sees siblings ----------------------------------------------------------------------


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "startup_failure"])
def test_release_refused_when_the_other_run_on_the_sha_failed(tmp_path, capsys, conclusion):
    """THE INCIDENT SHAPE. Two push runs on one sha; the other failed (a job killed by timeout-minutes ends `cancelled`, CI Complete then fails, and the RUN concludes `failure`), this one is green. Today's gate reads only this run's ci-complete and dispatches; this one must refuse and name the sibling."""
    fake = FakeApi([run(SECOND, conclusion=conclusion), run(FIRST, "in_progress", None)])
    rc, *_ = drive("release-gate", fake, FIRST, tmp_path)
    err = capsys.readouterr().err
    assert rc == 1
    assert "Refusing to release" in err
    assert str(SECOND) in err


def test_release_proceeds_with_a_green_sibling_and_a_green_self(tmp_path):
    """The mirror case: a green sibling plus a green this-run releases."""
    fake = FakeApi([run(SECOND), run(FIRST, "in_progress", None)])
    assert drive("release-gate", fake, FIRST, tmp_path)[0] == 0


def test_release_proceeds_with_a_sibling_queued_behind_the_concurrency_group(tmp_path):
    fake = FakeApi([run(SECOND, "queued", None), run(FIRST, "in_progress", None)])
    assert drive("release-gate", fake, FIRST, tmp_path)[0] == 0


# ---- rule 3: an earlier cancelled run blocks unless this run is its clean retry (operator ruling 2026-10-06) ------

CLEAN_JOBS: list[dict] = [
    {"name": "Initialize", "conclusion": "success"},
    {"name": "Build CLI", "conclusion": "success"},
    {"name": "Preview", "conclusion": "skipped"},
    {"name": "Finalize Release Sentinel", "status": "in_progress", "conclusion": None},
]


def _cancelled_then(jobs: list[dict] | None = None) -> FakeApi:
    return FakeApi(
        [run(SECOND, "in_progress", None), run(FIRST, conclusion="cancelled")],
        jobs={SECOND: CLEAN_JOBS if jobs is None else jobs},
    )


def test_a_clean_first_attempt_retry_of_a_cancelled_run_releases(tmp_path, capsys):
    assert drive("release-gate", _cancelled_then(), SECOND, tmp_path, attempt=1)[0] == 0
    assert "clean retry" in capsys.readouterr().err


def test_a_retry_on_its_second_attempt_does_not_release(tmp_path, capsys):
    rc, *_ = drive("release-gate", _cancelled_then(), SECOND, tmp_path, attempt=2)
    err = capsys.readouterr().err
    assert rc == 1
    assert "this is attempt 2" in err
    assert str(FIRST) in err


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_retry_with_an_unclean_job_does_not_release(tmp_path, capsys, conclusion):
    jobs = [*CLEAN_JOBS, {"name": "E2E Ceph", "conclusion": conclusion}]
    rc, *_ = drive("release-gate", _cancelled_then(jobs), SECOND, tmp_path, attempt=1)
    err = capsys.readouterr().err
    assert rc == 1
    assert "E2E Ceph (%s)" % conclusion in err


def test_a_missing_run_attempt_does_not_release_after_a_cancel(tmp_path, capsys):
    """The workflow passes `$GITHUB_RUN_ATTEMPT`; without it the run cannot show it is a first attempt."""
    rc, *_ = drive("release-gate", _cancelled_then(), SECOND, tmp_path)
    assert rc == 1
    assert "run attempt was not passed" in capsys.readouterr().err


def test_a_later_cancelled_sibling_never_blocks(tmp_path):
    """A duplicate queued behind this run and then cancelled says nothing about this run."""
    fake = FakeApi([run(SECOND, conclusion="cancelled"), run(FIRST, "in_progress", None)])
    assert drive("release-gate", fake, FIRST, tmp_path, attempt=2)[0] == 0


def test_unreadable_own_jobs_fail_open_after_a_cancel(tmp_path, capsys):
    fake = FakeApi([run(SECOND, "in_progress", None), run(FIRST, conclusion="cancelled")])
    rc, *_ = drive("release-gate", fake, SECOND, tmp_path, attempt=1)
    assert rc == 0
    assert "fail-open" in capsys.readouterr().err


def test_the_release_gate_ignores_its_own_failed_earlier_attempt(tmp_path):
    """A re-attempt shares the run id; the listing's conclusion is its latest attempt's."""
    fake = FakeApi([run(FIRST, "in_progress", None)])
    assert drive("release-gate", fake, FIRST, tmp_path)[0] == 0


def test_the_release_gate_fails_open_on_an_unreadable_api(tmp_path, capsys):
    rc, *_ = drive("release-gate", FakeApi(None), FIRST, tmp_path)
    assert rc == 0
    assert "fail-open" in capsys.readouterr().err
