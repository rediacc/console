"""Port of `.ci/scripts/test/gates/test-installmethods-container-version.sh`.

The container version fence in `.ci/scripts/test/test-install-methods.sh`.

WHY THIS CLASS NEEDS A GATE. On 2026-08-07 a release published CLI binaries
built as 1.2.16 under the label 1.2.17. `verify_version()` was one hole (pinned
by test-verify-version.sh). The other, larger one: SEVEN of the eleven install
methods -- apt, dnf, apk, pacman, npm, linuxbrew, quick -- never compared a
version at all. Each ended its `docker run ... set -e` heredoc with a bare
`${PKG_BINARY_NAME} --version` whose output was never captured and never
compared. `$VERSION` was referenced ZERO times inside any of those functions, so
the only assertion was "the installed binary exits 0" -- which a mislabelled
binary does.

The fix moves the comparison HOST-side, through verify_version, and fences the
container's version output between markers so the transcript's own mentions of
the version (apt-get, npm and brew all print it while installing) cannot satisfy
the check. Both properties are asserted in both directions: a checker that always
failed would satisfy every negative case, one that always passed would satisfy
every positive one, and neither would be a check.

WHY THE PORT STILL RUNS BASH. The subject's real implementations are shell
functions, and the twin lifts them out with awk and `eval`s them rather than
sourcing the script (which would run its argument parsing). Reimplementing
`run_container_version_test` in Python would test the PORT's idea of the fence
instead of the subject's, which is the one thing a port must not do. So the
Python side builds the same extraction prelude and drives the REAL functions;
what moves into Python is the case structure and the assertions.

ARGUMENT ORDER. The twin calls `assert_eq "0" "$(check ...)"`, i.e. EXPECTED
first, which is the inverse of `assert_eq`'s own contract (actual first). Same
verdict, inverted diagnostic; it is one of 67 such sites across six twins. The
port uses the contract's order, so a failure here reads the right way round.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-installmethods-container-version.sh"

TARGET = paths.from_root(".ci", "scripts", "test", "test-install-methods.sh")

FENCE_RE = re.compile(r"^VERSION_FENCE_(?:BEGIN|END)=.*$", re.MULTILINE)

# The seven container install methods that must route through the fence.
FENCED_METHODS = (
    "test_apt_install",
    "test_dnf_install",
    "test_apk_install",
    "test_pacman_install",
    "test_npm_install",
    "test_homebrew_linuxbrew",
    "test_quick_install",
)


def source(gate) -> str:
    if not TARGET.is_file():
        gate.log_fail("target not found: %s" % TARGET)
    return TARGET.read_text(encoding="utf-8")


def extract_fn(gate, name: str) -> str:
    """The body of `name()` from the subject, or a LOUD refusal.

    `awk "/^name\\(\\) \\{/,/^\\}/"` in the twin. Every extraction is checked for
    emptiness: a renamed or deleted function must make this file REFUSE, not
    quietly test nothing.
    """
    body: list[str] = []
    collecting = False
    for line in source(gate).splitlines():
        if not collecting and line.startswith("%s() {" % name):
            collecting = True
        if collecting:
            body.append(line)
            if line == "}":
                break
    if not body:
        gate.log_fail(
            "%s() not found in %s -- renamed or removed, so these tests would check nothing"
            % (name, paths.relative_to_root(TARGET))
        )
    return "\n".join(body)


def prelude(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    """A sourceable file carrying the subject's REAL fence functions.

    `log_info`/`log_warn`/`log_error` are stubbed to no-ops because the
    functions under test call them and their output is not what is being judged.
    """
    fence_lines = [ln for ln in source(gate).splitlines() if FENCE_RE.fullmatch(ln)]
    if not fence_lines:
        gate.log_fail("VERSION_FENCE_BEGIN/END not found in %s" % paths.relative_to_root(TARGET))
    parts = [
        "log_info() { :; }",
        "log_warn() { :; }",
        "log_error() { :; }",
        *fence_lines,
        extract_fn(gate, "verify_version"),
        extract_fn(gate, "version_fence_probe"),
        extract_fn(gate, "extract_fenced_version"),
        extract_fn(gate, "run_container_version_test"),
        # A stand-in for `docker run`: runs the REAL fenced probe the install
        # functions paste into their container scripts, so the probe itself is
        # under test and not just the host-side comparison. $1 is what the
        # "installed binary" prints, $2 is surrounding install-transcript noise.
        (
            "fake_container() {\n"
            '    local reported="$1" noise="${2:-}"\n'
            '    bash -c "\n'
            "        set -e\n"
            "        printf '%s\\n' \\\"\\$1\\\"\n"
            '        $(version_fence_probe "printf \'%s\\n\' \\"\\$2\\"")\n'
            '    " _ "$noise" "$reported"\n'
            "}"
        ),
        (
            "fake_container_fails() {\n"
            "    printf 'apt-get: package not found\\n' >&2\n"
            "    return 3\n"
            "}"
        ),
        # 0 when the check accepted, 1 when it refused.
        (
            "check() {\n"
            '    local expected="$1" reported="$2" noise="${3:-}"\n'
            '    VERSION="$expected"\n'
            '    run_container_version_test "T" fake_container "$reported" "$noise" '
            ">/dev/null 2>&1 && echo 0 || echo 1\n"
            "}"
        ),
    ]
    path = tmp_path / "prelude.sh"
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def bash(gate, tmp_path: pathlib.Path, snippet: str, *args: str) -> harness.RunResult:
    """Source the prelude and run `snippet` against the subject's real functions."""
    harness.require_tool("bash", "install bash; this gate drives the subject's own shell functions")
    return harness.run(
        ["bash", "-c", 'source "$1"\n%s' % snippet, "_", str(prelude(gate, tmp_path)), *args],
        timeout=120,
    )


