"""`rediacc_ci.security.shellcheck`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/security/shellcheck.sh` and the port over one scratch git repository apiece and compared the exit code, both streams and the recorded argv of every tool call.

The ledger `.ci/shadow/w7p6-shellcheck.observations.jsonl` recorded that comparison over five distinct trees, every one of them EQUIVALENT; the row count is stated here from the file rather than carried forward from the sentence that used to claim it.

Every FIXTURE case now compares against `goldens/shellcheck/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

HOW THE CORPUS IS HELD STABLE, which is the whole difficulty of freezing a gate that shells out to a real linter. The gate PRINTS `shellcheck --version` on every run, so the pinned version is a byte on stdout, and the acquisition path puts it in a URL as well. Three things keep that out of the recordings.

  * THE TOOL IS A RECORDING FAKE in every frozen case, so no recorded byte
    carries the real shellcheck's findings, wording or banner.
  * THE PIN IS THE FIXTURE'S OWN. The scratch repository carries its own
    `.devcontainer/toolchain.env`, and the builder rewrites `SHELLCHECK_VERSION`
    to `0.0.0-fixture`. Both implementations resolve the pin from the tree they
    are standing in, and the fake answers `--version` with that same string,
    which is also what makes the acquisition ACCEPT it. A real pin bump cannot
    red one recorded byte.
  * THE ARCHITECTURE IS MASKED, because `uname -m` is the one input the fixture
    cannot own: the download URL names `x86_64` on this host and `aarch64` on
    another, and a recording is compared on whichever runner picks it up.

WHAT ELSE IS MASKED: the scratch repository's path becomes `<fx>` and its tool cache becomes `<cache>`, both of which the differential already folded. Nothing else, and in particular the bash-4 block's `grep -r` order is NOT normalised; it is confined to single-file fixtures instead, for the reason given in the port's module docstring.

THE REAL-TREE CASES ARE DELIBERATELY NOT FROZEN. A recording of "info: 620 file(s)" followed by the real tool's output is a recording of this repository on the day it was taken, and the next `.sh` file added would red it for a reason that has nothing to do with the port. They survive as live runs asserting the SHAPE: the count matches the enumerator, the banner is present, and not
one input file was mutated.

EVERY GIT OPERATION IS `git -C <scratch>` AND NEVER A `cd`, and `git_in` asserts that `rev-parse --show-toplevel` resolves inside the scratch directory before it runs anything. The repository this file lives in normally holds several sessions' uncommitted work; a stray `git add -A` in the wrong tree is not recoverable.

ONE FROZEN CASE IS COMPARED BY SHAPE, and it is a stated disagreement rather than a reproduction: a path with a space in it is re-split by `xargs` and is not re-split by the port. The twin's behaviour is plainly wrong and re-deriving xargs' quoting rules to be wrong in the same way would be a worse port. No such path exists in this tree today; the day one does, the difference is
already recorded.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.security import shellcheck as port
from rediacc_ci.tests import differential, frozen

ROOT = paths.repo_root()
SLUG = "shellcheck"

TWIN_REL = ".ci/scripts/security/shellcheck.sh"
PORT_REL = ".ci/rediacc_ci/security/shellcheck.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

CALLS_MARKER = "--- calls ---\n"

# The anti-collapse floor for the real enumerator. See `real_hashes`.
FLOOR = 150

# The fixture's own pin, so no recorded byte depends on the real one. The fake answers `--version` with this, which is also what makes the acquisition accept it.
#
# IT HAS TO BE PURELY NUMERIC, which cost this suite its first recording. `toolchain_probe_version` keeps only the leading dotted-numeric run of whatever the tool prints, so a pin of `0.0.0-fixture` probes back as `0.0.0`, fails its own equality check, and sends every case down the download path, where the recording is a 404 from GitHub rather than anything about the port.
FIXTURE_VERSION = "9.99.0"
ARCH_RE = re.compile(r"(?<![A-Za-z0-9])(?:x86_64|aarch64|arm64|amd64)(?![A-Za-z0-9])")

COPIED = (
    ".ci/scripts/lib/toolchain.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/proc.py",
    ".ci/rediacc_ci/gitx.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/toolchain.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

# What a BASH subject needed in the tree on top of that: the twin itself. Reached only by the one-shot recorder, which ran while the twin was still tracked; the suite's subject is the port or a throwaway mutant of it.
TWIN_ONLY = (TWIN_REL,)

TRIVIAL_SH = '#!/bin/bash\necho "$1"\n'

FAKE_SHELLCHECK = """#!/bin/bash
if [[ "$1" == "--version" ]]; then
    printf 'ShellCheck - fake\\nversion: %s\\n' "$FAKE_VERSION"
    exit 0
