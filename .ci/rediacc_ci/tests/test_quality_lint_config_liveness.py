"""`rediacc_ci.quality.lint_config_liveness`, driven with the real ruff over planted trees.

The module's own `--selftest` covers the reader, the matcher and the verdict on synthetic findings. What it cannot cover is the half that decides whether any of that means anything: that ruff, given a table, suppresses what this module says the table suppresses. So every case here builds a git work tree in `tmp_path` with its own pyproject.toml and runs the gate's `run()` against it, and one case compares the matcher with ruff pattern by pattern.

BOTH DIRECTIONS, ON PURPOSE. A liveness check with only failing controls would refuse every table; one with only a passing control would accept every table. The live tree below uses each glob shape the real config uses (`**/`, a brace, a rooted path, a bare file name), so the green case is also the matcher's agreement with ruff on all four.
"""

import pathlib
import subprocess
import tomllib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import lint_config_liveness as gate
from rediacc_ci.quality import python_lint

REASON = "a planted reason long enough to clear the validator's thirty character floor"

# Ruff's own config for a specimen: every rule on, minus the families a three-line file trips for reasons unrelated to the table under test.
HEAD = """[tool.ruff]
target-version = "py312"

[tool.ruff.lint]
select = ["ALL"]
ignore = ["D", "ANN", "INP001", "CPY001", "S110", "SIM105", "EXE"]
"""

BLIND = "try:\n    VALUE = 1\nexcept Exception:\n    VALUE = 2\n"
CLEAN = "VALUE = 1\n"
SIDE_EFFECT = "import _cipath\n\nVALUE = 1\n"

LIVE_TABLES = """
[tool.ruff.lint.per-file-ignores]
"**/tests/**/test_*.py" = [
    # BLOCKER: %(reason)s
    "S101",
]
"hooks/{stop,context}/*.py" = [
    # BLOCKER: %(reason)s
    "BLE001",
]
"ci/publish.py" = [
    # BLOCKER: %(reason)s
    "BLE001",
]
"conftest.py" = [
    # BLOCKER: %(reason)s
    "BLE001",
]

[tool.ruff.lint.pyflakes]
allowed-unused-imports = [
    # BLOCKER: %(reason)s
    "_cipath",
]
""" % {"reason": REASON}

LIVE_FILES = {
    "pkg/tests/gates/test_a.py": "def test_a():\n    assert 1 + 1 == 2\n",
    "hooks/stop/wl_a.py": BLIND,
    "hooks/context/ctx_a.py": BLIND,
    "ci/publish.py": BLIND,
    "conftest.py": BLIND,
    "scripts/entry.py": SIDE_EFFECT,
    # Held to the rule: nothing above reaches it, so run B must still report it and the matcher must not claim it.
    "ci/other.py": BLIND,
}


def build(tmp_path: pathlib.Path, tables: str, files: dict[str, str]) -> pathlib.Path:
    """A git work tree holding one pyproject.toml and `files`. Untracked is enough: the enumerator lists untracked Python."""
    root = tmp_path / "specimen"
    root.mkdir()
    (root / "pyproject.toml").write_text(HEAD + tables, encoding="utf-8")
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    return root


