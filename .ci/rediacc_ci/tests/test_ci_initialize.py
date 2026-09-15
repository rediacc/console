"""`rediacc_ci.ci.initialize` against its bash twin.

NOTHING HERE TOUCHES THE REAL TREE, THE REAL GIT, THE REAL REGISTRY OR THE
NETWORK, and that is not a nicety: the twin writes a token rewrite into the
GLOBAL git config, initialises submodules, fetches from an authenticated remote
and asks GHCR about three images. Every one of those is faked, and the fakes
RECORD their argv so the two sides are compared on what they asked for as well
as on what they printed.

HOW BOTH SIDES ARE POINTED AT A FIXTURE. `get_repo_root` (common.sh:205) resolves
three directories up from the common.sh THAT WAS SOURCED, so a fixture carrying
its own `.ci/scripts/lib/common.sh`, reached through
`<fixture>/.ci/scripts/ci/initialize.sh`, sends the twin into the fixture. The
port resolves through `paths.repo_root()`, which honours `$REDIACC_CI_ROOT`. The
twin itself is a SYMLINK to the real file -- bash does not resolve symlinks in
`${BASH_SOURCE[0]}` -- so the script under test is the real, unmodified one and a
change to it cannot slip past this file.

EACH SIDE GETS ITS OWN FIXTURE, `old-root` and `new-root`, because both write
into it (an `--output` file, the `./true` of DEFECT C, the submodule sentinel a
fake creates). Every comparison replaces the side's own root, HOME and call log
with `<root>`, so the two are compared on everything except the one string that
must differ.

THE PATH IS A CLOSED LIST. `<root>/bin` holds the fakes; `<tmp>/minbin` holds
symlinks to the real coreutils the twin needs by name, and NOTHING ELSE. That is
what makes the "docker is not installed" arm testable on a host that has docker:
the arm is the default here, and the one case that needs docker adds the fake
explicitly.

WHAT IS NORMALISED. Two of the twin's exits are bash's own diagnostics, which
begin `<program>: line <N>:`. The program NAME necessarily differs between a
`.sh` and a module, so `strip_prog` replaces that one token; the LINE NUMBERS are
compared, because a drifting line number is exactly the silent failure the pins
exist to catch.

The K=5 ledger is `.ci/shadow/w7p6-initialize.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-initialize --assert --k 5`).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
from typing import TYPE_CHECKING

from rediacc_ci.ci import initialize as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/initialize.sh"
MODULE = "rediacc_ci.ci.initialize"

_PROG = re.compile(r"^\S+: line ", re.MULTILINE)

# Everything the twin, common.sh and the fakes reach for BY NAME. `git` and
# `docker` are deliberately absent: those are the fakes' names.
MIN_TOOLS = (
    "python3",
    "bash",
    "dirname",
    "basename",
    "tr",
    "sed",
    "head",
    "grep",
    "cat",
    "rm",
    "mkdir",
    "mktemp",
    "sleep",
    "touch",
    "printf",
    "env",
    "uname",
    "date",
    "wc",
)

FAKE_GIT = """#!/bin/bash
# SIGPIPE IGNORED, BELT AND BRACES. The twin no longer pipes `git tag` into
# `head -1`, which is what used to kill this fake mid-write and surface as the
# SCRIPT exiting 141 -- three cases in CI run 34970782616. Ignoring PIPE here
# means a future caller that reintroduces a short-reading pipe gets a real
# verdict from this fixture instead of a racy 141 that looks like a code
# failure, and it costs nothing: every write below is tiny.
trap '' PIPE
printf 'git %s\\n' "$*" >>"$FAKE_LOG"
case "${1:-}" in
    config) exit "${FAKE_GIT_CONFIG_EXIT:-0}" ;;
    submodule)
        if [[ -n "${FAKE_GIT_SUBMODULE_FAIL:-}" ]]; then
            echo "fake git: submodule update refused" >&2
            exit 1
        fi
        if [[ -n "${FAKE_GIT_SUBMODULE_CREATES:-}" ]]; then
            mkdir -p private/renet/.ci && touch private/renet/.ci/ci.sh
        fi
        exit 0
        ;;
    fetch)
        if [[ -n "${FAKE_GIT_FETCH_FAIL:-}" ]]; then
            echo "fatal: unable to access '${@: -1}'" >&2
            exit 128
        fi
        exit 0
        ;;
    tag)
        if [[ -n "${FAKE_GIT_TAGS:-}" ]]; then
            printf '%s\\n' ${FAKE_GIT_TAGS}
        fi
        exit "${FAKE_GIT_TAG_EXIT:-0}"
        ;;
    *)
        echo "fake git: unhandled subcommand ${1:-}" >&2
        exit 3
        ;;
