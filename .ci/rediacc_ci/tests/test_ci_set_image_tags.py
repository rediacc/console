"""`rediacc_ci.ci.set_image_tags` against its bash twin.

WHAT IS DRIVEN FOR REAL AND WHAT IS FIXTURED. Every case with an explicit `IMAGE_TAG` runs against the REAL checkout, because that arm reads nothing from the tree: `derive-image-tag.sh --version X` validates X and prints it. The
auto-derive arm reads `git tag -l 'v*' --sort=-v:refname`, whose answer is
whatever this repository happens to be tagged at, so it runs inside a DISPOSABLE one-commit repository built under `tmp_path` and carrying exactly the tags the
case needs.

HOW BOTH SIDES ARE POINTED AT THE FIXTURE, since it is the mechanism the whole file rests on. `get_repo_root` (common.sh:205) resolves three directories up
from the common.sh THAT WAS SOURCED, so a fixture that carries its own
`.ci/scripts/lib/common.sh` and reaches the twin through `<fixture>/.ci/scripts/ci/set-image-tags.sh` sends the twin to the fixture. The port resolves through `paths.repo_root()`, which honours `$REDIACC_CI_ROOT`. Both scripts are SYMLINKS to the real files -- bash does not resolve symlinks in
`${BASH_SOURCE[0]}`, so the twin under test is the real, unmodified twin, and a
change to it cannot be missed by this file.

`assert_scratch` re-derives `git rev-parse --show-toplevel` before any fixture is written to, and refuses anything inside `/home/developer/console`.

WHAT IS NORMALISED, and it is one token. `derive_image_tag` prints `<program>: line 81: ...` for a tag build with no `GITHUB_REF_NAME`, and the program is a `.sh` on one side and a `.py` on the other. `strip_prog` replaces that one token; the LINE NUMBER is compared, because a drifting line number is the silent failure the pin exists to catch.

The K=5 ledger is `.ci/shadow/w7p6-set-image-tags.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-set-image-tags --assert --k 5`).
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci.ci import set_image_tags as port
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/ci/set-image-tags.sh"
MODULE = "rediacc_ci.ci.set_image_tags"

# `git init` under a developer's own global config may sign, template or hook.
GIT_FLAGS = [
    "-c",
    "user.email=w7p6@example.invalid",
    "-c",
    "user.name=w7p6",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "init.defaultBranch=main",
]

_PROG = re.compile(r"^\S+: line ", re.MULTILINE)


def strip_prog(text: str) -> str:
    return _PROG.sub("<prog>: line ", text)


def assert_scratch(path: pathlib.Path) -> pathlib.Path:
    """Refuse to touch anything that is not a disposable fixture."""
    resolved = path.resolve()
    assert str(resolved) != diff.repo(), "refusing to operate on the checkout"
    assert not str(resolved).startswith(diff.repo() + os.sep), (
        "fixture %s is inside the checkout" % resolved
    )
    return resolved


def fixture_root(tmp_path: pathlib.Path, *tags: str) -> pathlib.Path:
    """A repo-shaped fixture: common.sh, the twin, its sibling, and `tags`."""
    root = assert_scratch(tmp_path / "fixture")
    (root / ".ci/scripts/lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci/scripts/ci").mkdir(parents=True, exist_ok=True)

    # A COPY of common.sh, not a symlink: `get_repo_root` walks up from the directory the file is IN, and a symlink would still report the fixture's directory, but a copy makes the fixture readable when it goes wrong.
    shutil.copyfile(
        "%s/.ci/scripts/lib/common.sh" % diff.repo(), root / ".ci/scripts/lib/common.sh"
    )
    for name in ("set-image-tags.sh", "derive-image-tag.sh"):
        link = root / ".ci/scripts/ci" / name
        if not link.exists():
            link.symlink_to("%s/.ci/scripts/ci/%s" % (diff.repo(), name))

    subprocess.run(["git", *GIT_FLAGS, "init", "-q", str(root)], check=True, capture_output=True)
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert_scratch(pathlib.Path(top))
    (root / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), *GIT_FLAGS, "add", "README"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), *GIT_FLAGS, "commit", "-q", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    for tag in tags:
        subprocess.run(
            ["git", "-C", str(root), *GIT_FLAGS, "tag", tag], check=True, capture_output=True
        )
    return root


def run_both(
    tmp_path: pathlib.Path,
    *,
    env_extra: dict[str, str | None] | None = None,
    github_env: str | None = "",
    root: pathlib.Path | None = None,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], dict[str, str | None]]:
    """Drive both sides. `github_env=""` means "give each side its own file".

    `github_env=None` leaves the variable UNSET (DEFECT E); any other string is
    used verbatim as the path, which is how the unwritable-target case is built.
    """
    files: dict[str, pathlib.Path] = {}
    envs: dict[str, dict[str, str | None]] = {}
    for side in ("old", "new"):
        env: dict[str, str | None] = dict(env_extra or {})
        if github_env == "":
            path = tmp_path / ("%s-github-env.txt" % side)
            path.write_text("", encoding="utf-8")
            env["GITHUB_ENV"] = str(path)
            files["%s_env" % side] = path
        elif github_env is None:
            env["GITHUB_ENV"] = None
        else:
            env["GITHUB_ENV"] = github_env
        envs[side] = env

    twin = "%s/%s" % (root, TWIN) if root is not None else "%s/%s" % (diff.repo(), TWIN)
    old = diff.bash_streams(
        "bash %s" % twin,
        env=diff.env_for(**envs["old"]),
        cwd=diff.repo(),
        tty=tty,
        timeout=30,
    )
    new = diff.bash_streams(
        "python3 -m %s" % MODULE,
        env=diff.env_for(
            **envs["new"],
            PYTHONPATH="%s/.ci" % diff.repo(),
            PYTHONDONTWRITEBYTECODE="1",
            **({"REDIACC_CI_ROOT": str(root)} if root is not None else {}),
        ),
        cwd=diff.repo(),
        tty=tty,
        timeout=30,
    )
    read = {k: v.read_text(encoding="utf-8") if v.exists() else None for k, v in files.items()}
    return old, new, read


def assert_identical(old, new, files) -> None:
    assert new[0] == old[0], "exit code: %r vs %r" % (old, new)
    assert new[1] == old[1], "stdout: %r vs %r" % (old[1], new[1])
    assert strip_prog(new[2]) == strip_prog(old[2]), "stderr: %r vs %r" % (old[2], new[2])
    for key, value in files.items():
        if key.startswith("old_"):
            assert files["new_" + key[4:]] == value, "%s diverged: %r vs %r" % (
                key[4:],
                value,
                files["new_" + key[4:]],
            )


# --------------------------------------------------------------------------- The explicit-tag arm ---------------------------------------------------------------------------


def test_both_overrides_are_appended_after_the_siblings_three_names(
    tmp_path: pathlib.Path,
) -> None:
    """The whole point of the script: five lines, in one fixed order."""
    old, new, files = run_both(
        tmp_path,
        env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": "renet-abc"},
    )
    assert old[0] == 0
    assert old[1] == "v1.2.3\n"
    assert files["old_env"] == (
        "TAG=v1.2.3\n"
        "WEB_TAG=v1.2.3\n"
        "RENET_TAG=v1.2.3\n"
        "WEB_TAG=web-abc-amd64\n"
        "RENET_TAG=renet-abc-amd64\n"
    )
    assert_identical(old, new, files)


def test_defect_f_the_success_line_reports_the_input_not_the_value_written(
    tmp_path: pathlib.Path,
) -> None:
    """The file says `web-abc-amd64`; the log says `web=web-abc`. Both sides."""
    old, new, files = run_both(
        tmp_path,
        env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": "renet-abc"},
    )
    assert "✓ Image tags set (web=web-abc renet=renet-abc)\n" in old[2]
    assert "web-abc-amd64" in files["old_env"]
    assert "web-abc-amd64" not in old[2]
    assert_identical(old, new, files)


def test_with_no_initialize_tags_only_the_sibling_writes(tmp_path: pathlib.Path) -> None:
    """The negative control for the case above: three lines, not five."""
    old, new, files = run_both(tmp_path, env_extra={"IMAGE_TAG": "v1.2.3"})
    assert files["old_env"] == "TAG=v1.2.3\nWEB_TAG=v1.2.3\nRENET_TAG=v1.2.3\n"
    assert old[2].endswith("✓ Image tags set (web=<derived> renet=<derived>)\n")
    assert_identical(old, new, files)


def test_one_override_present_and_one_absent(tmp_path: pathlib.Path) -> None:
    """`[[ -n "$WEB_TAG" ]] && echo` with WEB set and RENET empty. Both arms, one run.

    Also the `set -e` question: the failing `[[ -n "" ]]` must NOT end the script, so the trailing log line has to be there.
    """
    old, new, files = run_both(
        tmp_path, env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": ""}
    )
    assert old[0] == 0
    assert files["old_env"].endswith("WEB_TAG=web-abc-amd64\n")
    assert "RENET_TAG=-amd64" not in files["old_env"]
    assert "✓ Image tags set (web=web-abc renet=<derived>)" in old[2]
    assert_identical(old, new, files)


def test_an_empty_image_tag_falls_through_to_auto_derive(tmp_path: pathlib.Path) -> None:
    """`[[ -n "${IMAGE_TAG:-}" ]]` treats unset and empty alike."""
    root = fixture_root(tmp_path, "v4.5.6")
    old, new, files = run_both(tmp_path, env_extra={"IMAGE_TAG": ""}, root=root)
    assert old[0] == 0
    assert old[1] == "4.5.6\n"
    assert "Auto-derived from git tags" in old[2]
    assert_identical(old, new, files)
    assert port.derive_argv("") == ["--env-file"]
    assert port.derive_argv("v1") == ["--version", "v1", "--env-file"]


def test_the_auto_derive_arm_reads_the_fixtures_newest_tag(tmp_path: pathlib.Path) -> None:
    """`--sort=-v:refname` is a VERSION sort: v1.10.0 outranks v1.9.0."""
    root = fixture_root(tmp_path, "v1.9.0", "v1.10.0")
    old, new, files = run_both(tmp_path, root=root)
    assert old[1] == "1.10.0\n"
    assert files["old_env"] == "TAG=1.10.0\nWEB_TAG=1.10.0\nRENET_TAG=1.10.0\n"
    assert_identical(old, new, files)


# --------------------------------------------------------------------------- The refusal arms ---------------------------------------------------------------------------


def test_an_invalid_tag_stops_the_script_before_the_overrides(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` on the sibling: no overrides, no success line, the sibling's exit."""
    old, new, files = run_both(tmp_path, env_extra={"IMAGE_TAG": "not a tag", "WEB_TAG": "web-abc"})
    assert old[0] == 1
    assert old[1] == ""
    assert "✗ Invalid tag format: not a tag" in old[2]
    assert "Image tags set" not in old[2]
    assert files["old_env"] == ""
    assert_identical(old, new, files)