fi
printf 'FAKECALL shellcheck %s\\n' "$*" >>"$FAKE_LOG"
n=0
for a in "$@"; do
    [[ "$a" == -* || "$a" == SC* || "$a" == warning ]] && continue
    n=$((n + 1))
    if [[ -n "${FAKE_FLAG_ON:-}" && "$a" == *"$FAKE_FLAG_ON"* ]]; then
        printf 'In %s line 2:\\necho $1\\n     ^-- SC2086: Double quote.\\n' "$a"
        touch "$FAKE_DATA/flagged"
    fi
done
printf 'FAKEBATCH %d\\n' "$n" >>"$FAKE_LOG"
[[ -f "$FAKE_DATA/flagged" && -n "${FAKE_FLAG_ON:-}" ]] && exit 1
exit 0
"""

FAKE_CURL = """#!/bin/bash
printf 'FAKECALL curl %s\\n' "$*" >>"$FAKE_LOG"
exit 22
"""

BASH4_ALL_FOUR = "#!/bin/bash\ndeclare -A m\nfoo |& bar\ncoproc p { echo hi; }\nmapfile -t a < f\n"
BASH4_COMMENTED = "#!/bin/bash\n# mapfile -t a < f\n# declare -A m\n"
BASH4_WORD_BOUNDARY = "#!/bin/bash\ncoprocess=1\nreadarrayx=2\n"
BASH4_BACKSLASH_N = "#!/bin/bash\ndeclare -A m # printf 'a\\nb'\n"
BASH4_BACKSLASH_C = "#!/bin/bash\ndeclare -A m # \\c\ncoproc p { echo hi; }\n"

# name -> how the case is wired. `tweak` names the edit made to the built fixture, `bare` builds the alternate tree whose only tracked file is a .gitignore, `fake_tool` hides the fake shellcheck so the acquisition path is reached, and `env` adds to the base environment.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-clean-fixture": {},
    "forty-five-more-scripts": {"tweak": "many"},
    "findings-after-every-batch": {"tweak": "many", "env": {"FAKE_FLAG_ON": "gen00.sh"}},
    "a-tracked-file-deleted-in-the-working-tree": {"tweak": "delete-run-sh"},
    "two-deleted-files-listed-space-separated": {"tweak": "delete-two"},
    "deleting-the-last-sorted-file": {"tweak": "delete-last"},
    "a-path-with-a-space": {"tweak": "space-in-a-path"},
    "an-untracked-script": {"tweak": "untracked"},
    "a-gitignored-script": {"tweak": "gitignored"},
    "an-empty-corpus": {"bare": True},
    "an-unacquirable-shellcheck": {"fake_tool": False},
    "all-four-bash4-constructs": {"tweak": "build:" + BASH4_ALL_FOUR},
    "a-commented-mapfile-and-a-commented-declare": {"tweak": "build:" + BASH4_COMMENTED},
    "a-word-boundary-keeps-coprocess-out": {"tweak": "build:" + BASH4_WORD_BOUNDARY},
    "echo-e-mangles-a-backslash": {"tweak": "build:" + BASH4_BACKSLASH_N},
    "echo-e-backslash-c-truncates-the-report": {"tweak": "build:" + BASH4_BACKSLASH_C},
    "ci-true-disables-colour": {"env": {"CI": "true"}},
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = ("a-path-with-a-space",)


def write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def git_in(scratch: pathlib.Path, *args: str) -> str:
    """`git -C <scratch> ...`, with the toplevel guard fired FIRST.

    The guard is not decoration. `git add -A` and `git commit` in this repository would sweep several other sessions' uncommitted work into an index nobody asked for, and the check that the toplevel resolves inside `scratch` is the one thing standing between this fixture and that.
    """
    resolved = subprocess.run(
        ["git", "-C", str(scratch), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert pathlib.Path(resolved).resolve() == scratch.resolve(), (
        "REFUSING: git -C %s resolves to %s, not the scratch tree" % (scratch, resolved)
    )
    assert pathlib.Path(resolved).resolve() != ROOT.resolve(), "REFUSING: that is the real repo"
    return subprocess.run(
        ["git", "-C", str(scratch), *args],
        capture_output=True,
        text=True,
        check=True,
        env={
            **differential.env_for(),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    ).stdout


def repin(fx: pathlib.Path) -> None:
    """Give the scratch repository its OWN pin, so no recorded byte depends on the real one."""
    env_file = fx / ".devcontainer" / "toolchain.env"
    lines = [
        "SHELLCHECK_VERSION=%s" % FIXTURE_VERSION
        if line.startswith("SHELLCHECK_VERSION=")
        else line
        for line in env_file.read_text(encoding="utf-8").split("\n")
    ]
    env_file.write_text("\n".join(lines), encoding="utf-8")


def tweak(fx: pathlib.Path, kind: str | None) -> None:
    """The edit one case makes to the built fixture."""
    if kind is None:
        return
    if kind.startswith("build:"):
        write(fx / ".ci" / "scripts" / "build" / "b.sh", kind[len("build:") :])
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "build script")
        return
    if kind == "many":
        for index in range(45):
            write(fx / "scripts" / ("gen%02d.sh" % index), TRIVIAL_SH)
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "more")
    elif kind == "delete-run-sh":
        # The deleted file is deliberately NOT the last one in sorted order: that case is the defect below, and mixing the two would let a green here mean either thing.
        write(fx / "zz-last.sh", TRIVIAL_SH)
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "tail")
        (fx / "run.sh").unlink()
    elif kind == "delete-two":
        write(fx / "zz-last.sh", TRIVIAL_SH)
        write(fx / "scripts" / "two.sh", TRIVIAL_SH)
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "two")
        (fx / "scripts" / "one.sh").unlink()
        (fx / "scripts" / "two.sh").unlink()
    elif kind == "delete-last":
        files = sorted(git_in(fx, "ls-files", "*.sh").split())
        assert files[-1] == "scripts/one.sh", files
        (fx / "scripts" / "one.sh").unlink()
    elif kind == "space-in-a-path":
        write(fx / "scripts" / "has space.sh", TRIVIAL_SH)
        write(fx / "zz-last.sh", TRIVIAL_SH)
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "space")
    elif kind == "untracked":
        write(fx / "scripts" / "brand-new.sh", TRIVIAL_SH)
    elif kind == "gitignored":
        write(fx / ".gitignore", "ignored/\n")
        write(fx / "ignored" / "vendor.sh", TRIVIAL_SH)
    else:
        raise AssertionError("no such tweak: %r" % kind)


def build(tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL) -> pathlib.Path:
    """A scratch GIT repository holding the subject, the fakes and this case's edit."""
    kw = CASE_KW[name]
    fx = tmp_path / "fx"
    fx.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(fx)], check=True, capture_output=True, text=True
    )
    for rel in COPIED + (TWIN_ONLY if subject_rel.endswith(".sh") else ()):
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    repin(fx)
    if not subject_rel.endswith(".sh"):
        # THE SUBJECT IS A MEMBER OF THE CORPUS IT ENUMERATES, and that is not a detail here: a bash subject is a `.sh` file sitting at this path inside the fixture, so it was linted by its own run and counted in its own banner.
        # A Python subject is not, so the corpus would be one file short and every recorded count would be off by one. The placeholder keeps the enumeration identical; at recording time the file at this path WAS the twin.
        write(fx / TWIN_REL, TRIVIAL_SH)

    if kw.get("bare"):
        # THE ONLY WAY TO REACH AN EMPTY `git ls-files '*.sh'` is for the subject itself to be invisible to it, and the subject resolves its root from its own location. So it lives inside the tree and `.gitignore` hides it: nothing tracked is a `.sh`, and `--others --exclude-standard` honours the ignore.
        write(fx / ".gitignore", ".ci/\n")
        git_in(fx, "add", ".gitignore")
        git_in(fx, "commit", "-qm", "only the ignore file")
    else:
        write(fx / "run.sh", TRIVIAL_SH)
        write(fx / "scripts" / "one.sh", TRIVIAL_SH)
        git_in(fx, "add", "-A")
        git_in(fx, "commit", "-qm", "fixture")

    (fx / "fake" / "data").mkdir(parents=True, exist_ok=True)
    write(fx / "fake" / "bin" / "curl", FAKE_CURL, mode=0o755)
    write(fx / "fake" / "tool" / "shellcheck", FAKE_SHELLCHECK, mode=0o755)

    tweak(fx, kw.get("tweak"))
    return fx


