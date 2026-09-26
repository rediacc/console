"""Port of `.ci/scripts/test/gates/test-embed-arch-parity.sh`, retired in W7 P5.

Both-ways test for `scripts/gates/check-embed-arch-parity.ts`.

The gate exists because arm64 criu silently became a different version from amd64 criu and every existing gate stayed green: nothing carried an architecture dimension, so a per-arch divergence was structurally invisible. A gate for that
class is worthless unless it demonstrably FIRES, so every defect class below is
planted into a fixture lockfile and asserted to fail, and the real lockfile is asserted to pass.

WHAT THE PORT CHANGES, AND WHAT IT DELIBERATELY DOES NOT. The twin builds each mutant lockfile with `jq <filter> <real lockfile>`; the port loads the real lockfile with `json` and applies the same edit as a dict operation. That drops a dependency on `jq` being installed, and it makes each mutation READABLE as what it does rather than as a filter string. What it does NOT change is
the SOURCE: every fixture is still derived from the REAL `private/renet/embed-assets.lock.json`, so a lockfile that grows a new component grows a new fixture on its own, and a hand-typed fixture cannot drift away from the thing being guarded.

THE SUBMODULE-ABSENT PATH IS A REFUSAL HERE, NOT A PASS, and that is the one place this port disagrees with its twin on purpose. The twin logs `log_pass "renet submodule absent, skipping"` and returns, which folds "could not check" into "checked and fine" -- the exact shape this directory exists to refuse. The port fails loudly with the fix line instead. This CANNOT diverge the
verdict on any tree that has the submodule, which is every tree CI runs on and this one; on a tree without it the port is the stricter of the two, which is the safe direction.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts/gates", "check-embed-arch-parity.ts")
REAL_LOCKFILE = paths.from_root("private", "renet", "embed-assets.lock.json")

SUBMODULE_FIX = (
    "git submodule update --init private/renet; the lockfile this gate guards lives "
    "there, and without it these cases would report a pass having compared nothing"
)


def real_lockfile(gate) -> dict:
    if not REAL_LOCKFILE.is_file():
        gate.log_fail(
            "%s is absent, so nothing here could run. Fix: %s"
            % (paths.relative_to_root(REAL_LOCKFILE), SUBMODULE_FIX)
        )
    return json.loads(REAL_LOCKFILE.read_text(encoding="utf-8"))


def run_gate(gate, env: dict[str, str] | None = None) -> harness.RunResult:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(GATE)], cwd=paths.repo_root(), env=env)


def run_with_mutation(gate, tmp_path, mutate) -> harness.RunResult:
    """The twin's `run_with_filter`, with a Python edit in place of a jq filter."""
    data = real_lockfile(gate)
    mutate(data)
    fixture = tmp_path / "lock.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")
    return run_gate(gate, env={"EMBED_PARITY_LOCKFILE": str(fixture)})


def test_accepts_real_lockfile(gate):
    real_lockfile(gate)  # refuses loudly rather than skipping; see the module docstring
    result = run_gate(gate)
    gate.assert_exit(0, result, "the real lockfile should pass arch parity")
    gate.assert_contains(result.combined, "arch entries", "success output reports what it checked")
    gate.log_pass("real lockfile passes arch parity")


def test_rejects_missing_arch(gate, tmp_path):
    def mutate(data):
        del data["components"]["criu"]["arches"]["arm64"]

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a component missing an arch should fail")
    gate.assert_contains(result.combined, "architectures", "error names the arch mismatch")
    gate.log_pass("a component that loses an architecture is rejected")


def test_rejects_malformed_digest(gate, tmp_path):
    def mutate(data):
        data["components"]["k3s"]["arches"]["amd64"]["sha256"] = "not-a-digest"

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a malformed download digest should fail")
    gate.assert_contains(result.combined, "sha256", "error names the digest")
    gate.log_pass("a malformed download digest is rejected")


def test_rejects_unpinned_source(gate, tmp_path):
    def mutate(data):
        data["components"]["criu"]["source"].pop("commit", None)

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a source build without a commit pin should fail")
    gate.assert_contains(result.combined, "commit", "error names the missing pin")
    gate.log_pass("a source build with no immutable pin is rejected")


def test_rejects_bad_class(gate, tmp_path):
    def mutate(data):
        data["components"]["zot"]["class"] = "bogus"

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "an invalid class should fail")
    gate.assert_contains(result.combined, "base|cluster", "error names the valid classes")
    gate.log_pass("an invalid asset class is rejected")


def test_rejects_empty_lockfile(gate, tmp_path):
    """Anti-vacuity: a lockfile with nothing in it must never report parity."""

    def mutate(data):
        data["components"] = {}

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "an empty lockfile should fail, not vacuously pass")
    gate.assert_contains(result.combined, "blind", "error says the gate would be blind")
    gate.log_pass("an empty lockfile is rejected rather than vacuously passing")


def test_the_mutations_are_still_reachable(gate):
    """PORT-ONLY. Every case above edits a NAMED component out of the real lockfile, and a rename would turn each of those edits into a KeyError that pytest renders as an ERROR rather than as a finding about arch parity.

    This says which names the fixtures depend on, in one place, so a lockfile that drops `criu`, `k3s` or `zot` reds here with a sentence a reader can act on instead of five stack traces.
    """
    data = real_lockfile(gate)
    components = data.get("components", {})
    for name in ("criu", "k3s", "zot"):
        if name not in components:
            gate.log_fail(
                "the fixtures above mutate component %r, which the real lockfile no "
                "longer declares. Re-point them at a component that exists; a fixture "
                "naming a dead asset stops proving anything." % name
            )
    gate.assert_contains(
        json.dumps(components["criu"].get("arches", {})),
        "arm64",
        "criu still carries the arm64 arch the missing-arch case deletes",
    )
    gate.log_pass(
        "all 3 mutated component(s) exist in the real lockfile (%d component(s) total)"
        % len(components)
    )
