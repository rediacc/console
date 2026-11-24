"""The guard test tables live in `tests/guard_cases/`, and every reader still finds them on the guard module (PLAN-tooling-code-reduction CR5).

Both directions: a forwarded name must resolve to the table's own object (without `guards.tables` that read is an AttributeError, and the differential would quietly see no EDGE_CASES at all), and a hook call must import NO table (the point of the move is that the hot path stops loading test data).
"""

import ast
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks import guards
from rediacc_hooks.guards import _write_rules

HOOKS = pathlib.Path(__file__).resolve().parents[1]
TABLES = HOOKS / "tests" / "guard_cases"
TABLE_STEMS = sorted(p.stem for p in TABLES.glob("*.py") if not p.name.startswith("_"))


def _forwarded(stem):
    """The names a guard's `tables(...)` line forwards, read from its source."""
    tree = ast.parse((guards.HERE / ("%s.py" % stem)).read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__getattr__" for t in node.targets)
            and isinstance(node.value, ast.Call)
        ):
            args = [a.value for a in node.value.args if isinstance(a, ast.Constant)]
            assert args[:1] == [stem], "%s forwards from the table of %r" % (stem, args[:1])
            return args[1:]
    return None


def test_the_table_set_is_not_empty():
    """Anti-vacuity: the parametrized checks below over zero tables would pass over nothing."""
    assert len(TABLE_STEMS) >= 50, "only %d guard table(s) found under %s" % (
        len(TABLE_STEMS),
        TABLES,
    )


@pytest.mark.parametrize("stem", TABLE_STEMS)
def test_every_forwarded_name_resolves_to_the_tables_object(stem):
    assert stem in guards.stems(), "tests/guard_cases/%s.py names no guard" % stem
    names = _forwarded(stem)
    assert names, '%s has a table file but no `__getattr__ = tables("<stem>", ...)` line' % stem
    assert "EDGE_CASES" in names or "FIXTURES" in names or "ENVS" in names
    module = guards.load(stem)
    table = __import__("%s.%s" % (guards.TABLES, stem), fromlist=["_"])
    for name in names:
        assert name not in vars(module), "%s still defines %s inline" % (stem, name)
        assert getattr(module, name) is getattr(table, name), "%s.%s" % (stem, name)


def test_an_unlisted_name_is_an_attribute_error_and_imports_nothing():
    """CONTROL for the listing: an attribute the line does not name must not reach the table."""
    probe = (
        "import sys\n"
        "from rediacc_hooks import guards\n"
        "m = guards.load('block_git_amend')\n"
        "assert not hasattr(m, 'OWN_SUITE')\n"
        "assert not hasattr(m, 'datetime')\n"
        "print(sorted(k for k in sys.modules if '.guard_cases' in k))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(HOOKS.parent),
    ).stdout
    assert json.loads(out.replace("'", '"')) == []


def test_a_chain_run_imports_no_table():
    """SILENT CONTROL: the hot path. Every chain loads every guard; none may load test data."""
    probe = (
        "import json, sys\n"
        "from rediacc_hooks import dispatch, guards\n"
        "for chain in guards.CHAINS:\n"
        "    dispatch.run_chain(chain, json.dumps({'tool_input': {'command': 'true'}}))\n"
        "print(json.dumps(sorted(k for k in sys.modules if '.guard_cases' in k)))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(HOOKS.parent),
    )
    assert proc.stdout.strip(), proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_a_forwarded_read_does_import_the_table():
    """The positive half of the control above: the probe can see a table import when one happens."""
    probe = (
        "import json, sys\n"
        "from rediacc_hooks import guards\n"
        "assert guards.load('block_git_amend').EDGE_CASES\n"
        "print(json.dumps(sorted(k for k in sys.modules if '.guard_cases' in k)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(HOOKS.parent),
    ).stdout
    assert json.loads(out) == [
        "rediacc_hooks.tests.guard_cases",
        guards.TABLES + ".block_git_amend",
    ]


def test_no_guard_regrows_an_inline_table_except_the_clock_readers():
    """An inline table is allowed only where the differential re-executes the module under a frozen clock (`edge_cases()` in test_guards_differential.py reads `EDGE_CASES` out of the re-run module body)."""
    inline = []
    for stem in guards.stems():
        tree = ast.parse((guards.HERE / ("%s.py" % stem)).read_text(encoding="utf-8"))
        names = {
            t.id
            for n in tree.body
            if isinstance(n, (ast.Assign, ast.AnnAssign))
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
            if isinstance(t, ast.Name)
        }
        clock = any(
            isinstance(n, ast.Import) and any(a.name == "datetime" for a in n.names)
            for n in tree.body
        )
        if names & {"EDGE_CASES", "FIXTURES", "ENVS"} and not clock:
            inline.append(stem)
    assert inline == [], (
        "these guards define a test table inline; put it in tests/guard_cases/<stem>.py "
        'and forward it with `__getattr__ = tables("<stem>", ...)`: %s' % inline
    )


def _load_ledger_shell_guard():
    spec = importlib.util.spec_from_file_location(
        "ledger_shell_write_under_test", guards.HERE / "block_live_proof_ledger_shell_write.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ledger_shell_guard_refuses_to_load_on_a_row_with_no_path(monkeypatch):
    """Review 6453becc.2: a ROWS row with no path must stop the import, not leave a None ledger path."""
    rows = dict(_write_rules.ROWS)
    rows["live_proof_ledger"] = rows["live_proof_ledger"]._replace(path=None)
    monkeypatch.setattr(_write_rules, "ROWS", rows)
    with pytest.raises(RuntimeError, match="names no path"):
        _load_ledger_shell_guard()


def test_control_ledger_shell_guard_loads_on_the_real_row():
    assert _load_ledger_shell_guard().LEDGER_PATH is not None
