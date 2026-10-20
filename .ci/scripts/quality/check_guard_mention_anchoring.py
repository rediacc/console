#!/usr/bin/env python3
"""A guard must refuse a COMMAND, never a SENTENCE about one.

WHY THIS EXISTS. The defect class is "matches a MENTION rather than a TARGET": a guard greps the command line for a phrase, finds it inside prose, and refuses a worklist note or a doc line as if it were the rule being broken. It recurred FOUR times on 2026-08-28 alone -- block-bash-write-to-running-script.sh, block-roundlog-truncate.sh, block-git-empty-commit.sh (whose own header
records being routed through command-scan.sh "because matching the raw command meant matching PROSE", a fix that covered the QUOTED case only), and warn-stale-index.sh, which was written by the session fixing the other three and reintroduced the class within the hour. Every instance was repaired by hand and nothing stopped the next one.

HOW THE PROBE IS BUILT, and why the obvious version does not work. The first attempt collected a guard's vocabulary and wrote a sentence out of it. That gate passed while the pre-fix unanchored matcher was planted back into block-git-empty-commit.sh, because the words were sorted alphabetically and the pattern needs `git commit` BEFORE `--allow-empty`. A probe that cannot trigger
the guard proves nothing about it.

So the pattern itself is turned into a CONCRETE INSTANCE -- the shortest literal string that matches it -- and that instance is embedded in an ordinary sentence. If the guard fires on the sentence, it is matching a mention.

ANCHOR, DO NOT NARROW. The fix for a finding here is to require command position `(^|[;&|(])`, never to delete the pattern: a guard that stops catching the real command is a worse outcome than the false positive it was cured of.

STRUCTURE JUDGES ARE PROBED DIFFERENTLY, NOT SKIPPED. A pre-edit guard whose rule is about the RESULTING DOCUMENT (block_plan_without_depends.py refuses a live plan that loses its `Depends-On:` header) correctly refuses the plain probe, because that probe writes the sentence as the WHOLE content and the header is gone. The plain probe cannot tell that guard from a mention matcher, so a guard declares it with a module constant, `ANCHORING = "structure: <reason, 20+ chars>"`, and is then probed with a STRUCTURE-NEUTRAL edit instead: the sentence APPENDED to a document the guard accepts, at a path the guard has just refused the bare sentence at (which proves the path reaches its judgement). A structure judge stays silent on that; a mention matcher still sees the sentence and still fires, so declaring structure buys a mention matcher nothing. The reason is printed on every run, and a declaration with a missing or short reason, on a chain other than pre-edit, or with no accepted in-scope document to append to, is red.

RETARGETED 2026-09-24 (PLAN-retire-bash-oracles A2) from `.claude/oracles/`'s frozen bash originals to the LIVE Python guard modules at `.claude/rediacc_hooks/guards/`. The residue this file used to state out loud -- "a pattern edited in the PORT and not in the oracle is invisible here, because the oracle cannot change" -- is closed by this change rather than carried forward: there is no longer a second, frozen copy of a guard's pattern for an edit to miss. Patterns are read via `ast`, not text search, so a constant built across several lines, by string-literal concatenation, or from `hookio.rx()`'s `{S}`/`{B}` placeholders resolves exactly as the interpreter would resolve it.

---- gate ----
step: Guard mention anchoring
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
why: A guard that refuses PROSE is a guard nobody can write a doc line about.
     The class recurred FOUR times on 2026-08-28 and every instance was fixed
     by hand, including one reintroduced within the hour by the session doing
     the fixing -- which is the i18n lesson exactly. This probes each guard
     with a sentence built from its OWN pattern, so it cannot go stale as
     guards are added.
---- end gate ----
"""

from __future__ import annotations

import ast
import json
import re

# The `re` module's own parser, so a pattern is read exactly as the guard's `re.compile` reads it. `re._parser`/`re._constants` are the 3.11+ homes of the deprecated `sre_parse`/`sre_constants`.
import re._constants as sre
import re._parser as sre_parse
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import _cipath
from rediacc_ci import core_lease

# ALIASED: `proc` is the name this file's own code reaches for when it holds a completed process, and it did until these call sites were routed. Keeping the
# runner under a distinct name means a future local `proc =` cannot shadow it
# into a NameError on the timeout path -- the path least likely to be exercised.
from rediacc_ci import proc as ci_proc
from rediacc_ci.core import allowlist

REPO_ROOT = Path(__file__).resolve().parents[3]
# THE LIVE GUARD PACKAGE, not the retired oracle tree (PLAN-retire-bash-oracles A2). Patterns and the guard both come from here now, so there is exactly one copy of each guard's matcher to keep anchored.
GUARDS = REPO_ROOT / ".claude" / "rediacc_hooks" / "guards"
DISPATCH = REPO_ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"


def guard_argv(guard):
    """How to RUN the guard this path names.

    A path under the live guard package names an importable module, dispatched by stem through ONE entry point per chain. Anything else is run as a file, which is what the throwaway fixtures `controls()` writes have to be: they are bash by construction, deliberately, so that rewording a real guard cannot silently void the control.
    """
    try:
        guard.relative_to(GUARDS)
    except ValueError:
        # The structure-declaration fixtures are Python, because the declaration is a Python module constant; they run as a plain file, never through the dispatcher.
        if guard.suffix == ".py":
            return [sys.executable, str(guard)]
        return ["bash", str(guard)]
    return [sys.executable, str(DISPATCH), guard.stem]


# EVERY CHAIN, not just pre-bash. Scoping this to one directory was the same hole check-hook-integrity.sh has now had twice (pre-edit/pre-ask in its 2026-08-27 repair, post-bash in e60e30331) -- and it was in the file written to stop exactly this class. Found by e580532b: 35 of 42 guards were probed and 7 were not.
#
# The chains do not share a payload shape, which is why this is a builder and not one dict. A wrong key produces a probe that CANNOT FIRE, and a probe that cannot fire proves nothing -- so every prose probe below is paired with a positive one, and a guard whose positive probe stays silent is reported UNPROBED rather than counted clean.
CHAINS = {
    "pre-bash": "command",
    "pre-edit": "edit",
    "pre-ask": "ask",
}

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Guards whose matching is deliberately quote-blind, with the reason taken from the guard itself rather than invented here.
#
# BLOCKER: block_adhoc_sanctioned.py delegates matching to lib/sanctioned.py and holds no inline pattern to turn into an instance. Its own comment states the trade-off knowingly -- "the residue is that `echo 'gh run watch 123'` is still refused. That is the price of seeing inside quotes, it is paid knowingly" -- and it mitigates the costly half by stripping heredoc bodies, which is
# where a quoted recipe actually lives.
#
# BLOCKER: block_edit_of_running_script.py's decision is keyed on FILE IDENTITY (is the edited path one of the shell scripts a live process is currently interpreting) and the real process table, not on any phrase inside the edited content. `HOOK_CHAIN` matches a script PATH, not a command, and `META` is a character-escape set for building a `sed`-style substitution, not a matcher at
# all -- found live by this A2 retarget, whose ast-based reader surfaces both as string constants where the old text search never reached them. Neither is the "refuses a mention instead of a target" class this file exists to catch, because there is no prose to confuse with a target: a file is either the one running or it is not.
ALLOW_UNPROBED = {"block_adhoc_sanctioned.py", "block_edit_of_running_script.py"}

# Guards whose TARGET is prose, so a probe sentence they refuse is the rule working, not a mention mistaken for a command. Each one is still probed on every run, the refused sentence is PRINTED, and an entry whose guard stops refusing every probe is red as stale: an exemption nobody can see, or one that outlived its reason, is how a gate stops meaning what its name says.
PROSE_TARGETS = {
    "block_settled_questions.py": (
        "BLOCKER: a pre-ask guard reads a QUESTION, which is prose by construction, and push "
        "timing is a topic it refuses in any wording (operator ruling ASKED:2026-10-08T10:25Z, "
        '"It should not be even askable"), naming the TURBO_PUSH_REASON kind too. Every '
        "probe it refuses (`push now ?`, `which turbo_push_reason ?`, measured 12 of 133 on "
        "2026-10-09) is that topic, so the refusal is the target, not a mention."
    ),
}

# Joins the refused instances of a PROSE_TARGETS guard in `assess`'s detail. A control character, because an instance is rendered from a regex and may contain any printable one.
PROSE_SEP = "\x1f"

