"""`rediacc_ci.quality.cli_contract` against the diff logic it replaces.

WHAT THE SHADOW LEDGER CANNOT REACH. `.ci/shadow/w7p2-cli-contract.observations.jsonl` drives the whole gate over five distinct trees with `npm` and `npx` shimmed, so the wiring, the exit codes and the finding text are already compared end to end. What it cannot isolate is the COMPARISON ITSELF: which lines the version filter drops, what an unterminated file does to it, and the
no-nullglob behaviour that makes an empty i18n directory report a locale whose name is a glob.

The last of those is a DEFECT in the twin, carried deliberately. It is pinned here so that a future reader who "fixes" it discovers, from a red test, that they have changed the verdict rather than tidied the code.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import cli_contract as cc
from rediacc_ci.tests import differential as diff

# The twin's comparison, verbatim from check-cli-contract.sh:49-52.
COMPARE = (
    "diff -q <(grep -v -e '_VERSION = ' -e '\"version\":' a) "
    "<(grep -v -e '_VERSION = ' -e '\"version\":' b) >/dev/null 2>&1"
)

PAIRS = [
    # (a, b, the property this pair is here for)
    ("x\n", "x\n", "identical"),
    ("x\n", "y\n", "plain difference"),
    (
        'export const CLI_VERSION = "1";\nx\n',
        'export const CLI_VERSION = "2";\nx\n',
        "the TS version constant is filtered out",
    ),
    ('{"version": "1"}\nx\n', '{"version": "2"}\nx\n', "the JSON version field is filtered out"),
    (
        'export const CLI_VERSION = "1";\nx\n',
        'export const CLI_VERSION = "2";\ny\n',
        "a version change PLUS real drift is still drift",
    ),
    ("x", "x\n", "a missing final newline on one side only"),
    ("", "", "two empty files"),
    ("", "x\n", "empty against non-empty"),
    ("a\nb\n", "b\na\n", "reordered lines are a difference"),
    ('  "version": "1"\n', '  "version": "2"\n', "an indented version field is still filtered"),
]


@pytest.mark.parametrize(("left", "right", "why"), PAIRS)
def test_compare_ignoring_version_matches_bash(
    tmp_path: pathlib.Path, left: str, right: str, why: str
) -> None:
    (tmp_path / "a").write_text(left, encoding="utf-8")
    (tmp_path / "b").write_text(right, encoding="utf-8")
    code, _out, _err = diff.bash_streams(COMPARE, cwd=str(tmp_path))
    bash_says_equal = code == 0
    assert cc.compare_ignoring_version(tmp_path / "a", tmp_path / "b") is bash_says_equal, why


def test_the_pair_table_exercises_both_directions() -> None:
    """ANTI-VACUITY on the table above: a comparison that always answered
    "equal", or always "different", would satisfy a one-sided table."""
    verdicts = set()
    for left, right, _why in PAIRS:
        filtered_left = [
            ln for ln in left.split("\n") if not any(m in ln for m in cc.VERSION_MARKERS)
        ]
        filtered_right = [
            ln for ln in right.split("\n") if not any(m in ln for m in cc.VERSION_MARKERS)
        ]
        verdicts.add(filtered_left == filtered_right)
    assert verdicts == {True, False}


def test_a_missing_generated_file_is_not_equal(tmp_path: pathlib.Path) -> None:
    """The absent side must never compare EQUAL. A port that read a missing file
    as an empty one would call a vanished artefact up-to-date."""
    (tmp_path / "a").write_text("x\n", encoding="utf-8")
    assert cc.compare_ignoring_version(tmp_path / "a", tmp_path / "gone") is False


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
    """The no-nullglob behaviour, proven against a real bash loop rather than
    asserted from memory of how bash behaves."""
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
    entries = cc.stale_entries(committed, generated)
    assert "i18n/*.json (missing)" in entries
    assert any(e.startswith("i18n/*.json (orphaned") for e in entries)


def test_the_orphan_message_carries_the_twins_em_dash() -> None:
    """Byte fidelity on the one string the house style would otherwise rewrite.

    The twin emits U+2014. The port writes it as an escape so no em dash is typed into authored text, and this asserts the EMITTED value is unchanged -- which is what the shadow differential compares.
    """
    assert cc.ORPHAN_SUFFIX == " (orphaned \u2014 no such locale)"
    assert "\u2014" in cc.ORPHAN_SUFFIX


def test_locale_bundles_are_not_version_filtered(tmp_path: pathlib.Path) -> None:
    """The asymmetry between the two comparisons, asserted directly.

    A locale bundle whose only difference is a line containing `"version":` IS drift. Unifying the two comparisons would silence it.
    """
    committed = tmp_path / "committed"
    generated = tmp_path / "generated"
    for base in (committed, generated):
        (base / "i18n").mkdir(parents=True)
        (base / "contract.generated.ts").write_text("x\n", encoding="utf-8")
        (base / "contract.json").write_text("{}\n", encoding="utf-8")
    (committed / "i18n" / "en.json").write_text('{"version": "1"}\n', encoding="utf-8")
    (generated / "i18n" / "en.json").write_text('{"version": "2"}\n', encoding="utf-8")
    assert cc.stale_entries(committed, generated) == ["i18n/en.json"]


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
