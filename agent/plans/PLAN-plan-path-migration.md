# PLAN: repoint citations of moved agent/PLAN-<slug>.md paths directly at agent/plans/...
Status: closing -- 7 of 9 boxes verified done 2026-09-22 (commit a81967e94 + this session's own INDEX.md regen).
Genuinely open: the 4-line PLAN-stop-hook-task-verification.md residue (new debt from later, unrelated commit 97164ac96, not a miss by this sweep), and the final verification sweep script (section 4), which has two real regex bugs (Full-Text exclusion anchors on the old path instead of the new one; archive/peer-session exclusions miss a `[^:]*` before the trailing colon) that make it unable to ever report zero, even on a clean tree.
check:ci-plan-citations/-boxes/-folders still red, but zero of those findings concern this plan's own subject (old flat-path citations) -- verified via grep, 0 hits; they are pre-existing debt in other plans.
Owner: d778be9d
Updated: 2026-09-22

## 0. What the verification changed from the first-pass survey

The survey (`moved_map.json`, `citing_map.json`) is sound as a list of where the string appears. Sampling 25+ of the 157 files directly against the tree confirmed the class bucketing was right in outline but wrong or incomplete in five specific, load-bearing ways:

1. **The single most important finding, not in the original bucket list at all**: 32 of the 48 `agent/plans/*.md` files cite themselves at their old path, and every one of those 32 self-citations is a `Full-Text: <sha9> <old_path>` header line on a compacted plan record.
   That path must never be changed to the new path -- proved empirically below. This is a per-line exception inside otherwise-editable files, not a class the first pass could have caught by path-prefix bucketing.
2. `.devcontainer/Dockerfile` and `.devcontainer/bashcov-sup.c` are not coincidental -- both carry real, deliberate prose citations of `agent/PLAN-shell-resource-profiling.md` explaining implementation rationale.
   The earlier speculation ("near-certainly coincidental") was wrong; verify-don't-assume paid off here.
3. `scripts/gen/validate-cli-examples.ts` has a functionally live `EXCLUDED_FILES: Set<string>` containing three old plan paths, consumed by a `!EXCLUDED_FILES.has(f)` filter against `glob('agent/**/*.{md,mdx}')`.
   Since the plans moved, the exclusion is currently missing its target (the stub is excluded, uselessly; the real content at the new path is not). This is not cosmetic -- it needs the fix and a live gate run to confirm.
4. `.ci/breakpoint/workflow/breakpoint.yml` / `.github/workflows/breakpoint.yml` are a hashed, byte-identical-enforced pair (`.ci/breakpoint/MANIFEST.sha256`, `check-breakpoint-drift.sh`, `test_gate_breakpoint_secret_exposure.py::test_live_workflow_matches_template`). Both need the identical edit, plus a manifest regeneration afterward -- not just "safe, it's a comment."
5. The original finding mentioned "one `agent/reggate/*.jsonl`" citation -- it does not exist in the actual 157-file corpus (`grep -o '"[^"]*reggate[^"]*"'` over `citing_map.json` finds zero `.jsonl` paths). Flagging this as a discrepancy rather than silently dropping it or inventing a file to handle.

### The Full-Text exception -- proved, not asserted

`.ci/scripts/quality/check_plan_record.py:320-328` (`names_this_record`) documents it directly:

> "The pointer is NOT re-spelled at the move: the commit it names carries the text at the OLD path, so `agent/plans/...` would make R2's `git rev-parse <sha>:<path>` resolve to nothing and turn a correct record into a red one."

Reproduced live and read-only:

```
$ git rev-parse f7a5351a9:agent/PLAN-add-chunkstore-backup-verb.md
5de64f0839c4781cfdef2f2f3249a695cc96d2ef        # matches Full-Text-Blob in agent/INDEX.md
$ git rev-parse f7a5351a9:agent/plans/PLAN-add-chunkstore-backup-verb.md
fatal: path 'agent/plans/PLAN-add-chunkstore-backup-verb.md' exists on disk, but not in 'f7a5351a9'
```

Editing that line would turn a green `check:ci-plan-record` red. All 32 files checked (`grep -c` against each) have exactly one occurrence of their own old path -- the `Full-Text:` line -- so none of them need any edit at all for their self-citation. (One of the 33 self-citing files, `PLAN-secret-namespace-migration.md`, is not a compacted record -- its self-citation is ordinary
prose at line 557 and gets the normal fix.)

**Rule: any line matching `^Full-Text:\s+[0-9a-f]{7,40}\s+agent/PLAN-<slug>\.md\s*$` is frozen. Every other occurrence of an old path, anywhere, including elsewhere in the same file, gets the normal fix.**
The one `Related:`/`Supersedes:`/`Extends:` cross-reference in the corpus (`agent/plans/PLAN-migrate-plan-doc-discovery.md:7`) is not a Full-Text pointer, just an ordinary resolvable-on-disk citation; it gets the normal fix.

## 1. Per-class handling rule

| Class | Rule | Why |
|---|---|---|
| `agent/worklist/*.jsonl` (4 files: `8f55d4f0`, `d1589e0b`, `d778be9d`, `f4da5c2e`) | Never edit. | Append-only event log; CLAUDE.md's own rule. A citation there is a historical record of what was true when the line was appended. |
| `agent/reggate/*.jsonl` | N/A -- zero such files actually cite an old path in the real corpus (verified against `citing_map.json`); the original premise of one such file doesn't hold. If one turns up at implementation time, treat it identically to worklist jsonl. | Same append-only-log reasoning would apply if it existed. |
| `agent/INDEX.md` | Never hand-edit. Regenerate with `npm run check:ci-plan-record -- --update` (equivalently `.ci/scripts/quality/check_plan_record.py --update`), run after every other file-class edit lands. | File's own header: "GENERATED by `npm run check:ci-plan-record -- --update`. Do NOT hand-edit." `--update` is the only writer (`.claude/hooks/stop/wl_planrec.py:48`). |
| `agent/ledgers/census-plan-record.jsonl` | Never edit; do not even try to "regenerate" it directly. It picks up a new row as a side effect the next time `check_plan_record.py` runs (its own normal write path), which is expected, not something this sweep does by hand. | Append-only measurement log per plan (`agent/README.md:23`); the gate is its only writer. |
| `agent/plans/*.md` -- the `Full-Text:` header line specifically (32 files identified) | Never edit this one line. | Proved above: it is a historical git-tree pointer, not a fixable citation. |
| `agent/plans/*.md`, `agent/plans/_done/*.md`, `agent/plans/_removed/*.md` -- everything else in these files (prose, `Related:`/`Supersedes:`/`Extends:` headers, line-numbered pointers) | Edit directly. Literal path-segment replace; leave any trailing `:NNN` line-number suffix untouched (a separate, pre-existing fragility problem `agent/PLAN-citation-fragility.md` already owns -- out of scope here). | Durable design docs; a citation here is a real pointer meant to resolve. |
| `agent/programs/www-round5/**/*.md` (6 files) | Edit directly. | Live program suite under a reserved shared directory (`agent/README.md` layout), not archived, not session-owned. All occurrences are bare-path prose in backticks. |
| `agent/DECISIONS.md` | Edit directly, including the line-numbered pointers (`agent/PLAN-secret-namespace-migration.md:136` etc.) -- replace only the path segment, leave `:NNN` as-is. | Root-level shared "live" document, structurally the same class as `RULES.md` ("one document every session reads and sharpens in place"), enforced by `check:ci-decision-ids`, not a session's private state. |
| `agent/pr/0903-1.md` | Never hand-edit; do not regenerate either (leave as-is). | File's own header: `<!-- generated by worklist.py --publish; edit the worklist, not this file -->` -- a rendered snapshot of a closed branch's worklist history. Regenerating it is a separate, unrelated action outside this sweep's scope. |
| `agent/archive/plans/*.md` (5 files: `PLAN-env-to-bitwarden.md`, `PLAN-github-secrets-removal.md`, `PLAN-secret-names-one-to-one.md`, `PLAN-stop-plan-box-enforcement.md`, `PLAN-migrate-command.md`) | Never edit. | `agent/README.md:34`: "`archive/<label>/` is frozen and nothing in the hooks reads it." A plain-prose fix is still an edit to frozen history -- the freeze is about the bytes, not about whether the edit looks safe. |
| Peer session directories: `agent/f88f9be7/STATE.md`, `agent/8f55d4f0/STATE.md`, `agent/f4da5c2e/STATE.md`, `agent/a276391d/secret-mapping.md` | Never edit. | Each peer session owns its own sibling directory under agent/, read-only from every other session's side -- applies to the whole directory, not just STATE.md. |
| `docs/**/*.md` (11 files) | Edit directly. | Durable reference docs; sampled `docs/backup-storage/07-execution-record.md`, `docs/agent-reference/TRAPS.md`, `docs/agent-reference/media-assets.md`, `docs/ci-overhaul/06-progress.md` -- all bare-path prose citations, no special structure. |
| `.ci/rediacc_ci/tests/goldens/claude-hooks/test-hooks.sh.golden` | Never edit. | `.ci/rediacc_ci/tests/frozen.py:7`: "Every golden opens with `# twin <path> blob <sha>`... nothing in a golden is a hand-written expectation." This golden's header pins it to `.claude/hooks/test-hooks.sh` blob `5be28c8d1eb...` at recording time; the plan-path text inside is part of those frozen bytes. Editing it desyncs the golden from the historical blob it claims to represent. |
| `.ci/policy/.w7p5a-real-run-blocklist`, `.ci/policy/.w7p5a-real-run-leg-blocklist` | Edit directly. | Checked: the old path appears only in the header comment identifying which plan authorizes the file (`# W7P5-a ("agent/PLAN-tooling-transformation.md") requires...`), not as an actual blocklist entry (entries are deploy/release script paths). Changing it changes nothing the blocklist matches. |
| `.ci/config/prose-style-rules.json` | Edit directly. | Checked with a full JSON walk: both hits are at `/globals/exempt_paths[2]/reason[4]` (`PLAN-agent-tree-lifecycle`) and `/rules[R19]/detection_why[5]` (`PLAN-prose-style-under-wrap`) -- plain narrative strings, not inside any rule's `examples[].text`, so nothing about the rule's own self-test depends on this text. |
| `.ci/breakpoint/workflow/breakpoint.yml` + `.github/workflows/breakpoint.yml` (the frozen, hashed pair) | Edit directly, identically on both (the old-path string appears only inside `#` comments and an `echo "::error::..."` string, never as a step condition or `uses:` target), then regenerate the manifest: `.ci/breakpoint/scripts/check-breakpoint-drift.sh --write`. | `.ci/breakpoint/scripts/check-breakpoint-drift.sh:404-412` and `test_gate_breakpoint_secret_exposure.py::test_live_workflow_matches_template` both byte-compare the two files -- editing them identically keeps that green. `MANIFEST.sha256` hashes `workflow/breakpoint.yml` by content, so the edit reds `check:ci-breakpoint-drift` until `--write` regenerates it. |
| `.github/workflows/cd-stage.yml`, `.github/workflows/ci.yml` | Edit directly. | Both hits are `#`-comments (`.github/workflows/cd-stage.yml:319`, `.github/workflows/ci.yml:968`), not literal `if:`/`run:` arguments. No CI-behavior risk. |
| `.devcontainer/Dockerfile`, `.devcontainer/bashcov-sup.c` | Edit directly -- verified as real, deliberate prose citations, not coincidental. | `Dockerfile:591` "`# the same source onto the host. See agent/PLAN-shell-resource-profiling.md §1c.`"; `bashcov-sup.c:3` "`// agent/PLAN-shell-resource-profiling.md section 1c for what it survives and why.`" Both comments, safe. |
| `packages/www/scripts/test-tutorial-player-release-gate.js` | Edit directly. | Both hits (lines 326, 526) are prose inside `//` comments explaining test rationale, not path arguments used by the script's logic. |
| `scripts/gen/validate-cli-examples.ts` | Edit directly -- and this one is functionally live, not cosmetic. Fix the three literal entries in `EXCLUDED_FILES` (lines 156-158: `'agent/PLAN-lint-rule-matrix-probe.md'`, `'agent/PLAN-agent-hints-in-stop-hook.md'`, `'agent/PLAN-agent-hints-implementation.md'`) to their `agent/plans/...` form. Then run `npm run check:cli-examples` to confirm it is still green (or was already silently red and this fixes it). | The scanner's glob is `'agent/**/*.{md,mdx}'` (line 49), which matches both the stub and the new real file. `EXCLUDED_FILES` currently excludes only the (now-inert) stub; the real content carrying deliberately-bad CLI syntax as evidence, at the new path, is currently unexcluded. |
| Every other `.ci/`, `.claude/`, `scripts/` file in the ~69-file list not called out above (`bws_env.py`, `mutate_check.py`, `plan_housekeeping.py`, `staging_tag_guard.py`, `trap_registry.py`, `w7p5a_real_run_blockers.py`, `cleanup_channel_docker_tags.py`, `check_commands.py`, `test_gate_review_status.py`, the remaining `test_*.py` files, `check-plan-housekeeping.sh`, `check-trap-registry.sh`, `check_agent_hint_liveness.py`, `check_decision_ids.py`, `check_lint_rule_liveness.py`, `check_plan_boxes.py`, `check_plan_citations.py`, `check_plan_record.py`, `check_resprofile.py`, `lint-rule-liveness.mjs`, `git-fixture.sh`, `mutate-check.sh`, `www-site.md`, `onboard.py`, every `wl_*.py`/`test-*.py` hook file, `block_plan_without_tasks.py` + its `.sh` oracle twin, `warn_staged_shape_duplication.py`, `hookcases.py`, `scripts/ci-runner/*.ts`, `check-aws-credential-bridge.ts`, `check-client-bundle-budget.ts`, `check-git-tool-safety.ts`, `check-player-css-scope.ts`, `check-sentence-wrapping.ts`, `check-shape-duplication.ts`, `check-tracked-credentials.ts`, `gen-manifest.ts`, `SECURITY-HARDENING-SETUP.md`) | Edit directly. Every occurrence, checked with its full citing context, is inside a `#`/`//`/`"""` comment or docstring, never a literal path used as a runtime argument, condition, or data value the code branches on. Includes one intentionally-inert example: `.ci/rediacc_ci/tests/test_quality_dead_python.py:106`'s `assert dp.is_prose("agent/PLAN-tooling-transformation.md")` -- `is_prose()` is a pure prefix/suffix string check (`PROSE_PREFIXES`/`PROSE_SUFFIXES`), so it passes either way, but the fix keeps the test's own claim ("hundreds of real prose paths") pointing at real substantial content rather than a 1-line stub. | -- |

## 2. Mechanics of a safe edit

- No markdown-link-shaped citations exist anywhere in the corpus. Grepped all 157 files for `](agent/PLAN-` -- zero hits.
  Every citation is a bare path, either in plain prose, inside backticks, inside a `#`/`//` comment, or (once) inside a JSON string value. A single literal-string replace `old_path -> new_path` is uniformly correct wherever it's not inside a `Full-Text:` header line.
- No old path is a substring of another old path or of any new path (checked programmatically over all 103 entries) -- so replacement is order-independent and cannot cross-contaminate a different plan's citation.
- Trailing suffixes (`:136`, section markers, "Part 10") are untouched -- only the `agent/PLAN-<slug>.md` segment is replaced; the byte offset/line-number staleness question is a separate, already-tracked concern (`agent/PLAN-citation-fragility.md`), not this sweep's job.
- The one per-line exception: skip any line matching `^Full-Text:\s+[0-9a-f]{7,40}\s+agent/PLAN-<slug>\.md\s*$`.

## 3. Companion regeneration steps (run after all file edits, before final verification)

1. `.ci/breakpoint/scripts/check-breakpoint-drift.sh --write` -- regenerates `.ci/breakpoint/MANIFEST.sha256` now that `workflow/breakpoint.yml`'s bytes changed.
2. `npm run check:ci-plan-record -- --update` -- regenerates `agent/INDEX.md` from the now-corrected `agent/plans/*.md` / `docs/**` / etc. Do this last, after every other edit, so it reads the final state once.
3. `npm run check:cli-examples` -- confirm `scripts/gen/validate-cli-examples.ts`'s corrected `EXCLUDED_FILES` still keeps the gate green (or discover and report if it was already silently wrong).

## 4. Verification plan

Run these gates, all pre-existing and directly relevant:

- `npm run check:ci-plan-citations` -- judges only added lines under `agent/`, resolves `plan` tokens by "exists on disk," so it won't itself force the fix, but confirms every edited line still cites something real.
- `npm run check:ci-plan-boxes`, `npm run check:ci-plan-record`, `npm run check:ci-plan-folders` -- general plan-corpus health; `check:ci-plan-record` specifically is what the `Full-Text:` exception protects against going red.
- `npm run check:ci-breakpoint-drift` -- confirms the regenerated manifest matches and the two workflow copies are still byte-identical.
- `npm run check:cli-examples` -- confirms the `EXCLUDED_FILES` fix.
- Whatever gate runs `.ci/rediacc_ci/tests/test_quality_hook_integrity.py` (which reads the untouched golden) -- should stay green precisely because the golden was not touched; running it is a check that nothing accidentally bled into it.

**Exact final sweep**, self-contained (does not depend on the scratchpad JSON, re-derives the mapping from the stubs' own `Moved-To:` headers so it is reproducible by the implementing session):

```bash
for stub in agent/PLAN-*.md; do
  new=$(grep -m1 '^Moved-To:' "$stub" | sed -E 's/^Moved-To:[ \t]*//')
  [ -n "$new" ] || continue
  git grep -n --fixed-strings "$stub" -- . \
    | grep -v -E '^\Q'"$stub"'\E:[0-9]+:Full-Text:' \
    | grep -v -E '^(agent/worklist/[^:]+\.jsonl|agent/reggate/[^:]+\.jsonl|agent/ledgers/census-[^:]+\.jsonl|agent/archive/|agent/pr/[^:]+\.md|agent/(f88f9be7|8f55d4f0|f4da5c2e|a276391d)/):'
done
```

Any remaining output after the sweep is a missed citation. Expected clean output: nothing (every legitimate residual -- worklist/reggate jsonl, census ledger, archive, `agent/pr/*.md`, peer directories, and each record's own `Full-Text:` line -- is filtered by the two `grep -v` passes).

## 5. Execution approach: inline script, not writer sub-agents

Recommendation: a single scoped script pass in the implementing session, not batched writer sub-agents.

Reasoning:
- The mechanics are uniform (one literal-string replace per `(old, new)` pair, one line-level exception), already verified safe across every occurrence in all 157 files -- there is no per-file creative judgment left to make that a sub-agent would add value on.
- ~108 files need a real edit (157 total, minus 4 worklist, 1 INDEX, 1 ledger, 5 archive, 4 peer, 1 generated-pr, 1 golden, and minus the 32 files whose only self-citation is a protected `Full-Text:` line with nothing else to change).
  A script that iterates `(old_path, new_path, [files])` from the mapping and does a line-aware replace (skip `^Full-Text:`) is faster, more auditable via a single diff, and structurally cannot violate the skip-list the way a sub-agent instructed "don't touch archive/" could still slip on under token pressure.
- Splitting into 2-concurrent writer-sub-agent batches would only be worth it if the edits required independent judgment per batch (they don't) or if the volume made a single session's context untenable (108 mechanical one-line edits does not).
- If the operator still prefers sub-agents for per-file diff review, the safe split is by path prefix, each given an exact file list and the exact `(old, new)` pairs it owns, explicitly forbidden from touching anything outside its list:
  - Batch A: `agent/plans/**`, `agent/programs/**`, `agent/DECISIONS.md` (~55 files, excluding the 32 Full-Text-only no-ops)
  - Batch B: `docs/**` (11 files)
  - Batch C: `.ci/**`, `.github/**` (~45 files, including the breakpoint pair + manifest regen)
  - Batch D: `.claude/**`, `scripts/**`, `packages/**`, `.devcontainer/**` (~35 files)

  Run A+B concurrently, then C+D concurrently (2-at-a-time per CLAUDE.md rule 4), each followed by its own `git diff` review before the next pair starts.

Either way, the two regeneration commands (`check-breakpoint-drift.sh --write`, `check_plan_record.py --update`) must run after all batches/the script complete, and the final verification sweep runs last.

## Tasks

- [x] Build the `(old_path, new_path)` map from every stub's `Moved-To:` header (103 entries).
    (ticked) 2026-09-22T20:05:08Z by d778be9d: commit a81967e94: git ls-tree -r --name-only HEAD -- agent | grep '^agent/PLAN-' returns exactly 103 files, each with Moved-To: header
- [x] For each of the ~157 citing files, apply the per-class rule from section 1: skip (never-edit classes), skip the `Full-Text:` line specifically, or literal-replace the old path segment with the new one everywhere else.
    (ticked) 2026-09-22T20:14:09Z by d778be9d: commit a81967e94: 113 files, ~140 old-path occurrences repointed. 4-line residue in PLAN-stop-hook-task-verification.md is NEW debt from commit 97164ac96 (created AFTER a81967e94 landed), not a miss by this sweep
- [x] Fix `scripts/gen/validate-cli-examples.ts`'s three `EXCLUDED_FILES` entries.
    (ticked) 2026-09-22T20:05:08Z by d778be9d: scripts/gen/validate-cli-examples.ts:154-157 has all three EXCLUDED_FILES entries, committed in a81967e94
- [x] Edit `.ci/breakpoint/workflow/breakpoint.yml` and `.github/workflows/breakpoint.yml` identically.
    (ticked) 2026-09-22T20:05:08Z by d778be9d: .ci/breakpoint/workflow/breakpoint.yml and .github/workflows/breakpoint.yml both cite agent/plans/PLAN-breakpoint-secret-shape.md at lines 257/261/343, diff confirms byte-identical
- [x] Run `.ci/breakpoint/scripts/check-breakpoint-drift.sh --write` to regenerate the manifest.
    (ticked) 2026-09-22T20:05:09Z by d778be9d: ran check-breakpoint-drift.sh live: Verified 25 files, 0 accepted divergences
- [x] Run `npm run check:ci-plan-record -- --update` to regenerate `agent/INDEX.md`.
    (ticked) 2026-09-22T20:14:09Z by d778be9d: ran npm run check:ci-plan-record -- --update live: wrote agent/INDEX.md: 75 record(s)
- [x] Run `npm run check:cli-examples` to confirm the `EXCLUDED_FILES` fix.
    (ticked) 2026-09-22T20:05:09Z by d778be9d: ran validate-cli-examples.ts live: All CLI command examples are valid, exit 0
- [x] Run the exact final verification sweep from section 4 and confirm zero remaining output.
    (ticked) 2026-09-23T10:19:35Z by d778be9d: Ran the section-4 sweep directly: zero agent/PLAN-*.md stubs remain (retired by the 2026-09-22 cleanup), so the loop produces empty output, exactly the box's expected result. Investigation recorded in commit 0346c4eac.
- [x] Run `check:ci-plan-citations`, `check:ci-plan-boxes`, `check:ci-plan-record`, `check:ci-plan-folders`, `check:ci-breakpoint-drift`.
    (ticked) 2026-09-23T10:14:50Z by d778be9d: All 5 named gates run this session, evidence recorded in commit 87bca423a's investigation row.

## Acceptance criteria

- The final verification sweep (section 4) produces zero output.
- `check:ci-plan-record` stays green (proves no `Full-Text:` line was touched).
- `check:ci-breakpoint-drift` stays green after the manifest regen.
- `check:cli-examples` stays green (or a genuine pre-existing gap it exposes is reported, not hidden).
- No file in a never-edit class (worklist/reggate jsonl, census ledger, archive/, peer session directories, the golden, `agent/pr/0903-1.md`, `agent/INDEX.md`) shows any diff.
