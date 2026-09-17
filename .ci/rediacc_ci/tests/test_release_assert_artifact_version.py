"""`rediacc_ci.release.assert_artifact_version` against its bash twin.

`gh` IS FAKED ON PATH FOR BOTH SIDES, never called for real: the twin runs `gh run download <id> --repo <owner/repo> --name cli-manifest --dir /tmp/cd-artifact-check` with `2>/dev/null`, and there is no fixture hook anywhere in it. Putting one fake `gh` in front of both implementations is the only way to drive the four artifact states (download refused, downloaded but empty,
downloaded with a bad manifest, downloaded with a good one) and is the same technique `test_release_verify_artifact_attestation.py` uses.

`jq` IS THE REAL ONE ON BOTH SIDES, on purpose. The port shells out to it rather than reimplementing `.version // empty`, because on malformed input jq's exit code IS the script's exit code (`set -e` through a command substitution) and no `::error::` line is printed at all. Those two paths -- a parse error and a top-level array -- are the ones a hand-written JSON reader would
silently give a different code to, so they get their own cases below.

THE DOWNLOAD DIRECTORY IS A FIXED `/tmp/cd-artifact-check` IN BOTH IMPLEMENTATIONS, so the two sides of one case, and successive cases, share it. The fake `gh` therefore CLEARS it on every invocation before writing, which is what keeps case N+1 from reading case N's leftovers. That the twin itself never
clears it is a real hazard in the twin, reported rather than corrected here;
see the port's docstring. `XDIST_GROUP` below is the other half of the same fact: under `--dist loadgroup` this module must not be spread across workers, because the contested resource is a path on the host rather than anything a registry can see.

K=5 LEDGER: `.ci/shadow/w7p6-assert-artifact-version.observations.jsonl`,
recorded against a disposable scratch git repo built OUTSIDE this checkout (this repo's working tree is not clean and `shadow-gate.ts --record` refuses a dirty tree).
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

# One worker for the whole module: both implementations write the same fixed `/tmp/cd-artifact-check`, which no lock entry can express.
XDIST_GROUP = "cd-artifact-check"

TWIN = ".ci/scripts/release/assert-artifact-version.sh"
MODULE = "rediacc_ci.release.assert_artifact_version"

FAKE_GH = """#!/bin/bash
# Fake `gh run download` for this differential. Clears --dir first, because
# BOTH implementations point at a fixed /tmp path and never clear it themselves.
dir=""
prev=""
for a in "$@"; do
  if [ "$prev" = "--dir" ]; then dir="$a"; fi
  prev="$a"
done
if [ -n "$dir" ]; then rm -rf "$dir"; mkdir -p "$dir"; fi
rc="${FAKE_GH_DOWNLOAD_RC:-0}"
if [ "$rc" != "0" ]; then
  echo "fake gh: no artifact named cli-manifest on that run" >&2
  exit "$rc"
