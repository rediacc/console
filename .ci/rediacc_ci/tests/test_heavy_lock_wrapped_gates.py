"""The three incident gates stay behind the machine-wide heavy lock (PLAN-ciquick-cpu L3).

WHAT IS AT RISK. check:deps, check:ci-account-server and build:www timed out on 2026-11-21 when two trees ran them together. Their `run` is wrapped in `core_lease.py heavy-lock --`. Nothing else ties a gate to the wrapper (gate-bind only admits the wrapper as an npm hop), so a manifest edit that reverts one to a bare `npm run <id>` stays green everywhere and the timeout returns. This pin names the three and fails when one is unwrapped, when one is missing, or when the list is empty.

BLOCKER: the set is exactly the three gates with a measured timeout. lint:unused, check:types and check:types:incremental are NOT listed: no timeout has been measured for them (operator-lead decision, 2026-11-24). Add an id here only with the measured timeout that justifies it.

Both sides are read: scripts/ci-runner/manifest.ts (the source) and scripts/ci-runner/gates.lock.json (its generated form).
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "scripts" / "ci-runner" / "manifest.ts"
LOCK = ROOT / "scripts" / "ci-runner" / "gates.lock.json"

WRAPPER = "python3 .ci/rediacc_ci/core_lease.py heavy-lock -- "
WRAPPED_GATES = ("check:deps", "check:ci-account-server", "build:www")
# The run is the wrapper and nothing before it except `NAME="value"` env words. Anchored at both ends, so `npm run x && <wrapped x>` is refused: the unwrapped hop runs before the lock.
_ENV_PREFIX = r'(?:[A-Z_][A-Z0-9_]*="[^"]*"\s+)*'


def unwrapped(runs: dict[str, str], ids: tuple[str, ...]) -> list[str]:
    """Problems for every id whose run is absent, or does not carry the heavy-lock wrapper directly before `npm run <id>`."""
    if not ids:
        return ["the pinned gate list is empty; its green would mean nothing"]
    problems: list[str] = []
    for gate in ids:
        run = runs.get(gate)
        if run is None:
            problems.append(f"{gate}: no run found")
        elif not re.fullmatch(_ENV_PREFIX + re.escape(WRAPPER + "npm run " + gate), run):
            problems.append(f"{gate}: run is {run!r}, not wrapped in `{WRAPPER}npm run {gate}`")
    return problems


def manifest_runs(source: str) -> dict[str, str]:
    """id -> run for each entry of manifest.ts: the first `run: '...'` after an `id: '...'` line and before the next `id:` line."""
    runs: dict[str, str] = {}
    parts = re.split(r"^\s*id: '([^']+)',$", source, flags=re.MULTILINE)
    for i in range(1, len(parts) - 1, 2):
        m = re.search(r"^\s*run: '((?:[^'\\]|\\.)*)',$", parts[i + 1], flags=re.MULTILINE)
        if m:
            if parts[i] in runs:
                raise ValueError(f"duplicate manifest id {parts[i]!r}: only one run per id is read")
            runs[parts[i]] = m.group(1).replace('\\"', '"')
    return runs


def lock_runs(text: str) -> dict[str, str]:
    runs: dict[str, str] = {}
    for e in json.loads(text):
        if "run" in e:
            if e["id"] in runs:
                raise ValueError(f"duplicate lock id {e['id']!r}: only one run per id is read")
            runs[e["id"]] = e["run"]
    return runs


def test_real_manifest_wraps_the_three_incident_gates() -> None:
    runs = manifest_runs(MANIFEST.read_text())
    assert len(runs) > 100, (
        f"manifest parse saw {len(runs)} entries; the pin is not reading the tree"
    )
    assert unwrapped(runs, WRAPPED_GATES) == []


def test_real_lock_wraps_the_three_incident_gates() -> None:
    runs = lock_runs(LOCK.read_text())
    assert len(runs) > 100, f"lock parse saw {len(runs)} entries; the pin is not reading the tree"
    assert unwrapped(runs, WRAPPED_GATES) == []


def test_control_a_reverted_run_is_refused() -> None:
    """CONTROL: the real sources with one run reverted to a bare npm hop must go red, on both sides."""
    manifest = MANIFEST.read_text().replace(
        "run: '" + WRAPPER + "npm run check:deps'", "run: 'npm run check:deps'"
    )
    assert manifest != MANIFEST.read_text(), "the control did not change the manifest text"
    problems = unwrapped(manifest_runs(manifest), WRAPPED_GATES)
    assert len(problems) == 1
    assert problems[0].startswith("check:deps: ")

    lock = LOCK.read_text().replace(
        '"run": "' + WRAPPER + 'npm run check:deps"', '"run": "npm run check:deps"'
    )
    assert lock != LOCK.read_text(), "the control did not change the lock text"
    lock_problems = unwrapped(lock_runs(lock), WRAPPED_GATES)
    assert len(lock_problems) == 1
    assert lock_problems[0].startswith("check:deps: ")


def test_control_an_empty_list_a_missing_gate_and_a_foreign_wrapper_are_refused() -> None:
    assert unwrapped({}, ())
    assert unwrapped({"check:deps": WRAPPER + "npm run check:deps"}, WRAPPED_GATES)[0].startswith(
        "check:ci-account-server"
    )
    other = "python3 .ci/rediacc_ci/other.py heavy-lock -- npm run check:deps"
    assert unwrapped({"check:deps": other}, ("check:deps",))
    wrong_target = WRAPPER + "npm run check:other"
    assert unwrapped({"check:deps": wrong_target}, ("check:deps",))


def test_control_wrapped_runs_pass_including_an_env_prefix() -> None:
    runs = {
        "check:deps": WRAPPER + "npm run check:deps",
        "check:ci-account-server": 'VITEST_MAX_WORKERS="$CI_RUNNER_CORES" '
        + WRAPPER
        + "npm run check:ci-account-server",
        "build:www": WRAPPER + "npm run build:www",
    }
    assert unwrapped(runs, WRAPPED_GATES) == []


def test_control_a_bare_hop_before_the_wrapped_one_is_refused() -> None:
    """Review 838416b2.1: an unwrapped run chained ahead of the wrapped one must not pass."""
    chained = "npm run check:deps && " + WRAPPER + "npm run check:deps"
    assert unwrapped({"check:deps": chained}, ("check:deps",))
    semicolon = "npm run check:deps; " + WRAPPER + "npm run check:deps"
    assert unwrapped({"check:deps": semicolon}, ("check:deps",))


def test_control_a_duplicated_id_is_refused_on_both_sides() -> None:
    """Review 838416b2.2: the two readers disagreed on duplicates (first wins versus last wins); both now refuse."""
    wrapped = "run: '" + WRAPPER + "npm run check:deps',"
    bare = "run: 'npm run check:deps',"
    src = f"  id: 'check:deps',\n  {wrapped}\n  id: 'check:deps',\n  {bare}\n"
    with pytest.raises(ValueError, match="duplicate manifest id"):
        manifest_runs(src)
    lock = json.dumps(
        [
            {"id": "check:deps", "run": WRAPPER + "npm run check:deps"},
            {"id": "check:deps", "run": "npm run check:deps"},
        ]
    )
    with pytest.raises(ValueError, match="duplicate lock id"):
        lock_runs(lock)
