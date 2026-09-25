"""`.ci/scripts/quality/shape_cluster_diff.py`: a real execution route, not a manual exemption.

THE FILE WAS DEAD ON ARRIVAL, caught by `test_shadow_route_is_parsed_from_the_real_ledger` the first time the full suite ran after it was added: no gate wires it, no other module imports it, so `rediacc_ci.quality.dead_python` reported it correctly. The honest fix is not a `MANUAL_ENTRY_POINTS` entry, since that table is reserved for a script genuinely invoked another way that this
scanner's import graph cannot see (a workflow `run:` target, a differential's module-name-string dispatch) -- this script has no such invoker yet. `check_prose_style.py`'s own route is a `package.json` gate PLUS a test module that imports its engine directly; this module is the same shape for a diagnostic that has no gate of its own.

WHY NOT A GATE. The tool is a proof obligation a bulk transform attaches to itself before committing, per `agent/plans/PLAN-consolidation-pressure.md`, not a standing tree-wide check with a baseline. Running it on every CI invocation would compare the working tree to whatever `HEAD` happens to be at that moment, which is not a stable signal; it earns its keep at the moment a
transform is about to be reviewed, driven by hand or by a sub-agent, not on a schedule.
"""

import importlib.util
import json
import pathlib
import subprocess

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


# ---- JSON key-path mode (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.4) ----------------
# Every fire case has an inverse differing by one fact. The tool runs for real: a throwaway git repo, a committed locale file, a working-tree edit, and `main()` against `--rev HEAD`.

LOCALE = "packages/cli/src/i18n/locales/de/cli.json"
LOCALE_BEFORE = {"commands": {"up": {"help": "Hoch"}, "down": {"help": "Runter"}}, "count": 2}


def _repo(tmp_path, monkeypatch, files):
    monkeypatch.chdir(tmp_path)
    run = lambda *argv: subprocess.run(argv, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.invalid")
    run("git", "config", "user.name", "t")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "base")


def _edit(tmp_path, rel, text):
    (tmp_path / rel).write_text(text, encoding="utf-8")


def _run_json(capsys, *paths):
    code = scd.main(["--rev", "HEAD", "--json", *paths])
    return code, json.loads(capsys.readouterr().out)


def test_a_removed_locale_key_is_named_and_exits_1(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    after = json.loads(json.dumps(LOCALE_BEFORE))
    del after["commands"]["down"]
    _edit(tmp_path, LOCALE, json.dumps(after, indent=2))
    code, out = _run_json(capsys, "packages/cli/src/i18n/locales")
    assert code == 1
    assert out["findings"][0]["keys"]["removed"] == ["commands.down", "commands.down.help"]


def test_inverse_a_reformat_that_collapses_lines_removes_no_key(tmp_path, monkeypatch, capsys):
    """The one fact that differs: every key survives. Line shapes would call the collapse a loss of 7 `prose` lines; key paths see none."""
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    _edit(tmp_path, LOCALE, json.dumps(LOCALE_BEFORE))
    code, out = _run_json(capsys, "packages/cli/src/i18n/locales")
    assert code == 0, out
    assert out["findings"] == []
    assert out["summary"]["files_compared"] == 1


def test_an_added_key_and_a_type_change_are_reported_without_failing(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    after = json.loads(json.dumps(LOCALE_BEFORE))
    after["commands"]["up"]["hint"] = "neu"
    after["count"] = "2"
    _edit(tmp_path, LOCALE, json.dumps(after, indent=2))
    code, out = _run_json(capsys, "packages/cli/src/i18n/locales")
    assert code == 0
    (entry,) = out["summary"]["json"]
    assert entry["added"] == ["commands.up.hint"]
    assert entry["removed"] == []
    assert entry["type_changed"] == {"count": ["number", "string"]}


def test_inverse_a_value_only_edit_reports_no_key_change(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    after = json.loads(json.dumps(LOCALE_BEFORE))
    after["commands"]["up"]["help"] = "Nach oben"
    _edit(tmp_path, LOCALE, json.dumps(after, indent=2))
    code, out = _run_json(capsys, "packages/cli/src/i18n/locales")
    assert code == 0
    assert out["summary"]["json"] == []


def test_a_json_file_that_no_longer_parses_exits_1(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    _edit(tmp_path, LOCALE, json.dumps(LOCALE_BEFORE, indent=2)[:-1])
    code, out = _run_json(capsys, "packages/cli/src/i18n/locales")
    assert code == 1
    assert "error" in out["findings"][0]["keys"]


def test_inverse_a_markdown_file_in_the_same_run_still_reads_as_shapes(
    tmp_path, monkeypatch, capsys
):
    """The mode is chosen per file by suffix: a `.md` beside the `.json` keeps its line shapes."""
    _repo(
        tmp_path,
        monkeypatch,
        {LOCALE: json.dumps(LOCALE_BEFORE), "docs/a.md": "----------\nTITLE\n----------\nbody\n"},
    )
    _edit(tmp_path, "docs/a.md", "---------- TITLE ---------- body\n")
    code, out = _run_json(capsys, ".")
    assert code == 1
    assert out["findings"][0]["path"] == "docs/a.md"
    assert out["findings"][0]["lost"]["rule-line"] == [2, 0]
    assert "keys" not in out["findings"][0]


def test_the_text_report_names_the_key_paths(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch, {LOCALE: json.dumps(LOCALE_BEFORE, indent=2)})
    after = json.loads(json.dumps(LOCALE_BEFORE))
    del after["commands"]["up"]
    after["commands"]["left"] = {"help": "Links"}
    _edit(tmp_path, LOCALE, json.dumps(after, indent=2))
    code = scd.main(["--rev", "HEAD", "packages/cli/src/i18n/locales"])
    text = capsys.readouterr().out
    assert code == 1
    assert "added commands.left.help" in text
    assert "removed commands.up.help" in text
