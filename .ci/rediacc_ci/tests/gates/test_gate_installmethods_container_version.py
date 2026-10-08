"""Port of `.ci/scripts/test/gates/test-installmethods-container-version.sh`, retired in W7 P5.

The container version fence in `rediacc_ci.testrun.install_methods` (written against the bash `test-install-methods.sh`, retired behind its golden, PLAN-retire-bash-oracles B3).

WHY THIS CLASS NEEDS A GATE. On 2026-08-07 a release published CLI binaries built as 1.2.16 under the label 1.2.17. `verify_version()` was one hole (pinned by test_gate_verify_version.py). The other, larger one: SEVEN of the eleven install methods -- apt, dnf, apk, pacman, npm, linuxbrew, quick -- never compared a version at all. Each ended its `docker run ... set -e` heredoc
with a
bare
`${PKG_BINARY_NAME} --version` whose output was never captured and never
compared. `$VERSION` was referenced ZERO times inside any of those functions, so the only assertion was "the installed binary exits 0" -- which a mislabelled binary does.

The fix moves the comparison HOST-side, through verify_version, and fences the container's version output between markers so the transcript's own mentions of the version (apt-get, npm and brew all print it while installing) cannot satisfy the check. Both properties are asserted in both directions: a checker that always failed would satisfy every negative case, one that always
passed would satisfy every positive one, and neither would be a check.

HOW THE FENCE IS DRIVEN. `Runner.container` takes the argv a `docker run` would take, so the stand-in for the container is a `bash -c` that prints the install-transcript noise and then the REAL fenced probe (`version_fence_probe`) around what the "installed binary" reports. The host-side comparison, the fence extraction and the structural check all run against the module's own code.

ARGUMENT ORDER. The retired bash gate called `assert_eq "0" "$(check ...)"`, i.e. EXPECTED first, which is the inverse of `assert_eq`'s own contract (actual first). Same verdict, inverted diagnostic; it is one of 67 such sites across six twins. The port uses the contract's order, so a failure here reads the right way round.
"""

import inspect

from rediacc_ci.testrun import install_methods as port
from rediacc_ci.tests.gates import harness

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

# What reaches the fence: `container()` always reads the fenced region, and `container_method` always calls it.
FENCE_ENTRIES = ("self.container(", "self.container_method(")


def fake_container_argv(reported: str, noise: str = "") -> list[str]:
    """A stand-in for `docker run`: runs the REAL fenced probe the install scripts paste into their container scripts, so the probe itself is under test and not just the host-side comparison. `noise` is surrounding install-transcript output, `reported` is what the "installed binary" prints."""
    script = "set -e\nprintf '%s\\n' \"$1\"\n" + port.version_fence_probe("printf '%s\\n' \"$2\"")
    return ["bash", "-c", script, "_", noise, reported]


def check(expected: str, reported: str, noise: str = "") -> str:
    """ "0" when the fenced host-side comparison accepted, "1" when it refused."""
    runner = port.Runner(port.Config(version=expected))
    return str(runner.container("T", fake_container_argv(reported, noise)))


def test_correct_version_is_accepted(gate, capsys):
    gate.assert_eq(check("1.2.17", "1.2.17"), "0", "an exactly matching version must pass")
    gate.assert_eq(check("1.2.17", "rdc 1.2.17"), "0", "the version may sit inside a longer line")
    gate.assert_eq(
        check("1.2.17", "1.2.17", "Setting up rediacc-cli (1.2.17) ..."),
        "0",
        "install noise must not break a correct run",
    )
    capsys.readouterr()
    gate.log_pass("a container reporting the expected version passes")


def test_the_incident_is_caught(gate, capsys):
    """The exact 2026-08-07 shape: a 1.2.16 binary installed under the 1.2.17 label, exiting 0 the whole way. This is what the seven methods could not see."""
    gate.assert_eq(check("1.2.17", "1.2.16"), "1", "a 1.2.16 binary must FAIL a 1.2.17 run")
    gate.assert_eq(check("1.2.1", "1.2.16"), "1", "1.2.1 must not be satisfied by 1.2.16")
    capsys.readouterr()
    gate.log_pass("the mislabelled-binary case now fails")


