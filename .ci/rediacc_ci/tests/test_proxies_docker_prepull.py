"""`rediacc_ci.proxies.docker_prepull` against its bash twin.

Sibling of `test_proxies_cli_manifest.py`; see that file for why the two
invocations are compared byte-for-byte rather than as a finding set (this
proxy's own output carries no timestamps, tmp paths or PIDs either). This one
NEEDS a reachable docker daemon and a reachable public registry -- both
proxies exit 77 (cannot-run, not a verdict) without them, and this test would
then assert 77 == 77 rather than proving anything about the port, so it is
skipped in that case exactly as a developer's local run would be.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-docker-prepull.observations.jsonl`.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/test/proxies/proxy-docker-prepull.sh"
MODULE = "docker_prepull"


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        ).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(
    not _docker_ready(),
    reason="docker daemon not reachable; proxy would report 77, proving nothing",
)


def run_both(*args: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for()
    new_env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    arg_str = (" " + " ".join(args)) if args else ""
    old = diff.bash_streams(f"bash {TWIN}{arg_str}", env=old_env, timeout=120)
    new = diff.bash_streams(
        f"python3 -m rediacc_ci.proxies.{MODULE}{arg_str}", env=new_env, timeout=120
    )
    return old, new


def test_selftest_is_byte_identical() -> None:
    old, new = run_both("--selftest")
    assert old[0] == 0
    assert new == old


def test_full_run_is_byte_identical() -> None:
    old, new = run_both()
    assert old[0] == 0
    assert "9 check(s) passed, 3 requirement(s) present" in old[1]
    assert new == old
