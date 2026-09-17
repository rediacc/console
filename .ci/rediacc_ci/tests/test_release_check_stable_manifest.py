"""`rediacc_ci.release.check_stable_manifest` against its bash twin.

Sibling of `test_release_check_edge_manifest.py`; see that file for why the
fake is `curl` rather than a fixture URL, and why it is PREPENDED to PATH rather than replacing it (real `jq`/`bash` still need to resolve).
"""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/release/check-stable-manifest.sh"
MODULE = "check_stable_manifest"

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
    tmp_path: pathlib.Path, bindir: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-output.txt"
    out_new = tmp_path / "new-output.txt"
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(**env_extra, GITHUB_OUTPUT=str(out_old), PATH=path_with_fake)
    new_env = diff.env_for(
        **env_extra,
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


def test_matching_versions_report_same_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_curl(tmp_path, body='{"version":"1.2.3"}')
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, {"EDGE_VERSION": "1.2.3"}
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "Edge and stable are the same version (1.2.3), skipping\n"
    assert new_out == old_out
    assert old_output == "version=1.2.3\nsame=true\n"
    assert new_output == old_output


def test_differing_versions_report_not_same_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_curl(tmp_path, body='{"version":"1.2.2"}')
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, {"EDGE_VERSION": "1.2.3"}
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == ""
    assert new_out == ""
    assert old_output == "version=1.2.2\nsame=false\n"
    assert new_output == old_output


def test_no_stable_manifest_yet_is_never_the_same_on_either_side(
    tmp_path: pathlib.Path,
) -> None:
    bindir = _make_fake_curl(tmp_path, body="", rc=22)
    (old_exit, _old_out, old_err), (new_exit, _new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, {"EDGE_VERSION": "1.2.3"}
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_output == "version=\nsame=false\n"
    assert new_output == old_output


def test_missing_edge_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """Exit codes agree; wording does not, and is not supposed to."""
    bindir = _make_fake_curl(tmp_path, body='{"version":"1.2.3"}')
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, bindir, {})
    assert old_exit == 1
    assert new_exit == 1
    assert "EDGE_VERSION" in old_err
    assert "EDGE_VERSION" in new_err
