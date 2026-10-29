"""`machine._install_tofu`: the setup step that runs `./rdc.sh tools install tofu`.

The subprocess is faked by a scratch `rdc.sh` that logs its argv, so nothing installs. The step must take the version from `tools list -o json` and never carry one of its own.
"""

from __future__ import annotations

import json
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.setup import machine
from rediacc_ci.setup.ctx import Ctx

FAKE_RDC = """#!/bin/bash
echo "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "tools install") exit "${FAKE_INSTALL_RC:-0}" ;;
  "tools list") printf '%s\\n' "${FAKE_LIST_OUT}"; exit "${FAKE_LIST_RC:-0}" ;;
esac
exit 9
"""


def _ctx(tmp_path: pathlib.Path, monkeypatch, **env: str) -> Ctx:
    rdc = tmp_path / "rdc.sh"
    rdc.write_text(FAKE_RDC, encoding="utf-8")
    rdc.chmod(0o755)
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_LOG", str(log))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Ctx(root=tmp_path)


def _listing(version: str) -> str:
    return "-> Starting CLI\n" + json.dumps(
        {"success": True, "data": {"pinned": {"tofu": version}, "tools": []}}
    )


def test_success_reports_the_version_from_the_tool_output(tmp_path, monkeypatch, capsys) -> None:
    ctx = _ctx(tmp_path, monkeypatch, FAKE_LIST_OUT=_listing("7.8.9"))
    assert machine._install_tofu(ctx) == 0
    assert "7.8.9" in capsys.readouterr().err
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        "tools install tofu",
        "tools list -o json",
    ]


def test_a_failed_install_fails_the_step_and_skips_the_listing(
    tmp_path, monkeypatch, capsys
) -> None:
    ctx = _ctx(tmp_path, monkeypatch, FAKE_INSTALL_RC="3", FAKE_LIST_OUT=_listing("1.0.0"))
    assert machine._install_tofu(ctx) == 1
    assert "rdc tools install tofu failed (rc=3)" in capsys.readouterr().err
    assert (tmp_path / "calls.log").read_text().splitlines() == ["tools install tofu"]


def test_a_listing_without_the_pinned_version_fails_the_step(tmp_path, monkeypatch, capsys) -> None:
    ctx = _ctx(tmp_path, monkeypatch, FAKE_LIST_OUT="not json")
    assert machine._install_tofu(ctx) == 1
    assert "did not report the pinned tofu version" in capsys.readouterr().err


def test_a_failing_listing_fails_the_step(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, monkeypatch, FAKE_LIST_RC="1", FAKE_LIST_OUT=_listing("1.0.0"))
    assert machine._install_tofu(ctx) == 1


def test_machine_py_hard_codes_no_tool_version() -> None:
    source = pathlib.Path(paths.from_root(".ci/rediacc_ci/setup/machine.py")).read_text(
        encoding="utf-8"
    )
    body = source[source.index("def _install_tofu") : source.index("RETIRED_ENV_FILES")]
    assert not re.search(r"\d+\.\d+\.\d+", body)
    assert not re.search(r"\b[0-9a-f]{64}\b", body)


def test_a_null_pinned_version_fails_the_step(tmp_path, monkeypatch, capsys) -> None:
    listing = "x\n" + json.dumps({"success": True, "data": {"pinned": {"tofu": None}, "tools": []}})
    ctx = _ctx(tmp_path, monkeypatch, FAKE_LIST_OUT=listing)
    assert machine._install_tofu(ctx) == 1
    err = capsys.readouterr().err
    assert "did not report the pinned tofu version" in err
    assert "None installed" not in err


def test_devcontainer_tofu_install_cannot_fail_container_creation() -> None:
    text = pathlib.Path(paths.from_root(".devcontainer/devcontainer.json")).read_text(
        encoding="utf-8"
    )
    command = re.search(r'"postCreateCommand":\s*"([^"]*)"', text)
    assert command is not None
    steps = command.group(1)
    assert "{ ./rdc.sh tools install tofu || echo 'WARNING: rdc tools install tofu failed" in steps
    assert "&& ./rdc.sh tools install tofu" not in steps
    assert steps.index("tools install tofu") < steps.index("playwright install chromium")
