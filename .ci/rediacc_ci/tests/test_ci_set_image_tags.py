"""`rediacc_ci.ci.set_image_tags`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/set-image-tags.sh` and the port over the same fixture and compared exit code, stdout, stderr and the bytes appended to `$GITHUB_ENV`. The K=5 ledger `.ci/shadow/w7p6-set-image-tags.observations.jsonl` recorded that comparison over five distinct trees. Both the twin and its sibling `derive-image-tag.sh` have now been
deleted -- they had to go together, since the twin's whole first half was a call to the sibling -- and every case that executed them compares against `goldens/set-image-tags/`, which holds the twin's OWN recorded bytes, captured from the tracked scripts on their last day in the tree. Each golden's provenance header carries the twin's blob sha, so `git cat-file -p <sha>`
still yields the program that produced them.

WHAT WAS DRIVEN FOR REAL AND WHAT WAS FIXTURED. Every case with an explicit `IMAGE_TAG` ran against the REAL checkout, because that arm reads nothing from the tree: the sibling validates the value and prints it. The auto-derive arm reads `git tag -l 'v*' --sort=-v:refname`, whose answer is whatever this repository happens to be tagged at, so it runs inside a DISPOSABLE
one-commit repository built under `tmp_path` and carrying exactly the tags the case needs. `assert_scratch` re-derives `git rev-parse --show-toplevel` before any fixture is written to, and refuses anything inside the checkout.

HOW THE PORT IS POINTED AT THE FIXTURE. It resolves through `paths.repo_root()`, which honours `$REDIACC_CI_ROOT`. The twin resolved through `get_repo_root` (common.sh:205), which walks three directories up from the common.sh THAT WAS SOURCED, so the recording's fixture also carried a copy of common.sh and SYMLINKS to the two real scripts -- bash does not resolve symlinks
in `${BASH_SOURCE[0]}`, so what was recorded was the real, unmodified twin. The suite no longer builds those three files, and the port cannot tell the difference: the only thing either side reads out of the fixture is the git tag list.

WHAT IS NORMALISED, and it is two tokens. The sibling printed `<program>: line 81: ...` for a tag build with no `GITHUB_REF_NAME`, and the program is a `.sh` in the recording and a `.py` here; `strip_prog` replaces that one token, and the LINE NUMBER is compared, because a drifting line number is the silent failure the pin exists to catch. The unwritable-target case names
its own temporary directory, which `mask_root` replaces, for the reason `frozen.py` gives: a recording is compared against a tree built under a different tempdir name months later.

THE TWO STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE. One re-read the twin's two `>>"$GITHUB_ENV"` appends so the port's `WEB_TAG_LINE` and `RENET_TAG_LINE` could not drift from them; those numbers now name lines in a file that only history holds, and they reach no recording because twin line 33 was unreachable whenever the sibling had already written to the same
target. What is still asserted here is the part that can still be wrong: the ORDER of `OVERRIDES`, which the five recorded `GITHUB_ENV` lines fix exactly. The other alarm grepped the tree for a second live caller of the sibling; there is no sibling to call any more, and `test_the_sibling_is_called_in_process` asserts the replacement.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import typing

import pytest

from rediacc_ci.ci import set_image_tags as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

SLUG = "set-image-tags"
MODULE = "rediacc_ci.ci.set_image_tags"

ENV_MARKER = "--- github env ---\n"
NO_ENV = "<no file captured>"

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

TAGS = {"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": "renet-abc"}

# name -> how the run is wired
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "both-overrides-after-the-siblings-three": {"env_extra": dict(TAGS)},
    "no-overrides-at-all": {"env_extra": {"IMAGE_TAG": "v1.2.3"}},
    "one-override-present-and-one-empty": {
        "env_extra": {"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc", "RENET_TAG": ""}
    },
    "an-empty-image-tag-auto-derives": {"env_extra": {"IMAGE_TAG": ""}, "tags": ("v4.5.6",)},
    "the-auto-derive-arm-takes-the-newest-tag": {"tags": ("v1.9.0", "v1.10.0")},
    "an-invalid-tag-stops-before-the-overrides": {
        "env_extra": {"IMAGE_TAG": "not a tag", "WEB_TAG": "web-abc"}
    },
    "a-tag-build-with-no-ref-name": {
        "tags": ("v1.0.0",),
        "env_extra": {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": None},
    },
    "an-unset-github-env": {"env_extra": dict(TAGS), "github_env": None},
    "an-unwritable-github-env": {
        "env_extra": {"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc"},
        "github_env": "unwritable",
    },
    "colour-on-a-terminal": {
        "env_extra": {"IMAGE_TAG": "v1.2.3", "WEB_TAG": "web-abc"},
        "tty": "stderr",
    },
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = "an-unwritable-github-env"


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


def fixture_root(where: pathlib.Path, *tags: str) -> pathlib.Path:
    """A repo-shaped fixture carrying exactly `tags`."""
    root = assert_scratch(where / "fixture")
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", *GIT_FLAGS, "init", "-q", str(root)], check=True, capture_output=True)
    top = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert_scratch(root)
    assert top == str(root.resolve()), "fixture resolved to %r" % top
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


def run(
    where: pathlib.Path,
    command: str,
    name: str,
    *,
    env_extra: dict[str, str | None] | None = None,
    tags: tuple[str, ...] = (),
    github_env: str | None = "",
    tty: str | None = None,
) -> tuple[int, str, str, str | None]:
    """One side, once. `github_env=""` gives it its own file.

    `github_env=None` leaves the variable UNSET (DEFECT E); `"unwritable"` points it inside a directory that does not exist.
    """
    where.mkdir(parents=True, exist_ok=True)
    root = fixture_root(where, *tags) if tags or name == "a-tag-build-with-no-ref-name" else None

    env: dict[str, str | None] = dict(env_extra or {})
    captured: pathlib.Path | None = None
    if github_env == "":
        captured = where / "github-env.txt"
        captured.write_text("", encoding="utf-8")
        env["GITHUB_ENV"] = str(captured)
    elif github_env is None:
        env["GITHUB_ENV"] = None
    else:
        env["GITHUB_ENV"] = str(where / "no-such-dir" / "env.txt")

    if command.startswith("python3"):
        env["PYTHONPATH"] = "%s/.ci" % diff.repo()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if root is not None:
            env["REDIACC_CI_ROOT"] = str(root)

    # `{root}` is how the one-shot recorder reached the twin through the fixture's own symlink, since `get_repo_root` walked up from the common.sh that was sourced. The port takes no placeholder and formats to itself.
    returncode, stdout, stderr = diff.bash_streams(
        command.format(root=root if root is not None else diff.repo()),
        env=diff.env_for(**env),
        cwd=diff.repo(),
        tty=tty,
        timeout=30,
    )
    written = captured.read_text(encoding="utf-8") if captured is not None else None
    return returncode, stdout, frozen.mask_root(strip_prog(stderr), where), written


def render(returncode: int, stdout: str, stderr: str, written: str | None) -> str:
    body = frozen.render(returncode, stdout, stderr)
    return body + ENV_MARKER + json.dumps(written, ensure_ascii=False) + "\n"


def recorded(name: str) -> tuple[int, str, str, str | None]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, written = rest.split(ENV_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, json.loads(written)


def drive(tmp_path: pathlib.Path, name: str, *, command: str = "python3 -m %s" % MODULE):
    return run(tmp_path / "run", command, name, **CASE_KW[name])


def compare(tmp_path: pathlib.Path, name: str) -> None:
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: GITHUB_ENV diverged: %r vs %r" % (name, want[3], got[3])


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The explicit-tag arm ---------------------------------------------------------------------------


def test_both_overrides_are_appended_after_the_siblings_three_names() -> None:
    """The whole point of the script: five lines, in one fixed order."""
    returncode, stdout, _, written = recorded("both-overrides-after-the-siblings-three")
    assert returncode == 0
    assert stdout == "v1.2.3\n"
    assert written == (
        "TAG=v1.2.3\n"
        "WEB_TAG=v1.2.3\n"
        "RENET_TAG=v1.2.3\n"
        "WEB_TAG=web-abc-amd64\n"
        "RENET_TAG=renet-abc-amd64\n"
    )
    # The recorded order IS the table, so the port's copy is checked against it rather than left as a comment that can quietly go stale.
    appended = [line for line in written.splitlines() if line.endswith("-amd64")]
    assert [line.split("=", 1)[0] for line in appended] == [n for n, _ in port.OVERRIDES]
    assert port.WEB_TAG_LINE < port.RENET_TAG_LINE, "web is appended first"


def test_defect_f_the_success_line_reports_the_input_not_the_value_written() -> None:
    """The file says `web-abc-amd64`; the log says `web=web-abc`."""
    _, _, stderr, written = recorded("both-overrides-after-the-siblings-three")
    assert "✓ Image tags set (web=web-abc renet=renet-abc)\n" in stderr
    assert "web-abc-amd64" in written
    assert "web-abc-amd64" not in stderr


def test_with_no_initialize_tags_only_the_sibling_writes() -> None:
    """The negative control for the case above: three lines, not five."""
    _, _, stderr, written = recorded("no-overrides-at-all")
    assert written == "TAG=v1.2.3\nWEB_TAG=v1.2.3\nRENET_TAG=v1.2.3\n"
    assert stderr.endswith("✓ Image tags set (web=<derived> renet=<derived>)\n")


def test_one_override_present_and_one_absent() -> None:
    """`[[ -n "$WEB_TAG" ]] && echo` with WEB set and RENET empty. Both arms, one run.

    Also the `set -e` question: the failing `[[ -n "" ]]` must NOT end the script, so the trailing log line has to be there.
    """
    returncode, _, stderr, written = recorded("one-override-present-and-one-empty")
    assert returncode == 0
    assert written.endswith("WEB_TAG=web-abc-amd64\n")
    assert "RENET_TAG=-amd64" not in written
    assert "✓ Image tags set (web=web-abc renet=<derived>)" in stderr


def test_an_empty_image_tag_falls_through_to_auto_derive() -> None:
    """`[[ -n "${IMAGE_TAG:-}" ]]` treats unset and empty alike."""
    returncode, stdout, stderr, _ = recorded("an-empty-image-tag-auto-derives")
    assert returncode == 0
    assert stdout == "4.5.6\n"
    assert "Auto-derived from git tags" in stderr
    assert port.derive_argv("") == ["--env-file"]
    assert port.derive_argv("v1") == ["--version", "v1", "--env-file"]


def test_the_auto_derive_arm_reads_the_fixtures_newest_tag() -> None:
    """`--sort=-v:refname` is a VERSION sort: v1.10.0 outranks v1.9.0."""
    _, stdout, _, written = recorded("the-auto-derive-arm-takes-the-newest-tag")
    assert stdout == "1.10.0\n"
    assert written == "TAG=1.10.0\nWEB_TAG=1.10.0\nRENET_TAG=1.10.0\n"


# --------------------------------------------------------------------------- The refusal arms ---------------------------------------------------------------------------


def test_an_invalid_tag_stops_the_script_before_the_overrides() -> None:
    """`set -e` on the sibling: no overrides, no success line, the sibling's exit."""
    returncode, stdout, stderr, written = recorded("an-invalid-tag-stops-before-the-overrides")
    assert returncode == 1
    assert stdout == ""
    assert "✗ Invalid tag format: not a tag" in stderr
    assert "Image tags set" not in stderr
    assert written == ""


