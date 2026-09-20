r"""`rediacc_ci.quality.config_migrations` against the shell it replaced.

WHY A SHELL ORACLE AND NOT A TABLE OF EXPECTED STRINGS. Three of this gate's decisions are made by shell constructs whose behaviour is not inferable from reading them: a two-stage `grep -oE | grep -oE` whose second stage anchors to the FIRST stage's output, a `find | sort` whose order is byte order and not numeric, and -- most consequentially -- an assignment under `set -euo
pipefail` whose failure kills the script BEFORE the error message written to handle it. A table of expected strings would be a table of what the PORT does, asserted against itself.

The committed ledger `.ci/shadow/w7p2-config-migrations.observations.jsonl` compared the WHOLE gate over five distinct trees, with `npx` stubbed so the round-trip path is deterministic. It could not show that the "Could not parse" message is unreachable, because on such a tree BOTH sides print nothing. This file proves that with bash.

THE FRAGMENTS BELOW WERE LIFTED FROM
`.ci/scripts/quality/check-config-migrations.sh` lines 45-69 with the variables substituted and nothing else changed. That twin was retired in W7 P5 once the ledger licensed the port at K=5, so bash itself is the oracle now and the case that compared the port's `TSX_SOURCE` against the twin's heredoc was retired with it.
"""

import pathlib

import pytest

from rediacc_ci.quality import config_migrations as cm
from rediacc_ci.tests import differential as diff

# --------------------------------------------------------------------------- The version pipeline ---------------------------------------------------------------------------

# Every shape the runner can present, plus the near-misses that decide whether the gate dies silently. The comment on each line is the property it is there
# for; a case with no property is a case that will be deleted the first time
# someone tidies this file.
VERSION_CASES = [
    "export const CURRENT_SCHEMA_VERSION = 4;",  # the live shape
    "export const CURRENT_SCHEMA_VERSION = 4",  # no semicolon
    "CURRENT_SCHEMA_VERSION = 42",  # multi-digit
    "CURRENT_SCHEMA_VERSION = 1",  # the boundary: no migrations needed
    "  CURRENT_SCHEMA_VERSION = 7;",  # indented
    "CURRENT_SCHEMA_VERSION=4",  # NO spaces: the ERE demands them
    "CURRENT_SCHEMA_VERSION =4",  # one space, wrong side
    "CURRENT_SCHEMA_VERSION =  4",  # two spaces after the =
    "CURRENT_SCHEMA_VERSION = x",  # not a number
    "// CURRENT_SCHEMA_VERSION = 9",  # a COMMENT is matched: there is no filter
    "OTHER_SCHEMA_VERSION = 4",  # a different constant
    "nothing here",  # absent entirely
    "",  # an empty runner
]


@pytest.mark.parametrize("text", VERSION_CASES)
def test_version_pipeline_matches_grep(tmp_path: pathlib.Path, text: str) -> None:
    """`grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' | grep -oE '[0-9]+$'`.

    Run WITHOUT `set -e`, so the shell reports the empty result instead of dying on it. The dying is the subject of the next test, and conflating the two would make this one pass for the wrong reason.
    """
    (tmp_path / "index.ts").write_text(text + "\n", encoding="utf-8")
    code, out, err = diff.bash_streams(
        "grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' index.ts | grep -oE '[0-9]+$'; true",
        cwd=str(tmp_path),
    )
    assert code == 0, err
    from_bash = [line for line in out.split("\n") if line != ""]
    assert cm.current_versions(text) == from_bash


@pytest.mark.parametrize("text", VERSION_CASES)
def test_the_unparseable_runner_dies_before_its_error_message(
    tmp_path: pathlib.Path, text: str
) -> None:
    """The dead-code path, proven with bash rather than asserted from reading.

    Under `set -euo pipefail` the ASSIGNMENT carries the pipeline's status, so a runner with no constant exits 1 having printed NOTHING -- the `log_error "Could not parse CURRENT_SCHEMA_VERSION from ..."` beneath it is unreachable. The port reproduces the silence.

    BOTH DIRECTIONS: the parseable rows in the table must reach the marker, or this test would pass against a script that always died.
    """
    (tmp_path / "index.ts").write_text(text + "\n", encoding="utf-8")
    code, out, err = diff.bash_streams(
        "set -euo pipefail\n"
        "CURRENT=$(grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' index.ts | grep -oE '[0-9]+$')\n"
        'if [[ -z "$CURRENT" ]]; then echo REACHED_THE_MESSAGE; exit 1; fi\n'
        'echo "PARSED:$CURRENT"',
        cwd=str(tmp_path),
    )
    parsed = cm.current_versions(text)
    if parsed:
        assert code == 0, err
        assert out.strip() == "PARSED:" + "\n".join(parsed)
    else:
        assert code == 1
        # THE WHOLE POINT: no marker, no message, no output at all.
        assert out == ""
        assert "REACHED_THE_MESSAGE" not in out


