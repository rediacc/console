"""`rediacc_ci.quality.gate_argv` (check:ci-gate-argv) on planted entry points, both directions.

Every red case below is a shape that once let an entry point exit 0 on an argument it never read; every green case is a form the gate must keep accepting, so a rule that widened to flag the whole tree fails here first.
"""

import json
import pathlib

import pytest

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
    tmp_path: pathlib.Path, files: dict[str, str], scripts: dict[str, str] | None = None
) -> pathlib.Path:
    (tmp_path / QUALITY).mkdir(parents=True)
    for stem, text in files.items():
        (tmp_path / QUALITY / (stem + ".py")).write_text(text, encoding="utf-8")
    if scripts is not None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return tmp_path


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
    assert mod.run(root, own={}, floor=1) == 1
    err = capsys.readouterr().err
    assert "package.json:1: calls check_x.py with '--update'" in err


def test_a_registered_call_with_declared_flags_is_green(tmp_path, capsys):
    root = tree(
        tmp_path, {"check_x": SHARED}, {"check:ci-x": ".ci/scripts/quality/check_x.py --selftest"}
    )
    assert mod.run(root, own={}, floor=1) == 0
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
    (root / "scripts" / "ci-runner").mkdir(parents=True)
    (root / "scripts" / "ci-runner" / "manifest.ts").write_text(
        "// .ci/scripts/quality/check_x.py holds in place.\n", encoding="utf-8"
    )
    assert mod.registered_calls(root) == []


def test_fewer_entry_points_than_the_floor_is_refused(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    assert mod.run(root, own={}, floor=2) == 1
    assert "the scan is not seeing the tree" in capsys.readouterr().err


def test_the_real_floor_is_150():
    assert mod.FLOOR == 150


def test_an_own_refusal_name_that_is_not_an_entry_point_is_red(tmp_path, capsys):
    root = tree(tmp_path, {"check_x": SHARED})
    assert mod.run(root, own={"check_gone": "a reason"}, floor=1) == 1
    assert "OWN_REFUSAL names check_gone" in capsys.readouterr().err


def test_selftest_passes():
    assert mod.selftest() == 0
