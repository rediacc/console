# PLAN: Delete the unwired `lint:css` checkers and repair the wired gate they exposed
Status: compacted
Owner: e6500e92
Full-Text: f7a5351a9 agent/PLAN-lint-css-ci-wiring.md
Full-Text-Blob: e97837565b685d82e72fd542652a452a05df1e97
Record-Sig: 4b4a21b1

## Why
`packages/www` carried two unwired dead-CSS checkers, `lint:css` and `lint:css-files`, and the open question was whether to wire them into CI. Measured head to head against the WIRED `check:ci-dead-css`, the unwired checker found zero real findings the wired gate missed, missed six the wired gate caught, and invented three the wired gate correctly rejected. Wiring it would have
installed a second, less accurate implementation of a gate that already ran. It had slipped through unnoticed because `check:ci-parity` and `check:ci-gate-reachability-coverage` key off the `check:ci-*` naming convention and `lint:css` never carried that prefix. The comparison also exposed three real defects in the wired gate, which the plan fixed in the same change.

## Outcome
SHIPPED, measured on 2026-09-06 against the tree rather than read off the header. Every step of the plan's section 8 is present:

- `packages/www/package.json` now carries NO `lint*` script key at all: `lint:all`,
`lint:css` and `lint:css-files` are gone.
- `packages/www/scripts/check-unused-css.js` and `check-unused-css-files.js` do not
exist. `git log --diff-filter=D` names their removing commit as f7a5351a9, "feat(www): simplify the marketing and docs site, and the gates that watch it", an ancestor of origin/main.
- `packages/www/src/styles/team-video.css` and `language-switcher-inline.css` are
gone.
- All three defect fixes are in `scripts/gates/check-dead-css.ts`: defect A as the
`"cardClass"` harvest over `en.json` (`scripts/gates/check-dead-css.ts:110`), defect B as the class-position interpolation harvest, defect C as `VENDOR_CLASS_PREFIXES = ['plyr__']` (`scripts/gates/check-dead-css.ts:70`) with its BLOCKER reason (`scripts/gates/check-dead-css.ts:63`), each with the paired negative control the plan specified (`scripts/gates/check-dead-css.ts:208`).
- Step 7's stale prose was corrected too: `agent/PLAN-localize-cheat-sheet-rendering.md` (line 345 of blob f109c90887d63c381f47f648b684bcf281a24c53)
now reads "CORRECTED 2026-08-18: `lint:css` and `lint:css-files` no longer exist".

ONE NUMBER DID NOT LAND AS PREDICTED, recorded rather than smoothed over. The plan expected the baseline to fall from 92 to 63. `npm run check:ci-dead-css` run here exits 0 and reports "21 stylesheet(s), 1314 source file(s); 62 dead class(es), baseline 62", and `scripts/data/dead-css-baseline.json` holds 62 entries. One fewer than predicted. Whether that is a class rescued by a
later change or a slip in the estimate was not traced.

## Lessons
- A gate that is not wired is not a gate, and the naming convention is what hid it:
both parity gates key off `check:ci-*`, so a checker called `lint:css` was invisible to the machinery that exists to catch exactly this.
- Comparing a candidate gate against the incumbent is worth more than either gate's
own output. The three false positives and six misses were only visible as a set difference, and the same comparison surfaced the incumbent's own defects.
- Deleting a stylesheet touches other gates' baselines. This plan had to check
`static-nowrap-baseline.json` and `check:ci-css-dom-refs` before the file deletions were safe, and that dependency is invisible from the file being deleted.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:03:35Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: packages/www/package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml, packages/www/src/components/solution-pages/SPHowItWorks.astro, agent/programs/www-simplification/research/RESEARCH-docs.md, agent/PLAN-localize-cheat-sheet-rendering.md
Gates: check:ci-css-dom-refs, check:ci-dead-css, check:ci-gate-reachability-coverage, check:ci-parity
Why-Source: auto
Read-History: `git show e97837565b685d82e72fd542652a452a05df1e97` recovers the text; `git log --find-object=e97837565b685d82e72fd542652a452a05df1e97 --all` names the commit

## History
- 2026-09-06T17:03:35Z compacted by 8f55d4f0 from `done` (record-sig 4b4a21b1)
