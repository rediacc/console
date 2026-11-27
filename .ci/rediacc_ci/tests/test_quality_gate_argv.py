"""`rediacc_ci.quality.gate_argv` (check:ci-gate-argv) on planted entry points, both directions.

Every red case below is a shape that once let an entry point exit 0 on an argument it never read; every green case is a form the gate must keep accepting, so a rule that widened to flag the whole tree fails here first.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.controls import plant
from rediacc_ci.quality import gate_argv as mod

QUALITY = mod.QUALITY_REL

SHARED = (
    "import sys\nimport _cipath\nimport _gate_args\n\n"
    'def main(argv):\n    return 1 if "--selftest" in argv else 0\n\n'
    'if __name__ == "__main__":\n'
    '    _gate_args.parse("check_x.py", sys.argv[1:], switches=("--selftest",), valued=("--root",))\n'
    '    raise SystemExit(main(sys.argv[1:]))\n\nROOT_FLAG = "--root"\n'
)
ARGPARSE = (
    "import argparse\n\ndef main():\n    p = argparse.ArgumentParser()\n"
    '    p.add_argument("--selftest", action="store_true")\n    p.add_argument("--root")\n'
    '    p.parse_args()\n    return 0\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
)
HAND_SCAN = (
    'import sys\n\nif __name__ == "__main__":\n    if "--x" in sys.argv:\n        print(1)\n'
)
NEVER_READS = (
    'def main():\n    return 0\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
)
KNOWN_ARGS = ARGPARSE.replace("    p.parse_args()\n", "    p.parse_known_args()\n")


def tree(
    tmp_path: pathlib.Path,
    files: dict[str, str],
    scripts: dict[str, str] | None = None,
    runs: list[str] | None = None,
) -> pathlib.Path:
    """A scan root: shims under QUALITY, an optional package.json, and a lock whose gates run `runs` (default: every shim by path)."""
    (tmp_path / QUALITY).mkdir(parents=True)
    for stem, text in files.items():
        (tmp_path / QUALITY / (stem + ".py")).write_text(text, encoding="utf-8")
    if scripts is not None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    if runs is None:
        runs = ["%s/%s.py" % (QUALITY, stem) for stem in files]
    lock = tmp_path / mod.LOCK_REL
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps([{"id": "g%d" % i, "run": r} for i, r in enumerate(runs)]), encoding="utf-8"
    )
    return tmp_path


def module_file(root: pathlib.Path, dotted: str, text: str) -> pathlib.Path:
    path = mod.module_path(root, dotted)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def entry(tmp_path: pathlib.Path, text: str) -> mod.Entry:
    root = tree(tmp_path, {"check_x": text})
    return mod.analyse(root / QUALITY / "check_x.py", root, {})


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        (HAND_SCAN, "reads `sys.argv`"),
        (NEVER_READS, "never hands argv"),
        (KNOWN_ARGS, "parse_known_args"),
    ],
    ids=["hand-scan-of-sys-argv", "main-never-reads-argv", "parse-known-args"],
)
def test_red_forms_are_bypasses_named_by_what_they_do(tmp_path, text, needle):
    got = entry(tmp_path, text)
    assert got.form == "bypass"
    assert any(needle in p for p in got.problems), got.problems


def test_shared_parser_is_accepted_with_its_declared_set(tmp_path):
    got = entry(tmp_path, SHARED)
    assert (got.form, got.problems) == ("parse", [])
    assert got.decl == mod.Decl(switches=("--selftest",), valued=("--root",))


def test_plain_argparse_is_accepted(tmp_path):
    got = entry(tmp_path, ARGPARSE)
    assert (got.form, got.problems) == ("argparse", [])
    assert got.decl is not None
    assert "--selftest" in got.decl.switches
    assert got.decl.valued == ("--root",)


def test_a_parse_after_other_work_is_named(tmp_path):
    got = entry(
        tmp_path, SHARED.replace("    _gate_args.parse", "    print(1)\n    _gate_args.parse")
    )
    assert any("not the first statement" in p for p in got.problems)


def test_a_declared_flag_nothing_reads_is_named(tmp_path):
    got = entry(
        tmp_path, SHARED.replace('switches=("--selftest",)', 'switches=("--selftest", "--update")')
    )
    assert any("declares --update" in p for p in got.problems)


def test_a_registered_call_passing_an_undeclared_flag_is_red(tmp_path, capsys):
    files = {"check_x": SHARED}
    root = tree(tmp_path, files, {"check:ci-x": ".ci/scripts/quality/check_x.py --update"})
    assert mod.run(root, own={}, floor=1, debt={}) == 1
    err = capsys.readouterr().err
    assert "package.json:1: calls check_x.py with '--update'" in err


def test_a_registered_call_with_declared_flags_is_green(tmp_path, capsys):
    root = tree(
        tmp_path, {"check_x": SHARED}, {"check:ci-x": ".ci/scripts/quality/check_x.py --selftest"}
    )
    assert mod.run(root, own={}, floor=1, debt={}) == 0
    captured = capsys.readouterr()
    assert "1 registered call(s) checked" in captured.out + captured.err


def test_npm_run_args_append_to_the_last_command(tmp_path):
    scripts = {
        "check:ci-x": ".ci/scripts/quality/check_x.py --selftest && .ci/scripts/quality/check_x.py"
    }
    root = tree(tmp_path, {"check_x": SHARED}, scripts)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "w.yml").write_text(
        "run: npm run check:ci-x -- --update\n", encoding="utf-8"
    )
    calls = mod.registered_calls(root)
    assert (".github/workflows/w.yml:1", "check_x", ["--update"]) in calls


def test_prose_naming_an_entry_point_is_not_a_call(tmp_path):
    root = tree(tmp_path, {"check_x": SHARED}, {"a": "echo check_x.py"})
    (root / "scripts" / "ci-runner").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "ci-runner" / "manifest.ts").write_text(
        "// .ci/scripts/quality/check_x.py holds in place.\n", encoding="utf-8"
    )
    assert mod.registered_calls(root) == []


def test_a_comment_line_naming_an_entry_point_with_a_dash_token_is_not_a_call(tmp_path):
    """8dee6a3b.1: prose ending in a dash token ("for details -h") is not an argument list, while the same text on a code line is still judged."""
    root = tree(tmp_path, {"check_x": SHARED})
    (root / "scripts" / "ci-runner").mkdir(parents=True, exist_ok=True)
    manifest = root / "scripts" / "ci-runner" / "manifest.ts"
    manifest.write_text("// see .ci/scripts/quality/check_x.py for details -h\n", encoding="utf-8")
    assert mod.registered_calls(root) == []
    manifest.write_text("run('.ci/scripts/quality/check_x.py --update')\n", encoding="utf-8")
    assert [c[1:] for c in mod.registered_calls(root)] == [("check_x", ["--update"])]


def test_fewer_entry_points_than_the_floor_is_refused(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    assert mod.run(root, own={}, floor=2, debt={}) == 1
    assert "the scan is not seeing the tree" in capsys.readouterr().err


def test_an_unreadable_lock_is_refused_not_passed(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    (root / mod.LOCK_REL).unlink()
    assert mod.run(root, own={}, floor=0, debt={}) == 1
    assert "the scan is not seeing the tree" in capsys.readouterr().err


def test_the_floor_counts_what_the_lock_runs_on_the_real_tree():
    """FLOOR is re-derived from the lock's population (206 on 2026-11-27); the real lock must clear it, and the floor must still sit under it."""
    from_lock = mod.lock_targets(paths.repo_root())
    assert from_lock is not None
    assert mod.FLOOR == 180
    assert len(from_lock) >= mod.FLOOR


