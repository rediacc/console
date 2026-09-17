"""`rediacc_ci.log` against `.ci/scripts/lib/common.sh`, byte for byte.

THE THING BEING REPLACED is `.ci/scripts/lib/common.sh:18-55`: the colour block and the five `log_*` functions. It is the canonical bash logger -- 47 files under
`.ci` assign their own `RED=`, but common.sh's is the one every library in
`.ci/lib/` inherits (`local-common.sh:21` and `service.sh:14` both source it, and `run.sh:20` sources local-common.sh), and it is the only variant that tests the stream it actually writes to.

HOW EQUIVALENCE IS PROVEN. Not by reading both and agreeing they look alike. A bash child runs the REAL common.sh, with stdout and stderr captured SEPARATELY and, where the case needs one, a real pseudo-terminal on stderr. The bytes it produced are compared against the bytes `rediacc_ci.log` produces under the same conditions. That is the shape
`.ci/scripts/quality/check-python-lint.sh` uses for its own control: build a specimen, run the instrument, compare.

WHY THE STREAMS ARE NEVER MERGED. The defect these tests exist to prevent is a stream swap -- `emit-advisory.sh` moved log_info from stderr to stdout on 2026-09-06 and nothing noticed. `test-emit-advisory.sh:100-102` says it plainly: "The defect is a stream swap; the `2>&1` used by every case above merges the two streams back together and would hide it completely."

THE TWO DIVERGENCES ARE ASSERTED, NOT AVOIDED. A differential that only tests where two implementations agree is a differential that will be quietly broken by the first person who "fixes" a difference nobody wrote down. Both places where this module deliberately differs from common.sh have a test asserting the difference in both directions.
"""

import io
import subprocess

import pytest

from rediacc_ci import log
from rediacc_ci.tests import differential as diff


@pytest.fixture(autouse=True)
def _no_global_logger_leak():
    """Drop the module-global logger after every test in this file.

    THE LEAK THIS CLOSES, and it is a real order-dependence bug that predates any parallelism. `log.reset()` binds `sys.stderr` BY VALUE into `_default` (log.py:266). Called from a test where pytest's `capsys` has replaced `sys.stderr`, the global keeps a reference to that test's `CaptureIO`. Teardown closes it, and every later `log.*` in the same PROCESS then raises `ValueError:
    I/O operation on closed file` at log.py:209 -- `emit` suppresses ValueError around `flush()` but not around `write()`.

    It was invisible serially for a reason that is pure luck: a later test in this same file, `test_reset_replaces_the_default_and_returns_it`, has no `capsys` and happened to heal the global on its way past. Reproduced with no xdist at all, two tests in order -- `1 failed, 1 passed`; insert the healer between them and it is `3 passed`.

    `None` rather than a stream is the correct reset, because `default()` is documented to build LAZILY against the live `sys.stderr`; handing it a stream here would just move the same stale binding one step later.
    """
    yield
    log._default = None


# The library under differential test, and the exact calls made against it. One constant so every case drives the SAME script and a case cannot silently test a different message than the one it compares.
COMMON_SH = ".ci/scripts/lib/common.sh"

# `log_error a b` rather than `log_error "a b"` on purpose: the 2026-09-06 incident included `log_error` interpolating "$1" instead of "$*", which silently dropped every argument after the first. A single-argument call cannot see that, so the differential passes two.
BASH_CALLS = (
    """
source %s
log_info hello world
log_warn careful now
log_error a b
log_step doing a thing
"""
    % COMMON_SH
)

PYTHON_CALLS = [
    ("info", "hello world"),
    ("warn", "careful now"),
    ("error", "a b"),
    ("step", "doing a thing"),
]


def python_side(colour: bool) -> str:
    """The same four calls through rediacc_ci.log. Returns what it wrote."""
    logger, buf = log.capture(colour=colour)
    for level, message in PYTHON_CALLS:
        logger.emit(level, message)
    return buf.getvalue()


# --------------------------------------------------------------------------- The differential proper ---------------------------------------------------------------------------


def test_off_tty_bytes_are_identical():
    """No tty anywhere: both sides print the glyph and the message, uncoloured."""
    rc, _out, err = diff.bash_streams(BASH_CALLS, env=diff.env_for(CI=None, NO_COLOR=None))
    assert rc == 0
    assert err == python_side(colour=False)


