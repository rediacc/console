"""rdc.sh names the config it starts the CLI with (it said "production config" under --config p2bench, 2026-10-25)."""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _function_text() -> str:
    text = (ROOT / "rdc.sh").read_text()
    # One line: rdc.sh sits at check:ci-rdc-native's line ceiling.
    m = re.search(r"^selected_config_name\(\) \{.*\}(?= #|$).*\n", text, re.MULTILINE)
    assert m, "rdc.sh defines selected_config_name"
    return m.group(0)


def _name(args: list[str], env_config: str | None = None) -> str:
    script = _function_text() + 'selected_config_name "$@"\n'
    env = {"PATH": "/usr/bin:/bin"}
    if env_config is not None:
        env["REDIACC_CONFIG"] = env_config
    out = subprocess.run(
        ["bash", "-c", script, "rdc", *args], env=env, capture_output=True, text=True, check=True
    )
    return out.stdout


@pytest.mark.parametrize(
    ("args", "env_config", "want"),
    [
        (["--config", "p2bench", "repo", "list"], None, "p2bench"),
        (["--config=eu-remote", "machine", "status", "x"], None, "eu-remote"),
        (["repo", "list"], "bench", "bench"),
        (["repo", "list", "--config", "flag-wins"], "env-loses", "flag-wins"),
        (["repo", "list"], None, "rediacc"),
    ],
)
def test_selected_config_name(args: list[str], env_config: str | None, want: str) -> None:
    assert _name(args, env_config) == want


def test_the_banner_uses_the_selected_name() -> None:
    text = (ROOT / "rdc.sh").read_text()
    assert 'log_step "Starting CLI (production config)"' not in text
    assert 'log_step "Starting CLI (config $(selected_config_name "$@"))"' in text
