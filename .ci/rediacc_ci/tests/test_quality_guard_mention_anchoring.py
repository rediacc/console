"""`.ci/scripts/quality/check_guard_mention_anchoring.py`: every alternative is probed, and an anchor counts only where it governs every alternative.

THE FINDING THIS FILE PINS (worklist #d53494b0, from the writer of 276a69db9). A draft block_worktree_add pattern `(rediacc_ci(\\.__main__)?[{S}]+worktree|rediacc_ci\\.dev\\.worktree|(^|[^A-Za-z0-9_])worktree\\.py)[{S}]+create` passed the gate at rc 0 while the guard refused `echo the docs say never to run rediacc_ci.dev.worktree create in this repo` at rc 2. Three things let it through: the instantiator rendered each alternation through its FIRST branch only,
it rendered `[{S}]+` as a literal `x` so that branch's probe could not match anything, and the static tier's anchor test was a substring search for `(^|` that one alternative satisfied for all of them.
"""

import importlib.util
import pathlib
import re

import pytest

from rediacc_ci import paths

SCRIPTS = paths.from_root(".ci", "scripts", "quality")


def _load():
    # The script's own `import _cipath` shim lives beside it.
    paths.on_sys_path(SCRIPTS)
    spec = importlib.util.spec_from_file_location(
        "check_guard_mention_anchoring_under_test", SCRIPTS / "check_guard_mention_anchoring.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gma = _load()


@pytest.mark.parametrize(
    ("pattern", "anchored"),
    [
        (r"(^|[;&|(]|\$\(|`)[ \t]*git[ \t]+worktree", True),
        (r"(^|[;&|(])\s*(frob|grom)", True),
        (r"(?=x)(^|;)x", True),
        # Must NOT count: the anchor governs one alternative only.
        (r"(^|[;&|(])\s*frob|grom", False),
        (r"(alpha|beta|(^|[^A-Za-z0-9_])gamma)\.py", False),
        # Must NOT count: whitespace and a negated class are word boundaries, not command position.
        (r"(^|[ \t])rm[ \t]", False),
        (r"(^|[^a-z])worktree", False),
        # Must NOT count: an optional prefix in front of the anchor.
        (r"((bash|sh)\s+)?(^|;)run", False),
        # Unparsable is never anchored.
        (r"(^|[;&", False),
    ],
)
def test_command_anchored_requires_every_alternative(pattern: str, anchored: bool) -> None:
    assert gma.command_anchored(pattern) is anchored


def test_every_alternative_is_rendered_and_whitespace_is_a_space() -> None:
    got = gma.instances(r"(alpha|beta|(^|[^A-Za-z0-9_])gamma)[ \t\n]+widgets")
    assert {"alpha widgets", "beta widgets", "gamma widgets"} <= set(got)


def test_the_worktree_draft_renders_the_mention_the_guard_refused() -> None:
    space = r" \t\n\v\f\r"
    draft = (
        rf"(rediacc_ci(\.__main__)?[{space}]+worktree|rediacc_ci\.dev\.worktree|"
        rf"(^|[^A-Za-z0-9_])worktree\.py)[{space}]+create([{space}]|$)"
    )
    got = gma.instances(draft)
    assert "rediacc_ci.dev.worktree create" in got
    assert "worktree.py create" in got
    assert not gma.command_anchored(draft)


def test_instances_match_their_own_pattern_on_the_house_spellings() -> None:
    for pattern in (
        r"git\s+commit[^|;&]*--allow-empty",
        r"(^|[;&|(]|&&|\|\|)\s*git\s+commit[^|;&]*--allow-empty",
        r"(^|[;&|(]|\$\(|`)[ \t]*git([ \t]+-[A-Za-z-]+([ \t]+[^ ;&|]+)?)*[ \t]+worktree[ \t]+add([ \t]|$)",
    ):
        first = gma.instantiate(pattern)
        assert re.search(pattern, first), (pattern, first)


def test_lookaround_syntax_never_leaks() -> None:
    got = gma.instances(r"(^|[;&|(])\s*git\b[^;&|]*commit(?=$|[\s;&|])")
    assert got[0] == "git commit"
    assert not any("?=" in i or "?!" in i for i in got)


def test_an_unparsable_message_is_not_a_matcher(tmp_path: pathlib.Path) -> None:
    guard = tmp_path / "message_only.py"
    guard.write_text('CHAIN = "pre-bash"\nFOOTER = "see (pyproject.toml [tool.ruff+ for it"\n')
    assert gma.patterns_of(guard) == []


@pytest.mark.parametrize("row", gma._ALTERNATION_ROWS, ids=lambda r: r[0])
def test_planted_alternation_guards(tmp_path: pathlib.Path, row: tuple) -> None:
    name, pattern, extra, want, why = row
    guard = tmp_path / name
    guard.write_text(gma._COMMAND_FIXTURE.format(pattern=pattern, extra=extra))
    got, detail = gma.assess(guard, "command", "")
    assert got == want, f"{why}: {got} ({detail})"


def test_the_gates_own_controls_pass() -> None:
    gma.controls()


def test_a_prose_target_reports_every_refused_sentence(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The exemption is per guard, so the first refused sentence must not vouch for the rest: a mention-matcher added beside the target would otherwise ride on it unseen.
    pattern = r"frobnicate[ \t]+widgets|grommet[ \t]+gadgets"
    guard = tmp_path / "prose_target.py"
    guard.write_text(gma._COMMAND_FIXTURE.format(pattern=pattern, extra=""))
    monkeypatch.setitem(gma.PROSE_TARGETS, guard.name, "BLOCKER: a planted prose target")
    got, detail = gma.assess(guard, "command", "")
    assert got == "prose"
    assert set(detail.split(gma.PROSE_SEP)) == {"frobnicate widgets", "grommet gadgets"}


def test_an_unlisted_guard_still_stops_at_the_first_refusal(tmp_path: pathlib.Path) -> None:
    # The other direction: outside PROSE_TARGETS the verdict is one offending instance, never a joined list.
    pattern = r"frobnicate[ \t]+widgets|grommet[ \t]+gadgets"
    guard = tmp_path / "plain_offender.py"
    guard.write_text(gma._COMMAND_FIXTURE.format(pattern=pattern, extra=""))
    got, detail = gma.assess(guard, "command", "")
    assert got == "prose"
    assert gma.PROSE_SEP not in detail
