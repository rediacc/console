"""`rediacc_ci.quality.ci_gate_prerequisites` predicate builder: the predicate it returns is a one-argument callable, the shape `Resource.needs` declares."""

import re

from rediacc_ci.quality import ci_gate_prerequisites as CGP


def test_the_builder_declares_the_one_argument_predicate_resource_needs_takes():
    """`Callable[..., bool]` dropped the arity check mypy applies to the returned predicate (per-commit review 6f8d9da5.1)."""
    ret = str(CGP._needs_via_run_pattern.__annotations__["return"])
    assert ret.replace("collections.abc.", "") == "Callable[[str], bool]"
    assert str(CGP.Resource.__annotations__["needs"]).replace("collections.abc.", "") == ret


def test_the_predicate_matches_command_text_with_one_argument():
    needs = CGP._needs_via_run_pattern(re.compile(r"^\s*widget\b", re.MULTILINE))
    assert needs("widget --go") is True
    assert needs("echo widget") is False
