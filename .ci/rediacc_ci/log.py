"""The one logger. Colour only on a tty, messages only on stderr.

WHAT IT REPLACES, MEASURED 2026-09-06. There are 47 files under `.ci` that
assign a `RED=` themselves, and the conditions they gate that assignment on do
not agree. Counted by grepping the assignment and its guard:

    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]                       11 files
    if [[ "${CI:-}" == "true" ]]; then RED="" ... else ...        9 files
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${CI:-}" != "true" ]
                                                                 1 file (.ci/bootstrap.sh)
    if [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]      .ci/scripts/lib/common.sh:18
                                                   .ci/breakpoint/lib/breakpoint-common.sh:37

Read the first three rows next to the fourth and the disagreement is not
cosmetic. The 11-file variant tests **stdout** for a tty and then writes its
coloured message to **stderr**, so redirecting stdout to a file while watching
stderr in a terminal produces uncoloured output, and the reverse produces escape
sequences in the file. The 9-file variant tests CI and nothing else, so a
developer piping a gate into `less` gets escapes. Only `common.sh` tests the
stream it actually writes to, and it is the only one that ignores CI.

The colour VALUES disagree too: `YELLOW` is `\\033[1;33m` in `common.sh` and
`\\033[0;33m` in `.ci/bootstrap.sh`. Both are "yellow"; neither file knows the
other exists.

THE INCIDENT THIS MODULE IS SHAPED BY (2026-09-06, recorded verbatim at
`.ci/scripts/lib/emit-advisory.sh:22-50` and pinned by
`.ci/scripts/test/gates/test-emit-advisory.sh:85-105`). `emit-advisory.sh` used
to assign RED/GREEN/YELLOW/NC and define log_error / log_success / log_warn /
log_info UNCONDITIONALLY. Four quality gates -- check-profiler-coverage.sh,
check-swallowed-failures.sh, check-ci-job-aggregation.sh and check-go-deps.sh --
source `common.sh` first and then reach `emit-advisory.sh` transitively through
`blocker-validator.sh:26`, so the later definitions won and silently replaced
common.sh's TTY-gated logger. Two consequences:

  1. log_info / log_warn / log_success moved from stderr to STDOUT, so a gate
     whose stdout a caller pipes for data got colour escapes mixed into that
     pipe.
  2. log_error interpolated `"$1"` rather than `"$*"`, so `log_error a b`
     printed only `a` and silently dropped the rest.

`check-pool-writer-safety.sh` sources only common.sh, never reaches
blocker-validator.sh, and so was never affected -- which is why nothing noticed.

The fix there was a deference rule: every assignment guarded with `${RED+x}` and
every definition guarded with `declare -F`. That is the correct repair for two
libraries that must coexist. It is not a design; it is two implementations
agreeing to take turns. THIS module is the design: one implementation, imported
rather than sourced, so there is no second definition to defer to.

THE THREE RULES, and why each is not negotiable.

  STDERR, ALWAYS. A gate's stdout is DATA. `.ci/breakpoint/lib/breakpoint-common.sh:52`
  states it for its own callers -- "several breakpoint scripts put their real
  result (a URL, a mode, a descriptor) on stdout" -- and consequence 1 above is
  what happens when a logger forgets. There is deliberately no `stream=` argument
  and no `to_stdout` flag: an option is a thing a caller gets wrong.

  COLOUR ONLY ON A TTY, AND THE TTY TESTED IS THE ONE WRITTEN TO. Testing stdout
  while writing to stderr is the 11-file variant's bug, and it is invisible until
  someone redirects exactly one of the two.

  NO_COLOR AND CI BOTH DISABLE IT. NO_COLOR is the cross-tool convention
  (no-color.org: any value, including empty, disables). CI is this repo's own,
  and it matters because GitHub's log viewer renders escape sequences as
  literal text -- `emit-advisory.sh:22` says so in one line.

THE DELIBERATE DIVERGENCE FROM common.sh, stated out loud rather than discovered
later. Under `CI=true` with stderr attached to a tty, common.sh emits colour and
this module does not. That combination is rare (a CI runner rarely has a tty) but
it is real in a devbox with `CI=true` exported, and it is the case where the two
implementations genuinely disagree rather than merely differing in spelling.
`tests/test_log.py::test_ci_true_is_the_one_deliberate_divergence` asserts BOTH
sides of it, so the divergence is a pinned decision instead of a surprise.

A SECOND DIVERGENCE, and this one is a bug being dropped rather than a decision.
common.sh logs with `echo -e`, which interprets backslash escapes IN THE MESSAGE:
`log_error 'C:\tmp\new'` prints a tab and a newline. This module formats the
message as data. The differential test asserts the two disagree there, so a
future reader does not "fix" the Python to match.

USAGE. The module-level functions use one process-wide logger and are what a
gate wants:

    from rediacc_ci import log
    log.info("linting %d file(s)" % n)
    log.error("ruff reported findings")

A caller that needs a second, independently configured logger -- a test
capturing output, a sub-run whose colour must be forced off -- constructs one:

    buf = io.StringIO()
    Logger(stream=buf, colour=False).warn("...")
"""

