"""Port of `.ci/scripts/test/gates/test-overrides-reasons.sh`, retired in W7 P5.

Integration test for `scripts/gates/check-overrides-reasons.ts`: the JSON-safe sibling of the BLOCKER convention. JSON allows no inline comments, so every entry in
package.json's `overrides` carries its rationale in a parallel `_overridesReasons`
object keyed identically, and the validator refuses a missing reason, a low-effort one, and a reason whose override has since been removed.

HOW THE FIXTURE CASES REACH THE SUBJECT, and why it is a copy rather than a flag. The validator resolves package.json from ITS OWN location (`__dirname/..`), with no override. There is therefore no seam to point it at a fixture, so the twin copies the whole `scripts/` tree beside a synthetic package.json in a temp directory and runs it there. This port does the same thing for the
same reason; re-implementing the validator in Python to avoid the copy would be testing a copy.

THE FIRST CASE HAS NO FIXTURE AT ALL. `test_accepts_real_package_json` drives the validator against the repo's own package.json, which is what makes this a real-tree reader rather than a self-contained unit test.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Every case reads the working tree: three of them `cp -r` the entire `scripts/` directory, and the fourth reads
package.json in place. A battery step rewriting either mid-copy is a `cp: cannot
stat` flake that would be blamed on this port. `REAL_TREE_TWIN = True` is what buys
the serialisation, and it is honoured only because this module declares no `XDIST_GROUP` of its own.
"""

import json
import os
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# Copies `scripts/` and reads `package.json` off the real working tree.
REAL_TREE_TWIN = True

VALIDATOR_REL = "scripts/gates/check-overrides-reasons.ts"
VALIDATOR = paths.from_root(*VALIDATOR_REL.split("/"))
SCRIPTS_DIR = paths.from_root("scripts")


def npx(gate) -> str:
    """`npx`, probed by name with the remedy in the message.

    A missing node toolchain would otherwise arrive as `FileNotFoundError: 'npx'`
    from inside a helper, which reads as harness breakage rather than as a statement
    about the machine. `check:ci-pytest` runs in `quality-security`, which DOES set the workspace up, so an absent npx here is a real finding about the lane.
    """
    if not VALIDATOR.is_file():
        gate.log_fail("subject under test is missing: %s" % VALIDATOR_REL)
    return harness.require_tool(
        "npx", "install node and run `npm install` at the repo root; the subject is a tsx script"
    )


def run_validator_on_real_tree(gate) -> harness.RunResult:
    return harness.run([npx(gate), "tsx", VALIDATOR_REL], cwd=paths.repo_root())


def run_validator_with_pkg(gate, pkg_content: str) -> harness.RunResult:
    """`run_validator_with_pkg`: a synthetic package.json, the REAL validator.

    The validator reads package.json relative to its own `__dirname/..`, so `scripts/` has to sit beside the fixture manifest. The twin merges the streams (`2>&1`) and asserts on the merged text, so callers here read `.combined`.
    """
    tool = npx(gate)
    with harness.temp_dir() as temp:
        (temp / "package.json").write_text(pkg_content + "\n", encoding="utf-8")
        shutil.copytree(SCRIPTS_DIR, temp / "scripts")
        # REDIACC_CI_ROOT POINTS THE COPIED VALIDATOR AT THE REAL PACKAGE. Since 2026-09-09 `scripts/lib/blocker-validator.ts` is a client of `rediacc_ci.core.allowlist` and resolves that package two directories above its own file, which in this fixture is the temp dir. It refused loudly, which is the designed behaviour and exactly wrong here: the low-effort case then asserted on a
        # "canonical validator could not be run" traceback instead of on the verdict it exists to check. The same override, for the same reason, as `test-ci-job-aggregation.sh` uses on its mirrored `.ci` layout.
        return harness.run(
            [tool, "tsx", "scripts/gates/check-overrides-reasons.ts"],
            cwd=temp,
            env={"REDIACC_CI_ROOT": str(paths.repo_root())},
        )


def test_accepts_real_package_json(gate):
    """The actual repo package.json should pass."""
    result = run_validator_on_real_tree(gate)
    if result.rc != 0:
        gate.log_fail(
            "real package.json should pass overrides-reasons validation (rc=%d)\n"
            "--- stdout ---\n%s\n--- stderr ---\n%s" % (result.rc, result.out, result.err)
        )
    gate.log_pass("real package.json passes validation")


def test_rejects_missing_reason(gate):
    result = run_validator_with_pkg(gate, '{"overrides":{"somepkg":"^1.0.0"}}')
    gate.assert_exit(1, result, "missing reason should fail")
    gate.assert_contains(
        result.combined, "has no matching _overridesReasons", "error message names the problem"
    )
    gate.log_pass("missing reason is rejected")


def test_rejects_low_effort_reason(gate):
    result = run_validator_with_pkg(
        gate,
        '{"overrides":{"somepkg":"^1.0.0"},"_overridesReasons":{"somepkg":"tbd"}}',
    )
    gate.assert_exit(1, result, "tbd reason should fail")
    gate.assert_contains(
        result.combined, "low-effort placeholder", "error message identifies the issue"
    )
    gate.log_pass("low-effort reason is rejected")


def test_rejects_stale_reason(gate):
    result = run_validator_with_pkg(
        gate,
        '{"overrides":{},"_overridesReasons":'
        '{"ghost":"BLOCKER: this reason has no corresponding override in the tree"}}',
    )
    gate.assert_exit(1, result, "stale reason should fail")
    gate.assert_contains(result.combined, "stale reason", "error message names drift")
    gate.log_pass("stale (orphaned) reason is rejected")


def test_the_real_manifest_declares_overrides_to_check(gate):
    """ADDED BY THE PORT. `test_accepts_real_package_json` is the only case that touches the shipping manifest, and it would pass just as green against a
    package.json with NO overrides at all -- the validator prints
    `All 0 ... overrides have valid BLOCKER reasons` and exits 0. That green says nothing, so this pins the corpus: the count the validator reports must be non-zero AND must equal the number of top-level override keys in the file.

    Not a hand-typed floor. Both numbers are read at runtime, so the case follows the manifest instead of dating it.
    """
    manifest = paths.from_root("package.json")
    if not manifest.is_file():
        gate.log_fail("package.json is missing at the repo root; nothing to validate")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    overrides = data.get("overrides") or {}
    if not overrides:
        gate.log_fail(
            "package.json declares no `overrides`, so the seam-free case above proved "
            "only that a validator can count to zero. Either the manifest lost its "
            "overrides or this port is reading the wrong file."
        )
    result = run_validator_on_real_tree(gate)
    gate.assert_exit(0, result, "the real manifest must still validate")
    gate.assert_contains(
        result.combined,
        "All %d package.json overrides" % len(overrides),
        "the validator counted the same overrides this test can see in the manifest",
    )
    gate.log_pass(
        "the shipping manifest carries %d override(s), and the validator judged that many"
        % len(overrides)
    )
    gate.log_info(
        "shape: %s"
        % json.dumps(
            {
                "overrides": len(overrides),
                "reasons": len(data.get("_overridesReasons") or {}),
                "validator": os.fspath(paths.relative_to_root(VALIDATOR)),
            }
        )
    )
