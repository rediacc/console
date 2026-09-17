"""`rediacc_ci.release.resolve_ci_run` against its bash twin.

THE FAKE `gh` UNDERSTANDS `--jq`, because both the twin and this port ask `gh api` to apply a jq filter itself (`--jq '.workflow_runs[0].id // empty'`, `--jq '.head_sha'`) rather than piping to a separate `jq` process for those two calls -- so a fake that ignores `--jq` and echoes the whole body would silently test a different code path than CI runs. The fake shells out to the REAL
`jq` (a generic tool, no credentials) to apply whatever filter it was given, against one of two canned bodies selected by which endpoint the URL names: `FAKE_GH_LIST_JSON` for the `actions/workflows/ci.yml/runs?...` listing, `FAKE_GH_RUN_JSON` for `actions/runs/<id>` (used for both the explicit-id validation lookup and the final head_sha lookup, exactly as the twin calls that same
endpoint twice). `FAKE_GH_RUN_RC` reproduces the twin's
`2>/dev/null || echo '{}'` fallback path.
"""

from __future__ import annotations

import os
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/release/resolve-ci-run.sh"
MODULE = "resolve_ci_run"

FAKE_GH_SRC = r"""#!{python}
import json
import os
import subprocess
import sys

argv = sys.argv[1:]
# Expected shapes: ["api", URL] or ["api", URL, "--jq", FILTER]
url = argv[1] if len(argv) > 1 else ""
jq_filter = None
if "--jq" in argv:
    jq_filter = argv[argv.index("--jq") + 1]

if "workflows/ci.yml/runs" in url:
    rc = int(os.environ.get("FAKE_GH_LIST_RC", "0"))
    body = os.environ.get("FAKE_GH_LIST_JSON", "{}")
else:
    rc = int(os.environ.get("FAKE_GH_RUN_RC", "0"))
    body = os.environ.get("FAKE_GH_RUN_JSON", "{}")

if rc != 0:
    sys.stderr.write("gh: simulated failure\n")
    sys.exit(rc)

if jq_filter is None:
    sys.stdout.write(body)
    sys.exit(0)

out = subprocess.run(["jq", "-r", jq_filter], input=body, capture_output=True, text=True, check=False)
sys.stdout.write(out.stdout)
sys.exit(out.returncode)
"""


def _make_fake_gh(tmp_path: pathlib.Path) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH_SRC.replace("{python}", sys.executable))
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


def test_auto_derive_picks_the_latest_green_run_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "rediacc/console",
        "FAKE_GH_LIST_JSON": '{"workflow_runs":[{"id":555}]}',
        "FAKE_GH_RUN_JSON": '{"head_sha":"abc123"}',
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert "Auto-derived ci_run_id=555" in old_out
    assert old_out == new_out
    assert old_output == "ci_run_id=555\nci_sha=abc123\n"
    assert new_output == old_output


def test_auto_derive_with_no_green_run_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "rediacc/console",
        "FAKE_GH_LIST_JSON": '{"workflow_runs":[]}',
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "No green Console CI run found" in old_out
    assert old_out == new_out
    assert old_output == new_output == ""


def test_explicit_run_id_on_the_wrong_branch_is_refused_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "rediacc/console",
        "INPUT_CI_RUN_ID": "42",
        "FAKE_GH_RUN_JSON": (
            '{"head_branch":"feature-x","name":"Console CI","status":"completed",'
            '"conclusion":"success"}'
        ),
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "is on branch 'feature-x', not 'main'" in old_out
    assert old_out == new_out
    assert old_output == new_output == ""


def test_explicit_run_id_completed_failure_allow_stale_proceeds_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "rediacc/console",
        "INPUT_CI_RUN_ID": "42",
        "ALLOW_STALE": "true",
        "FAKE_GH_RUN_JSON": (
            '{"head_branch":"main","name":"Console CI","status":"completed",'
            '"conclusion":"failure","head_sha":"deadbeef"}'
        ),
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, bindir, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert "allow_stale_ci_run_id is set, proceeding anyway" in old_out
    assert old_out == new_out
    assert old_output == "ci_run_id=42\nci_sha=deadbeef\n"
    assert new_output == old_output


def test_a_failed_run_lookup_falls_back_to_empty_object_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """`gh api ... 2>/dev/null || echo '{}'`: a failed lookup degrades to an
    empty object, which then fails validation as an empty branch/workflow -- not a crash."""
    bindir = _make_fake_gh(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "rediacc/console",
        "INPUT_CI_RUN_ID": "999",
        "FAKE_GH_RUN_RC": "1",
    }
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), _old_output, _new_output = (
        run_both(tmp_path, bindir, env)
    )
    assert old_exit == 1
    assert new_exit == 1
    assert "is on branch '', not 'main'" in old_out
    assert old_out == new_out


def test_missing_github_repository_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    bindir = _make_fake_gh(tmp_path)
    old, new, _, _ = run_both(tmp_path, bindir, {})
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_REPOSITORY" in old[2]
    assert "GITHUB_REPOSITORY" in new[2]
