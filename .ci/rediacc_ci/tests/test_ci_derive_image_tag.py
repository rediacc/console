"""`rediacc_ci.ci.derive_image_tag` against its bash twin.

EVERY CASE RUNS IN A DISPOSABLE GIT REPOSITORY UNDER `tmp_path`, NEVER IN THE
CHECKOUT. The auto-derive arm reads `git tag -l 'v*'`, so running it here would
make the expected answer whatever the console repo happens to be tagged at that
hour -- a test that passes today and fails after the next release. `scratch_repo`
builds a one-commit repository with exactly the tags a case needs, and
`assert_is_scratch` re-derives `git rev-parse --show-toplevel` before any case
uses it, so a bug in the fixture cannot point the differential at the real tree.

THE FAKE `git` IS RECORDING, AND IT REFUSES `fetch`. The twin's shallow-clone
arm runs `git fetch --tags --force --no-recurse-submodules origin`, which is a
NETWORK call. A scratch repository has no `origin`, so a real git would fail
locally and never reach the network -- but "would fail locally" is a property of
the fixture, not a guarantee, and a differential that depends on it is one
`git remote add` away from dialling out. So the fetch arm is driven through a
fake `git` that logs its exact argv and exits non-zero for `fetch` while
delegating everything else to the real binary. Both sides get the same fake and
the two call logs are compared.

WHAT IS NORMALISED. Two of the twin's exits are bash's own `${...?message}`
diagnostics, which begin `<program>: line <N>:`, and the help text interpolates
`$0`. The program NAME necessarily differs between a `.sh` and a module file, so
`strip_prog` replaces that one token and `help_body` drops it from the help
lines; the line NUMBERS are compared, because a drifting line number is exactly
the silent failure this pinning exists to catch.

The K=5 ledger is `.ci/shadow/w7p6-derive-image-tag.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-derive-image-tag --assert
--k 5`).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci.ci import derive_image_tag as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/derive-image-tag.sh"
MODULE = "rediacc_ci.ci.derive_image_tag"

_PROG = re.compile(r"^\S+: line ", re.MULTILINE)

# A fake `git` that records argv and delegates to the real one, except `fetch`.
FAKE_GIT_SRC = """#!{python}
import os
import subprocess
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_GIT_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("FAKEGIT| " + " ".join(argv) + "\\n")
if argv[:1] == ["fetch"]:
    sys.stderr.write("fatal: 'origin' does not appear to be a git repository\\n")
    sys.exit(128)
