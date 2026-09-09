"""The gate test for `check:ci-hook-exec-baseline`, which has no bash twin.

NEW GATE, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` to name
here and nothing to compare against. What it tests instead is the thing a
selftest structurally cannot: the gate as a PROCESS, invoked the way CI invokes
it, against the REAL `.claude/settings.json` and the REAL pinned baseline.

WHY THAT DISTINCTION IS NOT PEDANTRY, and it is this gate's own history. Every
one of its thirteen selftest controls passed while `_load_counter()` resolved the
counter against the tree being JUDGED rather than against the instrument. The
controls could not see it because they all resolve the counter once, before any
fixture root exists. The first run against a scratch copy of the real tree died
with `ModuleNotFoundError`. So the cases below drive the entry point by path,
with `$REDIACC_CI_ROOT` pointed at copies of the real files, and plant into
those copies.

THE LIVE `.claude/settings.json` IS NEVER MUTATED. It is copied into a temp root
first. Other sessions share this worktree and a hook wiring that is wrong for
even a second is a hook wiring some other session's Bash call ran under.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_hook_exec_baseline.py")
COUNTER = paths.from_root(".claude", "rediacc_hooks", "execcount.py")
SETTINGS = paths.from_root(".claude", "settings.json")
BASELINE = paths.from_root(".ci", "policy", "hook-exec-baseline.json")


def _run(root=None) -> harness.RunResult:
    env = {"REDIACC_CI_ROOT": str(root)} if root else {}
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def _mirror(tmp: pathlib.Path) -> pathlib.Path:
    """A scratch root holding copies of the two REAL files the gate reads."""
    (tmp / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
    shutil.copy(SETTINGS, tmp / ".claude" / "settings.json")
    shutil.copy(BASELINE, tmp / ".ci" / "policy" / "hook-exec-baseline.json")
    return tmp


def _edit_settings(root: pathlib.Path, fn) -> None:
    p = root / ".claude" / "settings.json"
    obj = json.loads(p.read_text(encoding="utf-8"))
    fn(obj)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def test_the_gate_is_green_on_the_real_tree(gate):
    gate.log_test("the real tree, through the real entry point")
    for subject in (GATE, COUNTER, BASELINE):
        if not subject.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err)
    # The shape line, not just the verdict. A gate whose corpus collapsed to
    # nothing would still print a tick; the numbers are what says it did not.
    gate.assert_contains(result.combined, "harness command entries", "prints its shape")
    gate.assert_contains(result.combined, "probe tool(s)", "and its probe-set size")
    gate.log_pass("the gate passes on the real tree and says how much it looked at")


def test_a_removed_hook_command_reds_and_says_shrank(gate):
    gate.log_test("PLANT: delete one REAL hook command from a copy of settings.json")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")

        def drop(obj):
            for group in obj["hooks"]["PostToolUse"]:
                group["hooks"] = [h for h in group["hooks"] if "cancel-old-ci" not in h["command"]]

        _edit_settings(root, drop)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a cheaper wiring is still a finding")
        gate.assert_contains(result.combined, "entryCount SHRANK", "names the direction")
        gate.assert_contains(
            result.combined, "repin it with 29", "and hands over the value to paste"
        )
    gate.log_pass("a SHRINK reds with the repin value, which is what keeps the pin honest")


def test_an_added_hook_command_reds_and_says_grew(gate):
    gate.log_test("PLANT: add one hook command to a copy of settings.json")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)

        def add(obj):
            obj["hooks"]["PreToolUse"][0]["hooks"].append({"command": "bash planted.sh"})

        _edit_settings(root, add)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a more expensive wiring is a finding")
        gate.assert_contains(result.combined, "entryCount GREW", "names the direction")
        gate.assert_contains(result.combined, "Bash/fullmatch/total GREW", "and the tool row")
    gate.log_pass("growth reds, per tool as well as in the total")


def test_a_matcher_no_probe_selects_reds(gate):
    gate.log_test("PLANT: a matcher the probe table does not cover")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)

        def add(obj):
            obj["hooks"]["PreToolUse"].append(
                {"matcher": "Nonesuch", "hooks": [{"command": "bash n.sh"}]}
            )

        _edit_settings(root, add)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an uncounted matcher is a finding")
        gate.assert_contains(result.combined, "selected by no probe tool", "says why")
    gate.log_pass("a matcher whose cost no row carries cannot be added quietly")


def test_an_empty_wiring_is_refused_not_passed(gate):
    gate.log_test("VACUITY: settings.json with no hooks at all")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        (root / ".claude" / "settings.json").write_text('{"hooks": {}}\n', encoding="utf-8")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "zero inputs is a refusal, never a pass")
        gate.assert_contains(result.combined, "ZERO hook commands", "and says so in words")
    gate.log_pass("a wiring the counter cannot see is refused rather than counted as zero")


def test_the_counter_runs_standalone_and_agrees_with_the_pin(gate):
    gate.log_test("the counter is runnable by hand and its JSON matches the pin")
    result = harness.run([sys.executable, str(COUNTER), "--json"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "execcount.py --json (stderr: %s)" % result.err)
    live = json.loads(result.out)
    pinned = json.loads(BASELINE.read_text(encoding="utf-8"))["measured"]
    # The bare CLI derives its probe set from the matchers, so it measures FEWER
    # tools than the baseline declares. Comparing the intersection is the honest
    # claim: the two implementations agree wherever they overlap. Comparing the
    # whole dict would fail for a reason that is not a disagreement.
    shared = sorted(set(live["tools"]) & set(pinned["tools"]))
    gate.assert_eq(len(shared) >= 4, True, "the overlap is non-trivial (%d tools)" % len(shared))
    for tool in shared:
        gate.assert_eq(live["tools"][tool], pinned["tools"][tool], "%s agrees with the pin" % tool)
    gate.assert_eq(live["entryCount"], pinned["entryCount"], "entry count agrees")
    gate.assert_eq(live["events"], pinned["events"], "the lifecycle event table agrees")
    gate.log_pass("the standalone counter and the pinned baseline are the same measurement")


def test_the_selftest_runs_and_is_not_empty(gate):
    gate.log_test("--selftest runs its controls and prints them")
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "selftest (stderr: %s)" % result.err)
    passes = [ln for ln in result.combined.splitlines() if "PASS " in ln]
    # A floor, not a count: controls get added. Zero PASS lines with exit 0 is
    # the shape this whole file exists to refuse, and it is what a `--selftest`
    # that silently returned early would print.
    gate.assert_eq(len(passes) >= 12, True, "%d control(s) ran, floor 12" % len(passes))
    plants = [ln for ln in passes if "PLANT:" in ln]
    anti = [ln for ln in passes if "ANTI-SILENCER:" in ln]
    gate.assert_eq(len(plants) >= 5, True, "%d of them plant a defect" % len(plants))
    gate.assert_eq(len(anti) >= 2, True, "%d assert a NON-finding" % len(anti))
    gate.log_pass(
        "controls run in both directions: %d plants, %d anti-silencers" % (len(plants), len(anti))
    )
