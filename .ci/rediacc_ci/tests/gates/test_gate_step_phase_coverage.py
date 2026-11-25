"""Gate test for `rediacc_ci.quality.step_phase_coverage` (`check:ci-step-phase-coverage`).

The gate lists every step id renet's non-test sources pass to a step timer's `Start` or `Record` and refuses an id missing from `private/account/web/src/lib/run-phases.json`, or a json id renet no longer emits (agent/plans/PLAN-console-animations.md D7, box AN6).

BOTH DIRECTIONS, ON THE REAL SHAPE. The selftest proves the helpers against a three-file fixture. That proves the regexes, not that the gate reads renet as renet is written, so the plants here start from a COPY OF THE REAL renet Go sources and the real phase map under a root override and change exactly one thing each. The unplanted copy is the control: it must be green, or every red below could be red for a reason unrelated to its plant.

ZERO INPUTS IS 77. An empty root has no renet and no map; the gate must say it cannot run, never report a clean map. A root whose renet holds no timer call is the same refusal, through the floors rather than the missing directory.

NO `xdist_group`. Every case is a subprocess over the real tree (read only) or over its own tmp_path copy.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MODULE = "rediacc_ci.quality.step_phase_coverage"
SUT = paths.from_root(".ci", "rediacc_ci", "quality", "step_phase_coverage.py")
RENET_SUBDIR = "private/renet"
LIB_SUBDIR = "private/account/web/src/lib"
REAL_RENET = paths.from_root(*RENET_SUBDIR.split("/"))
REAL_LIB = paths.from_root(*LIB_SUBDIR.split("/"))


def _run(*args: str, root: pathlib.Path | None = None) -> harness.RunResult:
    env = {"PYTHONPATH": str(paths.from_root(".ci"))}
    if root is not None:
        env[paths.ROOT_ENV] = str(root)
    return harness.run([sys.executable, "-m", MODULE, *args], cwd=paths.repo_root(), env=env)


def _require_subject(gate) -> None:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not (REAL_RENET / "pkg" / "output" / "steps.go").is_file():
        gate.log_fail(
            "%s is not checked out, so no case below could read a step id. "
            "Fix: git submodule update --init %s" % (RENET_SUBDIR, RENET_SUBDIR)
        )
    if not (REAL_LIB / "run-phases.json").is_file():
        gate.log_fail(
            "the phase map is missing under %s. Fix: git submodule update --init private/account"
            % LIB_SUBDIR
        )


def _go_only(directory: str, names: list[str]) -> list[str]:
    base = pathlib.Path(directory)
    return [n for n in names if (base / n).is_file() and not n.endswith(".go")]


def _copy_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A root holding the real renet Go sources, the real run-phases.json and run-phases.ts, and nothing else."""
    root = tmp_path / "root"
    shutil.copytree(
        REAL_RENET,
        root / RENET_SUBDIR,
        ignore=_go_only,
        symlinks=True,
    )
    lib = root / LIB_SUBDIR
    lib.mkdir(parents=True)
    for name in ("run-phases.json", "run-phases.ts"):
        shutil.copy(REAL_LIB / name, lib / name)
    return root


def _phases(root: pathlib.Path) -> tuple[pathlib.Path, dict]:
    path = root / LIB_SUBDIR / "run-phases.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_gate_green_on_real_tree_with_a_non_trivial_shape(gate):
    gate.log_test("the gate is green on the real tree and prints a non-empty shape")
    _require_subject(gate)
    result = _run()
    gate.assert_exit(0, result, "gate must pass on the committed renet and phase map")
    gate.assert_contains(result.combined, "controls first", "controls ran before the verdict")
    gate.assert_contains(
        result.combined, "every plant fired", "the selftest reported in the real run"
    )
    gate.assert_contains(result.combined, "step phase coverage:", "green summary line present")
    _, phases = _phases(paths.repo_root())
    gate.assert_contains(
        result.combined,
        "maps %d to a scene and lists %d plain" % (len(phases["scenes"]), len(phases["plain"])),
        "the success line counts the committed map",
    )
    gate.assert_contains(
        result.combined, "alias(es): mark", "the migrate cutover alias was resolved"
    )
    gate.log_pass("green over the committed map")


def test_selftest_passes(gate):
    gate.log_test("the gate's own controls pass behind --selftest")
    _require_subject(gate)
    result = _run("--selftest")
    gate.assert_exit(0, result, "selftest must pass")
    gate.assert_contains(result.combined, "every plant fired", "selftest verdict present")
    gate.log_pass("selftest green")


