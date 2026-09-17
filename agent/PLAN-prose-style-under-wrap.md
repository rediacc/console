# PLAN: prose-style under-wrap detection (R19)

Status: draft
Owner: d778be9d

## Why

The operator read fresh comment-block prose this session wrote inside `prose_style.py` /
`block_prose_style_commit.py`, hard-wrapped at ~70-90 characters deep inside the 384-char R18
budget, and asked for three things: (1) sweep the tree for the same pattern and fix it, (2)
extend that sweep to commit/PR messages ("also for commit and others"), (3) make
`block_prose_style_edit.py` (and the commit guard) **block** a newly-introduced under-wrapped
paragraph rather than merely report it as debt.

This document designs that detector, decides its scope against measured numbers (not guesses),
and lays out the wiring -- without implementing anything.

## Do not regress

This session's tree already carries three uncommitted, review-found fixes in the same two files
this plan touches (`git diff .claude/rediacc_hooks/guards/block_prose_style_commit.py
.ci/rediacc_ci/quality/prose_style.py`):

1. `GIT_COMMIT`/`GH_PR` gained `re.MULTILINE` (a `git commit` on line 2 of a multi-line command
   was invisible to `^`).
2. `_is_docstring()` now steps past `tokenize.NL` (not just `tokenize.COMMENT`) so an
   implicitly-concatenated string fragment (the `PERMISSION` regex tuple in
   `block_secret_exposure.py`) is not misread as a docstring.
3. `block_prose_style_commit.py`'s `scope` is now computed per-message via `_scope_for(label)` /
   `PR_LABELS`, not once per whole chained command.

