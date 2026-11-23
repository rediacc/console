"""Every `.ci/scripts/quality/check_*.py` entry point refuses an argument it does not take, with exit 2.

THE FAILURE THIS GUARDS. `npm run check:ci-record-paths -- --update` exited 0 having done nothing, and 138 sibling entry points read `sys.argv` the same way (18 more read none at all and ignored everything). `_gate_args.parse` is adopted in each of them; this file runs EVERY entry point, for real, with `--definitely-not-a-flag` and demands rc 2. It is the control the adoption itself cannot be: a script that lost its `_gate_args.parse` call in a merge, kept a hand-rolled parse, or gained a code path ahead of the parse would exit 0 or 1 here.

THE SET IS THE DIRECTORY, not "the scripts that carry the call". A set derived from the call would shrink silently the day someone deleted the call, which is the exact failure to catch. So every `check_*.py` is run, and a script that does NOT carry the shared parse must be NAMED in REFUSES_ITSELF with how it refuses, or in FIXED_ELSEWHERE; the classification control fails on any script that is neither, and on a name listed there that now carries the call (the list only shrinks). A new entry point therefore has to either call `_gate_args.parse` or be named here with its reason.

An adopted script must refuse in the shared format on stderr (`<gate>.py: unknown argument '<arg>' (accepted: ...)`) with nothing on stdout. A script that refuses on its own is only required to exit 2: three of them print a usage text that does not name the flag, and that is their message to keep.
"""

import ast
import pathlib
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

QUALITY = paths.repo_root() / ".ci" / "scripts" / "quality"
BOGUS = "--definitely-not-a-flag"
CALL = "_gate_args.parse("

# Entry points that refuse an unknown argument through their own code, with where. They are RUN below like every other script.
REFUSES_ITSELF = {
    "check_config_server_key_constant": "own argument check, rc 2",
    "check_hooks_resolvable": "argparse",
    "check_i18n_value_types": "argparse",
    "check_inline_python": "argparse",
    "check_inline_suppressions": "inline_suppressions.argv_refusal",
    "check_job_timeout_headroom": "argparse",
    "check_lint_rule_liveness": "argparse",
    "check_lint_scope_coverage": "argparse",
    "check_model_invocable_commands": "argparse in model_invocable_commands.main",
    "check_plan_live_proof": "argparse",
    "check_runner_advice": "argparse",
    "check_scope_completeness": "argparse",
    "check_scope_mirrors": "`if rest or ...: print(USAGE); return 2`",
    "check_secret_reachability": "argparse",
    "check_settings_registry": "own argument check, rc 2",
    "check_worker_observability_budget": "own argument check, rc 2",
}
# Left out of the run on purpose, and named in the output.
FIXED_ELSEWHERE: dict[str, str] = {}
# Fewer than this and the scan is not seeing the tree.
MIN_SCRIPTS = 174
MIN_ADOPTED = 158


def everything() -> list[str]:
    return sorted(p.stem for p in QUALITY.glob("check_*.py"))


def carries_call(stem: str) -> bool:
    return CALL in (QUALITY / (stem + ".py")).read_text()


def targets() -> list[str]:
    return [s for s in everything() if s not in FIXED_ELSEWHERE]


def test_the_scan_sees_the_entry_points(gate):
    every = everything()
    adopted = [s for s in every if carries_call(s)]
    gate.log_info(
        "%d entry points: %d carry the shared parse, %d refuse on their own, %d fixed elsewhere"
        % (len(every), len(adopted), len(REFUSES_ITSELF), len(FIXED_ELSEWHERE))
    )
    if len(every) < MIN_SCRIPTS or len(adopted) < MIN_ADOPTED:
        gate.log_fail(
            "%d check_*.py (floor %d) and %d adopted (floor %d) under %s: the scan is not "
            "seeing the tree, or an adoption was lost"
            % (len(every), MIN_SCRIPTS, len(adopted), MIN_ADOPTED, QUALITY)
        )
    gate.log_pass(
        "%d entry points enumerated, %d carry the shared parse" % (len(every), len(adopted))
    )


def test_every_script_is_adopted_or_named(gate):
    unnamed = [
        s
        for s in everything()
        if not carries_call(s) and s not in REFUSES_ITSELF and s not in FIXED_ELSEWHERE
    ]
    gate.assert_eq(
        unnamed,
        [],
        "these entry points neither call _gate_args.parse nor appear in REFUSES_ITSELF: add the "
        "call (do not add the name)",
    )
    stale = [s for s in list(REFUSES_ITSELF) + list(FIXED_ELSEWHERE) if s not in everything()]
    gate.assert_eq(stale, [], "every named exemption is a real script")
    adopted_but_named = [s for s in REFUSES_ITSELF if carries_call(s)]
    gate.assert_eq(
        adopted_but_named, [], "a script that now carries the call leaves REFUSES_ITSELF"
    )
    gate.log_pass("every entry point is adopted or named, and no name is stale")


