"""`rediacc_ci.env.create_e2e_env`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/env/create-e2e-env.sh` and the port over the same arguments and compared four channels: the exit code, stdout, stderr and the GENERATED FILE. Every case now compares against `goldens/create-e2e-env/`, which holds the twin's OWN recorded bytes; each golden's provenance header carries the blob sha, so
`git cat-file -p <sha>` still yields the program that produced them.

THE LEDGER IS `.ci/shadow/w7p6-create-e2e-env.observations.jsonl`, FIVE rows over five distinct trees, every one EQUIVALENT. There is no `w7p4b-` file for this pair, so the w7p6 one is the only licence there is and it is cited as such.

THE FILE IS THE SUBJECT, NOT THE MESSAGES. This program prints three lines, all progress, all on stderr; its product is the `.env` file. So the recorded shape carries a fourth section, `--- file ---`, holding what landed on disk. A recording that froze only the two streams would pass while the port wrote a completely different file, which is the exact shape of blindness
`scripts/lib/shadow-gate.ts` was built to refuse.

EVERY CASE WRITES INTO `tmp_path`, NEVER INTO THE CHECKOUT, and one case makes that non-negotiable: `--output` with no value resolves to the literal string `true` and creates a file with that name in the CURRENT DIRECTORY. Driving it from the repository root leaves an untracked `true` behind, which is what happened while this port was being written, so `assert_is_scratch`
re-derives the working directory before anything runs.

WHAT IS MASKED, and it is three things. The OUTPUT PATH becomes `<out>`, because each recording was taken against its own temporary file. The PROGRAM NAME inside bash's `<prog>: line <N>:` diagnostics becomes `<prog>`, because a `.sh` and a module can never spell it the same way; the LINE NUMBERS are NOT masked and are compared. The CHECKOUT ROOT becomes `<root>`, for the one case
whose diagnostic names `common.sh` by absolute path.

WHAT THE DELETION COST, and it is three staleness alarms that read the twin's own source. Each is named here rather than dropped silently.

  * `test_the_pinned_twin_line_numbers_still_point_at_the_right_lines` asserted
    that `port.ARITH_LINE` and `port.HEREDOC_LINE` still pointed at
    `local total=$((` and `cat >"$OUTPUT" <<EOF` in the twin. The twin's half is
    gone. What still holds the property is stronger than a source grep: two
    recordings print those numbers in bash's own diagnostics, so
    `test_the_pinned_line_numbers_are_the_ones_bash_printed` compares the port's
    constants against what the twin SAID rather than against what it contained.
    The third pin, `PRINTF_LINE`, points into `common.sh`, which is still in the
    tree, so that half is unchanged and still reads the file.
  * `test_the_template_carries_every_key_the_twins_heredoc_writes` sliced the
    heredoc out of the twin and compared its sixteen keys against the port's
    template. The slice is gone; the RECORDED FILE is not. The key list is now
    read off `defaults`, which is the same sixteen keys in the same order,
    written by the twin itself.
  * `test_the_budget_constants_match_the_twin` grepped the twin for
    `bridge_ram=`, `ceiling_mb=`, the worker fallback and the budget expression.
    Three of the four are printed in the budget line every passing case emits,
    so they are read off the recordings; the fourth, the expression's own text,
    is asserted against the port alone, and the twin's copy is recoverable from
    the blob sha every golden header carries.

ONE CASE IS COMPARED BY SHAPE, and it is a documented divergence rather than a surprise: `1<<13` is a bash shift the port's arithmetic does not implement, so the twin evaluated it and REFUSED the topology while the port scores it as an arithmetic error and writes the file. Both halves are asserted, so a future reader who narrows the gap finds a red test telling them to update the
port docstring.
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import typing

import pytest

from rediacc_ci.core import bash_dialect
from rediacc_ci.env import create_e2e_env as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "create-e2e-env"
TWIN = ".ci/scripts/env/create-e2e-env.sh"
COMMON = ".ci/scripts/lib/common.sh"
MODULE = "rediacc_ci.env.create_e2e_env"

FILE_MARKER = "--- file ---\n"

# THE SUBJECT'S OWN NAME, and only that. bash prefixes its diagnostics with the file it is running, which is a `.sh` on one side and a module file on the other, so the two spellings are folded to `<prog>`.
#
# NOT a blanket `^\S+: line ` regex, which is what the first draft used and what over-masked: bash also names the file it SOURCED, and `common.sh`'s own unnormalised `$SCRIPT_DIR/../lib/common.sh` is identical on both sides. Masking it would have thrown away the one assertion that proves the port reproduces that spelling.
SUBJECT_NAMES = (
    "%s/%s" % (diff.repo(), TWIN),
    "%s/.ci/rediacc_ci/env/create_e2e_env.py" % diff.repo(),
)


def assert_is_scratch(workdir: pathlib.Path) -> None:
    """Refuse to run a WRITING case anywhere but the disposable tree."""
    resolved = str(workdir.resolve())
    assert resolved != diff.repo(), "refusing to write into the real checkout"
    assert not resolved.startswith(diff.repo() + os.sep), (
        "working directory %r is inside the checkout" % resolved
    )


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
    ("vm-ceph-nodes", ("--output", "{out}", "--vm-ceph-nodes", "21 22", "--vm-ram-ceph", "2048")),
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

# The arithmetic corpus, one case per value. The names are the differential's values, spelled so a reader can find the value in the case id.
ARITHMETIC_VALUES: tuple[tuple[str, str], ...] = (
    ("empty", ""),
    ("zero", "0"),
    ("negative-one", "-1"),
    ("spaced-seven", "  7  "),
    ("octal-ten", "010"),
    ("hex-ten", "0x10"),
    ("base-sixteen-ff", "16#ff"),
    ("one-plus-one", "1+1"),
    ("two-to-the-third", "2**3"),
    ("four-thousand-ninety-six-times-two", "4096*2"),
    ("a-parenthesised-product", "(1+1)*512"),
    ("a-division", "8192/2"),
    ("a-truncating-division", "9/2"),
    ("two-words", "1 2"),
    ("a-shell-fragment", "1;ls"),
    ("an-open-parenthesis", "("),
    ("an-unbalanced-close", "4096)"),
    ("the-name-home", "HOME"),
    ("the-name-path", "PATH"),
    ("the-name-red", "RED"),
    ("the-name-vm-net-base", "VM_NET_BASE"),
    ("the-name-arg-output", "ARG_OUTPUT"),
)

CEPH_RAM_VALUES: tuple[tuple[str, str], ...] = (
    ("an-octal-eight", "08"),
    ("a-bad-hex-digit", "0x1g"),
    ("two-words", "1 2"),
    ("a-word-and-a-number", "abc123 x"),
)

GLOB_PATTERNS: tuple[tuple[str, str], ...] = (
    ("a-bare-star", "*"),
    ("a-number-and-a-question-mark", "11 f?"),
    ("a-pattern-that-matches-nothing", "zz*"),
    ("a-bracket-class", "f[12]"),
    ("two-plain-numbers", "11 12"),
)

ECHO_OPTION_VALUES: tuple[tuple[str, str], ...] = (
    ("dash-n", "-n"),
    ("dash-e-and-two-numbers", "-e 11 12"),
    ("dash-n-dash-e", "-n -e"),
    ("dash-ne-and-a-number", "-ne 11"),
    ("dash-capital-e", "-E 11 12"),
    ("an-unknown-option", "-x 11"),
)

WHITESPACE_VALUES: tuple[tuple[str, str], ...] = (
    ("padded-with-spaces", "  11   12  13 "),
    ("separated-by-a-tab", "11\t12"),
    ("separated-by-a-newline", "11\n12"),
    ("a-single-id", "11"),
)

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


def build_cases() -> dict[str, dict[str, typing.Any]]:
    """Every case the differential drove, as a named table.

    `pre` names the fixture shape a case needs: `globdir` is the five-file working directory Defect B globs against, `adir` makes the output path a directory, `readonly` makes it an unwritable file, and `bare-output` is the case that writes a file called `true` into the current directory.
    """
    cases: dict[str, dict[str, typing.Any]] = {}
    for name, args in DOCUMENTED_CASES:
        cases["flag-%s" % name] = {"args": args}
    for name, value in ARITHMETIC_VALUES:
        cases["arithmetic-%s" % name] = {"args": ("--output", "{out}", "--vm-ram-worker", value)}
    for name, value in CEPH_RAM_VALUES:
        cases["ceph-ram-%s" % name] = {
            "args": ("--output", "{out}", "--vm-ram-ceph", value, "--vm-ceph-nodes", "21 22")
        }
    for name, value in GLOB_PATTERNS:
        cases["glob-%s" % name] = {
            "args": ("--output", "{out}", "--vm-workers", value),
            "pre": "globdir",
        }
    for name, value in ECHO_OPTION_VALUES:
        cases["echo-option-%s" % name] = {"args": ("--output", "{out}", "--vm-workers", value)}
    for name, value in WHITESPACE_VALUES:
        cases["worker-list-%s" % name] = {"args": ("--output", "{out}", "--vm-workers", value)}
    for name, env in ENVIRONMENT_CASES:
        cases["environment-%s" % name] = {"args": ("--output", "{out}"), "env": env}
    for padded in ("08", "09", "08192"):
        cases["a-zero-padded-ram-value-%s" % padded] = {
            "args": ("--output", "{out}", "--vm-ram-worker", padded, "--vm-workers", "1 2 3")
        }
    cases.update(
        {
            "no-arguments-at-all": {"args": ()},
            "a-bare-output-flag": {"args": ("--output",), "pre": "bare-output"},
            "a-flag-that-is-not-a-shell-identifier": {"args": ("--a.b=1", "--output", "{out}")},
            "an-output-that-is-a-directory": {"args": ("--output", "{adir}"), "pre": "adir"},
            "an-output-that-cannot-be-written": {
                "args": ("--output", "{readonly}"),
                "pre": "readonly",
            },
            "an-output-directory-that-cannot-be-created": {
                "args": ("--output", "/dev/null/x/y.env")
            },
            "a-topology-over-the-ceiling": {
                "args": (
                    "--output",
                    "{out}",
                    "--vm-ram-worker",
                    "6000",
                    "--vm-ram-ceph",
                    "6000",
                    "--vm-ceph-nodes",
                    "21 22 23",
                )
            },
            "a-topology-under-the-ceiling": {"args": ("--output", "{out}", "--ceph")},
            "the-padded-value-that-passes": {
                "args": (
                    "--output",
                    "{out}",
                    "--vm-ram-worker",
                    "08192",
                    "--vm-workers",
                    "11 12 13 14",
                )
            },
            "the-unpadded-value-that-refuses": {
                "args": (
                    "--output",
                    "{out}",
                    "--vm-ram-worker",
                    "8192",
                    "--vm-workers",
                    "11 12 13 14",
                )
            },
            "a-non-numeric-ram-value": {"args": ("--output", "{out}", "--vm-ram-worker", "abc")},
            "two-bad-operands-at-once": {
                "args": ("--output", "{out}", "--vm-ram-worker", "08", "--vm-ram-ceph", "09")
            },
            "an-unsupported-shift-operator": {
                "args": ("--output", "{out}", "--vm-ram-worker", "1<<13")
            },
            "a-flag-beats-the-environment": {
                "args": ("--output", "{out}", "--vm-image", "alpine-3"),
                "env": {"VM_IMAGE": "debian-13"},
            },
            "debug-true-dumps-the-file": {
                "args": ("--output", "{out}"),
                "env": {"DEBUG": "true"},
            },
            "debug-false-keeps-stdout-empty": {
                "args": ("--output", "{out}"),
                "env": {"DEBUG": "false"},
            },
            "the-output-path-from-the-environment": {"args": (), "pre": "env-output"},
            "a-tty-on-stderr": {"args": ("--output", "{out}"), "tty": "stderr"},
        }
    )
    return cases


CASE_KW = build_cases()
CASES = tuple(CASE_KW)

# The one case the port does not reproduce. Compared by shape, in its own test.
DIVERGENT = ("an-unsupported-shift-operator",)


def prepare(tmp_path: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path, dict[str, str]]:
    """This case's working directory, its output path and any extra environment."""
    kw = CASE_KW[name]
    shape = kw.get("pre")
    cwd = tmp_path / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    output = tmp_path / "out.env"
    extra: dict[str, str] = {}
    if shape == "globdir":
        cwd = tmp_path / "globdir"
        cwd.mkdir(parents=True, exist_ok=True)
        for filename in ("f1", "f2", "f3", "f4", "f5"):
            (cwd / filename).write_text("", encoding="utf-8")
    elif shape == "adir":
        output = tmp_path / "adir"
        output.mkdir(parents=True, exist_ok=True)
    elif shape == "readonly":
        output = tmp_path / "ro.env"
        output.write_text("", encoding="utf-8")
        output.chmod(0o444)
    elif shape == "bare-output":
        # `parse_args` turns a bare flag into the string `true`, and `-z` accepts it, so the file lands in the CURRENT directory under that name.
        output = cwd / "true"
    elif shape == "env-output":
        extra["ARG_OUTPUT"] = str(output)
    assert_is_scratch(cwd)
    return cwd, output, extra