# -- the module form: the entry the lock really runs ---------------------------------------

MODULE_IGNORES = (
    "import sys\n\n"
    'def main(argv):\n    return 1 if argv and argv[0] == "--selftest" else 0\n\n'
    'if __name__ == "__main__":\n    raise SystemExit(main(sys.argv[1:]))\n'
)
MODULE_REFUSES = plant(
    MODULE_IGNORES,
    'if __name__ == "__main__":\n',
    'if __name__ == "__main__":\n    from rediacc_ci.quality import gate_args\n\n'
    '    gate_args.parse("x.py", sys.argv[1:], switches=("--selftest",))\n',
)
DOTTED = "rediacc_ci.quality.planted"
RUN_MODULE = "PYTHONPATH=.ci python3 -m %s" % DOTTED


def test_a_lock_run_module_that_ignores_an_unknown_flag_is_red(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_IGNORES)
    assert mod.run(root, own={}, floor=1, debt={}) == 1
    err = capsys.readouterr().err
    assert "planted.py (python3 -m %s): " % DOTTED in err
    assert "never refuses what is left" in err or "reaches neither" in err


def test_the_old_shim_only_population_never_saw_that_module(tmp_path):
    """The control the finding needed: the shim scan the gate used to run holds only check_x, which is clean, so it was green over the same tree."""
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_IGNORES)
    shims = mod.entry_points(root)
    assert [p.stem for p in shims] == ["check_x"]
    assert all(mod.analyse(p, root, {}).problems == [] for p in shims)


