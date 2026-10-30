"""`check:ci-bws-step-scope` driven through its real entry point, in both directions.

The module's own selftest proves the rule functions on in-memory text. This file proves the CLI: the `WORKFLOW_DIR` and `BWS_STEP_SCOPED_CONFIG` seams reach the same scan, each planted fixture turns the exit code red and names its rule, the fixed fixture and the real tree stay green, and an empty corpus or a dead config entry reds instead of passing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import bws_step_scope as gate

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
ENTRY = ROOT / ".ci" / "scripts" / "quality" / "check_bws_step_scope.py"
REASON = "BLOCKER: the production licence-signing key, scoped to the one step that starts the account server"


def _config(tmp: pathlib.Path, names: dict[str, str]) -> pathlib.Path:
    path = tmp / "bws-step-scoped.json"
    path.write_text(
        json.dumps({"names": {n: {"reason": r} for n, r in names.items()}}), encoding="utf-8"
    )
    return path


def _run(
    workflow_dir: pathlib.Path | None, config: pathlib.Path | None, floor: str = "1"
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in (gate.WORKFLOW_DIR_ENV, gate.CONFIG_ENV, gate.MIN_WINDOWS_ENV):
        env.pop(key, None)
    if workflow_dir is not None:
        env[gate.WORKFLOW_DIR_ENV] = str(workflow_dir)
        env[gate.MIN_WINDOWS_ENV] = floor
    if config is not None:
        env[gate.CONFIG_ENV] = str(config)
    return subprocess.run(
        [sys.executable, str(ENTRY)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )


def _fixture(tmp: pathlib.Path, text: str) -> tuple[pathlib.Path, pathlib.Path]:
    wf = tmp / "workflows"
    wf.mkdir()
    (wf / "probe.yml").write_text(text, encoding="utf-8")
    return wf, _config(tmp, {"ACCOUNT_ED25519_PRIVATE_KEY": REASON})


def test_selftest_passes() -> None:
    assert gate.selftest() is False


def test_fixed_fixture_is_green(tmp_path: pathlib.Path) -> None:
    wf, cfg = _fixture(tmp_path, gate.FIXED)
    r = _run(wf, cfg)
    assert r.returncode == 0, r.stderr
    assert "1 fetch window(s)" in r.stdout


@pytest.mark.parametrize("rule", ["i", "ii", "iii", "iv", "v"])
def test_each_plant_is_red_and_names_its_rule(tmp_path: pathlib.Path, rule: str) -> None:
    wf, cfg = _fixture(tmp_path, gate.plants()[rule])
    r = _run(wf, cfg)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "rule (%s)" % rule in r.stderr


def test_pre_fix_ct_tests_shape_is_the_rule_i_plant() -> None:
    assert gate.plants()["i"] == gate.PRE_FIX
    assert "ACCOUNT_ED25519_PRIVATE_KEY > BWS_ACCOUNT_ED25519_PRIVATE_KEY" in gate.PRE_FIX


def test_real_tree_is_green() -> None:
    r = _run(None, None)
    assert r.returncode == 0, r.stderr
    assert "bws step scope:" in r.stdout


def test_empty_corpus_is_red(tmp_path: pathlib.Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(empty, _config(tmp_path, {"ACCOUNT_ED25519_PRIVATE_KEY": REASON}))
    assert r.returncode == 1
    assert "not seeing the tree" in r.stderr


def test_dead_config_entry_is_red(tmp_path: pathlib.Path) -> None:
    wf, _ = _fixture(tmp_path, gate.FIXED)
    cfg = _config(
        tmp_path, {"ACCOUNT_ED25519_PRIVATE_KEY": REASON, "ACCOUNT_X25519_PRIVATE_KEY": REASON}
    )
    r = _run(wf, cfg)
    assert r.returncode == 1
    assert "ACCOUNT_X25519_PRIVATE_KEY is requested by no bws-secrets fetch" in r.stderr


def test_unmapped_config_name_is_red(tmp_path: pathlib.Path) -> None:
    wf, _ = _fixture(tmp_path, gate.FIXED)
    cfg = _config(tmp_path, {"ACCOUNT_ED25519_PRIVATE_KEY": REASON, "NOT_A_MAPPED_SECRET": REASON})
    r = _run(wf, cfg)
    assert r.returncode == 1
    assert "NOT_A_MAPPED_SECRET is not in" in r.stderr


def test_weak_reason_is_red(tmp_path: pathlib.Path) -> None:
    wf, _ = _fixture(tmp_path, gate.FIXED)
    r = _run(wf, _config(tmp_path, {"ACCOUNT_ED25519_PRIVATE_KEY": "BLOCKER: tbd"}))
    assert r.returncode == 1


def test_floor_is_enforced(tmp_path: pathlib.Path) -> None:
    wf, cfg = _fixture(tmp_path, gate.FIXED)
    r = _run(wf, cfg, floor="2")
    assert r.returncode == 1
    assert "floor is 2" in r.stderr
