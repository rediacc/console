"""`rediacc_ci.security.shfmt`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/security/shfmt.sh` and the port over one scratch tree apiece and compared the exit code, both streams and the recorded argv of every tool call.

The ledger `.ci/shadow/w7p6-shfmt.observations.jsonl` recorded that comparison over five distinct trees, every one of them EQUIVALENT; the row count is stated here from the file rather than carried forward.

HOW THE CORPUS IS HELD STABLE. This gate prints `shfmt --version` and renders whatever diff the real formatter produces, so both the pin and the formatter's own rendering could have ended up frozen into a golden. Neither does.

  * THE TOOL IS A RECORDING FAKE in every frozen case, and it is SCRIPTED: it
    emits a canned diff block for a file named in `$FAKE_DIRTY` and a canned
    parse error for one named in `$FAKE_BAD`. What those cases test is the
    gate's plumbing, which scopes run, which stream carries what, and where the
    run stops, and none of that belongs to shfmt's diff algorithm.
  * THE PIN IS THE FIXTURE'S OWN. The scratch tree carries its own
    `.devcontainer/toolchain.env` and the builder rewrites `SHFMT_VERSION` to a
    numeric literal, which the fake then answers `--version` with. It has to be
    numeric: `toolchain_probe_version` keeps only the leading dotted-numeric run
    of what a tool prints, so a decorated pin probes back as something else and
    fails its own equality check.
  * THE REAL FORMATTER STILL RUNS, but in a LIVE case that is not frozen, so the
    claim that its bytes reach stdout unaltered is still driven and no version
    of its rendering is recorded.

WHAT IS NORMALISED, and it is the one thing the differential normalised too: the ORDER of the file arguments inside a single `shfmt` invocation. That order is not the subject's property at all, it is whatever `find` hands it, and POSIX leaves find's traversal order unspecified. This host does not even run GNU findutils (`bfs 4.1.1`, breadth-first) while `ubuntu-latest` runs GNU's
depth-first pre-order, and over `.ci` alone the two emit the same files in a visibly different sequence. So the recorded argv carries its flags in order and its files sorted, and `test_the_ports_order_is_byte_order` states what is left of the attribution.

WHAT THAT ATTRIBUTION LOST. The differential had two halves: the twin's block order follows the ambient `find`, and the port's follows byte order. The first half cannot outlive the twin. The second is kept, and so is the fact that makes it interesting, that the ambient find is NOT sorted, so the port's sortedness is a choice rather than a coincidence.

THE REAL-TREE CASE IS DELIBERATELY NOT FROZEN, for the same reason as its siblings: a recording of this repository's formatting verdict is a recording of the tree on the day it was taken. It survives as a live run asserting the shape and a read-only guard over every file in all four scopes.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.security import shfmt as port
from rediacc_ci.tests import differential, frozen

ROOT = paths.repo_root()
SLUG = "shfmt"

TWIN_REL = ".ci/scripts/security/shfmt.sh"
PORT_REL = ".ci/rediacc_ci/security/shfmt.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

CALLS_MARKER = "--- calls ---\n"

# The fixture's own pin. NUMERIC, for the reason in the module docstring.
FIXTURE_VERSION = "9.99.0"

# The minimum of the package a path-invoked port needs. `core/toolchain.py` is the shared acquisition path, so its bash original comes too.
COPIED = (
    ".ci/scripts/lib/toolchain.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/toolchain.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

# What a BASH subject needed on top of that. Reached only by the one-shot recorder; the suite's subject is the port or a throwaway mutant of it.
TWIN_ONLY = (TWIN_REL,)

# shfmt-CLEAN, at `-i 4 -ci`. Every fixture scope gets one of these so that a case can introduce exactly one dirty file and know the diff came from it.
CLEAN_SH = """#!/bin/bash
main() {
    local x="$1"
    case "$x" in
        a) echo a ;;
        *) echo b ;;
    esac
}

main "$@"
"""

# Two-space indent where the formatter wants four, plus an un-indented case arm. Only the LIVE case feeds this to the real shfmt; the frozen cases name a file in `$FAKE_DIRTY` instead.
DIRTY_SH = """#!/bin/bash
main() {
  local x="$1"
  case "$x" in
  a) echo a ;;
  *) echo b ;;
  esac
}