def test_a_lock_run_module_that_parses_first_after_its_import_is_green(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    path = module_file(root, DOTTED, MODULE_REFUSES)
    got = mod.analyse(path, root, {}, key=DOTTED)
    assert (got.form, got.problems) == ("parse", [])
    assert mod.run(root, own={}, floor=1, debt={}) == 0
    out = capsys.readouterr()
    assert "1 module, 0 shim, 0 script" in out.err + out.out


def test_npm_run_in_the_lock_resolves_through_package_json(tmp_path):
    root = tree(
        tmp_path,
        {"check_x": SHARED},
        scripts={"check:ci-p": RUN_MODULE + " && .ci/scripts/quality/check_x.py"},
        runs=["npm run check:ci-p"],
    )
    module_file(root, DOTTED, MODULE_REFUSES)
    got = mod.lock_targets(root)
    assert got is not None
    assert sorted((t.key, t.kind) for t in got) == [("check_x", "shim"), (DOTTED, "module")]


def test_a_lock_entry_naming_a_missing_module_is_a_finding(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    assert mod.run(root, own={}, floor=1, debt={}) == 1
    assert "the lock runs it as module, and the file does not exist" in capsys.readouterr().err


def test_a_registered_module_call_with_an_undeclared_flag_is_red(tmp_path, capsys):
    root = tree(
        tmp_path,
        {"check_x": SHARED},
        scripts={"check:ci-p": RUN_MODULE + " --update"},
        runs=[RUN_MODULE],
    )
    module_file(root, DOTTED, MODULE_REFUSES)
    assert mod.run(root, own={}, floor=1, debt={}) == 1
    assert "calls %s with '--update'" % DOTTED in capsys.readouterr().err


def test_known_bypass_debt_is_printed_and_not_red(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_IGNORES)
    assert mod.run(root, own={}, floor=1, debt={DOTTED: "BLOCKER: a reason"}) == 0
    out = capsys.readouterr().out
    assert "known bypass (shrink-only debt" in out
    assert DOTTED in out


def test_a_debt_entry_that_now_refuses_is_red_until_its_line_goes(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_REFUSES)
    assert mod.run(root, own={}, floor=1, debt={DOTTED: "BLOCKER: a reason"}) == 1
    assert "delete its line so the debt list keeps shrinking" in capsys.readouterr().err


def test_a_debt_entry_that_is_no_entry_point_is_red(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    assert mod.run(root, own={}, floor=1, debt={"rediacc_ci.gone": "BLOCKER: x"}) == 1
    assert "KNOWN_BYPASS names rediacc_ci.gone" in capsys.readouterr().err


def test_every_known_bypass_carries_a_blocker_reason():
    assert all(why.startswith("BLOCKER:") for why in mod.KNOWN_BYPASS.values())


def test_known_bypass_stays_inside_the_frozen_set():
    """Shrink-only in code (review 60874d5e.1): the real list may hold only names the frozen set allows."""
    assert set(mod.KNOWN_BYPASS) <= mod.KNOWN_BYPASS_FROZEN


def test_a_new_bypass_listed_as_debt_is_red_when_it_was_not_frozen(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_IGNORES)
    listed = {DOTTED: "BLOCKER: a reason"}
    assert mod.run(root, own={}, floor=1, debt=listed, frozen=frozenset(listed)) == 0
    assert mod.run(root, own={}, floor=1, debt=listed, frozen=frozenset()) == 1
    assert "was not in the debt frozen" in capsys.readouterr().err


@pytest.mark.parametrize("entry", ["stray", {"id": "check:ci-no-run"}, {"id": "x", "run": " "}])
def test_a_malformed_lock_entry_is_a_finding_not_a_silent_drop(tmp_path, capsys, entry):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_REFUSES)
    lock = root / mod.LOCK_REL
    lock.write_text(json.dumps([*json.loads(lock.read_text()), entry]), encoding="utf-8")
    assert mod.run(root, own={}, floor=1, debt={}) == 1
    assert "the entry points it runs are not being judged" in capsys.readouterr().err


def test_an_own_refusal_name_that_is_not_an_entry_point_is_red(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    assert mod.run(root, own={"check_gone": "a reason"}, floor=1, debt={}) == 1
    assert "OWN_REFUSAL names check_gone" in capsys.readouterr().err


def test_selftest_passes():
    assert mod.selftest() == 0


# -- the modules #d78d1ae3 moved onto the shared parse ---------------------------------------

REFUSING_MODULES = (
    "rediacc_ci.setup.port_parity",
    "rediacc_ci.security.rdc_sh_env_check",
    "rediacc_ci.release.install_sh_config_check",
    "rediacc_ci.quality.editorconfig",
    "rediacc_ci.quality.ci_scans_tracked_paths",
    "rediacc_ci.quality.cli_contract_coverage",
    "rediacc_ci.quality.prose_duplication",
    "rediacc_ci.quality.silent_failure_patterns",
    "rediacc_ci.quality.swallowed_failures",
)


@pytest.mark.parametrize("dotted", REFUSING_MODULES)
def test_the_module_form_refuses_an_unknown_flag_before_any_work(dotted):
    """Run exactly as the lock runs it. The first five exited 0 here before #d78d1ae3 and ran the whole gate; the parse now refuses with exit 2 and names the flag, so nothing else ran."""
    root = paths.repo_root()
    proc = subprocess.run(
        [sys.executable, "-m", dotted, mod.BOGUS],
        cwd=str(root),
        env=dict(os.environ, PYTHONPATH=str(root / ".ci")),
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stdout[-400:], proc.stderr[-400:])
    assert "unknown argument '%s'" % mod.BOGUS in proc.stderr
    assert proc.stdout == "", "a refused run does no work, so it prints nothing on stdout"


@pytest.mark.parametrize("dotted", REFUSING_MODULES)
def test_the_module_form_is_judged_as_a_shared_parse(dotted):
    root = paths.repo_root()
    path = mod.module_path(root, dotted)
    got = mod.analyse(path, root, {}, key=dotted)
    assert (got.form, got.problems) == ("parse", [])


# A frozen ceiling for the shrink-only debt list: a key added to KNOWN_BYPASS makes its entry read as "debt" before the file is judged, so a new genuine bypass named there would be green. Deleting a line from the list is the only edit that needs no change here; adding one fails this test until a reviewer edits the frozen set on purpose.
FROZEN_KNOWN_BYPASS = {
    ".ci/rediacc_ci/check_pytest.py",
    ".ci/rediacc_ci/deploy/write_once_guard_check.py",
    ".ci/rediacc_ci/release/install_script_check.py",
    ".ci/rediacc_ci/security/ci_workflow_invariants.py",
    ".ci/scripts/security/check_workflow_gates.py",
    "rediacc_ci.private.run_account",
    "rediacc_ci.private.run_renet",
    "rediacc_ci.proxies.cli_manifest",
    "rediacc_ci.proxies.docker_prepull",
    "rediacc_ci.proxies.ensure_nfpm",
    "rediacc_ci.proxies.go_unit",
    "rediacc_ci.proxies.license_e2e",
    "rediacc_ci.proxies.linux_packages",
    "rediacc_ci.proxies.ops_host_check",
    "rediacc_ci.proxies.rdc_update",
    "rediacc_ci.proxies.unit_tests",
    "rediacc_ci.security.actionlint",
    "rediacc_ci.security.audit",
    "rediacc_ci.security.check_commands",
    "rediacc_ci.security.shellcheck",
    "rediacc_ci.security.shfmt",
    "rediacc_ci.setup.tools",
    "rediacc_ci.testrun.onprem_lane",
}


def test_known_bypass_can_only_shrink():
    grown = sorted(set(mod.KNOWN_BYPASS) - FROZEN_KNOWN_BYPASS)
    assert grown == [], (
        "KNOWN_BYPASS grew: give the entry a parse instead of listing it: %s" % grown
    )


def test_a_malformed_lock_entry_is_refused_not_dropped(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    module_file(root, DOTTED, MODULE_REFUSES)
    lock = root / mod.LOCK_REL
    for bad in ("not-an-object", {"id": "no-run"}, {"id": "n", "run": 7}, {"id": "e", "run": " "}):
        gates = [*json.loads(lock.read_text(encoding="utf-8")), bad]
        lock.write_text(json.dumps(gates), encoding="utf-8")
        assert mod.lock_targets(root) is None, bad
        assert mod.run(root, own={}, floor=1, debt={}) == 1
        assert "the scan is not seeing the tree" in capsys.readouterr().err
        lock.write_text(json.dumps(gates[:-1]), encoding="utf-8")
    assert mod.run(root, own={}, floor=1, debt={}) == 0


def test_an_npm_chain_deeper_than_six_still_reaches_its_entry_point(tmp_path):
    scripts = {"s%d" % i: "npm run s%d" % (i + 1) for i in range(9)}
    scripts["s9"] = RUN_MODULE
    root = tree(tmp_path, {"check_x": SHARED}, scripts=scripts, runs=["npm run s0"])
    got = mod.lock_targets(root)
    assert got is not None
    assert [(t.key, t.kind) for t in got] == [(DOTTED, "module")]
    wide = {"w%d" % i: "python3 -m rediacc_ci.quality.m%d" % i for i in range(9)}
    wide["all"] = " && ".join("npm run w%d" % i for i in range(9))
    root2 = tree(tmp_path / "wide", {"check_x": SHARED}, scripts=wide, runs=["npm run all"])
    got2 = mod.lock_targets(root2)
    assert got2 is not None
    assert len(got2) == 9


def test_a_non_parser_import_before_the_parse_is_work_and_is_named(tmp_path):
    text = MODULE_REFUSES.replace(
        "    from rediacc_ci.quality import gate_args\n",
        "    from rediacc_ci.quality import gate_args\n    import heavy_side_effects\n",
    )
    assert text != MODULE_REFUSES
    root = tree(tmp_path, {"check_x": SHARED}, runs=[RUN_MODULE])
    path = module_file(root, DOTTED, text)
    got = mod.analyse(path, root, {}, key=DOTTED)
    assert any("work runs before an unknown argument is refused" in x for x in got.problems), got


def test_module_path_of_a_package_is_its_main_file(tmp_path):
    pkg = tmp_path / ".ci" / "rediacc_ci" / "pkgmod"
    pkg.mkdir(parents=True)
    (pkg / "__main__.py").write_text("", encoding="utf-8")
    assert mod.module_path(tmp_path, "rediacc_ci.pkgmod") == pkg / "__main__.py"
    assert mod.module_path(tmp_path, "rediacc_ci.plain") == pkg.parent / "plain.py"
