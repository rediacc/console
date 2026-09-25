"""`rediacc_ci.deploy.transfer_retry`: a transient failure is retried, a refusal is not (#b22efec4).

On 2026-09-24 (M-live item 10) the hotfix promote's minted R2 token expired mid-run and the retry spent its remaining attempts on `AccessDenied`, a verdict that cannot change between tries. These cases drive `retried` with a scripted `run` so no subprocess and no network is involved.
"""

from __future__ import annotations

import pytest

from rediacc_ci.deploy import transfer_retry

INCOMPLETE_READ = (
    "download failed: s3://b/apt/edge/x.deb to /tmp/promote-apt/x.deb "
    "('Connection broken: IncompleteRead(7540288 bytes read, 848320 more expected)', "
    "IncompleteRead(7540288 bytes read, 848320 more expected))\n"
)


def _script(*results: tuple[int, str]):
    """A `run` that returns each (status, stderr) in turn and counts its calls."""
    calls: list[int] = []

    def run() -> tuple[int, str]:
        calls.append(1)
        return results[min(len(calls), len(results)) - 1]

    return run, calls


@pytest.mark.parametrize(
    "code", ["AccessDenied", "InvalidAccessKeyId", "NoSuchBucket", "ExpiredToken"]
)
def test_a_non_transient_failure_is_fatal_on_the_first_try(code, capsys) -> None:
    run, calls = _script((1, "fatal error: An error occurred (%s) when calling GetObject\n" % code))
    assert transfer_retry.retried(run, "download of apt/edge", "self.sh", 0) == 1
    assert len(calls) == 1
    err = capsys.readouterr().err
    assert "retrying (" not in err, err
    assert code in err, err
    assert "not retrying" in err, err


def test_a_refusal_on_a_later_attempt_stops_the_retries_there(capsys) -> None:
    """The live shape: IncompleteRead first, then the token expires."""
    run, calls = _script(
        (1, INCOMPLETE_READ),
        (1, "An error occurred (AccessDenied) when calling the ListObjectsV2 operation\n"),
        (0, ""),
    )
    assert transfer_retry.retried(run, "download of apt/edge", "self.sh", 0) == 1
    assert len(calls) == 2
    err = capsys.readouterr().err
    assert err.count("retrying (") == 1, err
    assert "not retrying" in err, err


@pytest.mark.parametrize(
    "stderr",
    [
        INCOMPLETE_READ,
        'Read timeout on endpoint URL: "https://r2.example.invalid/b"\n',
        "An error occurred (InternalError) when calling the PutObject operation (reached max retries: 2)\n",
        "An error occurred (503) when calling the HeadObject operation: Service Unavailable\n",
    ],
)
def test_a_transient_failure_is_still_retried(stderr, capsys) -> None:
    run, calls = _script((1, stderr), (1, stderr), (0, ""))
    assert transfer_retry.retried(run, "sync of apt/stable", "self.sh", 0) == 0
    assert len(calls) == 3
    assert capsys.readouterr().err.count("retrying (") == 2


def test_a_transient_failure_that_persists_returns_the_last_status_after_every_attempt() -> None:
    run, calls = _script((2, INCOMPLETE_READ))
    assert transfer_retry.retried(run, "x", "self.sh", 0) == 2
    assert len(calls) == transfer_retry.ATTEMPTS


def test_success_is_not_retried() -> None:
    run, calls = _script((0, ""))
    assert transfer_retry.retried(run, "x", "self.sh", 0) == 0
    assert len(calls) == 1


def test_classify_names_the_refusal_code() -> None:
    assert transfer_retry.fatal_code("An error occurred (ExpiredToken) when ...") == "ExpiredToken"
    assert transfer_retry.fatal_code(INCOMPLETE_READ) == ""
    # A path that merely CONTAINS the word is not a refusal: the code is matched in aws's parenthesised form.
    assert transfer_retry.fatal_code("download failed: s3://b/AccessDenied.txt timed out\n") == ""