@pytest.mark.parametrize("stem", targets())
def test_an_unknown_flag_exits_2_naming_it(gate, stem):
    script = QUALITY / (stem + ".py")
    result = harness.run([sys.executable, str(script), BOGUS], cwd=paths.repo_root(), timeout=120)
    gate.assert_exit_code(2, result.rc, "%s must refuse %s" % (stem, BOGUS))
    if carries_call(stem):
        gate.assert_contains(result.combined, BOGUS, "%s names the argument it refused" % stem)
        gate.assert_contains(
            result.err,
            "%s.py: unknown argument '%s'" % (stem, BOGUS),
            "%s refuses on stderr in the shared format" % stem,
        )
        gate.assert_eq(result.out, "", "%s printed nothing on stdout before refusing" % stem)
    gate.log_pass("%s refuses %s with rc 2" % (stem, BOGUS))


def test_a_declared_flag_is_still_taken(gate):
    """The accepting side: `check_ops_health.py` takes -h, so the refusal is not a blanket one."""
    script = QUALITY / "check_ops_health.py"
    helped = harness.run([sys.executable, str(script), "-h"], cwd=paths.repo_root())
    gate.assert_exit_code(0, helped.rc, "-h is a declared switch and prints the usage")
    stray = harness.run([sys.executable, str(script), "-h", BOGUS], cwd=paths.repo_root())
    gate.assert_exit_code(2, stray.rc, "an unknown flag beside a declared one is still refused")
    gate.log_pass("a declared flag parses and an undeclared neighbour is refused")


# THE RUN CI MAKES. A gate whose `---- gate ----` header sits in its rediacc_ci.quality module is registered as `PYTHONPATH=.ci python3 -m rediacc_ci.quality.<x>` (PLAN-tooling-code-reduction D2), so the entry point above is no longer what the lane starts. Each such module refuses an unknown argument itself, from its own `__main__`, or the move dropped the check this file exists for.
MODULES = paths.repo_root() / ".ci" / "rediacc_ci" / "quality"
MIN_HEADED_MODULES = 80


def headed_modules() -> list[str]:
    return sorted(
        p.stem
        for p in MODULES.glob("*.py")
        if "\n---- gate ----\n" in p.read_text(encoding="utf-8")
    )


def test_the_scan_sees_the_headed_modules(gate):
    found = headed_modules()
    if len(found) < MIN_HEADED_MODULES:
        gate.log_fail(
            "%d modules under %s carry a gate header (floor %d): the scan is not seeing the tree"
            % (len(found), MODULES, MIN_HEADED_MODULES)
        )
    gate.log_pass("%d header-carrying modules enumerated" % len(found))


@pytest.mark.parametrize("mod", headed_modules())
def test_a_headed_module_run_with_dash_m_refuses_an_unknown_flag(gate, mod):
    result = harness.run(
        [sys.executable, "-m", "rediacc_ci.quality." + mod, BOGUS],
        cwd=paths.repo_root(),
        timeout=120,
        env={"PYTHONPATH": str(paths.repo_root() / ".ci")},
    )
    gate.assert_exit_code(2, result.rc, "rediacc_ci.quality.%s must refuse %s" % (mod, BOGUS))
    gate.log_pass("rediacc_ci.quality.%s refuses %s with rc 2" % (mod, BOGUS))


def runpy_entries(quality: pathlib.Path) -> list[str]:
    """Entry scripts under `quality` that run their module through `runpy`: check:ci-gate-argv cannot follow that hop to the module's parse, so such a shim reads as a bypass (CR2 batch B shipped nine and rewrote them to call `main(argv)` in 54a54fd570 and db09591e07)."""
    hits = []
    for script in sorted(quality.glob("check_*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(n == "runpy" or n.startswith("runpy.") for n in names):
                hits.append(script.stem)
                break
    return hits


def test_no_entry_runs_its_module_through_runpy(gate, tmp_path):
    gate.log_test("no quality entry script runs its module through runpy")
    # CONTROL: a planted runpy shim is seen, and a main(argv) shim beside it is not.
    (tmp_path / "check_planted.py").write_text(
        'import runpy\nif __name__ == "__main__":\n    runpy.run_module("rediacc_ci.quality.x", run_name="__main__")\n',
        encoding="utf-8",
    )
    (tmp_path / "check_clean.py").write_text(
        'import sys\nfrom rediacc_ci.quality import x\nif __name__ == "__main__":\n    raise SystemExit(x.main(sys.argv[1:]))\n',
        encoding="utf-8",
    )
    gate.assert_eq(
        runpy_entries(tmp_path), ["check_planted"], "the planted runpy shim, and only it, is found"
    )
    found = runpy_entries(QUALITY)
    gate.assert_eq(found, [], "entry scripts that run their module through runpy")
    gate.log_pass("no runpy entry under .ci/scripts/quality")