# --------------------------------------------------------------------------- Migration file coverage ---------------------------------------------------------------------------

COVERAGE_CASES = [
    (1, ()),  # the boundary: version 1 needs nothing
    (2, ()),  # one gap
    (2, (1,)),  # complete
    (3, (1, 2)),  # complete
    (3, (2,)),  # a gap at the START
    (3, (1,)),  # a gap at the END
    (5, (1, 3)),  # two gaps, non-adjacent
    (4, ()),  # everything missing
    (3, (1, 2, 3, 4)),  # extras beyond CURRENT are not findings
]


@pytest.mark.parametrize(("current", "present"), COVERAGE_CASES)
def test_coverage_loop_matches_bash(
    tmp_path: pathlib.Path, current: int, present: tuple[int, ...]
) -> None:
    """`for ((v = 1; v < CURRENT; v++))` and the `[[ ! -f ... ]]` inside it.

    BOTH DIRECTIONS. Four of these rows are complete chains that must report nothing; a table of only-broken chains would pass against a gate that reported every version.
    """
    for v in present:
        (tmp_path / ("v%d-to-v%d.ts" % (v, v + 1))).write_text("x\n", encoding="utf-8")
    code, out, err = diff.bash_streams(
        "for ((v = 1; v < %d; v++)); do next=$((v + 1)); "
        'if [[ ! -f "v${v}-to-v${next}.ts" ]]; then echo "$v"; fi; done' % current,
        cwd=str(tmp_path),
    )
    assert code == 0, err
    from_bash = [int(line) for line in out.split("\n") if line != ""]
    assert cm.missing_migrations(tmp_path, current) == from_bash


# --------------------------------------------------------------------------- The fixture lister ---------------------------------------------------------------------------


def test_fixture_files_matches_find_and_sort(tmp_path: pathlib.Path) -> None:
    """`find <dir> -maxdepth 1 -name 'v*-sample.json' | sort`.

    THE ORDER IS BYTE ORDER, NOT NUMERIC, and that is the assertion worth having: `-` is 0x2D and `0` is 0x30, so `v1-sample.json` sorts before `v10-sample.json`, which sorts before `v2-sample.json`. A port that sorted numerically would print its round-trip results in a different order for the rest of time.

    `-maxdepth 1` is the other half: a nested fixture is invisible to both.
    """
    for name in (
        "v2-sample.json",
        "v10-sample.json",
        "v1-sample.json",
        "notes.md",
        "sample.json",
        "v1-sample.json.bak",
    ):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "v3-sample.json").write_text("{}", encoding="utf-8")

    code, out, err = diff.bash_streams(
        "find . -maxdepth 1 -name 'v*-sample.json' | sort", cwd=str(tmp_path)
    )
    assert code == 0, err
    from_bash = [line[2:] for line in out.strip().split("\n")]
    assert [pathlib.Path(p).name for p in cm.fixture_files(tmp_path)] == from_bash
    assert from_bash == ["v1-sample.json", "v10-sample.json", "v2-sample.json"]


def test_an_empty_and_an_absent_fixtures_dir_are_both_empty(tmp_path: pathlib.Path) -> None:
    """The two WARNING paths, which are also this gate's vacuity hole.

    Neither is a failure in the twin: a repository with no fixtures at all reports success having round-tripped nothing. Pinned as a named control so the debt is on the record rather than inferred from the absence of a test.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cm.fixture_files(empty) == []
    assert cm.fixture_files(tmp_path / "gone") == []


# --------------------------------------------------------------------------- The generated tsx program ---------------------------------------------------------------------------


def test_the_scratch_file_lands_in_the_repository() -> None:
    """`.config-migrations-check.tmp.ts` sits in packages/cli, not in a tempdir.

    Asserted rather than commented because it is a real property with a real cost: the working tree is DIRTY for the duration of the run, and a `kill -9` between the write and the trap leaves the file behind. The path is load-bearing -- the generated program resolves `src/__tests__/fixtures/config` against its own working directory -- so this is carried, not repaired.
    """
    assert cm.TMP_SCRIPT_NAME == ".config-migrations-check.tmp.ts"
    assert not pathlib.Path(cm.TMP_SCRIPT_NAME).is_absolute()


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that fails the pytest suite when a control is deleted, which is the failure mode the flag on its own cannot catch (nobody runs it).
    """
    assert cm.selftest() == 0
