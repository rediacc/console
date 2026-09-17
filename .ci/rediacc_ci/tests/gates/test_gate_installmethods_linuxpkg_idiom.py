"""Port of `.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh`.

The version assertions in `.ci/scripts/test/test-linux-packages.sh`.

WHY THIS EXISTS. That file carried the same unanchored-grep idiom that let a 1.2.16 binary verify as 1.2.17 in the release path, in two shapes:

    ${PKG_BINARY_NAME} --version 2>/dev/null | grep -q '${TEST_VERSION}'
    echo "$info" | grep -q "Version: ${TEST_VERSION}"

SEVERITY IS LOW and deliberately recorded as such: TEST_VERSION is hardcoded to 99.0.0 and the binary under test is a dummy shell script the same file writes, so no real version could drift out from under those checks. The point of the change, and of this file, is to stop the idiom being COPIED somewhere a real version is at stake -- and to keep it from creeping back in.

The name carries the test-installmethods- prefix because that is the prefix the batch of gate tests was added under; the target is test-linux-packages.sh.

WHY THE PORT STILL RUNS BASH for the first four cases: `version_token_re` and `assert_version_field` are the SUBJECT's own shell functions, and reimplementing either in Python would pin the port's idea of the regex rather than the subject's. The fifth case is a text census and is pure Python.

ARGUMENT ORDER. The twin calls `assert_eq "0" "$(field ...)"`, EXPECTED first, which inverts `assert_eq`'s own contract. Same verdict, inverted diagnostic; one of the 67 known sites. The port uses the contract's order.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness, shellsubject

BASH_TWIN = ".ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh"

TARGET = paths.from_root(".ci", "scripts", "test", "test-linux-packages.sh")
SUBJECT = shellsubject.Subject(TARGET)

COMMENT_RE = re.compile(r"^[ \t]*#")


def subject_version(gate) -> str:
    """The subject's own TEST_VERSION. A missing one is a REFUSAL, not a default."""
    for line in SUBJECT.text(gate).splitlines():
        if line.startswith("TEST_VERSION="):
            parts = line.split('"')
            if len(parts) > 1 and parts[1]:
                return parts[1]
    gate.log_fail("TEST_VERSION not found in %s" % paths.relative_to_root(TARGET))
    return ""


