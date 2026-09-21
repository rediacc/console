"""Port of `.ci/scripts/test/gates/test-resprofile.sh`, retired in W7 P5.

Drives `.ci/scripts/quality/check_resprofile.py` through its three states and a mutant.

WHY. The gate judges process-tree captures nobody has looked at by hand, so its own honesty is the whole question: pristine must WARN rather than pass silently, a seeded baseline must let a planted structural defect FIRE, and the dilation control must refuse a predicate that reads wall-clock. The mutant is the control on the control: strip the wall-only scaling out of `dilate()`
and the gate must go red on its own captures, or the control was decoration.

THE FIXTURE IS BUILT PER CASE, and that is the one structural change.

The twin builds ONE `mktemp -d` at file scope and walks its four cases through it in order: `test_seeded_then_enforces` writes the baseline that `test_seed_refuses_empty_corpus` then accumulates onto, and `test_mutant_wall_scaling_removed` edits the `wl_profile.py` copy that lives in the same fixture root. Straight-line bash can afford that. Independent pytest functions cannot,
because an ordering dependency turns "case 2 broke" into "case 3 failed", and under `-n 8 --dist loadgroup` it is not even ordering, it is a race. Each case here therefore builds its own root. Verified case by case that the verdicts are unchanged by the rebuild: the seeding case seeds and then enforces within its own root, and the empty-seed case seeds from the quiet corpus first
so that "accumulation is the only silent direction" is still being asserted about an accumulating baseline rather than a first one.

NO `xdist_group`: every case owns a private `mkdtemp` root, sets `RESPROFILE_ROOT` to it, and never writes inside the repository.

THE 81 FIXTURE CAPTURES ARE WRITTEN IN-PROCESS. The twin spawns one `python3` heredoc per file, which is 81 interpreter startups and most of its 15 seconds. The port writes the identical JSON records with `json.dumps`, so the corpus the gate reads is byte-equivalent and the cost is milliseconds. 80 quiet captures, NOT 24:
admission is a one-sided 95% Wilson bound on F/J <= 0.05, and at F=0 that needs J
of roughly 60 before the bound drops under the line. The twin's first draft seeded 24 and the gate CORRECTLY kept E6 report-only -- the fixture was under-powered, not
the gate. "J >= 20" is necessary, not sufficient.
"""

import json
import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_resprofile.py")
HOOKS = paths.hooks_stop_dir()

QUIET_CAPTURES = 80


def _zombie_capture() -> str:
    """A live parent with 4 zombies across consecutive samples: the E6 shape."""
    procs = [
        {
            "pid": 1,
            "ppid": 0,
            "comm": "bash",
            "state": "S",
            "wchan": "do_wait",
            "utime": 1,
            "stime": 0,
            "hwm_kb": 4000,
            "wfd": [],
            "depth": 0,
        },
        *(
            {
                "pid": 10 + i,
                "ppid": 1,
                "comm": "true",
                "state": "Z",
                "wchan": None,
                "utime": 0,
                "stime": 0,
                "hwm_kb": 0,
                "wfd": [],
                "depth": 1,
            }
            for i in range(4)
        ),
    ]
    lines = [
        json.dumps({"v": 1, "k": "S", "run": "r", "t_ms": t, "p": procs})
        for t in (0, 500, 1000, 1500)
    ]
    lines.append(
        json.dumps(
            {
                "v": 1,
                "k": "RUN",
                "run": "r",
                "root_pid": 1,
                "interval_ms": 500,
                "samples_n": 4,
                "expected_n": 4,
                "wall_ms": 2000,
                "unsampled": False,
            }
        )
    )
    return "\n".join(lines) + "\n"


def _quiet_capture() -> str:
    procs = [
        {
            "pid": 1,
            "ppid": 0,
            "comm": "bash",
            "state": "R",
            "wchan": None,
            "utime": 5,
            "stime": 0,
            "hwm_kb": 3000,
            "wfd": [],
            "depth": 0,
        }
    ]
    lines = [
        json.dumps({"v": 1, "k": "S", "run": "q", "t_ms": t, "p": procs}) for t in (0, 500, 1000)
    ]
    lines.append(
        json.dumps(
            {
                "v": 1,
                "k": "RUN",
                "run": "q",
                "root_pid": 1,
                "interval_ms": 500,
                "samples_n": 3,
                "expected_n": 3,
                "wall_ms": 1500,
                "unsampled": False,
            }
        )
    )
    return "\n".join(lines) + "\n"


