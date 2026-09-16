"""`rediacc_ci.release.validate_stage_artifacts` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT`/`$GITHUB_STEP_SUMMARY`. The
K=5 ledger is `.ci/shadow/w7p5a-validate-stage-artifacts.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-validate-stage-artifacts
--assert --k 5` -> "equivalence holds over 5 distinct trees").

EVERY CASE HERE RUNS AGAINST AN ISOLATED `dist/` FIXTURE, never against this
checkout's own `dist/` (which does not exist in a fresh checkout, and must
not be created as a side effect of running a test suite). This needs BOTH
sides pointed at the fixture root, and the two mechanisms differ because the
two sides resolve "repo root" differently:

  * The bash twin's `get_repo_root()` derives the root from `common.sh`'s OWN
    file location (`${BASH_SOURCE[0]}`), so the fixture must carry a REAL
    copy of `.ci/scripts/lib/common.sh` and the twin script at the matching
    relative path -- copying the twin's bytes there is what makes its own
    root resolution land on the fixture instead of this checkout.
  * The Python port asks `rediacc_ci.paths.repo_root()`, which honours
    `$REDIACC_CI_ROOT` -- so the new side just sets that env var to the
    fixture root, no file copying needed.

`du` PRODUCES REAL, HOST-DEPENDENT BYTES (block-size rounding), so the
pages-bundle-size assertions check for a non-"N/A" value rather than an exact
string, and the exact-string cases below only ever exercise the "no
dist/pages" (`N/A`) path, which both sides compute without touching `du` at
all.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN_REL = ".ci/scripts/release/validate-stage-artifacts.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"
MODULE = "validate_stage_artifacts"


def _build_fixture(root: pathlib.Path, twin_root: str) -> None:
    """Copy just enough of the real tree for the bash twin's own root
    resolution (`get_repo_root()`) to land on `root` instead of this
    checkout."""
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    shutil.copy2(os.path.join(twin_root, COMMON_REL), root / COMMON_REL)
    shutil.copy2(os.path.join(twin_root, TWIN_REL), root / TWIN_REL)


def run_both(
    root: pathlib.Path, twin_root: str, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old_summary = root / "old-summary.md"
    out_old_output = root / "old-output.txt"
    out_new_summary = root / "new-summary.md"
    out_new_output = root / "new-output.txt"
    old_env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=str(out_old_summary),
        GITHUB_OUTPUT=str(out_old_output),
    )
    new_env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=str(out_new_summary),
        GITHUB_OUTPUT=str(out_new_output),
        PYTHONPATH=os.path.join(twin_root, ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
        REDIACC_CI_ROOT=str(root),
    )
    old = diff.bash_streams("bash %s" % (root / TWIN_REL), env=old_env, cwd=str(root), timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(root), timeout=30
    )
    old_summary = out_old_summary.read_text(encoding="utf-8") if out_old_summary.exists() else ""
    new_summary = out_new_summary.read_text(encoding="utf-8") if out_new_summary.exists() else ""
    return old, new, old_summary, new_summary


def test_empty_dist_fails_with_the_vacuity_errors(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    env = {"EVENT_NAME": "schedule", "NEXT_VERSION": "9.9.9", "CHANNEL": ""}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_summary, new_summary = run_both(
        root, diff.repo(), env
    )
    assert (old_exit, old_err) == (1, "")
    assert (new_exit, new_err) == (1, "")
    assert old_out == new_out
    assert "VACUOUS: No CLI artifacts found under dist/cli" in old_out
    assert "Channel is empty for event 'schedule'" in old_out
    assert old_summary == new_summary
    assert "| CLI artifacts | 0 files |" in old_summary
    assert "Validation FAILED" in old_summary


def test_full_dist_with_channel_passes(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    dist = root / "dist"
    (dist / "cli").mkdir(parents=True)
    (dist / "cli" / "rdc-linux-x64").write_bytes(b"x")
    pkg = dist / "packages"
    pkg.mkdir(parents=True)
    for name in (
        "a.deb",
        "b.deb",
        "a.rpm",
        "b.rpm",
        "a.apk",
        "b.apk",
        "a.pkg.tar.zst",
        "b.pkg.tar.zst",
    ):
        (pkg / name).write_bytes(b"x")
    (dist / "pages").mkdir(parents=True)
    (dist / "pages" / "index.html").write_bytes(b"x" * 1024)
    (dist / "repos" / "apt" / "dists").mkdir(parents=True)
    (dist / "repos" / "apt" / "dists" / "Release").write_bytes(b"x")
    (dist / "repos" / "rpm" / "repodata").mkdir(parents=True)
    (dist / "repos" / "rpm" / "repodata" / "repomd.xml").write_bytes(b"x")

    env = {"EVENT_NAME": "push", "NEXT_VERSION": "1.2.3", "CHANNEL": "edge"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_summary, new_summary = run_both(
        root, diff.repo(), env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_summary == new_summary
    assert "| CLI artifacts | 1 files |" in old_summary
    assert "| Linux packages | 8 files (deb:2 rpm:2 apk:2 arch:2) |" in old_summary
    assert "N/A" not in old_summary  # dist/pages/ exists; du produced a real size
    assert "All validation passed. Ready for publish." in old_summary


def test_missing_event_name_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """`$GITHUB_STEP_SUMMARY`/`$GITHUB_OUTPUT` are always supplied by
    `run_both` (both point at real temp files), so the first genuinely-missing
    required var is `EVENT_NAME`. Wording is not byte-identical here: bash's
    own `${VAR:?msg}` diagnostic (line-numbered) differs from the port's, same
    as every other twin in this box."""
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(root, diff.repo(), {})
    assert old_exit == 1
    assert new_exit == 1
    assert "EVENT_NAME" in old_err
    assert "must be set" in old_err
    assert "EVENT_NAME" in new_err
    assert "must be set" in new_err