def test_a_tag_build_with_no_ref_name_is_the_siblings_line_81(
    tmp_path: pathlib.Path,
) -> None:
    """The one diagnostic that carries a program name, and its line is pinned."""
    root = fixture_root(tmp_path, "v1.0.0")
    old, new, files = run_both(
        tmp_path,
        env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": None},
        root=root,
    )
    assert old[0] == 1
    assert strip_prog(old[2]) == (
        "<prog>: line 81: GITHUB_REF_NAME: GITHUB_REF_NAME is not set for a tag build\n"
    )
    assert "line 81:" in new[2], "the port must keep the twin's line number"
    assert_identical(old, new, files)


def test_defect_e_an_unset_github_env_claims_success_having_set_nothing(
    tmp_path: pathlib.Path,
) -> None:
    """The caller asked for tags to be set. Nothing was, and the exit is 0."""
    old, new, files = run_both(
        tmp_path,
        env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": "renet-abc"},
        github_env=None,
    )
    assert old[0] == 0, "the twin's DEFECT E changed; re-read the module docstring"
    assert "⚠ GITHUB_ENV not set, skipping --env-file" in old[2]
    assert "✓ Image tags set (web=web-abc renet=renet-abc)" in old[2]
    assert "amd64" not in old[2]
    assert "amd64" not in old[1]
    assert_identical(old, new, files)
    assert port.GITHUB_ENV_IS_SILENTLY_OPTIONAL == "GITHUB_ENV"