def test_a_tag_build_with_no_ref_name_is_the_siblings_line_81() -> None:
    """The one diagnostic that carried a program name, and its line is pinned."""
    returncode, _, stderr, _ = recorded("a-tag-build-with-no-ref-name")
    assert returncode == 1
    assert stderr == (
        "<prog>: line 81: GITHUB_REF_NAME: GITHUB_REF_NAME is not set for a tag build\n"
    )


def test_defect_e_an_unset_github_env_claims_success_having_set_nothing() -> None:
    """The caller asked for tags to be set. Nothing was, and the exit is 0."""
    returncode, stdout, stderr, written = recorded("an-unset-github-env")
    assert returncode == 0, "the twin's DEFECT E changed; re-read the module docstring"
    assert "⚠ GITHUB_ENV not set, skipping --env-file" in stderr
    assert "✓ Image tags set (web=web-abc renet=renet-abc)" in stderr
    assert "amd64" not in stderr
    assert "amd64" not in stdout
    assert written is None
    assert port.GITHUB_ENV_IS_SILENTLY_OPTIONAL == "GITHUB_ENV"


def test_an_unwritable_github_env_dies_in_the_sibling_and_the_port_dies_louder(
    tmp_path: pathlib.Path,
) -> None:
    """A KNOWN DIVERGENCE, and it belongs to `derive_image_tag`, not to this port.

    The unwritable target was reached by the SIBLING first (it writes TAG, WEB_TAG and RENET_TAG before this script appends anything), so `set-image-tags.sh`'s own line 33 was unreachable in this case and what the two sides are really compared on is the sibling's line 134 against `derive_image_tag.write_github_env`. The STATUS agrees; the stderr does not, and a traceback
    where the twin printed one line reads as a crash in the porting harness rather than as a bad path. So the disagreement is PINNED instead of hidden: when `write_github_env` and `write_github_output` learn to catch OSError, this test goes red, and the fix is to delete the two assertions about the traceback and call `compare` like every other case in this file.
    """
    want_exit, want_out, want_err, _ = recorded(DIVERGENT)
    returncode, stdout, stderr, _ = drive(tmp_path, DIVERGENT)
    assert want_exit == 1
    assert returncode == want_exit, "the exit codes still have to agree"
    assert want_out == stdout == ""
    assert want_err.endswith(
        "<prog>: line 134: <root>/no-such-dir/env.txt: No such file or directory\n"
    )
    assert "Image tags set" not in want_err
    assert "Traceback (most recent call last)" in stderr, (
        "derive_image_tag.write_github_env now handles OSError; drop this pin and compare instead"
    )


