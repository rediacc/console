"""`rediacc_ci.quality.prose_style`, driven mostly by the rules file's own examples.

WHAT IS WORTH TESTING HERE, and it is not "does the regex match". Every rule in `.ci/config/prose-style-rules.json` ships with `examples`, and those examples ARE the fixtures: this module generates one pytest case per example rather than restating them, so a rule whose example stops being detected reds without anybody remembering to write a second copy. The alternative -- a
hand-written fixture list beside the rules -- is two places to change and one of them always rots.

THE THREE EXPECTATIONS, and the third one is the honest part:

    flag        at least one rule must fire, and when the OWNING rule carries
                patterns, the owning rule must be among them
    clean       no rule may fire
    undetected  declared beyond mechanical detection, asserted NOT to fire, and
                COUNTED, so the coverage gap is a number in the output instead of
                a sentence in a comment somebody stops reading

`undetected` is not a skip and is not an excuse. R12's bad example "The project failed." and R3's good example "The build failed after the last change." are the same surface shape; a pattern catching one catches the other. The rules file says so, this file asserts the consequence, and `test_undetectable_set_is_small_and_declared` keeps the set from quietly growing into a way of
retiring rules.

THE REST OF THIS FILE IS THE EXTRACTOR, which is where a prose linter actually lives. Matching four characters is easy; deciding that the four characters inside a fence, an inline code span, a blockquote or a `bad:` exemplar are not prose is the entire gate, and each of those is a way for it to go green while meaning nothing.
"""

import ast
import contextlib
import json
import os
import pathlib
import re
import subprocess

import pytest

from rediacc_ci import gitx, paths
from rediacc_ci.quality import prose_style as ps

ROOT = paths.repo_root()
GLOBALS, RULES = ps.load_rules_file(ROOT)
BY_ID = {rule.id: rule for rule in RULES}


def _fired(text, scope="markdown"):
    return [f.rule for f in ps.lint_message(text, RULES, GLOBALS, scope)]


# --------------------------------------------------------------------------- The rules file itself ---------------------------------------------------------------------------


def test_the_rules_file_is_not_empty():
    """A rule set that collapsed to nothing would make every case below vacuous."""
    assert len(RULES) >= 18, (
        "only %d rule(s) loaded from %s; the brief declares R1-R18, and below that every "
        "example case in this file is passing over a rule that is not there"
        % (len(RULES), ps.RULES_FILE)
    )
    assert {r.id for r in RULES} >= {"R%d" % n for n in range(1, 19)}


def test_every_rule_carries_at_least_one_example():
    """An example-driven suite is only as wide as the examples.

    A rule with none contributes ZERO cases below and is indistinguishable, from the outside, from a rule that passes.
    """
    bare = [r.id for r in RULES if not r.examples]
    assert not bare, "these rules ship no example, so nothing here exercises them: %s" % bare


def test_every_rule_has_a_good_example():
    """The NEGATIVE direction, per rule.

    A rule with only `bad` examples is a rule this suite cannot catch over-matching on, and an over-matching prose rule flags the whole tree.
    """
    one_sided = [r.id for r in RULES if not any(e.get("kind") == "good" for e in r.examples)]
    assert not one_sided, (
        "these rules ship no `good` example, so nothing proves they do not fire on the "
        "rewritten sentence: %s" % one_sided
    )


# --------------------------------------------------------------------------- The examples, as cases ---------------------------------------------------------------------------

EXAMPLES = [
    (rule.id, index, example) for rule in RULES for index, example in enumerate(rule.examples)
]


@pytest.mark.parametrize(
    ("rule_id", "index", "example"),
    EXAMPLES,
    ids=["%s-%d-%s" % (r, i, e.get("expect")) for r, i, e in EXAMPLES],
)
def test_example(rule_id, index, example):
    del index  # part of the case id, not of the assertion
    rule = BY_ID[rule_id]
    text = example["text"]
    expect = example["expect"]
    # SCOPE MATTERS AND IS NOT ALWAYS `markdown`. R8 and R11 are scoped, and an example run under a scope its own rule excludes would assert the opposite of what it was written to assert.
    scope = "markdown" if rule.applies_to("markdown") else rule.scopes[0]
    fired = _fired(text, scope)

    if expect == "clean":
        assert not fired, (
            "%s's good example fired %s: %r. A rule that flags its own counter-example "
            "flags the tree." % (rule_id, fired, text)
        )
        return
    if expect == "undetected":
        assert not fired, (
            "%s declares %r as beyond mechanical detection, and something now detects it "
            "(%s). That is good news, not a failure -- move the example to `flag` and "
            "remove the `undetected` declaration." % (rule_id, text, fired)
        )
        return
    assert fired, "%s's bad example fired nothing: %r" % (rule_id, text)
    # WHICH RULE HAD TO CATCH IT. `caught_by` lets an example say that the rule really covering it is a neighbour -- R11's `Your feedback...` is caught by R1's `\byour\b`, and R11 duplicating that pattern would be two spellings of one rule. Naming it is the point: without it the assertion has to soften to "something fired", and then an example quietly leaning on a neighbour is
    # indistinguishable from one its own rule covers.
    owner = example.get("caught_by", rule_id)
    if BY_ID[owner].raw_patterns or BY_ID[owner].detection == "measured":
        assert owner in fired, (
            "%s's bad example was expected to be caught by %s and fired %s instead: %r"
            % (rule_id, owner, fired, text)
        )


def test_undetectable_set_is_small_and_declared():
    """`undetected` must stay a declared exception, never a drain.

    Without a ceiling, the cheapest way to make any future rule pass is to mark its examples undetectable, which retires the rule while leaving it in the documentation looking enforced.
    """
    undetected = [
        (r.id, e["text"]) for r in RULES for e in r.examples if e.get("expect") == "undetected"
    ]
    assert len(undetected) <= 5, (
        "%d example(s) are declared beyond mechanical detection: %s. Above a handful this "
        "stops being a declared exception and starts being how rules get retired."
        % (len(undetected), undetected)
    )
    for rule_id, _ in undetected:
        assert BY_ID[rule_id].detection == "advisory", (
            "%s declares an undetectable example while claiming to detect things. A rule "
            "with patterns whose own example is undetectable is two claims that disagree." % rule_id
        )


# --------------------------------------------------------------------------- The extractor, which is where the gate actually lives ---------------------------------------------------------------------------

EXTRACTION = [
    # (label, text, must_fire)
    ("plain prose fires", "Did you run the tests?", True),
    ("a fence is not prose", "```\nDid you run the tests?\n```", False),
    ("a ~~~ fence closes on ~~~", "~~~\nDid you run it?\n~~~", False),
    ("a longer closing fence closes a shorter one", "```\nDid you run it?\n`````", False),
    ("an inline code span is not prose", "The flag is `you` here.", False),
    ("a double-backtick span closes correctly", "Use ``a `you` b`` here.", False),
    ("a link TARGET is not prose", "See [the doc](docs/you-and-me.md).", False),
    ("a link TEXT is", "See [what you did](x.md).", True),
    ("a bare url is not prose", "Read https://x.test/you/here now.", False),
    ("an autolink is not prose", "Read <https://x.test/you> now.", False),
    ("a blockquote is somebody else's words", "> Did you run the tests?", False),
    ("a `bad:` exemplar carries its violation", "bad: Did you run the tests?", False),
    ("a `- bad:` list exemplar too", "- bad: Did you run the tests?", False),
    ("a `good:` line is NOT exempt", "good: Did you run the tests?", True),
    ("a heading is not linted", "## Did you run the tests?", False),
    ("an indented block is code", "    Did you run the tests?", False),
    ("frontmatter is metadata", "---\ntitle: did you\n---\nclean line", False),
    ("an html comment is stripped", "<!-- Did you run it? --> fine", False),
    ("a table rule is punctuation", "|---|---|", False),
    ("an explicit marker exempts the line", "Did you run it? <!-- style-ok -->", False),
    ("an identifier is not the pronoun", "The value of you_id is set.", False),
    ("i18n is not the pronoun", "The i18n pipeline is idempotent.", False),
    ("I/O is not the pronoun", "The I/O layer buffers writes.", False),
    ("a roman numeral behind a noun is not the pronoun", "Phase I covered the survey.", False),
]


