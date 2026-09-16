"""Differential: `rediacc_ci.security.shfmt` against its twin
`.ci/scripts/security/shfmt.sh`.

TWO KINDS OF CASE.

  A REAL RUN against this repository's own 570-odd shell scripts with the REAL
  pinned shfmt. `-d` is diff mode and reads only; the case hashes every file in
  all four scopes before and after and refuses a byte of drift. No fixture
  reproduces 38 simultaneous diffs across four scopes, and that is the input
  that makes the comparison mean something.

  FIXTURE RUNS in a scratch tree holding both implementations, with a RECORDING
  FAKE `shfmt` on a scratch PATH for the argv cases and the REAL pinned shfmt
  (through the same `toolchain_acquire` both sides call) for the output cases.

WHAT IS COMPARED, AND THE ONE THING THAT IS NOT.

  Byte for byte: the exit code, stderr, and stdout.

  NOT byte for byte: the ORDER of the file arguments inside one `shfmt`
  invocation, and therefore the order of the per-file diff blocks in stdout when
  more than one file differs. That order is not the twin's property at all -- it
  is whatever `find` hands it, and POSIX leaves find's traversal order
  unspecified. This host does not even run GNU findutils:

      $ find --version | head -1
      bfs 4.1.1

  `bfs` is breadth-first; GNU findutils, which is what `ubuntu-latest` runs, is
  depth-first pre-order. Over `.ci` alone they emit the same 300-odd files in a
  visibly different sequence. So `test_the_twins_order_is_the_ambient_finds_and_
  the_ports_is_sorted` ATTRIBUTES the difference by deriving both orders
  independently, and every other case compares the file arguments as a sorted
  list while still comparing everything else in order.

  Where a fixture scope holds ONE file the argv is compared with no sorting at
  all, because there is nothing for an ordering to disagree about; that is
  asserted rather than assumed, in `assert_logs`.

K=5 LEDGER: `.ci/shadow/w7p6-shfmt.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.security import shfmt as port
from rediacc_ci.tests import differential

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/shfmt.sh"
PORT_REL = ".ci/rediacc_ci/security/shfmt.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

# The minimum of the package a path-invoked port needs. `core/toolchain.py` is
# the shared acquisition path both sides go through, so its bash original comes
# too.
COPIED = (
    TWIN_REL,
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

# shfmt-CLEAN, at `-i 4 -ci`. Every fixture scope gets one of these so that a
# case can introduce exactly one dirty file and know the diff came from it.
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

# Two-space indent where the formatter wants four, plus an un-indented case arm.
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

# Not shell at all. shfmt writes a parse error to STDERR and exits non-zero,
# which is the only fixture path that puts anything on stderr.
UNPARSEABLE_SH = "#!/bin/bash\nif then fi\n"

FAKE_SHFMT = """#!/bin/bash
if [[ "$1" == "--version" ]]; then
    printf 'v%s\\n' "$FAKE_VERSION"
    exit 0
fi
printf 'FAKECALL shfmt %s\\n' "$*" >>"$FAKE_LOG"
exit 0
"""

# Silent on failure; see the module docstring of shfmt.py for why a talking fake
# would break the differential for a reason that is not the port's.
FAKE_CURL = """#!/bin/bash
printf 'FAKECALL curl %s\\n' "$*" >>"$FAKE_LOG"
exit 22
"""


def _write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def pin() -> str:
    return toolchain.pin_for("shfmt")


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch repository with one clean script in each of the four scopes."""
    fx = tmp_path / "fx"
    for rel in COPIED:
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    _write(fx / ".claude" / "two.sh", CLEAN_SH)
    _write(fx / "run.sh", CLEAN_SH)
    _write(fx / "scripts" / "dev" / "three.sh", CLEAN_SH)
    _write(fx / "scripts" / "docker" / "four.sh", CLEAN_SH)

    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    _write(bindir / "curl", FAKE_CURL, mode=0o755)
    return fx


