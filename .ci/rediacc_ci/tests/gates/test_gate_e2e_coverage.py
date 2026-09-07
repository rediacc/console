"""Port of `.ci/scripts/test/gates/test-e2e-coverage.sh`.

Integration test for the FORWARD half of the e2e-coverage gate
(`scripts/check-e2e-coverage.ts`), driven through its `E2E_COV_*` overrides
against a controlled fixture tree.

"Prove the instrument": the primary case PLANTS a renet function whose only
mention is a NON-LIVE file (a test the config does not select) plus its
declared-but-uncalled harness method, and asserts the gate FIRES and names it.
The negative control plants two verbs a live test genuinely covers (one via the
harness method map, one via a raw verb literal) and asserts the gate stays silent
about them. The remaining cases exercise the allowlist pass, the stale-entry
guard, and the registry/workflow drift self-check.

The fixture is entirely inside `tmp_path`; the only real-tree access is READING
`scripts/check-e2e-coverage.ts` to run it.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-e2e-coverage.sh"

GATE = paths.from_root("scripts", "check-e2e-coverage.ts")

FUNCTIONS_TS = """export const RENET_FUNCTIONS = [
  'live_verb',
  'litonly_verb',
  'dead_verb',
] as const;
export const RENET_BRIDGE_FUNCTIONS = ['live_verb', 'litonly_verb', 'dead_verb'] as const;
"""

# Plain-object config (no @playwright/test import needed): the gate reads
# .default.projects/testDir/testMatch, which is all defineConfig would give.
CONFIG_TS = """export default {
  testDir: './tests',
  projects: [{ name: 'test-01', testMatch: '01-*.test.ts' }],
};
"""

METHODS_TS = """export class FixtureMethods {
  async liveVerb(): Promise<unknown> {
    return this.testFunction({ function: 'live_verb' });
  }
  async deadVerb(): Promise<unknown> {
    return this.testFunction({ function: 'dead_verb' });
  }
}
"""

LIVE_TEST_TS = """test('covers live_verb via the method map', async () => {
  await runner.liveVerb();
  const shellForm = 'litonly_verb';
  expect(shellForm).toBeTruthy();
});
"""

# DARK file: not matched by '01-*'. dead_verb lives ONLY here plus in the method
# declaration, so a correct gate must flag it.
DARK_TEST_TS = """test('this suite is never selected by any live config', async () => {
  await runner.deadVerb();
  const dead = 'dead_verb';
  expect(dead).toBeTruthy();
});
"""

WORKFLOW_YML = """jobs:
  e2e:
    steps:
      - run: .ci/scripts/test/run-e2e.sh --workers 1 --config playwright.fixture.config.ts
"""


def build_fixture(gate, root):
    """One live suite (01-live) covers live_verb (via the harness method map: it
    calls .liveVerb()) and litonly_verb (via a raw 'litonly_verb' literal). One
    DARK suite (99-dark, unselected by the config's '01-*' testMatch) is the only
    place dead_verb is mentioned or its method called."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    for rel in (
        "e2e/tests",
        "e2e/src/utils/bridge/methods",
        "e2e/src/utils/bridge/helpers",
        "workflows",
    ):
        root.joinpath(*rel.split("/")).mkdir(parents=True, exist_ok=True)
    (root / "functions.generated.ts").write_text(FUNCTIONS_TS, encoding="utf-8")
    (root / "e2e" / "playwright.fixture.config.ts").write_text(CONFIG_TS, encoding="utf-8")
    (root / "e2e" / "src" / "utils" / "bridge" / "methods" / "FixtureMethods.ts").write_text(
        METHODS_TS, encoding="utf-8"
    )
    (root / "e2e" / "tests" / "01-live.test.ts").write_text(LIVE_TEST_TS, encoding="utf-8")
    (root / "e2e" / "tests" / "99-dark.test.ts").write_text(DARK_TEST_TS, encoding="utf-8")
    (root / "workflows" / "ci.yml").write_text(WORKFLOW_YML, encoding="utf-8")
    (root / "allowlist").write_text("", encoding="utf-8")
    return root


def run_gate(gate, root, registry: str = "playwright.fixture.config.ts") -> harness.RunResult:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    harness.require_tool("npx", "install Node.js; this gate drives scripts/check-e2e-coverage.ts")
    return harness.run(
        ["npx", "tsx", str(GATE)],
        env={
            "E2E_COV_E2E_DIR": str(root / "e2e"),
            "E2E_COV_FUNCTIONS_FILE": str(root / "functions.generated.ts"),
            "E2E_COV_WORKFLOWS_DIR": str(root / "workflows"),
            "E2E_COV_ALLOWLIST": str(root / "allowlist"),
            "E2E_COV_REGISTRY": registry,
        },
        timeout=300,
    )