sys.exit(subprocess.run(["{git}", *argv], check=False).returncode)
"""


def strip_prog(text: str) -> str:
    return _PROG.sub("<prog>: line ", text)


_HELP_PROG = re.compile(r"\S*derive[-_]image[-_]tag\.(?:sh|py)")


def help_body(stdout: str) -> list[str]:
    """The help text with the program's own name replaced and runs collapsed.

    `$0` appears five times (the usage line and four examples), and the column
    alignment of the four example comments is padded to a fixed width, so the
    LENGTH of the name changes the trailing spacing too. The name becomes
    `<prog>` and whitespace runs collapse; every option, every description and
    both auto-derivation lines survive and are compared.
    """
    return [
        re.sub(r"\s+", " ", _HELP_PROG.sub("<prog>", line)).strip() for line in stdout.split("\n")
    ]


def assert_is_scratch(repo: pathlib.Path) -> None:
    """Refuse to touch anything that is not the disposable repository.

    Not defensive theatre: every git command below is run with `-C <repo>`, and
    a `-C` that silently resolved into the real checkout would run `git tag`
    against work in progress. `--show-toplevel` is the only answer that settles
    it, and it must NOT be the console tree.
    """
    top = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert top == str(repo.resolve()), "scratch repo resolved to %r" % top
    assert top != diff.repo(), "refusing to operate on the real checkout"


def scratch_repo(tmp_path: pathlib.Path, *tags: str) -> pathlib.Path:
    """A one-commit git repository carrying exactly `tags`."""
    repo = tmp_path / "scratch"
    repo.mkdir(exist_ok=True)
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "scratch@example.invalid")
    git("config", "user.name", "Scratch")
    (repo / "README").write_text("scratch\n", encoding="utf-8")
    git("add", "README")
    git("commit", "-q", "-m", "scratch")
    assert_is_scratch(repo)
    for tag in tags:
        git("tag", tag)
    return repo


def make_fake_git(tmp_path: pathlib.Path) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "git"
    script.write_text(
        FAKE_GIT_SRC.format(python=sys.executable, git=shutil.which("git")), encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    tmp_path: pathlib.Path,
    *args: str,
    cwd: pathlib.Path | None = None,
    env_extra: dict[str, str | None] | None = None,
    fake_git: bool = False,
    outputs: bool = False,
    seed: str = "",
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], dict[str, str | None]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    workdir = str(cwd) if cwd is not None else diff.repo()

    files: dict[str, pathlib.Path] = {}
    envs: dict[str, dict[str, str | None]] = {}
    bindir = make_fake_git(tmp_path) if fake_git else None
    for side in ("old", "new"):
        env: dict[str, str | None] = dict(env_extra or {})
        if bindir is not None:
            env["PATH"] = "%s:%s" % (bindir, os.environ.get("PATH", ""))
            log = tmp_path / ("%s-gitcalls.txt" % side)
            log.write_text("", encoding="utf-8")
            env["FAKE_GIT_LOG"] = str(log)
            files["%s_gitlog" % side] = log
        if outputs:
            for name in ("GITHUB_OUTPUT", "GITHUB_ENV"):
                path = tmp_path / ("%s-%s.txt" % (side, name.lower()))
                path.write_text(seed, encoding="utf-8")
                env[name] = str(path)
                files["%s_%s" % (side, name.lower())] = path
        envs[side] = env

    old = diff.bash_streams(
        "bash %s/%s %s" % (diff.repo(), TWIN, quoted),
        env=diff.env_for(**envs["old"]),
        cwd=workdir,
        tty=tty,
        timeout=30,
    )
    new = diff.bash_streams(
        "python3 -m %s %s" % (MODULE, quoted),
        env=diff.env_for(
            **envs["new"],
            PYTHONPATH="%s/.ci" % diff.repo(),
            PYTHONDONTWRITEBYTECODE="1",
        ),
        cwd=workdir,
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
            assert files["new_" + key[4:]] == value, "%s diverged" % key[4:]


# --------------------------------------------------------------------------- Explicit --version ---------------------------------------------------------------------------


def test_an_explicit_version_wins_over_everything(tmp_path: pathlib.Path) -> None:
    repo = scratch_repo(tmp_path, "v1.0.0")
    old, new, files = run_both(
        tmp_path,
        "--version",
        "v9.9.9",
        cwd=repo,
        env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v0.0.1"},
    )
    assert old[0] == 0
    assert old[1] == "v9.9.9\n"
    assert old[2] == "✓ Using explicit version: v9.9.9\n"
    assert_identical(old, new, files)


def test_defect_b_an_empty_explicit_version_is_silently_auto_derived(
    tmp_path: pathlib.Path,
) -> None:
    """`${2?...}` refuses ABSENT, not EMPTY, and the decision is `[[ -n "$VERSION" ]]`.

    A blank `workflow_dispatch` input therefore produces a tag nobody asked for
    rather than a refusal, and the only sign of it is on stderr.
    """
    repo = scratch_repo(tmp_path, "v3.4.5")
    old, new, files = run_both(tmp_path, "--version", "", cwd=repo)
    assert old[0] == 0, "the twin's DEFECT B changed; re-read the module docstring"
    assert old[1] == "3.4.5\n"
    assert "Auto-derived from git tags (local): 3.4.5" in old[2]
    assert "explicit" not in old[2]
    assert_identical(old, new, files)


def test_a_missing_version_argument_is_bashs_diagnostic_at_line_34(
    tmp_path: pathlib.Path,
) -> None:
    """bash names the POSITIONAL PARAMETER `2`, not the option. Verbatim."""
    old, new, files = run_both(tmp_path, "--version")
    assert old[0] == 1
    assert strip_prog(old[2]) == "<prog>: line 34: 2: --version requires an argument\n"
    assert old[1] == ""
    assert_identical(old, new, files)


# --------------------------------------------------------------------------- Tag builds ---------------------------------------------------------------------------


def test_a_tag_build_uses_the_ref_name(tmp_path: pathlib.Path) -> None:
    repo = scratch_repo(tmp_path, "v1.0.0")
    old, new, files = run_both(
        tmp_path, cwd=repo, env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v2.3.4"}
    )
    assert old[1] == "v2.3.4\n"
    assert old[2] == "✓ Auto-derived from tag: v2.3.4\n"
    assert_identical(old, new, files)


def test_a_tag_build_keeps_the_leading_v_where_the_branch_arm_strips_it(
    tmp_path: pathlib.Path,
) -> None:
    """The asymmetry is real: `v2.3.4` from a tag build, `3.4.5` from git tags."""
    repo = scratch_repo(tmp_path, "v3.4.5")
    tag_build, _, _ = run_both(
        tmp_path, cwd=repo, env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v2.3.4"}
    )
    branch_build, _, _ = run_both(tmp_path, cwd=repo, env_extra={"GITHUB_REF_TYPE": "branch"})
    assert tag_build[1] == "v2.3.4\n"
    assert branch_build[1] == "3.4.5\n"


def test_a_tag_build_without_a_ref_name_is_refused_at_line_81(
    tmp_path: pathlib.Path,
) -> None:
    old, new, files = run_both(
        tmp_path, env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": None}
    )
    assert old[0] == 1
    assert strip_prog(old[2]) == (
        "<prog>: line 81: GITHUB_REF_NAME: GITHUB_REF_NAME is not set for a tag build\n"
    )
    assert_identical(old, new, files)


def test_a_tag_build_with_an_empty_ref_name_reaches_the_format_check(
    tmp_path: pathlib.Path,
) -> None:
    """`${VAR?...}` accepts an empty value, so the refusal comes later and elsewhere."""
    old, new, files = run_both(
        tmp_path, env_extra={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": ""}
    )
    assert old[0] == 1
    assert old[2] == (
        "✓ Auto-derived from tag: \n"
        "✗ Invalid tag format: \n"
        "✗ Tags must contain only alphanumeric characters, dots, hyphens, and underscores\n"
    )
    assert_identical(old, new, files)


# --------------------------------------------------------------------------- Branch builds: the git-tag ladder ---------------------------------------------------------------------------


def test_the_branch_arm_picks_the_highest_version_not_the_highest_string(
    tmp_path: pathlib.Path,
) -> None:
    """`--sort=-v:refname` puts v1.10.0 above v1.9.0. A lexicographic sort does not.

    This is the one case a hand-rolled Python sort would get wrong, and it is why
    the port shells out to git instead of reimplementing the ordering.
    """
    repo = scratch_repo(tmp_path, "v1.9.0", "v1.10.0", "v1.2.0")
    old, new, files = run_both(
        tmp_path, cwd=repo, env_extra={"GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"}
    )
    assert old[1] == "1.10.0\n"
    assert "Auto-derived from git tags (main): 1.10.0" in old[2]
    assert_identical(old, new, files)


def test_a_branch_build_without_a_ref_name_says_local(tmp_path: pathlib.Path) -> None:
    repo = scratch_repo(tmp_path, "v1.0.0")
    old, new, files = run_both(tmp_path, cwd=repo, env_extra={"GITHUB_REF_NAME": None})
    assert "Auto-derived from git tags (local): 1.0.0" in old[2]
    assert_identical(old, new, files)
    assert port.LOCAL_BRANCH == "local"


def test_non_v_tags_are_invisible_and_the_fetch_arm_then_fires(
    tmp_path: pathlib.Path,
) -> None:
    """No `v*` tag means the shallow-clone fetch, and then the `latest` fallback.

    The fake git records the fetch rather than performing it, and the two sides'
    call logs must be identical -- which is what proves the port sends the same
    four flags in the same order.
    """
    repo = scratch_repo(tmp_path, "release-1", "2.0.0")
    old, new, files = run_both(
        tmp_path, cwd=repo, env_extra={"GITHUB_REF_NAME": "topic"}, fake_git=True
    )
    assert old[0] == 0
    assert old[1] == "latest\n"
    assert "Auto-derived from git tags (topic): latest" in old[2]
    assert files["old_gitlog"] == (
        "FAKEGIT| tag -l v*\n"
        "FAKEGIT| fetch --tags --force --no-recurse-submodules origin\n"
        "FAKEGIT| tag -l v* --sort=-v:refname\n"
    )
    assert_identical(old, new, files)


def test_the_fetch_is_skipped_when_a_v_tag_is_already_present(
    tmp_path: pathlib.Path,
) -> None:
    """The negative control for the case above: two git calls, no fetch."""
    repo = scratch_repo(tmp_path, "v5.0.0")
    old, new, files = run_both(tmp_path, cwd=repo, fake_git=True)
    assert old[1] == "5.0.0\n"
    assert "fetch" not in files["old_gitlog"]
    assert files["old_gitlog"].count("FAKEGIT|") == 2
    assert_identical(old, new, files)


def test_the_placeholder_version_falls_back_to_latest(tmp_path: pathlib.Path) -> None:
    """Every package.json here carries `0.0.0-dev`; the twin refuses to ship it."""
    repo = scratch_repo(tmp_path, "v0.0.0-dev")
    old, new, files = run_both(tmp_path, cwd=repo)
    assert old[1] == "latest\n"
    assert_identical(old, new, files)
    assert port.PLACEHOLDER_VERSION == "0.0.0-dev"


def test_outside_a_git_repository_the_answer_is_latest(tmp_path: pathlib.Path) -> None:
    """`git tag` failing is swallowed twice over, so this cannot raise."""
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    old, new, files = run_both(tmp_path, cwd=bare, fake_git=True)
    assert old[0] == 0
    assert old[1] == "latest\n"
    assert_identical(old, new, files)


def test_a_missing_git_derives_latest_and_exits_zero(tmp_path: pathlib.Path) -> None:
    """The missing-tool arm, and it is GREEN. Pinned in both directions.

    All three git calls have their stderr on `/dev/null` and their status either
    tested or `|| true`d, so a machine without git prints nothing about it and
    ships an image tagged `latest`. The port raised `FileNotFoundError` here
    until `git_stdout` existed, which is the divergence this case keeps out.
    """
    bindir = tmp_path / "nogit"
    bindir.mkdir()
    # `head` and `sed` are in the twin's tag pipeline and only GIT's stderr is redirected there, so dropping them too would put a second, unrelated `command not found` on stderr and test the wrong absence.
    for tool in ("bash", "python3", "uname", "dirname", "cat", "sed", "head", "date"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    old, new, files = run_both(tmp_path, env_extra={"PATH": str(bindir)})
    assert old[0] == 0, "the twin's missing-git arm changed; re-read the docstring"
    assert old[1] == "latest\n"
    assert "✓ Auto-derived from git tags (local): latest\n" in old[2]
    assert "command not found" not in old[2], "the twin says nothing about the missing tool"
    assert_identical(old, new, files)


def test_only_the_first_leading_v_is_stripped(tmp_path: pathlib.Path) -> None:
    """`sed 's/^v//'` is one substitution at the start, not a strip of all v's."""
    repo = scratch_repo(tmp_path, "vv1.0.0")
    old, new, files = run_both(tmp_path, cwd=repo)
    assert old[1] == "v1.0.0\n"
    assert_identical(old, new, files)