def build_fixture(gate, work: pathlib.Path) -> pathlib.Path:
    """A fixture repo root. The gate resolves everything under `RESPROFILE_ROOT`, so the real baseline is never touched."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    root = work / "root"
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".ci" / "cache").mkdir(parents=True)
    (root / ".claude" / "hooks" / "stop").mkdir(parents=True)
    for name in ("wl_profile.py", "wl_ressample.py"):
        source = HOOKS / name
        if not source.is_file():
            gate.log_fail(
                "the fixture needs %s and it is not there" % paths.relative_to_root(source)
            )
        shutil.copy2(source, root / ".claude" / "hooks" / "stop" / name)

    caps = work / "caps"
    caps.mkdir()
    (caps / "zombies.jsonl").write_text(_zombie_capture(), encoding="utf-8")
    for i in range(1, QUIET_CAPTURES + 1):
        (caps / ("quiet%d.jsonl" % i)).write_text(_quiet_capture(), encoding="utf-8")

    quiet = work / "quiet"
    quiet.mkdir()
    for i in range(1, QUIET_CAPTURES + 1):
        shutil.copy2(caps / ("quiet%d.jsonl" % i), quiet / ("quiet%d.jsonl" % i))
    return root


def run_gate(root: pathlib.Path, *args: str) -> harness.RunResult:
    return harness.run(
        ["python3", str(GATE), *args],
        cwd=paths.repo_root(),
        env={"RESPROFILE_ROOT": str(root)},
    )


def test_pristine_warns_not_passes_silently(gate):
    gate.log_test("pristine: no baseline, so warn and name the finding without enforcing")
    with harness.temp_dir() as work:
        root = build_fixture(gate, work)
        result = run_gate(root, "--captures", str(work / "caps"))
        gate.assert_exit_code(0, result.rc, "pristine (no baseline) exits 0")
        gate.assert_contains(result.combined, "pristine", "and SAYS it is pristine")
        gate.assert_contains(result.combined, "E6", "and still names the planted finding as report")
        gate.log_pass("pristine warns and names findings without enforcing")


def test_seeded_then_enforces(gate):
    gate.log_test("a seeded baseline lets the planted E6 fire")
    with harness.temp_dir() as work:
        root = build_fixture(gate, work)
        # Seed from a QUIET corpus so the class becomes admissible with F=0.
        seeded = run_gate(root, "--seed", str(work / "quiet"))
        gate.assert_exit_code(0, seeded.rc, "seeding from a quiet corpus succeeds")
        baseline = root / ".ci" / "config" / "resprofile-baseline.json"
        if not baseline.is_file():
            gate.log_fail("no baseline written: %s" % baseline)
        gate.assertions += 1
        result = run_gate(root, "--captures", str(work / "caps"))
        gate.assert_exit_code(1, result.rc, "seeded: the planted E6 is ENFORCED")
        gate.assert_contains(result.combined, "E6", "and named")
        gate.log_pass("a seeded baseline lets a planted structural defect fire")


def test_seed_refuses_empty_corpus(gate):
    gate.log_test("accumulation is silent; an EMPTY seed is refused")
    with harness.temp_dir() as work:
        root = build_fixture(gate, work)
        # The twin reaches this case with a baseline already seeded by the case above, so seeding again is ACCUMULATION rather than a first seed. The rebuild would otherwise quietly turn this into a different assertion.
        first = run_gate(root, "--seed", str(work / "quiet"))
        gate.assert_exit_code(0, first.rc, "the fixture is seeded before accumulation is tested")
        # F rises, J rises: allowed.
        accumulate = run_gate(root, "--seed", str(work / "caps"))
        gate.assert_exit_code(0, accumulate.rc, "accumulating is the silent direction")
        # An EMPTY corpus must be refused: a baseline seeded from nothing enshrines nothing. The twin's first draft asserted a "silent shrink" refusal that could never fire, because seeds accumulate; this case is what exposed it.
        empty = work / "empty"
        empty.mkdir()
        refused = run_gate(root, "--seed", str(empty))
        gate.assert_exit_code(2, refused.rc, "seeding from zero judgeable captures is refused")
        gate.assert_contains(refused.combined, "0 judgeable", "and says why")
        gate.log_pass("an empty seed is refused; accumulation is the only silent direction")


def test_mutant_wall_scaling_removed(gate):
    gate.log_test("MUTANT: a no-op dilate must red the gate's own control")
    with harness.temp_dir() as work:
        root = build_fixture(gate, work)
        module = root / ".claude" / "hooks" / "stop" / "wl_profile.py"
        source = module.read_text(encoding="utf-8")
        old = 'int(s["t_ms"] * k)'
        # THE MUTATION IS ASSERTED BEFORE THE RUN. The twin's first draft used a sed that silently matched nothing after a formatter re-wrap: the gate ran UNMUTATED, enforced the planted E6 (exit 1), and the case read that as "wrong exit code" rather than "no mutant".
        gate.assert_eq(source.count(old), 1, "the mutation site must appear exactly once")
        module.write_text(source.replace(old, 's["t_ms"]'), encoding="utf-8")
        if 's2["t_ms"] = s["t_ms"]' not in module.read_text(encoding="utf-8"):
            gate.log_fail("mutant text not present after write")
        gate.assertions += 1
        result = run_gate(root, "--captures", str(work / "caps"))
        gate.assert_exit_code(
            2, result.rc, "a no-op dilate is refused as an instrument failure (exit 2)"
        )
        gate.assert_contains(
            result.combined,
            "dilate really moves wall",
            "and the deriver's own control is what named it",
        )
        gate.log_pass("MUTANT: removing wall scaling reds the gate's own control")


def test_the_gate_is_green_on_its_own_selftest(gate):
    """PORT-ONLY. Three of the four cases above read the gate's VERDICT, and a verdict is only worth reading if the instrument behind it passes its own
    controls on an unmutated tree. The mutant case proves the control can fail;
    this proves it does not fail by default, which is the other direction and the one that would otherwise make `test_mutant_wall_scaling_removed` pass for free."""
    gate.log_test("CONTROL: the unmutated instrument passes its own selftest")
    result = harness.run(["python3", str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the gate's own controls pass on the real tree")
    gate.assert_contains(result.combined, "0 failure(s)", "and say so with a count")
    gate.log_pass("the unmutated gate passes its own selftest, so the mutant case means something")