def judged(root: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    status = gate.run(root)
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def test_a_live_reasoned_table_passes_and_prints_its_shape(tmp_path, capsys) -> None:
    status, out, err = judged(build(tmp_path, LIVE_TABLES, LIVE_FILES), capsys)
    assert status == 0, err
    assert "4 (glob, code) pair(s) under 4 glob(s) and 1 allowed-unused-imports name(s)" in out
    # The brace glob covers two files and each of the others one; the count is per entry, so a pair that went from two sites to none would show here before it failed.
    assert '     2  "hooks/{stop,context}/*.py" BLE001' in out
    assert "     1  allowed-unused-imports _cipath" in out
    assert "ruff agrees on every one" in out
    assert err == ""


def test_a_planted_dead_pair_is_refused_with_its_line(tmp_path, capsys) -> None:
    files = dict(LIVE_FILES)
    files["ci/publish.py"] = CLEAN
    status, out, err = judged(build(tmp_path, LIVE_TABLES, files), capsys)
    assert status == 1
    assert '"ci/publish.py" BLE001 suppresses nothing' in err
    line = (HEAD + LIVE_TABLES).split("\n").index('"ci/publish.py" = [') + 3
    assert "pyproject.toml:%d:" % line in err
    assert "1 entr(ies)" in err, "only the planted pair may be reported dead"
    assert "each live" not in out


def test_a_planted_dead_import_name_is_refused(tmp_path, capsys) -> None:
    files = dict(LIVE_FILES)
    files["scripts/entry.py"] = CLEAN
    status, _out, err = judged(build(tmp_path, LIVE_TABLES, files), capsys)
    assert status == 1
    assert "allowed-unused-imports _cipath suppresses nothing" in err


def test_a_live_entry_with_no_blocker_is_refused(tmp_path, capsys) -> None:
    tables = LIVE_TABLES.replace(
        '"conftest.py" = [\n    # BLOCKER: %s\n' % REASON, '"conftest.py" = [\n    # because\n'
    )
    assert tables != LIVE_TABLES, "the plant did not land, so this case would pass for no reason"
    status, _out, err = judged(build(tmp_path, tables, LIVE_FILES), capsys)
    assert status == 1
    assert 'entry "conftest.py" BLE001 is missing' in err
    assert "suppress nothing" not in err, "the entry is live; only its reason is missing"


def test_a_low_effort_reason_is_refused(tmp_path, capsys) -> None:
    tables = LIVE_TABLES.replace(
        '"conftest.py" = [\n    # BLOCKER: %s\n' % REASON,
        '"conftest.py" = [\n    # BLOCKER: todo\n',
    )
    status, _out, err = judged(build(tmp_path, tables, LIVE_FILES), capsys)
    assert status == 1
    assert '"conftest.py" BLE001' in err


def test_a_reason_does_not_leak_into_the_next_array(tmp_path, capsys) -> None:
    """The end of an array ends the group: a key appended under one inherits nothing."""
    tables = LIVE_TABLES.replace(
        '"conftest.py" = [\n    # BLOCKER: %s\n' % REASON, '"conftest.py" = [\n'
    )
    status, _out, err = judged(build(tmp_path, tables, LIVE_FILES), capsys)
    assert status == 1
    assert 'entry "conftest.py" BLE001 is missing' in err


def test_an_inline_marker_is_the_reason_validated_for_its_own_line(tmp_path, capsys) -> None:
    """A group reason above an entry does not hide a weak marker on the entry's own line."""
    tables = LIVE_TABLES.replace(
        '"BLE001",\n]\n\n[tool.ruff.lint.pyflakes]',
        '"BLE001",  # BLOCKER: too short\n]\n\n[tool.ruff.lint.pyflakes]',
    )
    assert tables != LIVE_TABLES
    status, _out, err = judged(build(tmp_path, tables, LIVE_FILES), capsys)
    assert status == 1
    assert '"conftest.py" BLE001' in err, err


def test_an_empty_universe_is_cannot_verify_and_not_a_pass(tmp_path, capsys) -> None:
    files = dict.fromkeys(LIVE_FILES, CLEAN)
    status, out, err = judged(build(tmp_path, LIVE_TABLES, files), capsys)
    assert status == 1
    assert "CANNOT VERIFY" in err
    assert "ZERO findings" in err
    assert "each live" not in out


def test_a_table_the_line_reader_cannot_see_is_cannot_verify(tmp_path, capsys) -> None:
    tables = '\n[tool.ruff.lint.extend-per-file-ignores]\n"ci/publish.py" = ["BLE001"]\n'
    status, _out, err = judged(build(tmp_path, tables, LIVE_FILES), capsys)
    assert status == 1
    assert "CANNOT VERIFY" in err
    assert "extend-per-file-ignores" in err


# (pattern, path): the shapes the real table uses, each with a path it must match and a neighbour it must not.
MATCHER_CASES = [
    ("**/tests/**/test_*.py", "a/tests/test_x.py"),
    ("**/tests/**/test_*.py", "a/tests/deep/er/test_x.py"),
    ("**/tests/**/test_*.py", "a/tests/helper.py"),
    ("**/tests/**/test_*.py", "a/test_x.py"),
    ("**/hooks/{stop,context}/test-*.py", "c/hooks/stop/test-a.py"),
    ("**/hooks/{stop,context}/test-*.py", "c/hooks/other/test-a.py"),
    ("c/hooks/**/*.py", "c/hooks/stop/deep/a.py"),
    ("c/hooks/**/*.py", "c/hooks/a.py"),
    ("c/hooks/**/*.py", "c/hooksx/a.py"),
    ("c/guards/block_*.py", "c/guards/block_a.py"),
    ("c/guards/block_*.py", "c/guards/test-block_a.py"),
    ("c/guards/*.py", "c/guards/sub/a.py"),
    ("conftest.py", "conftest.py"),
    ("conftest.py", "a/b/conftest.py"),
    ("conftest.py", "a/b/notconftest.py"),
    ("c/one.py", "c/one.py"),
    ("c/one.py", "d/c/one.py"),
]


def test_the_matcher_agrees_with_ruff_pattern_by_pattern(tmp_path) -> None:
    """ruff is asked, one pattern at a time, which planted files a per-file ignore silences.

    The gate makes the same comparison on the real tree on every run, but only for the patterns the real table holds today. This pins the dialect itself, including the two facts that are easy to get wrong from memory: `*` crosses a directory separator, and a pattern is also tried against the bare file name.
    """
    ruff = python_lint.resolve_ruff()
    assert ruff is not None, "no ruff at the pin: this case cannot run, and a skip would hide that"
    files = sorted({path for _pattern, path in MATCHER_CASES})
    root = build(tmp_path, "", dict.fromkeys(files, BLIND))
    said_yes = said_no = 0
    for pattern in sorted({pattern for pattern, _path in MATCHER_CASES}):
        proc = subprocess.run(
            [
                *ruff,
                "check",
                "--no-cache",
                "--output-format",
                "concise",
                "--select",
                "BLE001",
                "--config",
                'lint.per-file-ignores = {"%s" = ["BLE001"]}' % pattern,
                "--",
                *files,
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
        assert proc.returncode in (0, 1), proc.stderr
        reported = {line.split(":", 1)[0] for line in proc.stdout.split("\n") if "BLE001" in line}
        for path in files:
            silenced = path not in reported
            assert gate.matches(pattern, path) == silenced, (
                "pattern %r on %r: ruff %s it, the matcher says %s"
                % (
                    pattern,
                    path,
                    "silences" if silenced else "reports",
                    gate.matches(pattern, path),
                )
            )
            said_yes += silenced
            said_no += not silenced
    assert said_yes >= 10, "ruff silenced almost nothing, so the agreement above is vacuous"
    assert said_no >= 10, "ruff silenced almost everything, so the agreement above is vacuous"


def test_the_real_tables_parse_whole_and_every_reason_passes() -> None:
    """The half that needs no linter: the repo's own pyproject.toml, both readers, and the validator.

    Liveness of the real entries is the gate's job, on the real tree, and is not repeated here: a peer's half-written file must not turn this suite red.
    """
    text = (paths.repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    entries, errors = gate.parse_config(text)
    assert errors == []
    assert gate.cross_check(entries, tomllib.loads(text)) == []
    assert gate.reason_failures(entries) == []
    # No typed floor: `cross_check` already holds the count to what tomllib sees, so the one shape left to refuse is both readers seeing nothing.
    assert entries, "both readers see empty tables; the gate would have nothing to prove"
    for entry in entries:
        if entry.kind == gate.IGNORE:
            gate.glob_regex(entry.glob)


def test_the_chain_returns_the_lints_status_and_stops(monkeypatch) -> None:
    """A lint refusal is returned unchanged, 77 included, and the tables are not judged behind it."""
    ran: list[str] = []

    def liveness(_argv=None) -> int:
        ran.append("liveness")
        return 0

    monkeypatch.setattr(gate, "main", liveness)
    for status in (1, python_lint.EXIT_CANNOT_RUN):
        monkeypatch.setattr(python_lint, "main", lambda _argv=None, status=status: status)
        assert gate.chained([]) == status
    assert ran == []
    monkeypatch.setattr(python_lint, "main", lambda _argv=None: 0)
    assert gate.chained([]) == 0
    assert ran == ["liveness"]


def test_selftest_exits_zero_and_prints_a_count(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert int(out.split(" control(s) passed")[0].strip()) >= 40