esac
"""

FAKE_DOCKER = """#!/bin/bash
printf 'docker %s\\n' "$*" >>"$FAKE_LOG"
case " ${FAKE_DOCKER_HAVE:-} " in
    *" ${3:-} "*) exit 0 ;;
esac
exit 1
"""

# One template per sibling. Each records its argv, then behaves as its env says.
FAKE_SIBLINGS = {
    ".ci/scripts/ci/detect-pointer-bump.sh": """#!/bin/bash
printf 'detect-pointer-bump.sh %s\\n' "$*" >>"$FAKE_LOG"
echo "pointer_bump_only=${FAKE_POINTER_BUMP:-false}"
exit "${FAKE_POINTER_BUMP_EXIT:-0}"
""",
    ".ci/scripts/ci/generate-tag.sh": """#!/bin/bash
printf 'generate-tag.sh %s\\n' "$*" >>"$FAKE_LOG"
if [[ -n "${FAKE_GENERATE_TAG_EXIT:-}" ]]; then
    echo "fake generate-tag: refusing" >&2
    exit "${FAKE_GENERATE_TAG_EXIT}"
fi
case "$*" in
    *"--submodule private/renet"*) echo "renet-aaaa" ;;
    *"--closure web"*) echo "web-bbbb" ;;
    *"--closure rdc"*) echo "rdc-cccc" ;;
esac
""",
    # The ONLY sibling whose environment the twin alters, so the value it
    # actually receives is logged: `GITHUB_OUTPUT=''` must arrive as the EMPTY
    # STRING, and `[UNSET]` here would mean the port dropped the assignment. The
    # same fact printed to stderr would prove nothing, because the twin's
    # `2>&1 | grep` swallows it -- which is what the stderr line below checks.
    ".ci/scripts/ci/dispatch-release.sh": """#!/bin/bash
printf 'dispatch-release.sh GITHUB_OUTPUT=[%s] %s\\n' "${GITHUB_OUTPUT-UNSET}" "$*" >>"$FAKE_LOG"
echo "GITHUB_OUTPUT=[${GITHUB_OUTPUT-UNSET}]" >&2
if [[ -n "${FAKE_DECISION:-}" ]]; then
    echo "decision: ${FAKE_DECISION}"
fi
""",
    ".ci/scripts/version/detect-bump-type.sh": """#!/bin/bash
printf 'detect-bump-type.sh %s\\n' "$*" >>"$FAKE_LOG"
echo "fake detect-bump-type: verbose noise" >&2
echo "${FAKE_BUMP_TYPE:-patch}"
""",
    ".ci/scripts/version/resolve-version.sh": """#!/bin/bash
printf 'resolve-version.sh %s\\n' "$*" >>"$FAKE_LOG"
case "$*" in
    *--current*) echo "1.2.3" ;;
    *) echo "1.2.4" ;;
esac
""",
}


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


def executable(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def minbin(tmp_path: pathlib.Path) -> pathlib.Path:
    """A PATH holding exactly MIN_TOOLS, so `command -v docker` can say no."""
    bindir = assert_scratch(tmp_path / "minbin")
    bindir.mkdir(exist_ok=True)
    for tool in MIN_TOOLS:
        real = shutil.which(tool)
        assert real is not None, "the host has no %s, which every case needs" % tool
        link = bindir / tool
        if not link.exists():
            link.symlink_to(real)
    return bindir


def fixture_root(
    tmp_path: pathlib.Path,
    side: str,
    *,
    sentinel: bool = True,
    docker: bool = False,
    missing_siblings: tuple[str, ...] = (),
) -> pathlib.Path:
    """One side's disposable repository-shaped tree."""
    root = assert_scratch(tmp_path / ("%s-root" % side))
    (root / ".ci/scripts/lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci/scripts/ci").mkdir(parents=True, exist_ok=True)
    (root / ".ci/scripts/version").mkdir(parents=True, exist_ok=True)
    (root / "bin").mkdir(exist_ok=True)
    (root / "home").mkdir(exist_ok=True)

    shutil.copyfile(
        "%s/.ci/scripts/lib/common.sh" % diff.repo(), root / ".ci/scripts/lib/common.sh"
    )
    twin = root / TWIN
    if not twin.exists():
        twin.symlink_to("%s/%s" % (diff.repo(), TWIN))

    for relative, body in FAKE_SIBLINGS.items():
        if relative in missing_siblings:
            continue
        executable(root / relative, body)

    executable(root / "bin/git", FAKE_GIT)
    if docker:
        executable(root / "bin/docker", FAKE_DOCKER)

    if sentinel:
        (root / "private/renet/.ci").mkdir(parents=True, exist_ok=True)
        (root / "private/renet/.ci/ci.sh").write_text("", encoding="utf-8")
    return root