@pytest.mark.parametrize(("label", "text", "must_fire"), EXTRACTION, ids=[c[0] for c in EXTRACTION])
def test_extraction(label, text, must_fire):
    fired = _fired(text)
    assert bool(fired) == must_fire, "%s: fired %s on %r" % (label, fired, text)


def test_extraction_has_both_directions():
    """The control on the control. A one-sided table proves one-sided behaviour."""
    positive = sum(1 for _, _, fire in EXTRACTION if fire)
    negative = len(EXTRACTION) - positive
    shape = (
        "the extraction table is %d positive / %d negative; a table that is all one "
        "way cannot tell a working extractor from a constant" % (positive, negative)
    )
    assert positive >= 3, shape
    assert negative >= 10, shape


# --------------------------------------------------------------------------- Code comments ---------------------------------------------------------------------------


def test_python_comments_are_prose_and_strings_are_not():
    text = "x = 1  # Did you run it?\ny = 'did you run it'\n"
    findings, note = ps.lint_text("a.py", text, RULES, GLOBALS)
    assert note is None
    assert [f.lineno for f in findings] == [1], (
        "tokenize is the point: a regex over `#` reads the string on line 2 as prose. "
        "Got %s" % [(f.lineno, f.text) for f in findings]
    )


def test_python_docstrings_are_prose():
    findings, _ = ps.lint_text("a.py", '"""Did you run it?"""\n', RULES, GLOBALS)
    assert [f.rule for f in findings] == ["R1"]


# A docstring is a string ALONE on its logical line. The first version of this predicate asked whether the token's LINE starts with a quote, which made every element of every multi-line collection in the repository read as prose. Found 2026-09-16 on this guard's own `EDGE_CASES` table, where R2 flagged the capital `I` inside a test LABEL. Both directions, because "nothing is a
# docstring" also passes a one-sided version of this.
DOCSTRING = [
    ("a module docstring", '"""Did you run it?"""\n', True),
    ("a function docstring", 'def f():\n    """Did you run it?"""\n', True),
    ("a bare module-level string", '"Did you run it?"\n', True),
    ("a list element that starts with a quote", 'X = [\n    "says I here",\n]\n', False),
    ("a dict value alone on its line", 'X = {\n    "k": "Did you run it?",\n}\n', False),
    ("an assigned string", 'X = "Did you run it?"\n', False),
    ("a call argument", 'f(\n    "Did you run it?",\n)\n', False),
]


@pytest.mark.parametrize(("label", "src", "is_prose"), DOCSTRING, ids=[c[0] for c in DOCSTRING])
def test_docstring_predicate(label, src, is_prose):
    findings, note = ps.lint_text("a.py", src, RULES, GLOBALS)
    assert note is None
    assert bool(findings) == is_prose, "%s: fired %s" % (label, [f.rule for f in findings])


# An indented block is CODE wherever it appears, and "wherever" took two rounds to get right: the docstring arm landed first and the very next sweep flagged the COMMENT restating the same snippet. Both token kinds, both directions.
INDENTED = [
    ("a comment showing a snippet", '# an example:\n#\n#     x = "says I"\n', False),
    ("an ordinary comment is still prose", "# Did you run it?\n", True),
    (
        "a docstring literal block",
        'def f():\n    """An example::\n\n        x = "says I"\n    """\n',
        False,
    ),
    ("a docstring's own prose is still linted", 'def f():\n    """Did you run it?"""\n', True),
    ("a one-space comment indent is not a block", "#  Did you run it?\n", True),
    ("a three-space comment indent is not a block", "#   Did you run it?\n", True),
    ("a four-space comment indent IS a block", "#    Did you run it?\n", False),
]


@pytest.mark.parametrize(("label", "src", "is_prose"), INDENTED, ids=[c[0] for c in INDENTED])
def test_indented_blocks_are_code_in_comments_and_docstrings(label, src, is_prose):
    findings, note = ps.lint_text("a.py", src, RULES, GLOBALS)
    assert note is None
    assert bool(findings) == is_prose, "%s: fired %s" % (label, [f.rule for f in findings])


def test_a_file_that_will_not_tokenize_is_unchecked_not_clean():
    """UNKNOWN IS A FAILURE. This is the half a gate gets wrong quietly."""
    findings, note = ps.lint_text("a.py", "def f(:\n", RULES, GLOBALS)
    assert findings == []
    assert note is not None
    assert "NOTHING was extracted" in note


def test_cstyle_strings_are_not_comments():
    text = 'const u = "https://x/you";\n// Did you run it?\n'
    findings, _ = ps.lint_text("a.ts", text, RULES, GLOBALS)
    assert [f.lineno for f in findings] == [2]


def test_cstyle_template_literal_is_not_a_comment():
    findings, _ = ps.lint_text("a.ts", "const a = `x // you y`;\n", RULES, GLOBALS)
    assert findings == []


def test_block_comments_are_prose():
    findings, _ = ps.lint_text("a.ts", "/* Did you run it? */\n", RULES, GLOBALS)
    assert [f.rule for f in findings] == ["R1"]


# --------------------------------------------------------------------------- Stable ids, and the baseline's composition guard ---------------------------------------------------------------------------


def _finding(path="a.md", line=3, rule="R1", text="Did you run it?"):
    return ps.Finding(path, line, rule, "you", text, "error")


def test_an_id_survives_a_move_and_not_a_rewrite():
    assert _finding(line=3).fid == _finding(line=900).fid
    assert _finding().fid != _finding(text="Did you run them?").fid
    assert _finding().fid != _finding(path="b.md").fid


def test_write_baseline_refuses_a_drain_that_added(tmp_path):
    """THE COMPOSITION TRAP, driven rather than argued.

    The set SHRINKS by one and still contains something brand new. A size comparison calls that progress; the diff calls it what it is.
    """
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    old = [_finding(text="one"), _finding(text="two"), _finding(text="three")]
    assert ps.write_baseline_guarded(tmp_path, old, None, False) is None
    previous = ps.load_baseline(tmp_path)
    assert len(previous) == 3

    # Two removed, one added: the TOTAL shrank from 3 to 2.
    drained = [_finding(text="one"), _finding(text="BRAND NEW")]
    refused = ps.write_baseline_guarded(tmp_path, drained, previous, False)
    assert refused == [_finding(text="BRAND NEW").fid], (
        "the added side was %r; a shrinking total must not be read as a clean drain" % refused
    )
    assert ps.load_baseline(tmp_path) == previous, "the file was written despite the refusal"

    # The same drain with the decision typed at the command line is allowed.
    assert ps.write_baseline_guarded(tmp_path, drained, previous, True) is None
    assert len(ps.load_baseline(tmp_path)) == 2


def test_by_rule_sum_matches_count_when_a_finding_repeats(tmp_path):
    """Two physical lines, one fid: `by_rule` must not double-count it.

    `fid` hashes (path, rule, text) and not the line number on purpose, so the identical template string flagged on two different lines of one file collapses to ONE baseline entry -- `count`/`findings` already dedupe by fid. `by_rule`'s own tally must collapse the same way, or its sum drifts from `count`: measured live, 8 such repeats in the real tree inflated the printed total by
    11 before this was fixed.
    """
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    repeated_a = [_finding(line=3, rule="R1", text="Did you run it?")] * 2
    repeated_b = [_finding(line=9, rule="R2", text="I already told you")] * 3
    single = [_finding(line=20, rule="R1", text="Your feedback")]
    ps.write_baseline_guarded(tmp_path, repeated_a + repeated_b + single, None, False)
    doc = json.loads((tmp_path / ps.BASELINE_FILE).read_text(encoding="utf-8"))
    assert doc["count"] == 3, "3 distinct fids, however many times each was seen"
    assert sum(doc["by_rule"].values()) == doc["count"]


