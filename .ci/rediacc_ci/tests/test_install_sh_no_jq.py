"""`install.sh`'s `write_install_config` with an existing config and no `jq` on PATH.

The no-jq branch must leave the config byte for byte untouched. With a custom releases URL it must also print the instruction naming the URL, because the CLI reads that URL only from the config. The function is sourced and called as bash, like `check:ci-install-sh-config` does.
"""

from __future__ import annotations

import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.well_known import RELEASES_ORIGIN

if typing.TYPE_CHECKING:
    import pathlib

INSTALL_SH = paths.repo_root() / "packages" / "www" / "public" / "install.sh"
DEFAULT_URL = RELEASES_ORIGIN
CUSTOM_URL = "https://releases.example.test/custom"
CONFIG = '{"schemaVersion":3,"machines":{"m":{}},"account":{"accountServer":"https://x"}}\n'
# Tools the sourced script and the function touch; `jq` is deliberately absent.
TOOLS = (
    "uname",
    "mkdir",
    "cat",
    "grep",
    "sed",
    "head",
    "tr",
    "dirname",
    "basename",
    "mktemp",
    "od",
)


def run_without_jq(
    tmp_path: pathlib.Path, releases_url: str, channel: str = ""
) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    assert shutil.which("jq", path=str(bin_dir)) is None
    home = tmp_path / "home"
    config_file = home / "xdg" / "rediacc" / "rediacc.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(CONFIG)
    env = {
        "PATH": str(bin_dir),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg"),
        "REDIACC_INSTALL_SH_SOURCE_ONLY": "1",
        "REDIACC_RELEASES_URL": releases_url,
    }
    if channel:
        env["REDIACC_CHANNEL"] = channel
    script = f'set -euo pipefail\nsource "{INSTALL_SH}"\nwrite_install_config\n'
    bash = shutil.which("bash") or "/bin/bash"
    result = subprocess.run(
        [bash, "-c", script], env=env, capture_output=True, text=True, check=False, cwd=tmp_path
    )
    return result, config_file


def test_custom_releases_url_is_reported_and_config_untouched(tmp_path: pathlib.Path) -> None:
    result, config_file = run_without_jq(tmp_path, CUSTOM_URL)
    assert result.returncode == 0, result.stderr
    assert "jq not found" in result.stderr + result.stdout
    assert f'"releasesUrl": "{CUSTOM_URL}"' in result.stdout
    assert config_file.read_text() == CONFIG


def test_no_custom_url_prints_no_releases_instruction(tmp_path: pathlib.Path) -> None:
    # A non-default channel forces the no-jq branch without a custom URL.
    result, config_file = run_without_jq(tmp_path, DEFAULT_URL, channel="stable")
    assert result.returncode == 0, result.stderr
    assert "rdc update --channel" in result.stdout
    assert "releasesUrl" not in result.stdout
    assert config_file.read_text() == CONFIG
