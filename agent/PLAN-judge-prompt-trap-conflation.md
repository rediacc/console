# PLAN: the stop-judge conflates a PAST trap example with a CURRENT finding
Status: done
Owner: d778be9d
Updated: 2026-09-17

Scope: `.claude/hooks/stop/wl_judge.py`, `wl_proofcheck.py`, `wl_classsweep.py`, `wl_reggate.py`, `wl_checks.py`, `wl_rules.py`, `worklist_messages.py`, `test-judge-schema.py`.

## The bug

Twice in one session the stop-judge fabricated a "PROOF OBLIGATION: a bulk mechanical transform landed with no verifiable proof attached" finding naming a change that does not exist anywhere in the working tree: first "Bulk reflow of 84 CI script files, already verified but uncommitted" (verified false: `git status`/`git diff --stat` showed no such files), then "Bulk prose-style
reflow applied uniformly to markdown files in plans/ directory" plus "A directory is excluded from the prose-style corpus scope" (verified false: no `plans/` directory exists in this repo, and the judge's own specified sibling-search grep found zero hits).

## Root cause, confirmed with a literal citation

`wl_proofcheck.py:83` (`PROOF_PROMPT`) quotes a worked example from the real 884-file/838-banner incident ("884 files changed, +200/-38000... an AST-equality proof ALSO attached and ALSO passing") directly into the LIVE prompt text sent to the judge on every fix-stop, with no typographic or semantic fence separating "here is a hypothetical" from "here is what to look for in the
message below." Hallucination #1 is a near-exact paraphrase of this example (same magnitude shape, same "already verified"/"proof attached" framing). Hallucination #2's specifics were not found verbatim in TRAPS.md, `wl_proofcheck.py`, or `wl_classsweep.py` -- the model generalized the same failure SHAPE ("a bulk transform with a suspicious exclusion") on its own once shown that
shape is a rewarded finding, rather than reusing stored content.

A second, structurally identical gap to one already fixed this session (the reserved-instruction bypass in `wl_classsweep.validate_search`): nothing in the judge pipeline checks that a fired finding's CLAIM FIELDS (`scope`, `defect_class`, etc.) correspond to the actual diff being evaluated -- only that a follow-up command built from those fields parses and names real paths.

The repo's own failure-direction contract for these two objects is explicit and must be preserved exactly: `wl_classsweep.py:34` / `wl_proofcheck.py:13-14` -- both NEVER fail closed, and any new check here may only ever make a fired finding more legible about its own uncertainty, never suppress it.

## Design

### 1. Ground the prompt in a real, computed file list (primary fix)

Add `wl_reggate.fixset_files(root, ids)` (extracted from the duplicated diff-tree-with-root-fallback logic already at `wl_reggate.py:293-320` and `:365-368` -- itself its own small class-sweep): returns the real files a fix-set's commit ids touched via `git diff-tree`, falling back to `git status --porcelain` for a tick-based (uncommitted) fix-set, since a tick id is not a
tree-ish. In `wl_checks.py`, compute `reg_fixset_files` beside the existing `reg_scripts` line and pass it into `wl_judge.run_judge(..., fixset_files=reg_fixset_files)` unconditionally (one cheap git call) so a follow-up question is grounded too, not just a fresh fire.

In `wl_judge.py`, thread `fixset_files=None` through `run_judge`, and when set, inject a new `M.FIXSET_GROUND_TRUTH` block (real file list, capped at 40 + a remainder count) into the prompt right before `sweep_extra`/`proof_extra`, telling the judge explicitly: the class_sweep and proof_obligation questions are ONLY about this list and the message below; a finding naming a file
count, directory or scope NOT in this list is either a misreading of the historical traps note (which is history, not a report on this stop) or an invention, and must not be reported as fresh either way.

### 2. De-fang the specific magic number and sharpen history vs. current

