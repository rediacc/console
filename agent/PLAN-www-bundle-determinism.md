# PLAN: The client-bundle budget silently drops 124 KB, and that is the "nondeterminism"
Status: compacted
Owner: 74de73ca
Full-Text-Blob: 16d1c4c5219f211e837df5055787fc2f3e22a99b
Record-Sig: 3adda97a

## Why
The client-bundle budget gate required whitespace after `import` but rollup emits bare side-effect imports without space (`import"./x.js"`). This caused a 129-byte facade chunk and 122 KB of TutorialVideoPlayer (plyr) to be invisible to measurement. The homepage was reported at 451 KB while actually shipping 576 KB — the gate passed on false data.

## Outcome
Landed. Commit 428569fbb (2026-09-03) fixed the regex from `\s+` to `\s*`, causing measurement to jump from 451,621 B to 576,294 B and exceed the 500,000 B budget (now honestly). Follow-up: commit 2fbbf49d1 deferred video hydration from DOMContentLoaded to first interaction (click), eliminating the actual 122 KB for users who never watch. Related gate fixes landed; file comment
rewritten to document the fix and the arithmetic.

## Lessons
- A false green is as dangerous as a false red. This gate had been passing while the page shipped 124 KB unmeasured—a gate ratifying the defect while sounding confident.
- Measurement fidelity requires matching actual output format (minified imports strip whitespace), not the formatted source read in code.
- Systemic blind spots need sweeping: 49 no-space edges across 20 files. Fixing one instance without verifying the class leaves the defect intact.
- Honest measurement that exceeds a budget is preferable to raising the budget to hide the defect. A budget set just above the real figure is not a ceiling, it is a ratification.
- Build variance (this case: 129 B facade-merge shape difference) only becomes visible once measurement is fixed. Pinning the build first would have left the blind spot intact.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:08:11Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: scripts/gates/check-client-bundle-budget.ts, packages/www/src/components/solution-pages/SPHomePage.astro
Gates: check:ci-client-bundle-budget, check:ci-gate-manifest, check:ci-hydration-clean, check:ci-parity, check:ci-seo
Why-Source: model
Read-History: `git show 16d1c4c5219f211e837df5055787fc2f3e22a99b` recovers the text; `git log --find-object=16d1c4c5219f211e837df5055787fc2f3e22a99b --all` names the commit

## History
- 2026-09-20T18:08:11Z compacted by d778be9d from `draft` (record-sig 3adda97a)
