"""pytest_impact: the map, the selection, the smoke floor and every FULL fallback (PLAN-ciquick-cpu W4.1).

Every fallback has a test that makes it fire, and the selection has a control that proves a leaf edit selects only its importers plus the smoke floor: a module that always answered FULL would pass every fallback test and still be useless, and one that never did would pass the control.
"""

import pathlib

import pytest

from rediacc_ci import pytest_impact as pi

ROOTS = [".ci", ".claude/hooks/stop", ".claude"]
TEST_ROOTS = [".ci/rediacc_ci/tests", ".claude/rediacc_hooks/tests"]

# A small tree in the repo's own shape: a leaf module, a module importing it, two tests that import one each, a test that names a guard script by a string literal, a smoke test, and a conftest chain.
TREE = {
    ".ci/rediacc_ci/__init__.py": "",
    ".ci/rediacc_ci/leaf.py": "X = 1\n",
    ".ci/rediacc_ci/mid.py": "from rediacc_ci import leaf\n",
    ".ci/rediacc_ci/other.py": "Y = 2\n",
    ".ci/rediacc_ci/quality/__init__.py": "",
    ".ci/rediacc_ci/quality/rel.py": "from . import sib\nfrom ..leaf import X\n",
    ".ci/rediacc_ci/quality/sib.py": "Z = 3\n",
    ".ci/rediacc_ci/tests/__init__.py": "",
    ".ci/rediacc_ci/tests/conftest.py": "import pytest\n",
    ".ci/rediacc_ci/tests/test_mid.py": "from rediacc_ci import mid\n\ndef test_a():\n    assert mid\n",
    ".ci/rediacc_ci/tests/test_other.py": "from rediacc_ci import other\n\ndef test_b():\n    assert other\n",
    ".ci/rediacc_ci/tests/test_rel.py": "from rediacc_ci.quality import rel\n\ndef test_r():\n    assert rel\n",
    ".ci/rediacc_ci/tests/test_smoke.py": "def test_s():\n    assert True\n",
    ".claude/rediacc_hooks/__init__.py": "",
    ".claude/rediacc_hooks/guards/__init__.py": "",
    ".claude/rediacc_hooks/guards/block_thing_push.py": "print('guard')\n",
    ".claude/rediacc_hooks/tests/__init__.py": "",
    ".claude/rediacc_hooks/tests/test_guard.py": (
        '"""Mentions .claude/rediacc_hooks/guards/block_other_doc.py only in prose."""\n'
        "GUARD = 'guards/block_thing_push.py'\n\n"
        "def test_g():\n    assert GUARD\n"
    ),
    ".claude/rediacc_hooks/guards/block_other_doc.py": "print('other')\n",
    "conftest.py": "",
}
# Fillers so the leaf control (3 files) sits under the 40% ceiling and a two-module edit (4 files) sits over it.
for _i in range(4):
    TREE[".ci/rediacc_ci/tests/test_filler%d.py" % _i] = "def test_f():\n    assert True\n"
TESTS = sorted(p for p in TREE if pi.is_test_file(p, TEST_ROOTS))
SMOKE = [".ci/rediacc_ci/tests/test_smoke.py"]


def build(tree=None):
    tree = dict(TREE if tree is None else tree)
    return pi.build_map(
        pathlib.Path("/nonexistent"),
        sorted(p for p in tree if p.endswith(".py")),
        ROOTS,
        TEST_ROOTS,
        read=tree.__getitem__,
    )


def policy(smoke=None, reads=None):
    return {"smoke": {"files": list(SMOKE if smoke is None else smoke)}, "reads": dict(reads or {})}


def run(changed, impact_map=None, pol=None, tree=None):
    tree = TREE if tree is None else tree
    return pi.select(
        changed,
        build(tree) if impact_map is None else impact_map,
        policy() if pol is None else pol,
        existing=frozenset(tree),
        test_roots=TEST_ROOTS,
        digest="d" * 64,
    )


# --------------------------------------------------------------------------- the map


def test_the_closure_follows_imports_transitively_and_holds_the_conftest_chain():
    m = build()
    closure = m["tests"][".ci/rediacc_ci/tests/test_mid.py"]["closure"]
    assert ".ci/rediacc_ci/mid.py" in closure
    assert ".ci/rediacc_ci/leaf.py" in closure, "the transitive import was not followed"
    assert ".ci/rediacc_ci/tests/conftest.py" in closure
    assert "conftest.py" in closure
    assert ".ci/rediacc_ci/other.py" not in closure, (
        "CONTROL: an unimported module joined the closure"
    )