def test_nothing_reported_is_never_a_pass(gate, capsys):
    gate.assert_eq(check("1.2.17", ""), "1", "a binary that printed no version must FAIL")
    gate.assert_eq(check("", "1.2.17"), "1", "an empty expected version must FAIL")
    capsys.readouterr()
    gate.log_pass("an unestablished version fails instead of passing")


def test_transcript_noise_cannot_satisfy_the_check(gate, capsys):
    """The reason the comparison is fenced. apt-get, npm and brew all print the version they are installing; if the host matched against the whole transcript, that line alone would satisfy the check even when the binary reported something else entirely."""
    noise = "Setting up rediacc-cli (1.2.17) ..."
    gate.assert_eq(
        check("1.2.17", "1.2.16", noise),
        "1",
        "the installer's own version line must NOT satisfy the check",
    )

    # And the control: an unfenced whole-transcript grep -- what a naive fix would have done -- DOES accept it. Without this, the fence would be decorative and nobody would know.
    raw = harness.run(fake_container_argv("1.2.16", noise))
    naive = "0" if "1.2.17" in raw.combined else "1"
    gate.assert_eq(
        naive, "0", "an unfenced grep must accept the wrong binary, or this test proves nothing"
    )
    capsys.readouterr()
    gate.log_pass("fencing is what stops the installer's own output from passing the check")


def test_a_failing_container_fails_the_test(gate, capsys):
    runner = port.Runner(port.Config(version="1.2.17"))
    code = runner.container(
        "T", ["bash", "-c", "printf 'apt-get: package not found\\n' >&2; exit 3"]
    )
    gate.assert_eq(str(code), "1", "a container that exits non-zero must fail")
    capsys.readouterr()
    gate.log_pass("a failed install is a failure, not a missing version")


def test_fence_extraction_takes_only_the_fenced_region(gate):
    raw = harness.run(fake_container_argv("1.2.16", "noise before 1.2.17"))
    extracted = port.extract_fenced_version(raw.out)
    gate.assert_eq(extracted.strip(), "1.2.16", "only the fenced region is extracted")
    unfenced = port.extract_fenced_version("no markers here at all")
    gate.assert_eq(
        unfenced.strip(),
        "",
        "an unfenced transcript yields nothing, which verify_version refuses",
    )
    gate.log_pass("extraction returns the binary's own output and nothing else")


def test_every_container_method_routes_through_the_fence(gate):
    """Structural, so a future edit that reverts one method to a bare, unfenced `--version` call is caught here rather than in a release."""
    for fn in FENCED_METHODS:
        body = inspect.getsource(getattr(port.Runner, fn))
        if not any(entry in body for entry in FENCE_ENTRIES):
            gate.log_fail("%s must verify its version through the fenced container run" % fn)

    # Discrimination check: the assertion above must be capable of NOT matching. test_docker_pull_and_run verifies its version without a container fence (it captures `docker run --rm <image> --version` directly), so it must contain neither entry -- if it did, the loop above would be matching something present in every function and asserting nothing.
    body = inspect.getsource(port.Runner.test_docker_pull_and_run)
    for entry in FENCE_ENTRIES:
        gate.assert_not_contains(
            body, entry, "the structural check must be able to miss, or it proves nothing"
        )
    gate.assert_contains(
        body, "verify_version", "test_docker_pull_and_run still compares its version directly"
    )
    gate.log_pass("all seven container install methods verify a version")


def test_the_probe_helpers_are_the_modules_own():
    """The stand-in container runs the module's own probe: a probe that stopped fencing would turn every case above into a comparison of the whole transcript."""
    probe = port.version_fence_probe("rdc --version")
    assert probe.startswith('echo "%s"' % port.FENCE_BEGIN)
    assert probe.endswith('echo "%s"' % port.FENCE_END)
