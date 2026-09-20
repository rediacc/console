"""Port of `.ci/scripts/test/gates/test-embed-credits.sh`.

Integration test for `scripts/gates/check-embed-credits.ts`.

Verifies the gate accepts the real in-tree inventories and rejects a Dockerfile pin that has drifted from the lockfile and a hand-edited generated artifact, using the gate's `EMBED_CREDITS_*` path overrides to point at fixtures.

THE SUBMODULE-ABSENT PATH IS A REFUSAL HERE, NOT A SILENT `exit 0`. The twin's guard is `[[ ! -f private/renet/Dockerfile ]] && echo skipping && exit 0`, and that exit is worse than the skip it announces: `run-all.sh` scores a test that exits 0
with no `PASS:` line as a FAILURE, so on a submodule-less tree the twin is red for
a reason its own message calls a skip. The port refuses with the `git submodule update` line instead, which is the same verdict said usefully. On any tree that HAS the submodule -- CI, and this one -- the two agree case for case.

WHY THE TWIN'S `setup_fixtures` HAS NO COUNTERPART HERE. It writes `bad-credits.go` and `missing.json` into a tempdir and NOTHING READS THEM: no case references `$FIXTURE_DIR`, both live cases build their own tempdir. Porting dead fixture-writing would carry the dead weight across, so it is dropped and named here, which is the finding rather than a silent omission.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-embed-credits.sh"

VALIDATOR = paths.from_root("scripts/gates", "check-embed-credits.ts")
DOCKERFILE = paths.from_root("private", "renet", "Dockerfile")
CREDITS_GO = paths.from_root("private", "renet", "pkg", "embed", "credits_data.go")

SUBMODULE_FIX = (
    "git submodule update --init private/renet; every assertion here reads the real "
    "Dockerfile and credits_data.go, so without them nothing was checked"
)


def require_submodule(gate) -> None:
    for path in (DOCKERFILE, CREDITS_GO):
        if not path.is_file():
            gate.log_fail(
                "%s is absent, so this case could not run at all. Fix: %s"
                % (paths.relative_to_root(path), SUBMODULE_FIX)
            )


def run_gate(gate, env: dict[str, str] | None = None) -> harness.RunResult:
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(VALIDATOR)], cwd=paths.repo_root(), env=env)


def test_accepts_real_inventories(gate):
    require_submodule(gate)
    result = run_gate(gate)
    if result.rc != 0:
        gate.log_fail(
            "real in-tree inventories should pass the embed-credits gate: %s" % result.combined
        )
    gate.log_pass("real inventories pass validation")


def test_rejects_dockerfile_pin_drift(gate, tmp_path):
    """The Dockerfile keeps its own ARG defaults so `docker build` works standalone. This is the check that stops those defaults drifting from the lockfile."""
    require_submodule(gate)
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines(keepends=True)
    drifted = []
    replaced = 0
    for line in lines:
        if line.startswith("ARG CRIU_VERSION="):
            drifted.append("ARG CRIU_VERSION=9.9.9\n")
            replaced += 1
        else:
            drifted.append(line)
    # THE CONTROL ON THE CONTROL. A sed that matched nothing would hand the gate a byte-identical Dockerfile, and the case would then be asserting that a CLEAN tree fails -- which is a defect in the test, not in the subject.
    if replaced == 0:
        gate.log_fail(
            "no `ARG CRIU_VERSION=` line in %s, so the planted drift was never planted "
            "and this case would be judging an unmodified Dockerfile"
            % paths.relative_to_root(DOCKERFILE)
        )
    fixture = tmp_path / "Dockerfile"
    fixture.write_text("".join(drifted), encoding="utf-8")
    result = run_gate(gate, env={"EMBED_CREDITS_DOCKERFILE": str(fixture)})
    gate.assert_exit_code(1, result.rc, "a Dockerfile pin drifting from the lockfile should fail")
    gate.assert_contains(result.combined, "CRIU_VERSION", "error names the drifted ARG")
    gate.log_pass("a Dockerfile pin that drifts from the lockfile is rejected")


def test_rejects_stale_generated_artifact(gate, tmp_path):
    """The attribution artifacts are generated from the lockfile; a hand-edit or a forgotten regenerate must be caught rather than silently shipped."""
    require_submodule(gate)
    fixture = tmp_path / "credits_data.go"
    fixture.write_text(
        CREDITS_GO.read_text(encoding="utf-8") + "\n// hand-edited\n", encoding="utf-8"
    )
    result = run_gate(gate, env={"EMBED_CREDITS_GO_FILE": str(fixture)})
    gate.assert_exit_code(1, result.rc, "a stale generated artifact should fail")
    gate.assert_contains(result.combined, "stale", "error says the artifact is stale")
    gate.log_pass("a stale generated attribution artifact is rejected")