# THE THIRD WAY A PATTERN PASSES. Every module-level pattern of a scanned guard is exactly one of: anchored at command position (`command_anchored`); WORDED, so every worded instance is rendered into the probe sentences and each one stays silent; or declared here as a FRAGMENT, a pattern with no literal word for a sentence to mention, because it parses a piece of a command the guard has
# already located by other means. Keyed by (guard file, constant name). Printed on every run, and red as STALE when the constant is gone, is anchored, has grown a word (and so is probed), or sits in a guard that is exempt anyway: a declaration that excuses nothing is how an exemption outlives its reason. A new unworded pattern that is not listed here is red, never silently skipped.
FRAGMENTS: dict[tuple[str, str], str] = {
    ("block_bash_write_to_running_script.py", "NOT_ARROW"): (
        "BLOCKER: a one-character lookbehind stand-in `(^|[^->])` that only stops a quoted `->` arrow scoring as a redirect; "
        "it is concatenated into REDIR_TARGET and matches nothing a sentence could name."
    ),
    ("block_bash_write_to_running_script.py", "REDIR_TARGET"): (
        "BLOCKER: harvests the file a `>`/`>>` redirect opens (`> x.sh`); its words are the user's file name, never the guard's, "
        "and the harvest only matters for a path a live process is interpreting."
    ),
    ("block_bash_write_to_running_script.py", "ANY_TAIL"): (
        "BLOCKER: extracts the `name.ext` tail from REDIR_TARGET and ASSIGN_TARGET matches; a file-name shape with no literal "
        "word, applied to text the anchored harvest already selected."
    ),
    ("block_blanket_git_add.py", "END"): (
        "BLOCKER: the end-of-clause tail (`$`, a separator or a redirect) concatenated after the anchored GIT_ADD prefix; "
        "only the composed BLANKET_* patterns are matchers, and they are anchored."
    ),
    ("block_review_file_shell_write.py", "_PERCENT_SPEC"): (
        "BLOCKER: a printf conversion matched inside a `%` template string that ast found in a Python program, so the "
        "guard can substitute the argument; it rewrites a parsed string value and never reads the command text."
    ),
    ("block_review_file_shell_write.py", "_FORMAT_FIELD"): (
        "BLOCKER: a `str.format` replacement field matched inside a template string that ast found in a Python program, "
        "so the guard can substitute the argument; it rewrites a parsed string value and never reads the command text."
    ),
    ("block_review_file_shell_write.py", "_LITERAL"): (
        "BLOCKER: extracts the body of each quoted or backticked literal in interpreter program text: on a line that "
        "already names the review directory beside a shell call (SHELL_CALL), and as a path resolved on disk for a write "
        "through a link (_code_writes_through_disk); quote shapes with no word, applied to program text, never to the command."
    ),
    ("block_user_only_command_shell_write.py", "_LITERAL"): (
        "BLOCKER: extracts the body of each quoted or backticked literal in interpreter program text, each resolved on disk "
        "as a path for a write through a link into a command or skill directory (_code_writes_through_disk); quote shapes "
        "with no word, applied to program text, never to the command."
    ),
    ("block_worktree_add.py", "QUOTE_LIKE"): (
        "BLOCKER: extracts the body of perl q{}/qq{}/qw and ruby %q()/%w() literals from interpreter program text for "
        "the static scan, beside LITERAL; bracket shapes with no word, applied to program text, never to the command."
    ),
    ("block_worktree_add.py", "PLACEHOLDER"): (
        "BLOCKER: a printf, format, f-string or ${}/#{} placeholder inside a string literal already found in interpreter "
        "program text, replaced by `.sub()` with the unknown marker that `_filled` completes; it rewrites a literal, "
        "never reads the command, and never decides a refusal."
    ),
    ("block_worktree_add.py", "TEXT_JOIN_BEFORE"): (
        "BLOCKER: a concatenation operator (`+`, perl `.`, `<<`) searched in the 16 characters before a literal that "
        "LITERAL or QUOTE_LIKE found in program text; it only says the literal is one piece of a built string."
    ),
    ("block_worktree_add.py", "TEXT_INTERPOLATION"): (
        "BLOCKER: a `${}`, `#{}`, `$name` or `@name` interpolation inside a literal found in program text, replaced by "
        "`.sub()` with the unknown marker that `_filled` completes; it rewrites a literal and never reads the command."
    ),
    ("block_blanket_git_add.py", "BARE_DDASH"): (
        "BLOCKER: an optional ` -- ` concatenated between GIT_ADD's anchored prefix and END; it is a piece of the composed "
        "BLANKET_* patterns, never searched on its own."
    ),
    ("block_commit_meta.py", "SHELL_VAR"): (
        "BLOCKER: a `$name`/`${name}` expansion parser used by `.sub()` to resolve variables in a commit message file name; "
        "it rewrites text, it never decides a refusal."
    ),
    ("block_pathspecless_git_commit.py", "DDASH_PATHSPEC"): (
        "BLOCKER: an ALLOW exemption (`-- <path>` after an anchored GIT_COMMIT), consulted only after the anchored commit "
        "matcher fired; a mention of it can only let a command through, never refuse one."
    ),
    ("block_prose_style_commit.py", "PARAM"): (
        "BLOCKER: a `$name`/`${name}` expansion parser used by `.sub()` to substitute assigned values into the commit "
        "text before linting; it rewrites text and decides nothing itself."
    ),
    ("block_suppressions_shell_write.py", "_SED_SUB"): (
        "BLOCKER: parses a sed `s<d>pat<d>rep<d>` expression from argv of an in-place sed already aimed at a suppression "
        "file; the delimiter is any punctuation, so there is no literal word to mention."
    ),
    ("block_suppressions_shell_write.py", "_SED_TEXT"): (
        "BLOCKER: parses sed `a`/`i`/`c` text commands from the same in-place sed argv as _SED_SUB; a one-letter command "
        "plus an address, applied after the file target was resolved."
    ),
    ("block_user_only_command_shell_write.py", "_SED_SUB"): (
        "BLOCKER: parses a sed `s<d>pat<d>rep<d>` expression from argv of an in-place sed already aimed at a command "
        "or skill file; the delimiter is any punctuation, so there is no literal word to mention."
    ),
    ("block_user_only_command_shell_write.py", "_SED_TEXT"): (
        "BLOCKER: parses sed `a`/`i`/`c` text commands from the same in-place sed argv as _SED_SUB; a one-letter command "
        "plus an address, applied after the file target was resolved."
    ),
    ("block_unlinked_commit_author.py", "IDENT_EMAIL"): (
        "BLOCKER: fullmatches `Name <email>` in a git identity value read back from git config, to extract the address; "
        "it parses a config value, not the command text."
    ),
    ("block_unproven_bulk_transform.py", "PATHSPEC_TAIL"): (
        "BLOCKER: collects the pathspec operands after ` -- ` from a commit already matched by the anchored commit "
        "pattern, to count files; it measures a command, it does not detect one."
    ),
    ("block_unproven_bulk_transform.py", "MANUAL_PATH"): (
        "BLOCKER: recognises a file name inside the commit message's own proof paragraph; its subject is prose by "
        "design and a match can only ACCEPT a proof, never refuse a command."
    ),
    ("block_unproven_bulk_transform.py", "PARAM"): (
        "BLOCKER: a `$name`/`${name}` expansion parser used by `.sub()` to resolve variables in pathspecs and message "
        "files before counting; it rewrites text and decides nothing itself."
    ),
    ("block_unproven_bulk_transform.py", "_HEX_WORD"): (
        "BLOCKER: finds 7 to 40 character hex words in a follow-up proof message to compare with a commit sha; a class "
        "run with no literal word, whose match can only accept a proof."
    ),
    ("block_unscoped_formatter_run.py", "ASSIGN"): (
        "BLOCKER: parses `NAME=value` shell assignments so a later `$NAME` operand can be resolved; it records values "
        "and never refuses, and the refusal itself is TOOL_WORD's, which is probed."
    ),
    ("block_worktree_add.py", "LITERAL"): (
        "BLOCKER: extracts quoted string literals from interpreter program text (`python -c`, `node -e`) for a static "
        "scan; quote characters around any content, with no literal word."
    ),
    ("block_roundlog_truncate.py", "_LIVE_PERL_RUBY"): (
        "BLOCKER: searched in the text of a perl or ruby inline program (`perl -e`, `ruby -e`) that the guard's command walk "
        "already extracted, for a pipe-open quote pair or a `<...>` glob that can turn a literal into file names; "
        "punctuation shapes with no literal word, and a sentence cannot contain a program."
    ),
    ("block_roundlog_truncate.py", "_LEXEME"): (
        "BLOCKER: tokenizes the same extracted inline program into string literals and brackets to see which call encloses a "
        "delimiter literal; quote and bracket characters with no literal word, applied only to program text the command "
        "walk extracted."
    ),
}

# The structure declaration (see the module docstring): `ANCHORING = "structure: <reason>"` as a module-level string constant, read by `ast` like every other constant here.
ANCHORING_NAME = "ANCHORING"
STRUCTURE_PREFIX = "structure:"
MIN_REASON = 20
# How many sibling documents are tried as the accepted baseline before the structure probe gives up (red, never silent).
MAX_BASELINES = 25

# A pattern must look like a command matcher before it is worth instantiating. Tuned for PYTHON `re` syntax rather than POSIX bracket expressions, since A2 retargeted the source from bash originals to the live guard modules: an anchor prefix, a character class built around the command separators, a word boundary, a non-capturing group, or a quantifier.
INTERESTING = re.compile(r"\(\^\||\[;&|\\b|\(\?:|[+*]")

# THE COMMAND-POSITION SEPARATORS. A pattern is anchored at command position only when every alternative it matches begins at the start of the subject or right after one of these: `;`, `&`, `|`, `(`, a backtick, a newline, `{`, `!`, or the two-character `$(`. Whitespace is deliberately NOT one of them: `(^|[ \t])rm` matches `rm` after any space, which is inside every sentence.
CMD_SEPARATORS = frozenset(map(ord, ";&|(`\n{!"))

_REPEATS = (sre.MAX_REPEAT, sre.MIN_REPEAT, sre.POSSESSIVE_REPEAT)

# The most instances one pattern is expanded into. Every alternative is meant to be probed (see `instances`), so a pattern that would exceed this is COUNTED and printed, never silently cut.
MAX_INSTANCES = 64


def _parse(pattern: str) -> list | None:
    """The pattern's top-level node list, or None when `re` cannot compile it (a message string that merely looked regex-shaped)."""
    try:
        return list(sre_parse.parse(pattern))
    except (re.error, OverflowError, RecursionError):
        return None