`test-block_prose_style_commit.py` is 27/27 green against these, and the baseline has already
been drained from 3597 to 3222 findings (375 false positives removed by fix #2, verified by
measuring `worklist_messages.py` alone: 1028 implicit string-concatenation boundaries). Any
change here must run that suite (and the engine's own `--selftest`) before and after, and must
not touch `_is_docstring`, `_scope_for`, or the `GIT_COMMIT`/`GH_PR` regexes.

## The measurement that has to drive the scope decision

Ground truth, measured live against this tree today, not estimated:

| Measurement | Command | Result |
|---|---|---|
| Baseline size (all 18 rules, post-drain) | `python3 -c "import json; d=json.load(open('.ci/config/prose-style-baseline.json')); print(d['count'], d['files'], d['by_rule'])"` | 3,222 findings, post-drain |
| Markdown reflow dry run (existing `reflow` subcommand, unchanged) | `python3 .ci/scripts/quality/check_prose_style.py reflow` | would rewrite 400/436 markdown files, collapsing 37,038 physical lines |
| **Naive** join-feasibility, markdown, per PARAGRAPH (reflow's own paragraph boundaries; a paragraph counts if `reflow_markdown(paragraph, 384) != paragraph`) | ad hoc script, see "How to re-run" below | **11,816 of 11,817** multi-line paragraphs (429/436 files) -- i.e., virtually the entire markdown corpus |
| Stricter heuristic: 3+ lines, all within a 20-char band, all <=40% of 384 | same script, banded variant | 7,228 paragraphs, 371/436 files -- still most of the corpus |
| Naive join-feasibility, **comment** scope (`.py`/`.ts`/`.tsx`/`.js`/`.cjs`/`.mjs`/`.go`), adjacent-line pairs | ad hoc script | **94,201** joinable pairs across 1,941 of 2,061 comment-scope files |
| Tooling conflict check for comment scope | `ruff check` / `ruff format --diff` on a long single-line comment | **No conflict found** (see note below the table) |

`pyproject.toml` disables `E501` ("owned by the formatter"), and `ruff format` does not touch
comment text. `eslint.config.js` has no `max-len` rule either. The ~80-100 col comment
convention is habit and readability, not a tool-enforced ceiling.

**Conclusion the plan is built on:** a literal "would this still fit if joined" test is not a
debt detector in this tree -- it is a description of how essentially all existing prose is
written. R18's 384 is a ceiling meant to catch a pathological unwrapped wall of text, not a
target width authors are expected to fill. Any rule built on the literal test will fire on
almost every future normal edit unless it is scoped very narrowly and its existing-corpus hits
are frozen at real scale (thousands, not dozens).

## Tasks

- [ ] Confirm with the operator, before writing code, the scope and blast-radius decisions below
      (they are default recommendations, not settled -- the numbers above are surprising enough
      that silent execution would be wrong per the operator's own instruction not to silently
      defer or silently narrow).
- [ ] Factor `reflow_markdown`'s paragraph-buffering loop (fence/frontmatter/list-item/
      REFLOW_STOP handling) out of the function body into a reusable `paragraphs(text)`
      generator yielding `(start_lineno, list[str])`, used by both `reflow_markdown` (unchanged
      behavior, `test_reflow*` must stay green) and the new detector. This is the "reuse, don't
      reinvent join-feasibility" requirement.
- [ ] Add `R19` to `.ci/config/prose-style-rules.json`: `detection: "underwrap"`,
      `scopes: ["markdown", "pr"]` (see Scope decision -- deliberately excludes `comment` and
      `commit`), no `patterns`, one `good` example (a normally-wrapped short paragraph) and one
      `bad` example (a 3+ line uniformly-narrow paragraph, embedded as a `\n`-joined JSON
      string, matching how `R18`/reflow tests embed multi-line fixtures).
- [ ] Extend `Rule.advisory` in `prose_style.py`: `return not self.raw_patterns and
      self.detection not in ("measured", "underwrap")` -- otherwise R19 is reported as
      advisory/undetected and the `_shape()`/`sync` output lies about it.
- [ ] Add `underwrap_findings(text, rule, scope, max_len)` in `prose_style.py`: runs
      `paragraphs(text)`, applies the heuristic gate (below), and for each qualifying paragraph
      emits **one** `Finding` anchored at the paragraph's first line, with `Finding.text` = the
      whole paragraph joined by `\n` (so a rewrite of any line inside it re-keys the baseline
      entry, matching the documented "a rewrite is exactly when a human should look again"
      contract).
- [ ] Wire it into `lint_text` and `lint_message`: both currently loop `for line in lines:
      lint_line(...)`, which has no cross-line context. Add a second pass,
      `findings.extend(underwrap_findings(...))` for the R19 rule if it applies to the scope,
      run once per document/message rather than per extracted `Line`.
- [ ] Decide and implement the heuristic gate (see Detection algorithm) as a named, tested
      function so it is not duplicated a third time.
- [ ] Wire `block_prose_style_edit.py`: no code change needed beyond what already exists -- it
      already calls `engine.lint_text(rel, new_prose, rules, globals_, scope=scope)` and already
      treats any `finding.fid` present in `load_baseline(root)` as carried/allowed. R19 rides the
      same mechanism automatically once wired into `lint_text`. Add `EDGE_CASES` to
      `test-block_prose_style_edit.py`: (a) a fresh multi-line under-wrapped paragraph in a
      `Write`/`content` block; (b) the same paragraph rewritten at full width passes; (c) a
      single-line `Edit.new_string` with no sibling context is NOT flagged (documented
      limitation, see below) -- must be asserted, not just hoped for.
- [ ] Wire `block_prose_style_commit.py`: same, no structural change --
      `lint_message(text, rules, globals_, _scope_for(label))` already exists; R19 applies only
      when `_scope_for(label) == "pr"` (title/body/body-file), never for `"commit"` labels,
      because R19's scopes list omits `commit`. Add `EDGE_CASES` to
      `test-block_prose_style_commit.py` mirroring the edit-guard cases, scoped to
      `gh pr create --body`.
- [ ] Run the tree-wide `check` once R19 is loaded, measure the real finding count (expect low
      thousands per the paragraph-level numbers above, scoped to markdown+pr only, not the
      inflated comment number), and freeze it with `check_prose_style.py check --write-baseline`
      -- this is the SAME shrink-only mechanism every other rule's debt already goes through
      (`write_baseline_guarded`, `baseline_additions`, `write_verdict`). No new baseline
      mechanism is needed or should be built.
- [ ] Update `.ci/rediacc_ci/tests/test_quality_prose_style.py`: the example-driven harness
      (`EXAMPLES`, `test_example`) picks up R19's example automatically once it is in the rules
      file; add dedicated `test_underwrap_*` functions mirroring the existing `test_reflow_*`
      block (paragraph joins -> flags; single-line paragraph -> clean; list item / heading /
      fence adjacency -> clean; already-wide paragraph -> clean; idempotence: a reflowed
      paragraph must not re-flag).
- [ ] Do NOT attempt to bulk-fix the existing pile inline this session. Re-running
      `check_prose_style.py reflow --write` is the correct bulk instrument for markdown, but
      rewriting 400+ files is its own large, separately reviewable diff -- schedule it as a
      follow-up PR, not bundled with the detector landing.
- [ ] Fix only the two files the operator actually pointed at (`prose_style.py`,
      `block_prose_style_commit.py`) by hand this session if the operator still wants that after
      seeing the scope numbers, since two files is a small, safe, human-reviewable diff, unlike
      the 400-file tree-wide reflow. (Already done live this session, ahead of this plan: both
      files' new comment blocks were rewrapped toward the 384 limit and re-verified green.)

## Detection algorithm

**Reuse, don't reinvent.** `reflow_markdown` already answers "would these lines join and still
fit" for markdown; the new rule's whole job is to turn a version of that same answer into a "did
NOT join, but should have" finding. Concretely: `paragraphs(text)` (factored out, see Tasks)
yields the same buffers `reflow_markdown` already collects; for each buffer with 2+ lines, call
`reflow_markdown("\n".join(buffer) + "\n", width)` and compare to the original -- this is the
literal reflow computation, not a second implementation of it.

**Why this can't be a bare "any paragraph reflow changes" test (the naive definition measured
above):** it flags 99.99% of the corpus. The gate needs a heuristic that isolates "this looks
like an accidental narrow hard-wrap" from "this is a normal short paragraph, a normal
sentence-ending short last line, or this repo's universal ~80-115 char authoring habit".
Recommended gate, to be validated against real numbers before landing (see the 7,228/371
measurement above as the current best estimate):

- the paragraph has **3 or more lines** (a 2-line paragraph almost always just ends there -- a
  short final line is not evidence of hard-wrap, it's evidence of a sentence ending);
- **all lines except the last** sit within a narrow width band of each other (candidate: 20
  characters) -- the fixed-column-wrap signature, as opposed to natural variation in sentence
  length;
- that common width is well under the limit (candidate: <= 40% of `max_line_length`, i.e. <=154
  chars) -- a paragraph already wrapped near 300+ chars is not under-wrapped even if one more
  word would technically fit;
- `reflow_markdown` on the paragraph in isolation actually produces fewer lines (guards against a
  paragraph that only differs from its reflow by trailing whitespace).

**Must NOT fire (false-positive list, verified against the extractors):**
- the **last line** of a paragraph (a paragraph is expected to end short; `reflow_markdown`'s own
  `flush()` treats the whole run, not each line, as the unit -- a solo-line finding on the
  terminal line would flag every paragraph in the tree by definition);
- a **list item** or its wrapped continuation (`LIST_ITEM.match`, already a `REFLOW_STOP` --
  `reflow_markdown`'s own controls (`test_reflow`) already assert lists are untouched; the new
  detector must reuse the identical `paragraphs()` boundaries so it inherits this for free rather
  than re-deciding it);
- a line immediately before a **heading, fence, table, blockquote, link definition, or indented
  code** (same `REFLOW_STOP` set -- a line ending right before a structural boundary is a
  deliberate break, not an accident);
- a **single-line "paragraph"** with no line 2 in the same buffer -- nothing to join;
- a paragraph whose next line's first word genuinely would not fit under the width -- this is
  correctly wrapped, not under-wrapped, and the `reflow_markdown` comparison already excludes it
  because the join-then-rewrap would reproduce the same break;
- (edit-time only) a single-line `Edit.new_string` payload with no sibling lines in the same tool
  call -- `lint_text`/`lint_message` only ever see the bytes handed to them ("ONLY THE NEW
  PROSE", per `block_prose_style_edit.py`'s own header), so a paragraph split across several
  sequential single-line `Edit` calls is structurally invisible to this check one edit at a time.
  This must be documented as a known gap, not silently accepted as full coverage: R19 at edit
  time reliably catches a multi-line paragraph authored in **one** `Write`/multi-line
  `Edit`/`MultiEdit` call (which covers the operator's actual triggering case -- the comment
  block was written in one shot), not one assembled a line at a time.

## Scope decision (recommended, needs operator confirmation)

`R19` scopes: **`["markdown", "pr"]`**. Explicitly excludes `comment` and `commit`.

- **`comment` excluded.** Not because of a tooling conflict (verified there isn't one: `ruff`
  has `E501` disabled and doesn't reformat comments; no `eslint` `max-len` found) but because of
  scale and rewrite-hazard false positives: 94,201 joinable pairs across 1,941 of 2,061
  comment-scope files is not a debt pile, it is the default comment-wrapping convention across
  the entire codebase (matching `pyproject.toml`'s `line-length = 100`). Blocking on it would
  mean any edit that touches one line inside an existing multi-line comment block -- an
  extremely common edit shape -- has a high chance of tripping R19 on the untouched sibling lines
  the moment their combined text is re-hashed, which is exactly the false-positive-teaches-
  suppression-marker failure mode `prose_style.py`'s own header names. This is a candidate for a
  **separate, much larger, future plan** (extending `reflow_markdown`'s reach to `comment` scope
  is itself a prerequisite that doesn't exist today), explicitly flagged here rather than
  silently done or silently dropped.
- **`commit` excluded**, on the same precedent R18 and R11 already set: R18's own `scopes` list
  already omits `commit` and R11's `exempt_scopes_why` measured this repo's actual commit
  convention (median 71, p90 84, max 98 chars) to justify excluding `commit` from the imperative
  rule. Git's own 50/72 convention is a **deliberate** narrow wrap, not accidental debt, and a
  rule that "fixes" it toward 384 would fight a fifteen-year-old universal git norm this repo's
  own guard docstring already respects.
- **`pr` included** because it is prose meant to be read like a document (unlike a commit
  subject/body) and already carries R18/R11 in its scope list; it is the "and others" half of
  "also for commit and others" that survives scrutiny once `commit` itself is excluded for cause.

## Debt-pile decision (recommended)

Baseline it via the **existing, unmodified** shrink-only mechanism (`write_baseline`,
`baseline_additions`, `write_verdict`) -- the same one that already carries 3,222 findings across
the other 17 rules. This is technically routine at this scale; nothing new needs to be built for
it. It does NOT mean "fix them all inline this session" -- a 400-file, tens-of-thousands-of-
lines-changed reflow is its own reviewable PR (`check_prose_style.py reflow --write`, which
already exists and is markdown-only, matching R19's scope exactly), scheduled separately from the
detector landing so the diff that adds enforcement and the diff that rewrites the corpus can each
be reviewed on their own terms.

## Wiring summary (files touched)

- `.ci/rediacc_ci/quality/prose_style.py` -- factor `paragraphs()` out of `reflow_markdown`; add
  `underwrap_findings()`; extend `Rule.advisory`; call the new pass from `lint_text`/
  `lint_message`.
- `.ci/config/prose-style-rules.json` -- add the `R19` entry (`scopes: ["markdown", "pr"]`,
  `detection: "underwrap"`, one bad/good example pair).
- `.claude/rediacc_hooks/guards/block_prose_style_edit.py` -- no logic change; new `EDGE_CASES`
  entries in `test-block_prose_style_edit.py`.
- `.claude/rediacc_hooks/guards/block_prose_style_commit.py` -- no logic change; new
  `EDGE_CASES` entries in `test-block_prose_style_commit.py`.
- `.ci/config/prose-style-baseline.json` -- regenerated via `--write-baseline` once R19 lands,
  absorbing the measured markdown pile (expect low thousands under the banded heuristic, not the
  11,816 naive count).
- `.ci/rediacc_ci/tests/test_quality_prose_style.py` -- new `test_underwrap_*` cases mirroring
  `test_reflow_*`.

## Verification

```bash
# engine + guard selftest, must stay green before and after
python3 .ci/scripts/quality/check_prose_style.py --selftest
python3 .claude/rediacc_hooks/guards/test-block_prose_style_edit.py
python3 .claude/rediacc_hooks/guards/test-block_prose_style_commit.py

# real corpus sweep, dry run, before freezing
python3 .ci/scripts/quality/check_prose_style.py check --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['new']))"

# freeze the measured pile -- must show the ADDED-side refusal working (no accidental
# growth) and must be re-run any time the heuristic constants change
python3 .ci/scripts/quality/check_prose_style.py check --write-baseline

# full CI test module
pytest .ci/rediacc_ci/tests/test_quality_prose_style.py -q
```

### Critical files for implementation

- .ci/rediacc_ci/quality/prose_style.py
- .ci/config/prose-style-rules.json
- .claude/rediacc_hooks/guards/block_prose_style_edit.py
- .claude/rediacc_hooks/guards/block_prose_style_commit.py
- .ci/rediacc_ci/tests/test_quality_prose_style.py
- .ci/config/prose-style-baseline.json
</content>
