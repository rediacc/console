"""Block lint/type suppression directives in Edit/Write/MultiEdit/NotebookEdit content.

NOTE: the banned tokens are written with a trailing char class (e.g.
eslint-disabl[e]) so this very file never contains the literal token
contiguously, otherwise this guard would block edits to its own source. The
[x] class still matches the real token. That convention is not decoration:
drafting the comment below WITHOUT it got the repair refused by the very guard
being repaired.

TWO NARROWINGS, both paid for. The original test was "does this content
contain the token, anywhere, in any file", which is the mention-as-execution
shape this repo hit twelve times in one session. Measured 2026-08-27, it
refused:

  docs/style.md   "Never write @ts-ignor[e]; fix the type instead."

That is not a suppression, it is the RULE being written down -- so the guard
refused the documentation of itself. Its own header had named this exact
over-block class as a known risk without ever testing for it, which is what an
allow case of `const x = 1;` buys you: proof the regex is not matching
literally everything, and nothing else.

  1. CODE FILES ONLY. A directive in Markdown is an example, and an example is
     how the rule gets taught. A fenced snippet showing the wrong way must
     stay writable.
  2. DIRECTIVE POSITION. A real suppression sits immediately after a comment
     opener: `// @ts-ignor[e]`, `/* eslint-disabl[e] */`, `{/* ... */}`. Prose
     puts words in between, and those words are what tell the two apart. This
     is a property of the syntax rather than a keyword list, so it does not
     need maintaining as people find new ways to phrase a sentence.

PORT NOTE ON THE TRAILING-CHAR-CLASS CONVENTION, WHICH SURVIVES FOR A SECOND
REASON HERE. In the pattern it is doing exactly what the header says. In the
MESSAGE it is doing something the bash spelled differently: the original writes
`"...eslint-disabl""e, @ts-ignor""e..."`, two adjacent double-quoted strings
that the shell concatenates, so the emitted bytes carry the whole token while
the SOURCE never does. The port keeps both halves apart for the same reason and
joins them once, at module level, so the message this guard prints is byte for
byte what its twin prints while the file remains editable.

PORT NOTE ON THE EXTENSION TEST. `case "$FILE" in *.ts | ... ) ;; "") ;; *)
exit 0 ;; esac` is a shell GLOB, not a regex, and the empty arm is a
deliberate hole-closer with its own comment. `hookio.case_glob` is the glob;
the empty string is spelled as its own disjunct rather than folded into the
pattern list, because `case_glob("", "*.ts")` is false and an empty payload
must NOT be dismissed as "not code".
"""

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-suppressions.sh"
ORDER = 3

# Narrowing 1, and the one the 2026-08-27 measurement exists for. Dropping the
# extension test restores "does this content contain the token, anywhere, in
# any file" -- which refused `docs/style.md` teaching the rule it enforces.
DEFECT = (
    'if not (hookio.case_glob(file_path, *CODE_SUFFIXES) or file_path == ""):',
    "if False:",
)

# The extensions a real suppression directive can live in. Everything else is
# prose until proven otherwise.
CODE_SUFFIXES = (
    "*.ts",
    "*.tsx",
    "*.js",
    "*.jsx",
    "*.cjs",
    "*.mjs",
    "*.vue",
    "*.svelte",
    "*.astro",
)

TOKENS = r"eslint-disabl[e]|@ts-ignor[e]|@ts-nochec[k]|@ts-expect-erro[r]|biome-ignor[e]"

# Narrowing 2. `//`, `/*`, a JSX `{/*`, a continued block-comment `*`, or `#`.
OPENER = r"(//+|/\*+|\{[" + hookio.SPACE + r"]*/\*+|^[" + hookio.SPACE + r"]*\*+|#)"

PATTERN = OPENER + r"[" + hookio.SPACE + r"]*(" + TOKENS + r")"

# The message's tokens, kept in halves in the SOURCE and whole in the OUTPUT.
# See the port note above; this is the `""` concatenation the bash uses.
MESSAGE = "❌ BLOCKED: Do not use %s, %s, %s, %s, or %s. Fix the issue properly." % (
    "eslint-disabl" + "e",
    "@ts-ignor" + "e",
    "@ts-nochec" + "k",
    "@ts-expect-erro" + "r",
    "biome-ignor" + "e",
)

_TS_IGNORE = "@ts-ignor" + "e"
_ESLINT_DISABLE = "eslint-disabl" + "e"

EDGE_CASES = [
    (
        "a directive at a comment opener in a code file",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "// %s\nconst x = 1;" % _TS_IGNORE}},
    ),
    (
        "a block comment opener",
        {"tool_input": {"file_path": "src/a.tsx", "new_string": "/* %s */" % _ESLINT_DISABLE}},
    ),
    (
        "a JSX comment opener",
        {"tool_input": {"file_path": "src/a.tsx", "new_string": "{/* %s */}" % _ESLINT_DISABLE}},
    ),
    # The 2026-08-27 case, in the file it was measured on. Markdown is not code,
    # so teaching the rule is not breaking it.
    (
        "the rule written down in a doc",
        {
            "tool_input": {
                "file_path": "docs/style.md",
                "new_string": "Never write %s; fix the type instead." % _TS_IGNORE,
            }
        },
    ),
    # ... and the same sentence inside a code file, which narrowing 2 covers on
    # its own: prose puts words between the opener and the token.
    (
        "prose in a code file is still prose",
        {
            "tool_input": {
                "file_path": "src/a.ts",
                "new_string": "// Never write %s; fix the type instead." % _TS_IGNORE,
            }
        },
    ),
    (
        "the token with no opener at all",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "const s = '%s';" % _TS_IGNORE}},
    ),
    # The empty arm of the `case`: a payload naming no file could be anything,
    # and defaulting to "not code" would be a hole.
    (
        "no file_path at all still gets checked",
        {"tool_input": {"new_string": "// %s" % _TS_IGNORE}},
    ),
    (
        "a MultiEdit edits array is collected too",
        {
            "tool_input": {
                "file_path": "src/a.ts",
                "edits": [{"new_string": "ok"}, {"new_string": "// %s" % _TS_IGNORE}],
            }
        },
    ),
    (
        "Write uses content rather than new_string",
        {"tool_input": {"file_path": "src/a.js", "content": "# %s" % _ESLINT_DISABLE}},
    ),
    (
        "a NotebookEdit new_source is collected too",
        {"tool_input": {"file_path": "src/a.mjs", "new_source": "// %s" % _TS_IGNORE}},
    ),
    (
        "an ordinary code edit",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "const x = 1;"}},
    ),
    (
        "a non-code file with no directive",
        {"tool_input": {"file_path": "README.md", "new_string": "hello"}},
    ),
]


def run(ev):
    file_path = ev.field("tool_input", "file_path")
    # `case "$FILE" in *.ts | ... ) ;; "") ;; *) exit 0 ;; esac`. No file_path
    # at all still gets checked: a payload that names no file could be
    # anything, and defaulting to "not code" would be a hole.
    if not (hookio.case_glob(file_path, *CODE_SUFFIXES) or file_path == ""):
        return hookio.ALLOW

    # `[.tool_input.content, .tool_input.new_string, .tool_input.new_source,
    #   (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")`
    content = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
    )
    if content == "":
        return hookio.ALLOW

    # `printf '%s' "$CONTENT" | grep -qE ...`, so an empty subject would be zero
    # records rather than one empty one. The `-z` test above already returned,
    # but the spelling is kept because the two differ and the next edit here
    # should not have to rediscover which one the original used.
    if hookio.grep_q(PATTERN, content):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