def _at_command_position(items: list) -> bool:
    """Does this node sequence begin at command position, on EVERY alternative it can take?

    THE OLD CHECK WAS A SUBSTRING. `ANCHORED` searched the pattern text for `(^|` or a separator class, so `(alpha|beta|(^|[^A-Za-z0-9_])gamma)` read as anchored: the `(^|` was there, inside ONE alternative of three, and the anchor it introduced was a word boundary rather than a separator. Walking the parse tree answers the real question: an alternation is anchored only when
    every branch is, a group only when its body is, an optional prefix never is, and a character class only when every member is a separator.
    """
    i = 0
    # A lookahead is zero-width: it constrains what follows without moving the position, so the anchor question passes through it.
    while i < len(items) and items[i][0] is sre.ASSERT and items[i][1][0] == 1:
        i += 1
    if i >= len(items):
        return False
    op, av = items[i]
    if op is sre.AT:
        return av in (sre.AT_BEGINNING, sre.AT_BEGINNING_STRING)
    if op is sre.SUBPATTERN:
        return _at_command_position(list(av[3]))
    if op is sre.ATOMIC_GROUP:
        return _at_command_position(list(av))
    if op is sre.BRANCH:
        return all(_at_command_position(list(alt)) for alt in av[1])
    if op is sre.IN:
        return bool(av) and all(o is sre.LITERAL and c in CMD_SEPARATORS for o, c in av)
    if op is sre.LITERAL:
        if av in CMD_SEPARATORS:
            return True
        return av == ord("$") and i + 1 < len(items) and items[i + 1] == (sre.LITERAL, ord("("))
    if op in _REPEATS:
        return av[0] >= 1 and _at_command_position(list(av[2]))
    return False


def command_anchored(pattern: str) -> bool:
    """True when every alternative of `pattern` is constrained to command position. An unparsable pattern is not anchored."""
    tree = _parse(pattern)
    return tree is not None and _at_command_position(tree)


def _category_admits(cat: object, ch: str) -> bool:
    word = ch.isalnum() or ch == "_"
    if cat is sre.CATEGORY_SPACE:
        return ch.isspace()
    if cat is sre.CATEGORY_NOT_SPACE:
        return not ch.isspace()
    if cat is sre.CATEGORY_DIGIT:
        return ch.isdigit()
    if cat is sre.CATEGORY_NOT_DIGIT:
        return not ch.isdigit()
    if cat is sre.CATEGORY_WORD:
        return word
    if cat is sre.CATEGORY_NOT_WORD:
        return not word
    return False


def _class_admits(av: list, ch: str) -> bool:
    negate = bool(av) and av[0][0] is sre.NEGATE
    hit = any(
        (op is sre.LITERAL and arg == ord(ch))
        or (op is sre.RANGE and arg[0] <= ord(ch) <= arg[1])
        or (op is sre.CATEGORY and _category_admits(arg, ch))
        for op, arg in (av[1:] if negate else av)
    )
    return hit != negate


def _class_char(av: list) -> str:
    """One character the class admits, chosen so the instance reads like a command line.

    WHITESPACE FIRST, when the class admits it and not a letter. The old regex-surgery instantiator turned every bracket expression into `x`, so `hookio.rx()`'s `[{S}]+`, the spelling most guards use for "some whitespace", rendered `git worktree add` as `xgitx-xx worktreexaddx`. That string matches nothing, so the probe could not fire and its silence was counted clean: 150 of 171
    instances on the 2026-10-09 tree did not match their own pattern.
    """
    if _class_admits(av, " ") and not _class_admits(av, "x"):
        return " "
    for ch in "xa1-_./ ":
        if _class_admits(av, ch):
            return ch
    for op, arg in av:
        if op is sre.LITERAL:
            return chr(arg)
        if op is sre.RANGE:
            return chr(arg[0])
    return "x"


# PROVENANCE OF A RENDERED CHARACTER. A word character the renderer CHOSE (for a class, `.` or a negated literal) is not a word the guard wrote, so it is carried through rendering as a private-use code point at a fixed offset and decoded only when the instance leaves `expand`. While marked it is a non-word character, so it splits a literal run instead of
# extending one: `\$[A-Za-z_]+` renders `$x`, and its `x` cannot make the instance look like a word. Plane 15 is private use, so no guard's own literal collides with it.
_MARK_BASE = 0xF0000
_MARK_END = _MARK_BASE + 0xFFFF
# A WORDED instance keeps a run of at least this many LITERAL alphanumerics: `go`, `scp`, `pdf` are words a sentence can mention, while `$x`, `x=x`, `-n` and `''` are fragments of a parser with nothing to mention. The floor this replaced was a LENGTH (`len(inst) < 4`), which dropped `scp` and `go` with the fragments and so left the one real mention matcher it hid unprobed.
MIN_WORD_RUN = 2
_WORD_RUN = re.compile(r"[^\W_]{%d,}" % MIN_WORD_RUN)


def _mark(ch: str) -> str:
    """`ch` as a renderer-chosen character: marked when it is a word character, unchanged otherwise (a space or punctuation is never part of a word either way)."""
    if (ch.isalnum() or ch == "_") and ord(ch) <= 0xFFFF:
        return chr(_MARK_BASE + ord(ch))
    return ch


def _unmark(text: str) -> str:
    return "".join(
        chr(ord(c) - _MARK_BASE) if _MARK_BASE <= ord(c) <= _MARK_END else c for c in text
    )


def worded(marked: str) -> bool:
    """Does this MARKED rendering keep a run of MIN_WORD_RUN literal alphanumerics?"""
    return bool(_WORD_RUN.search(marked))


def _render_seq(items: list, groups: dict) -> list[str]:
    """Every rendering of a node sequence that varies ONE element from its default, the all-default rendering first.

    One element at a time, rather than the full product, keeps this linear in the number of alternatives while still putting every alternative of every alternation into at least one instance.
    """
    parts = [_render(op, av, groups) for op, av in items]
    defaults = [p[0] for p in parts]
    out = ["".join(defaults)]
    for i, variants in enumerate(parts):
        head, tail = "".join(defaults[:i]), "".join(defaults[i + 1 :])
        out.extend(head + v + tail for v in variants[1:])
    return out


def _render(op: object, av: Any, groups: dict) -> list[str]:
    if op is sre.LITERAL:
        return [chr(av)]
    if op is sre.NOT_LITERAL:
        return [_mark("y" if av == ord("x") else "x")]
    if op is sre.ANY:
        return [_mark("x")]
    if op is sre.IN:
        return [_mark(_class_char(av))]
    if op is sre.BRANCH:
        out: list[str] = []
        for alt in av[1]:
            out.extend(_render_seq(list(alt), groups))
        return out
    if op is sre.SUBPATTERN:
        rendered = _render_seq(list(av[3]), groups)
        if av[0] is not None:
            groups[av[0]] = rendered[0]
        return rendered
    if op is sre.ATOMIC_GROUP:
        return _render_seq(list(av), groups)
    if op in _REPEATS:
        low = min(av[0], 50)
        inner = _render_seq(list(av[2]), groups)
        if low == 0:
            # An optional run of a class that admits a space renders as one space, so `git\b[^;&|]*commit` reads `git commit` rather than `gitcommit`.
            item = list(av[2])
            if len(item) == 1 and item[0][0] is sre.IN and _class_admits(item[0][1], " "):
                return [" ", *inner[1:]]
            # The empty default keeps an optional prefix out of the way; one copy of each variant still reaches every alternative inside it.
            return ["", *inner]
        return [v + inner[0] * (low - 1) for v in inner]
    if op is sre.GROUPREF:
        return [groups.get(av, "")]
    # AT, ASSERT, ASSERT_NOT, GROUPREF_EXISTS: zero-width, no text.
    return [""]


def _prose_safe(text: str) -> str:
    """A PROBE MUST STAY PROSE.

    An instance carrying a real command separator creates a genuine command POSITION inside the sentence, and the guard is then right to fire, which reads as a finding and is not one. Measured: an instance ending in a backgrounding operator was reported against block-shell-background-waiter.sh, whose natural-sentence probe is silent.
    """
    text = re.sub(r"[&;|`]", " ", text)
    text = text.replace("$(", " ").replace("(", " ").replace(")", " ")
    return re.sub(r"\s+", " ", text).strip()


def expand_marked(pattern: str) -> tuple[list[tuple[str, bool]], int]:
    """([(instance, worded)], how many MAX_INSTANCES dropped) for one pattern; ([], 0) when `re` cannot parse it.

    Deduplicated on the decoded text. When one text is reached both as a word and as a fragment, it is a word: the guard did write those letters on some path.
    """
    tree = _parse(pattern)
    if tree is None:
        return [], 0
    order: list[str] = []
    flags: dict[str, bool] = {}
    for raw in _render_seq(tree, {}):
        marked = _prose_safe(raw)
        text = _unmark(marked)
        if text not in flags:
            order.append(text)
            flags[text] = False
        flags[text] = flags[text] or worded(marked)
    out = [(text, flags[text]) for text in order]
    return out[:MAX_INSTANCES], max(0, len(out) - MAX_INSTANCES)


def expand(pattern: str) -> tuple[list[str], int]:
    """(instances, how many MAX_INSTANCES dropped) for one pattern, worded or not; ([], 0) when `re` cannot parse it."""
    found, dropped = expand_marked(pattern)
    return [text for text, _ in found], dropped


def instances(pattern: str) -> list[str]:
    """A concrete literal for EVERY alternative of the pattern, the first-branch rendering first.

    EVERY ALTERNATIVE, NOT THE FIRST. The old instantiator resolved each alternation to its first branch, "which is what a real command does", so an alternation whose first branch was anchored and whose later branches were not was only ever probed through the anchored one, and the unanchored branch refused prose unseen. Built from the `re` parse tree rather than by rewriting
    the pattern text, so nesting, escapes and lookarounds resolve exactly as the guard's own `re.compile` resolves them.
    """
    return expand(pattern)[0]


def instantiate(pattern: str) -> str:
    """The first-branch literal: the shortest command the pattern names, or "" when it cannot be rendered."""
    found = instances(pattern)
    return found[0] if found else ""