def run_both(
    tmp_path: pathlib.Path,
    *args: str,
    env_extra: dict[str, str | None] | None = None,
    output: str | None = None,
    tty: str | None = None,
    timeout: float = 60,
    **fixture_kwargs: object,
) -> tuple[tuple[int, str, str], tuple[int, str, str], dict[str, str | None]]:
    """Build one fixture per side, run both, and normalise the roots away.

    `output` is a path RELATIVE to the fixture root (so both sides name the same
    thing), or None for no `--output` at all.
    """
    tools = minbin(tmp_path)
    results: dict[str, tuple[int, str, str]] = {}
    files: dict[str, str | None] = {}

    for side in ("old", "new"):
        root = fixture_root(tmp_path, side, **fixture_kwargs)  # type: ignore[arg-type]
        call_log = root / "calls.log"
        call_log.write_text("", encoding="utf-8")
        argv = list(args) + (["--output", output] if output is not None else [])
        quoted = " ".join(shlex.quote(a) for a in argv)

        env: dict[str, str | None] = {
            "PATH": "%s:%s" % (root / "bin", tools),
            "HOME": str(root / "home"),
            "FAKE_LOG": str(call_log),
            **(env_extra or {}),
        }
        if side == "old":
            command = "bash %s %s" % (root / TWIN, quoted)
        else:
            env["PYTHONPATH"] = "%s/.ci" % diff.repo()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["REDIACC_CI_ROOT"] = str(root)
            command = "python3 -m %s %s" % (MODULE, quoted)

        result = diff.bash_streams(
            command, env=diff.env_for(**env), cwd=str(root), tty=tty, timeout=timeout
        )

        def scrub(text: str, root: pathlib.Path = root) -> str:
            return text.replace(str(root), "<root>")

        results[side] = (result[0], scrub(result[1]), scrub(result[2]))
        files["%s_calls" % side] = scrub(call_log.read_text(encoding="utf-8"))
        for name in ("output", "true"):
            target = root / (output if name == "output" and output else name)
            files["%s_%s" % (side, name)] = (
                scrub(target.read_text(encoding="utf-8")) if target.is_file() else None
            )
    return results["old"], results["new"], files


def assert_identical(old, new, files) -> None:
    assert new[0] == old[0], "exit code: %r vs %r" % (old, new)
    assert new[1] == old[1], "stdout:\n%s\n---\n%s" % (old[1], new[1])
    assert strip_prog(new[2]) == strip_prog(old[2]), "stderr:\n%s\n---\n%s" % (old[2], new[2])
    for key, value in files.items():
        if key.startswith("old_"):
            assert files["new_" + key[4:]] == value, "%s diverged:\n%r\n---\n%r" % (
                key[4:],
                value,
                files["new_" + key[4:]],
            )


PAT_ENV = {"GITHUB_PAT": "s3cr3t-app-token", "GITHUB_REPOSITORY": "rediacc/console"}


# ---------------------------------------------------------------------------
# Step 1 and step 2: the arms that never reach a sibling
# ---------------------------------------------------------------------------


def test_a_missing_token_is_four_lines_and_exit_one(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, env_extra={"GITHUB_PAT": None})
    assert old[0] == 1
    assert old[1] == ""
    assert old[2] == (
        "→ Validating required secrets...\n"
        "✗ ERROR: GITHUB_PAT is required but not set\n"
        "✗ This repository requires private submodule access.\n"
        "✗ Configure the GH_PAT secret in: Settings > Secrets and variables > Actions\n"
        "✗ Required scopes: repo, write:packages\n"
    )
    assert files["old_calls"] == "", "nothing may be executed before the token is checked"
    assert_identical(old, new, files)


def test_an_empty_token_is_refused_exactly_like_an_absent_one(
    tmp_path: pathlib.Path,
) -> None:
    """`[[ -z "${GITHUB_PAT:-}" ]]` does not distinguish the two."""
    old, new, files = run_both(tmp_path, env_extra={"GITHUB_PAT": ""})
    assert old[0] == 1
    assert "ERROR: GITHUB_PAT is required but not set" in old[2]
    assert_identical(old, new, files)


def test_check_only_stops_after_two_outputs(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--check-only", env_extra=dict(PAT_ENV))
    assert old[0] == 0
    assert old[1] == "is_bot=false\npointer_bump_only=false\n"
    assert old[2].endswith("✓ Check-only mode, skipping submodule and tag generation\n")
    assert files["old_calls"] == ""
    assert_identical(old, new, files)


def test_a_bot_push_stops_before_the_submodules(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "push",
            "COMMIT_AUTHOR": "github-actions[bot]",
        },
    )
    assert old[0] == 0
    assert old[1] == "is_bot=true\npointer_bump_only=false\n"
    assert "✓ Commit from bot: github-actions[bot] - downstream jobs will be skipped" in old[2]
    assert files["old_calls"] == ""
    assert_identical(old, new, files)