import contextlib
import io
import os
import sys

# The escape sequences, taken from .ci/scripts/lib/common.sh:19-24, which is the
# only pre-existing variant that tests the stream it writes to and is therefore
# the one this module is differentially checked against. YELLOW is the bright
# form (1;33) that common.sh uses, NOT the 0;33 in .ci/bootstrap.sh: a
# differential cannot be run against both, so the one with more callers wins and
# the other is named here so the choice is visible rather than accidental.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"

# The glyph and colour per level, matching common.sh:35-54 exactly so a ported
# script's output is byte-identical. `success` is the one level common.sh does
# not define -- it comes from emit-advisory.sh:74, which is precisely the file
# whose unconditional definitions caused the incident above, so it is carried
# here to remove the reason that library had to define anything at all.
_LEVELS = {
    "info": (GREEN, "\u2713"),
    "success": (GREEN, "\u2713"),
    "warn": (YELLOW, "\u26a0"),
    "error": (RED, "\u2717"),
    "step": (BLUE, "\u2192"),
    "debug": (CYAN, "[DEBUG]"),
}

# The environment variable that turns on debug output, and its truth value.
# `"true"` exactly, not any truthy string: common.sh:52 tests
# `"${DEBUG:-false}" == "true"`, and a Python port that accepted "1" would be
# quietly noisier than the thing it replaces on any machine where DEBUG=1 is set
# for some other tool.
DEBUG_ENV = "DEBUG"
DEBUG_ON = "true"


def colour_allowed(stream=None, env=None) -> bool:
    """Should THIS stream carry colour?

    Three conditions, all required. Stated as one function so there is one place
    to read the answer, and so a caller can ask without a Logger.

    NO_COLOR IS TESTED FOR PRESENCE, NOT TRUTH. no-color.org specifies that the
    variable disables colour when it is present with ANY value, and every bash
    variant in this repo agrees (`[ -z "${NO_COLOR:-}" ]` is a presence test on
    a non-empty value). The one gap: `NO_COLOR=` (set but empty) is `-z` in bash
    and would be falsy here too, so the two agree by accident of the same rule.

    A STREAM WITHOUT isatty IS NOT A TTY. io.StringIO has the method; a mock or
    a file-like without it must not crash a logger, because the place a logger
    crashes is the place something has already gone wrong.
    """
    environ = os.environ if env is None else env
    if environ.get("NO_COLOR"):
        return False
    if environ.get("CI") == "true":
        return False
    target = sys.stderr if stream is None else stream
    try:
        return bool(target.isatty())
    except (AttributeError, ValueError):
        # ValueError: a closed file raises rather than answering. "Not a tty" is
        # the safe answer for both, because escapes written to something broken
        # are the failure mode that outlives the run, in a log file.
        return False


