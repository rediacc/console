## SESSION e6500e92 2026-08-18T20:44:47Z

# www round 3: waves 1, 2, 4, 5 DONE. Wave 3 verifying. All UNCOMMITTED on `main`.

Plan: `/home/muhammed/.claude/plans/memoized-gliding-kay.md`. Reports:
`~/.claude/projects/-home-muhammed-monorepo-console/programs/www-round3/reports/`.

## Waves

- **w1 docs columns, w2 header, w4 references: DONE and ticked.** Five-track docs grid with
  EXPLICIT placement (auto-placement would have dropped the article into a slack track, a
  defect my plan missed); article 800px centred, TOC 31px from the edge, was 340px of dead
  space. Header gap 242px -> 16px. References replaced by underlined inline links,
  3,588 = 276 x 13, no orphan.
- **w5 catalogs: DONE, mine.** All 13 catalogs 6,988 -> 6,916 leaves (-72 each: 44
  label/disclaimer, 16 roiCalculator.references, 12 persona refs) and **339 literal `[n]`
  pointers stripped from 35 prose values**, a pre-existing bug where 8 locales shipped
  `Veeam ... 2021 [1][1]`. My independently-computed 339 matched w4's independent 339.
  `i18n:generate-hashes` run once. Tooling is durable in the scratchpad:
  `catalog_splice.py` (byte-splice, refuses array-element deletion, verifies leaf-set
  delta) and `wave5.py` (dry-run by default).
- **w3 video picker: source settled at 22:18, agent still verifying.** Owed: the
  `data-sources` byte size, and a manifest-absent probe re-run against a `dist/` it trusts.

## The catalogs are formatted by BIOME, correcting round 2

Round 2's note that "no formatter reproduces the catalogs' shape" is TRUE of python and
FALSE of biome, which is their canonical formatter. Rounds 1 and 2's byte-splices left 5
lines of `"x"},` shape that HEAD does not have, and `check:format` (wired at
manifest.ts:157 and ci-quality.yml:524) was RED because of it. Fixed by
`biome format --write` on the 13 catalogs, semantically a no-op (leaf counts identical).
**Any future catalog splice must end with `biome format --write` on that directory.**

## Fixed beyond the round, each with a planted control

- Em-dash gate: `.claude/commands`, `.claude/hooks`, `.claude/agents` all joined at ZERO,
  fence-aware markdown, PER-SURFACE floors, and a `ZERO_SURFACES` invariant so
  `--write-baseline` can never absorb a regression there. 15 controls.
- Search indexes shipped **2,122 unresolved `{{t:...}}` per locale** to readers; resolution
  now shared via `translation-keys.mjs` between the remark plugin and the index generator,
  and `check-search-index-freshness.ts` gained a content assertion proved to fire.
- `check-dead-css` marked **10 of 92 baselined classes dead when live** (catalog-supplied,
  template-interpolated, and vendor `plyr__`). Baseline 92 -> 62, zero added. Deleted the
  unwired `lint:css` / `lint:css-files` per `agent/PLAN-lint-css-ci-wiring.md`.
- `check-component-hardcoded-strings` read multi-line `{/* */}` comments as user-facing
  text, making the CI-blocking `check:i18n` chain red. Fixed and proved not blinded.
- The screen-reader " (opens in new tab)" suffix was hardcoded ENGLISH in CSS on 9,226
  links across 13 locales; now a localized custom property.
- biome's includes missed `packages/**/*.mjs|cjs` entirely, the same class as the earlier
  `scripts/**/*.js` gap.

## Next action

Read `/tmp/claude-1000/final-build.out` for the authoritative build, then run
`check:ci-landmarks`, `check:ci-browser-smoke` and `check:ci-ssr-locale` against it, plus a
built-output check that no `[n]` survives in visible text or in the 216 aria-labels. Then
tick **w3 `#86e5fc83`** once its two outstanding numbers arrive, and report to the operator
including the brainstorm (plan's `## Brainstorm`, none of it approved yet). Open and NOT
started: `#2e0695cf` CLI em-dash gate, plan written at
`agent/PLAN-cli-em-dash-lint-gate.md`; its 12 non-English catalogs are Sonnet work.