def _shellscan_placeholders() -> tuple[str, str]:
    """`(SPACE, BLANK)`, read from `shellscan.py` rather than retyped here.

    `hookio.rx()` substitutes `{S}`/`{B}` for these two character-class bodies at import time, so instantiating a pattern that uses them needs the same substitution. Reading them from the one file that defines them means a change there cannot silently desync from a second, hand-copied pair here; a fallback covers the read failing outright, since a stale pair is still closer to
    right than crashing this gate over a file it does not otherwise depend on.
    """
    path = REPO_ROOT / ".claude" / "rediacc_hooks" / "shellscan.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except OSError:
        return r" \t\n\v\f\r", r" \t\v\f\r"
    found: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("SPACE", "BLANK")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.targets[0].id] = node.value.value
    return found.get("SPACE", r" \t\n\v\f\r"), found.get("BLANK", r" \t\v\f\r")


SPACE, BLANK = _shellscan_placeholders()


def _const_eval(node: ast.AST, table: dict[str, str]) -> str | None:
    """Best-effort constant folding for one guard's regex-shaped assignments.

    A guard's matcher is not always a single string literal: `hookio.rx(...)` and `re.compile(...)` wrap one, several guards build theirs by concatenating a literal with `hookio.SPACE`/`hookio.BLANK` (the pre-`rx()` idiom, six guards still use it for a fragment `rx()`'s `{S}`/`{B}` placeholders do not reach), and a `NAME = expr` two constants up can be referenced by name in a
    later one, exactly as the interpreter would resolve it at import time. `table` carries every module-level constant already folded earlier in the same file, in source order, so a helper like `_S = hookio.SPACE` is available by the time a later line concatenates it in.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_eval(node.left, table)
        right = _const_eval(node.right, table)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name):
        return table.get(node.id)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "hookio"
    ):
        if node.attr == "SPACE":
            return SPACE
        if node.attr == "BLANK":
            return BLANK
        return None
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        is_rx = (isinstance(func, ast.Attribute) and func.attr == "rx") or (
            isinstance(func, ast.Name) and func.id == "rx"
        )
        is_compile = isinstance(func, ast.Attribute) and func.attr == "compile"
        if not (is_rx or is_compile):
            return None
        inner = _const_eval(node.args[0], table)
        if inner is None:
            return None
        return inner.replace("{S}", SPACE).replace("{B}", BLANK) if is_rx else inner
    return None


def named_patterns(path: Path) -> list[tuple[str, str]]:
    """(constant name, pattern) for every command-matcher-shaped string this guard module resolves to a constant, in source order.

    NAMED, because a FRAGMENTS declaration is keyed by the constant that holds the pattern, and a value alone cannot be declared. Not deduplicated: two constants holding one value are two names a declaration may use. `patterns_of` is the value view.

    Read from the AST, not the source TEXT: PLAN-retire-bash-oracles A2 retargeted this file from grepping quoted strings out of a frozen bash original to reading the LIVE Python guard's own regex constants, and those are not always one quoted literal on one line -- `hookio.rx(...)`, `re.compile(...)`, string-literal concatenation split across lines, and a constant built from
    another constant defined earlier in the same file all have to resolve exactly as the interpreter resolves them, or a real edit to a pattern goes on being invisible here for a different reason than the one this file used to name. The INTERESTING filter is what keeps ordinary message strings and non-matcher constants (`CHAIN`, `TWIN`, a file path) out.
    """
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))
    table: dict[str, str] = {}
    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        if node.targets[0].id == ANCHORING_NAME:
            continue
        value = _const_eval(node.value, table)
        if value is not None:
            table[node.targets[0].id] = value
    # PARSEABLE, TOO. A string `re` cannot compile is not a matcher the guard can be running (block_suppressions.py's refusal FOOTER looks regex-shaped and is not), so it is neither probed nor asked to carry an anchor.
    return [(n, p) for n, p in table.items() if INTERESTING.search(p) and _parse(p) is not None]


def patterns_of(path: Path) -> list[str]:
    """The distinct pattern values of `named_patterns`, first occurrence first."""
    uniq: list[str] = []
    for _, pat in named_patterns(path):
        if pat not in uniq:
            uniq.append(pat)
    return uniq


def payload_for(kind: str, text: str, file_path: str) -> str:
    """The tool_input shape each chain actually reads.

    Derived from the guards themselves: pre-edit reads file_path plus one of content / new_string / new_source / edits; pre-ask reads question and questions. Every field is filled rather than guessed at, because a guard that reads the one field left out would silently never fire.
    """
    if kind == "command":
        return json.dumps({"tool_input": {"command": text}})
    if kind == "edit":
        return json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": file_path,
                    "content": text,
                    "new_string": text,
                    "new_source": text,
                    "edits": [{"old_string": "x", "new_string": text}],
                },
            }
        )
    return json.dumps({"tool_input": {"question": text, "questions": [{"question": text}]}})


def fires(guard: Path, command: str, kind: str = "command", file_path: str = "") -> bool:
    payload = payload_for(kind, command, file_path)
    # THROUGH THE SHARED RUNNER. A guard is a script, and a script can leave a grandchild holding the read end; `subprocess.run` then blocks in `communicate()` past its own timeout, which is how check:ci-pytest came to hang with zero bytes on both streams. `proc.run` kills the group, and it RETURNS on timeout rather than raising, so the old `except TimeoutExpired` is gone -- only a
    # missing binary still raises.
    try:
        result = ci_proc.run(
            guard_argv(guard),
            input_text=payload,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
    except OSError:
        return False
    if result.timed_out:
        # A guard that will not answer is not a guard that said "no".
        return False
    return result.returncode == 2


# THE BATCH CHILD. One process per guard loads the guard module once and answers every payload in turn, instead of one interpreter start (~0.15 s, mostly imports) per probe sentence: 1459 sentences made the gate ~60 s wall on 24 cores. Each payload still gets its own fresh `Event`, exactly as `dispatch.run_one` builds it.
# THE RESULT CHANNEL IS PRIVATE. The child saves the real stdout on a duplicated fd and points fd 1 at stderr before any guard runs, so a guard that prints (or a subprocess it starts) cannot corrupt the JSON, which is written to the saved fd only at the very end.
# WORST CASE, STATED: a guard whose every probe hangs costs the child PER_PROBE_TIMEOUT per probe (its alarm fires, the child still answers), then the caller re-judges each hung probe alone for up to PER_PROBE_TIMEOUT more, so about twice the old per-process cost, 2 * PER_PROBE_TIMEOUT per probe. A child stuck where SIGALRM cannot reach is cut only by the outer backstop, 30 + PER_PROBE_TIMEOUT * n seconds for n probes (about 12 hours at 1459 probes), after which every probe is re-judged alone; `_batch_run`'s outer timeout is pinned by a test.
# THE HANG BOUND. Each payload runs under its own SIGALRM of PER_PROBE_TIMEOUT seconds (the old per-probe timeout), so one hanging probe is detected after the same 30 s a per-process run allowed, reported as null, and re-judged alone by the caller. The outer ceiling is only the backstop for a child stuck where a signal cannot reach: startup plus the sum of every payload's bound.
PER_PROBE_TIMEOUT = 30
_BATCH_CHILD = """
import json, os, signal, sys
real = os.dup(1)
os.dup2(2, 1)
sys.path.insert(0, sys.argv[1])
import dispatch
req = json.load(sys.stdin)

def _alarm(signum, frame):
    raise TimeoutError("probe exceeded %d s" % req["timeout"])

signal.signal(signal.SIGALRM, _alarm)
out = []
for payload in req["payloads"]:
    signal.alarm(req["timeout"])
    try:
        out.append(dispatch.run_one(req["stem"], payload)[0])
    except SystemExit as exc:
        out.append(exc.code if isinstance(exc.code, int) else 1)
    except BaseException:
        out.append(None)
    finally:
        signal.alarm(0)
os.write(real, json.dumps(out).encode())
"""


def _batch_run(request: str, count: int) -> Any:
    """Run the batch child once. Split out so a test can stand in for it."""
    return ci_proc.run(
        [sys.executable, "-c", _BATCH_CHILD, str(DISPATCH.parent)],
        input_text=request,
        timeout=30 + PER_PROBE_TIMEOUT * count,
        cwd=str(REPO_ROOT),
    )


def _fallback_warning(guard: Path, reason: str) -> None:
    print(
        f"WARNING: guard-mention-anchoring batch probe of {guard.name} fell back to one process per probe ({reason}); the speedup is lost for this guard",
        file=sys.stderr,
    )


def fires_many(
    guard: Path, texts: list[str], kind: str = "command", file_path: str = ""
) -> list[bool]:
    """`fires` for each text, in order. A live guard runs in ONE child. Anything else, and any text the child did not answer cleanly, is judged by one process per text, so a hung or crashing probe is judged alone, as before. Every fallback of a live guard warns on stderr with the reason."""
    if not texts:
        return []
    try:
        guard.relative_to(GUARDS)
    except ValueError:
        return [fires(guard, t, kind, file_path) for t in texts]
    request = json.dumps(
        {
            "stem": guard.stem,
            "timeout": PER_PROBE_TIMEOUT,
            "payloads": [payload_for(kind, t, file_path) for t in texts],
        }
    )
    codes: object = None
    reason = ""
    try:
        result = _batch_run(request, len(texts))
        if result.timed_out:
            reason = "the child timed out"
        elif result.returncode != 0:
            reason = f"the child exited {result.returncode}"
        else:
            codes = json.loads(result.stdout)
    except OSError as exc:
        reason = f"the child could not start: {exc}"
    except ValueError:
        reason = "the child's answer was not JSON"
    if not reason and (not isinstance(codes, list) or len(codes) != len(texts)):
        reason = f"the child answered {len(codes) if isinstance(codes, list) else 'a non-list'} for {len(texts)} payloads"
        codes = None
    if codes is None:
        _fallback_warning(guard, reason)
        return [fires(guard, t, kind, file_path) for t in texts]
    unanswered = [i for i, c in enumerate(codes) if not isinstance(c, int)]
    if unanswered:
        _fallback_warning(guard, f"{len(unanswered)} probe(s) raised or hung in the child")
    return [
        fires(guard, texts[i], kind, file_path) if i in unanswered else codes[i] == 2
        for i in range(len(texts))
    ]


def chain_of(path: Path) -> str | None:
    """This guard module's own `CHAIN = "..."` constant, without importing it.

    Read the same way `patterns_of` reads a pattern constant, since the guards all live in ONE flat directory now (`.claude/rediacc_hooks/guards/`) rather than one subdirectory per chain: there is no longer a directory name to infer this from, only the module's own declaration.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CHAIN"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def file_path_for(guard: Path) -> str:
    """A path the guard will consider in scope, taken from its own source.

    pre-edit guards gate on file_path before they look at content, so a probe carrying an irrelevant path never reaches the matcher. Rather than guess, the first concrete-looking repo path in the guard is reused.
    """
    src = guard.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"[\"'\(|]((?:\.?[a-z][a-z0-9_.-]*/)+[a-zA-Z0-9_.*-]+)", src):
        cand = m.group(1)
        if cand.startswith((".git/", "http")) or "*" in cand:
            continue
        if "/" in cand and len(cand) > 6:
            return str(REPO_ROOT / cand)
    return str(REPO_ROOT / "agent" / "probe" / "STATE.md")