def test_a_clean_drain_is_allowed(tmp_path):
    """The MIRROR: removing only must not be refused, or the guard blocks all progress."""
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    old = [_finding(text="one"), _finding(text="two")]
    ps.write_baseline_guarded(tmp_path, old, None, False)
    previous = ps.load_baseline(tmp_path)
    assert ps.write_baseline_guarded(tmp_path, [_finding(text="one")], previous, False) is None
    assert len(ps.load_baseline(tmp_path)) == 1


# --------------------------------------------------------------------------- run_check: the anti-vacuity arms, driven end to end ---------------------------------------------------------------------------


def _tree(tmp_path, files):
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


GIT_ISOLATED = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
DIRTY = "Did you run the tests?\n"  # <!-- style-ok -->
CLEAN = "The tests were run.\n"


def _repo(tmp_path, tracked, *, ignore=(), untracked=()):
    """A real checkout: `tracked` staged, `ignore` written to .gitignore, `untracked` planted AFTER the add so git never sees it.

    NO COMMIT. `git ls-files` reads the index, so `git add` is the whole requirement, and skipping the commit skips every way a global identity or signing configuration could make this fixture machine-dependent.
    """
    root = _tree(tmp_path, tracked)
    if ignore:
        (root / ".gitignore").write_text("".join(p + "\n" for p in ignore), encoding="utf-8")
    env = {**os.environ, **GIT_ISOLATED}
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=root, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    for rel, text in dict(untracked).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_a_gitignored_file_is_not_discovered(tmp_path):
    root = _repo(
        tmp_path, {"kept.md": CLEAN}, ignore=["local/"], untracked={"local/dirty.md": DIRTY}
    )
    found = ps.discover(root, GLOBALS)
    assert "kept.md" in found  # MIRROR: a real discover() cannot return nothing
    assert "local/dirty.md" not in found


def test_an_untracked_file_is_not_discovered(tmp_path):
    root = _repo(tmp_path, {"kept.md": CLEAN}, untracked={"fresh.md": DIRTY})
    found = ps.discover(root, GLOBALS)
    assert "kept.md" in found
    assert "fresh.md" not in found


def test_a_gitignored_finding_cannot_enter_the_baseline(tmp_path):
    root = _repo(
        tmp_path, {"kept.md": DIRTY}, ignore=["local/"], untracked={"local/dirty.md": DIRTY}
    )
    rc = ps.run_check(root, GLOBALS, RULES, [], write_baseline=True)
    assert rc == 0
    baseline = json.loads((root / ps.BASELINE_FILE).read_text(encoding="utf-8"))
    assert "kept.md" in baseline["findings"]  # MIRROR: the write was not vacuous
    assert "local/dirty.md" not in baseline["findings"]


def test_an_explicitly_named_untracked_file_is_still_scanned(tmp_path, capsys):
    root = _repo(tmp_path, {"kept.md": CLEAN}, untracked={"brand-new.md": DIRTY})
    rc = ps.run_check(root, GLOBALS, RULES, ["brand-new.md"])
    assert rc == 1
    assert "Do not add them to the baseline" in capsys.readouterr().err
    assert "brand-new.md" not in ps.discover(root, GLOBALS)


def test_discovery_outside_a_checkout_refuses_rather_than_reporting_nothing(tmp_path, capsys):
    root = _tree(tmp_path, {"a.md": DIRTY})
    with pytest.raises(ps.RuleError):
        ps.discover(root, GLOBALS)
    rc = ps.run_check(root, GLOBALS, RULES, [])
    assert rc == 1
    assert "not a git checkout" in capsys.readouterr().err


def test_the_real_corpus_is_a_subset_of_what_git_tracks():
    found = set(ps.discover(ROOT, GLOBALS))
    tracked = set(gitx.ls_files(root=ROOT))
    assert found <= tracked
    assert len(found) > 2000


def test_exclude_dirs_prunes_by_bare_name_and_by_path():
    skip = {"node_modules", "packages/www"}
    assert ps.under_excluded_dir("a/node_modules/b.md", skip) is True
    assert ps.under_excluded_dir("packages/www/x.md", skip) is True
    assert ps.under_excluded_dir("docs/build.md", {"build"}) is False
    assert ps.under_excluded_dir("node_modules", {"node_modules"}) is False


def test_zero_files_is_a_failure(tmp_path, capsys):
    """A glob that matches nothing must not exit 0 looking like a clean tree."""
    root = _repo(tmp_path, {})
    rc = ps.run_check(root, GLOBALS, RULES, [])
    assert rc == 1
    assert "VACUOUS" in capsys.readouterr().err


def test_zero_prose_lines_is_a_failure(tmp_path, capsys):
    """A non-empty file set that extracts nothing is the EXTRACTOR breaking.

    Distinct from the glob arm and invisible to it: the file count is healthy and the finding count is zero, which is exactly what a clean tree looks like.
    """
    root = _tree(tmp_path, {"a.md": "```\njust code\n```\n"})
    rc = ps.run_check(root, GLOBALS, RULES, ["a.md"])
    assert rc == 1
    assert "ZERO prose lines" in capsys.readouterr().err


def test_a_new_error_fails_and_a_clean_tree_passes(tmp_path, capsys):
    root = _tree(tmp_path, {"a.md": "Did you run the tests?\n"})
    assert ps.run_check(root, GLOBALS, RULES, ["a.md"]) == 1
    assert "Do not add them to the baseline" in capsys.readouterr().err

    (root / "a.md").write_text("Have the tests been run?\n", encoding="utf-8")
    assert ps.run_check(root, GLOBALS, RULES, ["a.md"]) == 0


def test_a_fixed_baselined_finding_must_be_drained(tmp_path, capsys):
    """The second half of shrink-only, which is what makes the set shrink."""
    root = _tree(tmp_path, {"a.md": "Did you run the tests?\n"})
    ps.run_check(root, GLOBALS, RULES, ["a.md"], write_baseline=True)
    assert ps.run_check(root, GLOBALS, RULES, ["a.md"]) == 0

    (root / "a.md").write_text("Have the tests been run?\n", encoding="utf-8")
    assert ps.run_check(root, GLOBALS, RULES, ["a.md"]) == 1
    assert "no longer fire" in capsys.readouterr().err


def test_an_unreadable_file_is_unchecked_not_clean(tmp_path, capsys):
    root = _tree(tmp_path, {"a.md": "clean prose here.\n", "b.py": "def f(:\n"})
    rc = ps.run_check(root, GLOBALS, RULES, ["a.md", "b.py"])
    assert rc == 1
    assert "went UNCHECKED" in capsys.readouterr().err


# --------------------------------------------------------------------------- Reflow ---------------------------------------------------------------------------

