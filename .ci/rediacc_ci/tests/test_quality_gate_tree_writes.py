"""`rediacc_ci.quality.gate_tree_writes` and its Python scanner, driven directly, both directions.

The Python half (`gate_tree_writes_py`) is exercised in-process on planted modules; the pipeline (`analyze`, the policy, `main`) runs over a planted tree through the `--root/--lock/--pkg` seams, so nothing here writes the real tree. The TS half has no vitest home; its `--selftest` is driven from the gate's selftest, which the last case runs.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import gate_tree_writes as gate
from rediacc_ci.quality import gate_tree_writes_py as py

ROOT = paths.repo_root()


def scan(tmp_path: pathlib.Path, files: dict[str, str], entry: str) -> list[py.Site]:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    a = py.Analyzer(tmp_path, py.load_mutators(tmp_path, ROOT))
    return a.analyze_group([entry]).sites


def test_repo_root_write_is_tree_and_temp_named_root_is_temp(tmp_path):
    tree = scan(
        tmp_path,
        {"g.py": "from rediacc_ci import paths\n(paths.repo_root() / 'x').write_text('x')\n"},
        "g.py",
    )
    assert [s.origin for s in tree] == ["TREE"]
    temp = scan(
        tmp_path,
        {
            "t.py": "import pathlib, tempfile\nwith tempfile.TemporaryDirectory() as tmp:\n"
            "    root = pathlib.Path(tmp)\n    (root / 'x').write_text('x')\n"
        },
        "t.py",
    )
    assert [s.origin for s in temp] == ["TEMP"]


def test_parameter_flow_is_per_call(tmp_path):
    """TREE through one call, TEMP through another: two contexts, the tree one gated."""
    sites = scan(
        tmp_path,
        {
            "g.py": "import sys, tempfile\nfrom rediacc_ci import paths\n\n\n"
            "def write(root):\n    (root / 'b').write_text('x')\n\n\n"
            "write(tempfile.mkdtemp())\nif '--write' in sys.argv:\n    write(paths.repo_root())\n"
        },
        "g.py",
    )
    got = sorted((s.origin, s.guard) for s in sites)
    assert got == [("TEMP", []), ("TREE", [["--write"]])]


def test_mode_gate_through_a_function_and_an_alias(tmp_path):
    sites = scan(
        tmp_path,
        {
            "g.py": "import sys\nfrom rediacc_ci import paths\n\n\n"
            "def refresh():\n    (paths.repo_root() / 'B').write_text('x')\n\n\n"
            "update = '--update' in sys.argv\nif update:\n    refresh()\n"
        },
        "g.py",
    )
    assert [(s.origin, s.guard) for s in sites] == [("TREE", [["--update"]])]


def test_unreached_function_is_not_a_site(tmp_path):
    sites = scan(
        tmp_path,
        {
            "g.py": "from rediacc_ci import paths\n\n\ndef never():\n    (paths.repo_root() / 'x').touch()\n"
        },
        "g.py",
    )
    assert sites == []


def test_scratch_is_ci_cache_only(tmp_path):
    sites = scan(
        tmp_path,
        {
            "g.py": "from rediacc_ci import paths\n(paths.repo_root() / '.ci' / 'cache' / 'x').mkdir()\n"
            "(paths.repo_root() / 'packages' / 'www' / 'dist').mkdir()\n"
        },
        "g.py",
    )
    assert [s.origin for s in sorted(sites, key=lambda s: s.line)] == ["SCRATCH", "TREE"]


def test_subprocess_mutator_targets_cwd(tmp_path):
    sites = scan(
        tmp_path,
        {
            "g.py": "import subprocess, tempfile\nsubprocess.run(['git', 'add', '-A'])\n"
            "subprocess.run(['git', 'add', '-A'], cwd=tempfile.mkdtemp())\nsubprocess.run(['git', 'status'])\n"
        },
        "g.py",
    )
    assert sorted((s.line, s.origin) for s in sites) == [(2, "TREE"), (3, "TEMP")]


@pytest.mark.parametrize(
    ("guard", "argv", "gated"),
    [
        ([["--write"]], [set()], True),
        ([["--write"]], [{"--write"}], False),
        ([["!--check"]], [{"--check"}], True),
        ([["!--check"]], [{"--check"}, set()], False),
    ],
)
def test_gating_is_per_invocation(guard, argv, gated):
    assert bool(gate.gating(guard, argv)) is gated


def test_pragma_rules():
    site = py.Site("f.py", 3, "open", "x", "UNRESOLVED", [])
    assert (
        gate.classify(site, [set()], ("safe", "", "a reason that is long enough"))[0] == "DECLARED"
    )
    assert gate.classify(site, [set()], ("safe", "", "short"))[0] == "BAD-PRAGMA"
    temp = py.Site("f.py", 3, "open", "x", "TEMP", [])
    assert gate.classify(temp, [set()], ("safe", "", "a reason that is long enough"))[0] == "STALE"
    # Not stale when the same line is unsafe in another calling context or entry.
    assert (
        gate.classify(temp, [set()], ("safe", "", "a reason that is long enough"), needed=True)[0]
        == "SAFE"
    )
    tree = py.Site("f.py", 3, "open", "x", "TREE", [])
    assert gate.classify(tree, [set()], ("safe", "", "a reason that is long enough"))[0] == "TREE"
    assert (
        gate.classify(tree, [set()], ("mode", "--write", "regenerates the baseline"))[0]
        == "MODE-GATED"
    )
    assert (
        gate.classify(tree, [{"--write"}], ("mode", "--write", "regenerates the baseline"))[0]
        == "TREE"
    )


def test_bash_mode_flag_follows_the_parse_args_shape():
    lines = [
        'MODE="verify"',
        'if [[ "${ARG_WRITE:-}" == "true" ]]; then',
        '    MODE="write"',
        "fi",
        'if [[ "$MODE" == "write" ]]; then',
        '    } >"$MANIFEST"',
        "fi",
        'printf x >"$ROOT/y"',
    ]
    assert gate.bash_mode_flag(lines, 6) == "--write"
    assert gate.bash_mode_flag(lines, 8) is None


def test_controls_fire_both_directions():
    seen: list[tuple[str, bool]] = []
    gate.run_controls(ROOT, lambda label, cond: seen.append((label, cond)))
    failed = [label for label, ok in seen if not ok]
    assert failed == []
    assert len(seen) >= gate.SELFTEST_FLOOR - 1


def test_main_refuses_a_tree_with_no_lock(tmp_path, capsys):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}), encoding="utf-8")
    rc = gate.main(["--root", str(tmp_path), "--lock", str(tmp_path / "gone.json")])
    assert rc == 1
    assert "VACUOUS INPUT" in capsys.readouterr().err


def test_main_is_red_on_a_planted_writer_and_green_without_it(tmp_path):
    gate.build_fixture(tmp_path, ROOT)
    lock = [{"id": "w", "run": "c2/gate.py", "gate": True}]
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    res = gate.analyze(tmp_path, tmp_path / "lock.json", tmp_path / "package.json", ROOT, {})
    assert any(f.startswith("w writes the real tree") for f in res.findings)
    lock = [{"id": "w", "run": "c2m/gate.py", "gate": True}]
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    res = gate.analyze(tmp_path, tmp_path / "lock.json", tmp_path / "package.json", ROOT, {})
    assert res.findings == []
    assert res.refusals == []


def test_selftest_is_green():
    proc = subprocess.run(
        [sys.executable, str(ROOT / ".ci/scripts/quality/check_gate_tree_writes.py"), "--selftest"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "control(s) passed" in proc.stdout