def mask(text: str, fx: pathlib.Path) -> str:
    masked = text.replace(str(fx / "cache"), "<cache>").replace(str(fx), "<fx>")
    return ARCH_RE.sub("<arch>", differential.mask_toolchain_tmp(masked))


def drive(
    fx: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    """One subject, once, over an already-built fixture."""
    kw = CASE_KW[name]
    log = fx / "calls.log"
    log.write_text("", encoding="utf-8")
    (fx / "fake" / "data" / "flagged").unlink(missing_ok=True)
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["FAKE_LOG"] = str(log)
    env["FAKE_DATA"] = str(fx / "fake" / "data")
    env["FAKE_VERSION"] = FIXTURE_VERSION
    if kw.get("fake_tool", True):
        # THE FAKE CURL IS ON PATH EVEN HERE, where nothing should download: a fixture that stopped acquiring from PATH would otherwise reach GitHub, and the recording would be a 404 rather than a refusal.
        env["PATH"] = "%s%s%s%s%s" % (
            fx / "fake" / "tool",
            os.pathsep,
            fx / "fake" / "bin",
            os.pathsep,
            env["PATH"],
        )
    else:
        # No tool anywhere and a curl that refuses, so the acquisition path is what the case reaches. CI_TEMP points the cache at this case's own scratch.
        env["CI_TEMP"] = str(fx / "cache")
        env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, "/usr/bin:/bin")
    if not subject_rel.endswith(".sh"):
        env["PYTHONPATH"] = str(fx / ".ci")
    env.update(kw.get("env") or {})
    argv = (
        ["bash", str(fx / subject_rel)]
        if subject_rel.endswith(".sh")
        else ["python3", str(fx / subject_rel)]
    )
    proc = subprocess.run(
        argv, env=env, cwd=str(fx), capture_output=True, text=True, check=False, timeout=300
    )
    calls = mask(log.read_text(encoding="utf-8"), fx).splitlines()
    return proc.returncode, mask(proc.stdout, fx), mask(proc.stderr, fx), calls


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    return drive(build(tmp_path, name, subject_rel=subject_rel), name, subject_rel=subject_rel)