fi
if [ -n "${FAKE_GH_MANIFEST:-}" ]; then printf '%s' "$FAKE_GH_MANIFEST" > "$dir/manifest.json"; fi
if [ -n "${FAKE_GH_EXTRA_FILE:-}" ]; then printf 'x' > "$dir/$FAKE_GH_EXTRA_FILE"; fi
exit 0
"""


def _bin_without(tmp_path: pathlib.Path, drop: str) -> str:
    """A PATH directory holding every tool both sides need EXCEPT `drop`.

    An empty PATH is not usable here: `differential.bash_streams` resolves `bash` through the environment it is handed, so emptying PATH breaks the harness rather than the subject, and the test then proves nothing about the
    missing-tool branch."""
    d = tmp_path / ("bin-no-%s" % drop)
    d.mkdir(exist_ok=True)
    # EVERY executable on the real PATH is mirrored, not a hand-picked list. A list is how this helper goes quietly wrong: the first attempt named ten tools and the twin died at `dirname` on line 39, before `require_cmd` had run at all, so the case was asserting on a broken harness rather than on the missing-tool branch. Mirroring everything means the ONLY thing absent is the one
    # being dropped.
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        # `/mnt/...` is the Windows drive mount a WSL developer's PATH carries, ~5400 entries behind a 9p filesystem. Listing them cost 79 SECONDS per test, measured, and nothing either implementation resolves lives there. Skipped before the isdir() probe, which is itself a 9p round trip.
        if not entry or entry.startswith("/mnt/") or not os.path.isdir(entry):
            continue
        for name in os.listdir(entry):
            if name == drop or (d / name).exists():
                continue
            src = os.path.join(entry, name)
            if os.access(src, os.X_OK) and not os.path.isdir(src):
                (d / name).symlink_to(src)
    return str(d)


def _fake_gh_bin(tmp_path: pathlib.Path) -> str:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(bindir)


def run_both(
    tmp_path: pathlib.Path,
    env_extra: dict[str, str],
    *,
    path: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    bindir = _fake_gh_bin(tmp_path)
    base_path = os.environ.get("PATH", "/usr/bin:/bin") if path is None else path
    path_with_fake = "%s:%s" % (bindir, base_path)
    old_env = diff.env_for(**env_extra, PATH=path_with_fake)
    new_env = diff.env_for(
        **env_extra,
        PATH=path_with_fake,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=60)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, timeout=60)
    return old, new


def _ok_env(**over: str) -> dict[str, str]:
    env = {
        "VERSION": "1.2.3",
        "CI_RUN_ID": "1234567890",
        "GITHUB_REPOSITORY": "rediacc/console",
        "GH_TOKEN": "fake-token",
    }
    env.update(over)
    return env


def test_matching_version_passes_byte_for_byte(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":"1.2.3"}'))
    assert old == (
        0,
        "::notice::Artifact version v1.2.3 matches promotion target v1.2.3.\n",
        "",
    )
    assert new == old


def test_leading_v_is_stripped_from_the_artifact_side(tmp_path: pathlib.Path) -> None:
    """`${ARTIFACT_VERSION#v}`. The artifact may or may not carry the `v`."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":"v1.2.3"}'))
    assert old == (
        0,
        "::notice::Artifact version v1.2.3 matches promotion target v1.2.3.\n",
        "",
    )
    assert new == old


def test_only_one_leading_v_is_stripped(tmp_path: pathlib.Path) -> None:
    """`#v` removes the SHORTEST matching prefix, i.e. exactly one `v`, so
    `vv1.2.3` still mismatches. A port using `lstrip('v')` would strip both and
    turn this failure into a pass."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":"vv1.2.3"}'))
    assert old[0] == 1
    assert "produced vv1.2.3, but CD is promoting as v1.2.3." in old[1]
    assert new == old


def test_normalisation_is_one_sided_so_a_v_prefixed_version_mismatches(
    tmp_path: pathlib.Path,
) -> None:
    """The promotion target is documented as having NO leading v, and nothing
    strips one from it. `VERSION=v1.2.3` against artifact `1.2.3` is therefore
    a hard mismatch on both sides -- a contract, not an oversight."""
    old, new = run_both(tmp_path, _ok_env(VERSION="v1.2.3", FAKE_GH_MANIFEST='{"version":"1.2.3"}'))
    assert old[0] == 1
    assert "produced v1.2.3, but CD is promoting as vv1.2.3." in old[1]
    assert new == old


def test_stale_ci_run_id_mismatch_names_both_versions(tmp_path: pathlib.Path) -> None:
    """The incident this script exists for: 1.2.16 bytes published as 1.2.17."""
    old, new = run_both(
        tmp_path,
        _ok_env(VERSION="1.2.17", CI_RUN_ID="42", FAKE_GH_MANIFEST='{"version":"1.2.16"}'),
    )
    assert old == (
        1,
        (
            "::error::Artifact-version mismatch: CI run 42 produced v1.2.16, but CD is "
            "promoting as v1.2.17.\n"
            "::error::This means ci_run_id is stale -- the artifacts were built before the "
            "latest tag bump.\n"
            "::error::Either dispatch again with no ci_run_id (auto-derive latest green CI "
            "on main), or re-run CI on current main to produce fresh artifacts.\n"
        ),
        "",
    )
    assert new == old


def test_leading_zeros_are_not_normalised_away(tmp_path: pathlib.Path) -> None:
    """String equality, never semver equality. `01.2.3` is not `1.2.3`, and a
    port that parsed the version into integers would call this a pass."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":"01.2.3"}'))
    assert old[0] == 1
    assert "produced v01.2.3, but CD is promoting as v1.2.3." in old[1]
    assert new == old