# --------------------------------------------------------------------------- Validation ---------------------------------------------------------------------------


def test_an_invalid_tag_format_is_two_error_lines_and_exit_1(
    tmp_path: pathlib.Path,
) -> None:
    old, new, files = run_both(tmp_path, "--version", "a b")
    assert old[0] == 1
    assert old[2] == (
        "✓ Using explicit version: a b\n"
        "✗ Invalid tag format: a b\n"
        "✗ Tags must contain only alphanumeric characters, dots, hyphens, and underscores\n"
    )
    assert old[1] == "", "nothing reaches stdout when validation fails"
    assert_identical(old, new, files)


def test_the_boundary_of_the_length_check_is_128(tmp_path: pathlib.Path) -> None:
    """128 passes, 129 fails. An off-by-one here would be invisible otherwise."""
    ok, ok_new, ok_files = run_both(tmp_path, "--version", "a" * 128)
    assert ok[0] == 0
    assert ok[1] == "a" * 128 + "\n"
    assert_identical(ok, ok_new, ok_files)

    bad, bad_new, bad_files = run_both(tmp_path, "--version", "a" * 129)
    assert bad[0] == 1
    assert "✗ Tag too long: 129 characters (max 128)\n" in bad[2]
    assert_identical(bad, bad_new, bad_files)
    assert port.MAX_TAG_LENGTH == 128


