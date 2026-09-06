# -lint-css-ci-wiring
Status: compacted
Owner: e6500e92
Full-Text: f7a5351a9 agent/PLAN-lint-css-ci-wiring.md
Full-Text-Blob: e97837565b685d82e72fd542652a452a05df1e97
Record-Sig: 4b4a21b1

## Why
The www package carried two unwired CSS checkers (lint:css, lint:css-files in scripts/) that were not wired into CI. When compared to the wired gate check:ci-dead-css, they were found to be strictly inferior on every axis: missing six real dead classes that the wired gate catches, reporting three false positives, and suffering from a word-boundary regex that silently matched prefixes on hyphenated class names (cf-pricing-card matched pricing-card). The comparison also exposed three defects in the wired gate itself: classes supplied only by translation catalogues were invisible, interpolated template-literal class names were not harvested, and vendor library classes had no allowlist.

## Outcome
Landed in commit f7a5351a9 (feat(www): simplify the marketing and docs site, and the gates that watch it). Deleted both unwired checkers and their npm script entries. Deleted two entirely dead stylesheets (team-video.css, language-switcher-inline.css, 269 lines). Created check-dead-css.ts to fix the three wired-gate defects: harvests only cardClass values from translations, harvests interpolation prefixes only from class= / className= / class:list positions, and adds vendor-prefix allowlist (plyr__) with BLOCKER reason. Regenerated baseline from 92 to 63 entries. Added seven new selftest controls and three end-to-end gate-firing controls to verify the fixes work.

## Lessons
- Word-boundary regex (`\b`) fails silently on hyphenated names when matching substrings — cf-pricing-card is not pricing-card to `\b\bpricing-card\b`, but the gap only shows when comparing two checkers on the same codebase.
- Static CSS analysis without reading translation catalogues (where template-supplied class names live) and without parsing template-literal positions (class= vs bare const) has invisible blind spots that comparison against a better implementation can reveal.
- A CI gate that doesn't follow the check:ci-* naming convention is invisible to meta-gates (check:ci-parity, reachability-coverage) and can sit red and unread indefinitely; the prefix is not a label, it is load-bearing.
- Vendor library classes need explicit allowlisting with documented BLOCKER reasons rather than trying to scan minified node_modules, because it couples the gate to the installed tree and a library's source format.
- Template literals look identical inside and outside class positions — a bare `const source = 'solution-${slug}'` is not a class, so harvesting interpolation must be position-aware to avoid rescuing unrelated dead classes.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T15:30:15Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: packages/www/package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml, packages/www/src/components/solution-pages/SPHowItWorks.astro, agent/programs/www-simplification/research/RESEARCH-docs.md, agent/PLAN-localize-cheat-sheet-rendering.md
Gates: check:ci-css-dom-refs, check:ci-dead-css, check:ci-gate-reachability-coverage, check:ci-parity
Why-Source: model
Read-History: `git show e97837565b685d82e72fd542652a452a05df1e97` recovers the text; `git log --find-object=e97837565b685d82e72fd542652a452a05df1e97 --all` names the commit

## History
- 2026-09-06T15:30:15Z compacted by 8f55d4f0 from `done` (record-sig 4b4a21b1)