def _env(fx: pathlib.Path, side: str, log: pathlib.Path, **extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`.

    `SHFMT_MIN_FILES=4` by default: the fixture holds exactly four `.sh` files
    across `.ci`, `.claude` and `scripts` once the two copied infrastructure
    scripts and `constants.sh` are counted, and the real floor of 200 would
    refuse every case before it started.
    """
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["FAKE_LOG"] = str(log)
    env["FAKE_VERSION"] = pin()
    env["SHFMT_MIN_FILES"] = "4"
    if side == "new":
        env["PYTHONPATH"] = str(fx / ".ci")
    env.update(extra)
    return env


def run_both(
    fx: pathlib.Path, *, fake_tool: bool = False, scratch_cache: bool = False, **extra: str
) -> tuple:
    """Both implementations, same fixture. Returns results AND call logs.

    `fake_tool` puts a recording `shfmt` at the pin on PATH so the argv is
    observable. Otherwise both sides reach the REAL pinned binary through the
    same `toolchain_acquire`, which is the shared code path a cutover would use.
    """
    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / PORT_REL)]),
    ):
        log = fx / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        env = _env(fx, side, log, **extra)
        if fake_tool:
            bindir = fx / "fake" / ("bin-%s" % side)
            bindir.mkdir(parents=True, exist_ok=True)
            _write(bindir / "shfmt", FAKE_SHFMT, mode=0o755)
            env["PATH"] = "%s%s%s" % (bindir, os.pathsep, env["PATH"])
        if scratch_cache:
            # An empty tool cache and NO `go`, so acquisition has to reach curl.
            env["CI_TEMP"] = str(fx / "cache" / side)
            env["PATH"] = "%s%s%s" % (
                fx / "fake" / "bin",
                os.pathsep,
                "/usr/bin:/bin",
            )
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(fx),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

        def _mask(text: str, side: str = side) -> str:
            return text.replace(str(fx / "cache" / side), "<cache>").replace(str(fx), "<fx>")

        results.append((proc.returncode, _mask(proc.stdout), _mask(proc.stderr)))
        logs.append(_mask(log.read_text(encoding="utf-8")).splitlines())
    return results[0], results[1], logs[0], logs[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def split_call(line: str) -> tuple[list[str], list[str]]:
    """One `FAKECALL shfmt ...` line as (flags, files). Flags keep their order."""
    words = line.split()
    assert words[:2] == ["FAKECALL", "shfmt"], line
    rest = words[2:]
    flags = rest[: rest.index("-d") + 1] if "-d" in rest else []
    return flags, rest[len(flags) :]


def assert_logs(old_log: list[str], new_log: list[str]) -> None:
    """Same invocations, same flags in order, same file SET per invocation.

    THE SORT IS SCOPED AS TIGHTLY AS IT CAN BE. A single-file invocation is
    compared with no sorting at all, so the only thing this ever forgives is the
    relative order of two files inside one scope, which is `find`'s to decide.

    Non-shfmt lines (the `curl` fake's) are compared BYTE FOR BYTE first: there
    is no ordering question in an acquisition, and forgiving one there would be
    forgiveness this file has no reason to extend.
    """
    old_other = [line for line in old_log if not line.startswith("FAKECALL shfmt ")]
    new_other = [line for line in new_log if not line.startswith("FAKECALL shfmt ")]
    assert new_other == old_other, "non-shfmt calls:\n%s\n--\n%s" % (old_other, new_other)
    old_log = [line for line in old_log if line.startswith("FAKECALL shfmt ")]
    new_log = [line for line in new_log if line.startswith("FAKECALL shfmt ")]
    assert len(new_log) == len(old_log), "invocation count:\n%s\n--\n%s" % (old_log, new_log)
    for old_line, new_line in zip(old_log, new_log, strict=True):
        old_flags, old_files = split_call(old_line)
        new_flags, new_files = split_call(new_line)
        assert new_flags == old_flags, "flags differ: %r vs %r" % (old_flags, new_flags)
        if len(old_files) <= 1:
            assert new_line == old_line, "single-file argv differs:\n%s\n%s" % (old_line, new_line)
            continue
        assert sorted(new_files) == sorted(old_files), "file set:\n%s\n--\n%s" % (
            old_line,
            new_line,
        )


def assert_agree(fx: pathlib.Path, **kwargs: object) -> tuple:
    old, new, old_log, new_log = run_both(fx, **kwargs)  # type: ignore[arg-type]
    assert_logs(old_log, new_log)
    assert_same(old, new)
    return old


# ---------------------------------------------------------------------------
# Diff-block plumbing, used by the real-run case
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# The real run
# ---------------------------------------------------------------------------


def real_scope_hashes() -> dict[str, str]:
    """sha256 of every file the four scopes reach. A COLLAPSED corpus fails."""
    out: dict[str, str] = {}
    for rel in (".ci", ".claude", "scripts/dev", "scripts/docker"):
        for path in port.shell_files(ROOT / rel):
            out[path] = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    out["run.sh"] = hashlib.sha256((ROOT / "run.sh").read_bytes()).hexdigest()
    assert len(out) > 300, "only %d shell files in the four scopes" % len(out)
    return out


@pytest.fixture(scope="session", autouse=True)
def _warm_shfmt_once() -> None:
    """Warm the shared shfmt cache ONCE per worker, before any case in this file.

    IT WAS NOT ENOUGH TO WARM ONLY `_run_real`. The fixture cases share the same
    on-disk cache (`_env` sets CI_TEMP only for the scratch-cache case), so the
    ordering artifact is not a property of the real-tree path -- it is a property
    of whichever case reaches a COLD cache first. Under `--dist loadgroup` that
    is a different case on a different worker from run to run, which is why
    `test_a_dirty_file_in_claude_reports_the_same_diff` failed in CI job
    104583449222 while the real-tree case, already warmed by `_run_real`, passed.
    Warming inside one code path fixed one case and left its siblings racing.

    Session-scoped and autouse, so it runs before the first case in this module
    on each worker; the cache is shared on disk, so the first worker pays and the
    rest are a no-op.
    """
    _warm_shfmt()


def _warm_shfmt() -> None:
    """Acquire shfmt into the cache the SUBJECTS use, before either is measured.

    WITHOUT THIS THE REAL-TREE CASE MEASURES RUN ORDER. `_run_real` runs the twin
    first and the port second into a cache they SHARE
    (`${CI_TEMP:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}}/rediacc-toolchain/shfmt-<v>`,
    toolchain.sh:258). Whoever runs first pays for acquisition and says so on
    stderr; the second finds it cached and is silent.

    That stayed invisible while acquisition simply FAILED in this lane -- both
    sides returned exit 77 and agreed about it. `b3a53cb06` made a failed
    `go install` fall back to the download, so acquisition now SUCCEEDS, and the
    twin started emitting `toolchain: go install shfmt@v3.13.1 failed` (its
    first, honest attempt) where the port, running second into a warm cache,
    emitted nothing. Measured in run 35009582358: `assert '' == 'toolchain: g...
    13.1 failed\n'`. Fixing acquisition PROMOTED an ordering artifact that had
    been hidden behind a shared failure -- errors stack.

    Warmed by running a SUBJECT under the same env rather than by calling the
    library in-process, because the cache path depends on the environment and an
    in-process call would resolve it against pytest's rather than the subjects'.
    """
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(ROOT / ".ci")
    subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _run_real() -> tuple[tuple, tuple]:
    _warm_shfmt()
    results = []
    for side, argv in (("old", ["bash", str(TWIN)]), ("new", ["python3", str(PORT)])):
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def test_the_real_repository_agrees_on_every_channel_but_block_order() -> None:
    """The whole tree, the real shfmt, both streams, and a read-only guard."""
    before = real_scope_hashes()
    old, new = _run_real()
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])
    old_pro, old_blocks = diff_blocks(old[1])
    new_pro, new_blocks = diff_blocks(new[1])
    assert new_pro == old_pro, "prologue:\n%s\n--\n%s" % (old_pro, new_pro)
    assert sorted(new_blocks) == sorted(old_blocks), "diff blocks disagree in CONTENT"
    assert _real_run_is_non_trivial(old, old_blocks)
    assert real_scope_hashes() == before, "a real run mutated a shell script"


def _real_run_is_non_trivial(old: tuple, blocks: list[str]) -> bool:
    """The anti-vacuity assertion for the case above, spelled out.

    A green over a tree with no formatting findings would compare two empty
    block lists and prove nothing about ordering, batching or diff rendering.
    The tree normally carries several sessions' work and is rarely clean, but
    "rarely" is not "never", so the two shapes are separated here: with findings
    the block count must be real, and without them the prologue must show all
    four scopes ran, which is the only other thing there is to check.
    """
    if blocks:
        assert len(blocks) >= 2, "only %d diff block(s); ordering is untested" % len(blocks)
        assert old[0] != 0
        return True
    assert old[0] == 0
    assert "success: Shell script formatting passed" in old[1]
    for scope in (".ci/**/*.sh", ".claude/**/*.sh", "./run.sh", "scripts/dev/**/*.sh"):
        assert ("info: Checking %s" % scope) in old[1], "scope %s never ran" % scope
    return True


def test_the_twins_order_is_the_ambient_finds_and_the_ports_is_sorted() -> None:
    """ATTRIBUTION, not a shrug. The residual difference belongs to `find`.

    Derives the ambient `find`'s order independently, then shows the twin's diff
    blocks follow it and the port's follow byte order. If a future host runs a
    `find` whose order IS sorted, both claims still hold and the two block
    sequences become equal, which is the outcome this case would happily record.
    """
    old, new = _run_real()
    _pro, old_blocks = diff_blocks(old[1])
    _pro, new_blocks = diff_blocks(new[1])
    if not old_blocks:
        # A CLEAN TREE IS A RESULT, NOT AN ABSENCE, and this used to `pytest.skip`
        # here. That made the gate above this file RED WHENEVER THE TREE WAS
        # CLEAN: `check:ci-pytest` refuses `passed != collected` on purpose,
        # because a skipped test is not a passing one, so the healthiest possible
        # state of the tree was the one state in which this case stopped counting.
        # The attribution claim genuinely has nothing to bite on with no diff
        # blocks -- but the DIFFERENTIAL still does, and it is the stronger half:
        # the two implementations must agree that there is nothing to report.
        # This arm fails if either side invents a finding the other does not see.
        assert new_blocks == [], (
            "the tree is shfmt-clean for the twin and NOT for the port; the port "
            "invented %d diff block(s):\n%s" % (len(new_blocks), new[1])
        )
        assert old[0] == 0, "clean tree, twin exited %s:\n%s" % (old[0], old[1])
        assert new[0] == 0, "clean tree, port exited %s:\n%s" % (new[0], new[1])
        assert "success: Shell script formatting passed" in old[1]
        assert "success: Shell script formatting passed" in new[1]
        return

    found = subprocess.run(
        ["find", ".ci", "-name", "*.sh", "-type", "f"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(ROOT),
        env=differential.env_for(),
    ).stdout.split()
    rank = {path: i for i, path in enumerate(found)}
    twin_files = block_files(old_blocks)
    # Only the `.ci` scope runs when it has findings; `set -e` ends the script
    # there. That is the twin's own defect, reproduced, and it is what makes the
    # comparison against a single `find .ci` legitimate.
    assert all(f.startswith(".ci/") for f in twin_files), twin_files
    assert all(f in rank for f in twin_files), "a diff names a file find did not"
    assert [rank[f] for f in twin_files] == sorted(rank[f] for f in twin_files), (
        "the twin's block order is NOT the ambient find's order; the attribution "
        "in this file's docstring is wrong"
    )
    port_files = block_files(new_blocks)
    assert port_files == sorted(port_files), "the port's block order is not byte order"


# ---------------------------------------------------------------------------
# Fixture runs
# ---------------------------------------------------------------------------


def test_a_clean_fixture_passes_and_names_every_scope(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture, fake_tool=True)
    assert old[0] == 0
    for scope in (
        "info: Checking .ci/**/*.sh",
        "info: Checking .claude/**/*.sh",
        "info: Checking ./run.sh",
        "info: Checking scripts/dev/**/*.sh",
        "info: Checking scripts/docker/**/*.sh",
        "success: Shell script formatting passed",
    ):
        assert scope in old[1], "missing %r in:\n%s" % (scope, old[1])


def test_the_run_sh_argument_keeps_its_leading_dot_slash(fixture: pathlib.Path) -> None:
    """`./run.sh`, not an absolute path: shfmt echoes it into the diff header."""
    _old, _new, old_log, new_log = run_both(fixture, fake_tool=True)
    assert_logs(old_log, new_log)
    assert any(line.endswith(" ./run.sh") for line in old_log), old_log
    assert any(line.endswith(" ./run.sh") for line in new_log), new_log


def test_a_dirty_file_in_claude_reports_the_same_diff(fixture: pathlib.Path) -> None:
    """The REAL shfmt, one dirty file, byte for byte on stdout."""
    _write(fixture / ".claude" / "two.sh", DIRTY_SH)
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "diff .claude/two.sh.orig .claude/two.sh" in old[1]
    # The scopes AFTER .claude never ran; that is the twin's `set -e` defect.
    assert "info: Checking ./run.sh" not in old[1]


def test_a_dirty_run_sh_reports_the_same_diff(fixture: pathlib.Path) -> None:
    _write(fixture / "run.sh", DIRTY_SH)
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "diff ./run.sh.orig ./run.sh" in old[1]
    assert "info: Checking scripts/dev/**/*.sh" not in old[1]


def test_a_dirty_scripts_docker_file_reports_the_same_diff(fixture: pathlib.Path) -> None:
    """The LAST scope, so this is the only case that proves the tail runs."""
    _write(fixture / "scripts" / "docker" / "four.sh", DIRTY_SH)
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "diff scripts/docker/four.sh.orig scripts/docker/four.sh" in old[1]
    assert "info: Checking scripts/dev/**/*.sh" in old[1]
    assert "success:" not in old[1]


def test_an_unparseable_file_puts_the_same_bytes_on_stderr(fixture: pathlib.Path) -> None:
    """The one fixture path with stderr content. A merged `2>&1` would hide it."""
    _write(fixture / ".claude" / "two.sh", UNPARSEABLE_SH)
    old = assert_agree(fixture)
    assert old[0] == 1
    assert old[2].strip(), "shfmt said nothing on stderr; the control did not fire"
    assert ".claude/two.sh" in old[2]
    assert old[1].count("diff ") == 0


def test_the_first_failing_scope_aborts_the_rest(fixture: pathlib.Path) -> None:
    """THE DEFECT, asserted rather than mentioned: three scopes go unchecked.

    A dirty file in `.claude` AND a dirty file in `scripts/docker`; only the
    first is ever reported, and a reader who fixes it learns about the second on
    the next run.
    """
    _write(fixture / ".claude" / "two.sh", DIRTY_SH)
    _write(fixture / "scripts" / "docker" / "four.sh", DIRTY_SH)
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "diff .claude/two.sh.orig" in old[1]
    assert "scripts/docker/four.sh" not in old[1], "the abort defect is gone; rewrite this case"


def test_the_vacuity_floor_refuses_a_collapsed_corpus(fixture: pathlib.Path) -> None:
    """Zero inputs is a FAILURE, never a pass. Both sides, same two lines."""
    old, new, old_log, new_log = run_both(fixture, fake_tool=True, SHFMT_MIN_FILES="9999")
    assert old[0] == 1
    assert new_log == old_log == [], "shfmt must not run once the floor refuses"
    assert_same(old, new)
    assert "VACUOUS: found" in old[2]
    assert "refusing to report formatting clean" in old[2]


def test_the_floor_counts_the_three_roots_and_says_the_number(fixture: pathlib.Path) -> None:
    """The count in the refusal is the real one, not a placeholder."""
    _write(fixture / ".claude" / "extra.sh", CLEAN_SH)
    old, _new, _ol, _nl = run_both(fixture, fake_tool=True, SHFMT_MIN_FILES="9999")
    expected = port.shell_files(fixture / ".ci")
    expected += port.shell_files(fixture / ".claude")
    expected += port.shell_files(fixture / "scripts")
    assert ("VACUOUS: found %d shell script(s), floor 9999." % len(expected)) in old[2]


def test_a_missing_scripts_directory_is_skipped_not_fatal(fixture: pathlib.Path) -> None:
    shutil.rmtree(fixture / "scripts")
    old = assert_agree(fixture, fake_tool=True, SHFMT_MIN_FILES="2")
    assert old[0] == 0
    assert "info: Checking scripts/dev/**/*.sh" not in old[1]


def test_an_unacquirable_shfmt_is_exit_77_not_a_verdict(fixture: pathlib.Path) -> None:
    """77 = CANNOT_RUN. exit 1 here would claim "shfmt found bad formatting"."""
    old = assert_agree(fixture, scratch_cache=True)
    assert old[0] == 77
    assert "shfmt is unusable for this gate -- CANNOT RUN, not a verdict" in old[2]
    assert "toolchain: could not download shfmt from" in old[2]
    assert "Every lane's toolchain:" in old[1], "the two hints go to STDOUT, like log_info"


# ---------------------------------------------------------------------------
# Colour, which this twin decides differently from common.sh
# ---------------------------------------------------------------------------


def test_colour_is_on_off_a_tty_because_this_twin_never_tests_one(
    fixture: pathlib.Path,
) -> None:
    """NOT a tty test: `if [[ "${CI:-}" == "true" ]]` and nothing else.

    Both directions, and the point is that a developer redirecting this gate's
    stdout to a file GETS escape sequences. Reproduced, and asserted so that
    "fixing" one side without the other reds here.
    """
    old, new, _ol, _nl = run_both(fixture, fake_tool=True)
    assert differential.escape_bytes(old[1]) > 0, "the twin stopped colouring off a tty"
    assert_same(old, new)


def test_ci_true_disables_colour_on_both_sides(fixture: pathlib.Path) -> None:
    old, new, _ol, _nl = run_both(fixture, fake_tool=True, CI="true")
    assert differential.escape_bytes(old[1]) == 0
    assert differential.escape_bytes(new[1]) == 0
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------


def test_shell_files_is_sorted_and_finds_the_nested_ones() -> None:
    """The paths carry the ROOT they were asked about; `main` asks relatively."""
    found = port.shell_files(ROOT / ".ci")
    assert found == sorted(found)
    assert len(found) > 200, "only %d .sh under .ci" % len(found)
    assert str(ROOT / ".ci/scripts/security/shfmt.sh") in found
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
    _write(real / "a.sh", "")
    inside = tmp_path / "tree"
    inside.mkdir()
    _write(inside / "b.sh", "")
    (inside / "link").symlink_to(real, target_is_directory=True)
    (inside / "c.sh").symlink_to(real / "a.sh")
    assert port.shell_files(inside) == [str(inside / "b.sh")]


def test_the_scope_list_and_flags_are_the_twins() -> None:
    """A silent widening of a scope, or a dropped flag, reds here."""
    twin = TWIN.read_text(encoding="utf-8")
    assert 'SHFMT_OPTS="-i 4 -ci -d"' in twin
    assert port.SHFMT_OPTS == ("-i", "4", "-ci", "-d")
    assert "for dir in scripts/dev scripts/docker; do" in twin
    assert port.OPTIONAL_SCOPES == ("scripts/dev", "scripts/docker")
    assert 'MIN_SHELL_FILES="${SHFMT_MIN_FILES:-200}"' in twin
    assert port.DEFAULT_MIN_FILES == "200"
    assert 'find .ci .claude scripts -name "*.sh" -type f' in twin
    assert port.FLOOR_ROOTS == (".ci", ".claude", "scripts")


def test_colours_reads_ci_at_the_call_site(monkeypatch) -> None:
    """No captured `env` alias; the value is read when it is needed."""
    monkeypatch.delenv("CI", raising=False)
    assert port.colours() == (port.RED, port.GREEN, port.NC)
    monkeypatch.setenv("CI", "true")
    assert port.colours() == ("", "", "")
    monkeypatch.setenv("CI", "1")
    assert port.colours() == (port.RED, port.GREEN, port.NC), "only the exact string 'true'"