main "$@"
"""

# A SCRIPTED fake. It answers `--version` from the fixture's pin, records its argv, and then emits a canned diff for any file named in `$FAKE_DIRTY` and a canned parse error for any file named in `$FAKE_BAD`, exiting 1 if it emitted either.
FAKE_SHFMT = """#!/bin/bash
if [[ "$1" == "--version" ]]; then
    printf 'v%s\\n' "$FAKE_VERSION"
    exit 0
fi
printf 'FAKECALL shfmt %s\\n' "$*" >>"$FAKE_LOG"
rc=0
for a in "$@"; do
    [[ "$a" == -* || "$a" == 4 ]] && continue
    for needle in ${FAKE_DIRTY:-}; do
        if [[ "$a" == *"$needle"* ]]; then
            printf 'diff %s.orig %s\\n--- %s.orig\\n+++ %s\\n@@ -1,2 +1,2 @@\\n-  local x\\n+    local x\\n' "$a" "$a" "$a" "$a"
            rc=1
        fi
    done
    for needle in ${FAKE_BAD:-}; do
        if [[ "$a" == *"$needle"* ]]; then
            printf '%s:2:4: "if" must be followed by "then"\\n' "$a" >&2
            rc=1
        fi
    done
done
exit "$rc"
"""

FAKE_CURL = """#!/bin/bash
printf 'FAKECALL curl %s\\n' "$*" >>"$FAKE_LOG"
exit 22
"""

# name -> how the case is wired. `tweak` names the edit made to the built tree, `fake_tool` puts the scripted shfmt on PATH, and `env` adds to the environment.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-clean-fixture": {},
    "a-dirty-file-in-claude": {"env": {"FAKE_DIRTY": ".claude/two.sh"}},
    "a-dirty-run-sh": {"env": {"FAKE_DIRTY": "run.sh"}},
    "a-dirty-scripts-ops-file": {"env": {"FAKE_DIRTY": "scripts/ops/four.sh"}},
    "an-unparseable-file": {"env": {"FAKE_BAD": ".claude/two.sh"}},
    "the-first-failing-scope-aborts-the-rest": {
        "env": {"FAKE_DIRTY": ".claude/two.sh scripts/ops/four.sh"}
    },
    "the-vacuity-floor-refuses-a-collapsed-corpus": {"env": {"SHFMT_MIN_FILES": "9999"}},
    "the-floor-counts-the-three-roots": {
        "tweak": "extra-claude-file",
        "env": {"SHFMT_MIN_FILES": "9999"},
    },
    "a-missing-scripts-directory": {
        "tweak": "drop-scripts",
        "env": {"SHFMT_MIN_FILES": "2"},
    },
    "an-unacquirable-shfmt": {"fake_tool": False},
    "ci-true-disables-colour": {"env": {"CI": "true"}},
}

CASES = tuple(CASE_KW)


def write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def repin(fx: pathlib.Path) -> None:
    """Give the scratch tree its OWN pin, so no recorded byte depends on the real one."""
    env_file = fx / ".devcontainer" / "toolchain.env"
    lines = [
        "SHFMT_VERSION=%s" % FIXTURE_VERSION if line.startswith("SHFMT_VERSION=") else line
        for line in env_file.read_text(encoding="utf-8").split("\n")
    ]
    env_file.write_text("\n".join(lines), encoding="utf-8")


def build(tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL) -> pathlib.Path:
    """A scratch tree with one clean script in each of the four scopes."""
    fx = tmp_path / "fx"
    for rel in COPIED + (TWIN_ONLY if subject_rel.endswith(".sh") else ()):
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    repin(fx)
    if not subject_rel.endswith(".sh"):
        # THE SUBJECT IS A MEMBER OF THE CORPUS IT ENUMERATES. A bash subject is a `.sh` under `.ci`, so it was formatted by its own run, counted in its own floor and named in its own argv. A Python subject is not, so without a placeholder at that path the recorded argv and the recorded floor count would both be one short.
        write(fx / TWIN_REL, CLEAN_SH)
    write(fx / ".claude" / "two.sh", CLEAN_SH)
    write(fx / "run.sh", CLEAN_SH)
    write(fx / "scripts" / "dev" / "three.sh", CLEAN_SH)
    write(fx / "scripts" / "ops" / "four.sh", CLEAN_SH)

    write(fx / "fake" / "bin" / "curl", FAKE_CURL, mode=0o755)
    write(fx / "fake" / "tool" / "shfmt", FAKE_SHFMT, mode=0o755)

    kind = CASE_KW[name].get("tweak")
    if kind == "extra-claude-file":
        write(fx / ".claude" / "extra.sh", CLEAN_SH)
    elif kind == "drop-scripts":
        shutil.rmtree(fx / "scripts")
    elif kind is not None:
        raise AssertionError("no such tweak: %r" % kind)
    return fx


def normalise_calls(text: str, fx: pathlib.Path) -> list[str]:
    """One line per call, with each `shfmt` invocation's FILES sorted.

    See the module docstring: the flags keep their order and are compared exactly; only the file order inside one invocation is `find`'s to decide, and a recording is replayed against whichever `find` the host has.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.replace(str(fx) + "/", "").replace(str(fx), "<fx>")
        line = differential.mask_toolchain_tmp(line)
        if not line.startswith("FAKECALL shfmt "):
            out.append(line)
            continue
        words = line.split()
        rest = words[2:]
        cut = rest.index("-d") + 1 if "-d" in rest else 0
        out.append(" ".join([*words[:2], *rest[:cut], *sorted(rest[cut:])]))
    return out


