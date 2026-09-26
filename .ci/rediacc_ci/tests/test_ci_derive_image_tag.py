"""`rediacc_ci.ci.derive_image_tag`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/derive-image-tag.sh` and the port over the same disposable git repository and compared exit code, stdout, stderr, the fake `git`'s call log and the bytes appended to `$GITHUB_OUTPUT` and `$GITHUB_ENV`. The K=5 ledger `.ci/shadow/w7p6-derive-image-tag.observations.jsonl` recorded that comparison over five distinct
trees. The twin has now been deleted and every case that executed it compares against `goldens/derive-image-tag/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

EVERY CASE RUNS IN A DISPOSABLE GIT REPOSITORY, NEVER IN THE CHECKOUT. The auto-derive arm reads `git tag -l 'v*'`, so running it here would make the expected answer whatever the console repo happens to be tagged at that hour -- a test that passes today and fails after the next release. `scratch_repo` builds a one-commit repository with exactly the tags a case needs, and
`assert_is_scratch` re-derives `git rev-parse --show-toplevel` before any case uses it, so a bug in the fixture cannot point this file at the real tree.

THE FAKE `git` IS RECORDING, AND IT REFUSES `fetch`. The twin's shallow-clone arm ran `git fetch --tags --force --no-recurse-submodules origin`, which is a NETWORK call. A scratch repository has no `origin`, so a real git would fail locally and never reach the network -- but "would fail locally" is a property of the fixture, not a guarantee, and a test that depends on it is
one `git remote add` away from dialling out. So the fetch arm is driven through a fake `git` that logs its exact argv and exits non-zero for `fetch` while delegating everything else to the real binary. The recorded call log is what proves the port sends the same flags in the same order.

WHAT IS NORMALISED. Two of the twin's exits were bash's own `${...?message}` diagnostics, which begin `<program>: line <N>:`, and the help text interpolated `$0`. The program NAME necessarily differs between a `.sh` and a `.py`, so `strip_prog` replaces that one token and `help_body` drops it from the help lines; the line NUMBERS are recorded and compared, because a drifting
line number is exactly the silent failure this pinning exists to catch.

THE TWO STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE, and the recordings replace them. One re-read every `echo` in the twin's help block so the port's `HELP_LINES` could not drift from it, including DEFECT A -- the line claiming the branch arm "uses version from package.json", which nothing in either file ever read. The other re-read the two `${...?}` statements the
port quotes line numbers for. A deleted file does not drift; the port's copies still can, and `the-help-text` plus the two `line <N>` recordings pin every one of them to the byte.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import typing

import pytest

from rediacc_ci.ci import derive_image_tag as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

SLUG = "derive-image-tag"
MODULE = "rediacc_ci.ci.derive_image_tag"

FILES_MARKER = "--- files ---\n"

_PROG = re.compile(r"^\S+: line ", re.MULTILINE)
_HELP_PROG = re.compile(r"\S*derive[-_]image[-_]tag\.(?:sh|py)")

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

# The tools the twin's tag pipeline needed with git taken away. Only GIT's stderr was redirected there, so dropping `head` or `sed` too would put a second, unrelated `command not found` on stderr and record the wrong absence.
NO_GIT_TOOLS = ("bash", "python3", "uname", "dirname", "cat", "sed", "head", "date")

LONG_TAG = "a" * 128
TOO_LONG_TAG = "a" * 129

# name -> (argv, how the run is wired)
CASE_KW: dict[str, tuple[tuple[str, ...], dict[str, typing.Any]]] = {
    "an-explicit-version-wins-over-everything": (
        ("--version", "v9.9.9"),
        {
            "tags": ("v1.0.0",),
            "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v0.0.1"},
        },
    ),
    "an-empty-explicit-version": (("--version", ""), {"tags": ("v3.4.5",)}),
    "a-missing-version-argument": (("--version",), {"in_repo": True}),
    "a-tag-build": (
        (),
        {
            "tags": ("v1.0.0",),
            "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v2.3.4"},
        },
    ),
    "a-tag-build-in-a-v3-repo": (
        (),
        {
            "tags": ("v3.4.5",),
            "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v2.3.4"},
        },
    ),
    "a-branch-build-in-a-v3-repo": (
        (),
        {"tags": ("v3.4.5",), "env_extra": {"GITHUB_REF_TYPE": "branch"}},
    ),
    "a-tag-build-without-a-ref-name": (
        (),
        {"in_repo": True, "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": None}},
    ),
    "a-tag-build-with-an-empty-ref-name": (
        (),
        {"in_repo": True, "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": ""}},
    ),
    "the-highest-version-not-the-highest-string": (
        (),
        {
            "tags": ("v1.9.0", "v1.10.0", "v1.2.0"),
            "env_extra": {"GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"},
        },
    ),
    "a-branch-build-without-a-ref-name": (
        (),
        {"tags": ("v1.0.0",), "env_extra": {"GITHUB_REF_NAME": None}},
    ),
    "non-v-tags-and-then-the-fetch": (
        (),
        {
            "tags": ("release-1", "2.0.0"),
            "env_extra": {"GITHUB_REF_NAME": "topic"},
            "fake_git": True,
        },
    ),
    "the-fetch-is-skipped-when-a-v-tag-exists": (
        (),
        {"tags": ("v5.0.0",), "fake_git": True},
    ),
    "the-placeholder-version": ((), {"tags": ("v0.0.0-dev",)}),
    "outside-a-git-repository": ((), {"bare": True, "fake_git": True}),
    "a-missing-git": ((), {"in_repo": True, "no_git": True}),
    "only-the-first-leading-v-is-stripped": ((), {"tags": ("vv1.0.0",)}),
    "an-invalid-tag-format": (("--version", "a b"), {"in_repo": True}),
    "a-128-character-tag": (("--version", LONG_TAG), {"in_repo": True}),
    "a-129-character-tag": (("--version", TOO_LONG_TAG), {"in_repo": True}),
    "a-non-ascii-tag-of-200-characters": (("--version", "é" * 200), {"in_repo": True}),
    "a-dotted-tag": (("--version", "v1.2.3"), {"in_repo": True}),
    "a-release-candidate-tag": (("--version", "1.2.3-rc.1"), {"in_repo": True}),
    "an-underscored-tag": (("--version", "edge_2026"), {"in_repo": True}),
    "a-leading-hyphen-tag": (("--version", "-leading-hyphen"), {"in_repo": True}),
    "a-leading-dot-tag": (("--version", ".leading-dot"), {"in_repo": True}),
    "github-output-mode": (
        ("--version", "v1", "--github-output"),
        {"in_repo": True, "outputs": True},
    ),
    "env-file-mode": (("--version", "v1", "--env-file"), {"in_repo": True, "outputs": True}),
    "both-output-modes": (
        ("--version", "v1", "--github-output", "--env-file"),
        {"in_repo": True, "outputs": True},
    ),
    "an-unset-output-target": (
        ("--version", "v1", "--github-output", "--env-file"),
        {"in_repo": True, "env_extra": {"GITHUB_OUTPUT": None, "GITHUB_ENV": None}},
    ),
    "an-empty-output-target": (
        ("--version", "v1", "--github-output"),
        {"in_repo": True, "env_extra": {"GITHUB_OUTPUT": ""}},
    ),
    "the-output-files-are-appended": (
        ("--version", "v1", "--env-file"),
        {"in_repo": True, "outputs": True, "seed": "PRE=1\n"},
    ),
    "an-unknown-option": (("--nope",), {"in_repo": True}),
    "a-positional-argument": (("v1.2.3",), {"in_repo": True}),
    "the-last-version-wins": (
        ("--version", "v1", "--version", "v2"),
        {"in_repo": True},
    ),
    "the-short-help": (("-h",), {"in_repo": True}),
    "the-long-help": (("--help",), {"in_repo": True}),
    "help-before-an-unknown-option": (("--help", "--nope"), {"in_repo": True}),
    "an-unknown-option-before-help": (("--nope", "--help"), {"in_repo": True}),
    "colour-on-a-terminal": (("--version", "a b"), {"in_repo": True, "tty": "stderr"}),
    "no-color-on-a-terminal": (
        ("--version", "a b"),
        {"in_repo": True, "tty": "stderr", "env_extra": {"NO_COLOR": "1"}},
    ),
}

CASES = tuple(CASE_KW)

# The help text interpolates `$0` five times and pads four example comments to a fixed width, so the LENGTH of the program name changes the trailing spacing too. These four cases are recorded with the name replaced and whitespace runs collapsed; every option, every description and both auto-derivation lines survive.
HELP_CASES = (
    "the-short-help",
    "the-long-help",
    "help-before-an-unknown-option",
    "an-unknown-option-before-help",
)


def strip_prog(text: str) -> str:
    return _PROG.sub("<prog>: line ", text)


def help_body(stdout: str) -> str:
    return "\n".join(
        re.sub(r"\s+", " ", _HELP_PROG.sub("<prog>", line)).strip() for line in stdout.split("\n")
    )


def assert_is_scratch(repo: pathlib.Path) -> None:
    """Refuse to touch anything that is not the disposable repository.

    Not defensive theatre: every git command below is run with `-C <repo>`, and a `-C` that silently resolved into the real checkout would run `git tag` against work in progress. `--show-toplevel` is the only answer that settles it, and it must NOT be the console tree.
    """
    top = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert top == str(repo.resolve()), "scratch repo resolved to %r" % top
    assert top != diff.repo(), "refusing to operate on the real checkout"


def scratch_repo(where: pathlib.Path, *tags: str) -> pathlib.Path:
    """A one-commit git repository carrying exactly `tags`."""
    repo = where / "scratch"
    repo.mkdir(parents=True, exist_ok=True)
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


def make_fake_git(where: pathlib.Path) -> pathlib.Path:
    bindir = where / "fakebin"
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / "git"
    script.write_text(
        FAKE_GIT_SRC.format(python=sys.executable, git=shutil.which("git")), encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def make_no_git_bin(where: pathlib.Path) -> pathlib.Path:
    bindir = where / "nogit"
    bindir.mkdir(parents=True, exist_ok=True)
    for tool in NO_GIT_TOOLS:
        found = shutil.which(tool)
        if found and not (bindir / tool).exists():
            (bindir / tool).symlink_to(found)
    assert shutil.which("git", path=str(bindir)) is None, "git leaked into the restricted PATH"
    return bindir


def run(
    where: pathlib.Path,
    command: str,
    name: str,
    *,
    tags: tuple[str, ...] = (),
    in_repo: bool = False,
    bare: bool = False,
    env_extra: dict[str, str | None] | None = None,
    fake_git: bool = False,
    no_git: bool = False,
    outputs: bool = False,
    seed: str = "",
    tty: str | None = None,
) -> tuple[int, str, str, dict[str, str | None]]:
    """One side, once, over this case's disposable repository."""
    where.mkdir(parents=True, exist_ok=True)
    args = CASE_KW[name][0]
    quoted = " ".join(shlex.quote(arg) for arg in args)

    if bare:
        workdir = where / "not-a-repo"
        workdir.mkdir(exist_ok=True)
    elif in_repo:
        workdir = None
    else:
        workdir = scratch_repo(where, *tags)

    env: dict[str, str | None] = dict(env_extra or {})
    files: dict[str, pathlib.Path] = {}
    if fake_git:
        env["PATH"] = "%s:%s" % (make_fake_git(where), os.environ.get("PATH", ""))
        log = where / "gitcalls.txt"
        log.write_text("", encoding="utf-8")
        env["FAKE_GIT_LOG"] = str(log)
        files["gitlog"] = log
    if no_git:
        env["PATH"] = str(make_no_git_bin(where))
    if outputs:
        for key in ("GITHUB_OUTPUT", "GITHUB_ENV"):
            path = where / ("%s.txt" % key.lower())
            path.write_text(seed, encoding="utf-8")
            env[key] = str(path)
            files[key.lower()] = path
    if command.startswith("python3"):
        env["PYTHONPATH"] = "%s/.ci" % diff.repo()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

    returncode, stdout, stderr = diff.bash_streams(
        "%s %s" % (command, quoted),
        env=diff.env_for(**env),
        cwd=str(workdir) if workdir is not None else diff.repo(),
        tty=tty,
        timeout=30,
    )
    read = {k: v.read_text(encoding="utf-8") if v.exists() else None for k, v in files.items()}
    return returncode, stdout, stderr, read


