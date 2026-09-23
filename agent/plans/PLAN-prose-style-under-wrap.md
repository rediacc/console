# PLAN: prose-style under-wrap detection (R19)

Status: mostly-done -- 9 of 12 boxes verified done 2026-09-22 (R19 shipped, wired, baselined at 62 findings).
Genuinely open: the EDGE_CASES regression tests for block_prose_style_edit.py and test_underwrap_* for test_quality_prose_style.py (behavior independently verified correct, but unasserted).
The "do not bulk-fix inline" decision box was reversed same-day by explicit operator instruction (commits 05b753df3, 6fb8849f9 bulk-reflowed the whole repo) -- left open rather than ticked, since the box's own instruction was not the thing that happened.
First-Seen: 2026-09-17
Owner: d778be9d

## Why

The operator read fresh comment-block prose this session wrote inside `prose_style.py` / `block_prose_style_commit.py`, hard-wrapped at ~70-90 characters deep inside the 384-char R18 budget, and asked for three things: (1) sweep the tree for the same pattern and fix it, (2) extend that sweep to commit/PR messages ("also for commit and others"), (3) make `block_prose_style_edit.py`
(and the commit guard) **block** a newly-introduced under-wrapped paragraph rather than merely report it as debt.

This document designs that detector, decides its scope against measured numbers (not guesses), and lays out the wiring -- without implementing anything.

## Do not regress

This session's tree already carries three uncommitted, review-found fixes in the same two files this plan touches (`git diff .claude/rediacc_hooks/guards/block_prose_style_commit.py .ci/rediacc_ci/quality/prose_style.py`):

1. `GIT_COMMIT`/`GH_PR` gained `re.MULTILINE` (a `git commit` on line 2 of a multi-line command
was invisible to `^`).
2. `_is_docstring()` now steps past `tokenize.NL` (not just `tokenize.COMMENT`) so an
implicitly-concatenated string fragment (the `PERMISSION` regex tuple in `block_secret_exposure.py`) is not misread as a docstring.
3. `block_prose_style_commit.py`'s `scope` is now computed per-message via `_scope_for(label)` /
`PR_LABELS`, not once per whole chained command.

`test-block_prose_style_commit.py` is 27/27 green against these, and the baseline has already been drained from 3597 to 3222 findings (375 false positives removed by fix #2, verified by measuring `worklist_messages.py` alone: 1028 implicit string-concatenation boundaries). Any change here must run that suite (and the engine's own `--selftest`) before and after, and must not touch
`_is_docstring`, `_scope_for`, or the `GIT_COMMIT`/`GH_PR` regexes.

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

`pyproject.toml` disables `E501` ("owned by the formatter"), and `ruff format` does not touch comment text. `eslint.config.js` has no `max-len` rule either. The ~80-100 col comment convention is habit and readability, not a tool-enforced ceiling.

**Conclusion the plan is built on:** a literal "would this still fit if joined" test is not a debt detector in this tree -- it is a description of how essentially all existing prose is written. R18's 384 is a ceiling meant to catch a pathological unwrapped wall of text, not a target width authors are expected to fill. Any rule built on the literal test will fire on almost every
future normal edit unless it is scoped very narrowly and its existing-corpus hits are frozen at real scale (thousands, not dozens).

## Tasks

- [x] Confirm with the operator, before writing code, the scope and blast-radius decisions.
      DONE 2026-09-17: operator answered "we go all in all but in a smarter way -- investigate
      the existing formatting tools" -- scope is now `["markdown", "pr", "comment"]`, and the
      tooling investigation above replaced the hand-rolled-heuristic guesswork with an evidenced
      conclusion (no external tool does under-wrap detection; `textwrap` stays the shared
      wrapping primitive, matching what `reflow_markdown` already uses).
- [x] Factor `reflow_markdown`'s paragraph-buffering loop (fence/frontmatter/list-item/
    (ticked) 2026-09-22T19:57:53Z by d778be9d: markdown_segments(text) at .ci/rediacc_ci/quality/prose_style.py:1001, consumed by both reflow_markdown:1159 and underwrap_findings:1120, landed in 527fc9ad7
      REFLOW_STOP handling) out of the function body into a reusable `paragraphs(text)`
      generator yielding `(start_lineno, list[str])`, used by both `reflow_markdown` (unchanged
      behavior, `test_reflow*` must stay green) and the new detector. This is the "reuse, don't
      reinvent join-feasibility" requirement.