def mask(text: str, fx: pathlib.Path) -> str:
    masked = text.replace(str(fx / "cache"), "<cache>").replace(str(fx), "<fx>")
    return differential.mask_toolchain_tmp(masked)


def drive(
    fx: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    """One subject, once, over an already-built tree."""
    kw = CASE_KW[name]
    log = fx / "calls.log"
    log.write_text("", encoding="utf-8")
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["FAKE_LOG"] = str(log)
    env["FAKE_VERSION"] = FIXTURE_VERSION
    # The fixture holds a handful of `.sh` files across the three floor roots, and the real floor of 200 would refuse every case before it started.
    env["SHFMT_MIN_FILES"] = "4"
    if not subject_rel.endswith(".sh"):
        env["PYTHONPATH"] = str(fx / ".ci")
    if kw.get("fake_tool", True):
        # The fake curl is on PATH even here, where nothing should download: a tree that stopped acquiring from PATH would otherwise reach the network.
        env["PATH"] = "%s%s%s%s%s" % (
            fx / "fake" / "tool",
            os.pathsep,
            fx / "fake" / "bin",
            os.pathsep,
            env["PATH"],
        )
    else:
        # An empty tool cache and NO tool anywhere, so acquisition has to reach curl and fail.
        env["CI_TEMP"] = str(fx / "cache")
        env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, "/usr/bin:/bin")
    env.update(kw.get("env") or {})
    runner = "bash" if subject_rel.endswith(".sh") else "python3"
    proc = subprocess.run(
        [runner, str(fx / subject_rel)],
        env=env,
        cwd=str(fx),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    calls = normalise_calls(log.read_text(encoding="utf-8"), fx)
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


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the tool calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_real_pin_or_a_host_path() -> None:
    """THE STABILITY CLAIM, checked over the corpus rather than argued in prose."""
    live = toolchain.pin_for("shfmt")
    assert live != FIXTURE_VERSION, "the fixture pin collided with the real one"
    for name in CASES:
        _code, stdout, stderr, calls = recorded(name)
        blob = "\n".join([stdout, stderr, *calls])
        assert live not in blob, name
        assert str(ROOT) not in blob, name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_clean_fixture_passes_and_names_every_scope() -> None:
    code, stdout, _, calls = recorded("a-clean-fixture")
    assert code == 0
    for scope in (
        "info: Checking .ci/**/*.sh",
        "info: Checking .claude/**/*.sh",
        "info: Checking ./run.sh",
        "info: Checking scripts/dev/**/*.sh",
        "info: Checking scripts/ops/**/*.sh",
        "success: Shell script formatting passed",
    ):
        assert scope in stdout, "missing %r in:\n%s" % (scope, stdout)
    assert len([c for c in calls if c.startswith("FAKECALL shfmt ")]) == 5, calls


def test_the_flags_are_passed_once_per_scope_and_in_order() -> None:
    """`-i 4 -ci -d`, as four argv entries rather than one string, on every invocation."""
    for line in recorded("a-clean-fixture")[3]:
        assert line.startswith("FAKECALL shfmt -i 4 -ci -d "), line


def test_the_run_sh_argument_keeps_its_leading_dot_slash() -> None:
    """`./run.sh`, not an absolute path: shfmt echoes it into the diff header."""
    assert any(line.endswith(" ./run.sh") for line in recorded("a-clean-fixture")[3]), recorded(
        "a-clean-fixture"
    )[3]


def test_a_dirty_file_in_claude_reports_the_diff_and_stops() -> None:
    code, stdout, _, _ = recorded("a-dirty-file-in-claude")
    assert code == 1
    assert "diff .claude/two.sh.orig .claude/two.sh" in stdout
    # The scopes AFTER .claude never ran; that is the `set -e` defect.
    assert "info: Checking ./run.sh" not in stdout


def test_a_dirty_run_sh_reports_the_diff_and_stops() -> None:
    code, stdout, _, _ = recorded("a-dirty-run-sh")
    assert code == 1
    assert "diff ./run.sh.orig ./run.sh" in stdout
    assert "info: Checking scripts/dev/**/*.sh" not in stdout


def test_a_dirty_scripts_ops_file_reports_the_diff() -> None:
    """The LAST scope, so this is the only case that proves the tail runs."""
    code, stdout, _, _ = recorded("a-dirty-scripts-ops-file")
    assert code == 1
    assert "diff scripts/ops/four.sh.orig scripts/ops/four.sh" in stdout
    assert "info: Checking scripts/dev/**/*.sh" in stdout
    assert "success:" not in stdout


def test_an_unparseable_file_puts_its_bytes_on_stderr() -> None:
    """The one fixture path with stderr content. A merged `2>&1` would hide it."""
    code, stdout, stderr, _ = recorded("an-unparseable-file")
    assert code == 1
    assert stderr.strip(), "the tool said nothing on stderr; the control did not fire"
    assert ".claude/two.sh" in stderr
    assert stdout.count("diff ") == 0


def test_the_first_failing_scope_aborts_the_rest() -> None:
    """THE DEFECT, recorded rather than mentioned: three scopes go unchecked.

    A dirty file in `.claude` AND a dirty file in `scripts/ops`; only the first is ever reported, and a reader who fixes it learns about the second on the next run.
    """
    code, stdout, _, _ = recorded("the-first-failing-scope-aborts-the-rest")
    assert code == 1
    assert "diff .claude/two.sh.orig" in stdout
    assert "scripts/ops/four.sh" not in stdout, "the abort defect is gone; rewrite this case"


def test_the_vacuity_floor_refuses_a_collapsed_corpus() -> None:
    """Zero inputs is a FAILURE, never a pass."""
    code, _, stderr, calls = recorded("the-vacuity-floor-refuses-a-collapsed-corpus")
    assert code == 1
    assert calls == [], "shfmt must not run once the floor refuses"
    assert "VACUOUS: found" in stderr
    assert "refusing to report formatting clean" in stderr


def test_the_floor_counts_the_three_roots_and_says_the_number(tmp_path: pathlib.Path) -> None:
    """The count in the refusal is the real one, not a placeholder.

    Counted here from the tree the case builds, so the number in the recording is checked against an independent enumeration rather than against itself.
    """
    name = "the-floor-counts-the-three-roots"
    fx = build(tmp_path, name)
    expected = port.shell_files(fx / ".ci")
    expected += port.shell_files(fx / ".claude")
    expected += port.shell_files(fx / "scripts")
    assert ("VACUOUS: found %d shell script(s), floor 9999." % len(expected)) in recorded(name)[2]


def test_a_missing_scripts_directory_is_skipped_not_fatal() -> None:
    code, stdout, _, _ = recorded("a-missing-scripts-directory")
    assert code == 0
    assert "info: Checking scripts/dev/**/*.sh" not in stdout


def test_an_unacquirable_shfmt_is_exit_77_not_a_verdict() -> None:
    """77 = CANNOT_RUN. exit 1 here would claim "shfmt found bad formatting"."""
    code, stdout, stderr, _ = recorded("an-unacquirable-shfmt")
    assert code == 77
    assert "shfmt is unusable for this gate -- CANNOT RUN, not a verdict" in stderr
    assert "toolchain: could not download shfmt from" in stderr
    assert "Every lane's toolchain:" in stdout, "the two hints go to STDOUT, like log_info"


def test_colour_is_on_off_a_tty_because_this_gate_never_tests_one() -> None:
    """NOT a tty test: `if [[ "${CI:-}" == "true" ]]` and nothing else.

    A developer redirecting this gate's stdout to a file GETS escape sequences. Recorded, so that "fixing" one side without the other reds here.
    """
    assert differential.escape_bytes(recorded("a-clean-fixture")[1]) > 0


def test_ci_true_disables_colour() -> None:
    assert differential.escape_bytes(recorded("ci-true-disables-colour")[1]) == 0


# --------------------------------------------------------------------------- The real formatter, live rather than frozen ---------------------------------------------------------------------------


def real_scope_hashes() -> dict[str, str]:
    """sha256 of every file the four scopes reach. A COLLAPSED corpus fails."""
    out: dict[str, str] = {}
    for rel in (".ci", ".claude", "scripts/dev", "scripts/ops"):
        for path in port.shell_files(ROOT / rel):
            out[path] = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    out["run.sh"] = hashlib.sha256((ROOT / "run.sh").read_bytes()).hexdigest()
    assert len(out) >= 150, "only %d shell files in the four scopes" % len(out)
    return out


def real_run() -> subprocess.CompletedProcess:
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(ROOT / ".ci")
    return subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def diff_blocks(text: str) -> tuple[list[str], list[str]]:
    """(the non-diff prologue lines, one string per `diff <a>.orig <b>` block)."""
    prologue: list[str] = []
    blocks: list[str] = []
    current: list[str] | None = None
    for line in text.split("\n"):
        if line.startswith("diff ") and ".orig " in line:
            if current is not None:
                blocks.append("\n".join(current).rstrip("\n"))
            current = [line]
        elif current is None:
            prologue.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current).rstrip("\n"))
    return prologue, blocks