class Logger:
    """A logger bound to one stream, with colour decided once at construction.

    DECIDED ONCE, ON PURPOSE. Re-testing `isatty()` per message would be more
    "correct" and would make a long run's output inconsistent if something
    reopened the stream mid-flight. It would also make every message pay a
    syscall. The bash originals decide once at source time; this matches them.

    `colour=None` means decide; `True` and `False` force it, which is what the
    differential test needs in order to compare bytes without a pty for every
    case.
    """

    def __init__(self, stream=None, colour: bool | None = None, env=None) -> None:
        # `stream=None` IS RESOLVED AT EMIT TIME, NOT HERE, and that is the whole
        # point of the property below. This line used to read
        #     self.stream = sys.stderr if stream is None else stream
        # which captured whatever `sys.stderr` happened to be at CONSTRUCTION.
        # Under pytest's `capsys` that is a per-test CaptureIO which teardown then
        # CLOSES, so a module-global logger built during one test kept writing to
        # a dead file and every later `log.*` in the process raised
        # `ValueError: I/O operation on closed file` from `emit`.
        #
        # It was invisible serially because a later test in the same file happened
        # to rebuild the global; xdist distributes a module across processes, so
        # the healer and the poisoner land in different workers. It was then
        # patched module-by-module with autouse fixtures -- test_log.py and two
        # others -- which left every OTHER module unprotected and the class
        # unfixed. This is the root: an explicit stream is still bound by value,
        # exactly as callers expect, and only the None case follows sys.stderr.
        self._stream = stream
        self.env = os.environ if env is None else env
        self.colour = colour_allowed(self.stream, self.env) if colour is None else colour

    @property
    def stream(self):
        """The live stream. `sys.stderr` NOW when built with `stream=None`."""
        return sys.stderr if self._stream is None else self._stream

    def format(self, level: str, message: str) -> str:
        """The exact line, WITHOUT its trailing newline.

        Separated from writing so the differential test can compare the string a
        Logger would produce against the bytes bash produced, without owning a
        stream. `KeyError` on an unknown level is deliberate and unhandled: a
        typo'd level name is a defect in the caller, and a logger that silently
        prints an unformatted line for it hides the typo forever.
        """
        colour, glyph = _LEVELS[level]
        if not self.colour:
            return "%s %s" % (glyph, message)
        return "%s%s%s %s" % (colour, glyph, NC, message)

    def emit(self, level: str, message: str) -> None:
        """Write one line and flush.

        FLUSHED EVERY TIME. stderr is unbuffered only when it is a tty; redirected
        to a file it is block-buffered, so a gate that dies mid-run loses exactly
        the messages that would say why. That is the one place a logger's output
        matters most, so the flush is not optional and there is no `flush=`
        argument to get wrong.
        """
        self.stream.write(self.format(level, message) + "\n")
        # A stream without flush(), or a closed one, must not turn a log line into
        # a traceback: the place a logger is called is the place something has
        # already gone wrong.
        with contextlib.suppress(AttributeError, ValueError):
            self.stream.flush()

    def info(self, message: str) -> None:
        self.emit("info", message)

    def success(self, message: str) -> None:
        self.emit("success", message)

    def warn(self, message: str) -> None:
        self.emit("warn", message)

    def error(self, message: str) -> None:
        self.emit("error", message)

    def step(self, message: str) -> None:
        self.emit("step", message)

    def debug(self, message: str) -> None:
        """Silent unless DEBUG=true, matching common.sh:51-55.

        The gate is read from the environment at CALL time, not construction,
        because a program that sets DEBUG for a section of its own run is a real
        pattern and a logger constructed at import would have missed it.
        """
        if self.env.get(DEBUG_ENV, "false") == DEBUG_ON:
            self.emit("debug", message)


# The process-wide default. Constructed lazily rather than at import, because a
# module-level Logger would capture whatever sys.stderr was at import time --
# and pytest's capsys, a subprocess wrapper and `contextlib.redirect_stderr` all
# REPLACE sys.stderr afterwards. A captured stream is the classic reason a test
# sees no output from a logger that is working perfectly.
_default: Logger | None = None


def default() -> Logger:
    """The shared Logger, built on first use against the current sys.stderr."""
    global _default  # noqa: PLW0603
    if _default is None:
        _default = Logger()
    return _default


def reset(stream=None, colour: bool | None = None, env=None) -> Logger:
    """Rebuild the default logger. Returns it.

    Exists for two callers: a test that has just swapped sys.stderr, and a
    program that has parsed `--no-color` from its own argv and must apply the
    answer to a logger some imported module already used.
    """
    global _default  # noqa: PLW0603
    _default = Logger(stream=stream, colour=colour, env=env)
    return _default


def info(message: str) -> None:
    default().info(message)


def success(message: str) -> None:
    default().success(message)


def warn(message: str) -> None:
    default().warn(message)


def error(message: str) -> None:
    default().error(message)


def step(message: str) -> None:
    default().step(message)


def debug(message: str) -> None:
    default().debug(message)


def capture(colour: bool = False) -> tuple[Logger, io.StringIO]:
    """A Logger writing into a fresh buffer, plus the buffer.

    A two-line convenience that exists because every test of anything that logs
    needs it, and because writing it by hand invites `colour=None`, which makes
    the assertion depend on whether the test runner happens to have a tty.
    """
    buf = io.StringIO()
    return Logger(stream=buf, colour=colour), buf


__all__ = [
    "BLUE",
    "CYAN",
    "DEBUG_ENV",
    "DEBUG_ON",
    "GREEN",
    "NC",
    "RED",
    "YELLOW",
    "Logger",
    "capture",
    "colour_allowed",
    "debug",
    "default",
    "error",
    "info",
    "reset",
    "step",
    "success",
    "warn",
]
