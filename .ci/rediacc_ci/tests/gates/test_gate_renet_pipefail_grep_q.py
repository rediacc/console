"""`private/renet/.ci/scripts/quality/pipefail-grep-q.sh`, driven from console.

renet carries its own BASH copy of the pipefail/`grep -q` detector, and that copy
is correct as bash: renet is required to work standalone, so a `sys.path` reach
into console's `.ci` would make the gate silently skip in exactly the case the
rest of that directory is built for. A third implementation of a detector this
repo already keeps as a bash/Python twin pair drifts unless something holds it,
and THIS FILE IS THAT SOMETHING. It pins two things:

  1. the detector's CONTRACT, driven against the renet script's own `offenders()`
     (reachable because the script guards its main block with
     `[[ "${BASH_SOURCE[0]}" == "${0}" ]]`), so the twelve directions its
     in-script controls assert are asserted from console too and a renet-side
     regression reds console CI rather than only renet's own stage;

  2. PRODUCER-LIST PARITY, one-directional on purpose: renet's
     `SCALING_PRODUCERS` must be a SUPERSET of console's. Superset, not equality,
     because renet may legitimately be AHEAD -- it was, by `tee` and `docker`,
     between the commit that added it and the console widening that followed. The
     direction that costs a MISSED DEFECT is console widening and renet not
     following, and that is the one this reds on.

Console's list is read by IMPORTING the shipped port
(`rediacc_ci.quality.pipefail_grep_q`), never by re-parsing its source: a test
that re-derives a value from the same text it is checking can agree with a typo.

NO `BASH_TWIN`, AND THAT IS NOT THE COEXISTENCE RULE BEING SKIPPED. This package's
`__init__` says a bash original is deleted by a LATER change than the one that
ports it, so both can be driven against each other for a while. There is no bash
original here to keep. A `.ci/scripts/test/gates/test-renet-pipefail-grep-q.sh`
existed for exactly one commit (eda35491a) before Ruling 7 (2026-09-06) caught it
-- `.ci` and `.claude` are Python trees and that surface may shrink but never grow
-- so it was written in Python instead and the bash file deleted in the same change
that added this one. Nothing was ported, so there is nothing to hold parity with,
and this module joins the nine others here that carry no twin.

WHY THE SUBJECT IS SOURCED RATHER THAN EXECUTED. Running the script outright runs
the real gate over the real renet tree, which is renet's own stage's job, not this
one's. Sourcing skips main and pulls `offenders`, `SCALING_PRODUCERS` and
`RENET_EXTRA_PRODUCERS` into scope. A Python port has no shell to source into, so
each case is one fresh `bash -c`; that is in the port's favour, since nothing a
case leaves behind can leak into the next.

THE FIXTURES ARE ASSEMBLED AT RUNTIME, out of `GQ` and `PF`, for exactly the
reason the renet script assembles its own that way: written out literally, this
file's text would carry the racing shape contiguously. `.ci/**` is inside
`check:ci-pipefail-grep-q`'s corpus, so a gate test that commits the defect it
polices would be found by that gate -- correctly.

NO `xdist_group`. Every case writes into pytest's own `tmp_path` and runs one
short-lived `bash -c`; nothing is bound, no module global is mutated, and both
subjects are only ever read.
"""

from rediacc_ci import paths
from rediacc_ci.quality.pipefail_grep_q import SCALING_PRODUCERS as CONSOLE_PRODUCERS
from rediacc_ci.tests.gates import harness

RENET_GATE = paths.from_root(
    "private", "renet", ".ci", "scripts", "quality", "pipefail-grep-q.sh"
)

# Assembled, never written contiguously. See the module docstring.
GQ = "grep -q"
PF = "set -o pipefail"

# The floor under the IMPORT, not under the comparison. An import that returned
# nothing would make the superset assertion trivially true, which is the
# "a check that cannot fail" shape this whole directory exists to refuse. Console's
# list was 18 names when this was written and 20 after the tee/docker widening; ten
# is comfortably below either and well above zero.
MIN_CONSOLE_PRODUCERS = 10