def test_off_tty_stdout_stays_empty_on_both_sides():
    """A gate's stdout is DATA. Nothing a logger emits may land there.

    The bash side is the real regression: this is what `emit-advisory.sh` broke. The Python side is structural -- `Logger` has no stdout path at all -- but it is asserted rather than argued, because "it cannot happen" is what the bash library's author believed too.
    """
    _, out, _ = diff.bash_streams(BASH_CALLS, env=diff.env_for(CI=None, NO_COLOR=None))
    assert out == ""
    logger, buf = log.capture(colour=True)
    logger.info("x")
    assert buf.getvalue()  # it went somewhere
    assert diff.escape_bytes(out) == 0


def test_on_a_stderr_tty_bytes_are_identical():
    """A real pseudo-terminal on stderr: both sides colour, with the same codes.

    This is the case that proves the palette matches. RED/GREEN/YELLOW/BLUE are each compared as raw bytes, so the `\\033[1;33m` versus `\\033[0;33m` disagreement between common.sh and .ci/bootstrap.sh cannot be inherited silently -- picking the wrong one turns this red.
    """
    rc, out, err = diff.bash_streams(
        BASH_CALLS, env=diff.env_for(CI=None, NO_COLOR=None), tty="stderr"
    )
    assert rc == 0
    assert err == python_side(colour=True)
    assert out == ""


def test_on_a_stderr_tty_the_output_really_is_coloured():
    """CONTROL FOR THE CASE ABOVE.

    Without this, a pty that silently failed to attach would make both sides uncoloured, they would still match, and the comparison would prove nothing. Every differential needs the control that says the interesting branch was the one taken.
    """
    _, _, err = diff.bash_streams(
        BASH_CALLS, env=diff.env_for(CI=None, NO_COLOR=None), tty="stderr"
    )
    assert diff.escape_bytes(err) > 0
    assert log.GREEN in err
    assert log.YELLOW in err
    assert log.RED in err
    assert log.BLUE in err


def test_no_color_disables_it_on_both_sides_even_on_a_tty():
    """NO_COLOR is the cross-tool convention, and both sides honour it."""
    env = diff.env_for(CI=None, NO_COLOR="1")
    _, _, err = diff.bash_streams(BASH_CALLS, env=env, tty="stderr")
    assert diff.escape_bytes(err) == 0
    assert err == python_side(colour=False)
    assert log.colour_allowed(io.StringIO(), env) is False


def test_stdout_tty_with_a_piped_stderr_stays_uncoloured_on_both_sides():
    """The bug in the 11-file `[ -t 1 ]` variant, proven absent from both.

    common.sh gates on `-t 2` and writes to fd 2, so a tty on stdout does not make it colour. `rediacc_ci.log` tests the stream it writes to, so neither does it. The eleven files listed in the module docstring WOULD colour here, and the next test plants that variant to show the difference is real.
    """
    _, _, err = diff.bash_streams(
        BASH_CALLS, env=diff.env_for(CI=None, NO_COLOR=None), tty="stdout"
    )
    assert diff.escape_bytes(err) == 0
    assert err == python_side(colour=False)


def test_planted_the_eleven_file_variant_does_colour_here():
    """CONTROL: the bug this module fixes is reproducible, so its absence means something.

    The block below is `.ci/scripts/quality/check-toolchain-pins.sh:30-37`'s
    condition -- `[ -t 1 ] && [ -z "${NO_COLOR:-}" ]` -- writing to stderr, which
    is what those eleven files do. With a tty on stdout and a pipe on stderr it paints escape sequences into the pipe. If this ever stops reproducing, the test above has become a check that cannot fail.
    """
    planted = r"""
RED=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then RED=$'\033[0;31m'; NC=$'\033[0m'; fi
printf '%sx%s\n' "$RED" "$NC" >&2
"""
    _, _, err = diff.bash_streams(planted, env=diff.env_for(CI=None, NO_COLOR=None), tty="stdout")
    assert diff.escape_bytes(err) == 2, "the planted V1 variant must colour a piped stderr"


def test_ci_true_off_a_tty_agrees():
    """Under CI with no tty -- the real CI shape -- both sides are uncoloured."""
    env = diff.env_for(CI="true", NO_COLOR=None)
    _, _, err = diff.bash_streams(BASH_CALLS, env=env)
    assert err == python_side(colour=False)
    assert diff.escape_bytes(err) == 0


def test_ci_true_is_the_one_deliberate_divergence():
    """CI=true WITH a tty: common.sh colours, this module does not. On purpose.

    common.sh tests only `-t 2` and NO_COLOR; it has no CI clause at all. This module has one, because GitHub's log viewer renders escape sequences as literal text (`emit-advisory.sh:22` states exactly that), and because a
    devbox with CI=true exported is a real place where a tty and CI coexist.

    BOTH SIDES ARE ASSERTED so the divergence is a recorded decision. If someone later adds a CI clause to common.sh, this test fails and the two can be reconciled deliberately rather than drifting into agreement unnoticed.
    """
    env = diff.env_for(CI="true", NO_COLOR=None)
    _, _, err = diff.bash_streams(BASH_CALLS, env=env, tty="stderr")
    assert diff.escape_bytes(err) > 0, "common.sh still colours under CI on a tty"
    assert err != python_side(colour=False)
    assert err == python_side(colour=True), "the only difference is the CI decision itself"
    assert log.colour_allowed(io.StringIO(), env) is False


