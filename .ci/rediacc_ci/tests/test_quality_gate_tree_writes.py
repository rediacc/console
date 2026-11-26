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


def test_a_runner_file_variable_is_outside_and_an_arbitrary_key_is_not(tmp_path):
    """Both directions: the step summary through an injected env mapping is OUTSIDE, any other key on the same mapping stays UNRESOLVED."""
    sites = scan(
        tmp_path,
        {
            "g.py": "import os\n\n\ndef run(env):\n"
            "    with open(env.get('GITHUB_STEP_SUMMARY'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(env.get('REVIEW_OUT'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(os.environ.get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n\n\n"
            "run(os.environ)\n"
        },
        "g.py",
    )
    assert [s.origin for s in sorted(sites, key=lambda s: s.line)] == [
        "OUTSIDE",
        "UNRESOLVED",
        "OUTSIDE",
    ]


def test_a_runner_variable_key_on_a_non_environment_mapping_is_still_unresolved(tmp_path):
    """Review aae50fd5.1: only an environment-named receiver is trusted; a plain dict under the same key stays UNRESOLVED."""
    sites = scan(
        tmp_path,
        {
            "g.py": "def run(cfg, env):\n"
            "    with open(cfg.get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(env.get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n\n\n"
            "run({}, {})\n"
        },
        "g.py",
    )
    assert [s.origin for s in sorted(sites, key=lambda s: s.line)] == ["UNRESOLVED", "OUTSIDE"]


def test_a_copy_of_the_environment_is_still_an_environment_receiver(tmp_path):
    """Review 239e74cb.1: `os.environ.copy().get(...)` and `dict(os.environ).get(...)` read the environment; a copy of a plain dict does not."""
    sites = scan(
        tmp_path,
        {
            "g.py": "import os\n\n\ndef run(cfg):\n"
            "    with open(os.environ.copy().get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(dict(os.environ).get('GITHUB_ENV'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(cfg.copy().get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n"
            "    with open(dict(cfg).get('GITHUB_OUTPUT'), 'a') as fh:\n        fh.write('x')\n\n\n"
            "run({})\n"
        },
        "g.py",
    )
    assert [s.origin for s in sorted(sites, key=lambda s: s.line)] == [
        "OUTSIDE",
        "OUTSIDE",
        "UNRESOLVED",
        "UNRESOLVED",
    ]


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
    # A write two flags reach names both, and turns red when EITHER is registered.
    both = ("mode", "--write|--init", "writes or seeds the baseline")
    assert gate.classify(tree, [set()], both)[0] == "MODE-GATED"
    assert gate.classify(tree, [{"--init"}], both)[0] == "TREE"
    assert gate.classify(tree, [{"--write"}], both)[0] == "TREE"
    m = gate.MODE_RE.match("--write|--init writes or seeds the baseline")
    assert m is not None
    assert m.group(1) == "--write|--init"


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


def test_a_refusal_names_the_module_a_reader_can_run(tmp_path, capsys):
    """Review finding db7749af.5: the twin `check-gate-tree-writes.sh` is deleted, so a refusal is prefixed with the module that prints it. Control first: the same fixture with a list-shaped lock prints no "not a JSON list" refusal, so the line below is the planted shape's alone."""
    gate.build_fixture(tmp_path, ROOT)
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(
        json.dumps([{"id": "w", "run": "c2m/gate.py", "gate": True}]), encoding="utf-8"
    )
    gate.main(["--root", str(tmp_path), "--lock", str(lock_path)])
    assert "is not a JSON list" not in capsys.readouterr().err
    lock_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert gate.main(["--root", str(tmp_path), "--lock", str(lock_path)]) == 1
    err = capsys.readouterr().err
    assert (
        "rediacc_ci.quality.gate_tree_writes: refusing to pass: the gate lock at %s is not a JSON list"
        % lock_path
        in err
    ), err
    assert "check-gate-tree-writes" not in err


def _verdicts(tmp_path: pathlib.Path, run: str) -> gate.Result:
    gate.build_fixture(tmp_path, ROOT)
    lock = [{"id": "w", "run": run, "gate": True}]
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return gate.analyze(tmp_path, tmp_path / "lock.json", tmp_path / "package.json", ROOT, {})


