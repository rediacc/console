"""The guard fire and cost ledger `dispatch.run_chain` appends (agent/plans/PLAN-tooling-code-reduction.md CR7).

Fake chains drive the shape: a refusal names its stem, an allow carries `refused_by: null`, a slow guard is listed under `slow`, and a raising guard is recorded as crashed while the chain keeps running. Two real-chain cases prove the same on the shipped pre-bash guards, and `main` is driven to prove the entry point really hands a ledger path, because a ledger only `run_chain` knows how to write and nothing asks it to is the vacuous green this file exists to refuse.
"""

import io
import json
import statistics
import time
import types

import pytest

from rediacc_hooks import dispatch, guards, hookio

SESSION = "0123abcd-test-session"


def payload(command="ls", session=SESSION):
    return json.dumps(
        {"session_id": session, "tool_name": "Bash", "tool_input": {"command": command}}
    )


def fake(name, rc=0, say="", sleep_ms=0, raises=False):
    module = types.ModuleType("rediacc_hooks.guards.%s" % name)

    def run(event):
        if sleep_ms:
            time.sleep(sleep_ms / 1000.0)
        if raises:
            raise RuntimeError("planted crash in %s" % name)
        if say:
            event.say(say)
        return rc

    module.__dict__["run"] = run
    return module


@pytest.fixture
def chain(monkeypatch):
    """Install a fake chain; returns the setter."""

    def install(*modules):
        monkeypatch.setattr(dispatch.guards, "by_chain", lambda _chain: list(modules))

    return install


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_refusal_names_the_refusing_stem(chain, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    chain(fake("guard_allow"), fake("guard_refuse", rc=2), fake("guard_behind", say="ran"))
    rc, out, _err = dispatch.run_chain("pre-bash", payload(), ledger=ledger)
    assert rc == 2
    assert "ran" not in out, "a guard behind the refusal ran"
    (row,) = rows(ledger)
    assert row["refused_by"] == "guard_refuse"
    assert row["rc"] == 2
    assert row["chain"] == "pre-bash"
    assert row["session"] == SESSION
    assert row["crashed"] == []
    assert isinstance(row["ms"], float)
    assert row["ts"].endswith("Z")


def test_allow_records_refused_by_null(chain, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    chain(fake("guard_a"), fake("guard_b"))
    rc, _out, _err = dispatch.run_chain("pre-bash", payload(), ledger=ledger)
    assert rc == 0
    (row,) = rows(ledger)
    assert row["refused_by"] is None
    assert row["rc"] == 0
    assert row["slow"] == []


def test_slow_guard_is_listed_and_fast_guard_is_not(chain, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    chain(fake("guard_fast"), fake("guard_slow", sleep_ms=dispatch.SLOW_MS + 15))
    dispatch.run_chain("pre-bash", payload(), ledger=ledger)
    (row,) = rows(ledger)
    assert [stem for stem, _ms in row["slow"]] == ["guard_slow"]
    assert row["slow"][0][1] > dispatch.SLOW_MS


def test_control_raising_guard_is_crashed_and_does_not_block(chain, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    chain(fake("guard_crash", raises=True), fake("guard_after", say="after ran"))
    rc, out, err = dispatch.run_chain("pre-bash", payload(), ledger=ledger)
    assert rc == 1, "a crash must exit 1, never 2: it decided nothing"
    assert "after ran" in out, "the guard behind the crash did not run"
    assert "HOOK GUARD CRASHED" in err
    (row,) = rows(ledger)
    assert row["crashed"] == ["guard_crash"]
    assert row["refused_by"] is None
    assert row["rc"] == 1


def test_empty_chain_is_recorded_as_a_refusal(chain, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    chain()
    rc, _out, err = dispatch.run_chain("pre-bash", payload(), ledger=ledger)
    assert rc == hookio.DENY
    assert "ZERO guards" in err
    (row,) = rows(ledger)
    assert row["rc"] == hookio.DENY
    assert row["refused_by"] is None


def test_no_ledger_records_nothing(chain, monkeypatch):
    """The differential and every in-process caller pass no ledger, and must not reach `ledger_path`."""
    monkeypatch.setattr(
        dispatch, "ledger_path", lambda: pytest.fail("run_chain resolved the ledger")
    )
    chain(fake("guard_a", rc=2))
    assert dispatch.run_chain("pre-bash", payload())[0] == 2


def test_unwritable_ledger_keeps_the_chain_answer(chain, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")
    chain(fake("guard_refuse", rc=2, say="refused"))
    rc, out, err = dispatch.run_chain("pre-bash", payload(), ledger=blocker / "ledger.jsonl")
    assert rc == 2
    assert out == "refused\n"
    assert "hook ledger: append to" in err


def test_main_hands_the_ledger_path(chain, tmp_path, monkeypatch):
    ledger = tmp_path / "nested" / "chains.jsonl"
    monkeypatch.setattr(dispatch, "ledger_path", lambda: ledger)
    monkeypatch.setattr("sys.stdin", io.StringIO(payload()))
    chain(fake("guard_refuse", rc=2))
    assert dispatch.main(["--chain", "pre-bash"]) == 2
    (row,) = rows(ledger)
    assert row["refused_by"] == "guard_refuse"


def test_default_ledger_is_under_the_gitignored_cache():
    path = dispatch.ledger_path()
    assert path == hookio.repo_root().joinpath(".ci", "cache", "hook-ledger", "chains.jsonl")


def test_real_chain_refusal_names_a_real_guard(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rc, _out, _err = dispatch.run_chain(
        "pre-bash", payload("git commit --amend -m x"), ledger=ledger
    )
    assert rc == 2, "the planted amend was not refused; the control is broken, not the ledger"
    (row,) = rows(ledger)
    # WHICH guard refuses first is the chain's order, not this test's business; that the stem is a shipped guard that refuses the same payload on its own is.
    stem = row["refused_by"]
    assert stem in guards.stems()
    assert dispatch.run_one(stem, payload("git commit --amend -m x"))[0] == 2


def test_real_chain_allow(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rc, _out, _err = dispatch.run_chain("pre-bash", payload("ls"), ledger=ledger)
    assert rc == 0
    (row,) = rows(ledger)
    assert row["refused_by"] is None


def test_append_costs_under_one_millisecond(tmp_path):
    """The selftest the plan asks for: the median of 200 appends, so one slow disk flush does not flake it."""
    ledger = tmp_path / "ledger.jsonl"
    record = {
        "chain": "pre-bash",
        "refused_by": None,
        "rc": 0,
        "ms": 12.5,
        "slow": [["block_example", 25.0]],
        "crashed": [],
        "session": SESSION,
        "ts": "2026-11-23T00:00:00Z",
    }
    dispatch.append_ledger(ledger, record)
    costs = []
    for _ in range(200):
        t0 = time.perf_counter()
        dispatch.append_ledger(ledger, record)
        costs.append((time.perf_counter() - t0) * 1000)
    assert len(rows(ledger)) == 201
    median = statistics.median(costs)
    assert median < 1.0, "median append took %.3f ms" % median
