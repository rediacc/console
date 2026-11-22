"""bootstrap.sh reuses the cached pytest tool only when its PyYAML is at the pin too.

`resolve_pytest` is taken from the real `bootstrap.sh` and run against a fake tool dir whose pytest reports the pinned version, with a stand-in interpreter reporting the PyYAML version.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

BOOTSTRAP = paths.repo_root() / ".ci" / "bootstrap.sh"


def _resolve(tmp_path: pathlib.Path, yaml_version: str, pin: str = "6.0.4") -> tuple[int, str, str]:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(r"^resolve_pytest\(\) \{\n.*?^\}\n", source, re.MULTILINE | re.DOTALL)
    assert match, "resolve_pytest left bootstrap.sh"
    tool = tmp_path / "uv-tools"
    (tool / "bin").mkdir(parents=True)
    (tool / "pytest" / "bin").mkdir(parents=True)
    pytest = tool / "bin" / "pytest"
    pytest.write_text("#!/bin/sh\necho 'pytest 9.9.9'\n", encoding="utf-8")
    pytest.chmod(0o755)
    python = tool / "pytest" / "bin" / "python"
    python.write_text("#!/bin/sh\necho '%s'\n" % yaml_version, encoding="utf-8")
    python.chmod(0o755)
    script = (
        "toolchain_check() { return 1; }\n"
        "toolchain_probe_version() { \"$2\" --version | awk '{print $2}'; }\n"
        'PYTEST_VERSION=9.9.9 PYYAML_VERSION="$2" TOOL_DIR="$1" TOOL_BIN_DIR="$1/bin"\n'
        + match.group(0)
        + "resolve_pytest\n"
    )
    done = subprocess.run(
        ["bash", "-c", script, "bash", str(tool), pin],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout, done.stderr


def test_a_cached_pytest_with_an_older_pyyaml_is_not_reused(tmp_path):
    # rc 1 with nothing on stderr is the refusal itself; a bash error or a broken harness exits otherwise or writes stderr.
    assert _resolve(tmp_path, "6.0.3") == (1, "", "")


def test_an_empty_pin_with_a_tool_env_that_cannot_import_yaml_is_not_reused(tmp_path):
    assert _resolve(tmp_path, "", pin="") == (1, "", "")


def test_a_cached_pytest_with_the_pinned_pyyaml_is_reused(tmp_path):
    assert _resolve(tmp_path, "6.0.4") == (0, str(tmp_path / "uv-tools" / "bin" / "pytest"), "")