def test_the_scripts_own_append_names_its_own_line_when_it_fails(
    tmp_path: pathlib.Path,
) -> None:
    """`append_override` directly, because no recording can reach it.

    Twin line 33 was only ever reached when the sibling had ALREADY appended three names to the same file, so any target that breaks this append breaks the sibling's first. The branch is still real -- a target removed or remounted read-only between the two writes, or a full disk -- and without a test it is a code path nobody has ever run. Driven here as a unit, since no
    recording can produce the state.
    """
    target = str(tmp_path / "gone" / "env.txt")
    with pytest.raises(SystemExit) as refusal:
        port.append_override("WEB_TAG", "web-abc", target, port.WEB_TAG_LINE)
    assert refusal.value.code == 1


def test_the_sibling_is_called_in_process() -> None:
    """The replacement for the staleness alarm that grepped for a second live caller.

    `derive-image-tag.sh` was retired with this twin, so the only implementation of the derivation is `rediacc_ci.ci.derive_image_tag`, and this module calls it directly rather than spawning anything. A second implementation of tag derivation is exactly what the module docstring argues against.
    """
    with open(port.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "from rediacc_ci.ci import derive_image_tag" in source
    assert "derive_image_tag.main(" in source, "the derivation is called, not re-implemented"
    assert "import subprocess" not in source, "the sibling must not be spawned"


# --------------------------------------------------------------------------- Colour ---------------------------------------------------------------------------


def test_colour_is_emitted_on_a_terminal() -> None:
    """stderr on a pty. The one branch a developer actually sees."""
    assert diff.escape_bytes(recorded("colour-on-a-terminal")[2]) > 0, "the twin must colour a tty"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_override_order_swap_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Append RENET_TAG before WEB_TAG.

    `$GITHUB_ENV` is read as a sequence of assignments, so the LAST value for a name wins; the three lines the sibling writes are then corrected by these two, and their order relative to each other is the only thing keeping a reader's mental model of the file honest. The recorded file ends `WEB_TAG=web-abc-amd64\\nRENET_TAG=renet-abc-amd64\\n`; a mutant that swaps them
    exits 0 with byte-identical streams, so the written file is the only witness. The mutation runs from a throwaway copy of the package's module file; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = (
        '        if os.environ.get("WEB_TAG", ""):\n'
        '            append_override("WEB_TAG", os.environ.get("WEB_TAG", ""), '
        "github_env, WEB_TAG_LINE)\n"
        '        if os.environ.get("RENET_TAG", ""):\n'
        "            append_override(\n"
        '                "RENET_TAG", os.environ.get("RENET_TAG", ""), github_env, RENET_TAG_LINE\n'
        "            )\n"
    )
    assert original.count(anchor) == 1, "the plant's anchor moved"
    swapped = (
        '        if os.environ.get("RENET_TAG", ""):\n'
        "            append_override(\n"
        '                "RENET_TAG", os.environ.get("RENET_TAG", ""), github_env, RENET_TAG_LINE\n'
        "            )\n"
        '        if os.environ.get("WEB_TAG", ""):\n'
        '            append_override("WEB_TAG", os.environ.get("WEB_TAG", ""), '
        "github_env, WEB_TAG_LINE)\n"
    )
    mutated = original.replace(anchor, swapped)

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "set_image_tags.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "both-overrides-after-the-siblings-three"
    returncode, _, _, written = run(
        tmp_path / "planted", "python3 %s" % mutant, name, **CASE_KW[name]
    )
    want = recorded(name)[3]
    assert want.endswith("WEB_TAG=web-abc-amd64\nRENET_TAG=renet-abc-amd64\n")
    assert returncode == 0, "the plant must not change the verdict"
    assert written.endswith("RENET_TAG=renet-abc-amd64\nWEB_TAG=web-abc-amd64\n"), (
        "the plant did not change the written file: %r" % written
    )

    compare(tmp_path / "good", name)
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original
