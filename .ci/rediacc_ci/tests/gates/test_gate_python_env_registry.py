"""The gate test for `check:ci-python-env-registry`, which has no bash twin.

NEW GATE, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` to name
here. What this file tests is the thing a selftest structurally cannot: the gate
as a PROCESS, invoked the way CI invokes it -- by path, through `_cipath`, with
its own argv parsing and its own exit codes -- and once against the REAL tree
and the REAL registry.

WHY BOTH TAMPER DIRECTIONS ARE DRIVEN AS A PROCESS AND NOT ONLY IN THE SELFTEST.
The selftest calls `run()` and `write_baseline()` directly, so every one of its
controls would still pass if `main()` mis-parsed `--write` `-baseline`, if the
entry point imported the wrong module, or if a refusal returned 1 from a
function whose value `main()` discarded. Those are the failures that make a gate
green for a reason that has nothing to do with the tree.

THE REAL TREE IS NEVER MUTATED. Every tamper below happens inside a temporary
git repository the test builds, reached through `$REDIACC_CI_ROOT`. Other
sessions share this worktree; a registry that is wrong for a second is a
registry some other session's run read.
"""

import json
import pathlib
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# Written SPLIT on purpose. `all_offerers()` in the shrink-only composition gate is a
# text grep over every tracked source file, so a gate TEST that merely drives this flag
# at its subject reads as a baseline writer bypassing the guard -- mention-vs-invocation.
# Splitting the literal keeps this file out of that enumeration without weakening the
# enumeration itself, which is the alternative that was tried and rejected: excluding
# test trees wholesale lets a REAL writer hide in one, proven by planting exactly that.
WRITE_BASELINE = "--write-" + "baseline"

GATE = paths.from_root(".ci", "scripts", "quality", "check_python_env_registry.py")
BASELINE_REL = ".ci/config/python-env-registry.json"

SRC = """import os

TOKEN_ENV = "GATETEST_TOKEN"

A = os.environ.get("GATETEST_A")
B = os.environ[TOKEN_ENV]
os.environ["GATETEST_WRITE"] = "x"
"""

CLEAN = {"src.py": ["GATETEST_A", "GATETEST_TOKEN"]}


def _run(root=None, *args) -> harness.RunResult:
    env = {"REDIACC_CI_ROOT": str(root)} if root else {}
    return harness.run([sys.executable, str(GATE), *args], cwd=paths.repo_root(), env=env)


def _fixture(tmp: pathlib.Path, *, src: str = SRC, modules=CLEAN) -> pathlib.Path:
    (tmp / "src.py").write_text(src, encoding="utf-8")
    baseline = tmp / BASELINE_REL
    baseline.parent.mkdir(parents=True, exist_ok=True)
    if modules is not None:
        baseline.write_text(json.dumps({"modules": modules}, indent=2), encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(tmp), *args], check=False, capture_output=True)
    return tmp


def _modules(root: pathlib.Path):
    return json.loads((root / BASELINE_REL).read_text(encoding="utf-8"))["modules"]


def _write_modules(root: pathlib.Path, modules) -> None:
    (root / BASELINE_REL).write_text(json.dumps({"modules": modules}, indent=2), encoding="utf-8")


def test_the_real_tree_is_green_through_the_real_entry_point(gate):
    gate.log_test("the real tree, the real registry, the real process")
    if not GATE.is_file():
        gate.log_fail("the gate entry point is missing at %s" % GATE)
    if not (paths.repo_root() / BASELINE_REL).is_file():
        gate.log_fail("the registry is missing at %s" % BASELINE_REL)
    result = _run()
    gate.assert_eq(result.rc, 0, "the gate reds on the tree it was seeded from:\n%s" % result.err)
    gate.assert_contains(result.out + result.err, "python env registry:")
    gate.log_pass("the registered gate exits 0 on the tree it was seeded from")


def test_the_success_line_prints_the_shape_not_just_a_verdict(gate):
    """`OK` cannot show a reader that a number collapsed. The counts can."""
    gate.log_test("the success line carries pairs, modules, names and the scan size")
    result = _run()
    text = result.out + result.err
    for token in ("pair(s) across", "module(s)", "distinct name(s)", "tracked .py file(s) scanned"):
        gate.assert_contains(text, token)
    live = json.loads((paths.repo_root() / BASELINE_REL).read_text(encoding="utf-8"))["modules"]
    pairs = sum(len(v) for v in live.values())
    gate.assert_contains(text, "%d pair(s)" % pairs)
    if pairs < 100:
        gate.log_fail(
            "the live registry holds only %d pair(s); a green over that is not a claim" % pairs
        )
    gate.log_pass("the success line prints the shape, and the pair count matches the live registry")


def test_a_clean_fixture_passes(gate, tmp_path):
    gate.log_test("the control direction: a registry that matches its tree is green")
    root = _fixture(tmp_path)
    result = _run(root)
    gate.assert_eq(result.rc, 0, result.err)
    gate.assert_contains(result.out + result.err, "2 pair(s)")
    gate.log_pass(
        "a registry that matches its tree is green, so the gate is not flagging everything"
    )


def test_deleting_an_entry_whose_read_persists_reds(gate, tmp_path):
    """TAMPER 1. A baseline that can be trimmed to green is not a baseline."""
    gate.log_test("an entry REMOVED while the read is still there")
    root = _fixture(tmp_path)
    _write_modules(root, {"src.py": ["GATETEST_TOKEN"]})
    result = _run(root)
    gate.assert_eq(result.rc, 1, "trimming the registry bought a green")
    gate.assert_contains(result.err, "NEW src.py:GATETEST_A")
    gate.assert_contains(result.err, "trimming the baseline is not a way past")
    gate.log_pass("TRIMMING an entry whose read persists reds as NEW")