Replace `wl_proofcheck.py:83-87`'s "884 files... proof ALSO attached" worked example with an abstracted version carrying no copy-pasteable magnitude, redirecting the judge to the injected ground truth instead. Add one anchoring sentence each to `wl_proofcheck.py`'s "(1) APPLICABLE" paragraph and `wl_classsweep.py`'s `SWEEP_PROMPT` opening, tying "applicable" to the real fix-set
(for sweep: to the triggering FIX, not the search target, since a sweep legitimately searches outside the touched files by design). Append one paragraph to `worklist_messages.py`'s `JUDGE_PROMPT` traps section: these are PAST, already-fixed incidents, never a report about this stop; never restate one's file count, directory or scope as a new finding unless the message itself quotes
or clearly implies it.

These are wording-only changes to constants the existing 399 controls compare by identity/equality to the live constant (not by parsing the body), so none of Parts 2/3 in `test-judge-schema.py` need touching for this part, provided `PROOF_MARKER`/`SWEEP_MARKER` and the existing `%()s` placeholders stay intact.

### 3. Deterministic grounding check -- annotate, never suppress (defense in depth)

Add `wl_rules.scope_grounded(text, fixset_files)`: `fixset_files is None` (computation unavailable) always reads `True` (never accuse of ungrounded on missing data); an empty, successfully-computed list reads `False` for any non-empty text; otherwise checks whether `text` names a real path or path segment from the list. In `wl_proofcheck.enforce`/`wl_classsweep.enforce`, when a
verdict already fired, append an "UNVERIFIED: git's own file list does not match '...'" sentence to `reason` when `scope_grounded` fails against `payload["scope"]`/`payload["defect_class"]` -- appended to `reason`, never used to flip the verdict. Thread `fixset_files=None` through `apply_verdict` so every existing call site (which does not know the parameter) behaves
byte-identically to today.

## Verification plan

Existing: all of `test-judge-schema.py` Parts 2/3 must still pass unmodified (they exercise the `fixset_files=None` no-op path). New: `scope_grounded` unit controls (real path -> True, `plans/` against an unrelated real list -> False, `None` -> always True, `[]` -> always False); a `PF.enforce`/`CS.enforce` control asserting `"UNVERIFIED"` appears in `reason` on a mismatched
scope and does NOT appear on a matching one, with the verdict/action unchanged either way; two controls replaying the literal repro shape of both this session's hallucinations; a `wl_reggate.fixset_files` control against a throwaway git fixture (commit sha -> its real diff-tree list, non-existent/tick id -> `git status --porcelain` fallback, clean repo -> `[]`).

Not attempted: reproducing either hallucination live against the real model (non-deterministic, costs real money per call, and a CI gate cannot depend on a flaky paid sample). The hermetic tests above pin the mechanism instead.

## Tasks

- [x] Add `wl_reggate._diff_tree_files`/`fixset_files`, refactor `gate_only_fixset` to use it
- [x] Compute and pass `fixset_files` through `wl_checks.py` -> `wl_judge.run_judge`
- [x] Add `M.FIXSET_GROUND_TRUTH`, inject into the judge prompt when `fixset_files is not None`
- [x] De-fang `wl_proofcheck.PROOF_PROMPT`'s magic-number example; add the anchoring sentences to `wl_proofcheck`/`wl_classsweep`/`JUDGE_PROMPT`
- [x] Add `wl_rules.scope_grounded`; wire the UNVERIFIED annotation into `wl_proofcheck.enforce`/`wl_classsweep.enforce` via a new optional `fixset_files` parameter on `apply_verdict`, defaulting to `None`
- [x] New hermetic tests: `scope_grounded` unit controls, enforce-with-grounding controls (both hallucination replays), `fixset_files` git-fixture controls
- [x] Run the full `test-judge-schema.py` suite (399 existing) unmodified, plus new controls, all green
- [x] Commit, `PR-TASK: e87fa3ce`, evidence into worklist `544eab1e`
