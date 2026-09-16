"""`rediacc_ci.quality.prose_style`, driven mostly by the rules file's own examples.

WHAT IS WORTH TESTING HERE, and it is not "does the regex match". Every rule in
`.ci/config/prose-style-rules.json` ships with `examples`, and those examples ARE
the fixtures: this module generates one pytest case per example rather than
restating them, so a rule whose example stops being detected reds without anybody
remembering to write a second copy. The alternative -- a hand-written fixture list
beside the rules -- is two places to change and one of them always rots.

THE THREE EXPECTATIONS, and the third one is the honest part:

    flag        at least one rule must fire, and when the OWNING rule carries
                patterns, the owning rule must be among them
    clean       no rule may fire
    undetected  declared beyond mechanical detection, asserted NOT to fire, and
                COUNTED, so the coverage gap is a number in the output instead of
                a sentence in a comment somebody stops reading

`undetected` is not a skip and is not an excuse. R12's bad example "The project
failed." and R3's good example "The build failed after the last change." are the
same surface shape; a pattern catching one catches the other. The rules file says
so, this file asserts the consequence, and `test_undetectable_set_is_small_and_declared`
keeps the set from quietly growing into a way of retiring rules.

THE REST OF THIS FILE IS THE EXTRACTOR, which is where a prose linter actually
lives. Matching four characters is easy; deciding that the four characters inside
a fence, an inline code span, a blockquote or a `bad:` exemplar are not prose is
the entire gate, and each of those is a way for it to go green while meaning
nothing.
"""

import json
import os
import pathlib
import subprocess

import pytest

from rediacc_ci import gitx, paths
from rediacc_ci.quality import prose_style as ps

ROOT = paths.repo_root()
GLOBALS, RULES = ps.load_rules_file(ROOT)
BY_ID = {rule.id: rule for rule in RULES}


def _fired(text, scope="markdown"):
    return [f.rule for f in ps.lint_message(text, RULES, GLOBALS, scope)]


# ---------------------------------------------------------------------------
# The rules file itself
# ---------------------------------------------------------------------------


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

    A rule with none contributes ZERO cases below and is indistinguishable, from
    the outside, from a rule that passes.
    """
    bare = [r.id for r in RULES if not r.examples]
    assert not bare, "these rules ship no example, so nothing here exercises them: %s" % bare


def test_every_rule_has_a_good_example():
    """The NEGATIVE direction, per rule.

    A rule with only `bad` examples is a rule this suite cannot catch
    over-matching on, and an over-matching prose rule flags the whole tree.
    """
    one_sided = [r.id for r in RULES if not any(e.get("kind") == "good" for e in r.examples)]
    assert not one_sided, (
        "these rules ship no `good` example, so nothing proves they do not fire on the "
        "rewritten sentence: %s" % one_sided
    )


# ---------------------------------------------------------------------------
# The examples, as cases
# ---------------------------------------------------------------------------

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
    # SCOPE MATTERS AND IS NOT ALWAYS `markdown`. R8 and R11 are scoped, and an
    # example run under a scope its own rule excludes would assert the opposite
    # of what it was written to assert.
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
    # WHICH RULE HAD TO CATCH IT. `caught_by` lets an example say that the rule
    # really covering it is a neighbour -- R11's `Your feedback...` is caught by
    # R1's `\byour\b`, and R11 duplicating that pattern would be two spellings of
    # one rule. Naming it is the point: without it the assertion has to soften to
    # "something fired", and then an example quietly leaning on a neighbour is
    # indistinguishable from one its own rule covers.
    owner = example.get("caught_by", rule_id)
    if BY_ID[owner].raw_patterns or BY_ID[owner].detection == "measured":
        assert owner in fired, (
            "%s's bad example was expected to be caught by %s and fired %s instead: %r"
            % (rule_id, owner, fired, text)
        )


def test_undetectable_set_is_small_and_declared():
    """`undetected` must stay a declared exception, never a drain.

    Without a ceiling, the cheapest way to make any future rule pass is to mark
    its examples undetectable, which retires the rule while leaving it in the
    documentation looking enforced.
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


# ---------------------------------------------------------------------------
# The extractor, which is where the gate actually lives
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Code comments
# ---------------------------------------------------------------------------


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


# A docstring is a string ALONE on its logical line. The first version of this
# predicate asked whether the token's LINE starts with a quote, which made every
# element of every multi-line collection in the repository read as prose. Found
# 2026-09-16 on this guard's own `EDGE_CASES` table, where R2 flagged the capital
# `I` inside a test LABEL. Both directions, because "nothing is a docstring" also
# passes a one-sided version of this.
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


# An indented block is CODE wherever it appears, and "wherever" took two rounds
# to get right: the docstring arm landed first and the very next sweep flagged the
# COMMENT restating the same snippet. Both token kinds, both directions.
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


