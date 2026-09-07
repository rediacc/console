"""Port of `.ci/scripts/test/gates/test-emit-advisory.sh`.

`.ci/scripts/lib/emit-advisory.sh`, in two halves that ask different questions.

THE SHAPE OF THE ANNOTATIONS. CI mode emits a `::error::` / `::warning::` prefix,
non-CI mode emits coloured ANSI with the glyphs, and continuation lines fire only
for the hints actually supplied.

THE STREAM AND ARGUMENT REGRESSIONS, found 2026-09-06. emit-advisory.sh used to
assign RED/GREEN/YELLOW/NC and define `log_error` / `log_success` / `log_warn` /
`log_info` UNCONDITIONALLY. Four gates (check-profiler-coverage.sh,
check-swallowed-failures.sh, check-ci-job-aggregation.sh, check-go-deps.sh)
source common.sh first and then reach this library TRANSITIVELY through
blocker-validator.sh:26, so the later definitions won and silently replaced
common.sh's TTY-gated logger. Two symptoms:

  * log_info / log_warn / log_success moved from stderr to STDOUT, so a gate a
    caller pipes for data got colour escapes mixed into that pipe.
  * log_error interpolated `"$1"`, so `log_error a b` printed only "a".

WHICH IS WHY THE LAST THREE CASES SPLIT THE STREAMS AND THE FIRST FOUR DO NOT,
and that difference is deliberate rather than sloppy. The defect is a stream
SWAP; the `2>&1` the first four cases use merges the two streams back together
and would hide it completely. The first four are about rendered text and merging
is correct for them. `RunResult` keeps `.out`, `.err` and `.combined` apart
precisely so a port can make that choice per case instead of once per file.

Sibling note carried over: check-pool-writer-safety.sh sources only common.sh and
never reaches blocker-validator.sh, which is why it was never affected. If it
ever grows a blocker-validator source, these cases are what keep it honest.

WHAT THE PORT REIMPLEMENTS. The twin counts escape bytes with
`tr -cd '\\033' < out | wc -c`; this counts `\\x1b` in the captured stdout
string. The two agree because both count ESC OCCURRENCES rather than lines, and
the harness captures the child's raw bytes as text without rewriting them.

`env -u CI` IS LOAD-BEARING in the split-stream cases, not tidiness: it puts
emit-advisory.sh in its colours-on branch, and neither stream is a tty, which is
exactly the condition common.sh gates its own colours on. The two libraries
disagree there if the fix regresses. The harness's `env_replace=True` is how that
is spelled, with the caller passing the whole environment it wants.

NO `xdist_group`. Every case is one `bash -c` subprocess with its own
environment; this process's own env is never mutated.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-emit-advisory.sh"

LIB_DIR = paths.from_root(".ci", "scripts", "lib")
EMIT = LIB_DIR / "emit-advisory.sh"
COMMON = LIB_DIR / "common.sh"
BLOCKER_VALIDATOR = LIB_DIR / "blocker-validator.sh"

# The seven associative arrays emit_advisory reads. Declared EMPTY in the cases
# that are not about metadata, because bash under `set -u` would abort on an
# undeclared one and the abort would look like a rendering failure.
EMPTY_TABLES = (
    "declare -A ADV_SEVERITY=() ADV_TITLE=() ADV_GHSA=() ADV_URL=()\n"
    "declare -A ADV_VULN_RANGE=() ADV_PATCHED_VERSION=() ADV_DESC_PREVIEW=()\n"
)


def bash_script(gate, script: str, *, env: dict[str, str]) -> harness.RunResult:
    for required in (EMIT, COMMON, BLOCKER_VALIDATOR):
        if not required.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(required))
    return harness.run(["bash", "-c", script], env=env, env_replace=True)


def with_ci() -> dict[str, str]:
    return {**os.environ, "CI": "true"}


def without_ci() -> dict[str, str]:
    """`env -u CI`. REMOVED, not emptied: those are different states here."""
    return {k: v for k, v in os.environ.items() if k != "CI"}


def test_ci_mode_prefix(gate):
    gate.log_test("CI mode must emit the annotation prefix and its continuation")
    result = bash_script(
        gate,
        "source '%s'\n%semit_advisory error 'testid' 'testpkg' 'test fix hint'\n"
        % (EMIT, EMPTY_TABLES),
        env=with_ci(),
    )
    gate.assert_contains(
        result.combined, "::error::testid (testpkg)", "CI error has annotation prefix"
    )
    gate.assert_contains(result.combined, "  Fix: test fix hint", "fix hint renders")
    gate.log_pass("CI mode emits annotation prefix + continuation")


def test_non_ci_mode_glyph(gate):
    gate.log_test("non-CI mode must use glyphs rather than annotations")
    result = bash_script(
        gate,
        "source '%s'\n%semit_advisory warn 'testid' 'testpkg' 'test fix hint'\n"
        % (EMIT, EMPTY_TABLES),
        env=without_ci(),
    )
    gate.assert_contains(result.combined, "⚠", "non-CI warn has the warning glyph")
    gate.assert_contains(result.combined, "testid (testpkg)", "header present")
    gate.log_pass("non-CI mode uses glyphs")


def test_full_metadata_renders_all_lines(gate):
    gate.log_test("every metadata line must render when the tables are populated")
    script = (
        """source '%s'