def test_dependabot_is_the_other_bot(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "push", "COMMIT_AUTHOR": "dependabot[bot]"},
    )
    assert old[1].startswith("is_bot=true\n")
    assert_identical(old, new, files)
    assert port.BOT_AUTHORS == ("github-actions[bot]", "dependabot[bot]")


def test_a_human_push_is_not_a_bot(tmp_path: pathlib.Path) -> None:
    """The negative control. Without it the bot arm would pass by flagging everyone."""
    old, new, files = run_both(
        tmp_path,
        "--check-only",
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "push", "COMMIT_AUTHOR": "a-human"},
    )
    assert old[1].startswith("is_bot=false\n")
    assert "✓ Commit author: a-human" in old[2]
    assert_identical(old, new, files)


def test_a_bot_author_on_a_pull_request_is_not_a_bot(tmp_path: pathlib.Path) -> None:
    """`$EVENT_NAME == push` guards the whole test, so only pushes can be skipped."""
    old, new, files = run_both(
        tmp_path,
        "--check-only",
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "COMMIT_AUTHOR": "github-actions[bot]",
        },
    )
    assert old[1].startswith("is_bot=false\n")
    assert "✓ Non-push event or no author info, running CI normally" in old[2]
    assert_identical(old, new, files)


def test_is_bot_commit_is_pure_and_covers_its_three_arms() -> None:
    assert port.is_bot_commit("push", "dependabot[bot]")[0] == "true"
    assert port.is_bot_commit("push", "someone")[0] == "false"
    assert port.is_bot_commit("push", "someone")[1] == "Commit author: someone"
    assert port.is_bot_commit("pull_request", "dependabot[bot]")[0] == "false"
    assert port.is_bot_commit("push", "")[1].startswith("Non-push event")


# ---------------------------------------------------------------------------
# write_output, and DEFECT C
# ---------------------------------------------------------------------------


def test_the_output_file_gets_every_key_stdout_gets(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, "--check-only", output="outputs.txt", env_extra=dict(PAT_ENV)
    )
    assert old[0] == 0
    assert files["old_output"] == "is_bot=false\npointer_bump_only=false\n"
    assert files["old_output"] == old[1]
    assert_identical(old, new, files)


def test_defect_c_output_with_no_value_writes_a_file_called_true(
    tmp_path: pathlib.Path,
) -> None:
    """`parse_args` turns a valueless flag into the STRING `true`, and nothing checks it."""
    old, new, files = run_both(tmp_path, "--check-only", "--output", env_extra=dict(PAT_ENV))
    assert old[0] == 0, "the twin's DEFECT C changed; re-read the module docstring"
    assert files["old_true"] == "is_bot=false\npointer_bump_only=false\n", (
        "the outputs must land in a file literally called `true`"
    )
    assert_identical(old, new, files)
    assert port.EMPTY_OUTPUT_FLAG_WRITES_TRUE == "true"


def test_an_unwritable_output_file_dies_before_the_key_reaches_stdout(
    tmp_path: pathlib.Path,
) -> None:
    """The file write comes FIRST in write_output, so the key is lost from both."""
    old, new, files = run_both(
        tmp_path, "--check-only", output="no-such-dir/outputs.txt", env_extra=dict(PAT_ENV)
    )
    assert old[0] == 1
    assert old[1] == "", "not one key may reach stdout when the file cannot be opened"
    assert strip_prog(old[2]).endswith(
        "<prog>: line 43: no-such-dir/outputs.txt: No such file or directory\n"
    )
    assert_identical(old, new, files)
    assert port.WRITE_OUTPUT_LINE == 43


def test_an_argument_that_is_not_a_shell_identifier_is_printfs_own_refusal(
    tmp_path: pathlib.Path,
) -> None:
    """`printf -v ARG_A.B` fails with status 2, and `set -e` takes the script.

    The PREFIX differs by construction (bash names the sourced common.sh, the
    port has no such file), so the prefix is normalised away and the twin's line
    number is asserted separately -- that is the half that can drift.
    """
    old, new, files = run_both(tmp_path, "--a.b=1", env_extra=dict(PAT_ENV))
    assert old[0] == 2
    assert old[2].endswith("line 333: printf: `ARG_A.B': not a valid identifier\n")
    assert new[0] == 2
    assert new[2] == "printf: `ARG_A.B': not a valid identifier\n"
    assert files["old_calls"] == ""
    assert files["new_calls"] == ""