def test_bash_interprets_escapes_in_the_message_and_python_does_not():
    """The second divergence: a bug dropped rather than a decision made.

    common.sh logs with `echo -e`, which expands backslash escapes in the MESSAGE body. A Windows path or a regex printed through it is silently mangled. This module formats the message as data.

    Asserted in both directions so nobody "fixes" the Python to match bash.
    """
    _, _, err = diff.bash_streams(
        r"""source %s; log_error 'C:\tmp\new'""" % COMMON_SH,
        env=diff.env_for(CI=None, NO_COLOR=None),
    )
    assert "\t" in err, "bash's echo -e expanded \\t in the message body"
    assert "\\t" not in err

    logger, buf = log.capture(colour=False)
    logger.error(r"C:\tmp\new")
    assert buf.getvalue() == "\u2717 C:\\tmp\\new\n"
    assert "\t" not in buf.getvalue()


def test_debug_is_silent_unless_debug_is_the_string_true():
    """`DEBUG=true` exactly, matching common.sh:52. Differential on all three states."""
    script = "source %s; log_debug secret" % COMMON_SH
    for value, expect_output in (("true", True), ("1", False), (None, False)):
        env = diff.env_for(CI=None, NO_COLOR=None, DEBUG=value)
        _, _, err = diff.bash_streams(script, env=env)
        assert bool(err) is expect_output, "bash DEBUG=%r" % value

        buf = io.StringIO()
        log.Logger(stream=buf, colour=False, env=env).debug("secret")
        assert bool(buf.getvalue()) is expect_output, "python DEBUG=%r" % value
        assert err == buf.getvalue()


def test_the_differential_harness_can_tell_the_two_streams_apart():
    """CONTROL FOR THE HARNESS ITSELF.

    Every case above rests on `bash_streams` returning stdout and stderr in the right slots. A harness that returned them swapped, or merged, would make the stream assertions vacuous while everything still looked green.
    """
    rc, out, err = diff.bash_streams("printf OUT; printf ERR >&2; exit 3")
    assert (rc, out, err) == (3, "OUT", "ERR")
    rc, out, err = diff.bash_streams("printf OUT; printf ERR >&2", tty="stderr")
    assert (out, err) == ("OUT", "ERR")
    rc, out, err = diff.bash_streams("printf OUT; printf ERR >&2", tty="stdout")
    assert (out, err) == ("OUT", "ERR")


def test_the_differential_harness_does_not_leak_the_callers_environment():
    """CONTROL: `env_for` REPLACES. A leaked CI or NO_COLOR would flip cases silently."""
    _, out, _ = diff.bash_streams(
        'echo "[${CI:-unset}][${NO_COLOR:-unset}][${REDIACC_CI_ROOT:-unset}]"',
        env=diff.env_for(),
    )
    assert out.strip() == "[unset][unset][unset]"


# --------------------------------------------------------------------------- The module's own behaviour, where a differential has nothing to compare to ---------------------------------------------------------------------------


def test_colour_allowed_needs_all_three_conditions():
    """Each condition alone is sufficient to say no."""

    class FakeTty(io.StringIO):
        def isatty(self):
            return True

    tty = FakeTty()
    assert log.colour_allowed(tty, diff.env_for()) is True
    assert log.colour_allowed(tty, diff.env_for(NO_COLOR="1")) is False
    assert log.colour_allowed(tty, diff.env_for(CI="true")) is False
    assert log.colour_allowed(io.StringIO(), diff.env_for()) is False


def test_ci_is_compared_to_the_literal_string_true():
    """`CI=1` and `CI=false` are not `CI=true`, matching every bash variant."""

    class FakeTty(io.StringIO):
        def isatty(self):
            return True

    for value in ("1", "false", "TRUE", ""):
        assert log.colour_allowed(FakeTty(), diff.env_for(CI=value)) is True, value


def test_a_stream_without_isatty_is_not_a_tty():
    """A logger is where things go wrong, so it must not be the thing that crashes."""

    class Bare:
        def write(self, _text):
            return None

    assert log.colour_allowed(Bare(), diff.env_for()) is False


