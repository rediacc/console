#!/usr/bin/env python3
"""The prose-style engine: R1-R18, "the work, not the person".

WHAT THIS ENFORCES. `.ci/config/prose-style-rules.json` is the single source of
truth for the eighteen rules, their severities, their scopes, their patterns and
their examples. Nothing in this module restates a rule; it loads them, extracts
PROSE from a file or a message, and reports what fires. A rule added to that file
is enforced here with no edit to this one, and a rule whose patterns move here
would be a rule with two definitions.

=============================================================================
THE THING THIS MODULE IS MOSTLY MADE OF: DECIDING WHAT IS PROSE
=============================================================================

Matching `\\byou\\b` is four characters. Everything hard about this gate is
deciding WHERE to match it, because the tree is full of text that contains the
word and is not prose addressed to a reader:

  * a fenced code block holding a shell transcript
  * an inline code span, `` `your-branch` ``
  * a URL, a link target, an identifier
  * a quoted operator message, which is somebody else's words and is not ours
    to restyle
  * a `bad:` line in a style document, which exists PRECISELY to hold the
    violation, and flagging it would make this file unable to describe itself

So the extractors are the subject of this module and the matchers are a
footnote. They are deliberately CONSERVATIVE, and the reason is the asymmetry a
dead-code gate has in the other direction: a false positive here blocks an edit
or a commit that was fine, which teaches the next session to reach for the
suppression marker, and a gate everybody suppresses is a gate that has stopped
meaning what its name says. A missed violation costs one unstyled sentence.

ANTI-VACUITY, baked in rather than remembered. `check` over ZERO extracted lines
is a FAILURE, not a pass: a glob that stops matching, an extractor that starts
throwing everything away, and a genuinely clean tree are indistinguishable by
exit code, and only one of them is good news. The success line prints the SHAPE
(files, prose lines, rules loaded, advisory rules, undetectable examples) so a
reader can see a number collapse.

=============================================================================
THE BASELINE IS SHRINK-ONLY, AND ITS COMPOSITION IS CHECKED
=============================================================================

577 markdown files already exceed the 384-character limit and hundreds of
comment blocks are hard-wrapped at 100. None of that is reflowed by this change.
The debt is FROZEN in `.ci/config/prose-style-baseline.json` as stable ids, and
the gate fails on GROWTH.

Two halves, and the second is what keeps the set shrinking:

  * a NEW finding fails, and the message says "do not add it to the baseline"
  * a BASELINED finding that no longer fires ALSO fails, telling the author to
    drain with `--write-baseline`

AN ID IS A HASH OF THE FINDING'S TEXT, NEVER OF ITS LINE NUMBER. A line number
churns the moment a paragraph is inserted above it, and a baseline that churns
gets regenerated wholesale, which silently re-absorbs every fresh finding made
in the same hour. The price of hashing text is that a REWRITE re-keys the entry,
and that is the right price: a rewrite is exactly when a human should look at
the line again.

`--write-baseline` DIFFS THE OLD AND NEW SETS AND REFUSES A NON-EMPTY ADDED
SIDE. Comparing SIZES is a different and weaker claim: a drain that removes
thirty and adds one prints a smaller number and goes green while enshrining a
brand-new violation. The ADDED side has to be empty, so the only way a new
finding enters the baseline is to say so on the command line.
"""

import fnmatch
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap
import tokenize

from rediacc_ci import gitx, log, paths
from rediacc_ci.controls import Controls

RULES_FILE = ".ci/config/prose-style-rules.json"
BASELINE_FILE = ".ci/config/prose-style-baseline.json"

# Every scope a rule may name, plus the wildcard. Checked at load time rather than at match time: a typo in `scopes` would otherwise make a rule silently apply nowhere, which is the vacuity this gate is built against.
SCOPE_ALL = "all"

# Which scope a path is linted under. `.md` is prose end to end; a source file
# contributes only its COMMENTS, so it is linted under `comment`, which is the scope R11's imperative arm deliberately excludes.
SCOPE_BY_SUFFIX = {
    ".md": "markdown",
    ".py": "comment",
    ".ts": "comment",
    ".tsx": "comment",
    ".js": "comment",
    ".cjs": "comment",
    ".mjs": "comment",
    ".go": "comment",
    # REUSES "comment" RATHER THAN A NEW SCOPE NAMED "config". A JSON `_comment`/`why`/`reason` block is the same register, by the same authors, as a source-file comment -- and a "config" scope would silently disable R18, since R18's own `scopes` list is `["markdown", "comment", "pr"]` and does not name one.
    ".json": "comment",
}

# A line carrying one of these is exempt, the same shape `<!-- slop-ok -->` has
# in `.ci/config/content-quality-patterns.conf`. Loaded from the rules file;
# this is only the fallback for a caller with no rules loaded.
DEFAULT_MARKERS = ("<!-- style-ok -->", "# style-ok", "// style-ok")


# --------------------------------------------------------------------------- The rules ---------------------------------------------------------------------------


class Rule:
    """One loaded rule, with its patterns already compiled.

    COMPILED AT LOAD, NOT AT MATCH. A bad regex in the rules file is then a LOAD
    failure naming the rule and the pattern, instead of an exception thrown from
    inside a sweep over four thousand files where the traceback names this module
    and not the data that broke it.
    """

    __slots__ = (
        "description",
        "detection",
        "examples",
        "exceptions",
        "id",
        "patterns",
        "raw_patterns",
        "scopes",
        "severity",
        "title",
    )

    def __init__(self, data):
        self.id = data["id"]
        self.title = data["title"]
        self.description = data["description"]
        self.severity = data["severity"]
        self.scopes = tuple(data.get("scopes") or [SCOPE_ALL])
        self.detection = data.get("detection", "pattern")
        self.raw_patterns = tuple(data.get("patterns") or ())
        self.examples = tuple(data.get("examples") or ())
        self.patterns = tuple(_compile(self.id, p) for p in self.raw_patterns)
        self.exceptions = tuple(_compile(self.id, p) for p in (data.get("exceptions") or ()))

    def applies_to(self, scope):
        return SCOPE_ALL in self.scopes or scope in self.scopes

    @property
    def advisory(self):
        """A rule with no patterns and no measurement: documentation only.

        Counted and PRINTED rather than hidden, because "18 rules" and "9 rules
        that can fire" are different claims and a reader is entitled to the
        second one.
        """
        return not self.raw_patterns and self.detection != "measured"


class RuleError(ValueError):
    """A rules file that cannot be trusted. Never swallowed into a default."""


def _compile(rule_id, pattern):
    try:
        return re.compile(pattern)
    except re.error as exc:
        msg = "%s: pattern %r does not compile: %s" % (rule_id, pattern, exc)
        raise RuleError(msg) from exc


def load_rules(text):
    """Parse the rules document. Exported so the selftest drives it directly.

    REFUSES AN EMPTY RULE SET. A rules file that parsed to zero rules would make
    every `check` below exit 0 over nothing, and the output would read exactly
    like a clean tree.
    """
    try:
        doc = json.loads(text)
    except ValueError as exc:
        msg = "rules file is not valid JSON: %s" % exc
        raise RuleError(msg) from exc
    if not isinstance(doc, dict):
        msg = "rules file must be an object, got %s" % type(doc).__name__
        raise RuleError(msg)
    globals_ = doc.get("globals") or {}
    rules = [Rule(r) for r in (doc.get("rules") or ())]
    if not rules:
        msg = "rules file declares ZERO rules; every check would then pass over nothing"
        raise RuleError(msg)
    seen = set()
    for rule in rules:
        if rule.id in seen:
            msg = "duplicate rule id %s" % rule.id
            raise RuleError(msg)
        seen.add(rule.id)
        if rule.severity not in ("error", "warning"):
            msg = "%s: severity must be error or warning, got %r" % (rule.id, rule.severity)
            raise RuleError(msg)
        known = set(globals_.get("scopes") or ()) | {SCOPE_ALL}
        unknown = [s for s in rule.scopes if s not in known]
        if unknown:
            msg = (
                "%s: unknown scope(s) %s; a rule scoped to a name nothing produces applies "
                "nowhere and would never fire" % (rule.id, unknown)
            )
            raise RuleError(msg)
    return globals_, rules


