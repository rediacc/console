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
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts/gates", "check-embed-arch-parity.ts")
REAL_LOCKFILE = paths.from_root("private", "renet", "embed-assets.lock.json")
# The gate reads the Dockerfile from BESIDE the lockfile, so every fixture directory carries a copy of the real one.
REAL_DOCKERFILE = paths.from_root("private", "renet", "Dockerfile")

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


def real_dockerfile(gate) -> str:
    if not REAL_DOCKERFILE.is_file():
        gate.log_fail(
            "%s is absent, so the digest cross-check could not run. Fix: %s"
            % (paths.relative_to_root(REAL_DOCKERFILE), SUBMODULE_FIX)
        )
    return REAL_DOCKERFILE.read_text(encoding="utf-8")


def run_with_mutation(gate, tmp_path, mutate, mutate_dockerfile=None) -> harness.RunResult:
    """The twin's `run_with_filter`, with a Python edit in place of a jq filter.

    Both inputs are copies of the REAL files in one directory, because the gate finds the Dockerfile beside the lockfile. `mutate_dockerfile`, when given, maps the real Dockerfile text to the planted one; passing `None` for its RESULT omits the Dockerfile from the fixture altogether.
    """
    data = real_lockfile(gate)
    mutate(data)
    fixture = tmp_path / "lock.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")
    dockerfile = real_dockerfile(gate)
    if mutate_dockerfile is not None:
        dockerfile = mutate_dockerfile(dockerfile)
    if dockerfile is not None:
        (tmp_path / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    return run_gate(gate, env={"EMBED_PARITY_LOCKFILE": str(fixture)})


def unchanged(_data) -> None:
    """The identity mutation, for cases that plant into the Dockerfile only or not at all."""


def omit_dockerfile(_text) -> None:
    """Leave the Dockerfile out of the fixture directory entirely."""


def replace_once(gate, text: str, old: str, new: str) -> str:
    """A plant that silently matched nothing would make the case pass for the wrong reason, so a missing anchor is a failure."""
    if text.count(old) != 1:
        gate.log_fail(
            "plant anchor %r occurs %d times in the fixture, expected 1" % (old, text.count(old))
        )
    return text.replace(old, new)


def dockerfile_arg(gate, text: str, name: str) -> str:
    match = re.search(r"^ARG %s=(\S+)$" % re.escape(name), text, re.MULTILINE)
    if not match:
        gate.log_fail("the real Dockerfile declares no ARG %s; the digest cases need it" % name)
    return match.group(1)


def test_accepts_real_lockfile(gate):
    real_lockfile(gate)  # refuses loudly rather than skipping; see the module docstring
    result = run_gate(gate)
    gate.assert_exit(0, result, "the real lockfile should pass arch parity")
    gate.assert_contains(result.combined, "arch entries", "success output reports what it checked")
    gate.log_pass("real lockfile passes arch parity")


def test_accepts_unmutated_fixture_copy(gate, tmp_path):
    """CONTROL for every case below: the fixture pipeline itself passes, so each red that follows is the plant's doing, not the copy's."""
    result = run_with_mutation(gate, tmp_path, unchanged)
    gate.assert_exit(0, result, "an unmutated copy of the real lockfile and Dockerfile should pass")
    gate.assert_contains(
        result.combined,
        "match their version and the Dockerfile digest",
        "success line reports the cross-check ran",
    )
    gate.assert_not_contains(
        result.combined, " 0 download arch", "the cross-check saw at least one download arch"
    )
    gate.log_pass("an unmutated fixture copy passes, with the download cross-check counted")


def test_rejects_stale_zot_url_version(gate, tmp_path):
    """The defect this check was added for: zot's url stayed at v2.1.18 through two version bumps."""

    def mutate(data):
        zot = data["components"]["zot"]
        zot["arches"]["amd64"]["url"] = zot["arches"]["amd64"]["url"].replace(
            "v%s" % zot["version"], "v2.1.18"
        )

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a download url naming an older version should fail")
    gate.assert_contains(
        result.combined,
        "zot/amd64: url does not carry the component version",
        "error names component, arch, field",
    )
    gate.assert_contains(result.combined, "v2.1.18", "error quotes the stale lockfile url")
    gate.assert_not_contains(
        result.combined, "zot/arm64: url", "the untouched arch is not reported"
    )
    gate.log_pass("a stale zot url version is rejected, naming the arch and the stale value")


def test_rejects_version_prefix_of_url_version(gate, tmp_path):
    """Boundary: version 2.1.2 must NOT be satisfied by a url naming v2.1.22, or a substring match passes a stale url."""

    def mutate(data):
        zot = data["components"]["zot"]
        for entry in zot["arches"].values():
            entry["url"] = entry["url"].replace("v%s" % zot["version"], "v2.1.22")
        zot["version"] = "2.1.2"

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a version that is only a prefix of the url's version should fail")
    gate.assert_contains(
        result.combined, "expected it to name version '2.1.2'", "error names the expected version"
    )
    gate.log_pass("a version matching only as a prefix of the url's version is rejected")


def test_accepts_url_encoded_plus(gate, tmp_path):
    """Must NOT fire: k3s's `+k3s1` spelled `%2B` in the url is the same version."""

    def mutate(data):
        for entry in data["components"]["k3s"]["arches"].values():
            entry["url"] = entry["url"].replace("+", "%2B")

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(0, result, "a %2B-encoded k3s url should still carry the version")
    gate.log_pass("a URL-encoded '+' in the k3s url is accepted")


def test_rejects_sha256_differing_from_dockerfile(gate, tmp_path):
    def mutate(data):
        data["components"]["zot"]["arches"]["arm64"]["sha256"] = "0" * 64

    result = run_with_mutation(gate, tmp_path, mutate)
    gate.assert_exit(1, result, "a well-shaped digest that is not the Dockerfile's should fail")
    gate.assert_contains(
        result.combined,
        "zot/arm64: sha256 differs from the Dockerfile",
        "error names component, arch, field",
    )
    gate.assert_contains(result.combined, "0" * 64, "error quotes the lockfile value")
    gate.assert_contains(result.combined, "ARG ZOT_SHA256_ARM64", "error names the Dockerfile ARG")
    gate.log_pass("a lockfile digest differing from the Dockerfile ARG is rejected")


def test_reads_the_dockerfile(gate, tmp_path):
    """CONTROL that the check reads the Dockerfile at all: the lockfile is UNCHANGED, only the Dockerfile ARG moves."""
    planted = "f" * 64

    def plant(text):
        old = dockerfile_arg(gate, text, "K3S_SHA256_AMD64")
        return replace_once(
            gate, text, "ARG K3S_SHA256_AMD64=%s" % old, "ARG K3S_SHA256_AMD64=%s" % planted
        )

    result = run_with_mutation(gate, tmp_path, unchanged, plant)
    gate.assert_exit(1, result, "a Dockerfile digest the lockfile does not carry should fail")
    gate.assert_contains(
        result.combined,
        "k3s/amd64: sha256 differs from the Dockerfile",
        "error names component and arch",
    )
    gate.assert_contains(
        result.combined,
        "expected '%s'" % planted,
        "the expected value comes from the planted Dockerfile",
    )
    gate.log_pass("a moved Dockerfile ARG with the lockfile unchanged is rejected")


def test_rejects_unmappable_download_component(gate, tmp_path):
    """Fail closed: a download arch with no `ARG <NAME>_SHA256_<ARCH>` is a finding, not a skip."""

    def plant(text):
        old = dockerfile_arg(gate, text, "ZOT_SHA256_AMD64")
        return replace_once(
            gate, text, "ARG ZOT_SHA256_AMD64=%s" % old, "ARG ZOT_DIGEST_AMD64=%s" % old
        )

    result = run_with_mutation(gate, tmp_path, unchanged, plant)
    gate.assert_exit(1, result, "a download arch the Dockerfile has no digest ARG for should fail")
    gate.assert_contains(
        result.combined, "zot/amd64: no 'ARG ZOT_SHA256_AMD64", "error names the ARG it looked for"
    )
    gate.log_pass("a download arch with no Dockerfile digest ARG is rejected")


def test_rejects_missing_dockerfile(gate, tmp_path):
    """Fail closed: a Dockerfile that cannot be read is a failure while a download arch needs it."""
    result = run_with_mutation(gate, tmp_path, unchanged, omit_dockerfile)
    gate.assert_exit(1, result, "an unreadable Dockerfile should fail, not skip the cross-check")
    gate.assert_contains(
        result.combined, "cannot read", "error says the Dockerfile could not be read"
    )
    gate.log_pass("a missing Dockerfile is rejected rather than skipping the digest cross-check")


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
