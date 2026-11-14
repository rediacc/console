"""`scripts/gates/check-redirect-integrity.ts` check 2b refuses a redirect rule that rewrites a live page, because the www Worker reads the table before it serves ASSETS (2026-11-12: a curated 410 for `/acceptable-use-policy` stood in front of the page the new Terms of Service cite).

`REDIRECT_INTEGRITY_FIXTURE_ROOT` points the gate at a fixture tree holding `workers/www/src/redirects.json` and `packages/www/dist/route-manifest.json`.

Proved, control first: a table with no rule on the live page passes; an exact 410 on it fails, and so does a pattern that rewrites it; an exact self-map protects it from the same pattern.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

VALIDATOR = paths.from_root("scripts", "gates", "check-redirect-integrity.ts")
LIVE = "/new-policy"
RATIONALE = "a fixture rule for the shadow check"
PATTERN = {
    "from": "^/[a-z]+-policy$",
    "to": "/privacy-policy",
    "status": 301,
    "rationale": RATIONALE,
}


def tree(tmp: pathlib.Path, exact: dict, patterns: list) -> pathlib.Path:
    root = tmp / "tree"
    table = root / "workers/www/src/redirects.json"
    manifest = root / "packages/www/dist/route-manifest.json"
    table.parent.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    table.write_text(
        json.dumps({"exact": exact, "patterns": patterns, "allowed_non_manifest_targets": []}),
        encoding="utf-8",
    )
    manifest.write_text(json.dumps([{"path": LIVE}, {"path": "/privacy-policy"}]), encoding="utf-8")
    return root


def run_gate(gate, root: pathlib.Path):
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(VALIDATOR))
    npx = harness.require_tool("npx", "install node; the subject is a TypeScript program")
    return harness.run(
        [npx, "tsx", str(VALIDATOR)],
        cwd=paths.repo_root(),
        env={"REDIRECT_INTEGRITY_FIXTURE_ROOT": str(root)},
    )


def test_control_a_table_with_no_rule_on_the_page_passes(gate, tmp_path):
    result = run_gate(gate, tree(tmp_path, {}, []))
    gate.assert_exit(0, result, "no rule names the live page")
    gate.assert_contains(result.out, "no rule shadows a live page", "check 2b ran")
    gate.log_pass("the control passes")


def test_an_exact_410_on_a_live_page_fails(gate, tmp_path):
    gone = {LIVE: {"to": None, "status": 410, "rationale": RATIONALE}}
    result = run_gate(gate, tree(tmp_path, gone, []))
    gate.assert_exit(1, result, "an exact 410 on a live page fails")
    gate.assert_contains(
        result.err, "%s  ->  (gone) 410  (exact; source is a live page)" % LIVE, "named"
    )
    gate.log_pass("an exact rule shadowing a live page fails")


def test_a_pattern_rewriting_a_live_page_fails_and_a_self_map_protects_it(gate, tmp_path):
    red = run_gate(gate, tree(tmp_path / "red", {}, [PATTERN]))
    gate.assert_exit(1, red, "a pattern rewriting a live page fails")
    gate.assert_contains(red.err, "%s  ->  /privacy-policy 301  (pattern" % LIVE, "named")
    self_map = {LIVE: {"to": LIVE, "status": 301, "rationale": RATIONALE}}
    green = run_gate(gate, tree(tmp_path / "green", self_map, [PATTERN]))
    gate.assert_exit(0, green, "an exact self-map wins over the pattern")
    gate.log_pass("a pattern shadow fails; an exact self-map protects the page")