declare -A ADV_SEVERITY=(['id1']='critical')
declare -A ADV_TITLE=(['id1']='Test title')
declare -A ADV_GHSA=(['id1']='GHSA-xxxx-yyyy-zzzz')
declare -A ADV_URL=(['id1']='https://github.com/advisories/GHSA-xxxx-yyyy-zzzz')
declare -A ADV_VULN_RANGE=(['id1']='<= 1.0.0')
declare -A ADV_PATCHED_VERSION=(['id1']='1.0.1')
declare -A ADV_DESC_PREVIEW=(['id1']='Detailed CVE description preview')
emit_advisory error 'id1' 'pkgname' 'fix: upgrade' 'action: take the fix'
"""
        % EMIT
    )
    result = bash_script(gate, script, env=with_ci())
    out = result.combined
    gate.assert_contains(out, "critical", "severity shown")
    gate.assert_contains(out, "GHSA-xxxx-yyyy-zzzz", "GHSA shown")
    gate.assert_contains(out, "Test title", "title shown")
    gate.assert_contains(out, "Affected: <= 1.0.0", "affected range shown")
    gate.assert_contains(out, "Patched in: 1.0.1", "patched version shown")
    gate.assert_contains(out, "Summary: Detailed CVE", "summary shown")
    gate.assert_contains(out, "Fix: fix: upgrade", "fix hint shown")
    gate.assert_contains(out, "Action: action:", "action hint shown")
    gate.assert_contains(out, "Details: https://github.com/advisories", "url shown")
    gate.log_pass("full metadata renders all lines")


def test_emit_returns_zero_even_with_empty_hints(gate):
    gate.log_test("the set -e gotcha: emit_advisory must return 0")
    # A caller running `set -euo pipefail` must not exit on the trailing
    # conditional inside emit_advisory.
    result = bash_script(
        gate,
        "set -euo pipefail\nsource '%s'\n%semit_advisory warn 'testid' 'testpkg' ''\n"
        "echo 'after-emit'\n" % (EMIT, EMPTY_TABLES),
        env=with_ci(),
    )
    gate.assert_exit_code(0, result.rc, "emit_advisory does not fail caller under set -e")
    gate.assert_contains(result.combined, "after-emit", "execution continues past emit_advisory")
    gate.log_pass("emit_advisory returns 0 (set -e safe)")


def test_production_order_keeps_common_logger(gate):
    gate.log_test("the production source order of the four affected gates, verbatim")
    result = bash_script(
        gate,
        "source '%s'\nsource '%s'\nlog_info x\nlog_warn y\nlog_error a b\n"
        % (COMMON, BLOCKER_VALIDATOR),
        env=without_ci(),
    )
    gate.assert_exit_code(0, result.rc, "production-order logging exits clean")
    gate.assert_eq(result.out, "", "stdout stays empty while a gate logs")
    gate.assert_contains(result.err, "x", "log_info reaches stderr, not stdout")
    gate.assert_contains(result.err, "y", "log_warn reaches stderr, not stdout")
    gate.assert_contains(result.err, "a", "log_error reaches stderr")
    gate.assert_contains(result.err, "b", "log_error keeps arguments past the first")
    gate.log_pass("common.sh logger survives blocker-validator's transitive source")


def test_no_escape_bytes_on_stdout_off_tty(gate):
    gate.log_test("off a tty, stdout must carry no colour escapes at all")
    # log_success is the interesting one: common.sh does not define it, so it
    # legitimately comes from this library even in production order. It must
    # still honour the RED/GREEN/... that common.sh already emptied.
    result = bash_script(
        gate,
        "source '%s'\nsource '%s'\nlog_info x\nlog_warn y\nlog_success z\nlog_error a b\n"
        % (COMMON, BLOCKER_VALIDATOR),
        env=without_ci(),
    )
    gate.assert_exit_code(0, result.rc, "off-tty logging exits clean")
    gate.assert_eq(result.out.count("\x1b"), 0, "zero ESC bytes on stdout when stderr is not a tty")
    gate.log_pass("off a tty, stdout carries no colour escapes")


def test_standalone_source_still_defines_logger(gate):
    gate.log_test("a script sourcing ONLY this library still gets all four helpers")
    # Making the definitions conditional must not quietly define nothing.
    result = bash_script(
        gate,
        "source '%s'\ndeclare -F log_error log_success log_warn log_info >/dev/null || exit 3\n"
        "log_info x\nlog_success z\nlog_warn y\nlog_error a b\n" % EMIT,
        env=without_ci(),
    )
    gate.assert_exit_code(0, result.rc, "standalone source defines all four log_* helpers")
    gate.assert_contains(result.out, "x", "standalone log_info still writes to stdout")
    gate.assert_contains(result.out, "z", "standalone log_success still writes to stdout")
    gate.assert_contains(result.out, "y", "standalone log_warn still writes to stdout")
    gate.assert_contains(result.err, "a", "standalone log_error still writes to stderr")
    gate.assert_contains(result.err, "b", "standalone log_error keeps its argument tail")
    gate.assert_not_contains(result.out, "✗", "standalone log_error does not leak onto stdout")
    gate.log_pass("emit-advisory alone keeps its standalone logger contract")
