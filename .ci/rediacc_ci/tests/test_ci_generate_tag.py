"""`rediacc_ci.ci.generate_tag` against its bash twin.

WHAT IS FAKED AND WHAT IS NOT, because this twin is the one of the three whose external tools are SAFE. `git` here is only ever `rev-parse`, and `resolve-version.sh` only ever `git tag -l` -- reads, all of them, so the real binaries are used against DISPOSABLE FIXTURE REPOSITORIES built under `tmp_path`. Nothing in this file writes to `/home/developer/console`'s git data, creates a
tag, or reaches a network. `assert_scratch` re-derives `--show-toplevel` for every fixture and refuses if it ever resolves to the checkout.

The two cases that do run against the real repository -- `--self` and `--closure` -- are read-only `git rev-parse` calls, and they are the only way to prove the port agrees with the twin on the REAL closure content rather than on a fixture's.

TWO NORMALISATIONS, AND ONLY TWO.

  1. `$0` in `--help`. The twin prints its own `.sh` path and the port its
     `.py` path; `strip_program` removes exactly that token from the four lines
     that carry it and compares the rest byte for byte.
  2. THE TIME-BASED TAG. `date -u +%Y%m%d-%H%M%S` against
     `datetime.now(UTC).strftime(...)`: two processes started a second apart
     mint different tags, and no amount of care makes them the same. Same
     ruling as `test_deploy_write_release_sentinel`'s `released_at`: the field
     is normalised for the comparison, and the FORMAT is asserted separately on
     both sides, along with the two tags being within a few seconds of each
     other. Every other mode is deterministic and compared byte for byte.

The K=5 ledger is `.ci/shadow/w7p6-generate-tag.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-generate-tag --assert --k 5`). Its `--finding-re` matches the tag shapes on stdout, because the twin's whole success report is `✓ ` lines that `shadow-gate.ts` classifies as CHATTER before any regex is consulted.
"""

from __future__ import annotations

import datetime
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path as _Path
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import generate_tag as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/generate-tag.sh"
MODULE = "rediacc_ci.ci.generate_tag"

# `YYYYMMDD-HHMMSS`, the shape both sides must produce in the default mode.
TIME_TAG = re.compile(r"^[0-9]{8}-[0-9]{6}$")

# `git init` in a tree whose owner's global config may sign, template, or hook. Every fixture repo is built with these, so a developer's own git config cannot change what the differential measures.
GIT_FLAGS = [
    "-c",
    "user.email=w7p6@example.invalid",
    "-c",
    "user.name=w7p6",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "init.defaultBranch=main",
    "-c",
    "core.abbrev=7",
]


def assert_scratch(path: pathlib.Path) -> pathlib.Path:
    """Refuse to touch anything that is not a disposable fixture.

    Asked of every fixture before it is written to, because a mistyped path in a `git -C` is the one mistake in this file that could not be undone. The guard compares the resolved toplevel, not the string, so a symlinked tmpdir cannot slip past it.
    """
    resolved = path.resolve()
    assert str(resolved) != diff.repo(), "refusing to operate on the checkout"
    assert not str(resolved).startswith(diff.repo() + os.sep), (
        "fixture %s is inside the checkout" % resolved
    )
    return resolved