REFLOW = [
    ("a hard-wrapped paragraph joins", "one two\nthree four\n", "one two three four\n"),
    ("a fenced block is untouched", "```\na\nb\n```\n", "```\na\nb\n```\n"),
    ("a list is untouched", "- a\n- b\n", "- a\n- b\n"),
    ("a numbered list is untouched", "1. a\n2. b\n", "1. a\n2. b\n"),
    ("a table is untouched", "| a | b |\n|---|---|\n", "| a | b |\n|---|---|\n"),
    (
        "a table with 3+ data rows is untouched, row for row",
        "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n",
        "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n",
    ),
    (
        "a gen-docs region marker does not absorb its neighbours",
        "lead-in sentence.\n<!-- >>> gen-docs: x -->\nbody\n<!-- <<< gen-docs -->\ntrailing sentence.\n",
        "lead-in sentence.\n<!-- >>> gen-docs: x -->\nbody\n<!-- <<< gen-docs -->\ntrailing sentence.\n",
    ),
    (
        "a trailing style-ok marker does not absorb its neighbours",
        "first line.\nDid you check it? <!-- style-ok -->\nthird line.\n",
        "first line.\nDid you check it? <!-- style-ok -->\nthird line.\n",
    ),
    (
        "doc-header key:value lines never merge into each other",
        "Status: done\nOwner: e580532b\nUpdated: 2026-09-06\n",
        "Status: done\nOwner: e580532b\nUpdated: 2026-09-06\n",
    ),
    (
        "a details/summary block does not absorb its neighbours",
        "lead-in.\n<details><summary>x</summary>\nbody\n</details>\ntrailing.\n",
        "lead-in.\n<details><summary>x</summary>\nbody\n</details>\ntrailing.\n",
    ),
    ("a heading does not absorb the next line", "# H\ntext\n", "# H\ntext\n"),
    ("a blockquote is untouched", "> a\n> b\n", "> a\n> b\n"),
    ("frontmatter is untouched", "---\na: b\n---\nc\n", "---\na: b\n---\nc\n"),
    ("indented code is untouched", "    a\n    b\n", "    a\n    b\n"),
    (
        "a link definition is untouched",
        "[a]: https://x\n[b]: https://y\n",
        "[a]: https://x\n[b]: https://y\n",
    ),
    ("a blank line separates paragraphs", "a\nb\n\nc\nd\n", "a b\n\nc d\n"),
    ("no trailing newline is preserved as none", "a\nb", "a b"),
]


@pytest.mark.parametrize(("label", "before", "after"), REFLOW, ids=[c[0] for c in REFLOW])
def test_reflow(label, before, after):
    assert ps.reflow_markdown(before, 384) == after, label


@pytest.mark.parametrize(("label", "before", "_after"), REFLOW, ids=[c[0] for c in REFLOW])
def test_reflow_is_idempotent(label, before, _after):
    once = ps.reflow_markdown(before, 384)
    assert ps.reflow_markdown(once, 384) == once, label


def test_reflow_leaves_a_period_free_paragraph_on_one_line_however_long():
    """The reflow side of `7a13350d5`'s own contract: 384 is where a line is ALLOWED to break, never where it must, so a paragraph with no sentence-ending period anywhere is never split, however far past `width` it runs.
    `textwrap.wrap`'s ordinary word-boundary wrapping used to do exactly the "arbitrary mid-thought split" that commit removed from the CHECK side -- this is the reflow-side regression control for it, added when `_join_and_wrap` was found still doing it.
    """
    text = ("word " * 200).strip() + "\n"
    out = ps.reflow_markdown(text, 80)
    assert out == text.strip() + "\n", "a period-free paragraph must not be split at all: %r" % out
    assert ps.reflow_markdown(out, 80) == out


def test_reflow_over_the_width_wraps_only_at_sentence_boundaries():
    text = " ".join("Sentence number %d ends here." % i for i in range(1, 15)) + "\n"
    out = ps.reflow_markdown(text, 80)
    lines = out.splitlines()
    assert len(lines) > 1, "the paragraph must actually wrap across several lines: %r" % out
    assert max(len(line) for line in lines) <= 80
    for line in lines:
        assert line.rstrip().endswith("."), "a wrap landed mid-sentence: %r" % line
    assert out.split() == text.split()
    assert ps.reflow_markdown(out, 80) == out


# --------------------------------------------------------------------------- Reflow of source comments, where a LEXER decides what a comment is ---------------------------------------------------------------------------
#
# THE FIRST FIVE CASES ARE THE GATE, and each was run against the reverted `^\s*#` / `^\s*//` implementation before being kept: every one of them comes back corrupted there. The eleven after them are CONTRACT PINS, which the reverted version also passes -- they hold behaviour that was already right (directives, commented-out code, indentation, an unknown suffix) so the rewrite
# above cannot have quietly traded one for the other. The distinction is stated because a table where only some rows can fail reads, at a glance, like a table where all of them can. That version rewrote 52 of the 1051 `.py` files in this repository into a different `ast.dump`, because a docstring quoting an example `# ...` line reads to a per-line regex exactly like the real
# comment paragraph under it. The fixtures are shaped around the two ways that bug hides:
#
# the docstring must END on the `#` line -- a `"""` on a line of its own already stops the paragraph, so the obvious fixture passes while broken
#
#   the template literal must carry NO `;` -- CODE_SHAPED_COMMENT catches the
# semicolon, and the broken version then passes for the wrong reason
#
# A `/* */` span is a STOP, never a paragraph: reflowing inside one would move its own asterisk alignment, and nothing asks for that.

REFLOW_COMMENTS = [
    (
        "a `#` line inside a docstring is not a comment",
        ".py",
        (
            'def f():\n    """Doc.\n\n    # an example inside the docstring"""\n'
            "    # a real comment that is\n    # hard wrapped over two lines\n    return 1\n"
        ),
        (
            'def f():\n    """Doc.\n\n    # an example inside the docstring"""\n'
            "    # a real comment that is hard wrapped over two lines\n    return 1\n"
        ),
    ),
    (
        "a `//` line inside a template literal is not a comment",
        ".ts",
        (
            "const t = `\n// looks like a comment`\n"
            "// a real comment that is\n// hard wrapped over two lines\n"
        ),
        (
            "const t = `\n// looks like a comment`\n"
            "// a real comment that is hard wrapped over two lines\n"
        ),
    ),
    (
        "a `//` line inside a `/* */` block is not a comment line",
        ".ts",
        "/*\n// inside a block comment */\n// a real one that is\n// hard wrapped\n",
        "/*\n// inside a block comment */\n// a real one that is hard wrapped\n",
    ),
    (
        "a trailing comment on a docstring's closing line is never joined",
        ".py",
        (
            'def f():\n    """D\n    # example"""  # note\n'
            "    # a real comment that is\n    # hard wrapped over two lines\n    return 1\n"
        ),
        (
            'def f():\n    """D\n    # example"""  # note\n'
            "    # a real comment that is hard wrapped over two lines\n    return 1\n"
        ),
    ),
    (
        "a file tokenize cannot read is returned unchanged",
        ".py",
        "def f(:\n# a comment that is\n# hard wrapped\n",
        "def f(:\n# a comment that is\n# hard wrapped\n",
    ),
    (
        "a plain hard-wrapped comment paragraph joins",
        ".py",
        "# one two\n# three four\n",
        "# one two three four\n",
    ),
    (
        "a blank comment line separates paragraphs",
        ".py",
        "# a\n# b\n#\n# c\n# d\n",
        "# a b\n#\n# c d\n",
    ),
    (
        "an indentation change ends the paragraph",
        ".py",
        "if x:\n    # a\n    # b\n        # c\n    pass\n",
        "if x:\n    # a b\n        # c\n    pass\n",
    ),
    (
        "a trailing comment on a code line is left alone",
        ".py",
        "x = 1  # note\ny = 2  # more\n",
        "x = 1  # note\ny = 2  # more\n",
    ),
    (
        "a directive comment never absorbs a neighbour",
        ".py",
        "# a comment that is\n# noqa: E501\n# hard wrapped\n",
        "# a comment that is\n# noqa: E501\n# hard wrapped\n",
    ),
    (
        "a go:build directive never absorbs a neighbour",
        ".go",
        "//go:build linux\n// a comment that is\n// hard wrapped\n",
        "//go:build linux\n// a comment that is hard wrapped\n",
    ),
    (
        "a triple-slash reference has no space and is left alone",
        ".ts",
        '/// <reference types="node" />\n/// <reference types="vite/client" />\n',
        '/// <reference types="node" />\n/// <reference types="vite/client" />\n',
    ),
    (
        "commented-out code is never joined",
        ".py",
        "# def foo():\n#     return 1\n",
        "# def foo():\n#     return 1\n",
    ),
    (
        "a `//` inside a url is not a comment",
        ".ts",
        'const u = "https://x/a"\n// a comment that is\n// hard wrapped\n',
        'const u = "https://x/a"\n// a comment that is hard wrapped\n',
    ),
    (
        "an unknown suffix is returned unchanged",
        ".rb",
        "# one two\n# three four\n",
        "# one two\n# three four\n",
    ),
    (
        "no trailing newline is preserved as none",
        ".py",
        "# one two\n# three four",
        "# one two three four",
    ),
]