# ---------------------------------------------------------------------------
# The full run
# ---------------------------------------------------------------------------

PUSH_MAIN = {
    **PAT_ENV,
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": "refs/heads/main",
    "COMMIT_AUTHOR": "a-human",
    "FAKE_GIT_TAGS": "v1.2.3 v1.0.0",
}


def test_the_whole_push_to_main_run_agrees_line_for_line(tmp_path: pathlib.Path) -> None:
    """Every step, every sibling, every output, and the call log as well."""
    old, new, files = run_both(
        tmp_path,
        output="outputs.txt",
        env_extra={**PUSH_MAIN, "FAKE_DECISION": "release", "FAKE_DOCKER_HAVE": ""},
        docker=True,
    )
    assert old[0] == 0
    assert old[1].split("\n") == [
        "is_bot=false",
        "pointer_bump_only=false",
        "pointer_bump_only=false",
        "renet_tag=renet-aaaa",
        "web_tag=web-bbbb",
        "rdc_tag=rdc-cccc",
        "image_tag=renet-aaaa",
        "bump_type=patch",
        "next_version=1.2.4",
        "renet_tag=renet-aaaa-1.2.4",
        "web_tag=web-bbbb-1.2.4",
        "rdc_tag=rdc-cccc-1.2.4",
        "image_tag=renet-aaaa-1.2.4",
        "renet_exists=false",
        "web_exists=false",
        "rdc_exists=false",
        "",
    ]
    assert files["old_calls"] == (
        "git config --global "
        "url.https://x-access-token:s3cr3t-app-token@github.com/.insteadOf https://github.com/\n"
        "detect-pointer-bump.sh --output outputs.txt\n"
        "generate-tag.sh --submodule private/renet\n"
        "generate-tag.sh --closure web --extra renet-aaaa\n"
        "generate-tag.sh --closure rdc --extra renet-aaaa\n"
        "detect-bump-type.sh --verbose\n"
        "dispatch-release.sh GITHUB_OUTPUT=[] --decide-only\n"
        "git fetch --tags --force --no-recurse-submodules "
        "https://x-access-token:s3cr3t-app-token@github.com/rediacc/console.git\n"
        "git tag -l v* --sort=-v:refname\n"
        "resolve-version.sh --bump-type patch\n"
        "resolve-version.sh --current\n"
        "docker manifest inspect ghcr.io/rediacc/renet:renet-aaaa-1.2.4\n"
        "docker manifest inspect ghcr.io/rediacc/server:web-bbbb-1.2.4\n"
        "docker manifest inspect ghcr.io/rediacc/rdc:rdc-cccc-1.2.4\n"
    )
    assert_identical(old, new, files)


def test_defect_b_the_versioned_tag_line_joins_with_a_bare_comma(
    tmp_path: pathlib.Path,
) -> None:
    """`IFS=', '` with `${array[*]}` uses only the FIRST character."""
    old, new, files = run_both(tmp_path, env_extra=PUSH_MAIN, docker=True)
    assert (
        "✓ Push event: versioned tags - "
        "RENET: renet-aaaa-1.2.4,WEB: web-bbbb-1.2.4,RDC: rdc-cccc-1.2.4\n"
    ) in old[2], "the twin's DEFECT B changed; re-read the module docstring"
    assert ", WEB" not in old[2]
    assert_identical(old, new, files)
    assert port.LOG_PARTS_SEPARATOR == ","


def test_a_pull_request_run_skips_the_release_decision_and_the_versioning(
    tmp_path: pathlib.Path,
) -> None:
    """The negative control for both push-only blocks, in one run."""
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "pull_request", "FAKE_GIT_TAGS": "v1.2.3"},
        docker=True,
    )
    assert old[0] == 0
    assert "dispatch-release.sh" not in files["old_calls"]
    assert "Push event: versioned tags" not in old[2]
    assert old[1].endswith("renet_exists=false\nweb_exists=false\nrdc_exists=false\n")
    assert "image_tag=renet-aaaa\n" in old[1]
    assert "-1.2.4" not in old[1], "only a push event versions the tags"
    assert_identical(old, new, files)


def test_an_existing_image_reports_true(tmp_path: pathlib.Path) -> None:
    """The other half of step 7: `docker manifest inspect` succeeding."""
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.2.3",
            "FAKE_DOCKER_HAVE": "ghcr.io/rediacc/server:web-bbbb",
        },
        docker=True,
    )
    assert "web_exists=true" in old[1]
    assert "renet_exists=false" in old[1]
    assert "✓ web:web-bbbb exists=true" in old[2]
    assert_identical(old, new, files)