def load_rules_file(root):
    path = pathlib.Path(root) / RULES_FILE
    if not path.is_file():
        msg = "rules file missing: %s" % RULES_FILE
        raise RuleError(msg)
    return load_rules(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- Extraction: what counts as prose ---------------------------------------------------------------------------

# An inline code span. Backtick runs of any length, matched shortest-first, so ``a `b` c`` yields one span and not the whole line.
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)*?\1", re.DOTALL)
# A markdown link or image: keep the TEXT, drop the destination. `[Read it](docs/ you-and-me.md)` must not be read as the word in its filename.
MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MD_AUTOLINK = re.compile(r"<[a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]*>")
BARE_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+")
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# A `bad:` exemplar. This document, the rules file and every style doc written against them CARRY their violations on purpose, and a gate that flagged them could not describe itself. The marker has to be at the START of the content.
BAD_EXAMPLE = re.compile(
    r"^\s*(?:[-*+>]\s*)?(?:\*\*)?(?:bad|wrong|avoid|before|✗|❌)(?:\*\*)?\s*[:\uff1a]"
)
# A markdown table's alignment row, which is punctuation rather than prose.
TABLE_RULE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
# A markdown table HEADER or DATA row -- any line using `|` as its cell delimiter, not just the alignment row TABLE_RULE matches above. Missing until 2026-09-17: reflow_markdown had no stop for an ordinary table row, so a table with more than one row after its header (no blank line separates consecutive rows, which is how every table in this tree is written) had its entire body
# flattened into one prose paragraph and rewrapped, destroying the table. Found live: `check_prose_style.py reflow --write` merged a 5-row table in a freshly written plan into two garbled lines the moment it ran tree-wide. `TABLE_RULE` alone caught the separator between the header and the first data row, so a two-row table (header + one data row) never showed the bug -- it takes 3+
# rows in a row for the gap to be visible.
TABLE_ROW = re.compile(r"^\s{0,3}\|")
# A line carrying an HTML comment: a gen-docs region marker (`<!-- >>> gen-docs: ... -->` / `<!-- <<< gen-docs -->`, see REGION_OPEN/
# REGION_CLOSE below) or a `<!-- style-ok -->` exemption (DEFAULT_MARKERS).
# Found live 2026-09-17, same session as TABLE_ROW: joining a marker line into an adjacent paragraph either shifted a gen-docs region boundary by a line (reported by check:ci-doc-region-parity as "closing marker with no open
# region") or widened/narrowed which physical line a style-ok exemption
# covers, surfacing hundreds of findings that were never real regressions. Every HTML comment in this tree is a directive, never prose ornamentation a reader would want re-flowed with its neighbours, so the rule is broad on
# purpose: contains `<!--` anywhere on the line, not just gen-docs/style-ok
# by name -- the next marker convention this repo invents gets the same protection for free instead of needing its own REFLOW_STOP entry. `.*` FIRST, DELIBERATELY: every other REFLOW_STOP pattern is anchored at column 0 and used with `.match()`, which only tests the START of the
# string. A `style-ok` marker is a TRAILING comment on an otherwise-ordinary
# prose line, so a bare `r"<!--"` would only catch a comment that opens the line and silently miss the far more common trailing shape -- caught by the synthetic test below before this pattern was ever wired in.
HTML_COMMENT_LINE = re.compile(r".*<!--")
# A short Title-Case "Key: value" line at column zero -- `Status:`, `Owner:`, `Updated:`, `Related:`, `Full-Text-Blob:`, and every other header field this repo's plan/handoff-document convention uses (`wl_checks.py`'s own header parsers, PLAN_STATUS_RE/PLAN_OWNER_RE, read exactly this shape). Found live 2026-09-17, third instance of the same class this session: joining "Status:
# done" into the very next line "Owner: e580532b" (no blank line separates them, which is how this repo writes every one of these headers) merged two independently-parsed fields into one line neither the plan-owner reader nor the handoff-checklist grammar can read anymore -- 89 files hit before this was caught. Matched GENERALLY (any Title-Case key, not an enumerated name list) on
# purpose: enumerating specific keys is exactly how the first two REFLOW_STOP gaps (tables, HTML comments) were found -- one
# case at a time, after real damage was already committed. Matching too much
# here (a "Note: ..." aside staying on its own line) is the safe direction;
# matching too little is what broke 89 files.
DOC_HEADER_FIELD = re.compile(r"^\s{0,3}\*{0,2}[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\*{0,2}:\s\S")
# A real HTML BLOCK element this repo's markdown actually uses -- `<details><summary>...</summary>`/`</details>` for collapsible sections, tables, images, line breaks -- found by SEARCHING THE CLASS after the operator's stop-hook judge asked whether more REFLOW_STOP gaps existed rather than waiting for a fourth one to corrupt a fourth file. Confirmed live: joining `</details>` into
# a wrapped prose paragraph moves the closing tag off its own line, which is exactly the shape that breaks GitHub's collapsible-section rendering. `HTML_TAG` (used elsewhere in this module
# for scrubbing tags out of LINT text) is deliberately NOT reused here: its
# broad `</?[a-zA-Z][^>]*>` also matches placeholder notation this repo's own prose uses constantly (`<machine>`, `<FILL: why>`), which would silently stop far more joins than the actual bug ever touched. This is a narrow, measured allowlist of the block elements really present in this tree (`grep`, 2026-09-17: 172 real hits across 69 files, versus 2860 for the broad pattern) --
# widen it if a future element joins the corpus, the same way `HTML_COMMENT_LINE` was written broad because comments have no such placeholder-collision problem.
HTML_BLOCK_TAG = re.compile(
    r".*</?(?:details|summary|div|table|tr|td|th|br|img|sub|sup|kbd|picture|source)\b",
    re.IGNORECASE,
)
BLOCKQUOTE = re.compile(r"^\s{0,3}>")
# A `gen-docs` generated region. Everything between the two markers is MACHINE OUTPUT, and `check:ci-doc-region-parity` refuses a hand-edit to it in as many words: "the committed bytes of every gen-docs region must equal what the generator produces".
#
# LINTING TEXT NOBODY MAY EDIT IS A TRAP, and it was sprung immediately. The `prose-style` region renders one row per rule, so its own table contains the
# cells `No "you"` and `Hidden "you"`; the pre-edit guard refused the document
# carrying it, and the only ways out would have been to rename the rules or to suppress the gate. Found 2026-09-16 by the guard blocking this gate's own reference document at the moment it was written.
REGION_OPEN = re.compile(r"^\s*<!--\s*>>>\s*gen-docs:")
REGION_CLOSE = re.compile(r"^\s*<!--\s*<<<\s*gen-docs\s*-->")
ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
# Setext underlines and thematic breaks: punctuation, and long ones would otherwise read as a very long prose line.
RULE_LINE = re.compile(r"^\s{0,3}(?:[-*_=]\s*){3,}$")
# A markdown link REFERENCE definition: `[id]: https://...`
LINK_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
# A word made of letters, at least two, with no digits or underscores. What is left after stripping is scanned as text, but only these are eligible to be a
# pronoun; the filter keeps `you_id` and `PROSE_STYLE` out without needing a
# separate identifier pass.
INDENT_CODE = re.compile(r"^(?: {4,}|\t)")


class Line:
    """One extracted prose line: where it came from, and what is left of it.

    `raw` is the untouched source line, kept because R18 measures the LINE and
    not the residue; `text` is what the pattern rules see, after code spans,
    URLs and link targets are removed.
    """

    __slots__ = ("lineno", "raw", "text")

    def __init__(self, lineno, raw, text):
        self.lineno = lineno
        self.raw = raw
        self.text = text

    def __repr__(self):
        return "Line(%d, %r)" % (self.lineno, self.text)

    def __eq__(self, other):
        return isinstance(other, Line) and (self.lineno, self.raw, self.text) == (
            other.lineno,
            other.raw,
            other.text,
        )

    def __hash__(self):
        return hash((self.lineno, self.raw, self.text))


def scrub(text):
    """Strip everything that is not prose from ONE line.

    ORDER MATTERS AND IS NOT ARBITRARY. Code spans go first, because a URL or a
    link inside one is already exempt and running the link stripper first would
    eat the backticks that proved it. Link TEXT is preserved deliberately:
    `[Send the file](x)` is prose a reader reads, and dropping it with its
    target would exempt every piece of link text in the tree.
    """
    out = HTML_COMMENT.sub(" ", text)
    out = INLINE_CODE.sub(" ", out)
    out = MD_LINK.sub(r"\1", out)
    out = MD_AUTOLINK.sub(" ", out)
    out = BARE_URL.sub(" ", out)
    return HTML_TAG.sub(" ", out)


def is_marked(line, markers):
    return any(marker in line for marker in markers)


def markdown_lines(text, markers=DEFAULT_MARKERS):
    """Every prose line of a markdown document, fences and quotations removed.

    WHAT IS DROPPED, and the reason for each, because a reader deciding whether a
    green means anything needs the list rather than the count:

      frontmatter      metadata, and its values are ids and dates
      fenced code      transcripts and source, where the words are not addressed
                       to anyone
      indented code    same, at the cost of also dropping deeply nested list
                       prose. Conservative on purpose; see the module header.
      blockquotes      SOMEBODY ELSE'S WORDS. This repository quotes its operator
                       verbatim in several documents, and restyling a quotation
                       would misreport what was said.
      bad: exemplars   the violation is the POINT of the line
      headings, tables, rules, link definitions, and lines carrying a marker
    """
    lines = []
    in_fence = None
    in_frontmatter = False
    in_region = False
    raw_lines = text.splitlines()
    for index, raw in enumerate(raw_lines, start=1):
        if in_region:
            if REGION_CLOSE.match(raw):
                in_region = False
            continue
        if REGION_OPEN.match(raw):
            in_region = True
            continue
        if index == 1 and raw.strip() == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if raw.strip() in ("---", "..."):
                in_frontmatter = False
            continue
        fence = FENCE.match(raw)
        if in_fence is not None:
            if fence and fence.group(1)[0] == in_fence[0] and len(fence.group(1)) >= len(in_fence):
                in_fence = None
            continue
        if fence:
            in_fence = fence.group(1)
            continue
        if not raw.strip():
            continue
        if is_marked(raw, markers):
            continue
        if INDENT_CODE.match(raw) or BLOCKQUOTE.match(raw):
            continue
        if ATX_HEADING.match(raw) or RULE_LINE.match(raw) or TABLE_RULE.match(raw):
            continue
        if LINK_DEF.match(raw) or BAD_EXAMPLE.match(raw):
            continue
        scrubbed = scrub(raw).strip()
        if not scrubbed:
            continue
        lines.append(Line(index, raw, scrubbed))
    return lines


def python_comment_lines(text, markers=DEFAULT_MARKERS):
    """Comments and docstrings of a Python module, by TOKENIZING it.

    NOT A REGEX OVER `#`. `re.split("#")` reports the fragment identifier inside
    `"https://x/#frag"` as a comment, and a string containing the word `you` as
    prose. `tokenize` knows which is which because it is the same lexer the
    interpreter uses, and on a file it cannot lex it raises rather than guessing,
    at which point the caller falls back and SAYS it fell back.
    """
    lines = []
    reader = io.StringIO(text).readline
    stream = list(tokenize.generate_tokens(reader))
    for index, token in enumerate(stream):
        if token.type == tokenize.COMMENT:
            # `# code` IS AN INDENTED BLOCK, exactly as ` code` is in markdown, and it is how a Python comment shows a snippet. Measured 2026-09-16 at `prose_style.py:388`: the fix for the docstring case below handled STRING bodies only, and the very next run flagged the capital `I` in the COMMENT restating that same literal block. The gate found a false positive in the comment
            # explaining its previous false positive, twice, which is what finally made the indent rule apply to both token kinds instead of one.
            after_hash = token.string.lstrip("#")
            if _indent(after_hash) >= 4:
                continue
            body = after_hash.strip()
        elif token.type == tokenize.STRING and _is_docstring(stream, index):
            body = token.string
        else:
            continue
        start = token.start[0]
        # THE DOCSTRING'S OWN INDENT, which is what makes an indented block inside it detectable at all. A markdown document's code block is four
        # spaces from column zero; a docstring's is four spaces from wherever the
        # docstring starts, and a function's docstring already starts at four.
        #
        # MEASURED, NOT ANTICIPATED. `prose_style.py:404` -- this file -- carries a reStructuredText literal block holding the very test label that exposed the docstring bug above::
        #
        # "an edit whose new_string says I",
        #
        # and R2 flagged its capital `I`. The gate found a false positive in the comment explaining its own last false positive, which is as good an argument as there is for treating an indented block as code everywhere rather than only in markdown.
        base = token.start[1] if token.type == tokenize.STRING else 0
        for offset, piece in enumerate(body.splitlines()):
            lineno = start + offset
            raw = _nth_line(text, lineno)
            if is_marked(raw, markers) or BAD_EXAMPLE.match(piece):
                continue
            if offset and _indent(raw) >= base + 4:
                continue
            scrubbed = scrub(_strip_quotes(piece)).strip()
            if not scrubbed:
                continue
            lines.append(Line(lineno, raw, scrubbed))
    return lines


