"""`rediacc_ci.core.upstream`, the Python copy of `scripts/lib/upstream.ts`'s retry rule and wording.

THE TWO COPIES MUST AGREE, and nothing else would notice if they drifted: the TypeScript gates and the Go dependency gate would then retry differently and print sentences `ci_diagnose.py` reads differently. The first case reads the four numbers out of the TypeScript source and compares them with the Python constants.

Proved, control first: an answer on the first attempt returns at once; a transient failure is retried up to three times with 2 s and 4 s between attempts, and each retry prints the note `ci_diagnose.py` skips; a failure that is not worth asking again raises after one attempt; the report carries both sentences the `upstream-unreachable` signature reads.
"""

import http.client
import pathlib
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import ci_diagnose
from rediacc_ci.core import upstream
from rediacc_ci.tests.gates import upstream_stub

TS = pathlib.Path(paths.CI_DIR).parent / "scripts" / "lib" / "upstream.ts"


def ts_number(name: str) -> str:
    match = re.search(
        r"export const %s(?::[^=]+)? = ([^;]+);" % name, TS.read_text(encoding="utf-8")
    )
    assert match, "%s is not declared in %s" % (name, TS)
    return match.group(1).replace("_", "").strip()


def test_the_retry_budget_matches_the_typescript():
    assert int(ts_number("HTTP_TIMEOUT_MS")) == upstream.HTTP_TIMEOUT_S * 1000
    assert int(ts_number("MAX_ATTEMPTS")) == upstream.MAX_ATTEMPTS
    backoff = [int(x) for x in ts_number("BACKOFF_MS").strip("[]").split(",")]
    assert backoff == [s * 1000 for s in upstream.BACKOFF_S]


@pytest.fixture
def slept(monkeypatch):
    waits: list[float] = []
    monkeypatch.setitem(upstream.SLEEP_SEAM, "sleep", waits.append)
    return waits


def test_control_an_answer_returns_at_once(slept):
    assert upstream.retry("GET h/p", "h", "who", lambda: upstream.Answer(7)) == 7
    assert slept == []


def test_a_transient_failure_is_retried_three_times_then_raises(slept, capsys):
    calls = []

    def once():
        calls.append(1)
        return upstream.Failure("HTTP 503", True, 503)

    with pytest.raises(upstream.NotComparedError) as raised:
        upstream.retry("GET h/p", "h", "pin", once)
    assert len(calls) == 3
    assert slept == [2, 4]
    assert str(raised.value) == "GET h/p -> HTTP 503, after 3 attempt(s)"
    captured = capsys.readouterr()
    # The note is progress on stderr; stdout stays free for a caller's JSON.
    assert captured.out == ""
    notes = captured.err.splitlines()
    assert notes[0] == "? pin: attempt 1 of 3 failed (HTTP 503), asking again in 2 s"
    assert all(ci_diagnose.RETRY_NOTE_RE.search(n) for n in notes), notes


def test_a_failure_not_worth_asking_again_raises_after_one(slept):
    with pytest.raises(upstream.NotComparedError) as raised:
        upstream.retry("GET h/p", "h", "pin", lambda: upstream.Failure("HTTP 404", False, 404))
    assert raised.value.attempts == 1
    assert raised.value.status == 404
    assert slept == []


def test_a_failure_that_clears_returns_the_answer(slept):
    answers: list[upstream.Answer[str] | upstream.Failure] = [
        upstream.Failure("network error ECONNRESET", True),
        upstream.Answer("ok"),
    ]
    assert upstream.retry("GET h/p", "h", "pin", lambda: answers.pop(0)) == "ok"
    assert slept == [2]


def test_the_report_carries_the_sentences_the_triage_reads(capsys):
    err = upstream.NotComparedError("timeout after 15 s", "osv.test", "POST osv.test/v1/query", 3)
    upstream.report_unreachable(
        "Go dependency lookup(s)", [("m: a v1 -> v2", err.host, str(err))], "an outdated module"
    )
    lines = capsys.readouterr().err.splitlines()
    hits = {hit[0] for line in lines if (hit := ci_diagnose._sig_hit(line))}
    assert hits == {"upstream-unreachable"}, lines
    assert (
        "  UPSTREAM REACHABILITY FAILURE (osv.test), not an outdated module and not a defect in the tree."
        in lines
    )


def test_no_item_prints_nothing(capsys):
    upstream.report_unreachable("x(s)", [], "y")
    assert capsys.readouterr().err == ""


class _TruncatedConnection:
    """A connection whose response ends early, which http.client reports as HTTPException and not as OSError."""

    def request(self, *_args, **_kwargs) -> None:
        return None

    def getresponse(self):
        raise http.client.IncompleteRead(b"", 10)

    def close(self) -> None:
        return None


def test_a_truncated_response_is_a_failed_ask_not_a_traceback(slept, monkeypatch):
    monkeypatch.setattr(upstream, "_connection", lambda _parts: _TruncatedConnection())
    with pytest.raises(upstream.NotComparedError) as raised:
        upstream.ask_json("https://example.test/q", "who")
    assert "network error IncompleteRead" in str(raised.value)
    assert "after 3 attempt(s)" in str(raised.value)
    assert slept == [2, 4]


def test_the_dns_stub_takes_an_mx_pair_as_a_tuple_or_a_list_and_refuses_anything_else():
    as_tuple = upstream_stub._rdata("MX", (10, "mx.example.test"))
    assert upstream_stub._rdata("MX", [10, "mx.example.test"]) == as_tuple
    for bad in ("mx.example.test", (10,), (10, "a", "b")):
        with pytest.raises(TypeError):
            upstream_stub._rdata("MX", bad)