- [x] Add `R19` to `.ci/config/prose-style-rules.json`: `detection: "underwrap"`,
    (ticked) 2026-09-22T19:57:53Z by d778be9d: .ci/config/prose-style-rules.json:883-915, R19 detection:underwrap, scopes widened to markdown/comment/pr/commit past this box's original spec, verified live via .claude/rediacc_hooks/guards/test-block_prose_style_commit.py:36-38,97-98
      `scopes: ["markdown", "pr"]` (see Scope decision -- deliberately excludes `comment` and
      `commit`), no `patterns`, one `good` example (a normally-wrapped short paragraph) and one
      `bad` example (a 3+ line uniformly-narrow paragraph, embedded as a `\n`-joined JSON
      string, matching how `R18`/reflow tests embed multi-line fixtures).
- [x] Extend `Rule.advisory` in `prose_style.py`: `return not self.raw_patterns and
    (ticked) 2026-09-22T19:57:53Z by d778be9d: .ci/rediacc_ci/quality/prose_style.py:130 exact match: return not self.raw_patterns and self.detection not in (measured, underwrap)
      self.detection not in ("measured", "underwrap")` -- otherwise R19 is reported as
      advisory/undetected and the `_shape()`/`sync` output lies about it.
- [x] Add `underwrap_findings(text, rule, scope, max_len)` in `prose_style.py`: runs
    (ticked) 2026-09-22T19:57:53Z by d778be9d: .ci/rediacc_ci/quality/prose_style.py:1112 underwrap_findings(path, text, rule, scope, max_len), one Finding per paragraph
      `paragraphs(text)`, applies the heuristic gate (below), and for each qualifying paragraph
      emits **one** `Finding` anchored at the paragraph's first line, with `Finding.text` = the
      whole paragraph joined by `\n` (so a rewrite of any line inside it re-keys the baseline
      entry, matching the documented "a rewrite is exactly when a human should look again"
      contract).
- [x] Wire it into `lint_text` and `lint_message`: both currently loop `for line in lines:
    (ticked) 2026-09-22T19:57:54Z by d778be9d: .ci/rediacc_ci/quality/prose_style.py:853-856 lint_text and :873-876 lint_message, both guarded by rule.detection == underwrap
      lint_line(...)`, which has no cross-line context. Add a second pass,
      `findings.extend(underwrap_findings(...))` for the R19 rule if it applies to the scope,
      run once per document/message rather than per extracted `Line`.
- [x] Decide and implement the heuristic gate (see Detection algorithm) as a named, tested
    (ticked) 2026-09-22T19:57:54Z by d778be9d: _looks_hard_wrapped(buffer, width) at .ci/rediacc_ci/quality/prose_style.py:1082, live-tested against must-not-fire list, all correct
      function so it is not duplicated a third time.
- [ ] Wire `block_prose_style_edit.py`: no code change needed beyond what already exists -- it
      already calls `engine.lint_text(rel, new_prose, rules, globals_, scope=scope)` and already
      treats any `finding.fid` present in `load_baseline(root)` as carried/allowed. R19 rides the
      same mechanism automatically once wired into `lint_text`. Add `EDGE_CASES` to
      `test-block_prose_style_edit.py`: (a) a fresh multi-line under-wrapped paragraph in a
      `Write`/`content` block; (b) the same paragraph rewritten at full width passes; (c) a
      single-line `Edit.new_string` with no sibling context is NOT flagged (documented
      limitation, see below) -- must be asserted, not just hoped for.
