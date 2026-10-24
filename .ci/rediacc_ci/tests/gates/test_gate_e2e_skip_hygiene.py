"""`scripts/gates/check-e2e-skip-hygiene.ts`, driven through tsx over fixture trees (seam: `E2E_HYGIENE_ROOT`).

Each case builds a small `packages/e2e-tests` and reads the gate's real exit code and stderr. The first case is the control: the clean fixture must exit 0, so a later red is the planted defect and not a broken fixture.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts", "gates", "check-e2e-skip-hygiene.ts")
OMITTED = "ops-lifecycle/18-ops-lifecycle.test.ts"

BASE = "import x from 'y';\nexport default { testDir: './tests', testMatch: %s, testIgnore: ['**/ops-lifecycle/**'] };\n"


def _tree(tmp_path: pathlib.Path, *, match: str = "'*.test.ts'", files=("a.test.ts", OMITTED)):
    e2e = tmp_path / "packages" / "e2e-tests"
    (e2e / "tests").mkdir(parents=True)
    (e2e / "playwright.config.ts").write_text(BASE % match, encoding="utf-8")
    for rel in files:
        path = e2e / "tests" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return tmp_path


def _run(root: pathlib.Path) -> harness.RunResult:
    npx = harness.require_tool("npx", "install node; the subject is driven through tsx")
    return harness.run(
        [npx, "tsx", str(GATE)], cwd=paths.repo_root(), env={"E2E_HYGIENE_ROOT": str(root)}
    )


def test_control_clean_fixture_passes(gate, tmp_path):
    gate.assert_exit(0, _run(_tree(tmp_path)), "the clean fixture is the control")
    gate.log_pass("control green")


def test_a_stale_deliberate_omission_key_reds(gate, tmp_path):
    result = _run(_tree(tmp_path, files=("a.test.ts",)))
    gate.assert_exit(1, result, "a key naming no file exempts a future test")
    gate.assert_contains(result.err, "no longer exist", "and says why")
    gate.log_pass("stale omission keys are refused")


def test_a_regexp_testmatch_is_refused_not_defaulted(gate, tmp_path):
    result = _run(_tree(tmp_path, match="/.*\\.test\\.ts$/"))
    gate.assert_exit(1, result, "an unreadable testMatch must not fall back to the default")
    gate.assert_contains(result.err, "cannot read it", "and names the limit")
    gate.log_pass("a RegExp testMatch fails loudly")


def test_an_extglob_testmatch_selects_both_spellings(gate, tmp_path):
    root = _tree(tmp_path, match="'*.@(spec|test).ts'", files=("a.spec.ts", "b.test.ts", OMITTED))
    gate.assert_exit(0, _run(root), "extglob alternatives are selected, not orphaned")
    gate.log_pass("@(a|b) globs are understood")


def test_an_orphaned_spec_file_reds(gate, tmp_path):
    result = _run(_tree(tmp_path, files=("a.test.ts", "b.spec.ts", OMITTED)))
    gate.assert_exit(1, result, "a .spec.ts no config selects is an orphan")
    gate.assert_contains(result.err, "b.spec.ts", "and is named")
    gate.log_pass("spec files are enumerated")