# ---------------------------------------------------------------------------
# Stable ids, and the baseline's composition guard
# ---------------------------------------------------------------------------


def _finding(path="a.md", line=3, rule="R1", text="Did you run it?"):
    return ps.Finding(path, line, rule, "you", text, "error")


def test_an_id_survives_a_move_and_not_a_rewrite():
    assert _finding(line=3).fid == _finding(line=900).fid
    assert _finding().fid != _finding(text="Did you run them?").fid
    assert _finding().fid != _finding(path="b.md").fid


def test_write_baseline_refuses_a_drain_that_added(tmp_path):
    """THE COMPOSITION TRAP, driven rather than argued.

    The set SHRINKS by one and still contains something brand new. A size
    comparison calls that progress; the diff calls it what it is.
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


def test_a_clean_drain_is_allowed(tmp_path):
    """The MIRROR: removing only must not be refused, or the guard blocks all progress."""
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    old = [_finding(text="one"), _finding(text="two")]
    ps.write_baseline_guarded(tmp_path, old, None, False)
    previous = ps.load_baseline(tmp_path)
    assert ps.write_baseline_guarded(tmp_path, [_finding(text="one")], previous, False) is None
    assert len(ps.load_baseline(tmp_path)) == 1


# ---------------------------------------------------------------------------
# run_check: the anti-vacuity arms, driven end to end
# ---------------------------------------------------------------------------


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
    """A real checkout: `tracked` staged, `ignore` written to .gitignore,
    `untracked` planted AFTER the add so git never sees it.

    NO COMMIT. `git ls-files` reads the index, so `git add` is the whole
    requirement, and skipping the commit skips every way a global identity
    or signing configuration could make this fixture machine-dependent.
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

    Distinct from the glob arm and invisible to it: the file count is healthy and
    the finding count is zero, which is exactly what a clean tree looks like.
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


# ---------------------------------------------------------------------------
# Reflow
# ---------------------------------------------------------------------------

REFLOW = [
    ("a hard-wrapped paragraph joins", "one two\nthree four\n", "one two three four\n"),
    ("a fenced block is untouched", "```\na\nb\n```\n", "```\na\nb\n```\n"),
    ("a list is untouched", "- a\n- b\n", "- a\n- b\n"),
    ("a numbered list is untouched", "1. a\n2. b\n", "1. a\n2. b\n"),
    ("a table is untouched", "| a | b |\n|---|---|\n", "| a | b |\n|---|---|\n"),
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


def test_reflow_over_the_width_rewraps_and_loses_no_word():
    text = ("word " * 200).strip() + "\n"
    out = ps.reflow_markdown(text, 80)
    assert max(len(line) for line in out.splitlines()) <= 80
    assert out.split() == text.split()
    assert ps.reflow_markdown(out, 80) == out


def test_reflow_of_the_real_corpus_is_a_dry_run_by_default(tmp_path, capsys):
    """`reflow` must not write unless asked. The default is the whole safety of it."""
    root = _tree(tmp_path, {"a.md": "one two\nthree four\n"})
    before = (root / "a.md").read_text(encoding="utf-8")
    assert ps.run_reflow(root, GLOBALS, ["a.md"]) == 0
    assert (root / "a.md").read_text(encoding="utf-8") == before
    # STDERR, not stdout. `log.info` writes to stderr here, and asserting the
    # wrong stream is how a message that stopped being printed goes unnoticed --
    # the assertion would still be reading an empty-by-design channel.
    assert "DRY RUN" in capsys.readouterr().err

    assert ps.run_reflow(root, GLOBALS, ["a.md"], write=True) == 0
    assert (root / "a.md").read_text(encoding="utf-8") == "one two three four\n"


# ---------------------------------------------------------------------------
# The loader refuses what it cannot trust
# ---------------------------------------------------------------------------

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


def test_the_loader_accepts_the_real_file():
    """The MIRROR for the seven refusals above. Without it they prove only that
    `load_rules` can raise, which a `raise RuleError` on line one would satisfy."""
    globals_, rules = ps.load_rules_file(ROOT)
    assert len(rules) >= 18
    assert globals_["max_line_length"] == 384


def test_the_gate_selftest_passes():
    """The gate's own controls, run from inside the suite that also tests it.

    Both matter and neither replaces the other: `--selftest` runs against a
    miniature rules file it controls completely, this module runs against the
    REAL one, and a bug in either direction shows up in exactly one of them.
    """
    assert ps.selftest() == 0


def test_the_entry_point_is_executable_and_declares_its_gate_header():
    entry = pathlib.Path(ROOT) / ".ci" / "scripts" / "quality" / "check_prose_style.py"
    text = entry.read_text(encoding="utf-8")
    assert "---- gate ----" in text
    assert "---- end gate ----" in text
    assert "lane: quality-content" in text
