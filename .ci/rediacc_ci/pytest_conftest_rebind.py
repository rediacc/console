"""Give EVERY collector pytest builds for a directory the fixtures of that directory's conftest, not only the first one.

THE DEFECT, IN PYTEST 9.1.1 ITSELF. A conftest's fixtures are bound to a NODE, not to a path. `FixtureManager.pytest_plugin_registered` parks the conftest in `_pending_conftests[dir]`, and `FixtureManager.pytest_make_collect_report` (`_pytest/fixtures.py:1800`) POPS it when the first `Directory` collector for `dir` finishes, calling `parsefactories(node=that collector)`. Lookup then
matches by identity, `fixturedef.node in parent_nodes` (`_pytest/fixtures.py:2165`). A second collector object for the same directory finds nothing pending, binds nothing, and every test under it fails setup with "fixture 'gate' not found".

WHEN PYTEST BUILDS THAT SECOND OBJECT. `Session.collect` (`_pytest/main.py:950`) collects a directory with `handle_dupes=False` when a command-line FILE sits directly in it, which re-runs `collect()` and replaces every child collector with a new object. So `gates/a.py tests/b.py gates/c.py` binds `gate` to the first `<Package gates>`, re-collects `<Package tests>` for `tests/b.py`, and walks
into a fresh `<Package gates>` for `gates/c.py`: `--co` prints two `<Package gates>` nodes, and the second has no `gate`. A run over directories (the gate, `npm run check:ci-pytest`) never passes a file, which is why the full suite was green while a hand-picked file list was red (worklist #6b5becd7).

THE REPAIR. After any `Directory` collector is collected, if its directory holds a registered conftest and an EARLIER collector for that directory already received it, parse the conftest's fixtures onto this one too. The first collector is left to pytest, so a run that never re-collects is untouched. Fixture scope stays node-scoped: a package-scoped fixture under two collector objects is two
packages to pytest, which is what it already believed.

THE CONTROL. `.ci/rediacc_ci/tests/test_pytest_conftest_rebind.py` runs the failing file order with this plugin BLOCKED and requires the error, so the day pytest fixes the defect upstream that test goes red and says to delete this module, rather than the shim living on as dead weight nobody can prove is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: directory -> the first collector seen for it, per Config (a nested pytester run gets its own).
_FIRST = pytest.StashKey[dict[Path, pytest.Collector]]()


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector: pytest.Collector):
    report = yield
    if isinstance(collector, pytest.Directory):
        _rebind(collector)
    return report


def _rebind(collector: pytest.Directory) -> None:
    config = collector.config
    plugin = config.pluginmanager.get_plugin(str(collector.path / "conftest.py"))
    if plugin is None:
        return
    first = config.stash.setdefault(_FIRST, {}).setdefault(collector.path, collector)
    if first is collector:
        return
    manager = config.pluginmanager.get_plugin("funcmanage")
    if manager is None:
        raise pytest.UsageError(
            "rediacc_ci.pytest_conftest_rebind: pytest registers no 'funcmanage' plugin, so "
            "%s cannot be re-bound to the second collector for %s. pytest's fixture internals "
            "changed; re-read _pytest/fixtures.py and check whether the defect this module "
            "repairs still exists." % (collector.path / "conftest.py", collector.path)
        )
    manager.parsefactories(holder=plugin, node=collector)