def test_an_unwritable_github_env_dies_in_the_sibling_and_the_port_dies_louder(
    tmp_path: pathlib.Path,
) -> None:
    """A KNOWN DIVERGENCE, and it belongs to `derive_image_tag`, not to this port.

    The unwritable target is reached by the SIBLING first (it writes TAG, WEB_TAG and RENET_TAG before this script appends anything), so `set-image-tags.sh`'s own line 33 is unreachable in this case and what the two sides are really being compared on is `derive-image-tag.sh:134` against `derive_image_tag.write_github_env`:

        $ IMAGE_TAG=v1.2.3 GITHUB_ENV=/nope/x.txt bash .ci/scripts/ci/set-image-tags.sh
        <path>/derive-image-tag.sh: line 134: /nope/x.txt: No such file or directory
        exit=1

        $ IMAGE_TAG=v1.2.3 GITHUB_ENV=/nope/x.txt PYTHONPATH=.ci \\
            python3 -m rediacc_ci.ci.set_image_tags
        Traceback (most recent call last): ... FileNotFoundError: [Errno 2] ...
        exit=1

    The STATUS agrees; the stderr does not, and a traceback where the twin prints one line reads as a crash in the porting harness rather than as a bad path. `derive_image_tag.py` is another wave's file and is not repaired from here, so the disagreement is PINNED instead of hidden: when `write_github_env` and `write_github_output` learn to catch OSError, this test goes red, and the
    fix is to delete the two `assert` lines about the traceback and call `assert_identical` like every other case in this file.
    """
    old, new, files = run_both(
        tmp_path,
        env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc"},
        github_env=str(tmp_path / "no-such-dir" / "env.txt"),
    )
    assert old[0] == 1
    assert new[0] == old[0], "the exit codes still have to agree"
    assert old[1] == new[1] == ""
    assert strip_prog(old[2]).endswith(
        "<prog>: line 134: %s: No such file or directory\n" % (tmp_path / "no-such-dir" / "env.txt")
    )
    assert "Image tags set" not in old[2]
    assert "Traceback (most recent call last)" in new[2], (
        "derive_image_tag.write_github_env now handles OSError; drop this pin and "
        "assert_identical instead"
    )
    assert files == {}, "this case supplies its own GITHUB_ENV path, so nothing is captured"