def prelude(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    parts = [
        "log_error() { :; }",
        SUBJECT.shell_fn(gate, "version_token_re"),
        SUBJECT.shell_fn(gate, "assert_version_field"),
        'TEST_VERSION="%s"' % subject_version(gate),
        'TEST_VERSION_RE="$(version_token_re "$TEST_VERSION")"',
        # dpkg-deb --info and rpm -qip lay the same field out differently; both shapes are what the two callers actually feed in.
        (
            "deb_info() { printf ' Package: rediacc-cli\\n Version: %s\\n "
            'Architecture: amd64\\n Maintainer: x\\n\' "$1"; }'
        ),
        (
            "rpm_info() { printf 'Name        : rediacc-cli\\nVersion     : %s\\n"
            'Architecture: x86_64\\n\' "$1"; }'
        ),
        'field() { assert_version_field "$1" "Version" >/dev/null 2>&1 && echo 0 || echo 1; }',
        'token() { grep -qE "$TEST_VERSION_RE" <<<"$1" && echo 0 || echo 1; }',
    ]
    path = tmp_path / "prelude.sh"
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def bash(gate, tmp_path: pathlib.Path, snippet: str, *args: str) -> harness.RunResult:
    harness.require_tool("bash", "install bash; this gate drives the subject's own shell functions")
    return harness.run(
        ["bash", "-c", 'source "$1"\n%s' % snippet, "_", str(prelude(gate, tmp_path)), *args],
        timeout=120,
    )


def field(gate, tmp_path, layout: str, version: str) -> str:
    return bash(gate, tmp_path, 'field "$(%s_info "$2")"' % layout, version).out.strip()


def field_raw(gate, tmp_path, info: str) -> str:
    return bash(gate, tmp_path, 'field "$2"', info).out.strip()


def token(gate, tmp_path, text: str) -> str:
    return bash(gate, tmp_path, 'token "$2"', text).out.strip()


def test_the_right_version_is_accepted_in_both_layouts(gate, tmp_path):
    version = subject_version(gate)
    gate.assert_eq(
        field(gate, tmp_path, "deb", version),
        "0",
        "the deb layout with the right version must pass",
    )
    gate.assert_eq(
        field(gate, tmp_path, "rpm", version),
        "0",
        "the rpm layout with the right version must pass",
    )
    gate.log_pass("both metadata layouts still validate a correct version")


def test_a_longer_version_no_longer_satisfies_the_field_check(gate, tmp_path):
    version = subject_version(gate)
    longer = "%s1" % version
    gate.assert_eq(
        field(gate, tmp_path, "deb", longer),
        "1",
        "'%s' must NOT satisfy a '%s' check" % (longer, version),
    )
    gate.assert_eq(
        field(gate, tmp_path, "rpm", longer),
        "1",
        "'%s' must NOT satisfy a '%s' check" % (longer, version),
    )

    # The control. Both old idioms accept it, which is what made them worth replacing even at low severity.
    old_deb = bash(
        gate,
        tmp_path,
        '[ -n "$(deb_info "$2" | grep "Version: $TEST_VERSION")" ] && echo 0 || echo 1',
        longer,
    ).out.strip()
    old_rpm = bash(
        gate,
        tmp_path,
        '[ -n "$(rpm_info "$2" | grep "Version.*: $TEST_VERSION")" ] && echo 0 || echo 1',
        longer,
    ).out.strip()
    gate.assert_eq(old_deb, "0", "the OLD deb idiom must accept it, or this test proves nothing")
    gate.assert_eq(old_rpm, "0", "the OLD rpm idiom must accept it, or this test proves nothing")
    gate.log_pass("a substring version is refused where it used to pass")


def test_a_missing_or_wrong_field_fails(gate, tmp_path):
    gate.assert_eq(
        field_raw(gate, tmp_path, " Package: rediacc-cli\n Architecture: amd64\n"),
        "1",
        "a missing Version field must FAIL",
    )
    gate.assert_eq(field(gate, tmp_path, "deb", "1.0.0"), "1", "a plainly wrong version must FAIL")
    gate.assert_eq(field(gate, tmp_path, "deb", ""), "1", "an empty version value must FAIL")
    gate.log_pass("an absent or wrong version field is a failure")


def test_the_token_regex_matches_whole_versions_only(gate, tmp_path):
    version = subject_version(gate)
    gate.assert_eq(
        token(gate, tmp_path, "rdc version %s" % version),
        "0",
        "the version inside a longer line must match",
    )
    gate.assert_eq(token(gate, tmp_path, "v%s" % version), "0", "a v-prefixed output must match")
    gate.assert_eq(
        token(gate, tmp_path, "rdc version %s1" % version),
        "1",
        "a longer version must NOT match",
    )
    gate.assert_eq(
        token(gate, tmp_path, "rdc version 1%s" % version),
        "1",
        "a longer prefix must NOT match",
    )
    gate.assert_eq(token(gate, tmp_path, ""), "1", "empty output must NOT match")

    # Control: the old container idiom accepts the first two negatives.
    old = bash(
        gate,
        tmp_path,
        'printf "rdc version %s1\\n" "$TEST_VERSION" | grep -q "$TEST_VERSION" && echo 0 || echo 1',
    ).out.strip()
    gate.assert_eq(
        old,
        "0",
        "the OLD container idiom must accept a longer version, or this test proves nothing",
    )
    gate.log_pass("the exact-token regex refuses what the old grep accepted")


def test_the_old_idiom_is_gone_from_the_target(gate):
    """Structural, so the idiom cannot quietly come back.

    Comment lines are stripped first: the header of the target QUOTES both old idioms verbatim to explain what was wrong with them, and a naive whole-file search matches that documentation and fails on it. (It did, on the first run of the twin.)

    `count` is LINES CONTAINING the literal, matching `grep -cF`, not the number of occurrences. Two spellings of that would disagree the day a line carries the token twice.
    """
    code = [ln for ln in SUBJECT.text(gate).splitlines() if not COMMENT_RE.match(ln)]

    def count(needle: str) -> int:
        return len([ln for ln in code if needle in ln])

    gate.assert_eq(
        count("grep -q '${TEST_VERSION}'"),
        0,
        "the unanchored container grep must be gone from the code",
    )
    gate.assert_eq(
        count('grep -q "Version: ${TEST_VERSION}"'),
        0,
        "the unanchored deb grep must be gone from the code",
    )
    gate.assert_eq(
        count('grep -q "Version.*: ${TEST_VERSION}"'),
        0,
        "the unanchored rpm grep must be gone from the code",
    )

    # Discrimination: count() must be able to find something, or the three zeros above would be satisfied by a broken matcher.
    gate.assert_eq(
        count('assert_version_field "$info" "Version"'),
        2,
        "both metadata validators must use assert_version_field",
    )

    # And all four container checks use the exact-match regex. Counted, not merely present: three of four converted would otherwise look identical.
    gate.assert_eq(
        count("grep -qE '${TEST_VERSION_RE}'"),
        4,
        "all four container install checks must use the exact-token regex",
    )
    gate.log_pass("the target carries one exact-match spelling and no copies of the old one")
