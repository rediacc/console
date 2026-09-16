"""Block edits that add a fat inline `run:` block to a GitHub workflow.

The rule (enforced in CI by .ci/scripts/quality/check-workflows.sh): a workflow
`run:` block scalar whose shell logic exceeds 8 non-blank/non-comment lines does
not belong inline. CI step logic lives in .ci/scripts/<area>/<name>.sh so it is
locally runnable and shareable across CI systems; the workflow step is env
wiring + one script call.

This is the fast local nudge for that rule: it fires only for
.github/workflows/*.yml|yaml edits, only when the new content introduces a
`run:` block that already crosses the threshold within the edited fragment.
The CI gate remains the source of truth: it parses whole files, so a fat block
assembled across several edits still fails there even if no single fragment
trips this hook.

PORT NOTE ON THE awk PROGRAM, which is the whole guard. Four of its details are
invisible once it is Python and each one changes the count:

  * UNINITIALISED awk VARIABLES ARE 0. `n`, `max`, `inblock` and `keyindent`
    are never assigned before use, and the program leans on that: the first
    record is judged with `inblock == 0` and `max == 0`.
  * `match(line, /^ */); cur = RLENGTH` counts LITERAL SPACES ONLY. A tab-
    indented workflow would measure as indent zero. That is the original's
    behaviour, kept, because the CI parser it mirrors does the same thing and a
    port that "fixed" it here would disagree with the gate.
  * `flush()` DOES NOT RESET `n`, only `max` and `inblock`. The END block calls
    it again unconditionally, which is why a block running to the last record
    is counted at all.
  * `substr(line, cur + 1)` is 1-BASED, so it is `line[cur:]` here and not
    `line[cur + 1:]`. An off-by-one there would read the second character of
    every line and never see a `#`.

PORT NOTE ON THE SUBJECT'S NEWLINE. `printf '%s\\n' "$CONTENT"` appends exactly
one newline whatever the content ends with, so the last line is a full record.
`hookio._printf_line` is that, and it is NOT the here-string: the difference
only shows on an empty subject, which the `-z` test above has already returned
on.
"""

import re

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-inline-workflow-run.sh"
ORDER = 5

# The comment skip inside the block scalar. Without it every `#` line in a
# `run: |` counts toward the limit, so a well-annotated 6-line step is refused
# for being 9 lines long -- the exact "logic lines" distinction the CI rule and
# this guard's own header are stated in terms of.
DEFECT = ('if rest[:1] != "#":', "if True:")

MAX = 8

# `case "$FILE" in *.github/workflows/*.yml | *.github/workflows/*.yaml)`. A
# shell glob, so the leading `*` makes the path test suffix-relative rather
# than anchored at the repo root, and a file merely NAMED like a workflow
# elsewhere in the tree does not match.
WORKFLOW_GLOBS = ("*.github/workflows/*.yml", "*.github/workflows/*.yaml")

BLANK_LINE = hookio.rx(r"^[{S}]*$")
RUN_BLOCK = hookio.rx(r"^[{S}]*run:[{S}]*[|>]")

MESSAGE = (
    "❌ BLOCKED: this edit puts a %s-line inline 'run:' block in %s (limit is %s logic "
    "lines). Do not add shell logic inline in a workflow. Extract it to "
    ".ci/scripts/<area>/<name>.sh (the script header documents required env + how to run "
    "it locally), and make the workflow step env wiring + one call to that script. CI "
    "enforces this via check-workflows.sh and there is no exemption list: the 52 legacy "
    "blocks that used to be grandfathered have all been extracted and the baseline file "
    "was deleted, so the rule now holds for every workflow without exception."
)

_FAT = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          echo %d" % i for i in range(9)]
)

_ANNOTATED = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          # step %d" % i for i in range(3)]
    + ["          echo %d" % i for i in range(6)]
)

EDGE_CASES = [
    (
        "nine logic lines in one block",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "new_string": _FAT}},
    ),
    # The comment skip, and the reason this guard counts LOGIC lines: nine
    # indented lines, six of them logic.
    (
        "comments inside the block are not logic",
        {"tool_input": {"file_path": ".github/workflows/ci.yaml", "new_string": _ANNOTATED}},
    ),
    # The glob's job: a workflow-shaped fragment in a file that is not a
    # workflow is the CI gate's business, not this hook's.
    (
        "the same fragment outside .github/workflows",
        {"tool_input": {"file_path": "docs/example.yml", "new_string": _FAT}},
    ),
    (
        "a short run block",
        {
            "tool_input": {
                "file_path": ".github/workflows/ci.yml",
                "new_string": "      - run: |\n          npm ci\n          npm test\n",
            }
        },
    ),
    (
        "a run: with no block scalar is not a block",
        {
            "tool_input": {
                "file_path": ".github/workflows/ci.yml",
                "new_string": "      - run: npm ci",
            }
        },
    ),
    (
        "an edits array is collected the same way",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "edits": [{"new_string": _FAT}]}},
    ),
    (
        "an empty fragment",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "new_string": ""}},
    ),
]


def _worst(content):
    """The awk program above, record for record.

    Same block-scalar rules as the CI parser: a block owns following
    blank/deeper-indented lines; a logic line is non-blank and does not start
    with `#`.
    """
    records, _ = hookio._records(hookio._printf_line(content))
    biggest = 0
    n = 0
    inblock = False
    keyindent = 0
    for record in records:
        # `line = $0; sub(/\r$/, "", line)` -- one CR, at the end, once.
        line = re.sub(r"\r$", "", record, count=1)
        if re.search(BLANK_LINE, line):
            continue
        cur = re.match(r"^ *", line).end()
        if inblock:
            if cur > keyindent:
                rest = line[cur:]
                if rest[:1] != "#":
                    n += 1
                continue
            # flush(): the running block ends here, and `n` deliberately keeps
            # its value until the next `run:` resets it.
            biggest = max(biggest, n)
            inblock = False
        if re.search(RUN_BLOCK, line):
            keyindent = cur
            inblock = True
            n = 0
    # `END { flush(); print max + 0 }`
    return max(biggest, n)


def run(ev):
    file_path = ev.field("tool_input", "file_path")
    if not hookio.case_glob(file_path, *WORKFLOW_GLOBS):
        return hookio.ALLOW

    content = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
    )
    if content == "":
        return hookio.ALLOW

    # Largest run: block logic-line count in the fragment.
    worst = _worst(content)
    if worst > MAX:
        ev.warn(MESSAGE % (worst, file_path, MAX))
        return hookio.DENY
    return hookio.ALLOW