def test_defect_d_a_missing_docker_reports_the_images_as_absent(
    tmp_path: pathlib.Path,
) -> None:
    """ "Could not ask" and "not there" produce the same three lines."""
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "pull_request", "FAKE_GIT_TAGS": "v1.2.3"},
        docker=False,
    )
    assert old[0] == 0
    assert "renet_exists=false\nweb_exists=false\nrdc_exists=false\n" in old[1]
    assert "docker" not in files["old_calls"]
    assert "docker" not in old[2], "nothing says the probe could not be made"
    assert_identical(old, new, files)


# ---------------------------------------------------------------------------
# Step 3 and step 4
# ---------------------------------------------------------------------------


def test_check_only_never_reaches_the_submodule_step(tmp_path: pathlib.Path) -> None:
    """The negative control for step 3: the early exit is above it."""
    old, new, files = run_both(tmp_path, "--check-only", env_extra=dict(PAT_ENV))
    assert "Submodules" not in old[2]
    assert_identical(old, new, files)


def test_submodule_init_runs_when_the_sentinel_is_missing(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.2.3",
            "FAKE_GIT_SUBMODULE_CREATES": "1",
        },
        sentinel=False,
    )
    assert old[0] == 0
    assert "✓ Submodules initialized successfully" in old[2]
    assert "git submodule update --init --recursive private/" in files["old_calls"]
    assert_identical(old, new, files)


def test_a_failing_submodule_update_stops_the_run(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "FAKE_GIT_SUBMODULE_FAIL": "1"},
        sentinel=False,
    )
    assert old[0] == 1
    assert old[2].endswith("✗ Failed to initialize submodules\n")
    assert "fake git: submodule update refused" not in old[2], "the twin sends its stderr to null"
    assert_identical(old, new, files)


def test_a_submodule_update_that_lies_about_success_is_caught(
    tmp_path: pathlib.Path,
) -> None:
    """Exit 0 without the sentinel: the second check is what makes the first honest."""
    old, new, files = run_both(tmp_path, env_extra=dict(PAT_ENV), sentinel=False)
    assert old[0] == 1
    assert old[2].endswith("✗ Submodule initialization incomplete\n")
    assert_identical(old, new, files)


def test_a_failing_pointer_bump_detector_degrades_to_a_full_run(
    tmp_path: pathlib.Path,
) -> None:
    """Fail-safe by design: a warning, a re-assertion of false, and the run continues."""
    old, new, files = run_both(
        tmp_path,
        output="outputs.txt",
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.2.3",
            "FAKE_POINTER_BUMP_EXIT": "7",
        },
    )
    assert old[0] == 0
    assert "⚠ detect-pointer-bump.sh errored; running full CI" in old[2]
    assert files["old_output"].count("pointer_bump_only=false") == 2
    assert_identical(old, new, files)


def test_a_missing_pointer_bump_detector_is_bashs_message_and_a_full_run(
    tmp_path: pathlib.Path,
) -> None:
    """The script is not there at all: one bash line, the warning, and on we go."""
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "pull_request", "FAKE_GIT_TAGS": "v1.2.3"},
        missing_siblings=(".ci/scripts/ci/detect-pointer-bump.sh",),
    )
    assert old[0] == 0
    assert (
        "<prog>: line 131: .ci/scripts/ci/detect-pointer-bump.sh: No such file or directory"
    ) in strip_prog(old[2])
    assert "⚠ detect-pointer-bump.sh errored; running full CI" in old[2]
    assert_identical(old, new, files)
    assert port.DETECT_POINTER_BUMP_LINE == 131


def test_the_output_path_is_forwarded_to_the_detector_as_one_word(
    tmp_path: pathlib.Path,
) -> None:
    """`${OUTPUT_FILE:+--output "$OUTPUT_FILE"}` unquoted: the inner quotes hold."""
    old, new, files = run_both(
        tmp_path,
        output="a file with spaces.txt",
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "pull_request", "FAKE_GIT_TAGS": "v1.2.3"},
    )
    assert "detect-pointer-bump.sh --output a file with spaces.txt\n" in files["old_calls"]
    assert_identical(old, new, files)


# ---------------------------------------------------------------------------
# Step 5 and step 6
# ---------------------------------------------------------------------------


def test_a_failing_tag_generator_takes_its_exit_status_with_it(
    tmp_path: pathlib.Path,
) -> None:
    """`RENET_TAG=$(...)` under `set -e`: the assignment IS the failure."""
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "FAKE_GENERATE_TAG_EXIT": "4"},
    )
    assert old[0] == 4
    assert "renet_tag=" not in old[1]
    assert old[2].endswith("fake generate-tag: refusing\n")
    assert files["old_calls"].count("generate-tag.sh") == 1, "it must stop at the first one"
    assert_identical(old, new, files)


