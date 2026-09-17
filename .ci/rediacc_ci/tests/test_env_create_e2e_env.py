"""`rediacc_ci.env.create_e2e_env` against its bash twin.

THE FILE IS THE SUBJECT, NOT THE MESSAGES. This program prints three lines, all progress, all on stderr; its product is the `.env` file. So `run_both` returns the generated FILE alongside the two streams and the exit code, and every case compares all four. A differential here that only read stdout and stderr would pass while the port wrote a completely different file, which is the
exact shape of blindness `scripts/lib/shadow-gate.ts` was built to refuse.

EVERY CASE WRITES INTO `tmp_path`, NEVER INTO THE CHECKOUT, and one case makes that non-negotiable: `--output` with no value resolves to the literal string `true` and creates a file with that name in the CURRENT DIRECTORY (Defect C in the port's docstring). Driving it from the repository root leaves an untracked `true` behind, which is what happened while this port was being
written. `assert_is_scratch` re-derives the working directory before the two sides run, so a bug in a fixture cannot point a writing differential at the real tree.

WHAT IS NORMALISED, AND WHAT DELIBERATELY IS NOT. Two things differ between the sides by construction: the OUTPUT PATH (each side writes its own file, so the two must not collide) and the PROGRAM NAME inside bash's own `<prog>: line <N>:` diagnostics. Both are replaced by placeholders. The LINE NUMBERS are compared, and
`test_the_pinned_twin_line_numbers_still_point_at_the_right_lines` re-derives them from the twin, because a drifting line number is precisely the silent divergence pinning exists to catch.

The K=5 ledger is `.ci/shadow/w7p6-create-e2e-env.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-create-e2e-env --assert --k 5`).
"""

from __future__ import annotations

import os
import pathlib
import re
import shlex
import subprocess

import pytest

from rediacc_ci.core import bash_dialect
from rediacc_ci.env import create_e2e_env as port
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/env/create-e2e-env.sh"
COMMON = ".ci/scripts/lib/common.sh"
MODULE = "rediacc_ci.env.create_e2e_env"

# `<anything>: line <N>: ` -- bash naming itself. The name differs between a `.sh` and a module; the number does not and is compared.
_PROG = re.compile(r"^\S+: line ", re.MULTILINE)


class Run:
    """One side's four observable results."""

    def __init__(self, code: int, stdout: str, stderr: str, produced: str | None) -> None:
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.produced = produced

    def normalised(self, output: pathlib.Path) -> tuple[int, str, str, str | None]:
        def clean(text: str) -> str:
            return _PROG.sub("<prog>: line ", text.replace(str(output), "<out>"))

        return self.code, clean(self.stdout), clean(self.stderr), self.produced

    def __repr__(self) -> str:
        return "Run(code=%r, stdout=%r, stderr=%r)" % (self.code, self.stdout, self.stderr)


def assert_is_scratch(workdir: pathlib.Path) -> None:
    """Refuse to run a WRITING differential anywhere but the disposable tree."""
    resolved = str(workdir.resolve())
    assert resolved != diff.repo(), "refusing to write into the real checkout"
    assert not resolved.startswith(diff.repo() + os.sep), (
        "working directory %r is inside the checkout" % resolved
    )


def run_both(
    tmp_path: pathlib.Path,
    args: tuple[str, ...] = (),
    *,
    workdir: pathlib.Path | None = None,
    env_extra: dict[str, str | None] | None = None,
    tty: str | None = None,
) -> tuple[Run, Run]:
    """Drive both implementations. `{out}` in `args` becomes each side's own path.

    The two sides get DIFFERENT output paths on purpose: a shared path would let the second run overwrite the first and every file comparison would pass by accident, comparing one file with itself.
    """
    cwd = workdir if workdir is not None else tmp_path / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    assert_is_scratch(cwd)

    # DELETED FIRST, ALWAYS. A test that calls this twice would otherwise read the PREVIOUS call's file when the current one refuses to write, and two stale files compare equal -- a differential passing on evidence from a run it is not describing. Caught here: the Defect A case below drove exactly that and reported an over-budget refusal as having produced a file.
    runs: list[Run] = []
    for side, invocation in (
        ("old", "bash %s/%s" % (diff.repo(), TWIN)),
        ("new", "python3 -m %s" % MODULE),
    ):
        output = tmp_path / ("%s.env" % side)
        output.unlink(missing_ok=True)
        quoted = " ".join(shlex.quote(a.replace("{out}", str(output))) for a in args)
        env: dict[str, str | None] = dict(env_extra or {})
        if side == "new":
            env["PYTHONPATH"] = "%s/.ci" % diff.repo()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        code, stdout, stderr = diff.bash_streams(
            "%s %s" % (invocation, quoted),
            env=diff.env_for(**env),
            cwd=str(cwd),
            tty=tty,
            timeout=30,
        )
        produced = output.read_text(encoding="utf-8") if output.exists() else None
        runs.append(Run(code, stdout, stderr, produced))

    old, new = runs
    return old, new