def test_relative_imports_resolve_both_levels():
    closure = build()["tests"][".ci/rediacc_ci/tests/test_rel.py"]["closure"]
    assert ".ci/rediacc_ci/quality/sib.py" in closure
    assert ".ci/rediacc_ci/leaf.py" in closure


def test_a_third_party_import_is_not_unresolved_but_a_missing_local_one_is():
    tree = dict(TREE)
    tree[".ci/rediacc_ci/tests/test_mid.py"] = (
        "import pytest\nimport yaml\nfrom rediacc_ci import mid\n"
    )
    assert all(not e["unresolved"] for e in build(tree)["tests"].values())
    tree[".ci/rediacc_ci/tests/test_mid.py"] = (
        "from rediacc_ci import gone_module\nimport rediacc_ci.nothere\n"
    )
    unresolved = build(tree)["tests"][".ci/rediacc_ci/tests/test_mid.py"]["unresolved"]
    assert any("rediacc_ci.nothere" in u for u in unresolved), unresolved


def test_docstrings_are_not_literals():
    lits = build()["tests"][".claude/rediacc_hooks/tests/test_guard.py"]["literals"]
    assert "guards/block_thing_push.py" in lits
    assert not any("block_other_doc" in lit for lit in lits), lits


# --------------------------------------------------------------------------- selection: the control


def test_a_leaf_edit_selects_only_its_importers_plus_smoke():
    sel = run([".ci/rediacc_ci/leaf.py"])
    assert sel.scope == "impact", sel.line()
    assert sel.files == sorted(
        [".ci/rediacc_ci/tests/test_mid.py", ".ci/rediacc_ci/tests/test_rel.py", *SMOKE]
    ), sel.files
    assert ".ci/rediacc_ci/tests/test_other.py" not in sel.files
    assert sel.line().startswith("pytest-impact: IMPACT 3 of 9")


def test_a_guard_named_by_a_literal_selects_the_test_that_names_it():
    sel = run([".claude/rediacc_hooks/guards/block_thing_push.py"])
    assert sel.scope == "impact", sel.line()
    assert ".claude/rediacc_hooks/tests/test_guard.py" in sel.files


def test_a_changed_test_file_is_selected():
    sel = run([".ci/rediacc_ci/tests/test_other.py"])
    assert sel.scope == "impact"
    assert ".ci/rediacc_ci/tests/test_other.py" in sel.files


def test_the_reads_table_covers_a_data_file():
    pol = policy(reads={".ci/rediacc_ci/tests/test_other.py": [".ci/policy/thing-*.json"]})
    tree = dict(TREE, **{".ci/policy/thing-a.json": "{}"})
    sel = run([".ci/policy/thing-a.json"], pol=pol, tree=tree)
    assert sel.scope == "impact", sel.line()
    assert sel.why[".ci/rediacc_ci/tests/test_other.py"].endswith("(policy)")


def test_a_file_outside_the_gate_paths_is_listed_not_judged():
    sel = run(["docs/readme.md", ".ci/rediacc_ci/other.py"])
    assert sel.scope == "impact"
    assert sel.outside == ["docs/readme.md"]


# --------------------------------------------------------------------------- every FULL fallback


@pytest.mark.parametrize(
    "path",
    [
        ".ci/rediacc_ci/tests/conftest.py",
        "conftest.py",
        "pyproject.toml",
        "uv.lock",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        ".ci/rediacc_ci/check_pytest.py",
        ".ci/rediacc_ci/pytest_impact.py",
        ".ci/policy/pytest-impact.json",
    ],
)
def test_full_when_pytest_config_changed(path):
    sel = run([path])
    assert sel.scope == "full", sel.line()
    assert path in sel.reason, sel.line()
    assert sel.line() == "pytest-impact: FULL (%s changed)" % path


def test_full_on_an_unresolved_import():
    tree = dict(TREE)
    tree[".ci/rediacc_ci/mid.py"] = (
        "from rediacc_ci import leaf\nimport rediacc_ci.deleted_module\n"
    )
    sel = run([".ci/rediacc_ci/other.py"], tree=tree)
    assert sel.scope == "full", sel.line()
    assert "unresolved import" in sel.reason, sel.line()


def test_full_on_a_changed_file_no_test_covers():
    tree = dict(TREE, **{".ci/rediacc_ci/orphan_mod.py": "Q = 1\n"})
    sel = run([".ci/rediacc_ci/orphan_mod.py"], tree=tree)
    assert sel.scope == "full", sel.line()
    assert "no test imports it" in sel.reason, sel.line()


def test_full_on_an_uncovered_data_file_under_claude():
    tree = dict(TREE, **{".claude/settings-fixture.json": "{}"})
    sel = run([".claude/settings-fixture.json"], tree=tree)
    assert sel.scope == "full", sel.line()