def _indent(raw):
    """Leading whitespace width, a tab counting as four. Blank lines read as zero."""
    width = 0
    for char in raw:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            return width
    return 0


_LINE_OPENERS = frozenset(
    {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING}
)
_LINE_CLOSERS = frozenset({tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER})


def _is_docstring(stream, index):
    """A STRING token that is a whole EXPRESSION STATEMENT: a docstring, or bare prose.

    THE FIRST VERSION ASKED WHETHER THE TOKEN'S LINE STARTS WITH A QUOTE, and it
    was wrong in a way that only a data structure shows. Measured 2026-09-16 on
    `block_prose_style_edit.py:129`, a row of a test-case table::

        "an edit whose new_string says I",

    That line starts with a quote, so it read as a docstring, and R2 flagged the
    capital `I` inside a TEST LABEL. Every element of every multi-line list,
    tuple and dict in the repository was being linted as prose, which is both a
    false-positive source and a quiet widening of what this gate claims to scan.

    The real predicate is grammatical rather than textual: a docstring is a
    string that is ALONE on its logical line. So the token before it must open a
    line (NEWLINE / NL / INDENT / DEDENT / ENCODING) and the token after it must
    close one. A collection element fails the second test, because what follows
    it is a comma.

    A BARE MODULE-LEVEL STRING PASSES BOTH AND IS DELIBERATELY ADMITTED: it is
    either documentation or dead, and linting it is right in the first case and
    harmless in the second.

    AN IMPLICITLY CONCATENATED FRAGMENT IS NOT A WHOLE LOGICAL STRING, and treating NL as a genuine opener/closer without also looking past it missed that. Found live by review 2026-09-16, reproduced against the `PERMISSION` regex tuple in `block_secret_exposure.py`::

        PERMISSION = (
            r"can (you|I) "
            r"do something"
        )

    Both STRING tokens sit inside the parens with only an NL between them and the surrounding tokens, so the OLD before/after scan (stop at the first non-COMMENT token, treat a bare NL as an opener/closer) read EACH fragment as alone on its logical line and linted regex source as prose.

    The scan now also steps PAST an NL looking for the real neighbour: a fragment's true neighbour on one side is always another STRING token, which is not in `_LINE_OPENERS`, so the walk-past correctly disqualifies both fragments instead of stopping one token too early. A genuine standalone string is unaffected, because there is no second STRING for the walk to find.
    """
    before = None
    for i in range(index - 1, -1, -1):
        if stream[i].type in (tokenize.COMMENT, tokenize.NL):
            continue
        before = stream[i].type
        break
    if before is not None and before not in _LINE_OPENERS:
        return False
    after = None
    for i in range(index + 1, len(stream)):
        if stream[i].type in (tokenize.COMMENT, tokenize.NL):
            continue
        after = stream[i].type
        break
    return after is None or after in _LINE_CLOSERS


_QUOTES = re.compile(r"^[rRbBuUfF]{0,2}('''|\"\"\"|'|\")|('''|\"\"\"|'|\")$")


def _strip_quotes(piece):
    out = _QUOTES.sub("", piece)
    return _QUOTES.sub("", out)


def _nth_line(text, lineno):
    rows = text.splitlines()
    return rows[lineno - 1] if 1 <= lineno <= len(rows) else ""


# `//` and `/* */`, found by a scanner rather than a regex, for the same reason the Python side tokenizes: `"https://x"` contains `//` and is not a comment, and a regex that excluded it by looking for a preceding `:` would then miss
# `const a = b // c`.
def cstyle_comment_lines(text, markers=DEFAULT_MARKERS):
    """Comments of a `//` + `/* */` language, string and template literals skipped."""
    lines = []
    i = 0
    lineno = 1
    length = len(text)
    quote = None
    while i < length:
        char = text[i]
        if char == "\n":
            lineno += 1
            i += 1
            continue
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
            _emit(lines, text, lineno, text[i + 2 : end], markers)
            i = end
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            end = length if end == -1 else end
            block = text[i + 2 : end]
            for offset, piece in enumerate(block.splitlines()):
                _emit(lines, text, lineno + offset, piece.lstrip().lstrip("*"), markers)
            lineno += block.count("\n")
            i = end + 2
            continue
        i += 1
    return lines


def _emit(lines, text, lineno, piece, markers):
    raw = _nth_line(text, lineno)
    if is_marked(raw, markers) or BAD_EXAMPLE.match(piece):
        return
    scrubbed = scrub(piece).strip()
    if scrubbed:
        lines.append(Line(lineno, raw, scrubbed))


# JSON string values whose key marks them as an IDENTIFIER or a QUOTED EXAMPLE rather than prose about the work. `patterns`/`exceptions` are regex
# text; `text` is a rule's own bad/good exemplar (the JSON analogue of
# `BAD_EXAMPLE`, since a JSON example's `kind: "bad"` marker sits on a DIFFERENT physical line than its `text`, so the character-level BAD_EXAMPLE
# match cannot see it); `id`/`glob`/`schema`/`$schema`/`format`/`version` are
# short machine-facing tokens, never a sentence about the work.
JSON_SKIP_KEYS = frozenset(
    ("patterns", "exceptions", "text", "id", "glob", "schema", "$schema", "format", "version")
)

_JSON_KEYED_STRING = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')
_JSON_ARRAY_STRING = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$')


def json_prose_lines(text, markers=DEFAULT_MARKERS):
    """Prose lines of a `.json` file: PHYSICAL LINE, decoded string VALUES only.

    NOT A PARSED WALK. `json.load` gives no line numbers, so a `Finding`
    (which is anchored to a line) could not be built from one, and a
    decoded-string-length measure would let a 380-char value sitting at 300
    columns of indentation pass while the file is unreadable as text. R18
    measures what a reader of the FILE sees, the same contract `Line.raw`
    already keeps for every other suffix.

    ONE LINE, ONE JSON TOKEN. This repository's `.json` is machine-written
    with `json.dumps(..., indent=2)` (or hand-written to match), so a
    `"key": "value"` pair and an array element each occupy exactly one
    physical line in practice. A minified or reformatted file degenerates to
    the file being unreadable as text, which is the same failure mode a
    minified `.js` file already has against `cstyle_comment_lines`.

    KEYS ARE NEVER PROSE, only the string VALUE beside one is -- catches a
    key like `"glob": "agent/pr/*.md"` before it is scanned as a sentence.
    An ARRAY ELEMENT has no key at all: this is the wrapped-prose shape
    `exempt_why`/`exclude_why`/an array-form `reason` already use, and each
    element is measured on its own line exactly the way a hand-wrapped
    paragraph in a `.md` file is.
    """
    lines = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        keyed = _JSON_KEYED_STRING.match(raw)
        if keyed:
            key, value = keyed.groups()
            if key in JSON_SKIP_KEYS:
                continue
        else:
            arrayed = _JSON_ARRAY_STRING.match(raw)
            if not arrayed:
                continue
            (value,) = arrayed.groups()
        if is_marked(raw, markers) or BAD_EXAMPLE.match(value):
            continue
        try:
            decoded = json.loads('"%s"' % value)
        except ValueError:
            continue
        scrubbed = scrub(decoded).strip()
        if scrubbed:
            lines.append(Line(lineno, raw, scrubbed))
    return lines


def extract(path, text, markers=DEFAULT_MARKERS):
    """Prose lines of one file, dispatched on its suffix.

    A file whose Python will not tokenize falls back to the C-style scanner,
    which finds nothing, and the CALLER is told: a file that silently extracted
    nothing is indistinguishable from a clean one, which is the whole vacuity
    problem in miniature.
    """
    suffix = pathlib.Path(path).suffix
    if suffix == ".md":
        return markdown_lines(text, markers), None
    if suffix == ".py":
        try:
            return python_comment_lines(text, markers), None
        except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
            return [], "%s did not tokenize as Python (%s), so NOTHING was extracted" % (path, exc)
    if suffix == ".json":
        return json_prose_lines(text, markers), None
    return cstyle_comment_lines(text, markers), None


# --------------------------------------------------------------------------- Matching ---------------------------------------------------------------------------


class Finding:
    __slots__ = ("lineno", "path", "rule", "severity", "snippet", "text")

    def __init__(self, path, lineno, rule, snippet, text, severity):
        self.path = path
        self.lineno = lineno
        self.rule = rule
        self.snippet = snippet
        self.text = text
        self.severity = severity

    @property
    def fid(self):
        """The stable id: a hash of the PATH, the RULE and the TEXT.

        NOT the line number. See the module header; this is the half that lets a
        paragraph move without regenerating the whole baseline.
        """
        digest = hashlib.sha256(
            ("%s\x1f%s\x1f%s" % (self.path, self.rule, self.text)).encode(
                "utf-8", "surrogateescape"
            )
        )
        return digest.hexdigest()[:16]

    def render(self):
        return "%s:%d  %s  %s" % (self.path, self.lineno, self.rule, self.snippet)


def lint_line(line, rules, scope, max_len):
    """Every rule that fires on ONE extracted line.

    An EXCEPTION on a rule suppresses that rule for the whole line, which is what
    makes `My mistake; the fix is on the way.` legal under R2 while `My branch is
    ready.` is not.
    """
    hits = []
    for rule in rules:
        if not rule.applies_to(scope):
            continue
        if rule.detection == "measured":
            if max_len is not None and len(line.raw) > max_len:
                hits.append((rule, "line is %d characters, limit %d" % (len(line.raw), max_len)))
            continue
        if not rule.patterns:
            continue
        if any(exc.search(line.text) for exc in rule.exceptions):
            continue
        for pattern in rule.patterns:
            found = pattern.search(line.text)
            if found:
                hits.append((rule, found.group(0)))
                break
    return hits


def lint_text(path, text, rules, globals_, scope=None):
    """Findings for one document. Returns `(findings, note)`.

    `note` is not None when extraction could not be trusted, and the caller must
    treat it as UNCHECKED rather than folding it into a pass.
    """
    markers = tuple(globals_.get("ignore_markers") or DEFAULT_MARKERS)
    max_len = globals_.get("max_line_length")
    if scope is None:
        scope = SCOPE_BY_SUFFIX.get(pathlib.Path(path).suffix, "markdown")
    lines, note = extract(path, text, markers)
    findings = []
    for line in lines:
        for rule, snippet in lint_line(line, rules, scope, max_len):
            findings.append(Finding(path, line.lineno, rule.id, snippet, line.text, rule.severity))
    return findings, note


def lint_message(text, rules, globals_, scope):
    """Findings for a MESSAGE rather than a file: a commit body, a PR body, an edit.

    Scoped by the caller, because a commit message and an Edit's new content are
    the same bytes to this function and different things to R11.
    """
    markers = tuple(globals_.get("ignore_markers") or DEFAULT_MARKERS)
    max_len = globals_.get("max_line_length")
    findings = []
    for line in markdown_lines(text, markers):
        for rule, snippet in lint_line(line, rules, scope, max_len):
            findings.append(
                Finding("<message>", line.lineno, rule.id, snippet, line.text, rule.severity)
            )
    return findings