def run(tmp_path: pathlib.Path, name: str, *, subject: str | None = None) -> tuple:
    """One subject, once, over this case's own scratch directory."""
    kw = CASE_KW[name]
    cwd, output, extra = prepare(tmp_path, name)
    output.unlink(missing_ok=True) if output.is_file() and kw.get("pre") != "readonly" else None
    invocation = subject or "python3 -m %s" % MODULE
    args = tuple(
        arg.replace("{out}", str(output))
        .replace("{adir}", str(output))
        .replace("{readonly}", str(output))
        for arg in kw["args"]
    )
    env: dict[str, str | None] = dict(kw.get("env") or {})
    env.update(extra)
    if not invocation.startswith("bash "):
        env["PYTHONPATH"] = "%s/.ci" % diff.repo()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    quoted = " ".join(shlex.quote(arg) for arg in args)
    code, stdout, stderr = diff.bash_streams(
        ("%s %s" % (invocation, quoted)).strip(),
        env=diff.env_for(**env),
        cwd=str(cwd),
        tty=kw.get("tty"),
        timeout=30,
    )
    produced = output.read_text(encoding="utf-8") if output.is_file() else None

    def clean(text: str | None) -> str | None:
        if text is None:
            return None
        for spelling in SUBJECT_NAMES:
            text = text.replace(spelling, "<prog>")
        if subject is not None and subject.startswith("python3 /"):
            text = text.replace(subject.split(" ", 1)[1].strip("'"), "<prog>")
        return text.replace(str(output), "<out>").replace(diff.repo(), "<root>")

    return code, clean(stdout), clean(stderr), clean(produced)