- [x] Wire `block_prose_style_commit.py`: same, no structural change --
    (ticked) 2026-09-22T19:57:54Z by d778be9d: .claude/rediacc_hooks/guards/test-block_prose_style_commit.py:36-38,97-98 add R19 heredoc case, guard suite passes 35/35
      `lint_message(text, rules, globals_, _scope_for(label))` already exists; R19 applies only
      when `_scope_for(label) == "pr"` (title/body/body-file), never for `"commit"` labels,
      because R19's scopes list omits `commit`. Add `EDGE_CASES` to
      `test-block_prose_style_commit.py` mirroring the edit-guard cases, scoped to
      `gh pr create --body`.
- [x] Run the tree-wide `check` once R19 is loaded, measure the real finding count (expect low
    (ticked) 2026-09-22T19:57:54Z by d778be9d: prose-style-baseline.json by_rule.R19=62 (far below original 13328 estimate, since the bulk-reflow already ran)
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
- [x] Fix only the two files the operator actually pointed at (`prose_style.py`,
    (ticked) 2026-09-22T19:57:54Z by d778be9d: verified: re.MULTILINE on GIT_COMMIT/GH_PR .claude/rediacc_hooks/guards/block_prose_style_commit.py:70-75, _is_docstring stepping past tokenize.NL .ci/rediacc_ci/quality/prose_style.py:477,485, both committed at HEAD, git diff empty
      `block_prose_style_commit.py`) by hand this session if the operator still wants that after
      seeing the scope numbers, since two files is a small, safe, human-reviewable diff, unlike
      the 400-file tree-wide reflow. (Already done live this session, ahead of this plan: both
      files' new comment blocks were rewrapped toward the 384 limit and re-verified green.)

## Detection algorithm

**Tooling investigation (2026-09-17), evidence not assumption.** The operator asked, on seeing the naive-test numbers, to find and use an EXISTING, documented formatting tool as the join/reflow engine rather than inventing one. Every candidate with a plausible fit was checked against its own official docs, or its own repository's stated scope where no hosted doc site exists.
Results, one line each:

| Tool | Scope checked | Verdict |
|---|---|---|
| Prettier `proseWrap: "always"` | markdown | Genuinely reflows existing narrow paragraphs to `printWidth` (confirmed from prettier.io's own worked example). Not present anywhere in this repo today; adopting it means a new, large npm dependency under `.npmrc`'s supply-chain hardening. |
| remark-lint | markdown | Has a "too long" rule (`remark-lint-maximum-line-length`). No rule anywhere in its catalogue for "too narrow". Same gap this plan fills, not a tool that fills it. |
| remark-stringify | markdown | 16 documented stringify options, none a fill/wrap-width control. Prettier's reflow is Prettier's own printer over an AST, not something remark exposes as a reusable primitive. |
| mdformat | markdown | `wrap` defaults to `"keep"` (no-op); an explicit width does reflow, but GFM tables need a separate plugin this repo's own `reflow_markdown` already handles natively. New Python dependency; this host has no `pip`/`pip3` at all, only `uv`. |
| `ruff format` | comment | Its own docs (docs.astral.sh/ruff/formatter) document no comment-reflow behavior at all. |
| `docformatter` | comment | README scopes it explicitly to PEP 257 docstrings. No bare `#`/`//` comment prose handling. |
| `clang-format` `ReflowComments` | comment | Real feature, but its documented language list excludes Python and Go -- the two languages dominating this repo's comment scope. |
| `gofmt` / `gofumpt` | comment | Official docs describe only indentation/alignment/rewrite rules. No comment-text reflow documented. |
| Python stdlib `textwrap.wrap`/`fill` | both | **Already the wrapping primitive `reflow_markdown` uses today** (`prose_style.py`'s `flush()` closure). No new dependency; already imported and exercised by `test_reflow*`. |

**Conclusion.** For markdown, no external tool changes the outcome that matters: the near-100% naive-fire rate is a property of the CORPUS (virtually every paragraph, once joined, still fits under 384 chars), not an artifact of which program performs the join -- Prettier, mdformat and this repo's own `textwrap`-based `reflow_markdown` all answer "yes, joinable" on the same set of
paragraphs. This is a STATED adoption of "use an existing tool's algorithm as the wrapping primitive, keep this repo's own paragraph-boundary logic" -- and explicitly the reason not to add Prettier or mdformat as dependencies: doing so swaps a working, dependency-free stdlib primitive for a heavier one producing the same verdict on the same inputs.

For comment scope (now IN, per "all in"), no full external tool reflows `#`/`//` comment prose at all -- confirmed absence across ruff, docformatter, clang-format and gofmt/gofumpt, each from its own documentation. The same reuse pattern applies, newly built for the boundary logic (nothing to factor out, since no comment-scope reflow exists today): a new `comment_paragraphs(lines)`
function, fed the SAME `Line` objects `extract()`/`python_comment_lines`/`cstyle_comment_lines` already produce for R1-R18, grouping contiguous same-indent, same-marker comment lines into buffers (a blank comment line, a code line, an indent change, or a docstring/comment-kind change ends a buffer), then reusing `textwrap.wrap` on the buffer exactly as `reflow_markdown`'s `flush()`
does.

**The heuristic gate itself does not change, and this is now an evidenced decision, not a fallback.** None of the nine tools/ecosystems surveyed documents any concept of "this prose is artificially narrow relative to its ceiling" -- every one does either too-long detection or unconditional reflow-on-request, never "is this narrow-wrap accidental." The gate from the original draft
is kept, applied identically to both `markdown` and `comment` buffers now that both are produced by a `paragraphs()`-shaped function:

- the paragraph has **3 or more lines** (a 2-line paragraph almost always just ends there -- a
short final line is not evidence of hard-wrap, it's evidence of a sentence ending);
- **all lines except the last** sit within a narrow width band of each other (candidate: 20
characters) -- the fixed-column-wrap signature, as opposed to natural variation in sentence length;
- that common width is well under the limit (candidate: <= 40% of `max_line_length`, i.e. <=154
chars) -- a paragraph already wrapped near 300+ chars is not under-wrapped even if one more word would technically fit;
- the shared reflow primitive (`textwrap.wrap` via `reflow_markdown` for markdown, the same call
directly for comment buffers) actually produces fewer lines when applied to the buffer.

**Must NOT fire (false-positive list, verified against the extractors):**
- the **last line** of a paragraph (a paragraph is expected to end short; `reflow_markdown`'s own
`flush()` treats the whole run, not each line, as the unit -- a solo-line finding on the terminal line would flag every paragraph in the tree by definition);
- a **list item** or its wrapped continuation (`LIST_ITEM.match`, already a `REFLOW_STOP` --
`reflow_markdown`'s own controls (`test_reflow`) already assert lists are untouched; the new detector must reuse the identical `paragraphs()` boundaries so it inherits this for free rather than re-deciding it);
- a line immediately before a **heading, fence, table, blockquote, link definition, or indented
code** (same `REFLOW_STOP` set -- a line ending right before a structural boundary is a deliberate break, not an accident);
- a **single-line "paragraph"** with no line 2 in the same buffer -- nothing to join;
- a paragraph whose next line's first word genuinely would not fit under the width -- this is
correctly wrapped, not under-wrapped, and the `reflow_markdown` comparison already excludes it because the join-then-rewrap would reproduce the same break;
- (edit-time only) a single-line `Edit.new_string` payload with no sibling lines in the same tool
call -- `lint_text`/`lint_message` only ever see the bytes handed to them ("ONLY THE NEW PROSE", per `block_prose_style_edit.py`'s own header), so a paragraph split across several sequential single-line `Edit` calls is structurally invisible to this check one edit at a time. This must be documented as a known gap, not silently accepted as full coverage: R19 at edit time reliably
catches a multi-line paragraph authored in **one** `Write`/multi-line `Edit`/`MultiEdit` call (which covers the operator's actual triggering case -- the comment block was written in one shot), not one assembled a line at a time.

## Scope decision (operator-confirmed: "we go all in")

`R19` scopes: **`["markdown", "pr", "comment"]`**. Still excludes `commit`.

- **`comment` now INCLUDED**, reversing the earlier default recommendation, per the operator's
explicit "we go all in ... in a smarter way" instruction. The scale concern that justified exclusion before (94,201 naive pairs) does not disappear, but it was measured with the wrong instrument: a naive adjacent-line-pair join test, not the same banded heuristic gating markdown. Re-measured with the real gate (see Debt-pile decision): 6,100 paragraphs across 1,416 of 2,149
comment-bearing files -- large, but a real, boundable pile the shrink-only baseline mechanism already knows how to carry, not an unbounded one.
- **`commit` stays excluded**, unchanged rationale: R18's own `scopes` list already omits
`commit`, and R11's `exempt_scopes_why` measured this repo's actual commit convention (median 71, p90 84, max 98 chars) to justify the same exclusion for the imperative rule. Git's own 50/72 convention is a deliberate narrow wrap, not accidental debt.
- **`pr` included**, unchanged rationale: prose meant to be read like a document, already carries
R18/R11 in its scope list.

## Debt-pile decision (measured, not naive)

Baseline it via the **existing, unmodified** shrink-only mechanism (`write_baseline`, `baseline_additions`, `write_verdict`) -- the same one that already carries 3,222 findings across the other 17 rules. The size estimate is now real for BOTH scopes, using the banded heuristic (not the naive join test) as the actual detector would compute it:

| Scope | Real (banded) count | Files | Naive count (comparison only, NOT what gets baselined) |
|---|---|---|---|
| `markdown` | 7,228 paragraphs | 371/436 | 11,816 paragraphs |
| `comment` | 6,100 paragraphs | 1,416/2,149 | 96,913 adjacent pairs (corroborates the earlier 94,201 order of magnitude) |
| **Combined R19 baseline at landing** | **~13,328 findings** | -- | -- |

This is larger than the sum of every other rule's current baseline (3,222 findings, R1-R18 combined) -- stated plainly, not softened, now that `comment` scope is included. It is still mechanically the same shrink-only baseline; nothing new needs to be built to carry it. It does NOT mean bulk-fixing 13,328 paragraphs inline this session -- markdown's bulk fix already has an
instrument (`check_prose_style.py reflow --write`); comment scope has NO bulk-reflow instrument yet (this plan adds detection, not an auto-fixer for comments), so the comment-scope pile rides the baseline as debt with no scheduled bulk-fix PR until one is separately planned.

## Wiring summary (files touched)

- `.ci/rediacc_ci/quality/prose_style.py` -- factor `paragraphs()` out of `reflow_markdown`; add
`underwrap_findings()`; extend `Rule.advisory`; call the new pass from `lint_text`/ `lint_message`.
- `.ci/config/prose-style-rules.json` -- add the `R19` entry (`scopes: ["markdown", "pr"]`,
`detection: "underwrap"`, one bad/good example pair).
- `.claude/rediacc_hooks/guards/block_prose_style_edit.py` -- no logic change; new `EDGE_CASES`
entries in `test-block_prose_style_edit.py`.
- `.claude/rediacc_hooks/guards/block_prose_style_commit.py` -- no logic change; new
`EDGE_CASES` entries in `test-block_prose_style_commit.py`.
- `.ci/config/prose-style-baseline.json` -- regenerated via `--write-baseline` once R19 lands,
absorbing the measured pile (~13,328 findings across markdown + comment, per the Debt-pile decision above, not the much larger naive counts).
- `.ci/rediacc_ci/tests/test_quality_prose_style.py` -- new `test_underwrap_*` cases mirroring
`test_reflow_*`.
- `.ci/rediacc_ci/quality/prose_style.py` -- also add `comment_paragraphs(lines)`, mirroring the
factored-out `paragraphs(text)` but consuming the `Line` objects `extract()` already produces for comment-scope files, so `underwrap_findings()` can run against BOTH markdown text and comment-scope `Line` lists via one shared gate function.

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