def test_unplanted_copy_is_green(gate, tmp_path):
    gate.log_test(
        "CONTROL: an untouched copy of renet and the map is green under the root override"
    )
    _require_subject(gate)
    result = _run(root=_copy_root(tmp_path))
    gate.assert_exit(0, result, "the copy must be green, or every plant below proves nothing")
    gate.log_pass("unplanted copy green")


def test_unmapped_renet_step_is_caught(gate, tmp_path):
    gate.log_test("PLANT: a renet timer emitting an id the map does not know turns the gate red")
    _require_subject(gate)
    root = _copy_root(tmp_path)
    probe = root / RENET_SUBDIR / "cmd" / "renet" / "zz_gate_probe.go"
    probe.write_text(
        'package main\n\nfunc zzGateProbe() {\n\ttimer := output.NewStepTimer()\n\ttimer.Start("zz_unmapped_probe")\n}\n',
        encoding="utf-8",
    )
    result = _run(root=root)
    gate.assert_exit(1, result, "an unmapped step id must be a finding")
    gate.assert_contains(
        result.combined, "zz_gate_probe.go:5", "the finding names the file and line"
    )
    gate.assert_contains(
        result.combined, "renet emits step `zz_unmapped_probe`", "the finding names the id"
    )
    gate.log_pass("unmapped id caught")


def test_stale_json_id_is_caught(gate, tmp_path):
    gate.log_test("PLANT: a json id no renet timer emits turns the gate red")
    _require_subject(gate)
    root = _copy_root(tmp_path)
    path, phases = _phases(root)
    phases["plain"].append("zz_stale_probe")
    path.write_text(json.dumps(phases, indent=2), encoding="utf-8")
    result = _run(root=root)
    gate.assert_exit(1, result, "a stale json id must be a finding")
    gate.assert_contains(
        result.combined, "`zz_stale_probe` is an id no renet", "the finding names the id"
    )
    gate.log_pass("stale id caught")


def test_removed_cutover_alias_call_makes_its_id_stale(gate, tmp_path):
    gate.log_test(
        "PLANT: removing the one call through the `mark` alias leaves cutover_complete stale"
    )
    _require_subject(gate)
    root = _copy_root(tmp_path)
    migrate = root / RENET_SUBDIR / "cmd" / "renet" / "repository_migrate.go"
    text = migrate.read_text(encoding="utf-8")
    needle = "ops.mark(migrateCutoverMarker,"
    if needle not in text:
        gate.log_fail("the migrate cutover call moved; update this plant to the new spelling")
    migrate.write_text(text.replace(needle, "_ = (migrateCutoverMarker,"), encoding="utf-8")
    result = _run(root=root)
    gate.assert_exit(1, result, "the cutover id must go stale once its only emitter is gone")
    gate.assert_contains(
        result.combined, "`cutover_complete` is an id no renet", "the alias was the only emitter"
    )
    gate.log_pass("alias-only emitter is load bearing")


def test_empty_root_cannot_run(gate, tmp_path):
    gate.log_test("ANTI-VACUITY: an empty root is CANNOT RUN (77), never a pass")
    _require_subject(gate)
    result = _run(root=tmp_path)
    gate.assert_exit(77, result, "an empty root must refuse a verdict")
    gate.assert_contains(result.combined, "CANNOT RUN", "the refusal is named")
    gate.log_pass("empty root refused")


def test_renet_without_timer_calls_cannot_run(gate, tmp_path):
    gate.log_test("ANTI-VACUITY: a renet copy whose timer calls are gone trips the floors (77)")
    _require_subject(gate)
    root = tmp_path / "root"
    (root / RENET_SUBDIR / "pkg" / "x").mkdir(parents=True)
    (root / RENET_SUBDIR / "pkg" / "x" / "x.go").write_text("package x\n", encoding="utf-8")
    lib = root / LIB_SUBDIR
    lib.mkdir(parents=True)
    for name in ("run-phases.json", "run-phases.ts"):
        shutil.copy(REAL_LIB / name, lib / name)
    result = _run(root=root)
    gate.assert_exit(77, result, "a renet with no timer calls must refuse a verdict")
    gate.assert_contains(result.combined, "VACUOUS", "the floor refusal is named")
    gate.log_pass("collapsed corpus refused")