def render(out: tuple) -> str:
    return "%s%s%s\n" % (frozen.render(out[0], out[1], out[2]), FILE_MARKER, json.dumps(out[3]))


def recorded(name: str) -> tuple:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, produced = rest.split(FILE_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, json.loads(produced)


def compare(tmp_path: pathlib.Path, name: str) -> tuple:
    want = recorded(name)
    got = run(tmp_path, name)
    for index, field in enumerate(("exit", "stdout", "stderr", "file")):
        assert got[index] == want[index], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[index],
            got[index],
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_generated_file_is_actually_compared() -> None:
    """ANTI-VACUITY. Two different flag sets must have produced two different files.

    Without this, every comparison above could be of None with None, or of one constant template with itself, and would stay green with the port's whole body deleted.
    """
    default = recorded("flag-defaults")[3]
    ceph = recorded("flag-ceph")[3]
    assert default is not None
    assert ceph is not None
    assert default != ceph
    assert "VM_WORKERS=11 12" in default
    assert "VM_CEPH_NODES=21 22 23" in ceph


def test_every_documented_flag_case_wrote_a_file() -> None:
    """The twenty-seven documented combinations all succeed, and each one's file is real rather than a refusal recorded as an empty string."""
    for name, _args in DOCUMENTED_CASES:
        produced = recorded("flag-%s" % name)[3]
        assert produced is not None, name
        assert "NODE_ENV=test" in produced, name


# --------------------------------------------------------------------------- Missing and malformed arguments ---------------------------------------------------------------------------


def test_no_arguments_at_all_prints_the_usage_and_exits_1() -> None:
    code, _stdout, stderr, produced = recorded("no-arguments-at-all")
    assert code == 1
    assert "Usage: create-e2e-env.sh --output <path> [options]" in stderr
    assert produced is None


def test_output_with_no_value_becomes_the_string_true() -> None:
    """DEFECT C: `parse_args` turns a bare flag into `true`, and `-z` accepts it."""
    code, _stdout, _stderr, produced = recorded("a-bare-output-flag")
    assert code == 0, "the twin succeeded and wrote a file named `true`"
    assert produced is not None
    assert "VM_NET_BASE=192.168.111" in produced


def test_a_flag_that_is_not_a_shell_identifier_exits_2_from_common_sh() -> None:
    """`printf -v ARG_A.B` fails, and `set -e` takes the whole script down."""
    code, _stdout, stderr, produced = recorded("a-flag-that-is-not-a-shell-identifier")
    assert code == 2
    assert produced is None
    # The path is recorded rather than masked away: the port reproduces common.sh's own unnormalised `$SCRIPT_DIR/../lib/common.sh` verbatim, and only the checkout root is folded.
    assert stderr.startswith(
        "<root>/.ci/scripts/env/../lib/common.sh: line %d: printf: `ARG_A.B'" % port.PRINTF_LINE
    ), stderr


def test_output_pointing_at_a_directory_fails_at_the_heredoc() -> None:
    code, _stdout, stderr, _produced = recorded("an-output-that-is-a-directory")
    assert code == 1
    assert "line %d" % port.HEREDOC_LINE in stderr
    assert "Is a directory" in stderr


def test_output_that_cannot_be_written_reports_permission_denied() -> None:
    code, _stdout, stderr, _produced = recorded("an-output-that-cannot-be-written")
    assert code == 1
    assert "Permission denied" in stderr


def test_a_directory_that_cannot_be_created_surfaces_mkdirs_own_message() -> None:
    """The port shells out to `mkdir -p` so this text is coreutils', not ours."""
    code, _stdout, stderr, _produced = recorded("an-output-directory-that-cannot-be-created")
    assert code != 0
    assert "mkdir:" in stderr


# --------------------------------------------------------------------------- The RAM budget, and DEFECT A ---------------------------------------------------------------------------


def test_a_topology_over_the_ceiling_is_refused() -> None:
    code, _stdout, stderr, produced = recorded("a-topology-over-the-ceiling")
    assert code == 1
    assert "31024 MB exceeds the 14848 MB" in stderr
    assert produced is None


def test_a_topology_under_the_ceiling_is_allowed() -> None:
    code, _stdout, stderr, _produced = recorded("a-topology-under-the-ceiling")
    assert code == 0
    assert "= 13312 MB" in stderr


@pytest.mark.parametrize("padded", ["08", "09", "08192"])
def test_defect_a_a_zero_padded_ram_value_skips_the_budget_check_entirely(padded: str) -> None:
    """Bash reads `08` as octal, the expansion fails, and `local` hides it."""
    code, _stdout, stderr, produced = recorded("a-zero-padded-ram-value-%s" % padded)
    assert code == 0, "the twin exited 0 despite the failed arithmetic"
    assert "value too great for base" in stderr
    assert "VM RAM budget" not in stderr, "the budget line proves the check ran"
    assert produced is not None
    assert "VM_RAM_WORKER=%s\n" % padded in produced


def test_defect_a_the_skip_lets_an_over_budget_topology_through() -> None:
    """The same numbers, padded and unpadded, give opposite verdicts."""
    assert recorded("the-padded-value-that-passes")[0] == 0
    code, _stdout, stderr, produced = recorded("the-unpadded-value-that-refuses")
    assert code == 1
    assert "exceeds the 14848 MB" in stderr
    assert produced is None


def test_a_non_numeric_ram_value_is_fatal_because_of_set_u() -> None:
    code, _stdout, stderr, produced = recorded("a-non-numeric-ram-value")
    assert code == 1
    assert "abc: unbound variable" in stderr
    assert produced is None


def test_the_leftmost_bad_operand_wins_when_both_are_bad() -> None:
    stderr = recorded("two-bad-operands-at-once")[2]
    assert 'error token is "08"' in stderr
    assert "09" not in stderr.split("\n")[0]


def test_the_documented_divergence_on_an_unsupported_operator_is_real(
    tmp_path: pathlib.Path,
) -> None:
    """PINNED GAP, not an oversight. See the port docstring's divergence section.

    `1<<13` is a bash shift, which `_arith` does not implement, and 2x8192 plus the bridge crosses the 14848 MB ceiling. So this is the WORST case the gap can produce: the twin evaluated the shift and REFUSED the topology, while the port scores the value as an arithmetic error, skips the budget exactly as Defect A skips it, and exits 0 having written the file.

    Asserted in both directions rather than glossed, so a future reader who narrows the gap finds a red test telling them to update the port docstring, and a reader who does not is told precisely what it costs.
    """
    name = "an-unsupported-shift-operator"
    want = recorded(name)
    got = run(tmp_path, name)
    assert want[0] == 1, "bash evaluated the shift and refused 17408 MB"
    assert "= 17408 MB" in want[2]
    assert want[3] is None
    assert got[0] == 0, "the port treats the shift as Defect A's arithmetic error"
    # The clause is asked of the running bash rather than recorded: bash 5.3 says "arithmetic syntax error" where 5.2 says "syntax error", and this tree's hosts are 5.3 while every CI runner is 5.2. A frozen literal would pass locally and fail only in the one place nobody could see.
    assert "%s in expression" % bash_dialect.arith_syntax_error() in got[2]
    assert got[3] is not None


# --------------------------------------------------------------------------- DEFECT B: the node count is globbed against the working directory ---------------------------------------------------------------------------


def test_defect_b_the_budget_and_the_written_file_disagree() -> None:
    code, _stdout, stderr, produced = recorded("glob-a-bare-star")
    assert code == 1, "five 4096 MB workers plus the bridge is over the ceiling"
    assert "5x4096 (worker)" in stderr
    assert produced is None


def test_defect_b_a_pattern_that_matches_nothing_stays_literal() -> None:
    """The other half: `zz*` matches no file, bash leaves it as its own text, and the count is one."""
    code, _stdout, stderr, produced = recorded("glob-a-pattern-that-matches-nothing")
    assert code == 0
    assert "1x4096 (worker)" in stderr
    assert produced is not None


# --------------------------------------------------------------------------- DEFECT D: the environment, and the twin's own env fallbacks ---------------------------------------------------------------------------


def test_defect_d_arg_output_from_the_environment_works_with_no_flag() -> None:
    code, _stdout, _stderr, produced = recorded("the-output-path-from-the-environment")
    assert code == 0
    assert produced is not None


def test_the_environment_fallbacks_agree() -> None:
    for name, _env in ENVIRONMENT_CASES:
        code, _stdout, _stderr, produced = recorded("environment-%s" % name)
        assert code == 0, name
        assert produced is not None, name


def test_a_flag_beats_the_environment() -> None:
    produced = recorded("a-flag-beats-the-environment")[3]
    assert produced is not None
    assert "VM_IMAGE=alpine-3\n" in produced


def test_debug_true_dumps_the_file_to_stdout() -> None:
    code, stdout, _stderr, produced = recorded("debug-true-dumps-the-file")
    assert code == 0
    assert stdout.startswith("\nContents:\n")
    assert produced is not None
    assert stdout.endswith(produced)


def test_debug_false_keeps_stdout_empty() -> None:
    assert recorded("debug-false-keeps-stdout-empty")[1] == ""


def test_a_tty_on_stderr_colours_the_output() -> None:
    """Colour is decided by `isatty`, so a pipe-only corpus would prove half."""
    assert diff.escape_bytes(recorded("a-tty-on-stderr")[2]) > 0, "the twin coloured a tty"
    assert diff.escape_bytes(recorded("flag-defaults")[2]) == 0, "and not a pipe"


# --------------------------------------------------------------------------- The pins, and what the deletion cost them ---------------------------------------------------------------------------


def test_the_pinned_line_numbers_are_the_ones_bash_printed() -> None:
    """WHAT REPLACED THE SOURCE GREP. See the module docstring.

    `HEREDOC_LINE` is quoted into a user-visible diagnostic, so the recording of the directory case carries the number bash itself printed, and `PRINTF_LINE` points into `common.sh`, which is still in the tree and is still read.
    """
    assert "line %d: " % port.HEREDOC_LINE in recorded("an-output-that-is-a-directory")[2]
    common = pathlib.Path(diff.repo(), COMMON).read_text(encoding="utf-8").split("\n")
    assert common[port.PRINTF_LINE - 1].strip() == 'printf -v "$key" \'%s\' "$value"'


def test_the_arith_line_still_names_an_arithmetic_diagnostic() -> None:
    """`ARITH_LINE` is the twin's `local total=$((` and reaches no message of its own, so what the recordings can show is the line bash blamed when the arithmetic failed."""
    stderr = recorded("a-zero-padded-ram-value-08")[2]
    assert "<prog>: line %d: " % port.ARITH_LINE in stderr, stderr


def test_the_template_carries_every_key_the_twins_heredoc_wrote() -> None:
    """A key silently dropped from the template is the port's worst failure.

    The heredoc slice is gone with the twin; the file the twin WROTE is not, and it carries the same sixteen keys in the same order.
    """
    produced = recorded("flag-defaults")[3]
    assert produced is not None
    recorded_keys = [
        line.split("=", 1)[0]
        for line in produced.split("\n")
        if "=" in line and not line.startswith("#")
    ]
    port_keys = [
        line.split("=", 1)[0]
        for line in port.FILE_TEMPLATE.split("\n")
        if "=" in line and not line.startswith("#")
    ]
    assert recorded_keys == port_keys
    assert len(recorded_keys) == 16


def test_the_budget_constants_are_the_ones_the_twin_printed() -> None:
    """Three of the four are in the budget line every passing case emits."""
    stderr = recorded("flag-ceph")[2]
    assert "bridge %d + " % port.BRIDGE_RAM_MB in stderr, stderr
    assert "x%s (worker)" % port.FALLBACK_ROLE_RAM_MB in stderr, stderr
    # The ceiling reaches a stream only on the refusal, which is its own recording.
    assert "exceeds the %d MB" % port.CEILING_MB in recorded("a-topology-over-the-ceiling")[2]
    # The fourth is the expression's own text, which reached no stream. The twin's copy is recoverable from the blob sha every golden header carries.
    assert port.BUDGET_EXPRESSION


def test_the_port_file_is_executable() -> None:
    mode = pathlib.Path(diff.repo(), ".ci/rediacc_ci/env/create_e2e_env.py").stat().st_mode
    assert mode & 0o111 == 0o111, "the port must be executable on disk, like its twin"


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


def test_dirname_is_not_os_path_dirname() -> None:
    """The one case that makes the hand-written version necessary."""
    assert os.path.dirname("a/") == "a"
    assert port.dirname("a/") == "."


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
    workdir = tmp_path / "globdir"
    workdir.mkdir()
    for filename in ("f1", "f2", "f3", "f4", "f5"):
        (workdir / filename).write_text("", encoding="utf-8")
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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_dropped_key_is_caught_only_by_the_file(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Drop one key from the generated file.

    The three progress lines say nothing about the file's contents, so a template that quietly loses `NODE_ENV=test` prints exactly what the recording prints and exits 0. `--- file ---` is the only section that sees it, which is why the recorded shape carries the file at all.

    The mutant is a throwaway copy invoked by path, resolving `rediacc_ci` through the same `PYTHONPATH`; the tracked port is never touched.
    """
    source = pathlib.Path(diff.repo(), ".ci/rediacc_ci/env/create_e2e_env.py")
    original = source.read_text(encoding="utf-8")
    anchor = "NODE_ENV=test\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "")

    mutant = tmp_path / "plant" / "create_e2e_env.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "flag-defaults"
    want = recorded(name)
    got = run(tmp_path / "planted", name, subject="python3 %s" % shlex.quote(str(mutant)))
    assert "NODE_ENV=test" in want[3], "the recorded corpus moved"
    assert got[3] is not None
    assert "NODE_ENV=test" not in got[3], "the plant did not change the file"
    assert got[:3] == want[:3], "only the written file may differ, and it is what catches this"

    compare(tmp_path / "good", name)
    assert source.read_text(encoding="utf-8") == original
