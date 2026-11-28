"""Tests for the on-premise CI lane: the stack comes up with a container machine, the scenarios run, and the stack goes down on every path."""

from __future__ import annotations

import pytest

from rediacc_ci.testrun import onprem_lane as mod


class Recorder:
    """Stands in for both the stack and the runner; records the argv of every call in order."""

    def __init__(self, rc: dict[str, int] | None = None, raises: bool = False) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.rc = rc or {}
        self.raises = raises

    def stack(self, argv: list[str]) -> int:
        self.calls.append(("stack", argv))
        return self.rc.get(argv[0], 0)

    def scenarios(self, argv: list[str]) -> int:
        self.calls.append(("scenarios", argv))
        if self.raises:
            raise RuntimeError("runner crashed")
        return self.rc.get("scenarios", 0)


def run(rec: Recorder, argv: list[str]) -> int:
    return mod.main(argv, stack=rec.stack, scenarios=rec.scenarios)


def test_up_with_a_container_machine_runs_every_suite_then_down() -> None:
    rec = Recorder()
    assert run(rec, []) == 0
    assert rec.calls == [
        ("stack", ["up", "--machines", "container"]),
        ("scenarios", ["--all"]),
        ("stack", ["down"]),
    ]


def test_arguments_pass_through_to_the_runner() -> None:
    rec = Recorder()
    assert run(rec, ["--suite", "smoke"]) == 0
    assert ("scenarios", ["--suite", "smoke"]) in rec.calls
    assert ("scenarios", ["--all"]) not in rec.calls


def test_a_failing_runner_fails_the_lane_and_still_takes_the_stack_down() -> None:
    rec = Recorder(rc={"scenarios": 1})
    assert run(rec, []) == 1
    assert rec.calls[-1] == ("stack", ["down"])


def test_a_crashing_runner_still_takes_the_stack_down() -> None:
    rec = Recorder(raises=True)
    with pytest.raises(RuntimeError):
        run(rec, [])
    assert rec.calls[-1] == ("stack", ["down"])


def test_a_stack_that_will_not_come_up_runs_nothing_and_leaves_nothing_to_take_down() -> None:
    rec = Recorder(rc={"up": 1})
    assert run(rec, []) == 1
    assert [name for name, _ in rec.calls] == ["stack"]


def test_a_failed_teardown_fails_a_passing_run() -> None:
    rec = Recorder(rc={"down": 3})
    assert run(rec, []) == 3


def test_control_a_runner_failure_wins_over_a_failed_teardown() -> None:
    rec = Recorder(rc={"scenarios": 1, "down": 3})
    assert run(rec, []) == 1
