"""Port of `.ci/scripts/test/gates/test-installmethods-linuxpkg-idiom.sh`, retired in W7 P5.

The version assertions in `rediacc_ci.testrun.linux_packages` (written against the bash `test-linux-packages.sh`, retired behind its golden, PLAN-retire-bash-oracles B3).

WHY THIS EXISTS. That file carried the same unanchored-grep idiom that let a 1.2.16 binary verify as 1.2.17 in the release path, in two shapes:

    ${PKG_BINARY_NAME} --version 2>/dev/null | grep -q '${TEST_VERSION}'
    echo "$info" | grep -q "Version: ${TEST_VERSION}"

SEVERITY IS LOW and deliberately recorded as such: TEST_VERSION is hardcoded to 99.0.0 and the binary under test is a dummy shell script the same file writes, so no real version could drift out from under those checks. The point of the change, and of this file, is to stop the idiom being COPIED somewhere a real version is at stake -- and to keep it from creeping back in.

The name carries the test-installmethods- prefix because that is the prefix the batch of gate tests was added under; the target is the linux-packages runner.

THE SUBJECT IS CALLED IN PROCESS: `version_token_re` and `assert_version_field` are the module's own functions, so the cases drive them directly and the census reads the module's own source.

ARGUMENT ORDER. The retired bash gate called `assert_eq "0" "$(field ...)"`, EXPECTED first, which inverts `assert_eq`'s own contract. Same verdict, inverted diagnostic; one of the 67 known sites. The port uses the contract's order.
"""

import inspect
import re

from rediacc_ci.testrun import linux_packages as port

COMMENT_RE = re.compile(r"^[ \t]*#")


def subject_version(gate) -> str:
    """The subject's own TEST_VERSION. A missing one is a REFUSAL, not a default."""
    if not port.TEST_VERSION:
        gate.log_fail("TEST_VERSION is empty in rediacc_ci.testrun.linux_packages")
    return port.TEST_VERSION


def deb_info(version: str) -> str:
    # dpkg-deb --info and rpm -qip lay the same field out differently; both shapes are what the two callers actually feed in.
    return " Package: rediacc-cli\n Version: %s\n Architecture: amd64\n Maintainer: x\n" % version


def rpm_info(version: str) -> str:
    return "Name        : rediacc-cli\nVersion     : %s\nArchitecture: x86_64\n" % version


def field(layout: str, version: str) -> str:
    info = deb_info(version) if layout == "deb" else rpm_info(version)
    return "0" if port.assert_version_field(info, "Version") else "1"


def field_raw(info: str) -> str:
    return "0" if port.assert_version_field(info, "Version") else "1"


def token(text: str) -> str:
    return "0" if re.search(port.version_token_re(port.TEST_VERSION), text) else "1"


def test_the_right_version_is_accepted_in_both_layouts(gate):
    version = subject_version(gate)
    gate.assert_eq(field("deb", version), "0", "the deb layout with the right version must pass")
    gate.assert_eq(field("rpm", version), "0", "the rpm layout with the right version must pass")
    gate.log_pass("both metadata layouts still validate a correct version")


def test_a_longer_version_no_longer_satisfies_the_field_check(gate):
    version = subject_version(gate)
    longer = "%s1" % version
    gate.assert_eq(
        field("deb", longer), "1", "'%s' must NOT satisfy a '%s' check" % (longer, version)
    )
    gate.assert_eq(
        field("rpm", longer), "1", "'%s' must NOT satisfy a '%s' check" % (longer, version)
    )

    # The control. Both old idioms accept it, which is what made them worth replacing even at low severity: `grep "Version: $V"` and `grep "Version.*: $V"` are unanchored substring (and, with the dots, regex) matches.
    old_deb = "0" if re.search("Version: " + version, deb_info(longer)) else "1"
    old_rpm = "0" if re.search("Version.*: " + version, rpm_info(longer)) else "1"
    gate.assert_eq(old_deb, "0", "the OLD deb idiom must accept it, or this test proves nothing")
    gate.assert_eq(old_rpm, "0", "the OLD rpm idiom must accept it, or this test proves nothing")
    gate.log_pass("a substring version is refused where it used to pass")


def test_a_missing_or_wrong_field_fails(gate):
    gate.assert_eq(
        field_raw(" Package: rediacc-cli\n Architecture: amd64\n"),
        "1",
        "a missing Version field must FAIL",
    )
    gate.assert_eq(field("deb", "1.0.0"), "1", "a plainly wrong version must FAIL")
    gate.assert_eq(field("deb", ""), "1", "an empty version value must FAIL")
    gate.log_pass("an absent or wrong version field is a failure")


def test_the_token_regex_matches_whole_versions_only(gate):
    version = subject_version(gate)
    gate.assert_eq(
        token("rdc version %s" % version), "0", "the version inside a longer line must match"
    )
    gate.assert_eq(token("v%s" % version), "0", "a v-prefixed output must match")
    gate.assert_eq(token("rdc version %s1" % version), "1", "a longer version must NOT match")
    gate.assert_eq(token("rdc version 1%s" % version), "1", "a longer prefix must NOT match")
    gate.assert_eq(token(""), "1", "empty output must NOT match")

    # Control: the old container idiom, `grep -q "$TEST_VERSION"`, accepts a longer version.
    old = "0" if version in "rdc version %s1\n" % version else "1"
    gate.assert_eq(
        old,
        "0",
        "the OLD container idiom must accept a longer version, or this test proves nothing",
    )
    gate.log_pass("the exact-token regex refuses what the old grep accepted")


def test_the_old_idiom_is_gone_from_the_target(gate):
    """Structural, so the idiom cannot quietly come back.

    Comment lines are stripped first, and `count` is LINES CONTAINING the literal, so two spellings of one idiom on a line cannot disagree. The module has no shell strings holding the old greps, and every version assertion goes through the two helpers.
    """
    source = inspect.getsource(port)
    code = [ln for ln in source.splitlines() if not COMMENT_RE.match(ln)]

    def count(needle: str) -> int:
        return len([ln for ln in code if needle in ln])

    for old in ("grep -q '${TEST_VERSION}'", 'grep -q "Version: ${TEST_VERSION}"'):
        gate.assert_eq(count(old), 0, "the unanchored grep %r must be gone from the code" % old)
    gate.assert_eq(count('"Version.*: ${TEST_VERSION}"'), 0, "the unanchored rpm grep must be gone")

    # Discrimination: count() must be able to find something, or the zeros above would be satisfied by a broken matcher.
    gate.assert_eq(
        count('assert_version_field(info, "Version")'),
        2,
        "both metadata validators must use assert_version_field",
    )
    gate.assert_eq(
        count("version_token_re(TEST_VERSION)"),
        1,
        "the container install checks must build their exact-token regex from the helper",
    )
    gate.log_pass("the target carries one exact-match spelling and no copies of the old one")