def test_a_skip_decision_writes_skip_release(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, env_extra={**PUSH_MAIN, "FAKE_DECISION": "skip"}, docker=False
    )
    assert "skip_release=true\n" in old[1]
    assert "✓ Release decision: decision: skip" in old[2]
    assert_identical(old, new, files)


def test_an_undecided_release_falls_open(tmp_path: pathlib.Path) -> None:
    """No `decision:` line at all: nothing is written and the run releases."""
    old, new, files = run_both(tmp_path, env_extra={**PUSH_MAIN, "FAKE_DECISION": ""})
    assert "skip_release" not in old[1]
    assert "✓ Release decision: <undecided, will release>" in old[2]
    assert_identical(old, new, files)


def test_the_deciders_stderr_is_swallowed_by_the_two_to_one_redirect(
    tmp_path: pathlib.Path,
) -> None:
    """`2>&1 | grep` means the child's diagnostics are filtered, never printed.

    The fake prints its own view of `$GITHUB_OUTPUT` to stderr, which also proves
    the variable reaches it as the EMPTY STRING rather than unset.
    """
    old, new, files = run_both(tmp_path, env_extra={**PUSH_MAIN, "FAKE_DECISION": "release"})
    assert "GITHUB_OUTPUT=[]" not in old[2]
    assert "GITHUB_OUTPUT=[UNSET]" not in old[2]
    assert "dispatch-release.sh GITHUB_OUTPUT=[] --decide-only" in files["old_calls"]
    assert_identical(old, new, files)


# ---------------------------------------------------------------------------
# The tag fetch: the block `test-releaseversion-tag-fetch.sh` also guards
# ---------------------------------------------------------------------------


def test_defect_a_an_unset_repository_slug_dies_at_line_219(
    tmp_path: pathlib.Path,
) -> None:
    """Eight outputs, a global git config write, three tags, and THEN this."""
    old, new, files = run_both(
        tmp_path,
        env_extra={
            "GITHUB_PAT": "s3cr3t-app-token",
            "GITHUB_REPOSITORY": None,
            "GITHUB_EVENT_NAME": "pull_request",
        },
    )
    assert old[0] == 1
    assert strip_prog(old[2]).endswith("<prog>: line 219: GITHUB_REPOSITORY: unbound variable\n")
    assert old[1].count("=") == 8, "the expensive half has already run and reported"
    assert_identical(old, new, files)
    assert port.UNCHECKED_REQUIRED_ENV == "GITHUB_REPOSITORY"
    assert port.FETCH_URL_LINE == 219


def test_an_empty_repository_slug_is_accepted_and_fetched(tmp_path: pathlib.Path) -> None:
    """`${VAR}` refuses UNSET and accepts EMPTY, so this one reaches the network layer."""
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_REPOSITORY": "",
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.2.3",
        },
    )
    assert old[0] == 0
    assert (
        "git fetch --tags --force --no-recurse-submodules "
        "https://x-access-token:s3cr3t-app-token@github.com/.git\n"
    ) in files["old_calls"]
    assert_identical(old, new, files)
    assert port.fetch_url("tok", "") == "https://x-access-token:tok@github.com/.git"


def test_three_failed_fetches_refuse_to_compute_a_version(tmp_path: pathlib.Path) -> None:
    """The whole retry ladder, its backoff, its refusal, and its redaction.

    Costs the real 15 seconds per side, because the two implementations must
    sleep the same amount: a fake `sleep` on the PATH would be used by bash and
    not by Python, and the call logs would then disagree for a reason that has
    nothing to do with the port.
    """
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_FETCH_FAIL": "1",
        },
        timeout=120,
    )
    assert old[0] == 1
    assert files["old_calls"].count("git fetch") == 3
    assert "⚠ Tag fetch attempt 1/3 failed\n⚠ Tag fetch attempt 2/3 failed\n" in old[2]
    assert "⚠ Tag fetch attempt 3/3 failed\n" in old[2]
    assert (
        "✗ Could not fetch tags after 3 attempts; refusing to compute a version from a "
        "tag list that may be stale.\n"
    ) in old[2]
    assert "s3cr3t-app-token" not in old[2], "the app token must never reach the log"
    assert "@github.com" in old[2], "the diagnostic must survive"
    assert "***" in old[2], "redacted, not suppressed"
    assert "git tag" not in files["old_calls"], "no version may be computed from a stale list"
    assert_identical(old, new, files)


