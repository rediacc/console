"""`rediacc_ci.quality.compose_env` against the three shell pipelines it replaces.

WHY EVERY CASE HERE IS A DIFFERENTIAL. This gate is three extraction pipelines and one set comparison, and all three pipelines are PCRE and sed:

    grep -ohP '\\$\\{[A-Z0-9_]+'                             the references
    grep -ohP '...:-[^}]+\\}' | grep -vP ':-\\}$' | grep -oP  the safe defaults
    sed -n '/<<ENVBLOCK/,/^ENVBLOCK/p' | grep -oP            the persisted set

sed's RANGE semantics are the part nobody reproduces correctly from memory: the start line never closes its own range, a range restarts, and an unterminated one runs to end of file. Asserting the Python against a table of expected lists would assert it against whatever the author believed sed does. Running sed is the only version of this test that can be wrong in the author's
favour and still fail.

The whole gate is compared end to end by `.ci/shadow/w7p2-compose-env.observations.jsonl` over five distinct trees.
"""

import pathlib
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import compose_env as ce
from rediacc_ci.tests import differential as diff

REFERENCE_PIPELINE = "grep -ohP '\\$\\{[A-Z0-9_]+' *.yml 2>/dev/null | sed 's/\\${//' | sort -u"
SAFE_PIPELINE = (
    "grep -ohP '\\$\\{[A-Z0-9_]+:-[^}]+\\}' *.yml 2>/dev/null | "
    "grep -vP ':-\\}$' | grep -oP '(?<=\\$\\{)[A-Z0-9_]+' | sort -u"
)
PERSISTED_PIPELINE = (
    "sed -n '/<<ENVBLOCK/,/^ENVBLOCK/p' ci-env.sh | grep -oP '^[A-Z0-9_]+(?==)' | sort -u"
)

COMPOSE_CASES = [
    ("plain", "a: ${ONE}\nb: ${TWO}\n"),
    ("defaults", "a: ${ONE:-yes}\nb: ${TWO}\n"),
    ("empty default", "a: ${ONE:-}\nb: ${TWO}\n"),
    ("nested default", "a: ${ONE:-${TWO}}\n"),
    ("unclosed reference", "a: ${ONE\n"),
    ("lowercase is not a reference", "a: ${one}\nb: ${TWO}\n"),
    ("digits and underscores", "a: ${A_1}\nb: ${B2_C}\n"),
    ("two on one line", "a: ${ONE}-${TWO}\n"),
    ("repeated reference", "a: ${ONE}\nb: ${ONE}\n"),
    ("no references at all", "image: alpine\n"),
    ("default containing a colon", "a: ${ONE:-http://x}\n"),
]


def _bash(script: str, cwd: pathlib.Path) -> list[str]:
    code, out, err = diff.bash_streams(script, cwd=str(cwd))
    assert err == "", err
    assert code in (0, 1), code
    return [line for line in out.split("\n") if line]


@pytest.mark.parametrize(("why", "content"), COMPOSE_CASES)
def test_reference_extraction_matches_bash(tmp_path: pathlib.Path, why: str, content: str) -> None:
    (tmp_path / "docker-compose.yml").write_text(content, encoding="utf-8")
    files = ce.compose_files(tmp_path)
    assert ce.referenced_vars(files) == _bash(REFERENCE_PIPELINE, tmp_path), why


@pytest.mark.parametrize(("why", "content"), COMPOSE_CASES)
def test_safe_default_extraction_matches_bash(
    tmp_path: pathlib.Path, why: str, content: str
) -> None:
    (tmp_path / "docker-compose.yml").write_text(content, encoding="utf-8")
    files = ce.compose_files(tmp_path)
    assert ce.safe_default_vars(files) == _bash(SAFE_PIPELINE, tmp_path), why


