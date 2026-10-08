"""`check:ci-scope-mirrors` (agent/plans/PLAN-scope-mirrors.md SM2): the pure helpers, driven directly.

The gate's `selftest()` plants one defect per check into a fixture tree. This file pins the four helpers every check stands on, each in both directions (what must be recognised and what must not), because a helper that quietly widens or narrows moves every verdict at once while the selftest's single fixture may not notice:

  * `normalize`, the D4 order;
  * the anchor parser, including the backtick and fence controls (an anchor written as documentation is prose) and the mirror span rules;
  * `quote_fragments`, the split on `...`, `[...]` and U+2026, in both directions: a marked cut is two fragments, and an unmarked cut is one fragment that the canonical text does not contain;
  * `py_constant`, the `ast` reader that never imports the module it reads.
"""

from __future__ import annotations

import pathlib
import tempfile

from rediacc_ci.quality import scope_mirrors as sm

ELLIPSIS = chr(0x2026)
EM_DASH = chr(0x2014)


# --------------------------------------------------------------------------- normalize


def test_normalize_runs_the_d4_order() -> None:
    raw = (
        "A <!-- scope: pr.abc -->**Bold** __u__ `code`"
        + EM_DASH
        + chr(0x201C)
        + "q"
        + chr(0x201D)
        + "\n\t  End"
    )
    assert sm.normalize(raw) == 'a bold u code--"q" end'


def test_normalize_keeps_what_is_not_markup() -> None:
    # A single `*` or `_` is content (snake_case keys, list bullets), and must survive.
    assert sm.normalize("`turbo_push: batch-end` * x") == "turbo_push: batch-end * x"
    assert sm.normalize("Plan:") != sm.normalize("Plan")


def test_normalize_folds_the_ellipsis_character() -> None:
    assert sm.normalize("a" + ELLIPSIS + "b") == "a...b"


def test_span_sha_ignores_markup_but_not_words() -> None:
    assert sm.span_sha("**every** `2` hours") == sm.span_sha("every 2   hours")
    assert sm.span_sha("every 2 hours") != sm.span_sha("every 3 hours")


# --------------------------------------------------------------------------- anchor parser


def test_a_bare_anchor_with_a_note_opens() -> None:
    marks = sm.parse_anchors("text <!-- scope: pr.plan-set -- why it is here -->rest\n")
    assert [(m.kind, m.clause) for m in marks] == [("open", "pr.plan-set")]


def test_a_close_is_recognised() -> None:
    marks = sm.parse_anchors("<!-- scope: pr.plan-set -->x<!-- /scope -->\n")
    assert [m.kind for m in marks] == ["open", "close"]


def test_an_anchor_in_a_backtick_span_is_prose() -> None:
    assert sm.parse_anchors("Write `<!-- scope: pr.plan-set -->` to anchor.\n") == []
    assert sm.parse_anchors("Write ``<!-- scope: pr.plan-set -->`` too.\n") == []


def test_an_anchor_in_a_fence_is_prose() -> None:
    for fence in ("```", "~~~", "````"):
        text = "%s\n<!-- scope: pr.plan-set -->\n%s\n" % (fence, fence)
        assert sm.parse_anchors(text) == [], fence


def test_an_anchor_in_an_indented_code_block_is_prose() -> None:
    assert sm.parse_anchors("# H\n\n    <!-- scope: pr.plan-set -->\n") == []


def test_an_anchor_after_a_closed_fence_is_live() -> None:
    text = "```\ncode\n```\n\n<!-- scope: pr.plan-set -->x\n"
    assert [m.kind for m in sm.parse_anchors(text)] == ["open"]


def test_a_list_continuation_is_not_mistaken_for_code() -> None:
    text = "- item\n\n    <!-- scope: pr.plan-set -->continued\n"
    assert [m.kind for m in sm.parse_anchors(text)] == ["open"]


def test_a_malformed_id_is_reported_not_dropped() -> None:
    for body in ("scope: PR.Upper", "scope: pr.ab", "scope:", "scope pr.plan-set"):
        marks = sm.parse_anchors("<!-- %s -->\n" % body)
        assert [m.kind for m in marks] == ["malformed"], body


def test_an_unrelated_comment_is_ignored() -> None:
    assert sm.parse_anchors("<!-- >>> gen-docs:x -->\n<!-- scoped elsewhere -->\n") == []


def test_canonical_spans_reads_a_closed_span() -> None:
    spans, problems = sm.canonical_spans("a <!-- scope: pr.abc -->one two<!-- /scope --> b\n")
    assert problems == []
    assert sm.normalize(spans["pr.abc"].raw) == "one two"