def test_a_good_fetch_that_finds_no_tags_refuses_too(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={**PAT_ENV, "GITHUB_EVENT_NAME": "pull_request", "FAKE_GIT_TAGS": ""},
    )
    assert old[0] == 1
    assert "✗ Tag fetch succeeded but no v* tag exists" in old[2]
    assert "git tag -l v* --sort=-v:refname" in files["old_calls"]
    assert_identical(old, new, files)


def test_a_failing_tag_read_dies_silently_under_pipefail(tmp_path: pathlib.Path) -> None:
    """`git ... | head -1` with pipefail: git's status, and not a word of the script's own."""
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.2.3",
            "FAKE_GIT_TAG_EXIT": "9",
        },
    )
    assert old[0] == 9
    assert "Latest tag" not in old[2]
    assert "no v* tag exists" not in old[2], "a failed read is not an empty read"
    assert_identical(old, new, files)


def test_the_version_sort_is_gits_and_only_the_first_line_is_taken(
    tmp_path: pathlib.Path,
) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={
            **PAT_ENV,
            "GITHUB_EVENT_NAME": "pull_request",
            "FAKE_GIT_TAGS": "v1.10.0 v1.9.0",
        },
    )
    assert "✓ Latest tag: v1.10.0" in old[2]
    assert "✓ Next version: 1.2.4 (from tag: 1.2.3)" in old[2]
    assert_identical(old, new, files)


def test_redact_replaces_every_occurrence_and_leaves_the_rest() -> None:
    """The `sed s|tok|***|g` half, as a unit, including the empty-token stand-in."""
    assert port.redact(b"a tok b tok\n", "tok") == b"a *** b ***\n"
    assert port.redact(b"nothing here\n", "tok") == b"nothing here\n"
    assert port.redact(b"x __no_github_pat_set__ y", "") == b"x *** y"
    assert port.redact(b"\xff\xfe binary", "tok") == b"\xff\xfe binary"


# ---------------------------------------------------------------------------
# Colour, and the pins
# ---------------------------------------------------------------------------


def test_colour_is_emitted_on_a_terminal_by_both_sides(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, "--check-only", env_extra=dict(PAT_ENV), tty="stderr")
    assert diff.escape_bytes(old[2]) > 0, "the twin must colour a tty"
    assert diff.escape_bytes(old[1]) == 0, "stdout is data and must never be coloured"
    assert_identical(old, new, files)


def test_the_pinned_line_numbers_still_point_at_the_twins_lines() -> None:
    """Every constant the port prints inside a bash-shaped diagnostic.

    Without this the port would keep printing `line 219` after someone inserted a
    line above it, and every differential above would still pass -- both sides
    would be wrong together until the twin moved, and the failure would then name
    a byte difference instead of the reason for it.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as handle:
        lines = handle.read().split("\n")

    def at(number: int) -> str:
        return lines[number - 1]

    assert 'echo "${key}=${value}" >>"$OUTPUT_FILE"' in at(port.WRITE_OUTPUT_LINE)
    assert "git config --global url." in at(port.GIT_CONFIG_LINE)
    assert "git submodule update --init --recursive private/" in at(port.GIT_SUBMODULE_LINE)
    assert port.DETECT_POINTER_BUMP in at(port.DETECT_POINTER_BUMP_LINE)
    assert "--submodule private/renet" in at(port.GENERATE_TAG_RENET_LINE)
    assert "--closure web" in at(port.GENERATE_TAG_WEB_LINE)
    assert "--closure rdc" in at(port.GENERATE_TAG_RDC_LINE)
    assert port.DETECT_BUMP_TYPE in at(port.DETECT_BUMP_TYPE_LINE)
    assert "FETCH_URL=" in at(port.FETCH_URL_LINE)
    assert "git fetch --tags --force --no-recurse-submodules" in at(port.GIT_FETCH_LINE)
    assert "git tag -l 'v*' --sort=-v:refname" in at(port.GIT_TAG_LINE)
    assert "--bump-type" in at(port.RESOLVE_VERSION_NEXT_LINE)
    assert "--current" in at(port.RESOLVE_VERSION_CURRENT_LINE)


def test_the_five_sibling_paths_are_the_ones_the_twin_calls() -> None:
    """A renamed sibling must red HERE, not in a CI job three steps later."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as handle:
        body = handle.read()
    for path in (
        port.DETECT_POINTER_BUMP,
        port.GENERATE_TAG,
        port.DISPATCH_RELEASE,
        port.DETECT_BUMP_TYPE,
        port.RESOLVE_VERSION,
    ):
        assert path in body, "%s is not called by the twin any more" % path
    for path in (port.DETECT_POINTER_BUMP, port.GENERATE_TAG, port.RESOLVE_VERSION):
        assert os.access("%s/%s" % (diff.repo(), path), os.X_OK), "%s is not executable" % path