@pytest.mark.parametrize(
    ("label", "suffix", "before", "after"),
    REFLOW_COMMENTS,
    ids=[c[0] for c in REFLOW_COMMENTS],
)
def test_reflow_comments(label, suffix, before, after):
    assert ps.reflow_comments(before, suffix, 384) == after, label


@pytest.mark.parametrize(
    ("label", "suffix", "before", "_after"),
    REFLOW_COMMENTS,
    ids=[c[0] for c in REFLOW_COMMENTS],
)
def test_reflow_comments_is_idempotent(label, suffix, before, _after):
    once = ps.reflow_comments(before, suffix, 384)
    assert ps.reflow_comments(once, suffix, 384) == once, label


def test_a_gate_header_is_never_folded_into_one_line():
    """`b13267223` folded two real gate headers and unregistered both gates; this is the control that stops it returning.

    A `---- gate ----` block is parsed one field per line by `scripts/lib/gate-header.ts`, so a join turns a declaration into prose that nothing reads. The paragraph BENEATH the block still folds, which is what keeps this a stop rather than a blanket refusal to touch the docstring.
    """
    before = (
        '"""A gate.\n'
        "\n"
        "---- gate ----\n"
        "step: CLI docs stay in sync\n"
        "needs: none\n"
        "lane: quality-code\n"
        "slow: true\n"
        "---- end gate ----\n"
        "\n"
        "one two\n"
        "three four\n"
        '"""\n'
    )
    out = ps.reflow_comments(before, ".py", 384)
    for line in (
        "---- gate ----",
        "step: CLI docs stay in sync",
        "needs: none",
        "lane: quality-code",
        "slow: true",
        "---- end gate ----",
    ):
        assert line in out.split("\n"), "%r was folded into another line: %r" % (line, out)
    assert "one two three four" in out, "the prose below the block must still fold: %r" % out


def test_reflow_comments_leaves_a_period_free_paragraph_on_one_line_however_long():
    """The comment-scope twin of `test_reflow_leaves_a_period_free_paragraph_on_one_line_however_long`: a `#` comment paragraph with no sentence-ending period is never split, however far past `width` it runs."""
    text = "# " + ("word " * 200).strip() + "\n"
    out = ps.reflow_comments(text, ".py", 80)
    assert out == text, "a period-free comment paragraph must not be split at all: %r" % out
    assert ps.reflow_comments(out, ".py", 80) == out


def test_reflow_comments_over_the_width_wraps_only_at_sentence_boundaries():
    text = "# " + " ".join("Sentence number %d ends here." % i for i in range(1, 15)) + "\n"
    out = ps.reflow_comments(text, ".py", 80)
    lines = out.splitlines()
    assert len(lines) > 1, "the paragraph must actually wrap across several lines: %r" % out
    assert max(len(line) for line in lines) <= 80
    for line in lines:
        assert line.rstrip().endswith("."), "a wrap landed mid-sentence: %r" % line
    assert out.replace("#", "").split() == text.replace("#", "").split()
    assert ps.reflow_comments(out, ".py", 80) == out


def _docstring_normalized_dump(tree):
    """`ast.dump`, with every module/class/function docstring's TEXT blanked out.

    A docstring is a string literal, so reflowing one changes `ast.dump` BY DESIGN -- the whole point of this refactor is that R19 and reflow can now see one, where before neither ever looked inside a docstring at all. The safety proof this module used to run (exact `ast.dump` equality across a reflow) asserted something no longer true and that must not become true again: this is
    its replacement, proving a reflow never touches anything OUTSIDE a docstring node. `node.body[0]` is only ever a docstring when it is an `Expr` wrapping a string `Constant` as the FIRST statement of a module, class or function -- the same grammar `_is_docstring` already checks token-by-token in `prose_style.py`. Walking the AST for it here is independent confirmation, not a
    restatement of that same code.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0].value.value = ""
    return ast.dump(tree)


def test_reflow_comments_preserves_the_ast_of_every_tracked_python_file():
    """THE test that caught the regex version: 52 of 1051 files, silently rewritten.

    A comment is not part of the AST, and a reflowed docstring is a CHANGED string constant by design -- both facts are folded into one property here: a reflow may change a docstring's own text and NOTHING else. Blanking every docstring's value in both trees before comparing turns that into an assertable claim instead of "trust the diff": anything outside a docstring that moves is
    a real corruption and fails loudly, a docstring's text changing is the feature under test, and the two are told apart by construction rather than by inspection.

    WIDTH 40, NOT 384. The real corpus was reflowed to 384 tree-wide in an earlier session, so a 384-width run now finds almost nothing left to join -- not because the property stopped holding, but because the debt it used to measure is gone. A narrow width forces real multi-line comment AND docstring paragraphs to rejoin regardless of the tree's current wrap state, so the vacuity
    floor stays meaningful independent of when this runs.
    """
    files = gitx.ls_files("*.py", root=ROOT, existing=True)
    assert len(files) > 500, "the corpus collapsed to %d file(s); this asserts nothing" % len(files)
    mismatched = []
    reflowed = 0
    docstrings_reflowed = 0
    for rel in files:
        before = (ROOT / rel).read_text(encoding="utf-8")
        try:
            expected = _docstring_normalized_dump(ast.parse(before))
        except SyntaxError:
            continue
        after = ps.reflow_comments(before, ".py", 40)
        reflowed += after != before
        if after != before:
            with contextlib.suppress(SyntaxError):
                docstrings_reflowed += ast.dump(ast.parse(before)) != ast.dump(ast.parse(after))
        try:
            if _docstring_normalized_dump(ast.parse(after)) != expected:
                mismatched.append(rel)
        except SyntaxError:
            mismatched.append(rel)
    assert reflowed > 100, "only %d file(s) changed at all; this asserts nothing" % reflowed
    assert docstrings_reflowed > 0, (
        "not one file's reflow touched a docstring's own AST value; the corpus proof this "
        "refactor exists for would then be vacuous for the hazard it is meant to catch"
    )
    assert not mismatched, (
        "reflow_comments changed the AST outside a docstring in %d file(s): %s"
        % (
            len(mismatched),
            mismatched[:10],
        )
    )


# --------------------------------------------------------------------------- Docstrings are reflow-eligible and R19-visible now, and the hazards that come with it ---------------------------------------------------------------------------


def test_a_narrow_docstring_paragraph_is_r19_visible_and_gets_rejoined():
    """THE HOLE THIS REFACTOR CLOSES. Before it, `_python_reflow_lines` never looked at a STRING token at all, so a docstring's prose was invisible to both `comment_segments` and the R19 pass it feeds, no matter how narrow-wrapped it was -- 9,932 such paragraphs across 1,021 files, measured live on this corpus."""
    text = (
        'def f():\n    """Summary.\n\n    one two three\n    four five six\n'
        '    seven eight nine\n    """\n'
    )
    findings, note = ps.lint_text("a.py", text, RULES, GLOBALS)
    assert note is None
    assert "R19" in [f.rule for f in findings], "a narrow docstring paragraph must fire R19 now"
    after = ps.reflow_comments(text, ".py", 384)
    assert after == (
        'def f():\n    """Summary.\n\n    one two three four five six seven eight nine\n    """\n'
    )


def test_a_verbatim_usage_docstring_is_never_rewrapped():
    """A REAL, currently-tracked shape, not a hypothetical: `.ci/scripts/housekeeping/retire-shadowed-secrets.py`'s module docstring `print(__doc__)`s a `Usage:` block at 2-space indent -- shallower than the `base + 4` code-block rule, and exactly what a naive "join every flush docstring line" reflow would corrupt into one unreadable line."""
    text = (
        '"""Retire a thing.\n\nUsage:\n'
        "  retire-thing.py <NAME> [<NAME>...]            # report only, default\n"
        "  retire-thing.py --apply <NAME> [<NAME>...]    # rewrite the files\n"
        "  retire-thing.py --selftest\n\n"
        'Exit: 0 clean, 1 nothing to do, 2 a failed control.\n"""\n'
    )
    assert ps.reflow_comments(text, ".py", 384) == text


