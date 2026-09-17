"""Port of `.ci/scripts/test/gates/test-releaseversion-inject-env.sh`.

Both-ways test for `.ci/scripts/version/inject-env.sh --strict`.

WHAT THE GUARD IS FOR. `--strict` is the one guard in the repo against a build
stamping a placeholder or bogus version into an artifact that CD will later
publish under a real tag.

WHAT WAS BROKEN. It had ZERO callers -- referenced only by a comment in
`.ci/config/constants.sh` and by its own header -- while every build boundary
spelled `|| '0.0.0-dev'` or `${CLI_VERSION:-0.0.0-dev}` inline instead. A guard
nothing calls cannot fire. On top of that it compared the resolved version
against the literal string "0.0.0-dev" and nothing else, so an EMPTY version, or
a resolver that exited 0 printing nothing, sailed straight through the strictest
setting the script has.

The empty-resolver case gets a fixture: inject-env.sh finds resolve-version.sh
next to itself, so the only way to plant "resolver succeeds but prints nothing"
is to run a copy with a planted sibling.

WHAT THIS MODULE READS FROM THE REAL TREE, and why that is safe for the parity
driver: the reachability case READS four release-path build boundaries and
writes nowhere in them. The falsifying half builds its own stripped copies under
`tmp_path`, exactly as the twin does.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-releaseversion-inject-env.sh"

GATE = paths.from_root(".ci", "scripts", "version", "inject-env.sh")

# Every release-path boundary that must invoke --strict. Listed once, so the count below is derived from this tuple rather than typed twice.
STRICT_CALLERS = (
    ".github/workflows/ci-build-cli.yml",
    ".github/workflows/ci-build-docker.yml",
    ".ci/scripts/build/build-cli-executables.sh",
    ".ci/scripts/build/build-cli-musl.sh",
)

EMPTY_RESOLVER = """#!/bin/bash
# Exits 0, prints nothing: the shape --strict used to accept as a version.
exit 0
"""


def subject(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    return GATE


def run_inject(gate, *args: str, **env: str) -> harness.RunResult:
    """The streams stay APART: the twin routes stderr into a file for the same
    reason, because the failure message is what says WHY it refused."""
    return harness.run(["bash", str(subject(gate)), *args], env=env or None, timeout=120)


def strict_callers(root) -> int:
    """How many of the four boundaries invoke --strict, under `root`."""
    found = 0
    for name in STRICT_CALLERS:
        path = root.joinpath(*name.split("/"))
        try:
            if "--strict" in path.read_text(encoding="utf-8"):
                found += 1
        except OSError:
            continue
    return found


def test_accepts_a_real_version(gate):
    result = run_inject(gate, "--version", "1.2.17", "--strict", "--print")
    gate.assert_exit_code(0, result.rc, "a real version must pass --strict")
    gate.assert_eq(result.out.strip(), "1.2.17", "and print unchanged")
    gate.log_pass("--strict accepts 1.2.17")


def test_rejects_the_placeholder(gate):
    result = run_inject(gate, "--version", "0.0.0-dev", "--strict", "--print")
    gate.assert_exit_code(1, result.rc, "0.0.0-dev must fail under --strict")
    gate.assert_contains(result.err, "0.0.0-dev", "the failure must name the placeholder")
    gate.log_pass("--strict rejects 0.0.0-dev")


def test_rejects_an_empty_version(gate):
    """THE CONTROL for the hole the original check had: it compared only against
    the literal "0.0.0-dev", so an empty version was "not 0.0.0-dev" and passed."""
    result = run_inject(gate, "--version", "", "--strict", "--print")
    gate.assert_exit_code(1, result.rc, "an empty --version must fail under --strict")
    gate.assert_contains(result.err, "empty", "the failure must say the version was empty")

    # And it is refused without --strict too: an explicitly-supplied empty version used to fall through to the resolver and silently pick up the CURRENT tag, i.e. the version that is already published.
    result = run_inject(gate, "--version", "", "--print")
    gate.assert_exit_code(1, result.rc, "an empty --version must fail even without --strict")
    gate.log_pass("empty --version is refused, strict or not")


def test_rejects_a_malformed_version(gate):
    for value in ("1.2.x", "latest", "none", "<html>404</html>"):
        result = run_inject(gate, "--version", value, "--strict", "--print")
        gate.assert_exit_code(1, result.rc, "'%s' must fail under --strict" % value)
    # Without --strict the same values still resolve: dev and local builds are not in the business of policing versions.
    result = run_inject(gate, "--version", "latest", "--print")
    gate.assert_exit_code(0, result.rc, "non-strict resolution must stay permissive")
    gate.assert_eq(result.out.strip(), "latest", "and yield the value it was given")
    gate.log_pass("--strict rejects malformed versions, non-strict does not")


def test_reads_the_VERSION_env(gate):  # noqa: N802 -- the twin's case name; parity compares by name
    result = run_inject(gate, "--strict", "--print", VERSION="1.4.0")
    gate.assert_exit_code(0, result.rc, "VERSION env must be used when no --version is given")
    gate.assert_eq(result.out.strip(), "1.4.0", "and its value is what is printed")

    result = run_inject(gate, "--strict", "--print", VERSION="0.0.0-dev")
    gate.assert_exit_code(1, result.rc, "VERSION=0.0.0-dev must fail under --strict")
    gate.log_pass("$VERSION path is policed the same way")


def test_empty_resolver_output_is_not_a_version(gate, tmp_path):
    """THE CONTROL for the second half of the same hole: a resolver that exits 0
    printing nothing produced an EMPTY resolved version, which --strict accepted.
    Planted in a fixture because inject-env.sh resolves its sibling by path."""
    version_dir = tmp_path / "version"
    version_dir.mkdir(parents=True, exist_ok=True)
    copy = version_dir / "inject-env.sh"
    copy.write_text(subject(gate).read_text(encoding="utf-8"), encoding="utf-8")
    copy.chmod(0o755)
    resolver = version_dir / "resolve-version.sh"
    resolver.write_text(EMPTY_RESOLVER, encoding="utf-8")
    resolver.chmod(0o755)

    result = harness.run(
        ["bash", "./version/inject-env.sh", "--strict", "--print"], cwd=tmp_path, timeout=120
    )
    gate.assert_exit_code(1, result.rc, "an empty resolver result must not pass --strict")

    # Non-strict must degrade to the documented dev placeholder, not to "".
    result = harness.run(["bash", "./version/inject-env.sh", "--print"], cwd=tmp_path, timeout=120)
    gate.assert_eq(
        result.out.strip(),
        "0.0.0-dev",
        "non-strict must fall back to the placeholder, not an empty string",
    )
    gate.log_pass("empty resolver output is refused, and non-strict degrades to the placeholder")


def test_guard_is_reachable_from_the_release_path(gate, tmp_path):
    """THE OTHER HALF OF FINDING 8, and the half that made the guard worthless:
    it had no callers. A --strict that nothing invokes is indistinguishable from
    no guard at all, which is what shipped for the whole life of the flag."""
    root = paths.repo_root()
    gate.assert_eq(
        strict_callers(root),
        len(STRICT_CALLERS),
        "all %d release-path build boundaries must call inject-env.sh --strict"
        % len(STRICT_CALLERS),
    )

    # PROVE THIS COUNT CAN FALL: strip the invocations in a COPY and watch it drop to zero -- the exact state the repo was in before this wave. The copy
    # lives under tmp_path; the real boundaries are read and never written.
    for name in STRICT_CALLERS:
        src = root.joinpath(*name.split("/"))
        dest = tmp_path.joinpath(*name.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        kept = [ln for ln in src.read_text(encoding="utf-8").splitlines() if "--strict" not in ln]
        dest.write_text("\n".join(kept) + "\n", encoding="utf-8")
    gate.assert_eq(
        strict_callers(tmp_path),
        0,
        "planted no-caller tree must count zero (else this control proves nothing)",
    )
    gate.log_pass("the guard is reachable, and the check notices when it is not")