def test_canonical_spans_refuses_unclosed_nested_and_stray() -> None:
    _, problems = sm.canonical_spans("<!-- scope: pr.abc -->x\n")
    assert any("never closed" in p for p in problems)
    _, problems = sm.canonical_spans(
        "<!-- scope: pr.abc -->x<!-- scope: pr.def -->y<!-- /scope -->\n"
    )
    assert any("do not nest" in p for p in problems)
    _, problems = sm.canonical_spans("x<!-- /scope -->\n")
    assert any("closes nothing" in p for p in problems)


def test_mirror_span_ends_at_its_block_without_a_close() -> None:
    spans = sm.mirror_spans("- <!-- scope: pr.abc -->one\n- two\n\npara\n", "m.md")
    assert [sm.normalize(s.raw) for s in spans] == ["one"]


def test_mirror_close_never_crosses_a_blank_line() -> None:
    spans = sm.mirror_spans("<!-- scope: pr.abc -->one\n\ntwo<!-- /scope -->\n", "m.md")
    assert [sm.normalize(s.raw) for s in spans] == ["one"]


def test_mirror_spans_in_one_block_each_run_to_its_end() -> None:
    spans = sm.mirror_spans("<!-- scope: pr.abc -->a <!-- scope: pr.def -->b\n\nc\n", "m.md")
    assert {s.clause: sm.normalize(s.raw) for s in spans} == {"pr.abc": "a b", "pr.def": "b"}


def test_frontmatter_span_reads_one_key_only() -> None:
    text = "---\nname: x\ndescription: one\n  two\ntools: Bash\n---\nbody\n"
    span = sm.frontmatter_span(text, "description", "a.md")
    assert span is not None
    assert sm.normalize(span.raw) == "one two"
    assert sm.frontmatter_span(text, "summary", "a.md") is None


# --------------------------------------------------------------------------- quote fragments


def test_quote_fragments_split_on_every_ellipsis_spelling() -> None:
    text = '"alpha... beta [...] gamma' + ELLIPSIS + ' delta."'
    assert sm.quote_fragments(text) == ["alpha", "beta", "gamma", "delta"]


def test_a_marked_cut_is_a_true_quote() -> None:
    canonical = sm.normalize(
        "put the whole cluster into a single plan (root cause, siblings) and ask to run it."
    )
    for mark in ("...", ELLIPSIS, "[...]"):
        frags = sm.quote_fragments(
            '"put the whole cluster into a single plan %s and ask to run it."' % mark
        )
        assert len(frags) == 2, mark
        assert all(sm.normalize(f) in canonical for f in frags), mark


def test_an_unmarked_cut_is_a_misquote() -> None:
    canonical = sm.normalize(
        "put the whole cluster into a single plan (root cause, siblings) and ask to run it."
    )
    frags = sm.quote_fragments('"put the whole cluster into a single plan and ask to run it."')
    assert len(frags) == 1
    assert sm.normalize(frags[0]) not in canonical


def test_smart_quotes_are_quotes_too() -> None:
    assert sm.quote_fragments(chr(0x201C) + "curly" + chr(0x201D)) == ["curly"]


def test_no_quotes_is_no_fragments() -> None:
    assert sm.quote_fragments("nothing quoted here") == []


# --------------------------------------------------------------------------- ast constant reader


SOURCE = '''
import os
KINDS = ("ci-cd", "red-fix")
NOTE: str = """multi
line"""
DYNAMIC = os.environ.get("X", "y")
def f():
    INNER = ("not", "module", "level")
'''


def test_py_constant_reads_tuples_and_annotated_strings() -> None:
    assert sm.py_constant(SOURCE, "KINDS") == (("ci-cd", "red-fix"), 3)
    value, line = sm.py_constant(SOURCE, "NOTE")
    assert value == "multi\nline"
    assert line == 4


def test_py_constant_refuses_what_is_not_a_module_literal() -> None:
    assert sm.py_constant(SOURCE, "DYNAMIC")[0] is sm.MISSING
    assert sm.py_constant(SOURCE, "INNER")[0] is sm.MISSING
    assert sm.py_constant(SOURCE, "ABSENT")[0] is sm.MISSING
    assert sm.py_constant("def (:\n", "KINDS")[0] is sm.MISSING


def test_py_constant_never_imports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sentinel = pathlib.Path(tmp) / "imported"
        source = "open(%r, 'w').write('x')\nKINDS = ('a',)\n" % str(sentinel)
        assert sm.py_constant(source, "KINDS")[0] == ("a",)
        assert not sentinel.exists(), "reading the constant executed the module"


def test_constant_values_accepts_string_collections_only() -> None:
    assert sm.constant_values(("b", "a")) == ["a", "b"]
    assert sm.constant_values({"k": 1}) == ["k"]
    assert sm.constant_values(("a", 1)) is None
    assert sm.constant_values("abc") is None