def test_an_indented_code_block_inside_a_docstring_is_never_rewrapped():
    """The `base + 4` rule (hazard 3 of this refactor) has to survive on the reflow side exactly as it always worked on the lint side, not merely be re-derived and hoped equivalent."""
    text = 'def f():\n    """An example::\n\n        x = 1\n        y = 2\n        z = 3\n    """\n'
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_doctest_block_inside_a_docstring_is_never_rewrapped():
    """A NEW gap this refactor opens if left unhandled: before it, nothing ever reflowed a docstring at all, so a doctest block was safe by omission rather than by any explicit stop."""
    text = 'def f():\n    """Example.\n\n    >>> f()\n    >>> f()\n    >>> f()\n    """\n'
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_rest_field_list_inside_a_docstring_is_never_rewrapped():
    text = (
        'def f():\n    """Do a thing.\n\n    :param x: the value\n    :param y: another one\n'
        '    :returns: the result\n    """\n'
    )
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_rule_line_banner_is_never_absorbed_into_the_prose_beside_it():
    """MEASURED DAMAGE, not a hypothetical. One reflow pass over 400 tracked `.py` files absorbed 793 banner lines across 154 files, turning the three-line `---- / TITLE / ----` section rule this repository writes inside its own module docstrings into a single run-on line joined to the paragraph beneath it. `REFLOW_STOP` has carried `RULE_LINE` for markdown since the beginning; the
    comment path simply never applied it, on the since-corrected belief that a comment carries no structure worth protecting.
    """
    text = (
        'def f():\n    """Header.\n\n    ----------------------------------------\n'
        "    THE SECTION TITLE\n    ----------------------------------------\n"
        "    Body prose that follows the banner and would otherwise swallow it whole.\n"
        '    """\n'
    )
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_standalone_allcaps_heading_is_never_absorbed():
    """The same measurement found 296 all-caps section headings absorbed into the paragraph after them. The stop requires the WHOLE line to be caps, so this module's own `WHAT THIS ENFORCES. The single source ...` lead-in -- caps followed by ordinary prose on one line -- still joins normally, which the second half of this control pins."""
    heading = 'def f():\n    """Header.\n\n    TWO HAZARDS IN THE TWIN, REPORTED AND PRESERVED\n    Body prose beneath the heading.\n    """\n'
    assert ps.reflow_comments(heading, ".py", 384) == heading
    lead_in = 'def f():\n    """Header.\n\n    WHAT THIS ENFORCES. The single\n    source of truth is one file.\n    """\n'
    assert ps.reflow_comments(lead_in, ".py", 384) != lead_in


def test_a_list_inside_a_hash_comment_block_is_never_absorbed():
    """A `#` comment block carries enumerated structure exactly as a docstring does, and the reflow path used to check neither. Joining item 1 into its own continuations while leaving item 2 alone is the shape this pins, since the inconsistency is what makes the damage hard to see in a diff."""
    text = (
        "#   1. The first rule, which carries a continuation line\n"
        "#      that belongs to it and must not be merged upward.\n"
        "#   2. The second rule, which must stay a separate item.\n"
        "x = 1\n"
    )
    assert ps.reflow_comments(text, ".py", 384) == text


def test_an_html_tag_named_inside_a_code_span_is_prose_not_a_block():
    """The mention-versus-target class, which `docs/ci-overhaul/06-progress.md` already records for six separate guards, reaching the reflow stop list. `HTML_BLOCK_TAG` carries a `.*` prefix so it can find a tag anywhere on a line, which also made it fire on a sentence merely NAMING one in backticks, stranding that paragraph over the length limit with no tool able to rewrap it.
    Both directions are pinned here, because the obvious fix of scrubbing the line first is WRONG: `scrub` strips every HTML tag, real ones included, so a genuine block would have stopped being a stop. Only the code spans may be removed.
    """
    block = "<details>\n<summary>Click</summary>\n\nBody text long enough to matter.\n</details>\n"
    assert ps.reflow_markdown(block, 384) == block
    inline_real = "Some text <details> opening inline here\nand a second line.\n"
    assert ps.reflow_markdown(inline_real, 384) == inline_real
    mention = "Bugs found: `<details>`/`<summary>` blocks swallowed, and\nanother line of the same paragraph that should join.\n"
    assert ps.reflow_markdown(mention, 384) != mention


def test_a_list_item_continuation_keeps_its_left_margin():
    """REPORTED BY THE OPERATOR FROM THE RENDERED RESULT, which is the detail worth keeping: this survived a corpus-wide AST proof, a structural fence/heading/table check and a full reflow, because every one of those counts lines and none of them reads the COLUMN a line starts in. `_join_and_wrap` strips each piece before joining, correct for the words and wrong for the margin, so
    an indented continuation came back at column 0 and detached from the item above it. `reflow_markdown`'s own docstring already claimed the opposite, which is how the gap stayed invisible.
    """
    text = (
        "- Without JSON output, Terraform can't detect if autostart was changed\n"
        "  outside of Terraform\n"
        "- [ ] Evaluate effort\n"
    )
    assert ps.reflow_markdown(text, 384) == text


def test_an_indented_continuation_joins_without_losing_its_margin():
    """The other half, so the stop above is not satisfied by refusing to reflow anything indented: several continuation lines under one item SHOULD collapse to a single line, and that line has to keep the item's margin rather than the document's."""
    text = "- item\n  first continuation line\n  second continuation line\n"
    assert (
        ps.reflow_markdown(text, 384)
        == "- item\n  first continuation line second continuation line\n"
    )


def test_a_midline_semicolon_is_prose_not_commented_out_code():
    """Measured 2026-09-17 across 400 tracked `.py` files: 650 comment-body semicolons sit MID-line, the shape a continuing English clause takes ("...can; it judges..."), against 30 sitting at the end of the body, the shape a commented-out statement (`# x = 1;`) actually takes. The unanchored version of this check matched a semicolon anywhere and silently stopped a real
    paragraph from folding -- safe direction, but real prose left narrow is exactly what this reflow exists to fix.
    """
    text = (
        "# It cannot judge WHETHER a transform is mechanical the way the LLM can; it\n"
        "# judges SCALE instead, which is the plan's own principle.\n"
        "x = 1\n"
    )
    assert ps.reflow_comments(text, ".py", 384) != text


def test_a_trailing_semicolon_still_reads_as_commented_out_code():
    """The other half: a real commented-out statement must still stop a join, or anchoring the check to end-of-body would have traded one false positive for a false negative."""
    text = "# x = 1;\n# y = 2;\nz = 3\n"
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_cstyle_comment_block_gets_the_same_stops_as_a_hash_block():
    """THE SIBLING THE FIRST FIX MISSED, which is the whole reason the class sweep is run against every scope rather than the one that surfaced the bug. Adding the stops to the Python branch alone still absorbed 32 rule-line banners, 19 list items and 3 all-caps headings across the tracked `.ts`/`.js`/`.go` corpus, because `_cstyle_reflow_lines` had no equivalent check. A `//`
    block carries section structure exactly as a `#` block does.
    """
    text = (
        "// ----------------------------------------\n"
        "// AI TROUBLESHOOTING GUIDE\n"
        "// ----------------------------------------\n"
        "//   1. The first step, which carries a continuation\n"
        "//      line that belongs to it and must not merge up.\n"
        "//   2. The second step, which stays its own item.\n"
        "const x = 1;\n"
    )
    assert ps.reflow_comments(text, ".ts", 384) == text