def test_a_docstring_mention_does_not_cover_a_file():
    sel = run([".claude/rediacc_hooks/guards/block_other_doc.py"])
    assert sel.scope == "full", "a prose mention covered a file: %s" % sel.line()


def test_full_above_forty_percent():
    sel = run([".ci/rediacc_ci/leaf.py", ".ci/rediacc_ci/other.py"])
    assert sel.scope == "full", sel.line()
    assert "above 40%" in sel.reason, sel.line()


def test_full_on_a_missing_map():
    sel = pi.select(
        [".ci/rediacc_ci/leaf.py"], None, policy(), existing=frozenset(TREE), test_roots=TEST_ROOTS
    )
    assert sel.scope == "full"
    assert sel.reason == "missing map"


def test_full_on_an_empty_map():
    sel = run(
        [".ci/rediacc_ci/leaf.py"], impact_map={"schema": pi.MAP_SCHEMA, "tests": {}, "errors": []}
    )
    assert sel.scope == "full"
    assert "no test files" in sel.reason


def test_full_on_a_module_that_does_not_parse():
    tree = dict(TREE, **{".ci/rediacc_ci/mid.py": "def broken(:\n"})
    sel = run([".ci/rediacc_ci/other.py"], tree=tree)
    assert sel.scope == "full", sel.line()
    assert "could not parse" in sel.reason, sel.line()


def test_full_on_a_missing_policy():
    sel = pi.select(
        [".ci/rediacc_ci/leaf.py"], build(), None, existing=frozenset(TREE), test_roots=TEST_ROOTS
    )
    assert sel.scope == "full"
    assert pi.POLICY_RELPATH in sel.reason


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"reads": {}}',
        '{"smoke": {"files": []}, "reads": {}}',
        '{"smoke": {"files": ["a"]}, "reads": []}',
    ],
)
def test_a_malformed_policy_is_refused(text):
    data, problem = pi.load_policy(text)
    assert data is None
    assert problem


def test_a_wellformed_policy_loads():
    data, problem = pi.load_policy('{"smoke": {"files": ["a.py"]}, "reads": {"x": ["y"]}}')
    assert problem is None
    assert data["smoke"]["files"] == ["a.py"]


def test_full_when_a_smoke_file_is_missing():
    sel = run([".ci/rediacc_ci/leaf.py"], pol=policy(smoke=[".ci/rediacc_ci/tests/test_gone.py"]))
    assert sel.scope == "full"
    assert "smoke floor" in sel.reason


def test_full_when_no_push_base_resolves():
    sel = run(None)
    assert sel.scope == "full"
    assert "push base" in sel.reason


# --------------------------------------------------------------------------- literal coverage


@pytest.mark.parametrize(
    ("literal", "rel", "want"),
    [
        (".claude/hooks/stop/wl_git.py", ".claude/hooks/stop/wl_git.py", True),
        ("./.claude/hooks/stop/wl_git.py", ".claude/hooks/stop/wl_git.py", True),
        ("stop/wl_git.py", ".claude/hooks/stop/wl_git.py", True),
        ("wl_git.py", ".claude/hooks/stop/wl_git.py", True),
        ("op/wl_git.py", ".claude/hooks/stop/wl_git.py", False),
        (
            "block_vm_unverified_push",
            ".claude/rediacc_hooks/guards/block_vm_unverified_push.py",
            True,
        ),
        ("terminal", ".claude/skills/rdc/terminal.md", False),
        ("wl_x", ".claude/hooks/stop/wl_x.py", False),
        ("test-*.py", ".claude/hooks/stop/test-adhoc-watch.py", True),
        ("*.py", ".claude/hooks/stop/test-adhoc-watch.py", False),
        (".ci/policy/*.json", ".ci/policy/carry-exempt.json", True),
        (".ci/policy", ".ci/policy/carry-exempt.json", True),
        (".ci/rediacc_ci/tests", ".ci/rediacc_ci/tests/fixtures/x.json", False),
        ("*", ".ci/policy/carry-exempt.json", False),
    ],
)
def test_literal_covers_and_its_index_agree(literal, rel, want):
    files = [rel, ".ci/policy/other.json", ".ci/rediacc_ci/tests/test_a.py"]
    dirs = pi.tracked_dirs_of(files, TEST_ROOTS)
    assert pi.literal_covers(literal, rel, dirs) is want
    assert pi.LiteralIndex([literal]).covers(rel, dirs) is want


def test_a_directory_with_too_many_files_covers_nothing():
    files = ["big/dir/f%d.json" % i for i in range(pi.MAX_DIR_FILES + 1)]
    dirs = pi.tracked_dirs_of(files)
    assert "big/dir" not in dirs
    assert not pi.literal_covers("big/dir", files[0], dirs)
    assert "big/dir" in pi.tracked_dirs_of(files[: pi.MAX_DIR_FILES]), (
        "CONTROL: a small directory was dropped too"
    )