def assert_equivalent(tmp_path: pathlib.Path, old: Run, new: Run) -> None:
    assert old.normalised(tmp_path / "old.env") == new.normalised(tmp_path / "new.env")


def both(tmp_path: pathlib.Path, *args: str, **kwargs: object) -> tuple[Run, Run]:
    old, new = run_both(tmp_path, args, **kwargs)  # type: ignore[arg-type]
    assert_equivalent(tmp_path, old, new)
    return old, new


# --------------------------------------------------------------------------- The documented flags, one case per line of the twin's own header ---------------------------------------------------------------------------

DOCUMENTED_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("defaults", ("--output", "{out}")),
    ("equals-form", ("--output={out}",)),
    ("vm-net-base", ("--output", "{out}", "--vm-net-base", "192.168.112")),
    ("vm-net-offset", ("--output", "{out}", "--vm-net-offset", "1")),
    ("vm-control", ("--output", "{out}", "--vm-control", "5")),
    ("vm-bridge-alias", ("--output", "{out}", "--vm-bridge", "7")),
    ("control-wins-over-bridge", ("--output", "{out}", "--vm-control", "5", "--vm-bridge", "7")),
    ("vm-workers", ("--output", "{out}", "--vm-workers", "11 12 13")),
    ("vm-workers-empty-falls-back", ("--output", "{out}", "--vm-workers", "")),
    (
        "vm-ceph-nodes",
        ("--output", "{out}", "--vm-ceph-nodes", "21 22", "--vm-ram-ceph", "2048"),
    ),
    ("ceph", ("--ceph", "--output", "{out}")),
    ("ceph-with-explicit-nodes", ("--ceph", "--output", "{out}", "--vm-ceph-nodes", "31 32")),
    ("ceph-false", ("--output", "{out}", "--ceph", "false")),
    ("vm-ram-worker", ("--output", "{out}", "--vm-ram-worker", "2560")),
    ("vm-ram-ceph", ("--output", "{out}", "--vm-ram-ceph", "2048")),
    ("ceph-osd-memory-target", ("--output", "{out}", "--ceph-osd-memory-target", "1717986918")),
    ("timeout", ("--output", "{out}", "--timeout", "5000")),
    ("renet-path", ("--output", "{out}", "--renet-path", "/opt/renet/bin/renet")),
    ("vm-image", ("--output", "{out}", "--vm-image", "debian-13")),
    ("vm-net", ("--output", "{out}", "--vm-net", "renet12")),
    ("docker-registry", ("--output", "{out}", "--docker-registry", "192.168.112.5:5000")),
    ("k8s", ("--output", "{out}", "--k8s")),
    ("k8s-false", ("--output", "{out}", "--k8s", "false")),
    (
        "second-group",
        (
            "--output",
            "{out}",
            "--vm-net",
            "renet12",
            "--vm-net-base",
            "192.168.112",
            "--docker-registry",
            "192.168.112.5:5000",
            "--k8s",
        ),
    ),
    (
        "combined-workers-and-ceph",
        (
            "--output",
            "{out}",
            "--vm-workers",
            "11 12",
            "--vm-ceph-nodes",
            "21 22 23",
            "--vm-ram-worker",
            "2560",
            "--vm-ram-ceph",
            "2560",
            "--ceph-osd-memory-target",
            "1717986918",
        ),
    ),
    ("unknown-flag-is-ignored", ("--output", "{out}", "--not-a-flag", "x")),
    ("positional-is-ignored", ("--output", "{out}", "stray")),
)


@pytest.mark.parametrize(
    ("name", "args"), DOCUMENTED_CASES, ids=[case[0] for case in DOCUMENTED_CASES]
)
def test_documented_flag_combinations_agree(
    tmp_path: pathlib.Path, name: str, args: tuple[str, ...]
) -> None:
    old, _new = both(tmp_path, *args)
    assert name  # the id is the case; the assert keeps ruff from calling it unused
    assert old.produced is not None, "the twin wrote no file, so the comparison proves nothing"
    assert "NODE_ENV=test" in old.produced