def render(returncode: int, stdout: str, stderr: str, files: dict[str, str | None]) -> str:
    body = frozen.render(returncode, stdout, strip_prog(stderr))
    return body + FILES_MARKER + json.dumps(files, sort_keys=True, ensure_ascii=False) + "\n"


def recorded(name: str) -> tuple[int, str, str, dict[str, str | None]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, files = rest.split(FILES_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, json.loads(files)


def drive(tmp_path: pathlib.Path, name: str, *, command: str = "python3 -m %s" % MODULE):
    returncode, stdout, stderr, files = run(tmp_path / "run", command, name, **CASE_KW[name][1])
    return returncode, stdout, strip_prog(stderr), files


def compare(tmp_path: pathlib.Path, name: str) -> None:
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    if name in HELP_CASES:
        assert help_body(got[1]) == help_body(want[1]), "%s: the help text diverged" % name
    else:
        assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: a written file diverged: %r vs %r" % (name, want[3], got[3])


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Explicit --version ---------------------------------------------------------------------------


def test_an_explicit_version_wins_over_everything() -> None:
    returncode, stdout, stderr, _ = recorded("an-explicit-version-wins-over-everything")
    assert returncode == 0
    assert stdout == "v9.9.9\n"
    assert stderr == "✓ Using explicit version: v9.9.9\n"


def test_defect_b_an_empty_explicit_version_is_silently_auto_derived() -> None:
    """`${2?...}` refused ABSENT, not EMPTY, and the decision was `[[ -n "$VERSION" ]]`.

    A blank `workflow_dispatch` input therefore produces a tag nobody asked for rather than a refusal, and the only sign of it is on stderr.
    """
    returncode, stdout, stderr, _ = recorded("an-empty-explicit-version")
    assert returncode == 0, "the twin's DEFECT B changed; re-read the module docstring"
    assert stdout == "3.4.5\n"
    assert "Auto-derived from git tags (local): 3.4.5" in stderr
    assert "explicit" not in stderr


def test_a_missing_version_argument_is_bashs_diagnostic_at_line_34() -> None:
    """bash named the POSITIONAL PARAMETER `2`, not the option. Verbatim."""
    returncode, stdout, stderr, _ = recorded("a-missing-version-argument")
    assert returncode == 1
    assert stderr == "<prog>: line 34: 2: --version requires an argument\n"
    assert stdout == ""
    assert port.VERSION_ARG_LINE == 34, "the port's copy of the twin's line number drifted"


# --------------------------------------------------------------------------- Tag builds ---------------------------------------------------------------------------


def test_a_tag_build_uses_the_ref_name() -> None:
    _, stdout, stderr, _ = recorded("a-tag-build")
    assert stdout == "v2.3.4\n"
    assert stderr == "✓ Auto-derived from tag: v2.3.4\n"


def test_a_tag_build_keeps_the_leading_v_where_the_branch_arm_strips_it() -> None:
    """The asymmetry is real: `v2.3.4` from a tag build, `3.4.5` from git tags, in the SAME repository."""
    assert recorded("a-tag-build-in-a-v3-repo")[1] == "v2.3.4\n"
    assert recorded("a-branch-build-in-a-v3-repo")[1] == "3.4.5\n"


def test_a_tag_build_without_a_ref_name_is_refused_at_line_81() -> None:
    returncode, _, stderr, _ = recorded("a-tag-build-without-a-ref-name")
    assert returncode == 1
    assert stderr == (
        "<prog>: line 81: GITHUB_REF_NAME: GITHUB_REF_NAME is not set for a tag build\n"
    )
    assert port.REF_NAME_LINE == 81, "the port's copy of the twin's line number drifted"


def test_a_tag_build_with_an_empty_ref_name_reaches_the_format_check() -> None:
    """`${VAR?...}` accepted an empty value, so the refusal came later and elsewhere."""
    returncode, _, stderr, _ = recorded("a-tag-build-with-an-empty-ref-name")
    assert returncode == 1
    assert stderr == (
        "✓ Auto-derived from tag: \n"
        "✗ Invalid tag format: \n"
        "✗ Tags must contain only alphanumeric characters, dots, hyphens, and underscores\n"
    )


# --------------------------------------------------------------------------- Branch builds: the git-tag ladder ---------------------------------------------------------------------------


def test_the_branch_arm_picks_the_highest_version_not_the_highest_string() -> None:
    """`--sort=-v:refname` puts v1.10.0 above v1.9.0. A lexicographic sort does not.

    This is the one case a hand-rolled Python sort would get wrong, and it is why the port shells out to git instead of reimplementing the ordering.
    """
    _, stdout, stderr, _ = recorded("the-highest-version-not-the-highest-string")
    assert stdout == "1.10.0\n"
    assert "Auto-derived from git tags (main): 1.10.0" in stderr


def test_a_branch_build_without_a_ref_name_says_local() -> None:
    assert (
        "Auto-derived from git tags (local): 1.0.0"
        in recorded("a-branch-build-without-a-ref-name")[2]
    )
    assert port.LOCAL_BRANCH == "local"


def test_non_v_tags_are_invisible_and_the_fetch_arm_then_fires() -> None:
    """No `v*` tag meant the shallow-clone fetch, and then the `latest` fallback.

    The fake git recorded the fetch rather than performing it, and the recorded call log is what the port's own log is compared against -- which is what proves it sends the same four flags in the same order.
    """
    returncode, stdout, stderr, files = recorded("non-v-tags-and-then-the-fetch")
    assert returncode == 0
    assert stdout == "latest\n"
    assert "Auto-derived from git tags (topic): latest" in stderr
    assert files["gitlog"] == (
        "FAKEGIT| tag -l v*\n"
        "FAKEGIT| fetch --tags --force --no-recurse-submodules origin\n"
        "FAKEGIT| tag -l v* --sort=-v:refname\n"
    )


def test_the_fetch_is_skipped_when_a_v_tag_is_already_present() -> None:
    """The negative control for the case above: two git calls, no fetch."""
    _, stdout, _, files = recorded("the-fetch-is-skipped-when-a-v-tag-exists")
    assert stdout == "5.0.0\n"
    assert "fetch" not in files["gitlog"]
    assert files["gitlog"].count("FAKEGIT|") == 2


def test_the_placeholder_version_falls_back_to_latest() -> None:
    """Every package.json here carries `0.0.0-dev`; the twin refused to ship it."""
    assert recorded("the-placeholder-version")[1] == "latest\n"
    assert port.PLACEHOLDER_VERSION == "0.0.0-dev"


def test_outside_a_git_repository_the_answer_is_latest() -> None:
    """`git tag` failing was swallowed twice over, so this could not raise."""
    returncode, stdout, _, _ = recorded("outside-a-git-repository")
    assert returncode == 0
    assert stdout == "latest\n"


def test_a_missing_git_derives_latest_and_exits_zero() -> None:
    """The missing-tool arm, and it is GREEN. Recorded in both directions.

    All three git calls had their stderr on `/dev/null` and their status either tested or `|| true`d, so a machine without git printed nothing about it and shipped an image tagged `latest`. The port raised `FileNotFoundError` here until `git_stdout` existed, which is the divergence this case keeps out.
    """
    returncode, stdout, stderr, _ = recorded("a-missing-git")
    assert returncode == 0, "the twin's missing-git arm changed; re-read the docstring"
    assert stdout == "latest\n"
    assert "✓ Auto-derived from git tags (local): latest\n" in stderr
    assert "command not found" not in stderr, "the twin said nothing about the missing tool"


def test_only_the_first_leading_v_is_stripped() -> None:
    """`sed 's/^v//'` was one substitution at the start, not a strip of all v's."""
    assert recorded("only-the-first-leading-v-is-stripped")[1] == "v1.0.0\n"


# --------------------------------------------------------------------------- Validation ---------------------------------------------------------------------------


def test_an_invalid_tag_format_is_two_error_lines_and_exit_1() -> None:
    returncode, stdout, stderr, _ = recorded("an-invalid-tag-format")
    assert returncode == 1
    assert stderr == (
        "✓ Using explicit version: a b\n"
        "✗ Invalid tag format: a b\n"
        "✗ Tags must contain only alphanumeric characters, dots, hyphens, and underscores\n"
    )
    assert stdout == "", "nothing reaches stdout when validation fails"


def test_the_boundary_of_the_length_check_is_128() -> None:
    """128 passes, 129 fails. An off-by-one here would be invisible otherwise."""
    returncode, stdout, _, _ = recorded("a-128-character-tag")
    assert returncode == 0
    assert stdout == LONG_TAG + "\n"
    returncode, _, stderr, _ = recorded("a-129-character-tag")
    assert returncode == 1
    assert "✗ Tag too long: 129 characters (max 128)\n" in stderr
    assert port.MAX_TAG_LENGTH == 128


def test_the_format_check_runs_before_the_length_check() -> None:
    """The ORDER is what makes bytes-vs-characters unable to diverge.

    A 200-character non-ASCII tag is rejected for its FORMAT, never reaching the length comparison where bash counted bytes under LC_ALL=C and Python counts characters. Reorder the two checks and the two implementations start disagreeing on exactly this input.
    """
    returncode, _, stderr, _ = recorded("a-non-ascii-tag-of-200-characters")
    assert returncode == 1
    assert "Invalid tag format" in stderr
    assert "Tag too long" not in stderr


def test_dots_hyphens_and_underscores_are_all_accepted() -> None:
    for name, tag in (
        ("a-dotted-tag", "v1.2.3"),
        ("a-release-candidate-tag", "1.2.3-rc.1"),
        ("an-underscored-tag", "edge_2026"),
        ("a-leading-hyphen-tag", "-leading-hyphen"),
        ("a-leading-dot-tag", ".leading-dot"),
    ):
        returncode, stdout, _, _ = recorded(name)
        assert returncode == 0, name
        assert stdout == tag + "\n", name


# --------------------------------------------------------------------------- Output modes ---------------------------------------------------------------------------


def test_github_output_mode_appends_one_line() -> None:
    returncode, stdout, stderr, files = recorded("github-output-mode")
    assert returncode == 0
    assert files["github_output"] == "tag=v1\n"
    assert files["github_env"] == "", "--github-output must not touch GITHUB_ENV"
    assert "✓ Set GITHUB_OUTPUT: tag=v1\n" in stderr
    assert stdout == "v1\n"


def test_env_file_mode_appends_three_lines_in_order() -> None:
    _, stdout, stderr, files = recorded("env-file-mode")
    assert files["github_env"] == "TAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"
    assert files["github_output"] == ""
    assert "✓ Set GITHUB_ENV: TAG=v1, WEB_TAG=v1, RENET_TAG=v1\n" in stderr
    assert port.ENV_FILE_NAMES == ("TAG", "WEB_TAG", "RENET_TAG")
    assert stdout == "v1\n", "the tag is on stdout and every log line on stderr"
    assert "✓" not in stdout


def test_both_output_modes_together() -> None:
    files = recorded("both-output-modes")[3]
    assert files["github_output"] == "tag=v1\n"
    assert files["github_env"] == "TAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"


def test_an_unset_output_target_is_a_warning_and_still_exit_0() -> None:
    """A skipped export was NOT an error here, and the tag still reached stdout."""
    returncode, stdout, stderr, _ = recorded("an-unset-output-target")
    assert returncode == 0
    assert stdout == "v1\n"
    assert "⚠ GITHUB_OUTPUT not set, skipping --github-output\n" in stderr
    assert "⚠ GITHUB_ENV not set, skipping --env-file\n" in stderr


def test_an_empty_output_target_counts_as_unset() -> None:
    """`[[ -n "${GITHUB_OUTPUT:-}" ]]` is emptiness, not presence."""
    assert (
        "⚠ GITHUB_OUTPUT not set, skipping --github-output\n"
        in recorded("an-empty-output-target")[2]
    )


def test_the_output_files_are_appended_to_not_truncated() -> None:
    """`>>`, not `>`. A step that overwrote GITHUB_ENV would erase earlier steps."""
    files = recorded("the-output-files-are-appended")[3]
    assert files["github_env"] == "PRE=1\nTAG=v1\nWEB_TAG=v1\nRENET_TAG=v1\n"


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_an_unknown_option_is_refused() -> None:
    returncode, _, stderr, _ = recorded("an-unknown-option")
    assert returncode == 1
    assert stderr == "✗ Unknown option: --nope\n"


def test_a_positional_argument_is_refused_too() -> None:
    """The `*)` arm was not a flag test. This script takes no positionals at all."""
    returncode, _, stderr, _ = recorded("a-positional-argument")
    assert returncode == 1
    assert stderr == "✗ Unknown option: v1.2.3\n"


def test_the_last_version_wins_when_it_is_repeated() -> None:
    assert recorded("the-last-version-wins")[1] == "v2\n"


def test_both_help_spellings_exit_0_with_the_same_text() -> None:
    short, long = recorded("the-short-help"), recorded("the-long-help")
    assert short[0] == long[0] == 0
    assert short[2] == long[2] == ""
    assert help_body(short[1]) == help_body(long[1])


def test_help_wins_over_a_later_unknown_option() -> None:
    """The loop exited at `-h`; the `*)` arm was never reached. Order matters."""
    returncode, stdout, stderr, _ = recorded("help-before-an-unknown-option")
    assert returncode == 0
    assert stderr == ""
    assert help_body(stdout) == help_body(recorded("the-long-help")[1])


def test_an_unknown_option_before_help_wins_instead() -> None:
    returncode, _, stderr, _ = recorded("an-unknown-option-before-help")
    assert returncode == 1
    assert stderr == "✗ Unknown option: --nope\n"


def test_the_help_text_is_the_twins_help_text_verbatim() -> None:
    """The port's HELP_LINES are a COPY, and the recorded help output keeps the copy honest.

    Includes DEFECT A: the line claiming the branch arm "uses version from package.json" is wrong -- nothing in either file ever read package.json -- and it is carried anyway, because the recording is of bytes the twin printed. Removing it from the port without a new recording is what this catches.
    """
    recorded_help = help_body(recorded("the-long-help")[1]).split("\n")
    for line in port.HELP_LINES:
        rendered = re.sub(r"\s+", " ", line.format(prog="<prog>")).strip()
        assert rendered in recorded_help, "help line not in the recording: %r" % rendered
    assert any("package.json" in line for line in recorded_help), (
        "the docstring's DEFECT A is stale: the twin no longer mentions package.json"
    )


# --------------------------------------------------------------------------- Colour ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical() -> None:
    returncode, _, stderr, _ = recorded("colour-on-a-terminal")
    assert returncode == 1
    assert diff.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"


def test_no_color_suppresses_colour_on_a_terminal() -> None:
    assert diff.escape_bytes(recorded("no-color-on-a-terminal")[2]) == 0


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_lexicographic_sort_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Swap `--sort=-v:refname` for `--sort=-refname`.

    git then lists tags in reverse LEXICOGRAPHIC order, which puts `v1.9.0` above `v1.10.0`, and the image is built and published under the tag of an OLDER release. The recorded answer for `the-highest-version-not-the-highest-string` is `1.10.0`; a mutant that sorts as text answers `1.9.0` with the same exit code and the same log wording, so only the derived tag itself
    says anything. The mutation runs from a throwaway copy of the package's module file; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = '"tag", "-l", "v*", "--sort=-v:refname"'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, '"tag", "-l", "v*", "--sort=-refname"')

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "derive_image_tag.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-highest-version-not-the-highest-string"
    _, stdout, _, _ = run(tmp_path / "planted", "python3 %s" % mutant, name, **CASE_KW[name][1])
    want = recorded(name)[1]
    assert want == "1.10.0\n", "the recorded answer moved"
    assert stdout == "1.9.0\n", "the plant did not change the derived tag: %r" % stdout

    compare(tmp_path / "good", name)
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original