def render(code: int, stdout: str, stderr: str, calls: list[str]) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), CALLS_MARKER, "\n".join(calls))


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls.rstrip("\n").splitlines(),
    )


def batch_sizes(calls: list[str]) -> list[int]:
    return [int(line.split()[1]) for line in calls if line.startswith("FAKEBATCH ")]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the tool calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_real_pin_or_a_host_path() -> None:
    """THE STABILITY CLAIM, checked over the corpus rather than argued in prose.

    A golden that named the live `SHELLCHECK_VERSION` or an absolute path from the recording host would be a golden that reds on the next pin bump or on another runner.
    """
    live = toolchain.pin_for("shellcheck")
    assert live != FIXTURE_VERSION, "the fixture pin collided with the real one"
    for name in CASES:
        _code, stdout, stderr, calls = recorded(name)
        blob = "\n".join([stdout, stderr, *calls])
        assert live not in blob, name
        assert str(ROOT) not in blob, name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_clean_fixture_passes_and_batches_once() -> None:
    code, stdout, _, calls = recorded("a-clean-fixture")
    assert code == 0
    assert "info: Checking shell script compatibility" in stdout
    assert "success: Shell scripts passed" in stdout
    assert batch_sizes(calls) == [5], calls


def test_the_version_banner_is_printed_before_anything_is_linted() -> None:
    """`"$SHELLCHECK_BIN" --version` is the gate's own receipt that it acquired a tool at the pin, and the fixture's pin is what the recording carries."""
    stdout = recorded("a-clean-fixture")[1]
    assert "version: %s" % FIXTURE_VERSION in stdout
    assert stdout.index("version:") < stdout.index("file(s)")