def block_files(blocks: list[str]) -> list[str]:
    """The path each block is about, in the order the blocks appeared."""
    return [b.split("\n", 1)[0].split()[1].removesuffix(".orig") for b in blocks]


def test_the_real_repository_is_read_only_and_reports_a_real_verdict() -> None:
    """The whole tree, the real pinned shfmt, and a read-only guard. NOT FROZEN, and the module docstring says why."""
    before = real_scope_hashes()
    proc = real_run()
    _prologue, blocks = diff_blocks(proc.stdout)
    if blocks:
        assert proc.returncode != 0
    else:
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
        assert "success: Shell script formatting passed" in proc.stdout
        for scope in (".ci/**/*.sh", ".claude/**/*.sh", "./run.sh", "scripts/dev/**/*.sh"):
            assert ("info: Checking %s" % scope) in proc.stdout, "scope %s never ran" % scope
    assert real_scope_hashes() == before, "a real run mutated a shell script"


def test_the_ports_order_is_byte_order() -> None:
    """ATTRIBUTION, halved by the deletion and stated as such.

    The differential proved two things: the twin's diff blocks followed the ambient `find` and the port's follow byte order. Only the second survives the twin, and it is kept together with the fact that makes it a choice rather than a coincidence: the ambient find is NOT sorted.
    """
    found = subprocess.run(
        ["find", ".ci", "-name", "*.sh", "-type", "f"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(ROOT),
        env=differential.env_for(),
    ).stdout.split()
    assert found != sorted(found), (
        "the ambient find IS sorted here, so the port's sortedness proves nothing on this host"
    )
    _prologue, blocks = diff_blocks(real_run().stdout)
    if not blocks:
        return
    files = block_files(blocks)
    assert files == sorted(files), "the port's block order is not byte order"


def test_the_real_dirty_file_reaches_stdout_unaltered(tmp_path: pathlib.Path) -> None:
    """THE REAL FORMATTER, LIVE. The frozen cases use a scripted fake, so this is what keeps the claim that shfmt's own bytes are relayed rather than reformatted.

    Shape rather than bytes: the header naming the file, a real hunk marker, exit 1, and the scopes after the failing one absent.
    """
    fx = build(tmp_path, "a-clean-fixture")
    # THE REAL PIN GOES BACK, because this is the one case that wants the real tool: `build` gives every tree the fixture's own pin so no recording can carry the live one, and acquisition at a version that does not exist is exit 77 rather than a verdict.
    env_file = fx / ".devcontainer" / "toolchain.env"
    env_file.write_text(
        env_file.read_text(encoding="utf-8").replace(
            "SHFMT_VERSION=%s" % FIXTURE_VERSION, "SHFMT_VERSION=%s" % toolchain.pin_for("shfmt")
        ),
        encoding="utf-8",
    )
    write(fx / ".claude" / "two.sh", DIRTY_SH)
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(fx / ".ci")
    env["SHFMT_MIN_FILES"] = "4"
    proc = subprocess.run(
        ["python3", str(fx / PORT_REL)],
        env=env,
        cwd=str(fx),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "diff .claude/two.sh.orig .claude/two.sh" in proc.stdout
    assert "@@" in proc.stdout, "no hunk marker; the real formatter did not produce a diff"
    assert "info: Checking ./run.sh" not in proc.stdout


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_shell_files_is_sorted_and_finds_the_nested_ones() -> None:
    """The paths carry the ROOT they were asked about; `main` asks relatively."""
    found = port.shell_files(ROOT / ".ci")
    assert found == sorted(found)
    assert len(found) >= 100, "only %d .sh under .ci" % len(found)
    assert str(ROOT / ".ci/bootstrap.sh") in found
    assert all(f.endswith(".sh") for f in found)


def test_shell_files_agrees_with_the_ambient_find_as_a_set() -> None:
    """Different ORDER, same SET. The whole divergence in one assertion."""
    for rel in (".ci", ".claude"):
        found = subprocess.run(
            ["find", rel, "-name", "*.sh", "-type", "f", "-not", "-path", ".claude/worktrees/*"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(ROOT),
            env=differential.env_for(),
        ).stdout.split()
        assert found != sorted(found), (
            "the ambient find IS sorted for %s, so this comparison proves nothing "
            "about order; the attribution case above is the one that matters" % rel
        )
        assert sorted(str(ROOT / f) for f in found) == port.shell_files(ROOT / rel), rel


def test_shell_files_does_not_follow_a_symlinked_directory(tmp_path: pathlib.Path) -> None:
    """`find -P` and `-type f`, both directions."""
    real = tmp_path / "real"
    write(real / "a.sh", "")
    inside = tmp_path / "tree"
    inside.mkdir()
    write(inside / "b.sh", "")
    (inside / "link").symlink_to(real, target_is_directory=True)
    (inside / "c.sh").symlink_to(real / "a.sh")
    assert port.shell_files(inside) == [str(inside / "b.sh")]


def test_the_scope_list_and_flags_are_the_twins() -> None:
    """The twin's literals are gone from the tree, so what is asserted is that the port still carries them and that the RECORDED argv agrees with the flags it claims."""
    assert port.SHFMT_OPTS == ("-i", "4", "-ci", "-d")
    assert port.OPTIONAL_SCOPES == ("scripts/dev", "scripts/ops")
    assert port.DEFAULT_MIN_FILES == "200"
    assert port.FLOOR_ROOTS == (".ci", ".claude", "scripts")
    first = recorded("a-clean-fixture")[3][0]
    assert first.startswith("FAKECALL shfmt %s " % " ".join(port.SHFMT_OPTS)), first


def test_colours_reads_ci_at_the_call_site(monkeypatch) -> None:
    """No captured `env` alias; the value is read when it is needed."""
    monkeypatch.delenv("CI", raising=False)
    assert port.colours() == (port.RED, port.GREEN, port.NC)
    monkeypatch.setenv("CI", "true")
    assert port.colours() == ("", "", "")
    monkeypatch.setenv("CI", "1")
    assert port.colours() == (port.RED, port.GREEN, port.NC), "only the exact string 'true'"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_narrowing_of_the_claude_scope_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Format `.claude/hooks` instead of `.claude`.

    The whole `.claude` tree has been in scope since 2026-08-15, when a helper under `.claude/lib` passed both shell gates while carrying a blatant SC2086 because neither gate was looking at it. A mutant that narrows the scope back to `.claude/hooks` still prints `info: Checking .claude/**/*.sh` and still exits 0 over this fixture, because the fixture's `.claude/two.sh` simply
    stops being passed to the formatter. Only `--- calls ---` sees the file disappear from the argv.

    THE MUTANT LIVES AT THE PORT'S OWN PATH INSIDE THE SCRATCH TREE, because the subject resolves its root from its own location; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '    rc = check_scope(binary, ".claude")\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, '    rc = check_scope(binary, ".claude/hooks")\n')

    name = "a-clean-fixture"
    want = recorded(name)
    fx = build(tmp_path / "planted", name)
    (fx / PORT_REL).write_text(mutated, encoding="utf-8")
    got = drive(fx, name)

    assert any(".claude/two.sh" in line for line in want[3]), "the recorded corpus moved"
    assert not any(".claude/two.sh" in line for line in got[3]), (
        "the plant did not narrow the scope"
    )
    assert got[:3] == want[:3], "only the recorded argv may differ, and it is what catches this"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