# --------------------------------------------------------------------------- Discovery ---------------------------------------------------------------------------


def tracked_files(root):
    """Every path git TRACKS under `root`, repo-relative, present on disk.

    GIT, NOT A FILESYSTEM WALK, and the reason is the artifact this gate writes.
    `.ci/config/prose-style-baseline.json` is COMMITTED and SHRINK-ONLY, so
    every path in it must exist in a fresh checkout. A walk enumerates whatever
    the machine happens to hold -- a gitignored scratch directory, a file not
    yet added, a peer's stale worktree -- and `--write-baseline` then freezes
    rows CI is structurally incapable of satisfying. 944aa6210 is the receipt:
    six precompact-facts entries, ignored by a gitignore of a bare star,
    reded CI with "6 baselined finding(s) no longer fire".

    TRACKED, NOT MERELY NOT-IGNORED. `dead_python.py:249` adds
    `--others --exclude-standard` and is right to: a reachability scan that
    could not see a brand-new module would call it dead. Here the claim is
    about what the repository SHIPS, and an untracked-but-unignored file is the
    same contamination as an ignored one -- it is on one disk and in no
    checkout.

    REFUSES RATHER THAN RETURNING NOTHING, which is what
    `plant_proofs.py:867-877`, `python_env_registry.py:345-355` and
    `check_language_policy.py:235-241` all do at this exact call. An empty
    corpus and a clean tree are indistinguishable by exit code, and only one is
    good news.

    `existing=True` drops index entries whose file is gone -- gitx TRAP 1's
    second half. A file removed with `rm` rather than `git rm` would otherwise
    arrive here, fail to open, and land in the UNCHECKED list that `run_check`
    treats as a failure.
    """
    if not gitx.is_work_tree(root):
        msg = (
            "%s is not a git checkout, so the tracked corpus this gate is built on cannot be "
            "enumerated. Reporting zero files would report zero INPUTS, which reads exactly "
            "like a clean tree." % root
        )
        raise RuleError(msg)
    return gitx.ls_files(root=root, existing=True)


def under_excluded_dir(rel, skip):
    """Does any ANCESTOR directory of `rel` appear in `skip`?

    BOTH SPELLINGS, because `exclude_dirs` has always carried both and the walk
    this replaces honoured both: a BARE NAME prunes at every depth, a
    repo-relative PATH prunes once. Dropping the bare-name arm is not a
    tidy-up, it is a corpus change -- `build` alone admits the tracked modules
    under `.ci/rediacc_ci/build/`, `private` admits `.ci/rediacc_ci/private/`.

    A FILE is never matched, only its ancestors, so a tracked `docs/build.md`
    survives an entry of `build`.
    """
    parts = rel.split("/")
    for index in range(len(parts) - 1):
        if parts[index] in skip or "/".join(parts[: index + 1]) in skip:
            return True
    return False


def discover(root, globals_, subtrees=None):
    """Every TRACKED file the globals admit, sorted.

    EXPLICIT TARGETS DO NOT COME THROUGH HERE, and that is the distinction this
    function exists on one side of. `run_check` and `run_reflow` both spell it
    `targets or discover(...)`: a path named on the command line is scanned
    whatever git thinks of it, because the caller named it and a file being
    written for the first time is untracked by definition. Only the BROAD
    sweep -- the default `check`, and every `--write-baseline` -- is narrowed
    to what git tracks, because only the broad sweep writes the committed
    baseline.

    SORTED, NOT READDIR ORDER. `check_content_quality.py` records measuring
    the same thing on this tree: raw `find` is not lexicographic here, so an
    unsorted walk makes the output depend on filesystem state rather than on
    repository content, and two runs on two machines disagree for no reason a
    reader can act on. git's own order is not this order either, so the sort
    stays.
    """
    patterns = tuple(globals_.get("include") or ())
    skip = set(globals_.get("exclude_dirs") or ())
    prefixes = tuple(str(s).rstrip("/") + "/" for s in (subtrees or ()))
    out = []
    for path in tracked_files(root):
        rel = path.replace(os.sep, "/")
        if not any(fnmatch.fnmatchcase(rel, pat) for pat in patterns):
            continue
        if under_excluded_dir(rel, skip):
            continue
        if prefixes and not rel.startswith(prefixes):
            continue
        out.append(rel)
    return sorted(set(out))


def read_text(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="surrogateescape")


def exemptions(globals_):
    """`[(glob, reason)]`, refusing any entry without a `BLOCKER:` reason.

    THE REFUSAL IS THE FEATURE. `docs/agent-reference/suppressions.md` requires a
    `BLOCKER:` on every allowlist entry in this tree, and an exemption mechanism
    that accepted a bare glob would be the one place that rule was not enforced
    by anything. A reason nobody had to type is a reason nobody will check.
    """
    out = []
    for entry in globals_.get("exempt_paths") or ():
        raw = entry.get("reason", "")
        # A REASON MAY BE AN ARRAY OF LINES, the same shape `exempt_why` and `exclude_why` already use elsewhere in this file. .json carries no R18 line-length check of its own -- it is absent from `include` -- so a reason long enough to need wrapping has nowhere else to be wrapped. Joined with a space, it reads as the one sentence it is.
        reason = " ".join(raw) if isinstance(raw, list) else raw
        if not reason.startswith("BLOCKER:"):
            msg = "exempt_paths entry %r carries no BLOCKER: reason" % entry.get("glob")
            raise RuleError(msg)
        out.append((entry["glob"], reason))
    return out


def exempt_for(rel, exempts):
    """The reason `rel` is exempt, or None.

    SEGMENT BY SEGMENT, NOT `fnmatch` OVER THE WHOLE PATH. `fnmatch`'s `*`
    crosses `/` -- `agent/*/STATE.md` would match `agent/archive/x/y/STATE.md`
    under it -- so an exemption written to cover one directory level silently
    covers every level below it. An exemption that is wider than its author
    believes is the shape this whole mechanism exists to keep visible, so the
    glob is matched the way a reader reads it: one segment at a time, and the
    depths must agree.
    """
    parts = rel.replace(os.sep, "/").split("/")
    for glob, reason in exempts:
        wanted = glob.split("/")
        if len(wanted) != len(parts):
            continue
        if all(fnmatch.fnmatchcase(got, want) for got, want in zip(parts, wanted, strict=True)):
            return reason
    return None


# --------------------------------------------------------------------------- Reflow ---------------------------------------------------------------------------

# A line that starts a structure reflow must not join into a paragraph. Reflow touches exactly one thing: a run of consecutive plain prose lines.
REFLOW_STOP = (
    FENCE,
    ATX_HEADING,
    RULE_LINE,
    TABLE_RULE,
    TABLE_ROW,
    LINK_DEF,
    BLOCKQUOTE,
    INDENT_CODE,
    HTML_COMMENT_LINE,
    DOC_HEADER_FIELD,
    HTML_BLOCK_TAG,
)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")


