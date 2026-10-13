"""`.ci/scripts/quality/check_guard_mention_anchoring.py`: every alternative is probed, and an anchor counts only where it governs every alternative.

THE FINDING THIS FILE PINS (worklist #d53494b0, from the writer of 276a69db9). A draft block_worktree_add pattern `(rediacc_ci(\\.__main__)?[{S}]+worktree|rediacc_ci\\.dev\\.worktree|(^|[^A-Za-z0-9_])worktree\\.py)[{S}]+create` passed the gate at rc 0 while the guard refused `echo the docs say never to run rediacc_ci.dev.worktree create in this repo` at rc 2. Three things let it through: the instantiator rendered each alternation through its FIRST branch only,
it rendered `[{S}]+` as a literal `x` so that branch's probe could not match anything, and the static tier's anchor test was a substring search for `(^|` that one alternative satisfied for all of them.

THE SECOND FINDING (worklist #ecb59527). A four-character floor in `probes_of` dropped every short instance, so block_binary_deploy's unanchored `(^|[{B}])scp[{B}]` was never probed, and its plain probe could not have reached the guard's `host:` destination test anyway. The tests at the end pin the worded-or-fragment provenance, the argument-shaped second template, and the
three-way rule (anchored, worded and silent, or a declared FRAGMENTS entry that is not stale).
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
    # Both templates for both instances: a worded instance is probed with the argument-shaped sentence too (#32e75fa4), and each sentence still carries the phrase.
    assert set(detail.split(gma.PROSE_SEP)) == {
        *gma.sentences_of("frobnicate widgets"),
        *gma.sentences_of("grommet gadgets"),
    }


def test_an_unlisted_guard_still_stops_at_the_first_refusal(tmp_path: pathlib.Path) -> None:
    # The other direction: outside PROSE_TARGETS the verdict is one offending instance, never a joined list.
    pattern = r"frobnicate[ \t]+widgets|grommet[ \t]+gadgets"
    guard = tmp_path / "plain_offender.py"
    guard.write_text(gma._COMMAND_FIXTURE.format(pattern=pattern, extra=""))
    got, detail = gma.assess(guard, "command", "")
    assert got == "prose"
    assert gma.PROSE_SEP not in detail


@pytest.mark.parametrize(
    ("pattern", "want"),
    [
        (r"(^|[ \t])scp[ \t]", {"scp": True}),
        (r"go|gofmt", {"go": True, "gofmt": True}),
        # Fragments: every word character was CHOSEN by the renderer, or the literal run is one character long.
        (r"\$[A-Za-z_]+", {"$x": False}),
        (r"--dry-run|-n", {"--dry-run": True, "-n": False}),
        (r"\bP([0-3])\b", {"P1": False}),
        (r"[0-9a-f]{7,40}", {"aaaaaaa": False}),
    ],
)
def test_provenance_separates_words_from_fragments(pattern: str, want: dict) -> None:
    assert dict(gma.expand_marked(pattern)[0]) == want


def test_a_planted_scp_style_guard_is_refused_through_the_second_template(
    tmp_path: pathlib.Path,
) -> None:
    # The block_binary_deploy shape: a short command name at a word boundary that refuses only when the last field is a `host:` spec.
    guard = tmp_path / "argshape.py"
    guard.write_text(gma._ARGSHAPE_FIXTURE.format(pattern=r"(^|[ \t])zcp[ \t]"))
    assert not gma.fires(guard, gma.sentence("zcp")), "the plain template must not reach it"
    assert gma.fires(guard, "zcp a.sh host:/dst/a.sh"), "the fixture must refuse its own command"
    assert gma.assess(guard, "command", "") == ("prose", gma.argument_sentence("zcp"))
    # The other direction: anchored, the same guard is silent through both templates and still refuses the real command.
    anchored = tmp_path / "argshape_anchored.py"
    anchored.write_text(gma._ARGSHAPE_FIXTURE.format(pattern=r"(^|[;&|(])[ \t]*zcp[ \t]"))
    assert gma.assess(anchored, "command", "") == ("clean", "")
    assert gma.fires(anchored, "true && zcp a.sh host:/dst/a.sh")


@pytest.mark.parametrize("name", ["zsync", "zftps"])
def test_a_long_command_name_that_needs_a_host_is_probed_with_arguments(
    tmp_path: pathlib.Path, name: str
) -> None:
    # #32e75fa4 (review a2d44aa4.3): the second template was gated on `len(instance) < SHORT_INSTANCE`, so an `rsync`/`sftp`-shaped matcher of four or more characters that refuses only on a `host:` last field was never asked an argument-shaped sentence, and was clean.
    guard = tmp_path / "argshape_long.py"
    guard.write_text(gma._ARGSHAPE_FIXTURE.format(pattern=r"(^|[ \t])%s[ \t]" % name))
    assert not gma.fires(guard, gma.sentence(name)), "the plain template must not reach it"
    assert gma.fires(guard, "%s a.sh host:/dst/a.sh" % name), (
        "the fixture must refuse its own command"
    )
    assert gma.assess(guard, "command", "") == ("prose", gma.argument_sentence(name))
    anchored = tmp_path / "argshape_long_anchored.py"
    anchored.write_text(gma._ARGSHAPE_FIXTURE.format(pattern=r"(^|[;&|(])[ \t]*%s[ \t]" % name))
    assert gma.assess(anchored, "command", "") == ("clean", "")
    assert gma.fires(anchored, "true && %s a.sh host:/dst/a.sh" % name)


@pytest.mark.parametrize("order", [(r"\w\w\w\w\w", "xxxxx"), ("xxxxx", r"\w\w\w\w\w")])
def test_a_text_any_pattern_spells_as_a_word_is_worded_in_either_order(order: tuple) -> None:
    """Review 5aa562c3.2: `\\w\\w\\w\\w\\w` renders `xxxxx` as a fragment and the literal pattern renders it as a word. The instance is probed once, and it earns the argument-shaped template whichever pattern came first; it did only when the literal came first."""
    probes = gma.probes_of(list(order))
    assert probes.instances == ["xxxxx"]
    assert probes.worded == {"xxxxx"}
    assert probes.texts("xxxxx") == [gma.sentence("xxxxx"), gma.argument_sentence("xxxxx")]


def test_a_short_worded_instance_is_probed_not_unprobed(tmp_path: pathlib.Path) -> None:
    probes = gma.probes_of([r"(^|[;&|(])[ \t]*(ab|cd+)"])
    assert set(probes.instances) == {"ab", "cd"}
    assert probes.fragments == 0
    assert gma.sentences_of("ab") == [gma.sentence("ab"), gma.argument_sentence("ab")]
    # Every WORDED instance gets both templates, whatever its length (#32e75fa4); an unworded one, never shorter than SHORT_INSTANCE here, gets only the plain one.
    assert gma.sentences_of("abcd") == [gma.sentence("abcd"), gma.argument_sentence("abcd")]
    assert gma.sentences_of("> x.x", worded=False) == [gma.sentence("> x.x")]
    guard = tmp_path / "short.py"
    guard.write_text(gma._COMMAND_FIXTURE.format(pattern=r"(^|[;&|(])[ \t]*(ab|cd+)", extra=""))
    assert gma.assess(guard, "command", "")[0] == "clean"


def test_an_undeclared_unworded_pattern_is_red_and_a_declared_one_is_not(
    tmp_path: pathlib.Path,
) -> None:
    guard = tmp_path / "fragment.py"
    guard.write_text(
        gma._COMMAND_FIXTURE.format(
            pattern=r"(^|[;&|(])[ \t]*frobnicate[ \t]+widgets",
            extra='OTHER = re.compile(r"\\$[A-Za-z_]+")',
        )
    )
    assert gma.assess(guard, "command", "", {}) == ("unprobed", "OTHER")
    declared = {(guard.name, "OTHER"): gma._FIXTURE_FRAGMENT}
    assert gma.assess(guard, "command", "", declared) == ("clean", "")


@pytest.mark.parametrize(
    ("key", "reason", "want"),
    [
        (("fragment.py", "GONE"), None, "no matcher-shaped constant"),
        (("fragment.py", "PAT"), None, "anchored at command position"),
        (("fragment.py", "WORDY"), None, "renders a worded instance"),
        (("missing.py", "OTHER"), None, "no longer exists"),
        (("fragment.py", "OTHER"), "BLOCKER: too short", "too short"),
        (("fragment.py", "OTHER"), "a reason without the prefix, long enough", "BLOCKER:"),
    ],
)
def test_a_stale_or_malformed_fragments_entry_is_red(
    tmp_path: pathlib.Path, key: tuple, reason: str | None, want: str
) -> None:
    (tmp_path / "fragment.py").write_text(
        gma._COMMAND_FIXTURE.format(
            pattern=r"(^|[;&|(])[ \t]*frobnicate[ \t]+widgets",
            extra='OTHER = re.compile(r"\\$[A-Za-z_]+")\nWORDY = re.compile(r"(^|[ \\t])zcp[ \\t]+")',
        )
    )
    # The valid declaration is the control: it must produce nothing, or every row below proves nothing.
    assert gma.fragment_findings({("fragment.py", "OTHER"): gma._FIXTURE_FRAGMENT}, tmp_path) == []
    found = gma.fragment_findings({key: reason or gma._FIXTURE_FRAGMENT}, tmp_path)
    assert len(found) == 1
    assert want in found[0]


def test_the_live_fragments_declarations_are_not_stale() -> None:
    assert gma.fragment_findings(gma.FRAGMENTS) == []
