"""The core floor of check:test-cli in the generated gate lock.

The ci-runner pool sizes an elastic gate from its full-width wall estimate, so a gate whose work is far larger than that wall can be granted one core on a busy machine. check:test-cli is about 500 core-seconds (512 vitest files: 64 s at 8 workers, 243 s at 6 workers beside a running ci:quick); at one core it cannot finish inside its 485.6 s limit, and four ci:quick runs on 2026-11-14 timed out that way (`elastic grants: ... check:test-cli 1 core(s)`). The floor of 6 is what keeps it inside the limit.
"""

from __future__ import annotations

import json

from rediacc_ci import paths

LOCK = paths.repo_root() / "scripts" / "ci-runner" / "gates.lock.json"
FLOOR = 6


def _floor_problem(entries: list[dict], gate_id: str) -> str | None:
    """None when `gate_id` declares an elastic floor of at least FLOOR cores, else what is wrong."""
    matches = [e for e in entries if e.get("id") == gate_id]
    if len(matches) != 1:
        return "%s has %d entries" % (gate_id, len(matches))
    cores = matches[0].get("cores")
    if not isinstance(cores, dict) or not isinstance(cores.get("min"), int):
        return "%s has no integer cores.min: %r" % (gate_id, cores)
    if cores["min"] < FLOOR:
        return (
            "%s may be granted %d core(s); below %d its ~500 core-seconds overrun the 485.6 s "
            "gate limit (scripts/ci-runner/manifest.ts explains the measurement)"
            % (gate_id, cores["min"], FLOOR)
        )
    return None


def test_check_test_cli_keeps_its_core_floor() -> None:
    entries = json.loads(LOCK.read_text(encoding="utf-8"))
    assert _floor_problem(entries, "check:test-cli") is None, _floor_problem(
        entries, "check:test-cli"
    )


def test_the_check_refuses_the_floor_that_starved_the_gate() -> None:
    """Control: min 1, the value that starved the gate, and a missing declaration are both refused."""
    starved = [{"id": "check:test-cli", "cores": {"min": 1, "max": "all"}}]
    assert "may be granted 1 core(s)" in (_floor_problem(starved, "check:test-cli") or "")
    bare = [{"id": "check:test-cli"}]
    assert "no integer cores.min" in (_floor_problem(bare, "check:test-cli") or "")
