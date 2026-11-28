"""`check:ci-prose-duplication` (agent/plans/PLAN-pr-loop-single-source.md W1): the pure helpers, driven directly.

The gate's `selftest()` plants each D6 control into a fixture tree. This file pins the helpers every verdict stands on, each in both directions (what must fire and what must not), because a helper that quietly widens or narrows moves every verdict at once:

  * `extract`: one normalization (`scope_mirrors.normalize`), markdown structure dropped, and every excluded region a run BREAK, never a join;
  * `registered_ids` and `scope_ranges`: a registered span's words stay in the corpus tagged with its clause, an unregistered anchor's words are untagged;
  * the exemption: only a word pair registered under ONE clause on both sides is skipped, so a canonical span still meets unregistered copies and other clauses' spans;
  * `shared_runs`: maximal runs only, the threshold inclusive at 25 and exclusive at 24.
"""

from __future__ import annotations

import pathlib
import tempfile

from rediacc_ci.quality import prose_duplication as pd

REG = {
    "clauses": {
        "pr.fix-rule": {"mirrors": [{"path": "m.md", "mode": "terms"}]},
        "pr.moved-rule": {"canonical": "a.md", "mirrors": [{"path": "CLAUDE.md", "mode": "ref"}]},
        "pr.quoted": {"mirrors": [{"path": "m.md", "mode": "verbatim", "where": "frontmatter:x"}]},
    }
}


def words(text: str, path: str = "x.md", registry: dict | None = None) -> list[str]:
    return [w.text for w in pd.extract(text, path, registry or REG).words]


def ext(path: str, tokens: list[str], segment_at: int = -1) -> pd.Extract:
    return pd.Extract(
        path,
        [pd.Word(t, i + 1, 1 if 0 <= segment_at <= i else 0) for i, t in enumerate(tokens)],
    )


def seq(n: int, stem: str = "w") -> list[str]:
    return ["%s%d" % (stem, i) for i in range(n)]


# --------------------------------------------------------------------------- extract


def test_extract_normalizes_markup_like_scope_mirrors() -> None:
    assert words("A **Bold** `Code` " + chr(0x201C) + "q" + chr(0x201D)) == [
        "a",
        "bold",
        "code",
        '"q"',
    ]


def test_extract_drops_markdown_structure_tokens() -> None:
    assert words("- one\n1. two\n| three | four |\n## five\n> six\n") == [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
    ]


def test_extract_keeps_words_that_only_look_like_structure() -> None:
    # A snake_case key, a flag and a version are content, not structure.
    assert words("commit_remind_min --changed 1.2.3") == ["commit_remind_min", "--changed", "1.2.3"]


def test_extract_reads_front_matter() -> None:
    assert words("---\ndescription: start the loop\n---\n\nbody\n") == [
        "description:",
        "start",
        "the",
        "loop",
        "body",
    ]


def test_extract_skips_comments_fences_indented_code_and_gen_docs() -> None:
    text = (
        "a <!-- hidden words -->\n\n```\nfenced\n```\n\n    indented\n\n"
        "<!-- >>> gen-docs:x -->\ngenerated\n<!-- <<< gen-docs -->\n\nb\n"
    )
    assert words(text) == ["a", "b"]


def test_every_excluded_region_is_a_break() -> None:
    ex = pd.extract("a\n\n```\nx\n```\n\nb\n", "x.md", REG)
    assert ex.words[0].segment != ex.words[1].segment
    plain = pd.extract("a\n\nb\n", "x.md", REG)
    assert plain.words[0].segment == plain.words[1].segment


def test_extract_line_numbers_survive_exclusions() -> None:
    ex = pd.extract("one\n\n```\nx\ny\n```\n\ntwo\n", "x.md", REG)
    assert [(w.text, w.line) for w in ex.words] == [("one", 1), ("two", 8)]


# --------------------------------------------------------------------------- registered spans


def test_registered_ids_reads_default_and_per_clause_canonical() -> None:
    assert pd.registered_ids(REG, "CLAUDE.md") == ({"pr.fix-rule", "pr.quoted"}, {"pr.moved-rule"})
    assert pd.registered_ids(REG, "a.md") == ({"pr.moved-rule"}, set())
    # A `where` mirror reads a front-matter key or a constant, never an inline anchor.
    assert pd.registered_ids(REG, "m.md") == (set(), {"pr.fix-rule"})


def tagged(text: str, path: str) -> list[tuple[str, frozenset[str]]]:
    return [(w.text, w.clauses) for w in pd.extract(text, path, REG).words]


def test_a_registered_mirror_span_stays_in_the_corpus_tagged() -> None:
    # The span's words are kept, so they are compared against unregistered text elsewhere; the tag only exempts them from the same clause's registered copies.
    assert tagged("x\n\n- <!-- scope: pr.fix-rule -->kept\n\ny\n", "m.md") == [
        ("x", frozenset()),
        ("kept", frozenset({"pr.fix-rule"})),
        ("y", frozenset()),
    ]


def test_an_unregistered_anchor_is_untagged_prose() -> None:
    assert tagged("- <!-- scope: pr.unknown-rule -->shown\n", "m.md") == [("shown", frozenset())]
    assert tagged("- <!-- scope: pr.fix-rule -->shown\n", "other.md") == [("shown", frozenset())]