def test_the_scripts_own_append_names_its_own_line_when_it_fails(
    tmp_path: pathlib.Path,
) -> None:
    """`append_override` directly, because the differential cannot reach it.

    Twin line 33 is only ever reached when the sibling has ALREADY appended three names to the same file, so any target that breaks this append breaks the sibling's first. The branch is still real -- a target removed or remounted read-only between the two writes, or a full disk -- and without a test it is a code path nobody has ever run. Driven here as a unit, since a differential
    cannot produce the state.
    """
    target = str(tmp_path / "gone" / "env.txt")
    with pytest.raises(SystemExit) as refusal:
        port.append_override("WEB_TAG", "web-abc", target, port.WEB_TAG_LINE)
    assert refusal.value.code == 1


# --------------------------------------------------------------------------- Colour, and the pins ---------------------------------------------------------------------------


def test_colour_is_emitted_on_a_terminal_by_both_sides(tmp_path: pathlib.Path) -> None:
    """stderr on a pty. The one branch a developer actually sees."""
    old, new, files = run_both(
        tmp_path, env_extra={"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc"}, tty="stderr"
    )
    assert diff.escape_bytes(old[2]) > 0, "the twin must colour a tty"
    assert_identical(old, new, files)


def test_the_pinned_line_numbers_still_point_at_the_twins_lines() -> None:
    """The two `>>"$GITHUB_ENV"` appends, re-derived from the twin.

    Without this the port would keep printing `line 33` after someone inserted a line above it, and every differential above would still pass: both sides would be wrong together only until the twin moved, and then the failure would name a byte difference instead of the reason for it.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    assert 'echo "WEB_TAG=${WEB_TAG}-amd64"' in lines[port.WEB_TAG_LINE - 1]
    assert 'echo "RENET_TAG=${RENET_TAG}-amd64"' in lines[port.RENET_TAG_LINE - 1]
    # The table is a reader's index into those two lines, so it is checked against them rather than left as a comment that can quietly go stale.
    assert port.OVERRIDES == (("WEB_TAG", port.WEB_TAG_LINE), ("RENET_TAG", port.RENET_TAG_LINE))
    assert port.WEB_TAG_LINE < port.RENET_TAG_LINE, "web is appended first"


def test_the_twin_is_still_the_one_live_caller_of_the_ported_sibling() -> None:
    """If a second caller appears, the in-process call above needs re-arguing."""
    found = subprocess.run(
        ["git", "-C", diff.repo(), "grep", "-l", "derive-image-tag.sh", "--", ".ci", ".github"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert TWIN in found
    assert ".ci/scripts/ci/derive-image-tag.sh" in found