def test_the_generated_file_is_actually_compared(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Two different flag sets must produce two different files.

    Without this, every `assert_equivalent` above could be comparing None with None, or one constant template with itself, and would stay green with the port's whole body deleted.
    """
    default_old, _ = run_both(tmp_path, ("--output", "{out}"))
    ceph_old, _ = run_both(tmp_path, ("--ceph", "--output", "{out}"))
    assert default_old.produced is not None
    assert ceph_old.produced is not None
    assert default_old.produced != ceph_old.produced
    assert "VM_WORKERS=11 12" in default_old.produced
    assert "VM_CEPH_NODES=21 22 23" in ceph_old.produced


# --------------------------------------------------------------------------- Missing and malformed arguments ---------------------------------------------------------------------------


def test_no_arguments_at_all_prints_the_usage_and_exits_1(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path)
    assert old.code == 1
    assert "Usage: create-e2e-env.sh --output <path> [options]" in old.stderr
    assert old.produced is None


def test_output_with_no_value_becomes_the_string_true(tmp_path: pathlib.Path) -> None:
    """DEFECT C: `parse_args` turns a bare flag into `true`, and `-z` accepts it."""
    old_cwd = tmp_path / "old-cwd"
    new_cwd = tmp_path / "new-cwd"
    results = []
    for cwd in (old_cwd, new_cwd):
        cwd.mkdir()
        assert_is_scratch(cwd)
    for cwd, invocation, env in (
        (old_cwd, "bash %s/%s" % (diff.repo(), TWIN), {}),
        (new_cwd, "python3 -m %s" % MODULE, {"PYTHONPATH": "%s/.ci" % diff.repo()}),
    ):
        code, stdout, stderr = diff.bash_streams(
            "%s --output" % invocation, env=diff.env_for(**env), cwd=str(cwd), timeout=30
        )
        results.append((code, stdout, stderr, (cwd / "true").read_text(encoding="utf-8")))

    assert results[0][0] == 0, "the twin is expected to succeed and write a file named `true`"
    assert results[0] == results[1]
    assert "VM_NET_BASE=192.168.111" in results[0][3]


def test_a_flag_that_is_not_a_shell_identifier_exits_2_from_common_sh(
    tmp_path: pathlib.Path,
) -> None:
    """`printf -v ARG_A.B` fails, and `set -e` takes the whole script down."""
    old, new = run_both(tmp_path, ("--a.b=1", "--output", "{out}"))
    assert old.code == 2
    assert old.produced is None
    # The PATH is compared here rather than normalised: the port reproduces common.sh's own unnormalised `$SCRIPT_DIR/../lib/common.sh` verbatim.
    expected = "%s/.ci/scripts/env/../lib/common.sh: line %d: printf: `ARG_A.B'" % (
        diff.repo(),
        port.PRINTF_LINE,
    )
    assert old.stderr.startswith(expected), old.stderr
    assert old.code == new.code
    assert old.stderr == new.stderr
    assert old.stdout == new.stdout
    assert new.produced is None


def test_output_pointing_at_a_directory_fails_at_the_heredoc(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "adir"
    target.mkdir()
    old, new = run_both(tmp_path, ("--output", str(target)))
    assert old.code == 1
    assert "line %d" % port.HEREDOC_LINE in old.stderr
    assert "Is a directory" in old.stderr
    assert _PROG.sub("<prog>: line ", old.stderr) == _PROG.sub("<prog>: line ", new.stderr)
    assert (old.code, old.stdout) == (new.code, new.stdout)


def test_output_that_cannot_be_written_reports_permission_denied(tmp_path: pathlib.Path) -> None:
    readonly = tmp_path / "ro.env"
    readonly.write_text("", encoding="utf-8")
    readonly.chmod(0o444)
    old, new = run_both(tmp_path, ("--output", str(readonly)))
    assert old.code == 1
    assert "Permission denied" in old.stderr
    assert _PROG.sub("<prog>: line ", old.stderr) == _PROG.sub("<prog>: line ", new.stderr)
    assert (old.code, old.stdout) == (new.code, new.stdout)


def test_a_directory_that_cannot_be_created_surfaces_mkdirs_own_message(
    tmp_path: pathlib.Path,
) -> None:
    """The port shells out to `mkdir -p` so this text is coreutils', not ours."""
    old, new = run_both(tmp_path, ("--output", "/dev/null/x/y.env"))
    assert old.code != 0
    assert "mkdir:" in old.stderr
    assert (old.code, old.stdout, old.stderr) == (new.code, new.stdout, new.stderr)


# --------------------------------------------------------------------------- The RAM budget, and DEFECT A ---------------------------------------------------------------------------


def test_a_topology_over_the_ceiling_is_refused(tmp_path: pathlib.Path) -> None:
    old, _ = both(
        tmp_path,
        "--output",
        "{out}",
        "--vm-ram-worker",
        "6000",
        "--vm-ram-ceph",
        "6000",
        "--vm-ceph-nodes",
        "21 22 23",
    )
    assert old.code == 1
    assert "31024 MB exceeds the 14848 MB" in old.stderr
    assert old.produced is None


def test_a_topology_under_the_ceiling_is_allowed(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path, "--output", "{out}", "--ceph")
    assert old.code == 0
    assert "= 13312 MB" in old.stderr


@pytest.mark.parametrize("padded", ["08", "09", "08192"])
def test_defect_a_a_zero_padded_ram_value_skips_the_budget_check_entirely(
    tmp_path: pathlib.Path, padded: str
) -> None:
    """Bash reads `08` as octal, the expansion fails, and `local` hides it."""
    old, _ = both(tmp_path, "--output", "{out}", "--vm-ram-worker", padded, "--vm-workers", "1 2 3")
    assert old.code == 0, "the twin exits 0 despite the failed arithmetic"
    assert "value too great for base" in old.stderr
    assert "VM RAM budget" not in old.stderr, "the budget line proves the check ran"
    assert old.produced is not None
    assert "VM_RAM_WORKER=%s\n" % padded in old.produced


def test_defect_a_the_skip_lets_an_over_budget_topology_through(tmp_path: pathlib.Path) -> None:
    """The same numbers, padded and unpadded, give opposite verdicts."""
    padded, _ = both(
        tmp_path, "--output", "{out}", "--vm-ram-worker", "08192", "--vm-workers", "11 12 13 14"
    )
    assert padded.code == 0
    unpadded, _ = both(
        tmp_path, "--output", "{out}", "--vm-ram-worker", "8192", "--vm-workers", "11 12 13 14"
    )
    assert unpadded.code == 1
    assert "exceeds the 14848 MB" in unpadded.stderr
    assert unpadded.produced is None


def test_a_non_numeric_ram_value_is_fatal_because_of_set_u(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path, "--output", "{out}", "--vm-ram-worker", "abc")
    assert old.code == 1
    assert "abc: unbound variable" in old.stderr
    assert old.produced is None


ARITHMETIC_VALUES = [
    "",
    "0",
    "-1",
    "  7  ",
    "010",
    "0x10",
    "16#ff",
    "1+1",
    "2**3",
    "4096*2",
    "(1+1)*512",
    "8192/2",
    "9/2",
    "1 2",
    "1;ls",
    "(",
    "4096)",
    "HOME",
    "PATH",
    "RED",
    "VM_NET_BASE",
    "ARG_OUTPUT",
]


@pytest.mark.parametrize("value", ARITHMETIC_VALUES)
def test_the_arithmetic_agrees_over_constants_expressions_and_error_shapes(
    tmp_path: pathlib.Path, value: str
) -> None:
    both(tmp_path, "--output", "{out}", "--vm-ram-worker", value)


@pytest.mark.parametrize("value", ["08", "0x1g", "1 2", "abc123 x"])
def test_the_ceph_ram_value_takes_the_same_path_as_the_worker_one(
    tmp_path: pathlib.Path, value: str
) -> None:
    both(tmp_path, "--output", "{out}", "--vm-ram-ceph", value, "--vm-ceph-nodes", "21 22")


def test_the_leftmost_bad_operand_wins_when_both_are_bad(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path, "--output", "{out}", "--vm-ram-worker", "08", "--vm-ram-ceph", "09")
    assert 'error token is "08"' in old.stderr
    assert "09" not in old.stderr.split("\n")[0]


def test_the_documented_divergence_on_an_unsupported_operator_is_real(
    tmp_path: pathlib.Path,
) -> None:
    """PINNED GAP, not an oversight. See the port docstring's divergence section.

    `1<<13` is a bash shift, which `_arith` does not implement, and 2x8192 plus the bridge crosses the 14848 MB ceiling. So this is the WORST case the gap can produce: the twin evaluates the shift and REFUSES the topology (exit 1),
    while the port scores the value as an arithmetic error, skips the budget
    exactly as Defect A skips it, and exits 0 having written the file.

    Asserted in both directions rather than glossed, so a future reader who narrows the gap finds a red test telling them to update the port docstring, and a reader who does not is told precisely what it costs.
    """
    old, new = run_both(tmp_path, ("--output", "{out}", "--vm-ram-worker", "1<<13"))
    assert old.code == 1, "bash evaluates the shift and refuses 17408 MB"
    assert "= 17408 MB" in old.stderr
    assert old.produced is None
    assert new.code == 0, "the port treats the shift as Defect A's arithmetic error"
    # The clause is asked of the running bash, not spelled here: bash 5.3 says "arithmetic syntax error" where 5.2 says "syntax error", and this tree's hosts are 5.3 while every CI runner is 5.2. A literal here passes locally and fails only in the one place nobody could see.
    assert "%s in expression" % bash_dialect.arith_syntax_error() in new.stderr
    assert new.produced is not None


# --------------------------------------------------------------------------- DEFECT B: the node count is globbed against the working directory ---------------------------------------------------------------------------


def five_file_directory(tmp_path: pathlib.Path) -> pathlib.Path:
    workdir = tmp_path / "globdir"
    workdir.mkdir()
    for name in ("f1", "f2", "f3", "f4", "f5"):
        (workdir / name).write_text("", encoding="utf-8")
    return workdir


@pytest.mark.parametrize("pattern", ["*", "11 f?", "zz*", "f[12]", "11 12"])
def test_defect_b_the_node_count_is_pathname_expanded(tmp_path: pathlib.Path, pattern: str) -> None:
    both(
        tmp_path,
        "--output",
        "{out}",
        "--vm-workers",
        pattern,
        workdir=five_file_directory(tmp_path),
    )


def test_defect_b_the_budget_and_the_written_file_disagree(tmp_path: pathlib.Path) -> None:
    old, _ = both(
        tmp_path, "--output", "{out}", "--vm-workers", "*", workdir=five_file_directory(tmp_path)
    )
    assert old.code == 1, "five 4096 MB workers plus the bridge is over the ceiling"
    assert "5x4096 (worker)" in old.stderr
    assert old.produced is None


@pytest.mark.parametrize("value", ["-n", "-e 11 12", "-n -e", "-ne 11", "-E 11 12", "-x 11"])
def test_echo_eats_its_own_option_words_before_counting(tmp_path: pathlib.Path, value: str) -> None:
    both(tmp_path, "--output", "{out}", "--vm-workers", value)


@pytest.mark.parametrize("value", ["  11   12  13 ", "11\t12", "11\n12", "11"])
def test_whitespace_in_a_node_list_is_split_for_the_count_and_kept_in_the_file(
    tmp_path: pathlib.Path, value: str
) -> None:
    both(tmp_path, "--output", "{out}", "--vm-workers", value)


# --------------------------------------------------------------------------- DEFECT D: the environment, and the twin's own env fallbacks ---------------------------------------------------------------------------


def test_defect_d_arg_output_from_the_environment_works_with_no_flag(
    tmp_path: pathlib.Path,
) -> None:
    # `{out}` is only substituted inside args, so the environment is built by
    # hand here rather than through `run_both`.
    results = []
    for side in ("old", "new"):
        output = tmp_path / ("env-%s.env" % side)
        env: dict[str, str | None] = {"ARG_OUTPUT": str(output)}
        invocation = "bash %s/%s" % (diff.repo(), TWIN)
        if side == "new":
            env["PYTHONPATH"] = "%s/.ci" % diff.repo()
            invocation = "python3 -m %s" % MODULE
        code, stdout, stderr = diff.bash_streams(
            invocation, env=diff.env_for(**env), cwd=str(tmp_path), timeout=30
        )
        results.append((code, stdout, stderr.replace(str(output), "<out>"), output.read_text()))
    assert results[0][0] == 0
    assert results[0] == results[1]


ENVIRONMENT_CASES: tuple[tuple[str, dict[str, str | None]], ...] = (
    ("ci-false", {"CI": "false"}),
    ("ci-empty-falls-back-to-true", {"CI": ""}),
    ("bridge-timeout", {"BRIDGE_TIMEOUT": "999"}),
    ("vm-image", {"VM_IMAGE": "debian-13"}),
    ("renet-binary", {"RENET_BINARY": "/x/renet"}),
    ("per-role-ram", {"VM_RAM_WORKER": "2560", "VM_RAM_CEPH": "2048"}),
    ("osd-memory-target", {"CEPH_OSD_MEMORY_TARGET": "17179"}),
    ("no-color", {"NO_COLOR": "1"}),
    (
        "everything-at-once",
        {
            "CI": "false",
            "BRIDGE_TIMEOUT": "999",
            "VM_IMAGE": "debian-13",
            "RENET_BINARY": "/x/renet",
            "VM_RAM_WORKER": "2560",
            "VM_RAM_CEPH": "2048",
            "CEPH_OSD_MEMORY_TARGET": "17179",
        },
    ),
)


@pytest.mark.parametrize(
    ("name", "env_extra"), ENVIRONMENT_CASES, ids=[case[0] for case in ENVIRONMENT_CASES]
)
def test_the_environment_fallbacks_agree(
    tmp_path: pathlib.Path, name: str, env_extra: dict[str, str | None]
) -> None:
    old, _ = both(tmp_path, "--output", "{out}", env_extra=env_extra)
    assert name
    assert old.code == 0
    assert old.produced is not None


def test_a_flag_beats_the_environment(tmp_path: pathlib.Path) -> None:
    old, _ = both(
        tmp_path, "--output", "{out}", "--vm-image", "alpine-3", env_extra={"VM_IMAGE": "debian-13"}
    )
    assert old.produced is not None
    assert "VM_IMAGE=alpine-3\n" in old.produced


def test_debug_true_dumps_the_file_to_stdout(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path, "--output", "{out}", env_extra={"DEBUG": "true"})
    assert old.stdout.startswith("\nContents:\n")
    assert old.produced is not None
    assert old.stdout.endswith(old.produced)


def test_debug_false_keeps_stdout_empty(tmp_path: pathlib.Path) -> None:
    old, _ = both(tmp_path, "--output", "{out}", env_extra={"DEBUG": "false"})
    assert old.stdout == ""


def test_a_tty_on_stderr_colours_both_sides_the_same_way(tmp_path: pathlib.Path) -> None:
    """Colour is decided by `isatty`, so a pipe-only differential proves half."""
    old, new = run_both(tmp_path, ("--output", "{out}"), tty="stderr")
    assert diff.escape_bytes(old.stderr) > 0, "the twin should colour a tty"
    assert_equivalent(tmp_path, old, new)


# --------------------------------------------------------------------------- The pure helpers, exercised directly ---------------------------------------------------------------------------


DIRNAME_INPUTS = [
    "a",
    "a/b",
    "/",
    "//",
    "///",
    "a/",
    "a//b",
    "/a",
    "a/b/",
    "///a///b///",
    "./a",
    "../a",
    ".env",
    "packages/e2e-tests/.env",
]


@pytest.mark.parametrize("path", DIRNAME_INPUTS)
def test_dirname_matches_coreutils(path: str) -> None:
    expected = subprocess.run(
        ["dirname", path], capture_output=True, text=True, check=True
    ).stdout.rstrip("\n")
    assert port.dirname(path) == expected, path


def test_dirname_is_not_os_path_dirname(tmp_path: pathlib.Path) -> None:
    """The one case that makes the hand-written version necessary."""
    assert os.path.dirname("a/") == "a"
    assert port.dirname("a/") == "."
    assert tmp_path  # fixture kept so the case sits with the rest


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", 0),
        ("11", 1),
        ("11 12", 2),
        ("  11   12  13 ", 3),
        ("11\t12", 2),
        ("11\n12", 2),
        ("-n", 0),
        ("-n -e", 0),
        ("-e 11 12", 2),
        ("-ne 11", 1),
        ("-x 11", 2),
        ("-e a\\nb", 2),
        ("-e a\\cb", 1),
    ],
)
def test_word_count_reproduces_echo_piped_into_wc_w(value: str, expected: int) -> None:
    assert port.word_count(value) == expected