def test_a_rest_directive_inside_a_docstring_is_never_rewrapped():
    text = 'def f():\n    """Do a thing.\n\n    .. note::\n\n       an aside\n    """\n'
    assert ps.reflow_comments(text, ".py", 384) == text


# --------------------------------------------------------------------------- A docstring's own opening/closing physical line folds and wraps too, when it carries prose alongside its delimiter ---------------------------------------------------------------------------


def test_a_short_opening_line_widens_and_joins_the_next_line():
    """THE ROOT BUG THIS PLAN FIXES. Before it, a docstring's opening physical line -- carrying the opening quote plus a lead sentence, this repository's own convention on every multi-line docstring -- was excluded from the eligible map unconditionally and emitted verbatim, so a short lead sentence could never widen by absorbing the line beneath it."""
    text = (
        'def f():\n    """Lead sentence.\n    More words that follow on the next line.\n    """\n'
    )
    assert ps.reflow_comments(text, ".py", 384) == (
        'def f():\n    """Lead sentence. More words that follow on the next line.\n    """\n'
    )


def test_an_opening_line_alone_over_width_is_left_unwrapped_without_a_period():
    """The other direction of the same gap: an opening line that alone exceeds width used to be emitted unchanged entirely, since a `"raw"` segment was never passed through `_join_and_wrap` at all.
    It now reaches the same wrap path everything else does, and -- carrying no sentence-ending period -- stays on its own line unsplit, by the same `7a13350d5` contract every other paragraph gets.
    """
    text = 'def f():\n    """' + ("word " * 90).strip() + '\n    """\n'
    out = ps.reflow_comments(text, ".py", 80)
    assert out == text, "a period-free opening line must not be split at all: %r" % out
    ast.parse(out)


def test_an_opening_line_alone_over_width_wraps_and_glues_at_a_sentence_break():
    """The same opening-line path, now WITH sentence breaks to wrap at, proving the delimiter still glues to the first wrapped line rather than the raw segment silently passing through untouched."""
    text = (
        'def f():\n    """'
        + " ".join("Sentence number %d ends here." % i for i in range(1, 20))
        + '\n    """\n'
    )
    out = ps.reflow_comments(text, ".py", 80)
    lines = out.splitlines()
    assert max(len(line) for line in lines) <= 80
    assert lines[1].startswith('    """'), "the opening delimiter must stay glued: %r" % out
    ast.parse(out)


def test_a_closing_line_alone_over_width_is_left_unwrapped_without_a_period():
    """The closing-side twin: unwrapped and unsplit without a sentence break to wrap at."""
    text = 'def f():\n    """Summary.\n\n    ' + ("word " * 90).strip() + '"""\n'
    out = ps.reflow_comments(text, ".py", 80)
    assert out == text, "a period-free closing line must not be split at all: %r" % out
    ast.parse(out)


def test_a_closing_line_alone_over_width_wraps_and_glues_at_a_sentence_break():
    """The closing-side twin of the opening-line wrap control, gluing the closing delimiter back on after the wrap rather than before it."""
    text = (
        'def f():\n    """Summary.\n\n    '
        + " ".join("Sentence number %d ends here." % i for i in range(1, 20))
        + '"""\n'
    )
    out = ps.reflow_comments(text, ".py", 80)
    lines = out.splitlines()
    assert max(len(line) for line in lines) <= 80
    assert lines[-1].endswith('."""'), "the closing delimiter must stay glued: %r" % out
    ast.parse(out)


def test_a_command_example_ending_in_a_line_continuation_backslash_is_never_folded():
    """A REAL, currently-tracked shape: `.ci/rediacc_ci/deploy/promote_r2_to_stable_hotfix.py`'s own docstring shows a shell command wrapped across two lines with a genuine `\\` continuation. Folding it would glue a delimiter onto an escaped position, corrupting the escape."""
    text = 'def f(tmp):\n    """`aws s3 cp tmp/ --quiet \\\n    --cache-control no-cache`."""\n'
    assert ps.reflow_comments(text, ".py", 384) == text


def test_a_closing_line_ending_in_the_delimiters_own_quote_gets_a_protective_space():
    """A REAL, currently-tracked shape: a docstring ending in a quoted word right before its own closing triple-quote. Gluing the closing delimiter straight onto text ending in the same quote character is an UNTERMINATED STRING, not cosmetic, so one space must separate them."""
    text = 'def f():\n    """Reads "The round\n    failed in failure." """\n'
    out = ps.reflow_comments(text, ".py", 384)
    ast.parse(out)


def test_an_opening_line_that_begins_with_a_quote_keeps_a_separating_space():
    """Found by the repository's own formatter gate rather than by any AST proof, which blanks docstring text and so cannot see it: gluing `\"\"\"` onto a first word that starts with a quote made a run of four, and `ruff format` rewrites that with a space, so the reflow and the formatter disagreed on 56 files until the glue wrote the space itself."""
    text = 'def f():\n    """ "pass" | "fail". Four outcomes\n    and more words here.\n    """\n'
    out = ps.reflow_comments(text, ".py", 384)
    assert '"""  "' not in out
    assert '""""' not in out
    assert ps.reflow_comments(out, ".py", 384) == out
    ast.parse(out)


def test_a_trailing_comment_on_a_docstrings_closing_line_still_never_joins():
    """THE BUG THIS FIX ALMOST INTRODUCED, caught by the pre-existing fixture above rather than by a new one, and pinned here so it cannot regress silently a second time. The tokenizer's own STRING text for the closing line ends at the quote; anything after it on the raw source line -- a real trailing comment -- is a SEPARATE token this fold must never absorb into the
    reconstructed line, since gluing `close_delim` back on would otherwise rebuild the line from parts and silently drop whatever followed the quote in the original source."""
    text = (
        'def f():\n    """D\n    # example"""  # note\n'
        "    # a real comment that is\n    # hard wrapped over two lines\n    return 1\n"
    )
    after = ps.reflow_comments(text, ".py", 384)
    assert "# note" in after
    assert after == (
        'def f():\n    """D\n    # example"""  # note\n'
        "    # a real comment that is hard wrapped over two lines\n    return 1\n"
    )


