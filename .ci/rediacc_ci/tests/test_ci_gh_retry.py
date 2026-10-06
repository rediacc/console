"""`gh_retry`: a transient GitHub failure is retried with backoff, anything else fails at once. Fake runner, fake sleep, no network."""

from __future__ import annotations

import pytest

from rediacc_ci.ci import budget_report as br
from rediacc_ci.ci import gh_retry
from rediacc_ci.core import ghx

SERVER_ERROR = "gh: Server Error (HTTP 502)"
NOT_FOUND = "gh: Not Found (HTTP 404)"


class _Runner:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        rc, out, err = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        return ghx.GhResult(["gh", *args], rc, out, err)


def _run(runner):
    slept: list[float] = []
    result = gh_retry.api_json("repos/o/r/x", runner=runner, sleep=slept.append)
    return result, slept


def test_a_502_then_success_passes_with_one_backoff():
    runner = _Runner((1, "", SERVER_ERROR), (0, '{"jobs": []}', ""))
    result, slept = _run(runner)
    assert result == {"jobs": []}
    assert len(runner.calls) == 2
    assert slept == [gh_retry.DELAY_S]
    assert all(kw == {"attempts": 1} for _a, kw in runner.calls)


def test_three_502s_fail_naming_the_error():
    runner = _Runner((1, "", SERVER_ERROR))
    slept: list[float] = []
    with pytest.raises(ghx.GhError, match="Server Error"):
        gh_retry.api_json("repos/o/r/x", runner=runner, sleep=slept.append)
    assert len(runner.calls) == gh_retry.ATTEMPTS == 3
    assert slept == [5.0, 15.0]


def test_a_404_fails_at_once_without_retry():
    runner = _Runner((1, "", NOT_FOUND))
    slept: list[float] = []
    with pytest.raises(ghx.GhError, match="Not Found"):
        gh_retry.api_json("repos/o/r/x", runner=runner, sleep=slept.append)
    assert len(runner.calls) == 1
    assert slept == []


@pytest.mark.parametrize(
    "text",
    [
        "read tcp 10.0.0.1:1->140.82.0.1:443: read: connection reset by peer",
        "stream error: stream ID 1; CANCEL; received from peer",
        "gh: Bad Gateway (HTTP 502)",
        "gh: Service Unavailable (HTTP 503)",
    ],
)
def test_connection_resets_and_other_5xx_are_transient(text):
    assert gh_retry.is_transient(text)


@pytest.mark.parametrize(
    "text",
    ["gh: Not Found (HTTP 404)", "gh: Forbidden (HTTP 403)", "HTTP 401: Bad credentials", "gh: API rate limit exceeded", ""],
)
def test_client_errors_and_rate_limits_are_not_transient(text):
    assert not gh_retry.is_transient(text)


def test_budget_report_reads_ride_the_retry(monkeypatch):
    """fetch_jobs hits a 502 once and still returns the jobs; the plain `ghx.gh` path is never used for it."""
    runner = _Runner((1, "", SERVER_ERROR), (0, '{"jobs": [{"id": 1}], "total_count": 1}', ""))
    monkeypatch.setattr(ghx, "gh", runner)
    monkeypatch.setattr(gh_retry.time, "sleep", lambda _s: None)
    assert br.fetch_jobs("o/r", 9) == [{"id": 1}]
    assert len(runner.calls) == 2


def test_artifact_download_does_not_retry_a_404(monkeypatch):
    n: list[int] = []

    class P:
        returncode, stdout, stderr = 1, b"", NOT_FOUND.encode()

    def run(*_a, **_k):
        n.append(1)
        return P()

    monkeypatch.setattr(br.subprocess, "run", run)
    monkeypatch.setattr(br.time, "sleep", lambda _s: None)
    with pytest.raises(ghx.GhBadOutputError):
        br.download_artifact_zip("o/r", 7)
    assert len(n) == 1