def git(repo: pathlib.Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *GIT_FLAGS, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def make_repo(path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A one-commit git repository holding exactly `files`. No tags."""
    assert_scratch(path)
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", *GIT_FLAGS, "init", "-q", str(path)], check=True, capture_output=True)
    # The guard again, this time on what git itself says the toplevel is. The first call guarded a path we chose; this one guards the path git chose, which is the one every destructive `git -C` below will act on.
    assert_scratch(_Path(git(path, "rev-parse", "--show-toplevel")))
    for name, body in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "fixture")
    return path


def run_both(
    *args: str,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = env_extra or {}
    twin = "%s/%s" % (diff.repo(), TWIN)
    old_env = diff.env_for(**extra)
    new_env = diff.env_for(**extra, PYTHONPATH="%s/.ci" % diff.repo(), PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams(
        "bash %s %s" % (twin, quoted), env=old_env, cwd=cwd, tty=tty, timeout=60
    )
    new = diff.bash_streams(
        "python3 -m %s %s" % (MODULE, quoted), env=new_env, cwd=cwd, tty=tty, timeout=60
    )
    return old, new


def assert_identical(
    *args: str,
    expect_exit: int,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    old, new = run_both(*args, cwd=cwd, env_extra=env_extra)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0], "exit: %r vs %r" % (new, old)
    assert new[1] == old[1], "stdout"
    assert new[2] == old[2], "stderr"
    return old


def strip_program(text: str) -> str:
    """Replace the program's own path with `<prog>` on the four lines carrying it.

    Exactly those four and nothing else: the `Usage:` line and the three `Examples:` lines. Every other line of the help block is compared byte for byte, so a reworded option description still reds.
    """
    out = []
    for line in text.split("\n"):
        if line.startswith("Usage: "):
            out.append("Usage: <prog>" + line[len("Usage: ") :].partition(" ")[1:][1])
        elif line.startswith(("  /", "  .")):
            _prog, sep, tail = line.strip().partition(" ")
            out.append("  <prog>" + sep + tail)
        else:
            out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------- Fixtures ---------------------------------------------------------------------------


@pytest.fixture
def submodule_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree shaped like the repo root, with a one-commit submodule inside."""
    root = assert_scratch(tmp_path / "tree")
    for name in (
        ".github/workflows/ci-build-renet.yml",
        ".github/workflows/ci-build-docker.yml",
        ".ci/scripts/build/build-renet.sh",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# %s\n" % name, encoding="utf-8")
    make_repo(
        root / "sub",
        {
            "Dockerfile": "FROM scratch\n",
            "Dockerfile.native": "FROM scratch\n",
            "build.sh": "#!/bin/bash\n",
        },
    )
    return root


@pytest.fixture
def closure_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A git repo holding every `rdc` closure path, and NO tags."""
    files = {}
    for path in port.CLOSURE_PATHS["rdc"]:
        # A directory entry is created as a directory with one file in it, so the tree oid the twin reads is a real tree.
        if path.endswith((".json", ".sh", ".ts", ".yml")):
            files[path] = "%s content\n" % path
        else:
            files["%s/keep.txt" % path] = "%s\n" % path
    return make_repo(tmp_path / "closure", files)


# --------------------------------------------------------------------------- Time-based mode (the default) ---------------------------------------------------------------------------


def test_the_default_mode_mints_a_utc_timestamp_tag() -> None:
    """Normalisation 2: the one field neither side can make identical."""
    old, new = run_both()
    assert old[0] == new[0] == 0
    old_tag = old[1].strip()
    new_tag = new[1].strip()
    assert TIME_TAG.match(old_tag), old_tag
    assert TIME_TAG.match(new_tag), new_tag
    assert old[2] == "✓ Generated CI tag: %s\n" % old_tag
    assert new[2] == "✓ Generated CI tag: %s\n" % new_tag
    old_at = datetime.datetime.strptime(old_tag, "%Y%m%d-%H%M%S").replace(tzinfo=datetime.UTC)
    new_at = datetime.datetime.strptime(new_tag, "%Y%m%d-%H%M%S").replace(tzinfo=datetime.UTC)
    assert abs((new_at - old_at).total_seconds()) < 30, "the two clocks disagree"


def test_the_time_tag_is_utc_and_not_local() -> None:
    """`date -u`. A port using `datetime.now()` would drift by the offset."""
    minted = port.time_tag()
    now = datetime.datetime.now(datetime.UTC)
    assert minted[:8] in (
        now.strftime("%Y%m%d"),
        (now - datetime.timedelta(seconds=60)).strftime("%Y%m%d"),
    )
    frozen = datetime.datetime(2026, 1, 20, 10, 46, 3, tzinfo=datetime.UTC)
    assert port.time_tag(frozen) == "20260120-104603"


def test_the_iso_week_bucket_is_percent_g_percent_v_not_percent_y_percent_w() -> None:
    """The twin's own reason: December 31 must not collide with January 1."""
    assert port.iso_week_bucket(datetime.datetime(2025, 12, 31, tzinfo=datetime.UTC)) == "202601"
    assert port.iso_week_bucket(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)) == "202601"
    assert port.iso_week_bucket(datetime.datetime(2026, 1, 5, tzinfo=datetime.UTC)) == "202602"
    live = subprocess.run(
        ["date", "-u", "+%G%V"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert port.iso_week_bucket() == live, "the port and `date -u +%G%V` disagree"


# --------------------------------------------------------------------------- --self ---------------------------------------------------------------------------


def test_self_mode_is_the_repos_short_head() -> None:
    old = assert_identical("--self", expect_exit=0)
    tag = old[1].strip()
    assert re.fullmatch(r"[0-9a-f]{7,40}", tag), tag
    assert old[2] == "✓ Generated self tag: %s\n" % tag


def test_self_mode_in_a_fixture_repo_agrees_with_git(closure_repo: pathlib.Path) -> None:
    old = assert_identical("--self", expect_exit=0, cwd=str(closure_repo))
    assert old[1].strip() == git(closure_repo, "rev-parse", "--short", "HEAD")


def test_self_mode_outside_a_repository_fails_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` on the assignment; git's own status and git's own stderr."""
    outside = assert_scratch(tmp_path / "not-a-repo")
    outside.mkdir()
    old, new = run_both("--self", cwd=str(outside))
    assert old[0] == new[0] == 128
    assert old[1] == new[1] == ""
    assert "not a git repository" in old[2].lower()


# --------------------------------------------------------------------------- --submodule ---------------------------------------------------------------------------


def test_submodule_mode_combines_the_commit_with_a_build_config_hash(
    submodule_tree: pathlib.Path,
) -> None:
    old = assert_identical("--submodule", "sub", expect_exit=0, cwd=str(submodule_tree))
    tag = old[1].strip()
    commit = git(submodule_tree / "sub", "rev-parse", "--short", "HEAD")
    assert re.fullmatch(r"%s-[0-9a-f]{12}" % re.escape(commit), tag), tag
    assert old[2] == "✓ Generated submodule tag (sub): %s\n" % tag


def test_the_config_half_of_the_tag_moves_when_a_build_config_file_moves(
    submodule_tree: pathlib.Path,
) -> None:
    """The membership rule's whole point, asserted on BOTH implementations."""
    before_old, before_new = run_both("--submodule", "sub", cwd=str(submodule_tree))
    (submodule_tree / ".github/workflows/ci-build-docker.yml").write_text(
        "# changed\n", encoding="utf-8"
    )
    after_old, after_new = run_both("--submodule", "sub", cwd=str(submodule_tree))
    assert before_old[1] != after_old[1], "the twin's tag did not move"
    assert before_new[1] == before_old[1]
    assert after_new[1] == after_old[1]


def test_the_real_renet_submodule_tag_is_identical_on_both_sides() -> None:
    """Not a fixture: the tag CI actually publishes, hashed from real bytes."""
    old = assert_identical("--submodule", "private/renet", expect_exit=0)
    assert re.fullmatch(r"[0-9a-f]{7,40}-[0-9a-f]{12}\n", old[1]), old[1]


def test_a_missing_submodule_directory_is_refused(submodule_tree: pathlib.Path) -> None:
    old = assert_identical("--submodule", "no/such", expect_exit=1, cwd=str(submodule_tree))
    assert old[1] == ""
    assert old[2] == "✗ Submodule not found: no/such\n"


def test_a_directory_that_is_not_a_repository_is_refused(
    submodule_tree: pathlib.Path,
) -> None:
    (submodule_tree / "plain").mkdir()
    old = assert_identical("--submodule", "plain", expect_exit=1, cwd=str(submodule_tree))
    assert old[2] == "✗ Not a git repository: plain\n"


def test_a_gitfile_submodule_counts_as_a_repository(
    submodule_tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """`[[ ! -d .git ]] && [[ ! -f .git ]]` -- a worktree's `.git` is a FILE."""
    real = make_repo(tmp_path / "real", {"Dockerfile": "x\n"})
    linked = assert_scratch(submodule_tree / "linked")
    linked.mkdir()
    for name in ("Dockerfile", "Dockerfile.native", "build.sh"):
        (linked / name).write_text("x\n", encoding="utf-8")
    (linked / ".git").write_text("gitdir: %s/.git\n" % real, encoding="utf-8")
    old = assert_identical("--submodule", "linked", expect_exit=0, cwd=str(submodule_tree))
    assert old[1].strip().startswith(git(real, "rev-parse", "--short", "HEAD"))


@pytest.mark.parametrize(
    "missing",
    [
        "sub/Dockerfile",
        "sub/Dockerfile.native",
        "sub/build.sh",
        ".github/workflows/ci-build-renet.yml",
        ".github/workflows/ci-build-docker.yml",
        ".ci/scripts/build/build-renet.sh",
    ],
)
def test_every_build_config_input_is_fail_loud(submodule_tree: pathlib.Path, missing: str) -> None:
    """Six inputs, six controls. One silently-skipped entry is the whole risk."""
    (submodule_tree / missing).unlink()
    old = assert_identical("--submodule", "sub", expect_exit=1, cwd=str(submodule_tree))
    assert old[1] == ""
    assert old[2].splitlines()[0] == "✗ Build-config input not found: %s" % missing
    for line in port.BUILD_CONFIG_ADVICE:
        assert "✗ %s" % line in old[2]


def test_the_build_config_list_is_the_twins_list_in_order() -> None:
    """Order matters: it decides WHICH missing input is reported first."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    block = text.partition("BUILD_CONFIG_FILES=(")[2].partition(")")[0]
    in_twin = [line.strip().strip('"') for line in block.strip().split("\n")]
    assert in_twin == [t.format(sub="$SUBMODULE_PATH") for t in port.BUILD_CONFIG_FILES]


def test_defect_h_the_build_config_check_is_cwd_dependent(
    submodule_tree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """A correct submodule reached from the wrong directory blames the file."""
    elsewhere = assert_scratch(tmp_path / "elsewhere")
    elsewhere.mkdir()
    old = assert_identical(
        "--submodule",
        str(submodule_tree / "sub"),
        expect_exit=1,
        cwd=str(elsewhere),
    )
    assert (
        old[2].splitlines()[0]
        == "✗ Build-config input not found: .github/workflows/ci-build-renet.yml"
    )
    stale = "the twin has started explaining the real cause; update the finding"
    assert "cwd" not in old[2], stale
    assert "directory" not in old[2], stale


def test_defect_i_the_bare_commit_arm_is_unreachable() -> None:
    """`BUILD_CONFIG_FILES` is non-empty and every miss exits, so it never fires."""
    assert port.UNREACHABLE_BARE_COMMIT_TAG is True
    assert len(port.BUILD_CONFIG_FILES) > 0
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        assert 'CI_TAG="${SUBMODULE_COMMIT}-${CONFIG_SHORT}"' in fh.read()


# --------------------------------------------------------------------------- --closure ---------------------------------------------------------------------------


@pytest.mark.parametrize("closure", ["web", "rdc"])
def test_the_real_closure_tags_are_identical_on_both_sides(closure: str) -> None:
    """Against the REAL repository, which is what cd-stage.yml retags."""
    old = assert_identical("--closure", closure, expect_exit=0)
    tag = old[1].strip()
    assert re.fullmatch(r"%s-[0-9a-f]{12}" % closure, tag), tag
    assert old[2] == "✓ Generated closure tag (%s): %s\n" % (closure, tag)


def test_an_unknown_closure_is_refused() -> None:
    old = assert_identical("--closure", "bogus", expect_exit=1)
    assert old[1] == ""
    assert old[2] == "✗ Unknown closure: bogus (expected: web, rdc)\n"


def test_extra_changes_the_closure_key() -> None:
    plain = assert_identical("--closure", "rdc", expect_exit=0)
    keyed = assert_identical("--closure", "rdc", "--extra", "RENET=abc", expect_exit=0)
    assert plain[1] != keyed[1]


def test_extra_appends_rather_than_overwrites() -> None:
    """`EXTRA_KEY+="$2"`, so two `--extra` are the concatenation of both."""
    both = assert_identical("--closure", "rdc", "--extra", "a", "--extra", "b", expect_exit=0)
    joined = assert_identical("--closure", "rdc", "--extra", "ab", expect_exit=0)
    assert both[1] == joined[1]
    only_b = assert_identical("--closure", "rdc", "--extra", "b", expect_exit=0)
    assert both[1] != only_b[1], "the second --extra overwrote the first"


def test_a_missing_closure_input_is_fail_loud(closure_repo: pathlib.Path) -> None:
    git(closure_repo, "rm", "-r", "-q", "--cached", "tsconfig.json")
    (closure_repo / "tsconfig.json").unlink()
    git(closure_repo, "commit", "-q", "-m", "drop tsconfig")
    old = assert_identical("--closure", "rdc", expect_exit=1, cwd=str(closure_repo))
    assert old[2].splitlines()[0] == "✗ Closure input not found at HEAD: tsconfig.json"
    for line in port.CLOSURE_ADVICE:
        assert "✗ %s" % line.format(closure="rdc") in old[2]


def test_the_missing_input_reported_is_the_first_in_list_order(
    closure_repo: pathlib.Path,
) -> None:
    """Two missing entries, and the loop stops at the earlier one."""
    for path in ("packages/cli/keep.txt", "tsconfig.json"):
        git(closure_repo, "rm", "-r", "-q", "--cached", path)
    git(closure_repo, "commit", "-q", "-m", "drop two")
    old = assert_identical("--closure", "rdc", expect_exit=1, cwd=str(closure_repo))
    assert "✗ Closure input not found at HEAD: packages/cli\n" in old[2]
    assert "tsconfig.json" not in old[2]


def test_an_untagged_checkout_falls_back_to_a_distinguishing_key(
    closure_repo: pathlib.Path,
) -> None:
    """An EMPTY marker would collapse every untagged build to one key."""
    head = git(closure_repo, "rev-parse", "HEAD")
    old = assert_identical("--closure", "rdc", expect_exit=0, cwd=str(closure_repo))
    assert (
        "⚠ No version tag reachable; closure key falls back to 'untagged-%s'. "
        "Image reuse is disabled for this build.\n" % head in old[2]
    )
    assert old[1].strip().startswith("rdc-")


def test_cutting_a_tag_moves_the_closure_key(closure_repo: pathlib.Path) -> None:
    """The measured v1.2.12 bug: the key must move when the baked version does."""
    untagged = assert_identical("--closure", "rdc", expect_exit=0, cwd=str(closure_repo))
    git(closure_repo, "tag", "v1.2.12")
    tagged = assert_identical("--closure", "rdc", expect_exit=0, cwd=str(closure_repo))
    assert tagged[1] != untagged[1]
    assert "No version tag reachable" not in tagged[2]
    git(closure_repo, "tag", "v1.2.13")
    bumped = assert_identical("--closure", "rdc", expect_exit=0, cwd=str(closure_repo))
    assert bumped[1] != tagged[1], "the key did not move when the tag did"


def test_the_closure_path_lists_are_the_twins_lists_in_order() -> None:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    for closure, paths in port.CLOSURE_PATHS.items():
        block = text.partition("        %s)\n            CLOSURE_PATHS=(" % closure)[2]
        block = block.partition(")")[0]
        in_twin = [line.strip() for line in block.strip().split("\n")]
        assert in_twin == list(paths), closure


# --------------------------------------------------------------------------- Output sinks ---------------------------------------------------------------------------


def test_output_writes_the_tag_and_says_so(tmp_path: pathlib.Path) -> None:
    old_file = assert_scratch(tmp_path / "old.txt")
    new_file = assert_scratch(tmp_path / "new.txt")
    twin = "%s/%s" % (diff.repo(), TWIN)
    old = diff.bash_streams(
        "bash %s --self --output %s" % (twin, shlex.quote(str(old_file))),
        env=diff.env_for(),
        timeout=60,
    )
    new = diff.bash_streams(
        "python3 -m %s --self --output %s" % (MODULE, shlex.quote(str(new_file))),
        env=diff.env_for(PYTHONPATH="%s/.ci" % diff.repo(), PYTHONDONTWRITEBYTECODE="1"),
        timeout=60,
    )
    assert old[0] == new[0] == 0
    assert old_file.read_text(encoding="utf-8") == new_file.read_text(encoding="utf-8")
    assert old_file.read_text(encoding="utf-8") == old[1]
    assert "✓ Wrote CI tag to: %s\n" % old_file in old[2]
    assert new[2].replace(str(new_file), str(old_file)) == old[2]


def test_github_output_appends_and_says_so(tmp_path: pathlib.Path) -> None:
    twin = "%s/%s" % (diff.repo(), TWIN)
    results = {}
    for label, cmd, env in (
        ("old", "bash %s --self --github-output" % twin, {}),
        (
            "new",
            "python3 -m %s --self --github-output" % MODULE,
            {"PYTHONPATH": "%s/.ci" % diff.repo(), "PYTHONDONTWRITEBYTECODE": "1"},
        ),
    ):
        target = assert_scratch(tmp_path / ("gho-%s.txt" % label))
        target.write_text("pre=1\n", encoding="utf-8")
        run = diff.bash_streams(cmd, env=diff.env_for(**env, GITHUB_OUTPUT=str(target)), timeout=60)
        results[label] = (run, target.read_text(encoding="utf-8"))
    (old_run, old_text) = results["old"]
    (new_run, new_text) = results["new"]
    assert old_run[0] == new_run[0] == 0
    assert old_text == new_text
    assert old_text.startswith("pre=1\nci_tag=")
    assert "✓ Set GITHUB_OUTPUT: ci_tag=" in old_run[2]
    assert old_run[2] == new_run[2]


def test_defect_g_github_output_without_the_variable_is_a_silent_no_op() -> None:
    """The caller asked. Both sides say nothing and exit 0."""
    assert port.GITHUB_OUTPUT_IS_SILENTLY_OPTIONAL is True
    asked = assert_identical("--self", "--github-output", expect_exit=0)
    plain = assert_identical("--self", expect_exit=0)
    assert asked == plain, "the request left no trace at all"
    assert "GITHUB_OUTPUT" not in asked[2]


def test_an_unwritable_output_path_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    target = assert_scratch(tmp_path / "no-such-dir") / "tag.txt"
    old, new = run_both("--self", "--output", str(target))
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == ""


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_help_is_the_twins_help_modulo_the_program_name() -> None:
    old, new = run_both("--help")
    assert old[0] == new[0] == 0
    assert old[2] == new[2] == ""
    assert strip_program(new[1]) == strip_program(old[1])
    assert "Generate time-based tag (YYYYMMDD-HHMMSS)" in old[1]


def test_short_h_is_the_same_as_long_help() -> None:
    old, new = run_both("-h")
    assert strip_program(new[1]) == strip_program(old[1])


def test_help_wins_over_a_mode_flag_that_precedes_it() -> None:
    """The `case` returns from inside the loop, so `--self --help` is help."""
    old, new = run_both("--self", "--help")
    assert old[0] == new[0] == 0
    assert "Usage:" in old[1]
    assert strip_program(new[1]) == strip_program(old[1])


def test_an_unknown_option_is_refused() -> None:
    old = assert_identical("--nope", expect_exit=1)
    assert old[1] == ""
    assert old[2] == "✗ Unknown option: --nope\n"


@pytest.mark.parametrize("opt", ["--output", "--submodule", "--closure", "--extra"])
def test_defect_j_a_value_option_as_the_last_token_dies_as_bash(opt: str) -> None:
    """Divergence 2: `$2: unbound variable` versus MISSING_VALUE."""
    old, new = run_both(opt)
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == ""
    assert "$2: unbound variable" in old[2]
    assert new[2] == (port.MISSING_VALUE % opt) + "\n"


def test_the_mode_precedence_is_silent(submodule_tree: pathlib.Path) -> None:
    """`--submodule` beats `--closure` beats `--self`, with no word about it."""
    both = assert_identical("--self", "--closure", "rdc", expect_exit=0)
    closure_only = assert_identical("--closure", "rdc", expect_exit=0)
    assert both == closure_only

    sub = assert_identical("--submodule", "sub", "--self", expect_exit=0, cwd=str(submodule_tree))
    sub_only = assert_identical("--submodule", "sub", expect_exit=0, cwd=str(submodule_tree))
    assert sub == sub_only


def test_a_repeated_value_option_takes_the_last_one() -> None:
    """Unlike `--extra`, `--closure` ASSIGNS, so the second wins."""
    old = assert_identical("--closure", "bogus", "--closure", "rdc", expect_exit=0)
    assert old[1].startswith("rdc-")


# --------------------------------------------------------------------------- Colour, and the module entry point ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical() -> None:
    old, new = run_both("--nope", tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides() -> None:
    old, new = run_both("--nope", tty="stderr", env_extra={"NO_COLOR": "1"})
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]


def test_the_info_line_goes_to_stderr_so_stdout_stays_capturable() -> None:
    """`log_info ... >&2`. A stream swap here would poison every `$(...)`."""
    old = assert_identical("--self", expect_exit=0)
    assert old[1].count("\n") == 1
    assert "Generated" not in old[1]


def test_the_module_runs_as_python_m() -> None:
    """The invocation the ledger records, proven to exist."""
    code, out, err = diff.bash_streams(
        "%s -m %s --self" % (sys.executable, MODULE),
        env=diff.env_for(PYTHONPATH="%s/.ci" % diff.repo(), PYTHONDONTWRITEBYTECODE="1"),
        timeout=60,
    )
    assert code == 0
    assert re.fullmatch(r"[0-9a-f]{7,40}\n", out), out
    assert "Traceback" not in err