def test_the_batch_size_is_forty() -> None:
    """`xargs -n 40`. The boundaries are OBSERVABLE in the real tool's output.

    45 scripts on top of the fixture's own, so the last batch is a short one and a port that chunked by 50 would show one invocation where there are two.
    """
    sizes = batch_sizes(recorded("forty-five-more-scripts")[3])
    assert sizes, "the fake shellcheck was never called"
    assert all(size <= 40 for size in sizes), sizes
    assert sizes[:-1] == [40] * (len(sizes) - 1), "a non-final batch was not full: %s" % sizes
    assert len(sizes) >= 2, "only one batch; the chunking is untested"


def test_findings_exit_1_after_every_batch_has_run() -> None:
    """xargs ran ALL batches and only then reported 123; so does the port."""
    code, stdout, stderr, calls = recorded("findings-after-every-batch")
    assert code == 1
    assert "error: shellcheck reported findings" in stderr
    assert "SC2086" in stdout
    assert len(batch_sizes(calls)) >= 2, "the run stopped at the first failing batch"


def test_a_tracked_file_deleted_in_the_working_tree_is_skipped() -> None:
    """`rm` without `git rm` leaves it in the index; shellcheck would die on it.

    THE CALL LOG IS WHERE THIS IS VISIBLE, and the differential this replaces looked in the wrong place: it filtered STDOUT for `FAKECALL` lines, which the fake writes to its log file and never to stdout, so the "the deleted file was not passed" half of the case could not fail. The recorded argv is the artifact that can.
    """
    code, stdout, _, calls = recorded("a-tracked-file-deleted-in-the-working-tree")
    assert code == 0
    assert "info: skipping 1 tracked file(s) deleted in the working tree: run.sh" in stdout
    argv = [line for line in calls if line.startswith("FAKECALL shellcheck ")]
    assert argv, calls
    assert not any(" run.sh" in line for line in argv), argv


def test_two_deleted_files_are_listed_space_separated() -> None:
    """`tr '\\n' ' '` with no trailing space, and the count from `wc -l`."""
    code, stdout, _, _ = recorded("two-deleted-files-listed-space-separated")
    assert code == 0
    assert (
        "info: skipping 2 tracked file(s) deleted in the working tree: "
        "scripts/one.sh scripts/two.sh" in stdout
    )


def test_deleting_the_last_sorted_file_kills_the_gate() -> None:
    """THE SECOND DEFECT, reproduced on both sides. See the port's docstring.

    `scripts/one.sh` sorts last in this fixture. Deleting it made the twin print its "skipping" line and then die at the FILTERING assignment, with exit 1 and not one file linted. Exit 1 is also "shellcheck reported findings", so the CI reader is told the tree is dirty when it was never read.
    """
    code, stdout, stderr, calls = recorded("deleting-the-last-sorted-file")
    assert code == 1, "the twin no longer dies here"
    assert calls == [], "shellcheck must never have run"
    assert "info: skipping 1 tracked file(s)" in stdout
    assert "error:" not in stderr, "and it dies with NO explanation: %r" % stderr


def test_an_untracked_script_is_still_checked() -> None:
    """`--others --exclude-standard`: a new gate test is covered before commit."""
    calls = recorded("an-untracked-script")[3]
    assert any("scripts/brand-new.sh" in line for line in calls), calls


