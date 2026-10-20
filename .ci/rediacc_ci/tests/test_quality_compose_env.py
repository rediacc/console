"""`rediacc_ci.quality.compose_env` against the shell pipelines it replaces, and its read of `ci_env.PERSISTED`.

WHY THE COMPOSE CASES ARE DIFFERENTIALS. Two of the gate's three extractions are PCRE pipelines, and they are still compared against the real `grep`:

    grep -ohP '\\$\\{[A-Z0-9_]+'                             the references
    grep -ohP '...:-[^}]+\\}' | grep -vP ':-\\}$' | grep -oP  the safe defaults

THE THIRD, THE PERSISTED SET, IS NO LONGER A PIPELINE (W7P5-c). It was a `sed` range over the deleted `ci-env.sh` heredoc; it is now an `ast` read of the `PERSISTED` tuple in `.ci/rediacc_ci/infra/ci_env.py`, so its cases below are a table of literal sources with the answer each must produce, in both directions, plus the refusals.

The whole gate is compared end to end by `.ci/shadow/w7p2-compose-env.observations.jsonl` over five distinct trees.
"""

import pathlib
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import ci_env
from rediacc_ci.quality import compose_env as ce
from rediacc_ci.tests import differential as diff

REFERENCE_PIPELINE = "grep -ohP '\\$\\{[A-Z0-9_]+' *.yml 2>/dev/null | sed 's/\\${//' | sort -u"
SAFE_PIPELINE = (
    "grep -ohP '\\$\\{[A-Z0-9_]+:-[^}]+\\}' *.yml 2>/dev/null | "
    "grep -vP ':-\\}$' | grep -oP '(?<=\\$\\{)[A-Z0-9_]+' | sort -u"
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


PERSISTED_CASES = [
    (
        "annotated tuple",
        'PERSISTED: tuple[tuple[str, str | None], ...] = (("B", None), ("A", "x"))\n',
        ["A", "B"],
    ),
    ("plain assignment", 'PERSISTED = (("ONE", None),)\n', ["ONE"]),
    (
        "other tables do not count",
        'SYSTEM_DEFAULTS = (("X", "1"),)\nPERSISTED = (("ONE", None),)\nMASKED = ("Y",)\n',
        ["ONE"],
    ),
    ("an empty table is read as empty", "PERSISTED = ()\n", []),
    (
        "a repeated name is reported once",
        'PERSISTED = (("ONE", None), ("ONE", ""))\n',
        ["ONE"],
    ),
    (
        "a nested PERSISTED inside a function is not the module table",
        'def f():\n    PERSISTED = (("INNER", None),)\nPERSISTED = (("OUTER", None),)\n',
        ["OUTER"],
    ),
]


@pytest.mark.parametrize(("why", "content", "want"), PERSISTED_CASES)
def test_persisted_extraction(
    tmp_path: pathlib.Path, why: str, content: str, want: list[str]
) -> None:
    (tmp_path / "ci_env.py").write_text(content, encoding="utf-8")
    assert ce.persisted_vars(tmp_path / "ci_env.py") == want, why


def test_the_persisted_table_exercises_both_directions() -> None:
    """ANTI-VACUITY: the table holds a case that persists nothing and cases that persist something."""
    wants = [want for _why, _content, want in PERSISTED_CASES]
    assert [] in wants, (
        "no case persists nothing: an extractor that always answers [] could not fail"
    )
    assert any(wants), "no case persists anything: the extractor may be dead"


@pytest.mark.parametrize(
    "content",
    [
        pytest.param('SYSTEM_DEFAULTS = (("X", "1"),)\n', id="no table at all"),
        pytest.param("PERSISTED = list()\n", id="the table is not a tuple"),
        pytest.param("PERSISTED = (NAME,)\n", id="an entry is not a literal tuple"),
        pytest.param("PERSISTED = ((1, None),)\n", id="an entry's name is not a string"),
        pytest.param("PERSISTED = ((\n", id="the file does not parse"),
    ],
)
def test_an_unreadable_table_is_refused(tmp_path: pathlib.Path, content: str) -> None:
    """A table the gate cannot read is a refusal, never an empty persisted set: an empty set reads as "everything unpersisted", which is red for the wrong reason."""
    (tmp_path / "ci_env.py").write_text(content, encoding="utf-8")
    with pytest.raises(ce.PersistedUnreadableError):
        ce.persisted_vars(tmp_path / "ci_env.py")


def test_a_missing_file_is_refused(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ce.PersistedUnreadableError):
        ce.persisted_vars(tmp_path / "ci_env.py")


def test_the_real_table_is_the_ports_own() -> None:
    """The AST read and the import agree on the real file, so the gate sees exactly what `ci_env` writes."""
    real = paths.repo_root() / ce.CI_ENV_SUBPATH
    assert ce.persisted_vars(real) == sorted({name for name, _ in ci_env.PERSISTED}, key=str.encode)


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
    (tmp_path / ".ci/rediacc_ci/infra").mkdir(parents=True)
    (tmp_path / ce.CI_ENV_SUBPATH).write_text('PERSISTED = (("ONE", None),)\n', encoding="utf-8")
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert ce.main([]) == 1


def test_a_persisted_reference_passes(tmp_path: pathlib.Path, monkeypatch) -> None:
    """The mirror. Without it the refusal above could be a gate that refuses everything."""
    (tmp_path / ".ci/docker/ci").mkdir(parents=True)
    (tmp_path / ".ci/docker/ci/docker-compose.yml").write_text("a: ${ONE}\n", encoding="utf-8")
    (tmp_path / ".ci/rediacc_ci/infra").mkdir(parents=True)
    (tmp_path / ce.CI_ENV_SUBPATH).write_text('PERSISTED = (("ONE", None),)\n', encoding="utf-8")
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert ce.main([]) == 0


def test_selftest_is_green() -> None:
    assert ce.selftest() == 0


def test_the_real_tree_is_complete() -> None:
    """The gate against the actual repository."""
    assert ce.main([]) == 0
