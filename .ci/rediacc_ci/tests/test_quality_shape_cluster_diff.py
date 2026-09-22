"""`.ci/scripts/quality/shape_cluster_diff.py`: a real execution route, not a manual exemption.

THE FILE WAS DEAD ON ARRIVAL, caught by `test_shadow_route_is_parsed_from_the_real_ledger` the first time the full suite ran after it was added: no gate wires it, no other module imports it, so `rediacc_ci.quality.dead_python` reported it correctly. The honest fix is not a `MANUAL_ENTRY_POINTS` entry, since that table is reserved for a script genuinely invoked another way that this
scanner's import graph cannot see (a workflow `run:` target, a differential's module-name-string dispatch) -- this script has no such invoker yet. `check_prose_style.py`'s own route is a `package.json` gate PLUS a test module that imports its engine directly; this module is the same shape for a diagnostic that has no gate of its own.

WHY NOT A GATE. The tool is a proof obligation a bulk transform attaches to itself before committing, per `agent/plans/PLAN-consolidation-pressure.md`, not a standing tree-wide check with a baseline. Running it on every CI invocation would compare the working tree to whatever `HEAD` happens to be at that moment, which is not a stable signal; it earns its keep at the moment a
transform is about to be reviewed, driven by hand or by a sub-agent, not on a schedule.
"""

import importlib.util
import pathlib

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "quality" / "shape_cluster_diff.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("shape_cluster_diff", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scd = _load()


def test_the_module_is_importable_and_exposes_its_public_surface():
    """The route this test exists to create: an IMPORT dead_python's scanner can see."""
    for name in ("shape_of", "cluster", "columns", "report", "selftest", "main"):
        assert hasattr(scd, name), "%s: expected surface missing" % name


def test_a_rule_line_banner_is_its_own_shape():
    assert scd.shape_of("----------------------------------------") == "rule-line"
    assert scd.shape_of("an ordinary sentence") == scd.PROSE


def test_the_tools_own_selftest_passes():
    """The script's `--selftest` battery, run in-process rather than as a subprocess.

    Both matter: in-process gives this test a stack trace on failure instead of a captured exit code, and it is a second, independent route on top of the plain import above.
    """
    assert scd.selftest() == 0


def test_cluster_and_columns_agree_on_a_planted_corruption():
    """The two views this tool offers, checked directly rather than only through `selftest`."""
    indented = "- item\n  continuation line\n"
    flattened = "- item\ncontinuation line\n"
    assert scd.cluster(indented)["list-cont"] == 1
    assert scd.cluster(flattened).get("list-cont", 0) == 0
    assert scd.columns(indented)[2] == 1
    assert scd.columns(flattened).get(2, 0) == 0