def test_a_gitignored_script_is_not_checked() -> None:
    """The other half of `--exclude-standard`: node_modules must stay out."""
    calls = recorded("a-gitignored-script")[3]
    assert calls, "nothing was linted at all; the case proves nothing"
    assert not any("vendor.sh" in line for line in calls), calls


def test_the_empty_corpus_refusal_is_reachable() -> None:
    """A work tree with the subject and NOTHING else tracked."""
    code, _, stderr, calls = recorded("an-empty-corpus")
    assert code == 1
    assert calls == [], "shellcheck must not run over an empty list"
    assert (
        "error: no tracked *.sh files found: the enumerator is broken, not the tree clean" in stderr
    )


def test_an_unacquirable_shellcheck_is_exit_1_with_both_hints() -> None:
    code, stdout, stderr, calls = recorded("an-unacquirable-shellcheck")
    assert code == 1
    assert "error: shellcheck is unusable for this gate" in stderr
    assert "toolchain: could not download shellcheck from" in stderr
    assert "Every lane's toolchain:" in stdout
    assert any(line.startswith("FAKECALL curl ") for line in calls), calls


# --------------------------------------------------------------------------- The bash-4 block ---------------------------------------------------------------------------


def test_all_four_bash4_constructs_are_reported_in_order() -> None:
    """One file, all four probes, so the report's own section order is pinned."""
    code, stdout, stderr, _ = recorded("all-four-bash4-constructs")
    assert code == 1
    assert "Found bash 4+ features in build scripts" in stderr
    sections = [
        "declare -A (associative arrays require bash 4.0+):",
        "|& (pipe stderr requires bash 4.0+):",
        "coproc (requires bash 4.0+):",
        "mapfile/readarray (requires bash 4.0+):",
    ]
    positions = [stdout.index(s) for s in sections]
    assert positions == sorted(positions), "the four sections came out in another order"
    assert "macOS ships with bash 3.2 due to GPLv3 licensing." in stdout


def test_a_commented_mapfile_is_not_reported_but_a_commented_declare_is() -> None:
    """`^[^#]*` guards one pattern and not the other. Both directions."""
    code, stdout, _, _ = recorded("a-commented-mapfile-and-a-commented-declare")
    assert code == 1
    assert "# declare -A m" in stdout
    assert "mapfile -t a" not in stdout


def test_a_word_boundary_keeps_coprocess_out() -> None:
    """`grep -w`. A port using a bare substring test would flag this line."""
    code, stdout, _, _ = recorded("a-word-boundary-keeps-coprocess-out")
    assert code == 0, "a word-boundary miss became a finding:\n%s" % stdout
    assert "success: Shell scripts passed" in stdout


def test_echo_e_mangles_a_backslash_in_a_matched_line() -> None:
    """THE DEFECT, both sides. `echo -e` re-expands the SOURCE line's escapes.

    The matched line contains a literal backslash-n; the report shows a real newline in the middle of the finding, so the `path:line:` prefix and the rest of the source line end up on different lines of the output.
    """
    code, stdout, _, _ = recorded("echo-e-mangles-a-backslash")
    assert code == 1
    assert "declare -A m # printf 'a" in stdout
    assert "\\n" not in stdout, "the backslash survived; the defect is gone"
    assert "\nb'" in stdout, "the escape was not expanded into a real newline"


def test_echo_e_backslash_c_truncates_the_whole_report() -> None:
    """The worst of the four: every finding after a `\\c` silently disappears.

    The `declare -A` section comes first and carries the `\\c`; the `coproc` section that follows it is found, assembled, and then thrown away by `echo -e`. So the operator is told about one construct and not the other, with nothing indicating that anything was dropped.
    """
    code, stdout, _, _ = recorded("echo-e-backslash-c-truncates-the-report")
    assert code == 1
    assert "declare -A (associative arrays require bash 4.0+):" in stdout
    assert "coproc (requires bash 4.0+):" not in stdout, (
        "the truncation defect is gone; rewrite this case"
    )