def test_word_count_globs_against_the_cwd(tmp_path: pathlib.Path, monkeypatch) -> None:
    workdir = five_file_directory(tmp_path)
    monkeypatch.chdir(workdir)
    assert port.word_count("*") == 5
    assert port.word_count("11 f?") == 6
    assert port.word_count("zz*") == 1, "a pattern with no match stays literal"
    assert port.word_count("11 12") == 2, "no metacharacter means no filesystem access"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("4096", 4096),
        ("010", 8),
        ("0x10", 16),
        ("0X10", 16),
        ("16#ff", 255),
        ("-1", -1),
        ("+5", 5),
        ("  7  ", 7),
        ("1+1", 2),
        ("2**3", 8),
        ("(1+1)*512", 1024),
        ("-2**2", 4),
        ("9/2", 4),
        ("-9/2", -4),
        ("-7%2", -1),
    ],
)
def test_arithmetic_matches_bash_for_the_supported_grammar(text: str, expected: int) -> None:
    assert port.arithmetic(text, {}) == expected
    proved = subprocess.run(
        ["bash", "-c", 'printf %%s "$((%s))"' % text], capture_output=True, text=True, check=True
    ).stdout
    assert int(proved) == expected, "bash disagrees with the pinned expectation for %r" % text


@pytest.mark.parametrize("text", ["08", "09", "0x1g", "2#12"])
def test_a_digit_outside_the_base_is_the_value_too_great_error(text: str) -> None:
    with pytest.raises(port.ArithError) as caught:
        port.arithmetic(text, {})
    assert 'value too great for base (error token is "%s")' % text in str(caught.value)