def sentence(instance: str) -> str:
    return f"echo the docs say never to run {instance} in this repo"


# An unworded instance shorter than this is a fragment (`$x`, `-n`, `''`) and is not probed; see `probes_of`.
SHORT_INSTANCE = 4

# EVERY WORDED INSTANCE IS ALSO PROBED WITH `argument_sentence`. A word is often a command name, and a command-name matcher often decides on the ARGUMENTS too: block_binary_deploy refused an `scp` clause only when its last field was a `host:` spec, so `sentence("scp")`, which ends in `repo`, could never reach that test (measured 2026-10-09: `echo avoid scp x h:/p` refused at rc 2 while the plain
# probe was silent). The second template was first gated on `len(instance) < SHORT_INSTANCE`, so an `rsync` or `sftp` matcher of the same shape was never asked it and stayed green (#32e75fa4, review a2d44aa4.3). Length says nothing about whether a word is a command name. An unworded instance (`> x.x`, `-- x`) keeps the plain template alone: followed by arguments it would be a real redirect, not a mention.


def argument_sentence(instance: str) -> str:
    """The second template: the instance followed by a source and a remote-looking destination, still inside an `echo`."""
    return f"echo the docs say never to run {instance} src/a.sh host:/dst/a.sh"


def sentences_of(instance: str, worded: bool = True) -> list[str]:
    """Every probe sentence for one instance: the plain template, and the argument-shaped one for a worded instance of any length."""
    out = [sentence(instance)]
    if worded:
        out.append(argument_sentence(instance))
    return out


