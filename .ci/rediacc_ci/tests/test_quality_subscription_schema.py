"""`rediacc_ci.quality.subscription_schema` seams the shadow ledger cannot isolate.

The whole gate is three phases of external tooling (npx tsx, npx biome, diff, go
test) and is covered end to end by
`.ci/shadow/w7p2-subscription-schema.observations.jsonl` over five distinct
trees. What that ledger CANNOT isolate is the branch each phase takes when its
tool is absent, because a fixture always supplies one. Those are here.
"""

import pathlib

import pytest

from rediacc_ci.quality import subscription_schema as mod
from rediacc_ci.tests import differential as diff

# The shapes `diff -q` rules on. Each is a pair (a-content, b-content-or-None).
DIFF_CASES = [
    ('{"x":1}\n', '{"x":1}\n'),  # identical
    ('{"x":1}\n', '{"x":2}\n'),  # a changed value
    ('{"x":1}\n', '{"x":1}'),  # a missing final newline IS a difference
    ('{"x":1}\n', ""),  # empty
    ('{"x":1}\n', None),  # absent: diff exits 2, which the twin reads as "differ"
]


@pytest.mark.parametrize(("left", "right"), DIFF_CASES)
def test_files_differ_matches_diff_q(tmp_path: pathlib.Path, left: str, right) -> None:
    a = tmp_path / "a.json"
    a.write_text(left, encoding="utf-8")
    b = tmp_path / "b.json"
    if right is not None:
        b.write_text(right, encoding="utf-8")
    code, _out, _err = diff.bash_streams("diff -q a.json b.json", cwd=str(tmp_path))
    assert mod.files_differ(a, b) is (code != 0)


def test_require_submodule_fails_closed_in_ci(tmp_path: pathlib.Path) -> None:
    """Absent in CI is a HARD failure; absent locally is a warn-and-skip.

    `check:ci-renet` rides on this and carries govulncheck, deadcode and
    golangci-lint. All three would report success while checking nothing, which
    is why the two environments cannot share an answer.
    """
    missing = tmp_path / "nope"
    assert mod.require_submodule(missing, "L", env={"CI": "false"}) is False
    with pytest.raises(SystemExit):
        mod.require_submodule(missing, "L", env={"CI": "true"})


def test_require_submodule_accepts_a_file_gitlink(tmp_path: pathlib.Path) -> None:
    """`-e`, not `-d`: a real submodule checkout's `.git` is a FILE."""
    gitlink = tmp_path / "sub"
    gitlink.write_text("gitdir: ../.git/modules/sub\n", encoding="utf-8")
    assert mod.require_submodule(gitlink, "L", env={}) is True


def test_a_missing_tool_is_127_and_never_an_exception(tmp_path: pathlib.Path, monkeypatch) -> None:
    """command-not-found is 127 in a shell and must be 127 here.

    Getting this wrong is the easiest way for a shell port to diverge: Python
    raises where bash returns, and an uncaught FileNotFoundError would produce a
    traceback and exit 1 where the twin exits 127 silently.
    """
    monkeypatch.setenv("PATH", str(tmp_path / "no-such-bin"))
    assert mod.generate(tmp_path, tmp_path / "out.json") == mod.NOT_FOUND


def test_a_formatter_that_cannot_run_leaves_a_comparable_file(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Formatting is cosmetic; an unformatted comparison is still valid.

    The failure this rules out is worse than a formatting nit: an empty
    `schema.formatted.json` would make every schema read as STALE.
    """
    fresh = tmp_path / "fresh.json"
    fresh.write_text('{"generated":true}\n', encoding="utf-8")
    formatted = tmp_path / "formatted.json"
    monkeypatch.setenv("PATH", str(tmp_path / "no-such-bin"))
    mod.format_through_stdin(tmp_path, fresh, formatted)
    # PATH is restored BEFORE the comparison, because `files_differ` shells out
    # to `diff` and an empty PATH would make it answer "they differ" for the
    # wrong reason -- which would pass this assertion while proving nothing.
    monkeypatch.undo()
    assert formatted.read_text(encoding="utf-8") == '{"generated":true}\n'
    assert mod.files_differ(fresh, formatted) is False