def test_a_json_number_version_keeps_its_source_spelling(tmp_path: pathlib.Path) -> None:
    """`{"version": 1.20}` reaches the comparison as the text `1.20`, not
    `1.2`: jq 1.8 preserves a number literal's spelling. So it mismatches
    `VERSION=1.2`, on both sides."""
    old, new = run_both(tmp_path, _ok_env(VERSION="1.2", FAKE_GH_MANIFEST='{"version":1.20}'))
    assert old[0] == 1
    assert "produced v1.20, but CD is promoting as v1.2." in old[1]
    assert new == old


def test_absent_version_field_refuses(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"tag":"v1.2.3"}'))
    assert old == (
        1,
        "::error::manifest.json has no .version field; refusing to publish unverified.\n",
        "",
    )
    assert new == old


def test_null_version_is_the_same_refusal(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":null}'))
    assert old[0] == 1
    assert "has no .version field" in old[1]
    assert new == old


def test_false_version_is_also_empty_because_slashslash_is_an_alternative(
    tmp_path: pathlib.Path,
) -> None:
    """`//` is jq's ALTERNATIVE operator, not a null-coalesce: it fires on
    `false` as well as on `null`. A port that special-cased only `None` would
    print `::notice::... vFalse ...` here."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":false}'))
    assert old[0] == 1
    assert "has no .version field" in old[1]
    assert new == old


def test_empty_string_version_is_the_same_refusal(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST='{"version":""}'))
    assert old[0] == 1
    assert "has no .version field" in old[1]
    assert new == old


def test_missing_artifact_is_a_hard_failure_not_a_warning(tmp_path: pathlib.Path) -> None:
    """HARDENED 2026-08-07. This branch used to warn and exit 0, and because
    nothing produced the artifact, EVERY release took it. Three `::error::`
    lines and exit 1 now, on both sides."""
    old, new = run_both(tmp_path, _ok_env(CI_RUN_ID="777", FAKE_GH_DOWNLOAD_RC="1"))
    assert old[0] == 1
    assert old[1] == (
        "::error::cli-manifest artifact not found on CI run 777, so the artifact version "
        "CANNOT be compared.\n"
        "::error::Refusing to publish on an unverified version. cd-stage.yml uploads this "
        "artifact on every push run, so its absence means the CI run is older than that "
        "change, was not a push run, or its artifacts expired (retention is 1 day).\n"
        "::error::Dispatch again with no ci_run_id to auto-derive the latest green CI on "
        "main, or re-run CI on current main.\n"
    )
    assert new == old


def test_gh_stderr_is_swallowed_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`2>/dev/null` on the gh call only. The fake writes a line to stderr that
    must not reach the CD log from either implementation."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_DOWNLOAD_RC="1"))
    assert "fake gh:" not in old[2]
    assert "fake gh:" not in new[2]
    assert old[2] == new[2] == ""


def test_artifact_present_but_manifest_json_absent(tmp_path: pathlib.Path) -> None:
    """A downloaded artifact holding something else entirely."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_EXTRA_FILE="README.txt"))
    assert old == (
        1,
        (
            "::error::cli-manifest artifact present but manifest.json missing; refusing to "
            "publish unverified.\n"
        ),
        "",
    )
    assert new == old


def test_malformed_json_propagates_jqs_own_exit_code_and_message(
    tmp_path: pathlib.Path,
) -> None:
    """No `::error::` line at all on this path: jq's stderr and jq's exit code
    are the entire output, because the command substitution fails under `set -e`. Whatever that code is for the installed jq, both sides must
    report the SAME one -- which is the argument for shelling out."""
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST="{not json"))
    assert old[0] != 0
    assert old[0] != 1
    assert old[1] == ""
    assert "jq: " in old[2]
    assert "parse error" in old[2]
    assert new == old