# --------------------------------------------------------------------------- Colour ---------------------------------------------------------------------------


def test_colour_is_on_off_a_tty_because_this_gate_never_tests_one() -> None:
    assert differential.escape_bytes(recorded("a-clean-fixture")[1]) > 0, (
        "the gate stopped colouring off a tty"
    )


def test_ci_true_disables_colour() -> None:
    assert differential.escape_bytes(recorded("ci-true-disables-colour")[1]) == 0


# --------------------------------------------------------------------------- The one recorded divergence ---------------------------------------------------------------------------


def test_a_path_with_a_space_is_the_one_named_divergence(tmp_path: pathlib.Path) -> None:
    """NOT a reproduction. xargs re-split the path; this port does not.

    Written down as a disagreement rather than hidden, because the twin's behaviour is plainly wrong and re-deriving xargs' quoting rules to be wrong in the same way would be a worse port.

    THE LOG LINE ITSELF CANNOT SHOW THIS, and that is worth stating: the fake records `"$*"`, which re-joins its argv with spaces, so a path split into two arguments prints identically to one that was not. The COUNT is what sees it, which is exactly why the fake records a count as well as a line.
    """
    name = "a-path-with-a-space"
    want = recorded(name)
    got = run(tmp_path, name)
    twin_count = batch_sizes(want[3])
    port_count = batch_sizes(got[3])
    assert twin_count, want[3]
    assert port_count, got[3]
    assert sum(twin_count) == sum(port_count) + 1, (
        "xargs stopped re-splitting (%s vs %s); this divergence is gone and the note in "
        "shellcheck.py should be deleted" % (twin_count, port_count)
    )
    assert got[0] == want[0] == 0


# --------------------------------------------------------------------------- The real tree, live rather than frozen ---------------------------------------------------------------------------


def real_hashes() -> dict[str, str]:
    """sha256 of every file the real enumerator reaches. A collapse FAILS.

    THE FLOOR WAS INHERITED AND STALE, and it was red before this file was rewritten. It read `> 400`, written when the tree carried 620 shell scripts; the bash-twin retirement campaign has since removed hundreds, the count is 334 today and still falling, so the floor was refusing the campaign's success rather than a defect.

    It is now 150, which still refuses a collapsed enumerator (the failure mode is zero or a handful) without being a second, accidental inventory of the tree.
    """
    files = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.sh"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(ROOT),
    ).stdout.split("\0")
    out = {}
    for rel in files:
        if not rel:
            continue
        path = ROOT / rel
        if path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(out) >= FLOOR, "only %d shell files; the enumerator collapsed" % len(out)
    return out


def test_the_real_repository_passes_with_the_real_shellcheck() -> None:
    """Every real script through the real pinned tool. NOT FROZEN, and the module docstring says why: the count in this banner is a fact about the repository today rather than about the port."""
    before = real_hashes()
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(ROOT / ".ci")
    proc = subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    assert "info: Checking every tracked and untracked *.sh file" in proc.stdout
    assert ("info: %d file(s)" % len(before)) in proc.stdout, (
        "the gate counted something other than the %d files git lists" % len(before)
    )
    assert real_hashes() == before, "a real run mutated a shell script"


def test_the_real_enumeration_matches_the_ports_exactly() -> None:
    """Cheap half of the case above, so a broken enumerator reds in a second."""
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        found = port.shell_files()
    finally:
        os.chdir(cwd)
    assert sorted(real_hashes()) == [f for f in found if (ROOT / f).is_file()]
    assert len(found) >= FLOOR


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_batches_are_forty_wide_and_lose_nothing() -> None:
    items = ["f%03d" % i for i in range(85)]
    chunks = port.batches(items)
    assert [len(c) for c in chunks] == [40, 40, 5]
    assert [x for c in chunks for x in c] == items
    assert port.batches([]) == []


