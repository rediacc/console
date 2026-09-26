"""`rediacc_ci.release.check_edge_manifest` against its bash twin.

THE FAKE `curl`, NOT A FAKE URL. The twin's manifest URL (`https://releases.rediacc.com/cli/edge/manifest.json`) is a hardcoded literal with no override hook -- unlike `wait-for-preview-worker.sh`, there is no env var to redirect it at a fixture. So both sides get a fake `curl` placed FIRST on PATH (prepended, not replacing PATH outright: `jq` and `bash` still need to resolve
normally, and only `curl` is the thing under test). Written in Python with an absolute interpreter path, same reasoning as `test_core_ghx.py`'s `fake_bin`: a shebang script depending on PATH to find its own interpreter defeats the point of controlling PATH in the first place.

`GITHUB_OUTPUT` is a real temp file, never `/dev/stdout`: reopening it under `subprocess.run` fails with ENXIO when fd 1 is a pipe (documented in every sibling test file and rediscovered painfully earlier in this box).
"""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/release/check-edge-manifest.sh"
MODULE = "check_edge_manifest"

FAKE_CURL_TEMPLATE = """#!{python}
import sys
sys.stdout.write({body!r})
sys.exit({rc})
"""


def _make_fake_curl(tmp_path: pathlib.Path, *, body: str, rc: int = 0) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "curl"
    script.write_text(FAKE_CURL_TEMPLATE.format(python=sys.executable, body=body, rc=rc))
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    tmp_path: pathlib.Path, bindir: pathlib.Path
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-output.txt"
    out_new = tmp_path / "new-output.txt"
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(GITHUB_OUTPUT=str(out_old), PATH=path_with_fake)
    new_env = diff.env_for(
        GITHUB_OUTPUT=str(out_new),
        PATH=path_with_fake,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_a_present_manifest_is_reported_identically(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_curl(
        tmp_path, body='{"version":"1.2.3","releaseDate":"2026-09-01T00:00:00Z"}'
    )
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "Edge version: 1.2.3 (released: 2026-09-01T00:00:00Z)\n"
    assert new_out == old_out
    assert old_output == "version=1.2.3\ndate=2026-09-01T00:00:00Z\nskip=false\n"
    assert new_output == old_output


def test_a_missing_manifest_skips_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`curl -sf` on a 404 exits non-zero and prints nothing -- the fake's rc=22
    with an empty body reproduces that."""
    bindir = _make_fake_curl(tmp_path, body="", rc=22)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "No edge manifest found, skipping\n"
    assert new_out == old_out
    assert old_output == "skip=true\n"
    assert new_output == old_output


def test_a_manifest_missing_release_date_prints_jq_null_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """`jq -r '.releaseDate'` on an absent field prints the literal string "null", never an empty string -- this is the case that would drift if the port used Python's `None` instead."""
    bindir = _make_fake_curl(tmp_path, body='{"version":"9.9.9"}')
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), old_output, new_output = run_both(
        tmp_path, bindir
    )
    assert old_exit == 0
    assert new_exit == 0
    assert "date=null" in old_output
    assert "date=null" in new_output
    assert old_out == new_out


def test_missing_github_output_fails_the_same_way_reworded() -> None:
    """Exit codes agree; wording does not, and is not supposed to -- see the port's module docstring."""
    old_env = diff.env_for(GITHUB_OUTPUT=None)
    new_env = diff.env_for(GITHUB_OUTPUT=None, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_OUTPUT" in old[2]
    assert "GITHUB_OUTPUT" in new[2]
