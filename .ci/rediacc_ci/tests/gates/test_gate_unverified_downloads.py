"""Port of `.ci/scripts/test/gates/test-unverified-downloads.sh`, retired in W7 P5.

Integration test for `scripts/gates/check-unverified-downloads.ts`.

Both-ways, offline, fixture-driven: proves the gate passes the real tree, that its own detector controls run on EVERY invocation, that a bare allowlist entry is refused, and that the allowlist is load-bearing rather than decorative.

THE SHAPES MATTER MORE THAN THE COUNT. Three of them shipped as real defects on 2026-09-01: a curl streamed straight into tar (unverifiable by construction), an image pinned by a MUTABLE tag, and a plain download with no checksum at all.

WHY `test_allowlist_is_load_bearing` IS THE INTERESTING ONE. Every other case here would still pass on a tree where the gate had nothing to find, because "no findings" and "found nothing because the scan is blind" are the same exit code. Emptying the allowlist strips the real exemptions and REQUIRES the gate to go red, which is the only case that distinguishes them. The port keeps
it verbatim and adds nothing, because there is nothing to add.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts/gates", "check-unverified-downloads.ts")


def run(gate, env: dict[str, str] | None = None) -> harness.RunResult:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(GATE)], cwd=paths.repo_root(), env=env)


def test_real_tree_passes(gate):
    result = run(gate)
    gate.assert_exit_code(
        0, result.rc, "the real tree must pass; every fetch is verified or allowlisted"
    )
    gate.log_pass("real tree passes")


def test_controls_run_every_invocation(gate):
    """The gate self-tests its detector on every run, so a green IS the planted-defect proof for the pure logic. This asserts that machinery is actually wired."""
    result = run(gate)
    gate.assert_contains(
        result.combined,
        "controls fired",
        "the detector's own controls must run on every invocation",
    )
    gate.log_pass("controls run unconditionally")


def test_bare_allowlist_entry_is_refused(gate, tmp_path):
    allow = tmp_path / "allow"
    allow.write_text("some-vendor.example.com\n", encoding="utf-8")
    result = run(gate, env={"UNVERIFIED_DOWNLOAD_ALLOWLIST": str(allow)})
    gate.assert_exit_code(
        1, result.rc, "an allowlist entry with no BLOCKER reason must fail the gate"
    )
    gate.assert_contains(
        result.combined, "invalid entries", "the error names the malformed allowlist"
    )
    gate.log_pass("allowlist entry without a BLOCKER reason fires")


def test_allowlist_is_load_bearing(gate, tmp_path):
    """An empty allowlist strips the four real exemptions, so the gate must go red on the tree's genuinely-unverifiable fetches. This is the vacuity guard: it proves the allowlist is doing work rather than the gate having nothing to find."""
    allow = tmp_path / "allow"
    allow.write_text("", encoding="utf-8")
    result = run(gate, env={"UNVERIFIED_DOWNLOAD_ALLOWLIST": str(allow)})
    gate.assert_exit_code(
        1, result.rc, "with an empty allowlist the tree's curl|bash fetches must be reported"
    )
    gate.assert_contains(
        result.combined, "unverified remote artifact", "the failure names the class"
    )
    gate.log_pass("the allowlist is load-bearing, not decorative")
