"""`rediacc_ci.release.verify_release_assets` against its bash twin.

`gh` is faked on PATH (prepended, real `jq` stays reachable); `jq` itself is
real on both sides, since it is a generic JSON tool with no credentials and no
production traffic, same reasoning as every other release-side port in this
box.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/release/verify-release-assets.sh"
MODULE = "verify_release_assets"

FAKE_GH_TEMPLATE = """#!{python}
import sys
sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
sys.exit({rc})
"""


def _make_fake_gh(
    tmp_path: pathlib.Path, *, rc: int, stdout: str = "", stderr: str = ""
) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(
        FAKE_GH_TEMPLATE.format(python=sys.executable, stdout=stdout, stderr=stderr, rc=rc)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    bindir: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(**env_extra, PATH=path_with_fake)
    new_env = diff.env_for(
        **env_extra, PATH=path_with_fake, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    return old, new


def test_a_release_with_a_cli_asset_passes_on_both_sides(tmp_path: pathlib.Path) -> None:
    body = json.dumps(
        {"tagName": "v1.2.3", "assets": [{"name": "rdc-linux-x64"}, {"name": "checksums.txt"}]}
    )
    bindir = _make_fake_gh(tmp_path, rc=0, stdout=body)
    old, new = run_both(bindir, {"VERSION": "v1.2.3", "GITHUB_REPOSITORY": "rediacc/console"})
    assert old == (0, "✓ Release v1.2.3 has 1 rdc-* CLI asset(s)\n", "")
    assert new == old


def test_a_release_with_no_cli_assets_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    body = json.dumps(
        {"tagName": "v1.2.3", "assets": [{"name": "checksums.txt"}, {"name": "notes.md"}]}
    )
    bindir = _make_fake_gh(tmp_path, rc=0, stdout=body)
    old, new = run_both(bindir, {"VERSION": "v1.2.3", "GITHUB_REPOSITORY": "rediacc/console"})
    assert old[0] == 1
    assert new[0] == 1
    assert "no rdc-* CLI assets" in old[1]
    assert "no rdc-* CLI assets" in new[1]
    assert '"checksums.txt"' in old[1]
    assert '"checksums.txt"' in new[1]
    assert new[1] == old[1]


def test_a_missing_release_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path, rc=1, stderr="release not found\n")
    old, new = run_both(bindir, {"VERSION": "v9.9.9", "GITHUB_REPOSITORY": "rediacc/console"})
    assert old == (1, "::error::no GitHub Release found for v9.9.9\nrelease not found\n", "")
    assert new == old


def test_missing_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path, rc=0, stdout="{}")
    old, new = run_both(bindir, {"GITHUB_REPOSITORY": "rediacc/console"})
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "VERSION" in new[2]