def test_literal_tokens_split_a_command_line():
    toks = pi.literal_tokens("python3 `.claude/hooks/stop/worklist.py` --roundlog x.")
    assert ".claude/hooks/stop/worklist.py" in toks
    assert "x" not in toks


# --------------------------------------------------------------------------- push base


def fake_git(refs: dict[str, str], abbrev: dict[str, str], bases: dict[str, str]):
    def git(args):
        if args[:3] == ["rev-parse", "--verify", "--quiet"]:
            return refs.get(args[3].removesuffix("^{commit}"))
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return abbrev.get(args[2])
        if args[:2] == ["merge-base", "HEAD"]:
            return bases.get(args[2])
        return None

    return git


def test_push_base_prefers_push_then_skips_a_foreign_upstream():
    git = fake_git(
        {"@{push}": "a", "@{upstream}": "b", "origin/main": "c"},
        {"@{push}": "origin/1104-1", "@{upstream}": "origin/0930-1"},
        {"@{push}": "mb-push", "@{upstream}": "mb-up", "origin/main": "mb-main"},
    )
    assert pi.resolve_push_base(git, "1104-1") == "mb-push"
    foreign = fake_git(
        {"@{push}": "a", "@{upstream}": "b", "origin/main": "c"},
        {"@{push}": "origin/0930-1", "@{upstream}": "origin/0930-1"},
        {"@{push}": "mb-push", "@{upstream}": "mb-up", "origin/main": "mb-main"},
    )
    assert pi.resolve_push_base(foreign, "1104-1") == "mb-main"


def test_push_base_is_none_when_nothing_resolves():
    assert pi.resolve_push_base(fake_git({}, {}, {}), "1104-1") is None


# --------------------------------------------------------------------------- the smoke floor


JUNIT = """<testsuites><testsuite>
<testcase classname=".ci.rediacc_ci.tests.test_mid" name="a" time="0.2"/>
<testcase classname=".ci.rediacc_ci.tests.test_mid.TestK" name="b" time="0.1"/>
<testcase classname=".ci.rediacc_ci.tests.test_other" name="c" time="5.0"/>
<testcase classname=".ci.rediacc_ci.tests.test_rel" name="d" time="0.3"/>
<testcase classname=".ci.rediacc_ci.tests.test_smoke" name="e" time="0.01"/>
<testcase classname="unknown.module" name="f" time="1.0"/>
</testsuite></testsuites>"""


def test_junit_times_map_classnames_to_files():
    times = pi.junit_file_times(JUNIT, TESTS)
    assert times[".ci/rediacc_ci/tests/test_mid.py"][0] == 2
    assert times[".ci/rediacc_ci/tests/test_other.py"][2] == 5.0
    assert len(times) == 4


def test_derive_smoke_covers_units_with_fast_files_only():
    m = build()
    files, unreached = pi.derive_smoke(m, pi.junit_file_times(JUNIT, TESTS), TEST_ROOTS)
    assert ".ci/rediacc_ci/tests/test_other.py" not in files, "a 5 s test joined the smoke floor"
    assert ".ci/rediacc_ci/other" in unreached, (
        "the slow file's only unit must be reported unreached"
    )
    assert ".ci/rediacc_ci/mid" not in unreached
    assert ".ci/rediacc_ci/leaf" not in unreached
    assert files, "CONTROL: nothing was chosen at all"


def test_unit_of():
    assert pi.unit_of(".ci/rediacc_ci/quality/x.py", TEST_ROOTS) == ".ci/rediacc_ci/quality"
    assert pi.unit_of(".ci/rediacc_ci/gitx.py", TEST_ROOTS) == ".ci/rediacc_ci/gitx"
    assert pi.unit_of(".claude/hooks/stop/wl_git.py", TEST_ROOTS) == ".claude/hooks/stop"
    assert pi.unit_of(".ci/rediacc_ci/tests/helpers.py", TEST_ROOTS) is None
    assert pi.unit_of(".ci/rediacc_ci/__init__.py", TEST_ROOTS) is None


def test_the_committed_policy_loads_and_names_real_test_files():
    root = pathlib.Path(__file__).resolve().parents[3]
    data, problem = pi.load_policy((root / pi.POLICY_RELPATH).read_text(encoding="utf-8"))
    assert problem is None, problem
    for rel in data["smoke"]["files"]:
        assert (root / rel).is_file(), "smoke floor names a missing file: %s" % rel
        assert pi.is_test_file(rel, pi.testpath_roots(root)), rel