def test_the_compose_table_exercises_both_directions(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. A safe-default extractor that always returned nothing, or always everything, would satisfy a one-sided table."""
    empty = []
    nonempty = []
    for why, content in COMPOSE_CASES:
        (tmp_path / "docker-compose.yml").write_text(content, encoding="utf-8")
        found = ce.safe_default_vars(ce.compose_files(tmp_path))
        (nonempty if found else empty).append(why)
    assert empty, "every case yields a safe default: the filter may be inert"
    assert nonempty, "no case yields a safe default: the extractor may be dead"


ENVBLOCK_CASES = [
    ("ordinary block", "x=1\ncat <<ENVBLOCK\nA=1\nB=2\nENVBLOCK\nC=3\n"),
    ("no block at all", "A=1\nB=2\n"),
    ("unterminated block runs to EOF", "cat <<ENVBLOCK\nA=1\nB=2\n"),
    (
        "two blocks restart the range",
        "cat <<ENVBLOCK\nA=1\nENVBLOCK\nB=2\ncat <<ENVBLOCK\nC=3\nENVBLOCK\nD=4\n",
    ),
    ("the terminator line itself is inside the range", "cat <<ENVBLOCK\nENVBLOCK\nA=1\n"),
    ("an indented terminator does not close it", "cat <<ENVBLOCK\nA=1\n  ENVBLOCK\nB=2\n"),
    ("assignments outside are ignored", "export A=1\ncat <<ENVBLOCK\nB=2\nENVBLOCK\nC=3\n"),
    ("lowercase names are not assignments", "cat <<ENVBLOCK\nabc=1\nB=2\nENVBLOCK\n"),
    ("an indented assignment is not at line start", "cat <<ENVBLOCK\n  A=1\nB=2\nENVBLOCK\n"),
    ("an empty file", ""),
]


@pytest.mark.parametrize(("why", "content"), ENVBLOCK_CASES)
def test_persisted_extraction_matches_sed(tmp_path: pathlib.Path, why: str, content: str) -> None:
    (tmp_path / "ci-env.sh").write_text(content, encoding="utf-8")
    assert ce.persisted_vars(tmp_path / "ci-env.sh") == _bash(PERSISTED_PIPELINE, tmp_path), why


def test_the_envblock_table_exercises_both_directions(tmp_path: pathlib.Path) -> None:
    """Same anti-vacuity claim for the sed range."""
    empty = []
    nonempty = []
    for why, content in ENVBLOCK_CASES:
        (tmp_path / "ci-env.sh").write_text(content, encoding="utf-8")
        found = ce.persisted_vars(tmp_path / "ci-env.sh")
        (nonempty if found else empty).append(why)
    assert empty, "every fixture persists something: the sed range may be too wide"
    assert nonempty, "no fixture persists anything: the sed range may be dead"


def test_the_safe_default_filter_is_dormant_not_dead() -> None:
    """The observation recorded in the port's docstring, asserted.

    With the shipped pattern the filter never sees a candidate; loosened by one
    character it is the only thing that catches `${VAR:-}`. So deleting it is a
    behaviour change waiting for the next edit to the pattern, not a cleanup.
    """
    text = "x: ${EMPTY:-}\ny: ${SAFE:-ok}\n"
    assert ce.SAFE_DEFAULT_RE.findall(text) == ["${SAFE:-ok}"]
    loose = re.compile(ce.SAFE_DEFAULT_RE.pattern.replace("[^}]+", "[^}]*"))
    caught = [m for m in loose.findall(text) if ce.EMPTY_DEFAULT_RE.search(m)]
    assert caught == ["${EMPTY:-}"]


def test_zero_references_is_a_refusal(tmp_path: pathlib.Path, monkeypatch) -> None:
    """ZERO INPUTS IS A FAILURE. A parse that finds nothing has verified nothing."""
    (tmp_path / ".ci/docker/ci").mkdir(parents=True)
    (tmp_path / ".ci/docker/ci/docker-compose.yml").write_text("image: alpine\n", encoding="utf-8")
    (tmp_path / ".ci/scripts/infra").mkdir(parents=True)
    (tmp_path / ".ci/scripts/infra/ci-env.sh").write_text("\n", encoding="utf-8")
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert ce.main([]) == 1


def test_a_persisted_reference_passes(tmp_path: pathlib.Path, monkeypatch) -> None:
    """The mirror. Without it the refusal above could be a gate that refuses everything."""
    (tmp_path / ".ci/docker/ci").mkdir(parents=True)
    (tmp_path / ".ci/docker/ci/docker-compose.yml").write_text("a: ${ONE}\n", encoding="utf-8")
    (tmp_path / ".ci/scripts/infra").mkdir(parents=True)
    (tmp_path / ".ci/scripts/infra/ci-env.sh").write_text(
        "cat <<ENVBLOCK\nONE=1\nENVBLOCK\n", encoding="utf-8"
    )
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert ce.main([]) == 0


def test_selftest_is_green() -> None:
    assert ce.selftest() == 0


def test_the_real_tree_is_complete() -> None:
    """The gate against the actual repository."""
    assert ce.main([]) == 0