def anchoring_of(path: Path) -> str | None:
    """The module's `ANCHORING` string constant, or None when it declares nothing. Read by `ast`, never imported."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == ANCHORING_NAME
        ):
            value = _const_eval(node.value, {})
            return value if value is not None else ""
    return None


def structure_reason(declared: str, kind: str) -> tuple[str | None, str]:
    """(reason, "") for a valid structure declaration, (None, why) for an invalid one."""
    if not declared.startswith(STRUCTURE_PREFIX):
        return None, "ANCHORING must read `structure: <reason>`, got %r" % declared[:60]
    reason = declared[len(STRUCTURE_PREFIX) :].strip()
    if len(reason) < MIN_REASON:
        return None, "ANCHORING's reason is %d char(s); at least %d are required" % (
            len(reason),
            MIN_REASON,
        )
    if kind != "edit":
        return None, "ANCHORING declares document structure, which only a pre-edit guard judges"
    return reason, ""


def baseline_candidates(fp: str) -> list[Path]:
    """Documents to append the sentence to: `fp` itself, then its same-suffix siblings, nearest name first."""
    target = Path(fp)
    out = [target] if target.is_file() else []
    try:
        siblings = [
            p
            for p in target.parent.iterdir()
            if p.is_file() and p.suffix == target.suffix and p != target
        ]
    except OSError:
        siblings = []

    def shared(p: Path) -> int:
        n = 0
        for a, b in zip(p.name, target.name, strict=False):
            if a != b:
                break
            n += 1
        return n

    out.extend(sorted(siblings, key=lambda p: (-shared(p), p.name)))
    return out[:MAX_BASELINES]


def structure_probe(guard: Path, kind: str, probes: Probes, fp: str) -> tuple[str, str]:
    """The structure-neutral probe. ("clean", <baseline>), ("prose", <refused sentence>) or ("nobase", <why>).

    A baseline qualifies only when the guard REFUSES the bare sentence at its path (so the path reaches the guard's judgement rather than an early out-of-scope allow) and ACCEPTS the document unmodified (so appending prose is the only change). Then the sentence is appended; a structure judge accepts the result and a mention matcher refuses it.
    """
    instances = probes.instances
    probe = sentence(instances[0])
    for doc in baseline_candidates(fp):
        try:
            body = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not fires(guard, probe, kind, str(doc)):
            continue
        if fires(guard, body, kind, str(doc)):
            continue
        for inst in instances:
            for text in probes.texts(inst):
                appended = body.rstrip("\n") + "\n\n" + text + "\n"
                if fires(guard, appended, kind, str(doc)):
                    return "prose", text
        return "clean", str(doc)
    return "nobase", (
        "no in-scope document the guard accepts unmodified was found beside %s, so the "
        "structure-neutral probe cannot run" % fp
    )


class Probes:
    """The probe set for one guard: every probed instance of every pattern, and how it was built."""

    def __init__(self) -> None:
        self.instances: list[str] = []
        # Instances the pattern they were rendered from actually matches. Printed every run: the old instantiator's figure was 21 of 171, and a probe its own pattern rejects is a probe that cannot fire.
        self.self_matching = 0
        self.dropped = 0
        # Unworded instances too short to probe: `$x`, `-n`, `''`. Counted and printed, never silently dropped; the pattern they came from is judged by `pattern_verdicts`.
        self.fragments = 0
        # The probed instances that carry a word, which earn the argument-shaped template too.
        self.worded: set[str] = set()

    def texts(self, inst: str) -> list[str]:
        return sentences_of(inst, inst in self.worded)

    def sentences(self) -> int:
        return sum(len(self.texts(inst)) for inst in self.instances)


def probes_of(pats: list[str]) -> Probes:
    """WORDED instances of any length, plus unworded ones at least SHORT_INSTANCE long.

    The unworded long ones (`> x.x`, `-- x`) were probed under the old length floor and still are, so dropping the floor cannot shrink coverage. The unworded short ones are fragments: a sentence carrying `>` or `''` is a probe of the shell, not of a mention.
    """
    out = Probes()
    for pat in pats:
        found, dropped = expand_marked(pat)
        out.dropped += dropped
        for inst, is_worded in found:
            # A text one pattern spells as a word is a word, whichever pattern reached it first (review 5aa562c3.2).
            if inst in out.instances:
                if is_worded:
                    out.worded.add(inst)
                continue
            if not is_worded and len(inst) < SHORT_INSTANCE:
                out.fragments += 1
                continue
            out.instances.append(inst)
            if is_worded:
                out.worded.add(inst)
            if re.search(pat, inst):
                out.self_matching += 1
    return out


def pattern_is_worded(pattern: str) -> bool:
    return any(w for _, w in expand_marked(pattern)[0])


def undeclared_fragments(
    guard: Path, named: list[tuple[str, str]], fragments: dict[tuple[str, str], str]
) -> list[str]:
    """The constants of `guard` that fit NONE of the three ways: not anchored, no worded instance, not in `fragments`."""
    return [
        name
        for name, pat in named
        if not command_anchored(pat)
        and not pattern_is_worded(pat)
        and (guard.name, name) not in fragments
    ]


def assess(
    guard: Path, kind: str, fp: str, fragments: dict[tuple[str, str], str] | None = None
) -> tuple[str, str]:
    """One guard's verdict: (outcome, detail).

    outcome is "clean", "static" (nothing to probe, every pattern anchored or a declared fragment), "unprobed" (detail = the undeclared fragment constants, comma-joined), "prose" (detail = the refused sentence), "invalid" (a malformed declaration), "nobase" or "allowed". Structure-judged verdicts carry the reason in the detail of "clean" as `<reason> | <baseline>`.
    """
    if fragments is None:
        fragments = FRAGMENTS
    declared = anchoring_of(guard)
    reason = None
    if declared is not None:
        reason, why = structure_reason(declared, kind)
        if reason is None:
            return "invalid", why
    named = named_patterns(guard)
    pats = patterns_of(guard)
    probes = probes_of(pats)
    instances = probes.instances
    # THE STRICT RULE, per pattern. Before 2026-10-09 this asked whether EVERY pattern was anchored only when no instance of four characters survived, so a short worded matcher (`scp`) beside long anchored siblings was never asked anything at all. And EVERY pattern, never any: an earlier `any` let one anchored constant vouch for an unanchored sibling it shared a module with. Structure judges, prose targets and ALLOW_UNPROBED guards stay exempt: the first two are probed whole by their own route, the third by reason.
    exempt = reason is not None or guard.name in PROSE_TARGETS or guard.name in ALLOW_UNPROBED
    missing = [] if exempt else undeclared_fragments(guard, named, fragments)
    if not instances:
        if guard.name in ALLOW_UNPROBED:
            return "allowed", ""
        if missing:
            return "unprobed", ", ".join(missing)
        return "static", reason or ""
    if reason is not None:
        outcome, detail = structure_probe(guard, kind, probes, fp)
        if outcome == "clean":
            return "clean", "%s | baseline %s" % (reason, detail)
        return outcome, detail
    # NO CAP. This read `instances[:40]`, a silent cut: block_settled_questions alone renders 137 instances once every alternative is expanded, and the 41st is as able to refuse prose as the first.
    # A PROSE TARGET IS PROBED IN FULL. Its exemption is per guard, so stopping at the first refused sentence would let every later one ride on it unseen, including a genuine mention-matcher added to the same module next month. Every refused sentence comes back, joined by PROSE_SEP, and each is printed.
    if guard.name in PROSE_TARGETS:
        every = [text for inst in instances for text in probes.texts(inst)]
        hits = [t for t, hit in zip(every, fires_many(guard, every, kind, fp), strict=True) if hit]
        return ("prose", PROSE_SEP.join(hits)) if hits else ("clean", "")
    # The batch answers every probe up front, so the loop below stops at the first refusal for reporting only and saves no probe work; acceptable because a clean guard (the common case) is probed in full anyway and a refusing one is a red run.
    every = [text for inst in instances for text in probes.texts(inst)]
    for text, hit in zip(every, fires_many(guard, every, kind, fp), strict=True):
        if hit:
            return "prose", text
    # PROSE FIRST, THEN THE UNDECLARED FRAGMENT: a guard refusing a sentence is the more urgent finding, and reporting "unprobed" alone would hide it.
    if missing:
        return "unprobed", ", ".join(missing)
    return "clean", ""


def fragment_findings(
    fragments: dict[tuple[str, str], str], guards_dir: Path = GUARDS
) -> list[str]:
    """Every FRAGMENTS entry that is malformed or stale, one message each. Empty when every declaration still excuses a real, unanchored, unworded pattern."""
    out: list[str] = []
    for (gname, const), why in sorted(fragments.items()):
        key = f"{gname}::{const}"
        if not why.startswith("BLOCKER:"):
            out.append(f"FRAGMENTS[{key}]: the reason must start with 'BLOCKER:'")
            continue
        rejection = allowlist.validate_reason(key, why[len("BLOCKER:") :], "FRAGMENTS")
        if rejection is not None:
            out.append(rejection.message)
            continue
        path = guards_dir / gname
        if not path.is_file():
            out.append(f"STALE FRAGMENTS[{key}]: the guard {gname} no longer exists")
            continue
        named = dict(named_patterns(path))
        if const not in named:
            out.append(
                f"STALE FRAGMENTS[{key}]: {gname} has no matcher-shaped constant {const} any more"
            )
            continue
        pat = named[const]
        if command_anchored(pat):
            out.append(
                f"STALE FRAGMENTS[{key}]: {const} is anchored at command position now, so it needs no declaration"
            )
        elif pattern_is_worded(pat):
            out.append(
                f"STALE FRAGMENTS[{key}]: {const} renders a worded instance now, so it is probed and needs no declaration"
            )
        elif gname in PROSE_TARGETS or gname in ALLOW_UNPROBED or anchoring_of(path) is not None:
            out.append(
                f"STALE FRAGMENTS[{key}]: {gname} is exempt from the per-pattern rule already, so the declaration excuses nothing"
            )
    return out


def controls() -> None:
    """A detector that cannot fire would pass the whole file silently."""
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "unanchored.sh"
        good = Path(td) / "anchored.sh"
        bad.write_text(
            "#!/usr/bin/env bash\n"
            "CMD=$(jq -r '.tool_input.command' 2>/dev/null)\n"
            "printf '%s' \"$CMD\" | grep -qE 'frobnicate[[:space:]]+widgets' && exit 2\n"
            "exit 0\n"
        )
        good.write_text(
            "#!/usr/bin/env bash\n"
            "CMD=$(jq -r '.tool_input.command' 2>/dev/null)\n"
            "printf '%s' \"$CMD\" | grep -qE '(^|[;&|(])[[:space:]]*frobnicate[[:space:]]+widgets' && exit 2\n"
            "exit 0\n"
        )
        probe = sentence("frobnicate widgets")
        if not fires(bad, probe):
            fail("an UNANCHORED fixture was not caught; the detector cannot fire")
        if fires(good, probe):
            fail("an ANCHORED fixture was reported as firing; the detector flags everything")
        if not fires(good, "frobnicate widgets --now"):
            fail(
                "the anchored fixture missed the REAL command; anchoring must narrow prose, not the target"
            )
        # CHAIN PLUMBING, proven with a REAL trigger against a REAL guard, one per non-pre-bash chain. This is what stands in for per-guard reachability, which was tried and discarded: most extracted fragments are one clause of a multi-part trigger (file_path AND tool_name AND content, all at once), so no single instantiated substring fires most guards alone. Proving the PAYLOAD
        # SHAPE once per chain is the part that is actually load-bearing.
        edit_guard = GUARDS / "block_roundlog_write.py"
        if edit_guard.exists():
            # `[ -e "$FILE" ]` gates this guard before anything else -- a nonexistent path is silently allowed by design (creating a log is not truncating one), so the fixture must actually exist on disk.
            # Under `td`, not a fresh `mkdtemp()`: that one was never removed, so every run of this gate left a directory in /tmp.
            rlog_dir = Path(td) / "rlog" / "reports"
            rlog_dir.mkdir(parents=True)
            rlog = rlog_dir / "pr-babysit-0827-1.md"
            rlog.write_text("## STATUS (round 1)\n")
            edit_payload = payload_for("edit", "irrelevant content", str(rlog))
            edit_result = ci_proc.run(
                guard_argv(edit_guard),
                input_text=edit_payload,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if edit_result.returncode != 2:
                fail(
                    "pre-edit payload plumbing: block_roundlog_write.py did not fire on a "
                    "REAL round-log write -- the edit payload shape cannot be trusted"
                )

        ask_payload = payload_for("ask", "should i commit this change", "")
        # DISPATCHED, not run as a bare bash file: this was pointed at the retired oracle directly (`["bash", str(ask_guard)]`, bypassing `guard_argv`) even before A2, a residue of the guard's chain-plumbing check never having been updated when the guard's LIVE half moved to Python at the P7 cutover. Fixed here as a small, in-scope finding rather than carried forward: the
        # plumbing check exists to prove the live payload shape, and the retired file cannot answer for that any more than the retired oracle tree can.
        ask_guard = GUARDS / "block_settled_questions.py"
        if ask_guard.exists():
            ask_result = ci_proc.run(
                guard_argv(ask_guard),
                input_text=ask_payload,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if ask_result.returncode != 2:
                fail(
                    "pre-ask payload plumbing: block_settled_questions.py did not fire on a "
                    "REAL settled question -- the ask payload shape cannot be trusted"
                )

        # The instantiator is load-bearing, so it gets its own control. Written in Python `re` syntax, not POSIX bracket expressions, since A2 retargeted the pattern source to the live guard modules.
        got = instantiate(r"git\s+commit[^|;&]*--allow-empty")
        if "git commit" not in got or "--allow-empty" not in got:
            fail(f"instantiate() lost the pattern's order or literals: {got!r}")
        # And the ANCHORED spelling must instantiate to the same literal, or the positive probe cannot reach any guard that was fixed for this class.
        anchored = instantiate(r"(^|[;&|(]|&&|\|\|)\s*git\s+commit[^|;&]*--allow-empty")
        if not anchored.startswith("git commit"):
            fail(f"instantiate() left anchor junk on the front: {anchored!r}")
        # The lookaround strip is load-bearing too, for the one guard that carries one (`block_prose_style_commit.GIT_COMMIT`'s trailing `(?=$|[\s;&|])`).
        # Without it the assertion's own syntax leaks into the instance as prose.
        lookaround = instantiate(r"(^|[;&|(])\s*git\b[^;&|]*commit(?=$|[\s;&|])")
        if "?=" in lookaround or "?!" in lookaround:
            fail(f"instantiate() leaked lookaround syntax into the instance: {lookaround!r}")

        alternation_controls(Path(td))
        argument_controls(Path(td))
        fragment_controls(Path(td))
        structure_controls(Path(td))


# The planted command-guard fixture. One Python guard body parameterised only by its pattern, so the alternation controls differ in exactly the property under test: where the anchor sits.
_COMMAND_FIXTURE = """import json
import re
import sys

PAT = re.compile(r"{pattern}")
{extra}
doc = json.load(sys.stdin).get("tool_input") or {{}}
sys.exit(2 if PAT.search(str(doc.get("command") or "")) else 0)
"""

# Each row: (fixture name, the guard's pattern, a second module-level matcher or "", the outcome `assess` must give, why). Every row whose outcome is not "clean" was "clean" or "static" under the first-branch instantiator and the substring ANCHORED test, which is what the row is there to keep from coming back.
_ALTERNATION_ROWS = [
    (
        "first_branch_anchored.py",
        r"(^|[;&|(])[ \t]*frobnicate[ \t]+widgets|grommet[ \t]+gadgets",
        "",
        "prose",
        "the anchor covers the FIRST alternative only, and the unanchored second one refuses prose",
    ),
    (
        "boundary_in_one_branch.py",
        r"(frobnicate[ \t]+widgets|grommet\.gadgets|(^|[^A-Za-z0-9_])sprocket\.py)[ \t]+create([ \t]|$)",
        "",
        "prose",
        "the 2026-10-09 block_worktree_add draft's shape: a `(^|` word boundary inside one alternative of three",
    ),
    (
        "every_branch_anchored.py",
        r"(^|[;&|(])[ \t]*(frobnicate[ \t]+widgets|grommet[ \t]+gadgets)",
        "",
        "clean",
        "the anchor governs the whole alternation, so no alternative can match inside a sentence",
    ),
    (
        "short_partial.py",
        r"(^|[;&|(])[ \t]*ab|cd+",
        "",
        "prose",
        "a SHORT WORDED instance (`cd`) is probed like any other word; the old four-character floor called this unprobed and never asked the guard",
    ),
    (
        "short_anchored.py",
        r"(^|[;&|(])[ \t]*(ab|cd+)",
        "",
        "clean",
        "short worded instances under an anchor that governs every alternative: probed, and silent",
    ),
    (
        "short_mixed.py",
        r"(^|[;&|(])[ \t]*(ab|cd+)",
        # The sibling is CONSULTED, joined into the matcher at run time (an expression `ast` does not fold, so the module constant PAT stays the anchored one). A sibling the guard never reads would be probed and rightly found silent.
        'OTHER = re.compile(r"ef+")\nPAT = re.compile(PAT.pattern + "|" + OTHER.pattern)',
        "prose",
        "one anchored matcher must not vouch for an unanchored short worded sibling in the same module",
    ),
    (
        "undeclared_fragment.py",
        r"(^|[;&|(])[ \t]*frobnicate[ \t]+widgets",
        'OTHER = re.compile(r"\\$[A-Za-z_]+")',
        "unprobed",
        "an unanchored pattern with NO worded instance (`$x`) and no FRAGMENTS declaration fits none of the three ways",
    ),
]

# The fragment declaration `fragment_controls` grants `undeclared_fragment.py`, so the same fixture is judged both ways.
_FIXTURE_FRAGMENT = "BLOCKER: a planted variable-expansion parser with no literal word, declared to prove the third way passes"

# The planted argument-shaped guard: the block_binary_deploy shape, a command-name matcher at a word boundary that refuses only when the clause's LAST field is a `host:` spec. `sentence()` ends in `repo`, so only `argument_sentence()` can reach the second test.
_ARGSHAPE_FIXTURE = """import json
import re
import sys

ZCP = re.compile(r"{pattern}")
HOST = re.compile(r"^[A-Za-z0-9_.-]+:")

doc = json.load(sys.stdin).get("tool_input") or {{}}
for clause in re.split(r"[;&|]", str(doc.get("command") or "")):
    fields = clause.split()
    if ZCP.search(clause) and fields and HOST.search(fields[-1]):
        sys.exit(2)
sys.exit(0)
"""


def alternation_controls(td: Path) -> None:
    """Every alternative is probed, and an anchor counts only where it governs every alternative."""
    # The renderer, directly: every alternative appears, and `[{S}]`-style whitespace classes render as a space rather than the `x` that made 150 of 171 old instances unmatchable.
    every = instances(r"(alpha|beta|(^|[^A-Za-z0-9_])gamma)[ \t\n]+widgets")
    for alternative in ("alpha widgets", "beta widgets", "gamma widgets"):
        if alternative not in every:
            fail(f"instances() did not render the alternative {alternative!r}: {every!r}")
    for pattern, anchored in (
        (r"(^|[;&|(]|\$\(|`)[ \t]*git[ \t]+worktree", True),
        (r"(^|[;&|(])\s*(frob|grom)", True),
        (r"(^|[;&|(])\s*frob|grom", False),
        (r"(alpha|beta|(^|[^A-Za-z0-9_])gamma)\.py", False),
        (r"(^|[ \t])rm[ \t]", False),
        (r"((bash|sh)\s+)?(^|;)run", False),
    ):
        if command_anchored(pattern) is not anchored:
            fail(f"command_anchored({pattern!r}) is {not anchored}, expected {anchored}")

    for name, pattern, extra, want, why in _ALTERNATION_ROWS:
        guard = td / name
        guard.write_text(_COMMAND_FIXTURE.format(pattern=pattern, extra=extra))
        got, detail = assess(guard, "command", "")
        if got != want:
            fail(f"{name}: assess() gave {got!r} ({detail}), expected {want!r}: {why}")
    # The fully anchored fixture must still refuse the REAL command on its second alternative, or its "clean" is a guard that refuses nothing.
    if not fires(td / "every_branch_anchored.py", "grommet gadgets --now"):
        fail("the anchored alternation fixture missed its own second alternative as a real command")


def argument_controls(td: Path) -> None:
    """The second template reaches a matcher that decides on the arguments, at any length, and an anchored twin stays clean through it."""
    # `zcp` is the block_binary_deploy shape; `zsync` is the same matcher at five characters, which the old `len < SHORT_INSTANCE` gate never asked the second template (#32e75fa4).
    for name in ("zcp", "zsync"):
        loose = td / f"argshape_loose_{name}.py"
        loose.write_text(_ARGSHAPE_FIXTURE.format(pattern=rf"(^|[ \t]){name}[ \t]"))
        tight = td / f"argshape_anchored_{name}.py"
        tight.write_text(_ARGSHAPE_FIXTURE.format(pattern=rf"(^|[;&|(])[ \t]*{name}[ \t]"))
        # The control on the control: the plain sentence must NOT reach it, or this proves nothing about the second template.
        if fires(loose, sentence(name)):
            fail(
                f"the argument-shaped {name} fixture refuses the PLAIN sentence; it cannot prove the second template"
            )
        if not fires(loose, f"{name} a.sh host:/dst/a.sh"):
            fail(
                f"the argument-shaped {name} fixture misses its own real upload; the control proves nothing"
            )
        got, detail = assess(loose, "command", "")
        if got != "prose" or detail != argument_sentence(name):
            fail(
                f"an unanchored command-name matcher ({name}) that needs a host argument was not refused "
                f"through argument_sentence() ({got}: {detail}); worded instances are not reaching it"
            )
        got, detail = assess(tight, "command", "")
        if got != "clean":
            fail(f"the ANCHORED argument-shaped {name} fixture was not clean ({got}: {detail})")
        if not fires(tight, f"true && {name} a.sh host:/dst/a.sh"):
            fail(
                f"the anchored argument-shaped {name} fixture misses the real command after a separator"
            )


def fragment_controls(td: Path) -> None:
    """Both directions of the FRAGMENTS declaration, and each way a declaration goes stale."""
    guard = td / "undeclared_fragment.py"
    if not guard.exists():
        fail("fragment_controls ran before alternation_controls wrote undeclared_fragment.py")
    declared = {(guard.name, "OTHER"): _FIXTURE_FRAGMENT}
    got, detail = assess(guard, "command", "", declared)
    if got != "clean":
        fail(
            f"a DECLARED unworded fragment was not passed ({got}: {detail}); the third way does not work"
        )
    if fragment_findings(declared, td):
        fail(f"a valid FRAGMENTS declaration was reported: {fragment_findings(declared, td)}")
    stale_rows = {
        "vanished": ((guard.name, "GONE"), "no matcher-shaped constant"),
        "anchored": ((guard.name, "PAT"), "anchored at command position"),
        "worded": (("short_mixed.py", "OTHER"), "renders a worded instance"),
        # Named after this run's temporary directory, so no tracked file can name it: the trap registry reads a guard named in a live file as live (668becd2.1).
        "no guard": ((f"retired_{td.name}.py", "OTHER"), "no longer exists"),
        "short reason": ((guard.name, "OTHER"), "too short"),
        "no prefix": ((guard.name, "OTHER"), "must start with 'BLOCKER:'"),
    }
    for label, (key, want) in stale_rows.items():
        why = _FIXTURE_FRAGMENT
        if label == "short reason":
            why = "BLOCKER: too short"
        elif label == "no prefix":
            why = why[len("BLOCKER: ") :]
        found = fragment_findings({key: why}, td)
        if len(found) != 1 or want not in found[0]:
            fail(f"a {label} FRAGMENTS entry was not reported as {want!r}: {found}")


# The planted structure-declaration fixtures. One Python guard body, parameterised by what it refuses and what it declares, so the three controls differ in exactly the property under test.
_FIXTURE = """import json
import re
import sys

{declaration}
SUBJECT = re.compile(r"frobnicate\\s+widgets")

doc = json.load(sys.stdin).get("tool_input") or {{}}
content = str(doc.get("content") or "")
if not str(doc.get("file_path") or "").endswith(".md"):
    sys.exit(0)
{rule}
sys.exit(0)
"""
_STRUCTURE_RULE = 'if not content.startswith("Header: ok\\n"):\n    sys.exit(2)'
_MENTION_RULE = "if SUBJECT.search(content):\n    sys.exit(2)"
_VALID = 'ANCHORING = "structure: judges whether the resulting document keeps its Header line"'


def structure_controls(td: Path) -> None:
    """Both directions of the structure declaration, against planted Python guards."""
    docs = td / "docs"
    docs.mkdir()
    (docs / "a-accepted.md").write_text("Header: ok\nA body with nothing in it.\n")
    # A path that does not exist, like the real plan guard's own first path: the baseline must then be found among its siblings.
    fp = str(docs / "a-probe.md")

    def write_guard(name: str, declaration: str, rule: str) -> Path:
        path = td / name
        path.write_text(_FIXTURE.format(declaration=declaration, rule=rule))
        return path

    structure = write_guard("structure_declared.py", _VALID, _STRUCTURE_RULE)
    outcome, detail = assess(structure, "edit", fp)
    if outcome != "clean" or "a-accepted.md" not in detail:
        fail(
            "a STRUCTURE guard that declares it was not passed by the neutral probe "
            f"({outcome}: {detail}); the declaration cannot work"
        )
    if not fires(structure, sentence("frobnicate widgets"), "edit", fp):
        fail(
            "the planted structure guard does not refuse the bare sentence; the control proves nothing"
        )

    bare = write_guard("structure_undeclared.py", "", _STRUCTURE_RULE)
    outcome, detail = assess(bare, "edit", fp)
    if outcome != "prose":
        fail(
            "the SAME structure guard WITHOUT the declaration was not reported as refusing prose "
            f"({outcome}: {detail}); the plain probe has stopped firing"
        )

    mention = write_guard("mention_declared.py", _VALID, _MENTION_RULE)
    outcome, detail = assess(mention, "edit", fp)
    if outcome != "prose":
        fail(
            "a MENTION matcher that declares structure passed the neutral probe "
            f"({outcome}: {detail}); the declaration would excuse the very class this gate catches"
        )

    short = write_guard("structure_short.py", 'ANCHORING = "structure: short"', _STRUCTURE_RULE)
    if assess(short, "edit", fp)[0] != "invalid":
        fail("a structure declaration with a too-short reason was accepted")
    missing = write_guard("structure_noreason.py", 'ANCHORING = "document shape"', _STRUCTURE_RULE)
    if assess(missing, "edit", fp)[0] != "invalid":
        fail("an ANCHORING constant without the `structure:` form was accepted")
    if assess(structure, "command", fp)[0] != "invalid":
        fail("a structure declaration on a non-pre-edit chain was accepted")

    # No accepted document to append to: red, never a silent skip.
    lonely = td / "lonely"
    lonely.mkdir()
    (lonely / "b-rejected.md").write_text("no header here\n")
    if assess(structure, "edit", str(lonely / "b-probe.md"))[0] != "nobase":
        fail("a structure guard with no accepted baseline document was not reported")


def fail(msg: str) -> None:
    print(f"{RED}✗ CONTROL FAILED{NC}: {msg}", file=sys.stderr)
    print("  A clean result below would mean nothing, so this gate refuses.", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    controls()

    probed = 0
    static_ok = 0
    unprobed: list[tuple[str, str]] = []
    offenders: list[tuple[str, str]] = []

    guards: list[tuple[Path, str, str]] = []
    for path in sorted(GUARDS.glob("*.py")):
        name = path.stem
        if not name.startswith(("block_", "warn_", "require_")):
            continue
        chain = chain_of(path)
        if chain is None:
            continue
        kind = CHAINS.get(chain)
        if kind is None:
            continue
        guards.append((path, kind, chain))

    # CONCURRENT ACROSS GUARDS, sequential within one. Probing every alternative raised the probe count from 171 to about 630, each a guard subprocess of ~0.2 s, which serial would be over two minutes. One guard's probes stay in one worker so a guard with a side effect (block_settled_questions appends a refusal ledger) never races itself.
    with ThreadPoolExecutor(max_workers=core_lease.granted_cores()) as pool:
        verdicts = list(pool.map(lambda g: assess(g[0], g[1], file_path_for(g[0])), guards))

    probe_total = 0
    probe_sentences = 0
    probe_self = 0
    probe_dropped = 0
    probe_fragments = 0
    invalid: list[tuple[str, str]] = []
    stale: list[str] = []
    for (guard, _kind, chain), (outcome, detail) in zip(guards, verdicts, strict=True):
        name = guard.name
        shape = probes_of(patterns_of(guard))
        probe_total += len(shape.instances)
        probe_sentences += shape.sentences()
        probe_self += shape.self_matching
        probe_dropped += shape.dropped
        probe_fragments += shape.fragments
        # TIER 2, STATIC, inside `assess`. A guard with nothing to probe is not automatically a defect, and treating it as one would demand that guards be rewritten to suit this instantiator rather than to match commands correctly. Every pattern is judged on its own, three ways: ANCHORED (`command_anchored`, every alternative at command position), WORDED (a literal word a sentence can
        # mention, so it is probed at any length), or a declared FRAGMENT (a parser for a piece of a command the guard already located, in FRAGMENTS with a reason). A pattern fitting none of the three is red by name. Before 2026-10-09 the question was asked of the whole guard, only when no instance of four characters survived, and short words such as `scp` were dropped with the fragments.
        #
        # PROSE FIRING IS SELF-EVIDENT: nothing else has to be true for a guard refusing a sentence to be a defect. Requiring a POSITIVE probe to also fire before trusting silence was tried and rejected -- most extracted instances are one fragment of a multi-part trigger (a roundlog guard needs BOTH a matching file_path AND a write call; no single instantiated substring can satisfy
        # that alone), so demanding per-instance reachability reported 37 of 42 guards as inconclusive even though most were already known-clean from the pre-bash-only scan. The signal this check needs is the one that is unconditionally trustworthy: does prose trip the guard.
        if outcome == "allowed":
            continue
        if outcome == "static":
            static_ok += 1
            continue
        if outcome == "unprobed":
            unprobed.append((name, detail))
            continue
        if outcome == "invalid":
            invalid.append((f"{chain}/{name}", detail))
            continue
        probed += 1
        if name in PROSE_TARGETS:
            if outcome == "prose":
                refused = detail.split(PROSE_SEP)
                print(f"PROSE-TARGET {chain}/{name}: {PROSE_TARGETS[name]}")
                print(f"    {len(refused)} probe sentence(s) refused, as its rule intends:")
                for text in refused:
                    print(f"      {text}")
            else:
                stale.append(f"{chain}/{name}")
            continue
        if outcome == "prose":
            offenders.append((f"{chain}/{name}", detail))
        elif outcome == "nobase":
            invalid.append((f"{chain}/{name}", detail))
        elif " | baseline " in detail:
            # PRINTED EVERY RUN: a structure declaration is an exemption from the plain probe, and a quiet exemption is how a gate stops meaning what its name says.
            reason, base = detail.split(" | baseline ", 1)
            print(f"STRUCTURE-JUDGED {chain}/{name}: {reason}")
            shown = Path(base)
            if shown.is_relative_to(REPO_ROOT):
                shown = shown.relative_to(REPO_ROOT)
            print(f"    probed structure-neutrally: the sentence appended to {shown}")

    if probed < 20:
        print(
            f"{RED}✗{NC} only {probed} guard(s) were probed; the enumeration or the",
            file=sys.stderr,
        )
        print(
            "  instantiator is broken, not the guards. A scan this small cannot fail.",
            file=sys.stderr,
        )
        return 1

    for name, text in offenders:
        print(f"{RED}✗{NC} {name} refuses PROSE, not a command.", file=sys.stderr)
        print(f"    sentence: {text}", file=sys.stderr)
        print(
            "    Anchor the match to command position -- (^|[;&|(]) and friends --", file=sys.stderr
        )
        print("    rather than deleting or narrowing the pattern.", file=sys.stderr)

    for name, consts in unprobed:
        print(
            f"{RED}✗{NC} {name}: {consts} is not anchored at command position and renders no "
            "word a sentence could mention, so nothing probes it.",
            file=sys.stderr,
        )
        print(
            "    Anchor it with (^|[;&|(]) and friends, or, if it parses a piece of a command the guard",
            file=sys.stderr,
        )
        print(
            f"    already located, declare (guard, constant) in FRAGMENTS in {Path(__file__).name} with a BLOCKER reason.",
            file=sys.stderr,
        )

    for name, why in invalid:
        print(f"{RED}✗{NC} {name}: {why}", file=sys.stderr)
        print(
            f'    A structure judge declares `{ANCHORING_NAME} = "{STRUCTURE_PREFIX} <reason>"` '
            f"(>= {MIN_REASON} chars) and needs an accepted in-scope document to append to.",
            file=sys.stderr,
        )

    # PRINTED EVERY RUN, like a structure declaration: a FRAGMENTS entry is an exemption from the probe, and a quiet one is how the gate stops meaning what its name says.
    for (gname, const), why in sorted(FRAGMENTS.items()):
        print(f"FRAGMENT {gname}::{const}: {why}")
    fragment_problems = fragment_findings(FRAGMENTS)
    for problem in fragment_problems:
        print(f"{RED}✗{NC} {problem}", file=sys.stderr)

    for name in stale:
        print(
            f"{RED}✗{NC} {name} is listed in PROSE_TARGETS but refused no probe sentence. The "
            "exemption is stale: delete the entry and let the plain probe judge the guard.",
            file=sys.stderr,
        )

    # THE SHAPE, every run. A collapse in the instance count or in how many instances their own pattern matches is how a broken instantiator shows itself before it shows up as a false green.
    print(
        f"probes: {probe_total} instance(s) rendered from every alternative of every pattern, "
        f"as {probe_sentences} sentence(s); {probe_self} match the pattern they came from; "
        f"{probe_fragments} unworded fragment instance(s) under {SHORT_INSTANCE} chars not probed; "
        f"{len(FRAGMENTS)} declared FRAGMENTS constant(s); {probe_dropped} past the "
        f"{MAX_INSTANCES}-per-pattern bound"
    )
    if probe_dropped:
        print(
            f"{RED}✗{NC} {probe_dropped} instance(s) were dropped by MAX_INSTANCES, so those "
            "alternatives were never probed. Raise the bound; never let it cut silently.",
            file=sys.stderr,
        )
        return 1

    if offenders or unprobed or invalid or stale or fragment_problems:
        print(
            f"\n{RED}✗{NC} {len(offenders)} guard(s) refuse prose; {len(unprobed)} hold an "
            f"unprobed pattern; {len(invalid)} structure declaration(s) invalid or unprobeable; "
            f"{len(stale)} stale PROSE_TARGETS entr(y/ies); {len(fragment_problems)} FRAGMENTS "
            "problem(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"{GREEN}✓{NC} {probed} guard(s) across {len(CHAINS)} chain(s) refuse commands, not "
        f"sentences about them; {static_ok} anchored or not phrase-matching; "
        f"{len(PROSE_TARGETS)} prose-target exemption(s) and {len(FRAGMENTS)} declared "
        "fragment(s), printed above"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
