# PLAN: Bring packages/cli under the em dash gate
Status: compacted
Owner: e6500e92
Full-Text: bb878f6e7 agent/PLAN-cli-em-dash-lint-gate.md
Full-Text-Blob: 629e12f4662163b2e5b78fecaa292abf7354ae6f
Record-Sig: 3816a060

## Why
The em dash gate covered `packages/www` only, so the largest prose surfaces in the repo were invisible while its output stayed green. This plan argued for extending the existing gate's surface table rather than writing a second gate: the id scheme, the shrink-only baseline, the per-surface floor and the inline selftest are one implementation, a second gate needs three new wiring
points to reach CI at all, and two tables each true about their own files and silent about the other's is exactly the founding defect of the gate being extended.

## Outcome
SHIPPED. Header `done` is TRUE. Measured 2026-09-06.

- The three surfaces of section 3 are in `SURFACES` verbatim at
`scripts/gates/check-em-dash-surfaces.ts:155-157` (blob cab1c05b8163724110a719f09ae5d4937cd1e3ec), with the floors 10 / 8 / 300 as specified, including the deliberate 300 that sits above the 295 non-test files so a quiet `__tests__` exclusion trips a red floor.
- The zero-join is a RULE and not a fact about one afternoon: both drained surfaces are
in `ZERO_SURFACES` at `:268-269`, and `--write-baseline` refuses to bake in a finding from either.
- Section 3's "one character away from breaking" prose became a control rather than
staying a comment: `nestedSurfaceOverlap` at `:245`, asserted over the live table at `:584` and exercised in both directions at `:589` and `:597`.
- The baseline SHRANK as designed, with nobody assigned to drain it:
`scripts/data/em-dash-surfaces-baseline.json` (blob 1cad58318a6dbcb877bd9d943c3addfe73e5b67e) now holds 2648 entries against the 2876 recorded at close, so 228 findings left under the shrink-only rule.
- Live landing: console commit 55f18e024, "feat(gate): bring packages/cli under the em
dash gate, two surfaces at zero" (2026-08-21).

## Lessons
- THE COMMIT SHA IN THIS PLAN'S OWN OUTCOME IS DEAD, and nothing reported the loss. The
rebase this repo merges with rewrote it. Quoted inside a fence because it is evidence of a dead pointer rather than a citation to follow:

```
82def0b11   section 11's claimed landing for steps 6 to 8
```

`git cat-file -t` on it answers "Not a valid object name". The live commit is 55f18e024 and the durable pointer is the blob.
- A comment is not a control. The nesting hazard was named in prose and only became safe
when it was turned into an assertion that fires in both directions.
- Baselining the residue and assigning nobody was right: shrink-only makes every passing
edit ratchet, and 228 findings drained without a campaign.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:30:34Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: scripts/ci-runner/manifest.ts, package.json, scripts/gates/check-em-dash-surfaces.ts, packages/cli/src/services/config/config-resources-resolve.ts, packages/cli/src/services/cluster/cluster-fork.ts, packages/cli/src/services/cluster/cluster-kube.ts, packages/cli/src/services/cluster/cluster-membership.ts, packages/cli/src/services/cluster/repo-replicate-ops.ts, packages/cli/src/services/repo/prune.ts, packages/cli/src/commands/update.ts, packages/cli/src/services/update/background-updater.ts, packages/cli/src/commands/doctor.ts, packages/cli/src/utils/timeline.ts, packages/cli/src/commands/config/field.ts, packages/cli/src/remote/repository/bashFunctions.ts, packages/cli/src/utils/repo-context-guard.ts, packages/cli/src/utils/process-ancestry.ts, packages/cli/src/services/core/embedded-assets.ts, packages/cli/src/commands/mcp/tools.ts, scripts/gen/sync-translations.ts
Gates: check:ci-em-dash-surfaces, check:ci-gate-reachability-coverage, check:ci-i18n-cli-help-render, check:ci-i18n-cli-key-usage, check:ci-i18n-placeholders, check:ci-parity, check:i18n, check:i18n:completeness
Why-Source: author
Read-History: `git show 629e12f4662163b2e5b78fecaa292abf7354ae6f` recovers the text; `git log --find-object=629e12f4662163b2e5b78fecaa292abf7354ae6f --all` names the commit

## History
- 2026-09-06T17:30:34Z compacted by 8f55d4f0 from `done` (record-sig 3816a060)
