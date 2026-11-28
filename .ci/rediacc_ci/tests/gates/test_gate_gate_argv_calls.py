"""registered_calls collects a call whose flag is not its first argument, and still skips prose."""

import json

from rediacc_ci.quality import gate_argv


def _root(tmp_path, workflow_text, scripts=None):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text(workflow_text)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts or {}}))
    return tmp_path


def test_a_flag_after_a_value_is_collected(tmp_path):
    root = _root(tmp_path, "run: python .ci/scripts/quality/check_x.py value --undeclared\n")
    calls = [c for c in gate_argv.registered_calls(root) if c[0].startswith(".github")]
    assert [(c[1], c[2]) for c in calls] == [("check_x", ["value", "--undeclared"])]


def test_an_npm_call_with_a_value_before_the_flag_is_collected(tmp_path):
    root = _root(
        tmp_path,
        "run: npm run check:x -- value --undeclared\n",
        {"check:x": "python3 .ci/scripts/quality/check_x.py --known"},
    )
    calls = [c for c in gate_argv.registered_calls(root) if c[0].startswith(".github")]
    assert [(c[1], c[2]) for c in calls] == [("check_x", ["--known", "value", "--undeclared"])]


def test_prose_naming_an_entry_point_is_not_a_call(tmp_path):
    root = _root(tmp_path, "# .ci/scripts/quality/check_x.py holds in place.\n")
    assert gate_argv.registered_calls(root) == []