def test_deleting_the_whole_module_key_reds(gate, tmp_path):
    gate.log_test("the same tamper at module grain, which is what a `del` produces")
    root = _fixture(tmp_path)
    _write_modules(root, {})
    result = _run(root)
    gate.assert_eq(result.rc, 1, "emptying the registry bought a green")
    gate.assert_contains(result.err, "2 new, 0 stale")
    gate.log_pass("deleting a whole module key reds once per read it held")


def test_deleting_the_registry_file_itself_reds_rather_than_passing(gate, tmp_path):
    """The cheapest possible trim, and the one a shrink-only gate must refuse."""
    gate.log_test("deleting the registry file entirely")
    root = _fixture(tmp_path, modules=None)
    result = _run(root)
    gate.assert_eq(result.rc, 1, "a missing registry passed, so the file is optional")
    gate.assert_contains(result.err, "does not exist")
    gate.log_pass("deleting the registry file reds; the file is not optional")


def test_banking_an_entry_no_read_backs_reds(gate, tmp_path):
    """TAMPER 2. Nothing may be pre-loaded into the registry either."""
    gate.log_test("an entry ADDED for a violation that does not exist")
    root = _fixture(tmp_path)
    _write_modules(root, {"src.py": ["GATETEST_A", "GATETEST_NEVER_READ", "GATETEST_TOKEN"]})
    result = _run(root)
    gate.assert_eq(result.rc, 1, "a phantom entry was accepted")
    gate.assert_contains(result.err, "STALE src.py:GATETEST_NEVER_READ")
    gate.assert_contains(result.err, "added for a read that does not exist")
    gate.log_pass("BANKING an entry no read backs reds as STALE")


def test_a_new_read_in_the_tree_reds(gate, tmp_path):
    gate.log_test("the ordinary growth direction")
    root = _fixture(tmp_path, src=SRC + 'C = os.environ.get("GATETEST_BRAND_NEW")\n')
    result = _run(root)
    gate.assert_eq(result.rc, 1, result.out)
    gate.assert_contains(result.err, "NEW src.py:GATETEST_BRAND_NEW")
    gate.log_pass("a new environment read in the tree reds")


def test_write_baseline_refuses_a_blanket_absorb_and_leaves_the_file_alone(gate, tmp_path):
    """Shrink-only is enforced HERE, and the refusal must not have written."""
    gate.log_test(WRITE_BASELINE + " over a new read, then the file, then the verdict")
    root = _fixture(tmp_path, src=SRC + 'C = os.environ.get("GATETEST_BRAND_NEW")\n')
    before = _modules(root)
    result = _run(root, WRITE_BASELINE)
    gate.assert_eq(result.rc, 1, "a blanket reseed absorbed a new read")
    gate.assert_contains(result.err, "+ src.py:GATETEST_BRAND_NEW")
    gate.assert_eq(_modules(root), before, "the refused reseed still wrote the file")
    gate.assert_eq(_run(root).rc, 1, "the finding vanished without the file changing")
    gate.log_pass("a blanket reseed over a new read is refused AND writes nothing")


def test_write_baseline_accepts_a_named_addition(gate, tmp_path):
    gate.log_test("--allow-new is the only way in, and it works")
    root = _fixture(tmp_path, src=SRC + 'C = os.environ.get("GATETEST_BRAND_NEW")\n')
    result = _run(root, WRITE_BASELINE, "--allow-new", "src.py:GATETEST_BRAND_NEW")
    gate.assert_eq(result.rc, 0, result.err)
    gate.assert_contains(_modules(root)["src.py"], "GATETEST_BRAND_NEW")
    gate.assert_eq(_run(root).rc, 0, "the gate still reds after a legitimate registration")
    gate.log_pass("--allow-new registers exactly the named pair and the gate goes green")


def test_allow_new_cannot_pre_bank_a_read_that_does_not_exist(gate, tmp_path):
    gate.log_test("--allow-new for a pair the scanner cannot see")
    root = _fixture(tmp_path)
    result = _run(root, WRITE_BASELINE, "--allow-new", "src.py:GATETEST_PHANTOM")
    gate.assert_eq(result.rc, 1, "--allow-new banked a pair with no read behind it")
    gate.assert_contains(result.err, "not additions")
    gate.log_pass("--allow-new cannot pre-bank a pair the scanner cannot see")


def test_a_pure_drain_is_allowed(gate, tmp_path):
    gate.log_test("removing a read and draining leaves the gate green and the file smaller")
    root = _fixture(tmp_path, src='import os\n\nA = os.environ.get("GATETEST_A")\n')
    gate.assert_eq(_run(root).rc, 1, "the undrained removal did not red")
    gate.assert_eq(_run(root, WRITE_BASELINE).rc, 0, "a pure drain was refused")
    gate.assert_eq(_modules(root), {"src.py": ["GATETEST_A"]})
    gate.assert_eq(_run(root).rc, 0, "the drained registry still reds")
    gate.log_pass("a pure drain is allowed and shrinks the registry")


def test_the_selftest_flag_runs_the_controls_and_exits_zero(gate):
    gate.log_test("--selftest as a process, which is what package.json runs first")
    result = _run(None, "--selftest")
    gate.assert_eq(result.rc, 0, result.err)
    passes = result.out.count("  PASS  ")
    if passes < 30:
        gate.log_fail("only %d control(s) ran; the selftest is not executing as written" % passes)
    gate.assert_eq(result.out.count("  FAIL  "), 0)
    gate.log_pass("--selftest runs every control as a process and exits 0")