def test_fires_on_dark_only_verb(gate, tmp_path):
    result = run_gate(gate, build_fixture(gate, tmp_path))
    gate.assert_exit_code(1, result.rc, "gate must fire when a verb is covered only by a dark file")
    gate.assert_contains(result.combined, "dead_verb", "the red list names the uncovered verb")
    gate.log_pass("RED-FIRST: gate fires and names the dark-only verb")


def test_negative_control_live_verbs_pass(gate, tmp_path):
    result = run_gate(gate, build_fixture(gate, tmp_path))
    # live_verb (method map) and litonly_verb (raw literal) are genuinely covered
    # by the live suite -- a gate that flagged them would be crying wolf.
    gate.assert_not_contains(
        result.combined, "live_verb", "method-map-covered verb must NOT be flagged"
    )
    gate.assert_not_contains(
        result.combined, "litonly_verb", "literal-covered verb must NOT be flagged"
    )
    gate.log_pass("negative control: live-suite-covered verbs are not flagged")


def test_comment_mention_is_not_coverage(gate, tmp_path):
    """A COMMENT IS NOT COVERAGE. This is the one that was live: a storage test
    asserted a retirement message names its replacement, and the verb literal in
    that assertion plus the comment explaining it made backup_restore read as
    exercised. The gate then demanded its allowlist entry be deleted as a debt
    paid. Stripping comments also exposed machine_uninstall, whose only trace was
    a header comment listing a whole domain."""
    root = build_fixture(gate, tmp_path)
    # dead_verb is genuinely uncovered. Name it in a COMMENT inside the LIVE
    # suite and nothing else: a gate that reads comments will call it covered.
    (root / "e2e" / "tests" / "01-live.test.ts").write_text(
        "// dead_verb is described here and never called\n"
        "/* dead_verb again, in a block comment */\n" + LIVE_TEST_TS,
        encoding="utf-8",
    )
    result = run_gate(gate, root)
    gate.assert_contains(
        result.combined,
        "dead_verb",
        "a verb named only in comments must still be reported as uncovered",
    )
    gate.log_pass("a comment mention does not confer coverage")


def test_allowlist_silences_dead_verb(gate, tmp_path):
    root = build_fixture(gate, tmp_path)
    (root / "allowlist").write_text(
        "# BLOCKER: dead_verb predates the fixture suite; migration into a live test is "
        "tracked follow-up work\ndead_verb\n",
        encoding="utf-8",
    )
    result = run_gate(gate, root)
    gate.assert_exit_code(0, result.rc, "a BLOCKER-allowlisted uncovered verb should pass")
    gate.log_pass("allowlist with a valid BLOCKER silences the uncovered verb")


def test_missing_blocker_rejected(gate, tmp_path):
    root = build_fixture(gate, tmp_path)
    (root / "allowlist").write_text("dead_verb\n", encoding="utf-8")
    result = run_gate(gate, root)
    gate.assert_exit_code(1, result.rc, "allowlist entry without a BLOCKER should fail")
    gate.assert_contains(result.combined, "BLOCKER", "error demands a BLOCKER reason")
    gate.log_pass("allowlist entry without a BLOCKER is rejected")


def test_stale_allowlist_entry_rejected(gate, tmp_path):
    root = build_fixture(gate, tmp_path)
    # live_verb IS covered by the live suite -- allowlisting it is stale debt.
    (root / "allowlist").write_text(
        "# BLOCKER: live_verb is genuinely covered so this entry is stale by construction "
        "for the test\nlive_verb\n",
        encoding="utf-8",
    )
    result = run_gate(gate, root)
    gate.assert_exit_code(1, result.rc, "an allowlisted-but-covered verb should fail as stale")
    gate.assert_contains(result.combined, "live_verb", "the stale entry is named")
    gate.log_pass("stale allowlist entry (now covered) is rejected")


def test_registry_workflow_drift_rejected(gate, tmp_path):
    root = build_fixture(gate, tmp_path)
    # Registry names a second config that no workflow runs -> drift.
    result = run_gate(gate, root, "playwright.fixture.config.ts,playwright.ghost.config.ts")
    gate.assert_exit_code(
        1, result.rc, "a config in the registry that no workflow runs should fail"
    )
    gate.assert_contains(
        result.combined, "playwright.ghost.config.ts", "the drift error names the ghost config"
    )
    gate.log_pass("registry/workflow drift self-check fires")
