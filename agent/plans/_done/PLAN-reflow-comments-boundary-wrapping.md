# PLAN: fold a docstring's opening/closing physical line into reflow correctly
Status: done
First-Seen: 2026-09-20
Owner: d778be9d
Updated: 2026-09-17

Scope: `.ci/rediacc_ci/quality/prose_style.py`, `.ci/rediacc_ci/tests/test_quality_prose_style.py`.

## The bug

`_python_reflow_lines` (`prose_style.py:1415-1454`) unconditionally excludes a docstring's first and last physical line from ever joining a reflowed paragraph. The reasoning stated there is correct only when that physical line is just the delimiter (`"""` alone on its own line). It is wrong whenever real prose shares the physical line with the delimiter, e.g. `"""Lead sentence.` on
line one -- a shape this repository's own docstring convention uses on every multi-line docstring. `reflow_comments` (`prose_style.py:1561-1571`) emits an excluded line via `out.append(raw)`, completely unchanged, so such a line stays unfoldable when short and unwrappable when long, even past width. Worked around this session by hand (giving affected docstrings a short/empty lead
line); root cause untouched until this plan.

## Design (from the Plan agent's report, verified against the tree)

1. **Delimiter vs. prose, precisely.** Match the opening delimiter against the whole STRING token text with `_DOCSTRING_OPEN = re.compile(r'^[rRbBuUfF]{0,2}(\'\'\'|"""|\'|")')`. `open_delim` (the full match) stays pinned to the reconstructed paragraph's first output line; everything after it on that physical line is foldable prose, unless blank, a structural stop
(`_is_structural_comment_line`), or ending in an odd backslash run (a real line-continuation escape -- found live at `.ci/rediacc_ci/deploy/promote_r2_to_stable_hotfix.py:248`). The closing line is symmetric: `close_delim = quote` (the matched quote run), `close_prose = body_lines[last][: -len(quote)]`, gated by the same rules interior lines already get (flush-margin check
included, since a closing line's own indentation carries meaning an opening line's does not). A one-line docstring (`last == 0`) stays explicitly out of scope (see "What cannot be fixed").

2. **Gluing, not text injection.** `open_delim`/`close_delim` never join the wrapped TEXT `_join_and_wrap` sees; they attach to the finished first/last output line afterward. Two measured hazards drive the gluing rule: width -- reserve `len(open_delim or "") + len(close_delim or "") + (1 if close_delim else 0)` off the wrap width before wrapping, summed rather than
`max()`-ed, since a short paragraph can collapse to one line carrying both delimiters at once and `max()` under-reserved that case, producing a 386-char line against a 384 budget on `test_housekeeping_cleanup_github_deployments.py:332`; and adjacency -- gluing `close_delim` straight onto a wrapped line ending in the same quote character, or in an odd trailing-backslash run,
produces an unterminated string (`""""`/`\"""`, confirmed with `ast.parse`), a real tracked shape at `test_autopilot_post_escalation.py:332-335`, fixed by inserting one space first when that condition holds. `open_delim` needs no such guard, since prepending a delimiter never creates lexical ambiguity.

3. **Plumbing.** `_python_reflow_lines`'s per-entry tuple grows a 4th field `(open_delim, close_delim)`, both `None` for a comment or an ordinary interior docstring line. `_cstyle_reflow_lines` gets the same 4-tuple shape (always `(None, None)`) for parity, with no behavior change. `comment_segments` threads `buf_open`/`buf_close` through its paragraph buffer and
yields two extra trailing fields on every `"para"` item (both `yield` sites, `prose_style.py:1505` and `1532`). Both consumers of that shape -- `reflow_comments` and `underwrap_findings` (`prose_style.py:996-1006`, the R19 sibling `comment_segments`'s own docstring already demands stay on one boundary logic) -- unpack and use the two new fields for their own width-budget math.

## Measurement (run before writing the patch)

Across all 1,057 tracked `.py` files: 9,990 docstrings, 2,879 one-line (out of scope), 7,111 multi-line. All 7,111 have prose sharing the opening line; 2,278 across 406 files would actually gain an opening-side fold (the next line already eligible, no blank separator); 1,053 across 229 files on the closing side; 1,009 both. Zero open/close lines currently exceed width 384 alone.
Exactly one tracked line ends in an odd backslash run (`promote_r2_to_stable_hotfix.py:248`) -- the guard must exclude it, byte-identical after the fix. Zero non-triple-quoted docstrings exist in the corpus (the path is exercised generically, not specially carved out, and carries no live proof).

## Tasks

- [x] Add `_DOCSTRING_OPEN`, `_ends_in_odd_backslash_run`, `_delimiter_reserve`, `_glue_delimiters` to `prose_style.py`
- [x] Rewrite `_python_reflow_lines` for the 4-tuple shape and the opening/closing-line eligibility rules above; widen `_cstyle_reflow_lines`'s tuple for parity
- [x] Thread the 4-tuple through `comment_segments` (both `yield "para"` sites) and update its own docstring
- [x] Update `reflow_comments` and `underwrap_findings` to reserve width and glue delimiters
- [x] Correct the now-narrower claims in `_python_reflow_lines`'s and `reflow_comments`'s own docstrings (excluded only when the line carries no prose alongside its delimiter)
- [x] The one existing hermetic fixture needed NO expected-value change, a deviation from the design: the closing-line-tail guard found and added during implementation (see Outcome) excludes exactly that fixture's shape, so it keeps reading its ORIGINAL expected value rather than a new one
- [x] Add six new hermetic tests (five from the design plus one pinning the closing-line-tail guard itself, found during implementation)
- [x] Verify: `pytest test_quality_prose_style.py` full pass (231), `selftest()` full pass (82), a corpus-wide docstring-normalized AST-equality + idempotency + zero-new-overwidth-line sweep across all 1,057 tracked `.py` files (same shape as `469faae58`'s proof), and `shape_cluster_diff.py` before/after on every changed file: zero new clusters of the seven previously-fixed shapes
- [x] Commit `d43cd6212`, `PR-TASK: e87fa3ce`, evidence into worklist `24e4b91d`

## Outcome

One real deviation from the design, found during implementation rather than anticipated by it: the closing physical line's own STRING-token text never includes a trailing token after the quote (a real comment sharing that line, `"""D""" # note`), so gluing `close_delim` back on from parts alone silently DROPPED it -- caught by the design's own predicted fixture (the pre-existing "a
trailing comment on a docstring's closing line is never joined" test) going red on the first implementation pass, not by a new test written in advance. Fixed by reading the raw source line and excluding a closing line whose tail (beyond where the string token ends) is non-blank, falling back to the pre-fix, safe, unchanged behavior for exactly that shape. A new hermetic test pins
the guard itself so this cannot regress silently a second time.

Applying the corpus-wide reflow (644 files) also surfaced 15 pre-existing `you`/`I`/`my`/`mine`/`yours` prose-style violations across 14 files unrelated to this fix, invisible to the gate only because they sat on lines this reflow's line-shifting then moved into view. Fixed inline (reworded, meaning preserved) rather than re-baselined, per the same commit.

## What cannot be fixed safely

A one-line docstring whose single physical line exceeds width: shortening it means relocating the opening `"""` onto its own line, a strictly bigger transform than a fold (it changes where the string literal starts, not just how its interior wraps) and outside this bug's own invariant. Zero occurrences exist in this corpus today, so the gap stays explicitly out of scope rather than
silently widened into the patch.

Non-triple-quoted multi-line docstrings: handled by the same generic code path but exercised by zero real tracked files -- the design covers the shape, but it carries no corpus proof behind it.