def test_an_unset_name_raises_the_fatal_class_and_a_set_one_recurses() -> None:
    with pytest.raises(port.UnboundVariableError):
        port.arithmetic("nope", {})
    assert port.arithmetic("outer", {"outer": "inner", "inner": "42"}) == 42
    assert port.arithmetic("blank", {"blank": ""}) == 0


def test_deep_variable_recursion_is_bounded_rather_than_a_stack_overflow() -> None:
    scope = {"v%d" % index: "v%d" % (index + 1) for index in range(200)}
    scope["v200"] = "1"
    with pytest.raises(port.ArithError):
        port.arithmetic("v0", scope)


# --------------------------------------------------------------------------- The pins ---------------------------------------------------------------------------


def twin_lines() -> list[str]:
    return pathlib.Path(diff.repo(), TWIN).read_text(encoding="utf-8").split("\n")


def test_the_pinned_twin_line_numbers_still_point_at_the_right_lines() -> None:
    lines = twin_lines()
    assert lines[port.ARITH_LINE - 1].strip().startswith("local total=$(("), (
        "twin line %d is %r" % (port.ARITH_LINE, lines[port.ARITH_LINE - 1])
    )
    assert lines[port.HEREDOC_LINE - 1].strip() == 'cat >"$OUTPUT" <<EOF'
    common = pathlib.Path(diff.repo(), COMMON).read_text(encoding="utf-8").split("\n")
    assert common[port.PRINTF_LINE - 1].strip() == 'printf -v "$key" \'%s\' "$value"'