def test_callers_pragma_exempts_only_the_listed_referrer(tmp_path):
    """Review finding 160a24a5.1. Control: `cw/lib.py` lists its one referrer and is green. Plant: `cwm/lib.py` has the same shape but a second module (`cwm/bad.py`) references `put`, so the site is judged as a tree write again, for the listed entry too."""
    control = _verdicts(tmp_path, "cw/ok.py")
    assert control.findings == []
    assert sorted(v.bucket for v in control.verdicts) == ["DECLARED"]
    planted = _verdicts(tmp_path, "cwm/ok.py")
    assert any("cwm/bad.py" in f and "does not list" in f for f in planted.findings), (
        planted.findings
    )
    assert any("UNRESOLVED" in f for f in planted.findings)


def test_a_safe_pragma_still_exempts_every_referrer(tmp_path):
    """The old `safe` form on the same function is green whoever references it, which is why env_doc.write no longer uses it: this pins the hole the `callers` form closes."""
    gate.build_fixture(tmp_path, ROOT)
    lib = tmp_path / "cwm" / "lib.py"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace(
            "tree-write: callers cwm/ok.py", "tree-write: safe"
        ),
        encoding="utf-8",
    )
    lock = [{"id": "w", "run": "cwm/ok.py", "gate": True}]
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    res = gate.analyze(tmp_path, tmp_path / "lock.json", tmp_path / "package.json", ROOT, {})
    assert res.findings == []


def test_a_listed_file_that_stopped_referencing_is_a_bad_pragma(tmp_path):
    res = _verdicts(tmp_path, "cws/ok.py")
    assert any("BAD-PRAGMA" in f and "cws/gone.py" in f for f in res.findings), res.findings


def test_env_doc_write_is_exempt_for_exactly_the_two_registry_writers():
    """The real tree: the referrers of env_doc.write are the two writer verbs, and every tree-write pragma in env_doc.py is the `callers` form."""
    files, fn = gate.referrers(ROOT, ".ci/rediacc_ci/quality/env_doc.py", 80)
    assert fn == "write"
    assert files == [
        ".ci/rediacc_ci/quality/env_register.py",
        ".ci/rediacc_ci/quality/python_env_registry.py",
    ]
    text = (ROOT / ".ci/rediacc_ci/quality/env_doc.py").read_text(encoding="utf-8")
    pragmas = [ln for ln in text.splitlines() if "tree-write:" in ln]
    assert len(pragmas) == 4
    assert all("tree-write: callers " in ln for ln in pragmas)


def _referrer_tree(tmp_path: pathlib.Path) -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/lib.py": "def put(x):\n    return x\n",
        "unparsed.py": "def (:\nput(1)\n",
        "dotted.py": "import pkg.lib\npkg.lib.put(1)\n",
        "star.py": "from pkg.lib import *\nput(2)\n",
        "quiet.py": "x = 1\n",
    }
    for rel, body in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def test_referrers_count_an_undecodable_file_and_an_unreadable_one(tmp_path):
    """Reviews 47fc6711.1/.2/.3: a file with undecodable bytes that names the function is a referrer, a file that cannot be read at all is one too (it cannot be cleared), and a decodable one that never names it is not."""
    _referrer_tree(tmp_path)
    (tmp_path / "binary.py").write_bytes(b"\xff\xfe put(3)\n")
    (tmp_path / "binary_quiet.py").write_bytes(b"\xff\xfe nothing here\n")
    (tmp_path / "dangling.py").symlink_to(tmp_path / "no-such-target.py")
    files, _fn = gate.referrers(tmp_path, "pkg/lib.py", 2)
    assert "binary.py" in files
    assert "binary_quiet.py" not in files
    assert "dangling.py" in files


def test_a_stale_pragma_message_names_the_pragma_kind():
    """Review 47fc6711.4: the STALE text carries the kind of the pragma it judges, `safe` or `callers`."""
    temp = py.Site("f.py", 3, "open", "x", "TEMP", [])
    reason = "a reason that is long enough"
    assert gate.classify(temp, [set()], ("safe", "", reason)) == (
        "STALE",
        "a `safe` pragma on a site the scanner resolves as TEMP",
    )
    assert gate.classify(temp, [set()], ("callers", "a.py", reason)) == (
        "STALE",
        "a `callers` pragma on a site the scanner resolves as TEMP",
    )


def test_referrers_count_an_unparseable_file_a_dotted_import_and_a_star_import(tmp_path):
    """Reviews 8a37ddf8.1 and .2: each of the three shapes is a referrer; the file that never names the function is not."""
    _referrer_tree(tmp_path)
    files, fn = gate.referrers(tmp_path, "pkg/lib.py", 2)
    assert fn == "put"
    assert files == ["dotted.py", "star.py", "unparsed.py"]