def test_top_level_array_propagates_jqs_index_error(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, _ok_env(FAKE_GH_MANIFEST="[1,2,3]"))
    assert old[0] != 0
    assert old[1] == ""
    assert 'Cannot index array with string "version"' in old[2]
    assert new == old


def test_missing_version_variable_refuses_reworded(tmp_path: pathlib.Path) -> None:
    """DOCUMENTED DIVERGENCE: the twin's `${VAR:?msg}` diagnostic carries a bash
    line number. Same exit code, same stream, same variable named."""
    env = _ok_env(FAKE_GH_MANIFEST='{"version":"1.2.3"}')
    del env["VERSION"]
    old, new = run_both(tmp_path, env)
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "must be set" in old[2]
    assert "VERSION" in new[2]
    assert "must be set" in new[2]
    # Neither side may have reached the download.
    assert old[1] == new[1] == ""


def test_missing_ci_run_id_refuses_reworded(tmp_path: pathlib.Path) -> None:
    env = _ok_env(FAKE_GH_MANIFEST='{"version":"1.2.3"}')
    del env["CI_RUN_ID"]
    old, new = run_both(tmp_path, env)
    assert old[0] == new[0] == 1
    assert "CI_RUN_ID" in old[2]
    assert "CI_RUN_ID" in new[2]


def test_missing_github_repository_refuses_reworded(tmp_path: pathlib.Path) -> None:
    env = _ok_env(FAKE_GH_MANIFEST='{"version":"1.2.3"}')
    del env["GITHUB_REPOSITORY"]
    old, new = run_both(tmp_path, env)
    assert old[0] == new[0] == 1
    assert "GITHUB_REPOSITORY" in old[2]
    assert "GITHUB_REPOSITORY" in new[2]


def test_missing_gh_binary_refuses_identically(tmp_path: pathlib.Path) -> None:
    """`require_cmd gh` runs BEFORE any variable check, and its message is a
    `log_error` string rather than a bash diagnostic, so this one IS byte-identical. A gate that exits 0 because its tool is not installed is the failure this repo names first, so the missing-tool branch gets a real
    probe rather than a comment."""
    nogh = _bin_without(tmp_path, "gh")
    env = _ok_env()
    old_env = diff.env_for(**env, PATH=nogh)
    new_env = diff.env_for(**env, PATH=nogh, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, timeout=30)
    assert old[0] == 1
    assert old[1] == ""
    assert old[2] == "✗ Required command 'gh' is not available\n"
    assert new == old


def test_missing_jq_binary_refuses_identically(tmp_path: pathlib.Path) -> None:
    """`require_cmd jq` is carried into the port even though the port could
    parse JSON itself, because dropping the probe would make the port SUCCEED on a host where the twin refuses. It shells out to jq anyway (see the module
    docstring), so the dependency is real on both sides, not ceremonial."""
    nojq = _bin_without(tmp_path, "jq")
    env = _ok_env()
    old_env = diff.env_for(**env, PATH=nojq)
    new_env = diff.env_for(**env, PATH=nojq, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, timeout=30)
    assert old[0] == 1
    assert old[2] == "✗ Required command 'jq' is not available\n"
    assert new == old
