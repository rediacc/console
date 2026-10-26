"""`check:ci-worker-observability-budget` (`.ci/scripts/quality/check_worker_observability_budget.py`): the sampling ceiling and the persist rule hold over every `workers/*/wrangler*.toml`.

CONTROL FIRST, AND NEVER ON THE REAL CONFIGS. Each plant goes into a synthetic tree under `tmp_path` that the gate reads through `--root`; the unplanted tree must pass first, so a red on a plant is the plant's doing. The planted defects: rate 1 on a stable account config, a missing rate, `persist = true` on a disallowed config, no destination on a non-persisting signal, an exemption naming no config, and zero configs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

GATE = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_worker_observability_budget.py"
EU = "workers/account/wrangler.eu.toml"
EDGE = "workers/account/wrangler.edge-eu.toml"

RULES = {
    "worker_observability": {
        "sampling_ceiling": 0.1,
        "sampling_exempt": {EDGE: {"rate": 1, "why": "edge volume stays under 1 percent"}},
        "persist_disallowed": ["workers/*/wrangler*.toml"],
    }
}


def toml(rate: str | None = "0.1", persist: str = "false", dest: str = '["d"]') -> str:
    lines = ["[observability]", "enabled = true", "", "[observability.logs]", "enabled = true"]
    if rate is not None:
        lines.append("head_sampling_rate = %s" % rate)
    lines += [
        "persist = %s" % persist,
        "destinations = %s" % dest,
        "",
        "[observability.traces]",
        "enabled = false",
        "",
    ]
    return "\n".join(lines)


def tree(
    tmp_path: pathlib.Path, configs: dict[str, str], rules: dict | None = None
) -> pathlib.Path:
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "cf-spend-guard.json").write_text(
        json.dumps(RULES if rules is None else rules)
    )
    for name, body in configs.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return tmp_path


def run(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


GOOD = {EU: toml(), EDGE: toml(rate="1")}


def test_selftest_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(GATE), "--selftest"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_unplanted_tree_passes(tmp_path: pathlib.Path) -> None:
    result = run(tree(tmp_path, GOOD))
    assert result.returncode == 0, result.stderr
    assert "2 configs" in result.stdout


@pytest.mark.parametrize(
    ("label", "configs", "needle"),
    [
        ("rate 1 on a stable account config", {**GOOD, EU: toml(rate="1")}, "above 0.1"),
        ("missing rate", {**GOOD, EU: toml(rate=None)}, "no explicit head_sampling_rate"),
        (
            "persist true on a disallowed config",
            {**GOOD, EU: toml(persist="true")},
            "persists in Cloudflare",
        ),
        (
            "persist unset on a disallowed config",
            {**GOOD, EU: toml().replace("persist = false\n", "")},
            "persists in Cloudflare",
        ),
        ("no destination without persist", {**GOOD, EU: toml(dest="[]")}, "goes nowhere"),
    ],
)
def test_planted_violation_fails(
    tmp_path: pathlib.Path, label: str, configs: dict[str, str], needle: str
) -> None:
    result = run(tree(tmp_path, configs))
    assert result.returncode == 1, label + ": " + result.stdout + result.stderr
    assert needle in result.stderr


def test_exempt_rate_is_a_ceiling(tmp_path: pathlib.Path) -> None:
    rules = json.loads(json.dumps(RULES))
    rules["worker_observability"]["sampling_exempt"][EDGE]["rate"] = 0.5
    result = run(tree(tmp_path, GOOD, rules))
    assert result.returncode == 1
    assert "sampling_exempt rate" in result.stderr


def test_exemption_for_a_missing_config_fails(tmp_path: pathlib.Path) -> None:
    result = run(tree(tmp_path, {EU: toml()}))
    assert result.returncode == 1
    assert "which is not a config" in result.stderr


def test_disabled_observability_is_not_judged(tmp_path: pathlib.Path) -> None:
    off = "[observability]\nenabled = false\n"
    result = run(tree(tmp_path, {**GOOD, EU: off}))
    assert result.returncode == 0, result.stderr


def test_zero_configs_is_exit_two(tmp_path: pathlib.Path) -> None:
    result = run(
        tree(
            tmp_path,
            {},
            {"worker_observability": {**RULES["worker_observability"], "sampling_exempt": {}}},
        )
    )
    assert result.returncode == 2


def test_missing_rules_is_exit_two(tmp_path: pathlib.Path) -> None:
    result = run(tree(tmp_path, GOOD, {"notifications": {}}))
    assert result.returncode == 2


def test_template_and_dev_configs_are_skipped(tmp_path: pathlib.Path) -> None:
    configs = {
        **GOOD,
        "workers/proxy/wrangler.template.toml": toml(rate="1"),
        "workers/proxy/wrangler.dev.toml": toml(rate="1"),
    }
    result = run(tree(tmp_path, configs))
    assert result.returncode == 0, result.stderr