def check(gate, tmp_path, expected: str, reported: str, noise: str = "") -> str:
    """ "0" when the fenced host-side comparison accepted, "1" when it refused."""
    return bash(gate, tmp_path, 'check "$2" "$3" "$4"', expected, reported, noise).out.strip()


def test_correct_version_is_accepted(gate, tmp_path):
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", "1.2.17"), "0", "an exactly matching version must pass"
    )
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", "rdc 1.2.17"),
        "0",
        "the version may sit inside a longer line",
    )
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", "1.2.17", "Setting up rediacc-cli (1.2.17) ..."),
        "0",
        "install noise must not break a correct run",
    )
    gate.log_pass("a container reporting the expected version passes")


def test_the_incident_is_caught(gate, tmp_path):
    """The exact 2026-08-07 shape: a 1.2.16 binary installed under the 1.2.17
    label, exiting 0 the whole way. This is what the seven methods could not
    see."""
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", "1.2.16"), "1", "a 1.2.16 binary must FAIL a 1.2.17 run"
    )
    gate.assert_eq(
        check(gate, tmp_path, "1.2.1", "1.2.16"), "1", "1.2.1 must not be satisfied by 1.2.16"
    )
    gate.log_pass("the mislabelled-binary case now fails")


def test_nothing_reported_is_never_a_pass(gate, tmp_path):
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", ""), "1", "a binary that printed no version must FAIL"
    )
    gate.assert_eq(check(gate, tmp_path, "", "1.2.17"), "1", "an empty expected version must FAIL")
    gate.log_pass("an unestablished version fails instead of passing")


def test_transcript_noise_cannot_satisfy_the_check(gate, tmp_path):
    """The reason the comparison is fenced. apt-get, npm and brew all print the
    version they are installing; if the host matched against the whole
    transcript, that line alone would satisfy the check even when the binary
    reported something else entirely."""
    noise = "Setting up rediacc-cli (1.2.17) ..."
    gate.assert_eq(
        check(gate, tmp_path, "1.2.17", "1.2.16", noise),
        "1",
        "the installer's own version line must NOT satisfy the check",
    )

    # And the control: an unfenced whole-transcript grep -- what a naive fix
    # would have done -- DOES accept it. Without this, the fence would be
    # decorative and nobody would know.
    raw = bash(gate, tmp_path, 'fake_container "$2" "$3" 2>&1', "1.2.16", noise)
    naive = "0" if "1.2.17" in raw.combined else "1"
    gate.assert_eq(
        naive, "0", "an unfenced grep must accept the wrong binary, or this test proves nothing"
    )
    gate.log_pass("fencing is what stops the installer's own output from passing the check")


def test_a_failing_container_fails_the_test(gate, tmp_path):
    result = bash(
        gate,
        tmp_path,
        'VERSION=1.2.17\nrun_container_version_test "T" fake_container_fails '
        ">/dev/null 2>&1 && echo 0 || echo 1",
    )
    gate.assert_eq(result.out.strip(), "1", "a container that exits non-zero must fail")
    gate.log_pass("a failed install is a failure, not a missing version")


def test_fence_extraction_takes_only_the_fenced_region(gate, tmp_path):
    raw = bash(gate, tmp_path, 'fake_container "$2" "$3"', "1.2.16", "noise before 1.2.17")
    extracted = bash(gate, tmp_path, 'extract_fenced_version "$2"', raw.out)
    gate.assert_eq(extracted.out.strip(), "1.2.16", "only the fenced region is extracted")
    unfenced = bash(gate, tmp_path, 'extract_fenced_version "$2"', "no markers here at all")
    gate.assert_eq(
        unfenced.out.strip(),
        "",
        "an unfenced transcript yields nothing, which verify_version refuses",
    )
    gate.log_pass("extraction returns the binary's own output and nothing else")


def test_every_container_method_routes_through_the_fence(gate):
    """Structural, so a future edit that reverts one method to a bare
    `${PKG_BINARY_NAME} --version` is caught here rather than in a release."""
    for fn in FENCED_METHODS:
        body = extract_fn(gate, fn)
        gate.assert_contains(
            body, "run_container_version_test", "%s must verify its version host-side" % fn
        )
        gate.assert_contains(body, "version_fence_probe", "%s must fence its version output" % fn)

    # Discrimination check: the assertion above must be capable of NOT matching.
    # test_docker_pull_and_run verifies its version without a container fence
    # (it captures `docker run --rm <image> --version` directly), so it must not
    # contain either token -- if it did, the loop above would be matching
    # something present in every function and asserting nothing.
    body = extract_fn(gate, "test_docker_pull_and_run")
    gate.assert_not_contains(
        body,
        "version_fence_probe",
        "the structural check must be able to miss, or it proves nothing",
    )
    gate.assert_contains(
        body, "verify_version", "test_docker_pull_and_run still compares its version directly"
    )
    gate.log_pass("all seven container install methods verify a version")
