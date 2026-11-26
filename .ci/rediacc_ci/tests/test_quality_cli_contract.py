"""`rediacc_ci.quality.cli_contract` against the diff logic it replaces.

WHAT THE SHADOW LEDGER CANNOT REACH. the ledger (deleted in commit:936280cd35) drives the whole gate over five distinct trees with `npm` and `npx` shimmed, so the wiring, the exit codes and the finding text are already compared end to end. What it cannot isolate is the COMPARISON ITSELF: that every artefact, its version line included, is compared byte for byte, and the
no-nullglob behaviour that makes an empty i18n directory report a locale whose name is a glob.

The last of those is a DEFECT in the twin, carried deliberately. It is pinned here so that a future reader who "fixes" it discovers, from a red test, that they have changed the verdict rather than tidied the code.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import cli_contract as cc
from rediacc_ci.tests import differential as diff

# Every artefact, the version line included, is compared byte for byte since the version became a deterministic content hash (PLAN-console-contract-semantics.md D5).
PAIRS = [
    # (a, b, the property this pair is here for)
    ("x\n", "x\n", "identical"),
    ("x\n", "y\n", "plain difference"),
    (
        "export const CLI_CONTRACT_VERSION = '1';\nx\n",
        "export const CLI_CONTRACT_VERSION = '2';\nx\n",
        "a version-only difference is drift",
    ),
    ('{"version": "1"}\nx\n', '{"version": "2"}\nx\n', "a JSON version-only difference is drift"),
    ("x", "x\n", "a missing final newline on one side only"),
    ("", "", "two empty files"),
    ("a\nb\n", "b\na\n", "reordered lines are a difference"),
]


@pytest.mark.parametrize(("left", "right", "why"), PAIRS)
def test_files_equal_matches_diff_q(
    tmp_path: pathlib.Path, left: str, right: str, why: str
) -> None:
    (tmp_path / "a").write_text(left, encoding="utf-8")
    (tmp_path / "b").write_text(right, encoding="utf-8")
    code, _out, _err = diff.bash_streams("diff -q a b >/dev/null 2>&1", cwd=str(tmp_path))
    assert cc._files_equal(tmp_path / "a", tmp_path / "b") is (code == 0), why


def test_the_pair_table_exercises_both_directions() -> None:
    """ANTI-VACUITY on the table above: a comparison that always answered "equal", or always "different", would satisfy a one-sided table."""
    assert {left == right for left, right, _why in PAIRS} == {True, False}


def test_a_missing_generated_file_is_not_equal(tmp_path: pathlib.Path) -> None:
    """The absent side must never compare EQUAL. A port that read a missing file as an empty one would call a vanished artefact up-to-date."""
    (tmp_path / "a").write_text("x\n", encoding="utf-8")
    assert cc._files_equal(tmp_path / "a", tmp_path / "gone") is False


def test_a_missing_side_names_the_path_on_stderr(tmp_path: pathlib.Path, capsys) -> None:
    """A vanished generated artefact is reported on stderr with its path, not only as a bare stale line (per-commit review b6917624.2)."""
    committed = tmp_path / "committed"
    generated = tmp_path / "generated"
    committed.mkdir()
    generated.mkdir()
    (committed / "contract.json").write_text("x\n", encoding="utf-8")
    assert "contract.json" in cc.stale_entries(committed, generated)
    err = capsys.readouterr().err
    assert str(generated / "contract.json") in err
    assert "No such file or directory" in err


def test_glob_or_literal_both_directions(tmp_path: pathlib.Path) -> None:
    """Bash has no nullglob here, so an empty match yields the PATTERN.

    Both halves in one test on purpose: the literal branch only means something beside the populated branch, and a reader deleting one would see the other still passing.
    """
    directory = tmp_path / "i18n"
    directory.mkdir()
    assert cc._glob_or_literal(directory) == [directory / "*.json"]
    (directory / "en.json").write_text("{}", encoding="utf-8")
    (directory / "tr.json").write_text("{}", encoding="utf-8")
    assert [p.name for p in cc._glob_or_literal(directory)] == ["en.json", "tr.json"]


def test_glob_or_literal_matches_bash(tmp_path: pathlib.Path) -> None:
    """The no-nullglob behaviour, proven against a real bash loop rather than asserted from memory of how bash behaves."""
    directory = tmp_path / "i18n"
    directory.mkdir()
    script = 'for f in "%s"/*.json; do basename "$f"; done' % directory
    _code, out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert out.split("\n")[0] == "*.json"
    assert cc._glob_or_literal(directory)[0].name == "*.json"


def test_empty_i18n_yields_a_glob_named_finding(tmp_path: pathlib.Path) -> None:
    """THE DEFECT, PINNED. See the module docstring of the port.

    An empty COMMITTED i18n directory makes the orphan loop iterate over the literal pattern and emit a finding naming a glob. Changing this is changing the verdict, which is why it is asserted rather than described.
    """
    committed = tmp_path / "committed"
    generated = tmp_path / "generated"
    for base in (committed, generated):
        (base / "i18n").mkdir(parents=True)
        (base / "contract.generated.ts").write_text("x\n", encoding="utf-8")
        (base / "contract.json").write_text("{}\n", encoding="utf-8")
        (base / "contract-version.generated.ts").write_text("x\n", encoding="utf-8")
    entries = cc.stale_entries(committed, generated)
    assert "i18n/*.json (missing)" in entries
    assert any(e.startswith("i18n/*.json (orphaned") for e in entries)


def test_the_orphan_message_carries_the_twins_em_dash() -> None:
    """Byte fidelity on the one string the house style would otherwise rewrite.

    The twin emits U+2014. The port writes it as an escape so no em dash is typed into authored text, and this asserts the EMITTED value is unchanged -- which is what the shadow differential compares.
    """
    assert cc.ORPHAN_SUFFIX == " (orphaned \u2014 no such locale)"
    assert "\u2014" in cc.ORPHAN_SUFFIX


def test_a_version_only_difference_is_stale(tmp_path: pathlib.Path) -> None:
    """The version is not exempt in any artefact: each one whose only difference is its version line is reported by name."""
    committed = tmp_path / "committed"
    generated = tmp_path / "generated"
    for base, version in ((committed, "1"), (generated, "2")):
        (base / "i18n").mkdir(parents=True)
        (base / "i18n" / "en.json").write_text("{}\n", encoding="utf-8")
        (base / "contract.generated.ts").write_text(
            "export const CLI_CONTRACT_VERSION = '%s';\n" % version, encoding="utf-8"
        )
        (base / "contract.json").write_text('{"version": "%s"}\n' % version, encoding="utf-8")
        (base / "contract-version.generated.ts").write_text(
            "export const CLI_CONTRACT_VERSION = '%s';\n" % version, encoding="utf-8"
        )
    assert cc.stale_entries(committed, generated) == list(cc.TOP_LEVEL_FILES)


def test_selftest_is_green() -> None:
    """The gate's own plants, which shim npm and npx rather than building."""
    assert cc.selftest() == 0


def test_main_intercepts_selftest_before_scanning(tmp_path: pathlib.Path, monkeypatch) -> None:
    """`--selftest` must be handled BEFORE anything real runs, in BOTH directions.

    The root override is pointed at a path that does not exist, which makes `paths.repo_root()` raise. A real scan therefore RAISES, and `--selftest` returns 0 -- so the flag is proven to short-circuit rather than merely to
    return the same number a scan would have returned.
    """
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path / "does-not-exist"))
    with pytest.raises(paths.RootError):
        cc.main([])
    assert cc.main(["--selftest"]) == 0