def _cstyle_comment_spans(text):
    """Character `[start, end)` spans covering every `//`/`/* */` comment span, walked INDEPENDENTLY of `prose_style._cstyle_scan` on purpose: this is the proof that `reflow_comments` never touches a byte outside one, and reusing the very walk reflow is fed from would let one bug shared by both sides of the proof pass silently."""
    spans = []
    i = 0
    length = len(text)
    quote = None
    while i < length:
        char = text[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "\"'`":
            quote = char
            i += 1
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "/":
            end = text.find("\n", i)
            end = length if end == -1 else end
            spans.append((i, end))
            i = end
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            close = text.find("*/", i + 2)
            end = length if close == -1 else min(close + 2, length)
            spans.append((i, end))
            i = end
            continue
        i += 1
    return spans


def _mask_comments(text):
    out = []
    pos = 0
    for start, end in _cstyle_comment_spans(text):
        out.append(text[pos:start])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def test_reflow_comments_preserves_non_comment_bytes_of_every_tracked_cstyle_file():
    """The C-style analogue of the Python AST proof above. A `//`/`/* */` language has no docstring convention this module reflows, so the claim is simpler and stronger: every character OUTSIDE a comment span must be byte-identical before and after, in the same relative order.

    WHITESPACE-RUNS ARE COLLAPSED BEFORE COMPARING, and that is a stated relaxation rather than a blind spot: joining several whole-line `//` comments into fewer physical lines removes newlines that sat BETWEEN those comment lines, which shrinks the amount of connective whitespace outside the masked spans too, exactly as expected. A real corruption -- a code token deleted, altered
    or reordered -- survives whitespace collapsing and still fails this assertion; only the benign, expected shrinkage from line-count reduction does not.
    """
    files = gitx.ls_files(
        "*.ts", "*.tsx", "*.js", "*.cjs", "*.mjs", "*.go", root=ROOT, existing=True
    )
    assert len(files) > 500, "the corpus collapsed to %d file(s); this asserts nothing" % len(files)
    reflowed = 0
    corrupted = []
    for rel in files:
        suffix = pathlib.Path(rel).suffix
        before = (ROOT / rel).read_text(encoding="utf-8", errors="surrogateescape")
        after = ps.reflow_comments(before, suffix, 40)
        if after == before:
            continue
        reflowed += 1
        before_skel = re.sub(r"\s+", " ", _mask_comments(before))
        after_skel = re.sub(r"\s+", " ", _mask_comments(after))
        if before_skel != after_skel:
            corrupted.append(rel)
    assert reflowed > 50, "only %d file(s) changed at all; this asserts nothing" % reflowed
    assert not corrupted, "reflow_comments changed non-comment bytes in %d file(s): %s" % (
        len(corrupted),
        corrupted[:10],
    )


def test_reflow_of_the_real_corpus_is_a_dry_run_by_default(tmp_path, capsys):
    """`reflow` must not write unless asked. The default is the whole safety of it."""
    root = _tree(tmp_path, {"a.md": "one two\nthree four\n"})
    before = (root / "a.md").read_text(encoding="utf-8")
    assert ps.run_reflow(root, GLOBALS, ["a.md"]) == 0
    assert (root / "a.md").read_text(encoding="utf-8") == before
    # STDERR, not stdout. `log.info` writes to stderr here, and asserting the wrong stream is how a message that stopped being printed goes unnoticed -- the assertion would still be reading an empty-by-design channel.
    assert "DRY RUN" in capsys.readouterr().err

    assert ps.run_reflow(root, GLOBALS, ["a.md"], write=True) == 0
    assert (root / "a.md").read_text(encoding="utf-8") == "one two three four\n"


# --------------------------------------------------------------------------- The loader refuses what it cannot trust ---------------------------------------------------------------------------

BAD_RULES = [
    ("no rules at all", "{}"),
    ("not an object", "[]"),
    ("not json", "{"),
    (
        "a pattern that does not compile",
        json.dumps(
            {
                "globals": {"scopes": ["markdown"]},
                "rules": [
                    {
                        "id": "B",
                        "title": "t",
                        "description": "d",
                        "severity": "error",
                        "scopes": ["all"],
                        "patterns": ["("],
                    }
                ],
            }
        ),
    ),
    (
        "a scope nothing produces",
        json.dumps(
            {
                "globals": {"scopes": ["markdown"]},
                "rules": [
                    {
                        "id": "B",
                        "title": "t",
                        "description": "d",
                        "severity": "error",
                        "scopes": ["typo"],
                        "patterns": ["x"],
                    }
                ],
            }
        ),
    ),
    (
        "a severity that is neither",
        json.dumps(
            {
                "globals": {"scopes": ["markdown"]},
                "rules": [
                    {
                        "id": "B",
                        "title": "t",
                        "description": "d",
                        "severity": "maybe",
                        "scopes": ["all"],
                        "patterns": ["x"],
                    }
                ],
            }
        ),
    ),
    (
        "a duplicate id",
        json.dumps(
            {
                "globals": {"scopes": ["markdown"]},
                "rules": [
                    {
                        "id": "D",
                        "title": "t",
                        "description": "d",
                        "severity": "error",
                        "scopes": ["all"],
                        "patterns": ["a"],
                    },
                    {
                        "id": "D",
                        "title": "t",
                        "description": "d",
                        "severity": "error",
                        "scopes": ["all"],
                        "patterns": ["b"],
                    },
                ],
            }
        ),
    ),
]


@pytest.mark.parametrize(("label", "text"), BAD_RULES, ids=[c[0] for c in BAD_RULES])
def test_the_loader_refuses(label, text):
    del label  # part of the case id
    with pytest.raises(ps.RuleError):
        ps.load_rules(text)


def _r18(name: str, text: str) -> list:
    findings, _ = ps.lint_text(name, text, RULES, GLOBALS)
    return [f for f in findings if f.rule == "R18"]


#: A line that both exceeds 768 AND ran past a genuine sentence-ending break sitting well before the floor, and does NOT itself close on a period -- the shape that must still fire once the break is not table/Touched-exempted. The lead sentence ends at a low, fixed offset; the filler after it is what pushes the line past 768 with no upper limit of its own, and it stops on a bare `x` rather than a period so the new trailing-period exemption does not also swallow it.
_LONG_WITH_EARLY_BREAK = "A short lead-in sentence ends here. " + ("x" * 800)


def test_a_long_table_row_and_a_touched_list_are_not_width_findings():
    """A table cannot wrap a row and the plan-record parser reads one line of `Touched:`, so R18 has nothing to fold there -- even when the line carries a sentence break it could otherwise be flagged for skipping."""
    long = _LONG_WITH_EARLY_BREAK
    assert len(long) > 768
    assert _r18("a.md", "| `package.json` | %s |\n" % long) == []
    assert _r18("a.md", "Touched: %s\n" % long) == []


def test_the_same_length_in_ordinary_prose_is_still_a_width_finding():
    """CONTROL for the case above: the exemption is the row and the key, not the length. The line runs well past 768, its lead sentence ended long before that, and it does not close on a period either -- an available break the author ran past, which R18's floor still catches."""
    assert len(_r18("a.md", "Prose that is far too long: %s\n" % _LONG_WITH_EARLY_BREAK)) == 1


def test_a_long_line_with_no_sentence_break_anywhere_is_not_a_width_finding():
    """768 is a FLOOR, not a ceiling: a comma-joined list of `.md` paths has no `. ` anywhere (every period is immediately followed by a filename character, never whitespace), so however far past 768 it runs, there was nowhere sane to break it -- and R18 must not flag it."""
    long = ", ".join("agent/PLAN-%03d.md" % n for n in range(80))
    assert len(long) > 768
    assert _r18("a.md", "Prose that is far too long: %s\n" % long) == []


def test_a_break_that_only_arrives_past_the_floor_does_not_count():
    """The MIRROR half of `_LONG_WITH_EARLY_BREAK`: the line's only sentence-ending period sits PAST 768, so there was no break available AT OR BEFORE the floor to skip, and the line is not flagged even though it plainly runs long and does end in a real sentence eventually."""
    text = ("x" * 800) + ". Trailing sentence that arrives after the floor.\n"
    assert len(text) > 768
    assert _r18("a.md", "Prose that is far too long: %s" % text) == []


def test_a_line_that_closes_on_its_own_period_is_not_a_width_finding_either():
    """A second, DISTINCT reason a long line is not flagged, alongside 'no break at all': the line reaches ITS OWN end on a genuine sentence-ending period, however many earlier breaks it also passed over. `_LONG_WITH_EARLY_BREAK` stops on a bare `x` precisely so this case and the CONTROL above stay separable."""
    text = _LONG_WITH_EARLY_BREAK + "."
    assert len(text) > 768
    assert _r18("a.md", "Prose that is far too long: %s\n" % text) == []


def test_the_loader_accepts_the_real_file():
    """The MIRROR for the seven refusals above. Without it they prove only that `load_rules` can raise, which a `raise RuleError` on line one would satisfy."""
    globals_, rules = ps.load_rules_file(ROOT)
    assert len(rules) >= 18
    assert globals_["max_line_length"] == 768


def test_the_gate_selftest_passes():
    """The gate's own controls, run from inside the suite that also tests it.

    Both matter and neither replaces the other: `--selftest` runs against a miniature rules file it controls completely, this module runs against the REAL one, and a bug in either direction shows up in exactly one of them.
    """
    assert ps.selftest() == 0


def test_the_entry_point_is_executable_and_declares_its_gate_header():
    entry = pathlib.Path(ROOT) / ".ci" / "scripts" / "quality" / "check_prose_style.py"
    text = entry.read_text(encoding="utf-8")
    assert "---- gate ----" in text
    assert "---- end gate ----" in text
    assert "lane: quality-content" in text
