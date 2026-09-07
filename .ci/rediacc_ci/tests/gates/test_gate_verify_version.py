"""Port of `.ci/scripts/test/gates/test-verify-version.sh`.

Tests for `verify_version()` in `.ci/scripts/test/test-install-methods.sh`.

WHY THIS EXISTS. On 2026-08-07 release run 31154305287 published CLI binaries
built as 1.2.16 under the label 1.2.17. Two guards passed silently, and
underneath both sat this one primitive, whose whole body was

    echo "$output" | grep -q "$expected"

which reports success in three situations where nothing was verified: an EMPTY
expectation (`grep -q ""` matches any line), EMPTY output (a binary that did not
run, or whose output was discarded by `|| true`), and a SUBSTRING match, so
1.2.1 "verified" against a binary reporting 1.2.16. The dots are regex wildcards
on top of that.

The rule being pinned: there is ALWAYS a version, or it fails. A caller that
genuinely cannot determine one must SKIP visibly, never hand an empty string to
this and take the pass.

WHY THE SUBJECT IS EXTRACTED RATHER THAN SOURCED, unchanged from the twin:
sourcing the whole script would run its argument parsing. The extraction is by
ANCHOR, so a rename breaks this file loudly instead of leaving it exercising a
copy pasted in here -- and an extraction that comes back EMPTY is a refusal, not
a suite that passes over nothing.

WHY EACH CALL IS ITS OWN `bash -c`. The bash twin evals the function into its
own shell once. A Python port has no shell to eval into, so each call is a
process, and the function text is re-injected each time. That is slower and
strictly more honest: no case can leave state behind for the next one.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-verify-version.sh"

TARGET = paths.from_root(".ci", "scripts", "test", "test-install-methods.sh")

# `verify_version() {` .. the closing `}` at column 0, which is the awk range the
# twin uses spelled as a regex.
FN_RE = re.compile(r"^verify_version\(\) \{.*?^\}", re.MULTILINE | re.DOTALL)

# The EXACT pre-fix body, re-created. Not a mutation of the current one: a
# mutation drifts with the subject, and the point of this control is that the
# shape which shipped the incident really did admit both silent-pass classes.
OLD_BODY = """
old_verify() {
    local output="$1" expected="$2"
    if [[ "$expected" == "latest" ]]; then
        [[ -n "$output" ]] && grep -qE '^v?[0-9]+\\.[0-9]+\\.[0-9]+(-[a-zA-Z0-9.]+)?$' <<<"$output"
    else
        grep -q "$expected" <<<"$output"
    fi
}
"""


def function_source() -> str:
    match = FN_RE.search(TARGET.read_text(encoding="utf-8"))
    return match.group(0) if match else ""


def require_subject(gate) -> str:
    """The function text, or a refusal. Never an empty string handed onward."""
    if not TARGET.is_file():
        gate.log_fail("target not found: %s" % TARGET)
    body = function_source()
    if not body:
        gate.log_fail(
            "verify_version() not found in %s -- renamed or removed, so these tests "
            "would check nothing" % paths.relative_to_root(TARGET)
        )
    return body


def vv(gate, output: str, expected: str) -> int:
    """0 when verify_version ACCEPTED, 1 when it refused. The twin's `vv`."""
    body = require_subject(gate)
    script = (
        "log_error() { :; }\n"  # the function under test calls it; keep output clean
        + body
        + '\nverify_version "$1" "$2" >/dev/null 2>&1 && echo 0 || echo 1\n'
    )
    result = harness.run(["bash", "-c", script, "verify-version-port", output, expected])
    return int(result.out.strip() or "-1")


def old_verify(output: str, expected: str) -> int:
    """0 when the PRE-FIX body accepted. Same convention as `vv`."""
    script = OLD_BODY + '\nold_verify "$1" "$2" >/dev/null 2>&1 && echo 0 || echo 1\n'
    result = harness.run(["bash", "-c", script, "old-verify-port", output, expected])
    return int(result.out.strip() or "-1")


def test_real_versions_are_accepted(gate):
    gate.assert_eq(vv(gate, "rdc 1.2.17", "1.2.17"), 0, "an exact match must pass")
    gate.assert_eq(vv(gate, "v1.2.17", "1.2.17"), 0, "a v-prefixed output must pass")
    gate.assert_eq(vv(gate, "rdc 1.2.17", "v1.2.17"), 0, "a v-prefixed expectation must pass")
    gate.assert_eq(
        vv(gate, "rediacc rdc 1.2.17 (linux)", "1.2.17"),
        0,
        "the version may sit inside a longer line",
    )
    gate.log_pass("well-formed versions are accepted")


def test_missing_version_never_passes(gate):
    # The founding defect class: nothing was established, yet grep said yes.
    gate.assert_eq(vv(gate, "rdc 1.2.17", ""), 1, "an EMPTY expectation must never pass")
    gate.assert_eq(vv(gate, "", "1.2.17"), 1, "EMPTY output must never pass")
    gate.assert_eq(vv(gate, "", ""), 1, "both empty must never pass")
    gate.log_pass("a version that could not be established fails instead of passing")


def test_substring_matches_are_refused(gate):
    # This is how a patch release would "verify" against the wrong build.
    gate.assert_eq(vv(gate, "rdc 1.2.16", "1.2.1"), 1, "1.2.1 must NOT match 1.2.16")
    gate.assert_eq(vv(gate, "rdc 11.2.1", "1.2.1"), 1, "1.2.1 must NOT match 11.2.1")
    gate.assert_eq(vv(gate, "rdc 1x2y17", "1.2.17"), 1, "dots must not behave as regex wildcards")
    gate.assert_eq(vv(gate, "rdc 1.2.16", "1.2.17"), 1, "a genuinely wrong version must fail")
    gate.log_pass("substring and regex matches are refused")


def test_latest_still_requires_a_real_version(gate):
    gate.assert_eq(vv(gate, "1.2.17", "latest"), 0, "latest accepts a well-formed semver")
    gate.assert_eq(vv(gate, "1.2.17-rc.1", "latest"), 0, "latest accepts a prerelease")
    gate.assert_eq(vv(gate, "command not found", "latest"), 1, "latest must reject garbage")
    gate.assert_eq(vv(gate, "", "latest"), 1, "latest must reject empty output")
    gate.log_pass("latest means any REAL version, not any output")


def test_the_founding_defect_fires(gate):
    """The control on every case above: the OLD body must ACCEPT what the new one
    refuses. If it did not, these tests would be decorative and would have let
    the incident through unchanged."""
    gate.assert_eq(
        old_verify("rdc 1.2.17", ""),
        0,
        "the OLD body must accept an empty expectation, or this test proves nothing",
    )
    gate.assert_eq(
        old_verify("rdc 1.2.16", "1.2.1"),
        0,
        "the OLD body must accept 1.2.1 against 1.2.16, or this test proves nothing",
    )
    gate.log_pass("the old implementation really did admit both silent-pass classes")


def test_the_extraction_anchor_is_present(gate):
    """PORT-ONLY. The twin refuses at load time when the anchor is gone; a pytest
    module cannot refuse at import without taking the whole file down, so the
    refusal becomes its own case and stays visible in the report."""
    require_subject(gate)
    gate.log_pass(
        "verify_version() extracted from %s (%d lines)"
        % (paths.relative_to_root(TARGET), len(function_source().splitlines()))
    )