def source_and_run(gate, code: str) -> harness.RunResult:
    """Source the renet subject in a fresh bash and run one call, streams MERGED.

    Merged because renet's `common.sh` writes its log lines to stderr while the
    assertions here care only about what `offenders` printed on stdout; keeping
    them apart would still work, but `.combined` is what makes a failure message
    show the log line that explains it.

    A MISSING SUBJECT IS A FAILURE, NOT A SKIP. `check:ci-pytest` runs in
    `quality-security`, whose checkout sets `submodules: true`, so the absent
    submodule is not a state CI reaches -- and a case that could not run has not
    been checked.
    """
    if not RENET_GATE.is_file():
        gate.log_fail(
            "the subject is missing at %s, so not one case below could run -- which is a "
            "FAILURE and not a pass. Fix: git submodule update --init private/renet"
            % paths.relative_to_root(RENET_GATE)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a bash library")
    return harness.run([bash, "-c", "source '%s'\n%s" % (RENET_GATE, code)])


def offenders_of(gate, tmp_path, name: str, *lines: str) -> str:
    """Write a fixture script, then print what renet's `offenders()` makes of it.

    `|| true` IS REQUIRED, not defensive noise: `offenders` returns the status of
    its LAST inner grep, which is non-zero exactly when the file is CLEAN. The
    renet gate never notices because it runs under `set +e`. Without this, every
    silent-direction case below would die on the `bash -c` exit status instead of
    asserting on empty output.
    """
    fixture = tmp_path / ("%s.sh" % name)
    fixture.write_text("".join("%s\n" % line for line in lines), encoding="utf-8")
    result = source_and_run(gate, "offenders '%s' || true" % fixture)
    gate.assert_exit_code(0, result.rc, "driving offenders over %s should not crash" % name)
    return result.out


def assert_flagged(gate, tmp_path, name: str, message: str, *lines: str) -> None:
    hits = offenders_of(gate, tmp_path, name, *lines)
    if not hits.strip():
        gate.log_fail(
            "%s -- renet's offenders() returned NOTHING for:\n    %s"
            % (message, "\n    ".join(lines))
        )
    gate.log_pass(message)


def assert_silent(gate, tmp_path, name: str, message: str, *lines: str) -> None:
    hits = offenders_of(gate, tmp_path, name, *lines)
    if hits.strip():
        gate.log_fail("%s -- renet's offenders() flagged it: %s" % (message, hits.strip()))
    gate.log_pass(message)


def renet_list(gate, variable: str) -> list[str]:
    """One of the subject's producer lists, word-split, as the shell sees it."""
    result = source_and_run(gate, 'printf "%%s\\n" "$%s"' % variable)
    gate.assert_exit_code(0, result.rc, "reading $%s out of the subject" % variable)
    return result.out.split()


# ---- 1. the detector contract, twelve directions ----------------------------
#
# The seven FLAGGED cases and the five SILENT ones are the same twelve the renet
# script's own in-script controls assert. Stated from both sides on purpose: a
# gate that can only say yes is half a gate, and an over-broad one gets
# suppressed, which is how a gate dies.


def test_a_local_function_is_flagged(gate, tmp_path):
    gate.log_test("a function the file defines, piped into grep -q under pipefail")
    assert_flagged(
        gate,
        tmp_path,
        "local-fn",
        "a local function piped into grep -q is detected",
        PF,
        'body() { cat "$1"; }',
        'if body "$1" | %s x; then :; fi' % GQ,
    )


def test_a_printf_producer_is_flagged(gate, tmp_path):
    gate.log_test("a BUILTIN producer: printf takes EPIPE, pipefail promotes it")
    assert_flagged(
        gate,
        tmp_path,
        "builtin-printf",
        "a printf producer is detected",
        PF,
        'if printf "%%s" "$x" | %s y; then :; fi' % GQ,
    )


def test_an_echo_producer_is_flagged(gate, tmp_path):
    gate.log_test("the other builtin, for the same reason")
    assert_flagged(
        gate,
        tmp_path,
        "builtin-echo",
        "an echo producer is detected",
        PF,
        'if echo "$x" | %s y; then :; fi' % GQ,
    )


def test_a_scaling_command_producer_is_flagged(gate, tmp_path):
    gate.log_test("a producer that is a COMMAND, not a function this file defines")
    assert_flagged(
        gate,
        tmp_path,
        "command-producer",
        "a scaling COMMAND producer is detected",
        PF,
        'if grep -vE "^x" "$1" | %s needle; then :; fi' % GQ,
    )


def test_a_pipeline_spanning_lines_is_flagged(gate, tmp_path):
    """No single LINE holds both halves, which is how the real one hid.

    console's `check-control-vacuity.sh` offender sat on three separate lines, so
    no per-line regex ever saw a producer and `grep -q` together. `join_logical`
    is what closes that, and this case is what proves it still does.
    """
    gate.log_test("producer on one line, grep -q on the next")
    assert_flagged(
        gate,
        tmp_path,
        "multiline",
        "a pipeline SPANNING LINES is detected",
        PF,
        'grep -vE "^x" "$1" |',
        "    %sE needle" % GQ,
    )


def test_the_tee_extra_is_flagged(gate, tmp_path):
    """One of renet's two extras. Its site was `.ci/scripts/quality/i18n.sh`."""
    gate.log_test("tee is a pure pass-through, so its output scales with its input")
    assert_flagged(
        gate,
        tmp_path,
        "tee-extra",
        "the `tee` extra is detected",
        PF,
        'if cmd 2>&1 | tee "$LOG" | %s ok; then :; fi' % GQ,
    )


def test_the_docker_extra_is_flagged(gate, tmp_path):
    """The other extra. Its sites were both `docker version` calls in ci-test.sh."""
    gate.log_test("docker output scales with the daemon's state, not with a constant")
    assert_flagged(
        gate,
        tmp_path,
        "docker-extra",
        "the `docker` extra is detected",
        PF,
        'if docker ps --format "{{.Names}}" | %s x; then :; fi' % GQ,
    )


def test_the_sanctioned_fix_is_not_flagged(gate, tmp_path):
    """The drop-in the gate's own failure message hands out must not be flagged."""
    gate.log_test("command substitution reads the producer to completion")
    assert_silent(
        gate,
        tmp_path,
        "sanctioned-fix",
        "the sanctioned command-substitution fix is NOT flagged",
        PF,
        'body() { cat "$1"; }',
        'if [ -n "$(body "$1" | grep x)" ]; then :; fi',
    )


def test_without_pipefail_the_shape_is_not_flagged(gate, tmp_path):
    """Without pipefail the pipeline reports grep's status and the match stands."""
    gate.log_test("the same bytes, in a file that never sets pipefail")
    assert_silent(
        gate,
        tmp_path,
        "no-pipefail",
        "without pipefail the same shape is not flagged",
        'body() { cat "$1"; }',
        'if body "$1" | %s x; then :; fi' % GQ,
    )


def test_the_shape_in_a_comment_is_not_flagged(gate, tmp_path):
    """Mention-as-execution: prose describing the shape is not committing it."""
    gate.log_test("the shape inside a # comment")
    assert_silent(
        gate,
        tmp_path,
        "in-comment",
        "the shape inside a # COMMENT is not code",
        PF,
        'body() { cat "$1"; }',
        '# never write: body "$1" | %s x' % GQ,
    )


def test_the_shape_in_a_single_quoted_string_is_not_flagged(gate, tmp_path):
    gate.log_test("the shape inside a single-quoted string literal")
    assert_silent(
        gate,
        tmp_path,
        "in-squote",
        "the shape inside a SINGLE-quoted string is not code",
        PF,
        'body() { cat "$1"; }',
        "advice='run body \"$1\" | %s x instead'" % GQ,
    )


def test_the_shape_in_a_double_quoted_string_is_not_flagged(gate, tmp_path):
    """The blanking that stopped the gate flagging its own message text."""
    gate.log_test("the shape inside a double-quoted string literal")
    assert_silent(
        gate,
        tmp_path,
        "in-dquote",
        "the shape inside a DOUBLE-quoted string is not code",
        PF,
        'body() { cat "$1"; }',
        'advice="run body \\$1 | %s x instead"' % GQ,
    )


# ---- 2. producer-list parity -------------------------------------------------


def test_the_console_import_is_not_empty(gate):
    """THE FLOOR UNDER THE NEXT CASE, and it is not ceremony.

    `test_renet_list_is_a_superset_of_consoles` iterates console's names and
    checks each one. Over an empty list that loop body never runs and the
    assertion passes having compared nothing, which is indistinguishable from
    agreement. This is the case that makes the next one's green mean something.
    """
    gate.log_test("console's SCALING_PRODUCERS imported, and non-trivially so")
    count = len(CONSOLE_PRODUCERS)
    if count < MIN_CONSOLE_PRODUCERS:
        gate.log_fail(
            "imported only %d producer(s) from rediacc_ci.quality.pipefail_grep_q -- the "
            "import is broken, so the superset assertion would pass vacuously" % count
        )
    gate.log_pass("console's list imported: %d name(s)" % count)


def test_renet_list_is_a_superset_of_consoles(gate):
    """The drift direction that costs a missed defect, and only that direction."""
    gate.log_test("renet's SCALING_PRODUCERS must contain every name console has")
    renet = set(renet_list(gate, "SCALING_PRODUCERS"))
    if not renet:
        gate.log_fail("renet's $SCALING_PRODUCERS read back EMPTY, so nothing was compared")
    missing = sorted(set(CONSOLE_PRODUCERS) - renet)
    if missing:
        gate.log_error("  Console widened its list and renet did not follow. That is the drift")
        gate.log_error("  direction that costs a missed defect: the class is now detected in")
        gate.log_error("  console and invisible in the submodule.")
        gate.log_error("  Fix: add them to CONSOLE_SCALING_PRODUCERS in")
        gate.log_error("  private/renet/.ci/scripts/quality/pipefail-grep-q.sh, convert whatever")
        gate.log_error("  sites the widening surfaces there, and bump the submodule pointer.")
        gate.log_fail(
            "renet's SCALING_PRODUCERS is MISSING %d name(s) console has: %s"
            % (len(missing), " ".join(missing))
        )
    gate.log_pass(
        "renet's producer list is a superset of console's (%d console name(s) all present)"
        % len(CONSOLE_PRODUCERS)
    )


def test_every_declared_extra_is_really_in_the_list(gate):
    """`RENET_EXTRA_PRODUCERS` is documentation two headers lean on.

    If an extra is removed from the live list but left named as an extra, the
    declaration and the behaviour disagree silently. This is what stops that.
    """
    gate.log_test("every name renet declares as an extra is really in its live list")
    extras = renet_list(gate, "RENET_EXTRA_PRODUCERS")
    if not extras:
        gate.log_fail(
            "renet's $RENET_EXTRA_PRODUCERS is EMPTY, so this assertion would be vacuous"
        )
    live = set(renet_list(gate, "SCALING_PRODUCERS"))
    bad = sorted(name for name in extras if name not in live)
    if bad:
        gate.log_fail(
            "RENET_EXTRA_PRODUCERS declares %s but SCALING_PRODUCERS does not contain them"
            % " ".join(bad)
        )
    gate.log_pass("every name in RENET_EXTRA_PRODUCERS (%s) is really in the list" % " ".join(extras))