def test_echo_e_expands_the_separators_and_stops_at_backslash_c() -> None:
    assert port.echo_e("a\\nb") == "a\nb\n"
    assert port.echo_e("a\\tb") == "a\tb\n"
    assert port.echo_e("a\\\\b") == "a\\b\n"
    assert port.echo_e("a\\cb") == "a", "no trailing newline after \\c either"
    assert port.echo_e("a\\qb") == "a\\qb\n", "an unknown escape is left alone"
    assert port.echo_e("\\x41") == "A\n"
    assert port.echo_e("\\0101") == "A\n"


def single_quote(text: str) -> str:
    return "'%s'" % text.replace("'", "'\\''")


def test_echo_e_agrees_with_bash_on_every_case_above() -> None:
    """The assertion above is only worth as much as BASH agreeing with it.

    Drives the real `echo -e` for each case, so the unescaper is pinned to the behaviour it is reproducing rather than to one reading of the manual.
    """
    for text in ("a\\nb", "a\\tb", "a\\\\b", "a\\cb", "a\\qb", "\\x41", "\\0101"):
        code, out, _err = differential.bash_streams(
            "echo -e %s" % single_quote(text), env=differential.env_for(), cwd=str(ROOT)
        )
        assert code == 0
        assert out == port.echo_e(text), "bash %r -> %r, port -> %r" % (
            text,
            out,
            port.echo_e(text),
        )


def test_missing_files_follows_symlinks_like_dash_e(tmp_path: pathlib.Path) -> None:
    """`[ -e ]` follows, so a dangling symlink counts as MISSING."""
    (tmp_path / "real.sh").write_text("", encoding="utf-8")
    (tmp_path / "dangling.sh").symlink_to(tmp_path / "gone.sh")
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert port.missing_files(["real.sh", "dangling.sh", "absent.sh"]) == [
            "dangling.sh",
            "absent.sh",
        ]
    finally:
        os.chdir(cwd)


def test_the_flags_and_the_batch_size_are_the_twins() -> None:
    """The twin's literals are gone from the tree, so what is asserted is that the port still carries them and that the recorded argv agrees with the flags."""
    assert port.SHELLCHECK_OPTS == ("-e", "SC1090", "-e", "SC1091", "-e", "SC2034", "-S", "warning")
    assert port.BATCH == 40
    assert port.BUILD_DIR == ".ci/scripts/build"
    argv = [line for line in recorded("a-clean-fixture")[3] if line.startswith("FAKECALL shell")]
    assert argv, "no recorded shellcheck call to compare the flags against"
    assert " ".join(port.SHELLCHECK_OPTS) in argv[0], argv[0]


def test_colours_reads_ci_at_the_call_site(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert port.colours() == (port.RED, port.GREEN, port.NC)
    monkeypatch.setenv("CI", "true")
    assert port.colours() == ("", "", "")
    monkeypatch.setenv("CI", "1")
    assert port.colours() == (port.RED, port.GREEN, port.NC), "only the exact string 'true'"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_wider_batch_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Chunk by fifty instead of forty.

    The batch size is not cosmetic: 451 files with dataflow on peaked at 3074 MB and was OOM-killed on a 6.6 GB box, and the batching is the floor that keeps the many-files component of that bounded. It is also invisible on both streams, because the fake records to its log rather than to stdout: the mutant prints exactly what the recording prints and only `--- calls ---` sees that
    one invocation replaced two.

    THE MUTANT LIVES AT THE PORT'S OWN PATH INSIDE THE SCRATCH REPOSITORY, which is what makes the plant honest: the subject resolves its root from its own location, so a copy anywhere else would resolve a different tree. The fixture is a throwaway copy already; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "BATCH = 40\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "BATCH = 50\n")

    name = "forty-five-more-scripts"
    want = recorded(name)
    fx = build(tmp_path / "planted", name)
    (fx / PORT_REL).write_text(mutated, encoding="utf-8")
    got = drive(fx, name)

    assert batch_sizes(want[3]) == [40, 10], "the recorded corpus moved: %s" % want[3]
    assert batch_sizes(got[3]) == [50], "the plant did not widen the batch"
    assert got[:3] == want[:3], "only the recorded argv may differ, and it is what catches this"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