def test_the_format_check_runs_before_the_length_check(tmp_path: pathlib.Path) -> None:
    """The ORDER is what makes bytes-vs-characters unable to diverge.

    A 200-character non-ASCII tag is rejected for its FORMAT, never reaching the
    length comparison where bash counts bytes under LC_ALL=C and Python counts
    characters. Reorder the two checks and the two implementations start
    disagreeing on exactly this input.
    """
    old, new, files = run_both(tmp_path, "--version", "é" * 200)
    assert old[0] == 1
    assert "Invalid tag format" in old[2]
    assert "Tag too long" not in old[2]
    assert_identical(old, new, files)


def test_dots_hyphens_and_underscores_are_all_accepted(tmp_path: pathlib.Path) -> None:
    for tag in ("v1.2.3", "1.2.3-rc.1", "edge_2026", "-leading-hyphen", ".leading-dot"):
        old, new, files = run_both(tmp_path, "--version", tag)
        assert old[0] == 0, tag
        assert old[1] == tag + "\n"
        assert_identical(old, new, files)


# --------------------------------------------------------------------------- Output modes ---------------------------------------------------------------------------


def test_github_output_mode_appends_one_line(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--version", "v1", "--github-output", outputs=True)
    assert files["old_github_output"] == "tag=v1\n"
    assert files["old_github_env"] == "", "--github-output must not touch GITHUB_ENV"
    assert "✓ Set GITHUB_OUTPUT: tag=v1\n" in old[2]
    assert old[1] == "v1\n"
    assert_identical(old, new, files)


def test_env_file_mode_appends_three_lines_in_order(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--version", "v1", "--env-file", outputs=True)
    assert files["old_github_env"] == "TAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"
    assert files["old_github_output"] == ""
    assert "✓ Set GITHUB_ENV: TAG=v1, WEB_TAG=v1, RENET_TAG=v1\n" in old[2]
    assert_identical(old, new, files)
    assert port.ENV_FILE_NAMES == ("TAG", "WEB_TAG", "RENET_TAG")


def test_both_output_modes_together(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, "--version", "v1", "--github-output", "--env-file", outputs=True
    )
    assert files["old_github_output"] == "tag=v1\n"
    assert files["old_github_env"] == "TAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"
    assert_identical(old, new, files)


def test_an_unset_output_target_is_a_warning_and_still_exit_0(
    tmp_path: pathlib.Path,
) -> None:
    """A skipped export is NOT an error here, and the tag still reaches stdout."""
    old, new, files = run_both(
        tmp_path,
        "--version",
        "v1",
        "--github-output",
        "--env-file",
        env_extra={"GITHUB_OUTPUT": None, "GITHUB_ENV": None},
    )
    assert old[0] == 0
    assert old[1] == "v1\n"
    assert "⚠ GITHUB_OUTPUT not set, skipping --github-output\n" in old[2]
    assert "⚠ GITHUB_ENV not set, skipping --env-file\n" in old[2]
    assert_identical(old, new, files)


def test_an_empty_output_target_counts_as_unset(tmp_path: pathlib.Path) -> None:
    """`[[ -n "${GITHUB_OUTPUT:-}" ]]` is emptiness, not presence."""
    old, new, files = run_both(
        tmp_path, "--version", "v1", "--github-output", env_extra={"GITHUB_OUTPUT": ""}
    )
    assert "⚠ GITHUB_OUTPUT not set, skipping --github-output\n" in old[2]
    assert_identical(old, new, files)


def test_the_output_files_are_appended_to_not_truncated(tmp_path: pathlib.Path) -> None:
    """`>>`, not `>`. A step that overwrote GITHUB_ENV would erase earlier steps."""
    old, new, files = run_both(
        tmp_path, "--version", "v1", "--env-file", outputs=True, seed="PRE=1\n"
    )
    assert files["old_github_env"] == "PRE=1\nTAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"
    assert_identical(old, new, files)


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_an_unknown_option_is_refused(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--nope")
    assert old[0] == 1
    assert old[2] == "✗ Unknown option: --nope\n"
    assert_identical(old, new, files)


def test_a_positional_argument_is_refused_too(tmp_path: pathlib.Path) -> None:
    """The `*)` arm is not a flag test. This script takes no positionals at all."""
    old, new, files = run_both(tmp_path, "v1.2.3")
    assert old[0] == 1
    assert old[2] == "✗ Unknown option: v1.2.3\n"
    assert_identical(old, new, files)


def test_the_last_version_wins_when_it_is_repeated(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--version", "v1", "--version", "v2")
    assert old[1] == "v2\n"
    assert_identical(old, new, files)


def test_both_help_spellings_exit_0_with_the_same_text(tmp_path: pathlib.Path) -> None:
    short, short_new, _ = run_both(tmp_path, "-h")
    long, long_new, _ = run_both(tmp_path, "--help")
    assert short[0] == long[0] == 0
    assert short[2] == long[2] == ""
    assert help_body(short[1]) == help_body(long[1])
    assert help_body(short_new[1]) == help_body(short[1])
    assert help_body(long_new[1]) == help_body(long[1])


def test_help_wins_over_a_later_unknown_option(tmp_path: pathlib.Path) -> None:
    """The loop exits at `-h`; the `*)` arm is never reached. Order matters."""
    old, new, _ = run_both(tmp_path, "--help", "--nope")
    assert old[0] == 0
    assert new[0] == 0
    assert old[2] == ""
    assert new[2] == ""
    assert help_body(new[1]) == help_body(old[1])


def test_an_unknown_option_before_help_wins_instead(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--nope", "--help")
    assert old[0] == 1
    assert_identical(old, new, files)


def test_the_help_text_is_the_twins_help_text_verbatim() -> None:
    """The port's HELP_LINES are a COPY. Re-read the twin instead of restating it.

    Includes DEFECT A: the line claiming the branch arm "uses version from
    package.json" is wrong -- nothing in either file reads package.json -- and
    it is copied anyway, because the differential compares bytes. Removing it
    from the port without removing it from the twin is what this catches.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    for line in port.HELP_LINES:
        rendered = line.format(prog="$0")
        assert 'echo "%s"' % rendered in text, (
            "help line not found verbatim in the twin: %r" % rendered
        )

    # The liveness half of DEFECT A: the claim is only worth carrying while the twin really does mention package.json in its prose and never read it.
    assert "package.json" in text, "the docstring's DEFECT A is stale"
    executable = "\n".join(
        line for line in text.split("\n") if not line.lstrip().startswith(("#", "echo ", "log_"))
    )
    assert "package.json" not in executable, (
        "the twin now reads package.json; DEFECT A is fixed and the docstring is stale"
    )


def test_the_pinned_line_numbers_still_point_at_the_twins_lines() -> None:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert (
        lines[port.VERSION_ARG_LINE - 1].strip() == 'VERSION="${2?--version requires an argument}"'
    )
    assert (
        lines[port.REF_NAME_LINE - 1].strip()
        == 'TAG="${GITHUB_REF_NAME?GITHUB_REF_NAME is not set for a tag build}"'
    )


# --------------------------------------------------------------------------- Streams and colour ---------------------------------------------------------------------------


def test_the_tag_is_on_stdout_and_every_log_line_on_stderr(
    tmp_path: pathlib.Path,
) -> None:
    """The consuming step reads stdout. One line, the tag, and nothing else."""
    old, new, files = run_both(tmp_path, "--version", "v1", "--env-file", outputs=True)
    assert old[1] == "v1\n"
    assert "✓" not in old[1]
    assert_identical(old, new, files)


def test_colour_on_a_terminal_is_byte_identical(tmp_path: pathlib.Path) -> None:
    old, new, _ = run_both(tmp_path, "--version", "a b", tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new, _ = run_both(tmp_path, "--version", "a b", tty="stderr", env_extra={"NO_COLOR": "1"})
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]