def reflow_markdown(text, width):
    """Join hard-wrapped prose paragraphs to one line, then wrap at `width`.

    IDEMPOTENT BY CONSTRUCTION, and that is a property rather than a hope: the
    output of a join-then-wrap is a paragraph whose lines are all at or under
    `width`, and joining those again reproduces the same string before the same
    wrap. `test_reflow_is_idempotent` drives it rather than trusting the
    argument.

    WHAT IT REFUSES TO TOUCH: fences, headings, tables, blockquotes, indented
    code, link definitions and LIST ITEMS. A list item's wrapped continuation
    lines carry indentation that is part of the structure, and a joiner that did
    not know the difference would flatten a nested list into a paragraph. The
    conservative choice loses some reflow and cannot corrupt a document.
    """
    out = []
    buffer = []
    in_fence = None
    in_frontmatter = False

    def flush():
        if not buffer:
            return
        joined = " ".join(piece.strip() for piece in buffer)
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        if len(joined) <= width:
            out.append(joined)
        else:
            out.extend(
                textwrap.wrap(
                    joined,
                    width=width,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        buffer.clear()

    raw_lines = text.splitlines()
    for index, raw in enumerate(raw_lines):
        if index == 0 and raw.strip() == "---":
            in_frontmatter = True
            out.append(raw)
            continue
        if in_frontmatter:
            out.append(raw)
            if raw.strip() in ("---", "..."):
                in_frontmatter = False
            continue
        fence = FENCE.match(raw)
        if in_fence is not None:
            out.append(raw)
            if fence and fence.group(1)[0] == in_fence[0] and len(fence.group(1)) >= len(in_fence):
                in_fence = None
            continue
        if fence:
            flush()
            out.append(raw)
            in_fence = fence.group(1)
            continue
        if not raw.strip():
            flush()
            out.append(raw)
            continue
        if LIST_ITEM.match(raw) or any(p.match(raw) for p in REFLOW_STOP):
            flush()
            out.append(raw)
            continue
        buffer.append(raw)
    flush()
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing


# --------------------------------------------------------------------------- Baseline ---------------------------------------------------------------------------


def load_baseline(root):
    """The frozen ids, as `{id: (path, rule)}`, or None when there is no baseline.

    THE FILE IS GROUPED BY PATH AND CARRIES IDS ONLY, and the reason is a measured
    one rather than tidiness. The first cut stored one flat record per finding
    with its text, and produced a 2.3 MB file against a repository whose largest
    data file is a 620 KB lockfile. A baseline nobody can open in a diff is a
    baseline that gets regenerated wholesale, which is precisely the failure the
    stable-id design exists to prevent. Grouped, ids only, it is an order of
    magnitude smaller and it READS: a reader sees which files carry debt and
    under which rule, which is the question anyone opening it has.
    """
    path = pathlib.Path(root) / BASELINE_FILE
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for rel, by_rule in (doc.get("findings") or {}).items():
        for rule, ids in by_rule.items():
            for fid in ids:
                out[fid] = (rel, rule)
    return out


def write_baseline(root, findings, previous):
    """Write the baseline, refusing a drain that ADDED anything.

    THE COMPOSITION TRAP, which a size comparison does not catch. A drain here
    can print `2,189 -> 2,160` and go green while the two sets differ by thirty
    removed and ONE added -- a fresh violation, made in the same hour, silently
    enshrined. So the ADDED side is diffed and must be empty. Baselining a new
    finding is still possible; it takes `--accept-new`, at the command line,
    where it is a decision somebody typed.
    """
    path = pathlib.Path(root) / BASELINE_FILE
    entries = {f.fid: f for f in findings}
    added = sorted(set(entries) - set(previous or {}))
    grouped = {}
    # DEDUPED BY fid, THE SAME WAY `entries`/`count` ARE. `fid` hashes (path, rule, text) and not the line number, so the identical template string flagged on two physical lines of one file collapses to one entry in `findings` -- and `by_rule` must collapse it the same way, or its sum drifts from `count` by exactly the number of such repeats. Measured live: 8 repeated (path, rule,
    # text) triples inflated the sum by 11 before this fix.
    by_rule = {}
    for finding in entries.values():
        grouped.setdefault(finding.path, {}).setdefault(finding.rule, set()).add(finding.fid)
        by_rule[finding.rule] = by_rule.get(finding.rule, 0) + 1
    doc = {
        "why": [
            "Frozen prose-style debt. SHRINK-ONLY: a new finding fails the gate and does NOT",
            "belong here. Drain with `check_prose_style.py check --write-baseline` after",
            "fixing something, never to make a red go away.",
            "",
            "Ids are a hash of (path, rule, finding text). NOT the line number: a line number",
            "churns when a paragraph moves above it, and a baseline that churns gets",
            "regenerated wholesale, which re-absorbs every fresh finding made that hour. The",
            "price is that a REWRITE re-keys an entry, and that is the right price: a rewrite",
            "is exactly when a human should look at the line again. When a re-key happens,",
            "hand-edit the one line rather than regenerating, which would rewrite every entry",
            "and absorb any other writer's fresh findings.",
            "",
            "`--write-baseline` REFUSES a drain whose ADDED side is non-empty, because a total",
            "that shrank by 29 can still hide one brand-new violation. Comparing sizes is not",
            "the same claim as diffing the sets.",
        ],
        "count": len(entries),
        "files": len(grouped),
        "by_rule": dict(sorted(by_rule.items())),
        "findings": {
            rel: {rule: sorted(ids) for rule, ids in sorted(rules.items())}
            for rel, rules in sorted(grouped.items())
        },
    }
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


# --------------------------------------------------------------------------- The gate ---------------------------------------------------------------------------


def _shape(globals_, rules, files, prose_lines):
    advisory = [r.id for r in rules if r.advisory]
    undetectable = sum(1 for r in rules for e in r.examples if e.get("expect") == "undetected")
    return (
        "%d file(s), %d prose line(s), %d rule(s) loaded, %d advisory (%s), "
        "%d example(s) declared beyond mechanical detection, limit %d chars"
        % (
            files,
            prose_lines,
            len(rules),
            len(advisory),
            ",".join(advisory) or "none",
            undetectable,
            globals_.get("max_line_length", 0),
        )
    )


def run_check(
    root, globals_, rules, targets, *, write_baseline=False, accept_new=False, as_json=False
):
    """The `check` subcommand. Returns an exit code.

    ZERO SCANNED FILES IS A FAILURE. So is zero extracted prose lines across a
    non-empty file set: the second one is the extractor breaking rather than the
    glob, and both look like a clean tree from the outside.
    """
    # TARGETS BYPASS DISCOVERY DELIBERATELY. A path named on the command line
    # is scanned whether or not git tracks it; only the broad sweep is
    # narrowed.
    try:
        files = targets or discover(root, globals_)
    except RuleError as exc:
        log.error(str(exc))
        return 1
    if not files:
        log.error(
            "VACUOUS: zero files matched. This gate is not seeing the tree, and its green "
            "would mean nothing. Check `globals.include` in %s." % RULES_FILE
        )
        return 1

    exempts = exemptions(globals_)
    findings = []
    notes = []
    exempted = {}
    prose_lines = 0
    for rel in files:
        full = pathlib.Path(root) / rel
        try:
            text = read_text(full)
        except OSError as exc:
            notes.append("%s could not be read (%s), so it went UNCHECKED" % (rel, exc))
            continue
        markers = tuple(globals_.get("ignore_markers") or DEFAULT_MARKERS)
        lines, note = extract(rel, text, markers)
        prose_lines += len(lines)
        if note:
            notes.append(note)
        got, _ = lint_text(rel, text, rules, globals_)
        reason = exempt_for(rel, exempts)
        if reason is not None:
            # EXEMPT, AND COUNTED. The file is still read and still linted; only
            # the VERDICT is suppressed, so the number below is real rather than an absence. A quiet exemption is how a gate stops meaning what its name says.
            if got:
                exempted.setdefault(reason, []).append((rel, len(got)))
            continue
        findings.extend(got)

    if prose_lines == 0:
        log.error(
            "VACUOUS: %d file(s) scanned and ZERO prose lines extracted. The extractor is "
            "throwing everything away, which is indistinguishable from a clean tree by exit "
            "code alone." % len(files)
        )
        return 1

    previous = load_baseline(root)

    if write_baseline:
        added = write_baseline_guarded(root, findings, previous, accept_new)
        if added is not None:
            log.error(
                "REFUSED to write the baseline: the drain ADDED %d finding(s). Comparing "
                "SIZES would have missed this. Fix the value instead of baselining it, or "
                "pass --accept-new if it is genuinely being frozen on purpose:" % len(added)
            )
            for fid in added[:20]:
                print("  + %s" % fid, file=sys.stderr)
            return 1
        log.success(
            "baseline written: %d finding(s) frozen. %s"
            % (len({f.fid for f in findings}), _shape(globals_, rules, len(files), prose_lines))
        )
        return 0

    if previous is None:
        new = findings
        fixed = []
    else:
        seen = {f.fid for f in findings}
        new = [f for f in findings if f.fid not in previous]
        fixed = [fid for fid in previous if fid not in seen]

    if as_json:
        print(
            json.dumps(
                {
                    "files": len(files),
                    "prose_lines": prose_lines,
                    "findings": len(findings),
                    "new": [
                        {"id": f.fid, "path": f.path, "line": f.lineno, "rule": f.rule} for f in new
                    ],
                    "fixed": fixed,
                    "unchecked": notes,
                },
                indent=2,
            )
        )

    rc = 0
    errors = [f for f in new if f.severity == "error"]
    warnings = [f for f in new if f.severity == "warning"]

    # PRINTED EVERY RUN, GREEN OR RED. The landmark gate this copies prints its one vendored exemption's two offending pages on every run for the same reason: debt that is suppressed silently is debt nobody ever drains.
    for reason, rows in sorted(exempted.items()):
        total = sum(count for _, count in rows)
        log.warn(
            "EXEMPT: %d finding(s) across %d file(s) were NOT counted -- %s"
            % (total, len(rows), reason)
        )
        for rel, count in sorted(rows)[:10]:
            print("  - %s (%d)" % (rel, count), file=sys.stderr)

    if notes:
        # UNKNOWN IS A FAILURE. A file that could not be read or lexed went UNCHECKED, and folding that into "fine" is how a gate reports a green
        # for a tree it never looked at.
        log.error("%d file(s) went UNCHECKED, which is not the same as clean:" % len(notes))
        for note in notes[:20]:
            print("  ? %s" % note, file=sys.stderr)
        rc = 1

    if warnings and not as_json:
        log.warn("%d new prose-style warning(s):" % len(warnings))
        for finding in warnings[:40]:
            print("  ~ %s" % finding.render(), file=sys.stderr)

    if errors:
        log.error("%d NEW prose-style violation(s). Do not add them to the baseline:" % len(errors))
        for finding in errors[:40]:
            print("  ✗ %s" % finding.render(), file=sys.stderr)
        _rule_help(rules, {f.rule for f in errors})
        rc = 1

    if fixed:
        log.error(
            "%d baselined finding(s) no longer fire. The baseline is SHRINK-ONLY, and an "
            "entry left in it after the fix hides the next regression. Drain it:" % len(fixed)
        )
        print(
            "    .ci/scripts/quality/check_prose_style.py check --write-baseline", file=sys.stderr
        )
        rc = 1

    if rc == 0:
        log.success(
            "prose style: no new findings (%d baselined). %s"
            % (len(previous or {}), _shape(globals_, rules, len(files), prose_lines))
        )
    return rc


def baseline_additions(old, new):
    """Ids `new` carries that `old` did not -- the DIFF half of the shrink-only guard.

    Named the way `.ci/scripts/quality/check_language_policy.py:442` names it, and
    extracted from the call site rather than left inline, because the composition gate
    at `.ci/scripts/test/gates/test-shrink-only-composition.sh:148` requires a writer to
    DEFINE the diff, CALL the verdict, and compute both -- a writer that reseeds without
    a named diff can drain thirty findings, absorb one brand new one, and print a smaller
    number while doing it.
    """
    return sorted(set(new) - set(old or {}))


def write_verdict(*, previous_exists: bool, additions, accept_new: bool):
    """The complete write decision. Returns the ADDED ids when refused, None when allowed.

    A first-ever baseline (`previous_exists` False) is always allowed to write: there is
    nothing yet to have shrunk relative to, so refusing it would make `--write-baseline`
    unusable on a fresh gate. Every later write refuses unless the addition side is empty
    or the caller typed `--accept-new`.
    """
    if additions and not accept_new and previous_exists:
        return additions
    return None


def write_baseline_guarded(root, findings, previous, accept_new):
    """`write_baseline`, with the added-side refusal the caller reports.

    Returns the ADDED ids when the write was refused, and None when it happened.
    """
    entries = {f.fid for f in findings}
    additions = baseline_additions(previous, entries)
    refused = write_verdict(
        previous_exists=previous is not None, additions=additions, accept_new=accept_new
    )
    if refused is not None:
        return refused
    write_baseline(root, findings, previous)
    return None


def _rule_help(rules, ids):
    by_id = {r.id: r for r in rules}
    for rule_id in sorted(ids):
        rule = by_id.get(rule_id)
        if rule is None:
            continue
        print("    %s %s -- %s" % (rule.id, rule.title, rule.description), file=sys.stderr)
        for example in rule.examples:
            if example.get("kind") == "good":
                print("      instead: %s" % example["text"], file=sys.stderr)
                break


# Directive-shaped comment bodies that must NEVER be joined with a neighbour, checked against the RAW line rather than a stripped body, to sidestep any assumption about whether a space follows the marker -- Go's own directive
# comments, `//go:build linux`, have none. An ALLOWLIST of known tool-directive
# shapes, deliberately, not a broad heuristic: after two structural bugs in `reflow_markdown` this same session (a multi-row table, an HTML-comment marker), under-reflowing here -- leaving a directive-adjacent line un-joined
# -- is the safe failure mode; over-reflowing -- silently absorbing a
# `noqa`/`eslint-disable`/`go:build` line into a joined paragraph, turning the
# tool it talks to off -- is not. The names are BACKTICKED, deliberately: bare, the first one reads to ruff as a malformed suppression directive on this very line (ruff warns "Invalid ... directive" on every lint run, quoting the marker back -- which is why this sentence cannot quote it either), and one well-meant edit adding a code after it would have suppressed a real finding
# here while looking like prose.
COMMENT_DIRECTIVE = re.compile(
    r"(?:^\s*#!|-\*-\s*coding|\bnoqa\b|\btype:\s|\bpragma\b|\bpylint:|\bmypy:|\bstyle-ok\b"
    r"|eslint|@ts-(?:ignore|expect-error|nocheck)|prettier-ignore|//go:(?:build|generate)"
    r"|\bnolint\b|SPDX-License-Identifier)",
    re.IGNORECASE,
)
# A body that reads as CODE rather than PROSE: an assignment, a brace, a statement/block keyword, or a trailing semicolon. This exists because the obvious "does the body start with a space" test alone would happily join COMMENTED-OUT CODE into one garbled line -- `# def foo():` followed by `# return 1` reads as "a space after the marker" exactly like real prose does, and joining
# them corrupts the reference the comment exists to keep. Matching commented-out code is the safe direction to err in: a missed reflow costs one narrow paragraph, a wrongly-joined one costs a broken reference nobody notices until they try to use it.
CODE_SHAPED_COMMENT = re.compile(
    r"[={};]|^\s*(?:def|class|import|from|return|if|elif|else|for|while|try|except|"
    r"finally|with|const|let|var|function|type|interface|enum|switch|case|package|"
    r"func|struct|@\w)\b"
)
# Whole-line comment markers, by suffix. Only a line that IS a comment for its ENTIRE length (after its own leading whitespace) is ever eligible -- a
# trailing comment on a code line (`x = 1  # note`) is left alone and ends
# the current paragraph, exactly like a real code line would.
COMMENT_LINE_BY_SUFFIX = {
    ".py": "#",
    ".ts": "//",
    ".tsx": "//",
    ".js": "//",
    ".cjs": "//",
    ".mjs": "//",
    ".go": "//",
}


# A LEXER DECIDES WHAT A COMMENT IS, never `^\s*#`. Measured 2026-09-17: the regex version of this map rewrote 52 of 1051 `.py` files in this repository into a DIFFERENT `ast.dump`, because a docstring quoting an example `# ...` line reads to a per-line regex exactly like the real comment paragraph underneath it, and the two were joined into one line -- moving the closing quotes
# and silently rewriting the string's own content. The equivalent line-prefix survey of the `.ts`/`.js`/`.go` corpus reported zero damage, but it shared the blind spot of the thing it was checking, so it was evidence of nothing. `python_comment_lines` and `cstyle_comment_lines` already resolve
# strings correctly for the LINT path; these two are the same resolution kept
# addressable by physical line, which is what reconstruction needs and what `_emit` throws away.
def _python_reflow_lines(text):
    """1-based line number -> (indent, body) for each WHOLE-LINE `#` comment.

    `tokenize` is the interpreter's own lexer, so a `#` inside a string or a
    docstring is never a `COMMENT` token and can never reach this map. A
    comment whose physical line carries code before it is TRAILING and is
    dropped here, which leaves it unjoinable and makes it end a paragraph.
    """
    found = {}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            continue
        row, col = token.start
        indent = token.line[:col]
        if indent.strip():
            continue
        found[row] = (indent, token.string[1:])
    return found


def _cstyle_reflow_lines(text):
    """The same map for a `//` language, from `cstyle_comment_lines`' scanner.

    The state machine is that function's, with two additions reconstruction
    needs: the offset each physical line starts at, so a comment's column
    separates whole-line from trailing, and a `/* */` span consumed WITHOUT
    recording anything. A block comment is left entirely alone -- rewrapping
    one risks its own asterisk alignment, and there is no reader benefit that
    pays for that.
    """
    found = {}
    i = 0
    lineno = 1
    line_start = 0
    length = len(text)
    quote = None
    while i < length:
        char = text[i]
        if char == "\n":
            lineno += 1
            i += 1
            line_start = i
            continue
        if quote is not None:
            if char == "\\":
                if i + 1 < length and text[i + 1] == "\n":
                    lineno += 1
                    line_start = i + 2
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
            indent = text[line_start:i]
            if not indent.strip():
                found[lineno] = (indent, text[i + 2 : end])
            i = end
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            end = length if end == -1 else end
            lineno += text.count("\n", i, end)
            i = min(end + 2, length)
            line_start = text.rfind("\n", 0, i) + 1
            continue
        i += 1
    return found


def reflow_comments(text, suffix, width):
    """Join hard-wrapped WHOLE-LINE comment paragraphs, then wrap at `width`.

    Same join-then-wrap contract as `reflow_markdown`, over a narrower and
    more conservative corpus. A paragraph ends on: a blank line, a code line
    (including a line with a TRAILING comment -- `x = 1  # note` is left
    alone, not partially joined), an indentation change (a different nesting
    level, not a continuation), a marker this suffix does not use, a
    `COMMENT_DIRECTIVE` line, a `CODE_SHAPED_COMMENT` line, or a body whose
    first character is not whitespace (`#!shebang`, `##header`, `///
    <reference>`, an ASCII divider `#---`) -- none of which is prose a reader
    would want rewrapped with its neighbours, and each is emitted unchanged.

    A FILE THE LEXER CANNOT READ IS RETURNED UNCHANGED, which is where this
    contract differs from `python_comment_lines`. That function lets the error
    reach a caller that reports the file as UNCHECKED, because a lint result
    nobody produced must not read as clean. A rewriter has no equivalent
    honest partial answer: guessing at the shape of a file Python itself
    rejects is how a broken file becomes a differently broken file.
    """
    marker = COMMENT_LINE_BY_SUFFIX.get(suffix)
    if marker is None:
        return text
    try:
        eligible = _python_reflow_lines(text) if suffix == ".py" else _cstyle_reflow_lines(text)
    except (tokenize.TokenError, SyntaxError, ValueError):
        return text

    out = []
    buffer = []
    buf_indent = None

    def flush():
        if not buffer:
            return
        joined = " ".join(piece.strip() for piece in buffer)
        joined = re.sub(r"\s{2,}", " ", joined).strip()
        prefix = buf_indent + marker + " "
        avail = max(width - len(prefix), 20)
        if len(prefix) + len(joined) <= width:
            out.append(prefix + joined)
        else:
            out.extend(
                prefix + piece
                for piece in textwrap.wrap(
                    joined, width=avail, break_long_words=False, break_on_hyphens=False
                )
            )
        buffer.clear()

    # `split("\n")`, not `splitlines()`. The lexers above number lines the way `StringIO.readline` does, on `\n` alone, while `splitlines()` also breaks on `\f`, `\v` and U+2028 (named, not written -- a literal one here would break this very file). A single one of those anywhere in a file would slide every later line number by one against the map, and rejoining
    # with `\n` would rewrite the separator itself. Splitting on `\n` also makes
    # the round trip exact, so the trailing newline needs no special case.
    for offset, raw in enumerate(text.split("\n")):
        entry = eligible.get(offset + 1)
        if entry is None:
            flush()
            buf_indent = None
            out.append(raw)
            continue
        indent, body = entry
        if (
            not body.strip()
            or COMMENT_DIRECTIVE.search(raw)
            or CODE_SHAPED_COMMENT.search(body)
            or (body and not body[0].isspace())
        ):
            flush()
            buf_indent = None
            out.append(raw)
            continue
        if buf_indent is not None and indent != buf_indent:
            flush()
        buf_indent = indent
        buffer.append(body)
    flush()
    return "\n".join(out)


def run_reflow(root, globals_, targets, *, write=False, show_diff=False):
    """The `reflow` subcommand. DRY RUN BY DEFAULT; `--write` is the opt-in."""
    width = globals_.get("max_line_length", 384)
    try:
        files = targets or discover(root, globals_)
    except RuleError as exc:
        log.error(str(exc))
        return 1
    files = [
        f for f in files if f.endswith(".md") or pathlib.Path(f).suffix in COMMENT_LINE_BY_SUFFIX
    ]
    if not files:
        log.error("VACUOUS: zero reflowable file(s) matched, so reflow checked nothing.")
        return 1
    changed = []
    for rel in files:
        full = pathlib.Path(root) / rel
        before = read_text(full)
        if rel.endswith(".md"):
            after = reflow_markdown(before, width)
        else:
            after = reflow_comments(before, pathlib.Path(rel).suffix, width)
        if after == before:
            continue
        joined = len(before.splitlines()) - len(after.splitlines())
        changed.append((rel, joined))
        if show_diff:
            print("--- %s" % rel)
            print("+++ %s (reflowed)" % rel)
            print("    %d line(s) would collapse" % joined)
        if write:
            full.write_text(after, encoding="utf-8")
    verb = "rewrote" if write else "would rewrite"
    total = sum(n for _, n in changed)
    log.info(
        "reflow: %s %d of %d file(s) at width %d, collapsing %d line(s) in total "
        "(largest single file %d)"
        % (verb, len(changed), len(files), width, total, max((n for _, n in changed), default=0))
    )
    if not write:
        log.info("DRY RUN: nothing was written. `--write` is the opt-in.")
    for rel, joined in changed[:40]:
        print("  %s  %+d line(s)" % (rel, -joined))
    if len(changed) > 40:
        print(
            "  ... and %d more file(s), %d further line(s)"
            % (len(changed) - 40, total - sum(n for _, n in changed[:40]))
        )
    return 0


def run_sync(globals_, rules):
    """The `sync` subcommand: render the rules as the markdown a document embeds.

    ONE SOURCE, RENDERED. The table below is what a `gen-docs` region would carry;
    printing it here means the rules file is the only place a rule's text is
    typed, and a document quoting a rule can be regenerated instead of edited.
    """
    out = [
        "Scans: %s, one row per rule." % RULES_FILE,
        "",
        "| Rule | Title | Severity | Scopes | Detection |",
        "|---|---|---|---|---|",
    ]
    for rule in rules:
        detection = (
            "advisory"
            if rule.advisory
            else (
                "measured" if rule.detection == "measured" else "%d pattern(s)" % len(rule.patterns)
            )
        )
        out.append(
            "| %s | %s | %s | %s | %s |"
            % (rule.id, rule.title, rule.severity, ", ".join(rule.scopes), detection)
        )
    out.append("")
    out.append(
        "%d rule(s), limit %d characters. `advisory` means the rule is documented and NOT "
        "mechanically detected; see %s for why, per rule."
        % (len(rules), globals_.get("max_line_length", 0), RULES_FILE)
    )
    print("\n".join(out))
    return 0


# --------------------------------------------------------------------------- main ---------------------------------------------------------------------------


USAGE = """usage: check_prose_style.py [check|reflow|sync] [options] [files...]

  check                 lint the tree (default). Fails on a NEW finding and on a
                        baselined finding that was fixed but not drained.
    --write-baseline    freeze today's findings. Refuses a drain that ADDED any.
    --accept-new        allow --write-baseline to add. A typed decision.
    --scope <name>      force the scope instead of deriving it from the suffix
    --json              machine-readable summary on stdout

  reflow                join hard-wrapped prose paragraphs. DRY RUN by default.
    --check             the default: report, write nothing
    --diff              also print which files would change
    --write             actually rewrite them

  sync                  render the rules as a markdown table

  --selftest            run the controls and exit
"""


def main(argv=None):
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="surrogateescape")

    root = paths.repo_root()

    subcommand = "check"
    if args and not args[0].startswith("-"):
        subcommand = args.pop(0)

    try:
        globals_, rules = load_rules_file(root)
    except RuleError as exc:
        log.error(str(exc))
        return 1

    off = globals_.get("env_off", "PROSE_STYLE")
    if os.environ.get(off, "").lower() in ("off", "0", "false"):
        log.warn(
            "%s=%s: the prose-style gate did NOT run. That is an UNCHECKED tree, not a clean "
            "one." % (off, os.environ.get(off))
        )
        return 0

    flags = {a for a in args if a.startswith("-")}
    targets = [a for a in args if not a.startswith("-")]
    scope = None
    if "--scope" in args:
        index = args.index("--scope")
        if index + 1 < len(args):
            scope = args[index + 1]
            targets = [t for t in targets if t != scope]

    if subcommand == "sync":
        return run_sync(globals_, rules)
    if subcommand == "reflow":
        return run_reflow(
            root, globals_, targets, write="--write" in flags, show_diff="--diff" in flags
        )
    if subcommand != "check":
        log.error("unknown subcommand %r" % subcommand)
        print(USAGE, file=sys.stderr)
        return 1
    if scope is not None and scope not in (globals_.get("scopes") or ()):
        log.error("unknown scope %r; the rules file declares %s" % (scope, globals_.get("scopes")))
        return 1
    return run_check(
        root,
        globals_,
        rules,
        targets,
        write_baseline="--write-baseline" in flags,
        accept_new="--accept-new" in flags,
        as_json="--json" in flags,
    )


# --------------------------------------------------------------------------- selftest ---------------------------------------------------------------------------

_MINI = json.dumps(
    {
        "globals": {
            "max_line_length": 40,
            "scopes": ["markdown", "comment"],
            "ignore_markers": ["<!-- style-ok -->"],
            "include": ["*.md"],
            "exclude_dirs": [],
        },
        "rules": [
            {
                "id": "X1",
                "title": "no you",
                "description": "d",
                "severity": "error",
                "scopes": ["all"],
                "patterns": ["(?i)\\byou\\b"],
                "examples": [],
            },
            {
                "id": "X2",
                "title": "imperative",
                "description": "d",
                "severity": "warning",
                "scopes": ["markdown"],
                "patterns": ["^Send\\b"],
                "examples": [],
            },
            {
                "id": "X3",
                "title": "length",
                "description": "d",
                "severity": "error",
                "scopes": ["markdown"],
                "patterns": [],
                "detection": "measured",
                "examples": [],
            },
        ],
    }
)


def _ids(findings):
    return sorted(f.rule for f in findings)


def selftest():
    """Plant each violation and prove it reds; remove it and prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL, and the negative half is the one that
    matters here: a prose linter with only positive controls will happily flag
    the entire tree, and every one of those flags looks like the gate working.
    """
    ctl = Controls("prose-style", floor=40, verbose=True)
    globals_, rules = load_rules(_MINI)

    # ---- loading --------------------------------------------------------
    ctl.check("loader: three rules", [r.id for r in rules], ["X1", "X2", "X3"])
    ctl.check("loader: severity survives", rules[0].severity, "error")
    ctl.raises("loader: a rule set with no rules is refused", RuleError, load_rules, "{}")
    ctl.raises("loader: a non-object document is refused", RuleError, load_rules, "[]")
    ctl.raises("loader: unparseable JSON is refused", RuleError, load_rules, "{")
    ctl.raises(
        "loader: a bad regex is refused AT LOAD, naming the rule",
        RuleError,
        load_rules,
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
    )
    ctl.raises(
        "loader: an unknown scope is refused (a rule scoped nowhere never fires)",
        RuleError,
        load_rules,
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
    )
    ctl.raises(
        "loader: a duplicate id is refused",
        RuleError,
        load_rules,
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
    )

    # ---- the matcher, both directions -----------------------------------
    def md(text):
        return _ids(lint_message(text, rules, globals_, "markdown"))

    ctl.check("PLANT: the word fires", md("Did you run it?"), ["X1"])
    ctl.check("MIRROR: the rewritten sentence does not", md("Have the tests been run?"), [])
    ctl.check("PLANT: the imperative fires under markdown", md("Send the file."), ["X2"])
    ctl.check(
        "MIRROR: the same line under `comment` does NOT (scopes are real)",
        _ids(lint_message("Send the file.", rules, globals_, "comment")),
        [],
    )
    ctl.check("PLANT: a long line fires", md("x" * 60), ["X3"])
    ctl.check("MIRROR: a short line does not", md("x" * 10), [])

    # ---- extraction: the part that decides whether a green means anything
    ctl.check("fence: a violation inside ``` is not prose", md("```\nDid you run it?\n```"), [])
    ctl.check(
        "fence: the same line outside the fence IS", md("Did you run it?\n```\nx\n```"), ["X1"]
    )
    ctl.check("fence: a ~~~ fence closes on ~~~", md("~~~\nyou\n~~~\nclean"), [])
    ctl.check("fence: a longer closing fence closes a shorter one", md("```\nyou\n`````"), [])
    ctl.check("inline code: a backticked pronoun is exempt", md("The flag is `you` here."), [])
    ctl.check(
        "inline code: the same word outside the span is not", md("The flag is you here."), ["X1"]
    )
    ctl.check(
        "inline code: a double-backtick span closes correctly", md("Use ``a `you` b`` here."), []
    )
    ctl.check("link: the TARGET is stripped", md("See [the doc](docs/you-and-me.md)."), [])
    ctl.check("link: the TEXT is kept and still linted", md("See [what you did](x.md)."), ["X1"])
    ctl.check("url: a bare url is stripped", md("Read https://x.test/you/here for more."), [])
    ctl.check("blockquote: a quotation is somebody else's words", md("> Did you run it?"), [])
    ctl.check(
        "bad example: a `bad:` line carries its violation on purpose",
        md("bad: Did you run it?"),
        [],
    )
    ctl.check("bad example: a list-item `- bad:` too", md("- bad: Did you run it?"), [])
    ctl.check("bad example: `good:` is NOT exempt", md("good: Did you run it?"), ["X1"])
    ctl.check(
        "marker: an explicit style-ok exempts the line", md("Did you run it? <!-- style-ok -->"), []
    )
    ctl.check(
        "marker: the line above it is not exempted",
        md("Did you run it?\nok <!-- style-ok -->"),
        ["X1"],
    )
    ctl.check("heading: a heading is not linted", md("## Did you run it?"), [])
    ctl.check("indent: a 4-space indented block is code", md("    Did you run it?"), [])
    ctl.check("frontmatter: metadata is skipped", md("---\ntitle: did you\n---\nclean"), [])
    ctl.check("html comment: stripped", md("<!-- Did you run it? --> fine"), [])
    ctl.check("identifier: `your_var` does not match `your`", md("The value of you_id is set."), [])

    # ---- exceptions -----------------------------------------------------
    real_globals, real_rules = load_rules(
        json.dumps(
            {
                "globals": {"scopes": ["markdown"], "max_line_length": 384},
                "rules": [
                    {
                        "id": "R2",
                        "title": "no I",
                        "description": "d",
                        "severity": "error",
                        "scopes": ["all"],
                        "patterns": ["\\bI\\b", "(?i)\\bmy\\b"],
                        "exceptions": ["(?i)\\bmy (?:mistake|error)\\b", "\\bI/O\\b"],
                    }
                ],
            }
        )
    )

    def rd(text):
        return _ids(lint_message(text, real_rules, real_globals, "markdown"))

    ctl.check("PLANT: a bare pronoun fires", rd("I think this is wrong."), ["R2"])
    ctl.check(
        "MIRROR: the ownership exception suppresses it", rd("My mistake; a fix is on the way."), []
    )
    ctl.check("MIRROR: I/O is not the pronoun", rd("The I/O layer buffers writes."), [])
    ctl.check("PLANT: `my branch` is not the exception", rd("My branch is ready."), ["R2"])

    # ---- python and c-style extraction ----------------------------------
    py = "x = 1  # Did you run it?\ny = 'you are a string'\n"
    ctl.check(
        "python: a comment is prose",
        _ids(list(lint_text("a.py", py, rules, globals_)[0])),
        ["X1"],
    )
    ctl.check(
        "python: a STRING is not (tokenize, not a regex over #)",
        [f.lineno for f in lint_text("a.py", py, rules, globals_)[0]],
        [1],
    )
    ctl.check(
        "python: a docstring IS prose",
        _ids(lint_text("a.py", '"""Did you run it?"""\n', rules, globals_)[0]),
        ["X1"],
    )
    ctl.check(
        "python: a file that will not tokenize is reported UNCHECKED, not clean",
        lint_text("a.py", "def f(:\n", rules, globals_)[1] is not None,
        True,
    )
    ts = 'const u = "https://x/you";\n// Did you run it?\n'
    ctl.check(
        "ts: the // comment is prose", _ids(lint_text("a.ts", ts, rules, globals_)[0]), ["X1"]
    )
    ctl.check(
        "ts: the `//` inside a string literal is NOT a comment",
        [f.lineno for f in lint_text("a.ts", ts, rules, globals_)[0]],
        [2],
    )
    ctl.check(
        "ts: a /* */ block is prose",
        _ids(lint_text("a.ts", "/* Did you run it? */\n", rules, globals_)[0]),
        ["X1"],
    )
    ctl.check(
        "ts: a template literal holding // is not a comment",
        _ids(lint_text("a.ts", "const a = `x // you y`;\n", rules, globals_)[0]),
        [],
    )

    # ---- stable ids -----------------------------------------------------
    first = Finding("a.md", 3, "X1", "you", "Did you run it?", "error")
    moved = Finding("a.md", 900, "X1", "you", "Did you run it?", "error")
    rewritten = Finding("a.md", 3, "X1", "you", "Did you run them?", "error")
    ctl.check("id: a MOVE keeps the id", first.fid, moved.fid)
    ctl.check("id: a REWRITE changes it, so a human looks again", first.fid != rewritten.fid, True)
    ctl.check(
        "id: the same text in another file is a different finding",
        first.fid != Finding("b.md", 3, "X1", "you", "Did you run it?", "error").fid,
        True,
    )

    # ---- the baseline's composition guard -------------------------------
    old = {first.fid: {"id": first.fid}}
    ctl.check(
        "baseline: a drain that only REMOVES is allowed",
        write_baseline_guarded.__doc__ is not None and _added(old, []),
        [],
    )
    ctl.check(
        "baseline: a drain that ADDS one is caught, though the total SHRANK",
        _added(old, [rewritten]),
        [rewritten.fid],
    )

    # ---- discovery is git's answer, not the walking machine's -----------
    with tempfile.TemporaryDirectory() as ctldir:
        ctlroot = pathlib.Path(ctldir)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=ctlroot, env=env, check=True)
        (ctlroot / "kept.md").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=ctlroot, env=env, check=True)
        (ctlroot / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (ctlroot / "ignored").mkdir()
        (ctlroot / "ignored" / "dirty.md").write_text("dirty\n", encoding="utf-8")
        (ctlroot / "untracked.md").write_text("dirty\n", encoding="utf-8")
        discovered = discover(ctlroot, globals_)
        ctl.check("discovery: a tracked file is discovered (MIRROR)", "kept.md" in discovered, True)
        ctl.check(
            "discovery: a gitignored file is NOT discovered",
            "ignored/dirty.md" in discovered,
            False,
        )
        ctl.check(
            "discovery: an untracked, unignored file is NOT discovered",
            "untracked.md" in discovered,
            False,
        )
        ctl.check(
            "discovery: exclude_dirs prunes a bare name at depth",
            under_excluded_dir("a/node_modules/b.md", {"node_modules"}),
            True,
        )
        ctl.check(
            "discovery: a FILE whose stem matches an exclude_dirs entry survives (MIRROR)",
            under_excluded_dir("node_modules", {"node_modules"}),
            False,
        )
    with tempfile.TemporaryDirectory() as nongit:
        (pathlib.Path(nongit) / "a.md").write_text("dirty\n", encoding="utf-8")
        ctl.raises(
            "discovery: outside a checkout refuses rather than reporting nothing",
            RuleError,
            discover,
            nongit,
            globals_,
        )

    # ---- reflow ---------------------------------------------------------
    wrapped = "one two three\nfour five six\n\nnext para\n"
    once = reflow_markdown(wrapped, 40)
    ctl.check(
        "reflow: a hard-wrapped paragraph joins", once, "one two three four five six\n\nnext para\n"
    )
    ctl.check("reflow: IDEMPOTENT", reflow_markdown(once, 40), once)
    ctl.check(
        "reflow: a fenced block is untouched",
        reflow_markdown("```\na\nb\n```\n", 40),
        "```\na\nb\n```\n",
    )
    ctl.check(
        "reflow: a list is untouched (indentation is structure)",
        reflow_markdown("- a\n- b\n", 40),
        "- a\n- b\n",
    )
    ctl.check(
        "reflow: a table is untouched",
        reflow_markdown("| a | b |\n|---|---|\n", 40),
        "| a | b |\n|---|---|\n",
    )
    # A 2-row table (header + separator, no data) cannot expose the bug this pins: TABLE_RULE alone stops the join between header and separator, so the gap only shows once a THIRD consecutive `|`-row (a real data row) has nothing after it to stop against. Found live 2026-09-17: `reflow --write` merged a 5-data-row table into two garbled lines the first time it ran tree-wide,
    # because ordinary table rows were never in REFLOW_STOP -- only the `---` alignment row was.
    _table_3row = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
    ctl.check(
        "reflow: a table with 3+ DATA rows is untouched, row for row",
        reflow_markdown(_table_3row, 40),
        _table_3row,
    )
    # Found the same session, same shape: a gen-docs region marker with no blank line to a neighbouring paragraph shifted the region boundary, which check:ci-doc-region-parity reported as "closing marker with no open region" the first time reflow --write ran tree-wide.
    _gendocs = "lead-in sentence.\n<!-- >>> gen-docs: x -->\nbody\n<!-- <<< gen-docs -->\ntrailing sentence.\n"
    ctl.check(
        "reflow: a gen-docs region marker does not absorb its neighbours",
        reflow_markdown(_gendocs, 40),
        _gendocs,
    )
    # A TRAILING marker, not a line that OPENS with one -- the shape `DEFAULT_MARKERS`/`is_marked` actually use. Caught live: the first fix (anchored at column 0) missed this and still let the marked line merge
    # with its neighbours, moving which physical line the exemption covers.
    _styleok = "first line.\nDid you check it? <!-- style-ok -->\nthird line.\n"
    ctl.check(
        "reflow: a TRAILING style-ok marker does not absorb its neighbours",
        reflow_markdown(_styleok, 40),
        _styleok,
    )
    # Found live 2026-09-17, THIRD instance of the same class this session: 89 real plan/handoff-document files had "Status: done" merged into the very next line "Owner: <id>" when this reflow ran tree-wide, because neither line matched any existing REFLOW_STOP pattern.
    _docheader = "Status: done\nOwner: e580532b\nUpdated: 2026-09-06\n"
    ctl.check(
        "reflow: doc-header key:value lines never merge into each other",
        reflow_markdown(_docheader, 40),
        _docheader,
    )
    # Found by SWEEPING THE CLASS, not by a fourth corrupted file: the operator's stop-hook judge asked whether more REFLOW_STOP gaps existed after the third one, and this repo really does use <details>/<summary> collapsible sections in a few documents.
    _htmlblock = "lead-in.\n<details><summary>x</summary>\nbody\n</details>\ntrailing.\n"
    ctl.check(
        "reflow: a <details>/<summary> block does not absorb its neighbours",
        reflow_markdown(_htmlblock, 40),
        _htmlblock,
    )
    ctl.check(
        "reflow: a heading is untouched and does not absorb the next line",
        reflow_markdown("# H\ntext\n", 40),
        "# H\ntext\n",
    )
    long_para = reflow_markdown(("word " * 40).strip() + "\n", 40)
    ctl.check(
        "reflow: a joined paragraph over the width re-wraps UNDER the width",
        max(len(x) for x in long_para.splitlines()) <= 40,
        True,
    )
    ctl.check(
        "reflow: and the re-wrap is still idempotent (the join reproduces it)",
        reflow_markdown(long_para, 40),
        long_para,
    )
    ctl.check(
        "reflow: no word was lost to the wrap",
        long_para.split(),
        ["word"] * 40,
    )

    # ---- reflow of comments: a LEXER decides what a comment is ----------- The regex version of this joined the docstring line below into the real comment paragraph under it, which moved the closing `"""` and rewrote the string. Measured over `git ls-files '*.py'` on 2026-09-17: 52 of 1051 files came back with a DIFFERENT `ast.dump`. The docstring has to END on the `#` line for
    # the bug to show -- a `"""` on a line of its own already stops the paragraph, which is why the obvious three-line fixture passes against the broken code and proves nothing.
    _py_docstring = (
        'def f():\n    """Doc.\n\n    # an example inside the docstring"""\n'
        "    # a real comment that is\n    # hard wrapped over two lines\n    return 1\n"
    )
    ctl.check(
        "reflow: a `#` line inside a docstring is not a comment",
        reflow_comments(_py_docstring, ".py", 384),
        'def f():\n    """Doc.\n\n    # an example inside the docstring"""\n'
        "    # a real comment that is hard wrapped over two lines\n    return 1\n",
    )
    # The same shape one language over: a template literal ending on a line
    # that OPENS with `//`. No semicolon, deliberately -- `;` would trip
    # CODE_SHAPED_COMMENT and the broken code would pass by accident.
    _ts_template = (
        "const t = `\n// looks like a comment`\n"
        "// a real comment that is\n// hard wrapped over two lines\n"
    )
    ctl.check(
        "reflow: a `//` line inside a template literal is not a comment",
        reflow_comments(_ts_template, ".ts", 384),
        "const t = `\n// looks like a comment`\n"
        "// a real comment that is hard wrapped over two lines\n",
    )
    # A block comment CONTAINING a `//` line, not a plain one: a plain block is already left alone by a line regex, so it would pass against the broken code and pin nothing. Reflowing WITHIN a `/* */` span is out of scope -- the span is a stop, never a paragraph.
    _block = "/*\n// inside a block comment */\n// a real one that is\n// hard wrapped\n"
    ctl.check(
        "reflow: a `//` line inside a `/* */` block is not a comment line",
        reflow_comments(_block, ".ts", 384),
        "/*\n// inside a block comment */\n// a real one that is hard wrapped\n",
    )
    # The trailing-comment rule, pinned where it can actually fail: a `#` that
    # follows the docstring's own closing quotes on one physical line. `x = 1  #
    # note` alone is refused by a line regex too, so it pins nothing here.
    _trailing = (
        'def f():\n    """D\n    # example"""  # note\n'
        "    # a real comment that is\n    # hard wrapped over two lines\n    return 1\n"
    )
    ctl.check(
        "reflow: a TRAILING comment on a docstring's closing line is never joined",
        reflow_comments(_trailing, ".py", 384),
        'def f():\n    """D\n    # example"""  # note\n'
        "    # a real comment that is hard wrapped over two lines\n    return 1\n",
    )
    # A rewriter has no honest partial answer for a file the lexer rejects, so it returns the bytes it was given. The broken code joined these two.
    ctl.check(
        "reflow: a file `tokenize` cannot read is returned UNCHANGED",
        reflow_comments("def f(:\n# a comment that is\n# hard wrapped\n", ".py", 384),
        "def f(:\n# a comment that is\n# hard wrapped\n",
    )
    ctl.check(
        "reflow: comments IDEMPOTENT",
        reflow_comments(reflow_comments(_py_docstring, ".py", 384), ".py", 384),
        reflow_comments(_py_docstring, ".py", 384),
    )

    # ---- the real rules file loads and its examples are consistent -------
    try:
        real_root = paths.repo_root()
        rg, rr = load_rules_file(real_root)
        ctl.check("the real rules file loads", len(rr) >= 18, True)
        ctl.check("the real rules file declares a limit", rg.get("max_line_length"), 384)
        bad_expect = [
            (r.id, e.get("text"))
            for r in rr
            for e in r.examples
            if e.get("expect") not in ("flag", "clean", "undetected")
        ]
        ctl.check("every example declares a known expectation", bad_expect, [])
        ctl.truthy("at least one rule is advisory and SAYS so", [r for r in rr if r.advisory])
    except (RuleError, RuntimeError) as exc:
        ctl.fail("the real rules file loads", exc)

    return 0 if ctl.report() else 1


def _added(previous, findings):
    return sorted({f.fid for f in findings} - set(previous))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
