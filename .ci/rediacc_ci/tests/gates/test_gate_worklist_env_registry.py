"""The gate test for `check:ci-worklist-env-registry`, which has no bash twin.

NEW GATE, NOT A PORT. The selftest proves the predicate against a four-name fixture repository; nothing in it says the registry matches the 133-name tree. These cases drive the entry point as a PROCESS against the real corpus, and plant into the real files.

TWO KINDS OF PLANT, and the pairing is the point. Planting into the REGISTRY exercises the comparison against a real scan; planting into a real SOURCE file exercises the scanner against a real registry. A gate can pass one and fail the other, and this gate did neither until both were driven.

THE SOURCE PLANT TARGET is `.claude/hooks/stop/test-reggate-ledger.py`, a test file reached only by its own harness and never by a live hook chain, and the bytes are never written at all: the seam below substitutes CONTENT from a tmp copy. `git diff --quiet` is asked afterwards, so a different instrument confirms it.

IT USED TO BE `worklist-cases/21-cadence.sh`, which was chosen for the same property and deleted when the bash Stop-hook suite was ported to pytest. The plant moved with it rather than being dropped, because the direction it covers, the SCANNER against a real registry, is the one the registry plant above cannot reach.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_worklist_env_registry.py")
REGISTRY = paths.from_root(".ci", "policy", "worklist-env-registry.json")
SOURCE_PLANT = paths.from_root(".claude", "hooks", "stop", "test-reggate-ledger.py")
SOURCE_PLANT_REL = str(SOURCE_PLANT.relative_to(paths.repo_root()))


def _run(*args, env=None) -> harness.RunResult:
    return harness.run([sys.executable, str(GATE), *args], cwd=paths.repo_root(), env=env)


def _rel(path) -> str:
    return str(path.relative_to(paths.repo_root()))


def _unmodified(gate, path) -> None:
    proc = subprocess.run(
        ["git", "diff", "--quiet", "--", _rel(path)],
        cwd=paths.repo_root(),
        capture_output=True,
        check=False,
    )
    gate.assert_exit_code(0, proc.returncode, "%s is unmodified against the index" % _rel(path))


def test_the_real_tree_is_fully_registered(gate):
    gate.log_test("133 names, the real corpus, through the real entry point")
    for subject in (GATE, REGISTRY, SOURCE_PLANT):
        if not subject.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err)
    gate.assert_contains(result.combined, "all registered and all read", "set equality both ways")
    gate.assert_contains(result.combined, "read site(s)", "prints the site count")
    gate.assert_contains(result.combined, "kinds ", "and the per-kind breakdown")
    # The exclusions are printed on SUCCESS. An exclusion only visible when something is already broken is an exclusion nobody drains.
    gate.assert_contains(result.combined, "excluded by declaration: agent/", "agent/ is named")
    gate.assert_contains(result.combined, "excluded by declaration: docs/", "docs/ is named")
    gate.log_pass("the registry and the tree are one set, and the shape is printed")


def test_the_registry_size_matches_the_shape_line(gate):
    gate.log_test("the number the gate prints is the number in the file")
    registered = len(json.loads(REGISTRY.read_text(encoding="utf-8"))["names"])
    gate.assert_eq(registered >= 100, True, "%d names registered" % registered)
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean run")
    gate.assert_contains(
        result.combined, "%d name(s)" % registered, "and the gate reports the same count"
    )
    gate.log_pass("%d registered names, and the gate says %d" % (registered, registered))


def test_dropping_a_registered_name_reds(gate):
    gate.log_test("PLANT: remove a name from a REAL registry copy while the code still reads it")
    # WORKLIST_REGISTRY_OVERRIDE_FILE (registered, kind=path) points run() at a
    # tmp copy instead of the tracked file. The comparison is still against the REAL corpus scan (scan_corpus reads the real tree unchanged) -- only the registry side is a copy, so a hard kill here corrupts a tmp file, never `.ci/policy/worklist-env-registry.json`. That file used to be written and restored in a `finally`, and a kill landing in that window deleted WORKLIST_FOCUS
    # from it for real, twice in one session.
    original = REGISTRY.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        mutated = pathlib.Path(td) / "worklist-env-registry-mutated.json"
        obj = json.loads(original.decode("utf-8"))
        del obj["names"]["WORKLIST_FOCUS"]
        mutated.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        result = _run(env={"WORKLIST_REGISTRY_OVERRIDE_FILE": str(mutated)})
    gate.assert_exit_code(1, result.rc, "an unregistered read must red")
    gate.assert_contains(result.combined, "UNREGISTERED WORKLIST_FOCUS", "names it")
    gate.assert_contains(result.combined, "reads as UNSET", "and says which way it fails")
    gate.assert_eq(REGISTRY.read_bytes(), original, "never touched on disk, not merely restored")
    gate.log_pass("a read the registry does not know about reds, with no real file at risk")


def test_a_registered_name_nobody_reads_reds(gate):
    gate.log_test("PLANT: the OTHER direction, a phantom entry in a REAL registry copy")
    original = REGISTRY.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        mutated = pathlib.Path(td) / "worklist-env-registry-mutated.json"
        obj = json.loads(original.decode("utf-8"))
        obj["names"]["WORKLIST_ZZZ_PHANTOM"] = {"kind": "tuning", "defaults": ["'1'"]}
        mutated.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        result = _run(env={"WORKLIST_REGISTRY_OVERRIDE_FILE": str(mutated)})
    gate.assert_exit_code(1, result.rc, "a dead entry must red")
    gate.assert_contains(result.combined, "DEAD WORKLIST_ZZZ_PHANTOM", "names it")
    gate.assert_eq(REGISTRY.read_bytes(), original, "never touched on disk, not merely restored")
    gate.log_pass("the direction that rots is the one this case covers, with no real file at risk")


def test_a_typo_in_a_real_source_file_reds(gate):
    gate.log_test("PLANT: a misspelled expansion, scanned in place of a real tracked file")
    # WORKLIST_SOURCE_OVERRIDE_FILE (registered, kind=path) substitutes CONTENT
    # for one real corpus entry without ever writing to the tracked file: the
    # real `git ls-files` list, the real file count and the real everything-else are unchanged, only SOURCE_PLANT's bytes come from a tmp copy instead of disk. A hard kill mid-test now leaves a tmp file orphaned, never the tracked one -- the same class of hazard the WORKLIST_FOCUS registry corruption was (that half fixed by the registry-path seam above), one file over.
    original = SOURCE_PLANT.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        mutated = pathlib.Path(td) / "reggate-ledger-mutated.py"
        # THE PLANT IS PYTHON NOW, because the target is. The scanner counts a
        # named environment lookup, not a shell expansion, so a bash `${...}`
        # appended to a .py file would be invisible and the case would go green
        # having planted nothing.
        mutated.write_bytes(
            original
            + b'\n# gate probe\nimport os\n_probe = os.environ.get("WORKLIST_CADENEC", "on")\n'
        )
        result = _run(env={"WORKLIST_SOURCE_OVERRIDE_FILE": "%s:%s" % (SOURCE_PLANT_REL, mutated)})
    gate.assert_exit_code(1, result.rc, "a typo'd name must red")
    gate.assert_contains(result.combined, "WORKLIST_CADENEC", "names the misspelling")
    gate.assert_contains(result.combined, "test-reggate-ledger.py", "and the file it is in")
    gate.assert_eq(
        SOURCE_PLANT.read_bytes(), original, "never touched on disk, not merely restored"
    )
    _unmodified(gate, SOURCE_PLANT)
    after = _run()
    gate.assert_exit_code(0, after.rc, "green with no override set, since nothing was ever mutated")
    gate.log_pass("the scanner sees a real typo without a real file ever being at risk")


def test_prose_under_agent_is_not_a_read(gate):
    gate.log_test("ANTI-SILENCER: a name that exists only in agent/ prose must stay invisible")
    # WORKLIST_EMAIL is the real case: one mention, in a comment, describing a name that no longer exists. If the exclusion or the scanner ever admitted prose, it would appear as an unregistered read.
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean run")
    gate.assert_not_contains(result.combined, "WORKLIST_EMAIL", "the prose-only name is absent")
    registered = json.loads(REGISTRY.read_text(encoding="utf-8"))["names"]
    gate.assert_eq("WORKLIST_EMAIL" in registered, False, "and it is not registered either")
    gate.log_pass(
        "the grep answer (134) and the read answer (133) differ, and the gate uses the read answer"
    )


def test_the_selftest_covers_both_directions(gate):
    gate.log_test("--selftest runs, with plants, anti-silencers and refusals")
    result = _run("--selftest")
    gate.assert_exit_code(0, result.rc, "selftest (stderr: %s)" % result.err)
    passes = [ln for ln in result.combined.splitlines() if "PASS " in ln]
    gate.assert_eq(len(passes) >= 18, True, "%d control(s) ran, floor 18" % len(passes))
    plants = [ln for ln in passes if "PLANT:" in ln]
    anti = [ln for ln in passes if "ANTI-SILENCER:" in ln]
    vacuity = [ln for ln in passes if "VACUITY:" in ln]
    gate.assert_eq(len(plants) >= 8, True, "%d plants" % len(plants))
    gate.assert_eq(len(anti) >= 3, True, "%d anti-silencers" % len(anti))
    gate.assert_eq(len(vacuity) >= 5, True, "%d refusals" % len(vacuity))
    gate.log_pass(
        "%d plants, %d anti-silencers, %d refusals" % (len(plants), len(anti), len(vacuity))
    )