def test_the_template_carries_every_key_the_twins_heredoc_writes() -> None:
    """A key silently dropped from the template is the port's worst failure."""
    body = "\n".join(twin_lines())
    heredoc = body.split('cat >"$OUTPUT" <<EOF\n', 1)[1].split("\nEOF\n", 1)[0]
    twin_keys = [
        line.split("=", 1)[0]
        for line in heredoc.split("\n")
        if "=" in line and not line.startswith("#")
    ]
    port_keys = [
        line.split("=", 1)[0]
        for line in port.FILE_TEMPLATE.split("\n")
        if "=" in line and not line.startswith("#")
    ]
    assert twin_keys == port_keys
    assert len(twin_keys) == 16


def test_the_budget_constants_match_the_twin() -> None:
    body = "\n".join(twin_lines())
    assert "local bridge_ram=%d" % port.BRIDGE_RAM_MB in body
    assert "local ceiling_mb=%d" % port.CEILING_MB in body
    assert 'local worker_ram="${VM_RAM_WORKER:-%s}"' % port.FALLBACK_ROLE_RAM_MB in body
    assert port.BUDGET_EXPRESSION in body


def test_the_port_file_is_executable() -> None:
    mode = pathlib.Path(diff.repo(), ".ci/rediacc_ci/env/create_e2e_env.py").stat().st_mode
    assert mode & 0o111 == 0o111, "the port must be executable on disk, like its twin"
