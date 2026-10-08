"""Port of `.ci/scripts/test/gates/test-emit-advisory.sh`, retired in W7 P5, retargeted onto the PORT of its subject in PLAN-retire-bash-oracles section 12 U1.

THE SUBJECT IS NOW `rediacc_ci.core.advisory`, the port of `.ci/scripts/lib/emit-advisory.sh`. The bash library was deleted in section 12 U1 (nothing sourced it but the also-deleted `blocker-validator.sh`); its bytes on both streams stay frozen in `goldens/twins/lib.emit-advisory.jsonl`, which `test_core_advisory.py` compares the port against. This file keeps its own two questions and asks
them of the port, through its real entry point (`python3 -m rediacc_ci.core.advisory`, a program on stdin) and its four loggers.

THE SHAPE OF THE ANNOTATIONS. CI mode emits a `::error::` / `::warning::` prefix, non-CI mode emits coloured ANSI with the glyphs, and continuation lines fire only
for the hints actually supplied.

THE STREAM AND ARGUMENT REGRESSIONS, found 2026-09-06. emit-advisory.sh used to assign RED/GREEN/YELLOW/NC and define `log_error` / `log_success` / `log_warn` / `log_info` UNCONDITIONALLY, and four gates reached it transitively after common.sh, so its logger silently replaced common.sh's TTY-gated one. Two symptoms: log_info / log_warn / log_success moved from stderr to STDOUT, and log_error printed only
its first argument. The port has no second definition to collide with (an imported module cannot be shadowed by a later `source`), so what is left to pin is the port's OWN standalone contract: which stream each level writes to, and that a message is kept whole.

WHICH IS WHY THE LAST CASE SPLITS THE STREAMS AND THE FIRST FOUR DO NOT, and that difference is deliberate rather than sloppy. The defect class is a stream SWAP; merging the streams would hide it completely. The first four are about rendered text and merging is correct for them. `RunResult` keeps `.out`, `.err` and `.combined` apart precisely so a port can make that choice per case.

`CI` REMOVED, NOT EMPTIED, in the non-CI cases: the port's colour rule tests the literal `CI=true` and nothing else, so an inherited `CI=true` from the runner would flip every non-CI case into annotation mode. The harness's `env_replace=True` is how that is spelled, with the caller passing the whole environment it wants.

NO `xdist_group`. Every case is one `python3` subprocess with its own environment; this process's own env is never mutated.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

PORT = paths.from_root(".ci", "rediacc_ci", "core", "advisory.py")
US = "\x1f"


def _env(base: dict[str, str]) -> dict[str, str]:
    return {**base, "PYTHONPATH": str(paths.ci_dir()), "PYTHONSAFEPATH": "1"}


def with_ci() -> dict[str, str]:
    return _env({**os.environ, "CI": "true"})


def without_ci() -> dict[str, str]:
    """`env -u CI`. REMOVED, not emptied: those are different states here."""
    return _env({k: v for k, v in os.environ.items() if k != "CI"})


def program(*rows: tuple[str, ...]) -> str:
    """The port's stdin program: one US-separated row per `meta` cell or `emit` call."""
    return "".join(US.join(row) + "\n" for row in rows)


def advisory(gate, rows: str, *, env: dict[str, str]) -> harness.RunResult:
    if not PORT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(PORT))
    return harness.run(
        ["python3", "-m", "rediacc_ci.core.advisory"],
        cwd=paths.repo_root(),
        env=env,
        env_replace=True,
        stdin=rows,
    )


def test_ci_mode_prefix(gate):
    gate.log_test("CI mode must emit the annotation prefix and its continuation")
    result = advisory(
        gate, program(("emit", "error", "testid", "testpkg", "test fix hint")), env=with_ci()
    )
    gate.assert_exit(0, result, "the program ran")
    gate.assert_contains(
        result.combined, "::error::testid (testpkg)", "CI error has annotation prefix"
    )
    gate.assert_contains(result.combined, "  Fix: test fix hint", "fix hint renders")
    gate.log_pass("CI mode emits annotation prefix + continuation")


def test_non_ci_mode_glyph(gate):
    gate.log_test("non-CI mode must use glyphs rather than annotations")
    result = advisory(
        gate, program(("emit", "warn", "testid", "testpkg", "test fix hint")), env=without_ci()
    )
    gate.assert_exit(0, result, "the program ran")
    gate.assert_contains(result.combined, "\u26a0", "non-CI warn has the warning glyph")
    gate.assert_contains(result.combined, "testid (testpkg)", "header present")
    gate.assert_not_contains(result.combined, "::warning::", "and no annotation off CI")
    gate.log_pass("non-CI mode uses glyphs")


def test_full_metadata_renders_all_lines(gate):
    gate.log_test("every metadata line must render when the tables are populated")
    rows = program(
        ("meta", "severity", "id1", "critical"),
        ("meta", "title", "id1", "Test title"),
        ("meta", "ghsa", "id1", "GHSA-xxxx-yyyy-zzzz"),
        ("meta", "url", "id1", "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz"),
        ("meta", "range", "id1", "<= 1.0.0"),
        ("meta", "patched", "id1", "1.0.1"),
        ("meta", "desc", "id1", "Detailed CVE description preview"),
        ("emit", "error", "id1", "pkgname", "fix: upgrade", "action: take the fix"),
    )
    result = advisory(gate, rows, env=with_ci())
    gate.assert_exit(0, result, "the program ran")
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
    gate.log_test("emit_advisory must succeed with an empty fix hint, and print no Fix line")
    # The twin's `set -e` gotcha: its trailing conditional must not fail the caller. The port keeps the promise through its exit code, and an empty hint must render as NO continuation line rather than an empty one.
    result = advisory(gate, program(("emit", "warn", "testid", "testpkg", "")), env=with_ci())
    gate.assert_exit(0, result, "an empty hint is not a failure")
    gate.assert_contains(result.combined, "testid (testpkg)", "the header still renders")
    gate.assert_not_contains(result.combined, "Fix:", "an empty hint prints no Fix line")
    gate.log_pass("emit_advisory exits 0 on empty hints and omits their lines")


def test_standalone_source_still_defines_logger(gate):
    gate.log_test("the port's four loggers write to their own streams and keep the whole message")
    # The 2026-09-06 contract, asked of the port: info, success and warn on STDOUT, error on STDERR, and a multi-word message kept whole (the bash regression printed only its first argument).
    script = (
        "from rediacc_ci.core import advisory as a\n"
        "a.log_info('x')\na.log_success('z')\na.log_warn('y')\na.log_error('a b')\n"
    )
    result = harness.run(
        ["python3", "-c", script], cwd=paths.repo_root(), env=without_ci(), env_replace=True
    )
    gate.assert_exit(0, result, "the port defines all four log_* helpers")
    gate.assert_contains(result.out, "\u2192 x", "log_info writes to stdout")
    gate.assert_contains(result.out, "\u2713 z", "log_success writes to stdout")
    gate.assert_contains(result.out, "\u26a0 y", "log_warn writes to stdout")
    gate.assert_contains(result.err, "\u2717 a b", "log_error writes the whole message to stderr")
    gate.assert_not_contains(result.out, "\u2717", "log_error does not leak onto stdout")
    gate.assert_not_contains(result.err, "\u2192", "log_info does not leak onto stderr")
    gate.log_pass("the port keeps the standalone logger contract")