def test_a_closed_stream_is_not_a_tty():
    """`isatty()` on a closed file RAISES ValueError rather than answering False."""
    handle = io.StringIO()
    handle.close()
    assert log.colour_allowed(handle, diff.env_for()) is False


def test_format_returns_the_line_without_a_newline():
    """Separated from writing so a differential can compare strings, not streams."""
    logger = log.Logger(stream=io.StringIO(), colour=False)
    assert logger.format("error", "boom") == "\u2717 boom"
    assert "\n" not in logger.format("error", "boom")


def test_the_coloured_form_wraps_only_the_glyph():
    """common.sh:43 is `${RED}✗${NC} $*` -- the message is NOT inside the colour.

    emit-advisory.sh:71 wraps the whole message instead (`${RED}✗ $*${NC}`), and
    that difference is exactly how the two libraries produced different bytes for the same call. This module follows common.sh, and the differential above would catch a change; this states it locally so the reason is readable.
    """
    logger = log.Logger(stream=io.StringIO(), colour=True)
    assert logger.format("error", "boom") == log.RED + "\u2717" + log.NC + " boom"


def test_success_uses_the_same_glyph_and_colour_as_info():
    """common.sh has no log_success; emit-advisory.sh:74 supplies it as GREEN ✓."""
    logger = log.Logger(stream=io.StringIO(), colour=True)
    assert logger.format("success", "x") == logger.format("info", "x")


def test_an_unknown_level_raises_rather_than_printing_something():
    """A typo'd level is a caller defect, and a silent fallback hides it forever."""
    logger = log.Logger(stream=io.StringIO(), colour=False)
    with pytest.raises(KeyError):
        logger.format("critical", "x")


def test_every_level_writes_to_the_bound_stream_and_nowhere_else(capsys):
    """No level has a stray print. Checked with pytest's own capture."""
    logger, buf = log.capture(colour=False)
    for level in ("info", "success", "warn", "error", "step"):
        getattr(logger, level)(level)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert buf.getvalue().count("\n") == 5


def test_the_module_functions_go_to_stderr_not_stdout(capsys):
    """The module-level shorthand must have the same stream discipline."""
    log.reset(colour=False)
    log.info("m")
    log.warn("m")
    log.error("m")
    log.step("m")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 4
    log.reset()


def test_the_default_logger_is_built_lazily_against_the_current_stderr(capsys):
    """A logger constructed at import captures the wrong stream under capture.

    pytest's capsys, `contextlib.redirect_stderr` and a subprocess wrapper all REPLACE sys.stderr after import. `default()` therefore builds on first use.
    """
    log._default = None
    log.error("late")
    assert "late" in capsys.readouterr().err
    log.reset()


def test_reset_replaces_the_default_and_returns_it():
    logger = log.reset(stream=io.StringIO(), colour=False)
    assert log.default() is logger
    log.info("routed")
    assert "routed" in logger.stream.getvalue()
    log.reset()


def test_capture_defaults_to_no_colour():
    """Otherwise every assertion would depend on the test runner having a tty."""
    logger, _ = log.capture()
    assert logger.colour is False


def test_the_palette_matches_common_sh_byte_for_byte():
    """Read the escape sequences straight out of the bash file and compare.

    This is a SECOND, independent check on the palette: the differential above compares rendered output, this compares the source constants. It catches the
    case where both sides are wrong in the same way because someone edited them
    together.
    """
    with open("%s/%s" % (diff.repo(), COMMON_SH), encoding="utf-8") as handle:
        text = handle.read()
    block = text.split("log_info()")[0]
    for name, value in (
        ("RED", log.RED),
        ("GREEN", log.GREEN),
        ("YELLOW", log.YELLOW),
        ("BLUE", log.BLUE),
        ("CYAN", log.CYAN),
        ("NC", log.NC),
    ):
        literal = "%s='%s'" % (name, value.replace("\033", "\\033"))
        assert literal in block, "%s does not match %s" % (name, COMMON_SH)


def test_common_sh_is_actually_there():
    """ANTI-VACUITY. Every differential above sources this file.

    `source` of a missing file under `set -e` would abort the child, the child would print nothing, and a comparison against a Python side that also printed nothing... would not arise, because the Python side always prints. But the two DEBUG-off cases compare empty to empty, and those would pass on a tree where common.sh had been deleted. This is the base case under that.
    """
    path = "%s/%s" % (diff.repo(), COMMON_SH)
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    assert "log_info()" in body
    assert "log_debug()" in body
    assert body.count("log_") >= 10


def test_bash_is_available_at_all():
    """ANTI-VACUITY for the harness: a missing bash makes every case throw, but a future refactor that caught the exception would make them all pass."""
    proc = subprocess.run(["bash", "-c", "echo alive"], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "alive"
