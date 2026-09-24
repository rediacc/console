r"""Port of `.ci/scripts/test/gates/test-regions-sync.sh`, retired in W7 P5.

`check_regions_sync.py` must actually refuse a divergence.

WHY THE GATE EXISTS, restated so this file stands alone: `data.json` is the region list the CLI ships with, and `region-discovery.ts` fetches `${SITE_URL}/regions.json`, which returns 404 (measured 2026-08-26). So the "fallback" is the only list anyone gets, and `index.ts` claimed a build process kept it in step with the root `regions.json` when nothing did.

THE FAILURE THIS TEST GUARDS is not "the files differ" -- it is a comparison that cannot fail. Two empty files compare equal; so do two invalid ones if the parse errors are swallowed. Each refusal below is planted and observed.

HERMETIC: every case runs against tmp_path fixtures via the gate's own `REGIONS_ROOT_FILE` / `REGIONS_BAKED_FILE` seams, so this never edits the real tree and cannot race another session's checkout.

WHAT THIS CANNOT SEE: whether either file's CONTENT is right, and whether the live endpoint serves anything. Both are outside the gate's claim.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUT = paths.from_root(".ci", "scripts", "quality", "check_regions_sync.py")

GOOD = {
    "regions": [
        {"id": "eu", "label": "Europe", "domain": "eu.example"},
        {"id": "us", "label": "US", "domain": "us.example"},
    ]
}


def run_gate(gate, root, baked) -> harness.RunResult:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    return harness.run(
        ["python3", str(SUT)],
        cwd=paths.repo_root(),
        env={"REGIONS_ROOT_FILE": str(root), "REGIONS_BAKED_FILE": str(baked)},
    )


def test_identical_files_pass(gate, tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(GOOD), encoding="utf-8")
    b.write_text(json.dumps(GOOD), encoding="utf-8")
    result = run_gate(gate, a, b)
    if result.rc != 0:
        gate.log_fail(
            "identical files were rejected; every refusal below would then be trivially satisfied",
            result,
        )
    gate.log_pass("identical lists pass")


def test_formatting_alone_is_not_drift(gate, tmp_path):
    # Byte comparison would fail here, and failing on whitespace trains people to reformat rather than to reconcile.
    a = tmp_path / "a.json"
    pretty = tmp_path / "pretty.json"
    a.write_text(json.dumps(GOOD), encoding="utf-8")
    pretty.write_text(json.dumps(GOOD, indent=4, sort_keys=True), encoding="utf-8")
    result = run_gate(gate, a, pretty)
    if result.rc != 0:
        gate.log_fail("reformatted-but-equal JSON was reported as drift", result)
    gate.log_pass("formatting differences are not drift")


def test_a_real_divergence_is_caught(gate, tmp_path):
    a = tmp_path / "a.json"
    drift = tmp_path / "drift.json"
    a.write_text(json.dumps(GOOD), encoding="utf-8")
    doctored = json.loads(json.dumps(GOOD))
    doctored["regions"].append({"id": "planted", "label": "p", "domain": "p"})
    drift.write_text(json.dumps(doctored), encoding="utf-8")
    result = run_gate(gate, a, drift)
    if result.rc == 0:
        gate.log_fail("a divergent baked list PASSED -- a stale copy would ship to every install")
    gate.log_pass("a real divergence is caught")


def test_two_empty_files_do_not_compare_equal(gate, tmp_path):
    e1 = tmp_path / "e1.json"
    e2 = tmp_path / "e2.json"
    e1.write_text("", encoding="utf-8")
    e2.write_text("", encoding="utf-8")
    result = run_gate(gate, e1, e2)
    if result.rc == 0:
        gate.log_fail(
            "two EMPTY files passed; equality over nothing is the vacuous pass this guards"
        )
    gate.log_pass("empty files are refused, not compared")


def test_invalid_json_fails_rather_than_passing(gate, tmp_path):
    a = tmp_path / "a.json"
    bad = tmp_path / "bad.json"
    a.write_text(json.dumps(GOOD), encoding="utf-8")
    bad.write_text("not json at all", encoding="utf-8")
    result = run_gate(gate, a, bad)
    if result.rc == 0:
        gate.log_fail("invalid JSON passed; a comparison that could not parse is not a match")
    gate.log_pass("invalid JSON is refused")


def test_missing_file_is_not_a_clean_tree(gate, tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps(GOOD), encoding="utf-8")
    result = run_gate(gate, a, tmp_path / "does-not-exist.json")
    if result.rc == 0:
        gate.log_fail("a missing baked list passed; 'nothing to compare' must never be a pass")
    gate.log_pass("a missing file is refused")


def test_the_live_tree_agrees(gate):
    # Over-fire guard, and the reason the gate is worth running at all: if these two ever drift, CI says so instead of shipping a stale list.
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    result = harness.run(["python3", str(SUT)], cwd=paths.repo_root())
    if result.rc != 0:
        gate.log_fail("the live tree's two region lists have diverged; reconcile them", result)
    gate.log_pass("the live tree's two lists agree")