def test_a_canonical_span_runs_to_its_close_across_blocks() -> None:
    text = "<!-- scope: pr.moved-rule -->one\n\ntwo<!-- /scope -->\n\nthree\n"
    moved = frozenset({"pr.moved-rule"})
    assert tagged(text, "a.md") == [("one", moved), ("two", moved), ("three", frozenset())]
    _, count = pd.scope_ranges(text, "a.md", REG)
    assert count == 1


# --------------------------------------------------------------------------- shared runs


def test_threshold_is_inclusive_at_25() -> None:
    assert [len(r.words) for r in pd.shared_runs(ext("a", seq(25)), ext("b", seq(25)))] == [25]
    assert pd.shared_runs(ext("a", seq(24)), ext("b", seq(24))) == []


def test_runs_are_maximal_and_located() -> None:
    a = ext("a", seq(5, "x") + seq(40))
    b = ext("b", seq(3, "y") + seq(40))
    runs = pd.shared_runs(a, b)
    assert [(len(r.words), r.line_a, r.line_b) for r in runs] == [(40, 6, 4)]


def test_a_break_in_either_file_splits_the_run() -> None:
    assert pd.shared_runs(ext("a", seq(40)), ext("b", seq(40), segment_at=20)) == []
    assert pd.shared_runs(ext("a", seq(40), segment_at=20), ext("b", seq(40))) == []


def tag(e: pd.Extract, clause: str, lo: int = 0, hi: int | None = None) -> pd.Extract:
    hi = len(e.words) if hi is None else hi
    e.words = [
        pd.Word(w.text, w.line, w.segment, frozenset({clause}) if lo <= k < hi else w.clauses)
        for k, w in enumerate(e.words)
    ]
    return e


def test_a_pair_registered_under_one_clause_is_exempt() -> None:
    assert pd.shared_runs(tag(ext("a", seq(40)), "pr.x"), tag(ext("b", seq(40)), "pr.x")) == []


def test_a_registered_span_against_unregistered_text_is_compared() -> None:
    runs = pd.shared_runs(tag(ext("a", seq(40)), "pr.x"), ext("b", seq(40)))
    assert [len(r.words) for r in runs] == [40]


def test_spans_of_different_clauses_are_compared() -> None:
    runs = pd.shared_runs(tag(ext("a", seq(40)), "pr.x"), tag(ext("b", seq(40)), "pr.y"))
    assert [len(r.words) for r in runs] == [40]


def test_an_exempt_stretch_splits_the_run_and_the_rest_is_judged() -> None:
    # Words 0-9 registered on both sides under one clause; 10-39 unregistered: one 30-word run, located at word 10.
    a = tag(ext("a", seq(40)), "pr.x", 0, 10)
    b = tag(ext("b", seq(40)), "pr.x", 0, 10)
    assert [(len(r.words), r.line_a, r.line_b) for r in pd.shared_runs(a, b)] == [(30, 11, 11)]
    # The same split leaving 24 words on each side of the exempt stretch reports nothing.
    a = tag(ext("a", seq(49)), "pr.x", 24, 25)
    b = tag(ext("b", seq(49)), "pr.x", 24, 25)
    assert pd.shared_runs(a, b) == []


def test_a_passage_repeated_in_one_file_is_reported_per_copy() -> None:
    a = ext("a", [*seq(30), "gap", *seq(30)])
    assert len(pd.shared_runs(a, ext("b", seq(30)))) == 2


def test_render_names_both_places_and_quotes_twelve_words() -> None:
    run = pd.Run("a.md", 3, "b.md", 9, seq(30))
    line = run.render()
    assert "a.md:3 ~ b.md:9 30 words:" in line
    assert '"w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 ..."' in line


# --------------------------------------------------------------------------- whole gate


def test_selftest_is_green() -> None:
    assert pd.selftest(verbose=False) == 0


def test_an_empty_root_is_a_refusal_not_a_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert pd.report(pathlib.Path(tmp)) == 2


def test_the_family_is_the_four_loop_files() -> None:
    assert pd.FAMILY == (
        "CLAUDE.md",
        ".claude/commands/pr-babysit.md",
        ".claude/agents/pr-babysitter.md",
        ".claude/commands/landing.md",
    )
    assert pd.THRESHOLD == 25


def test_the_selftest_unpacking_survives_a_wider_family() -> None:
    """Review e1ecd8e0.2: the module-level unpacking names the first four files and swallows the rest, so widening FAMILY cannot stop the import."""
    line = next(
        ln
        for ln in pathlib.Path(pd.__file__).read_text(encoding="utf-8").splitlines()
        if ln.startswith("CLAUDE_MD, FIX_LAUNCHER")
    )
    scope: dict = {"FAMILY": tuple("f%d.md" % i for i in range(7))}
    exec(compile(line, "<unpack>", "exec"), scope)
    assert scope["FIX_MERGE"] == "f3.md"
    assert scope["_BEYOND_FIXTURES"] == ["f4.md", "f5.md", "f6.md"]
    assert list(pd.FAMILY[4:]) == pd._BEYOND_FIXTURES
