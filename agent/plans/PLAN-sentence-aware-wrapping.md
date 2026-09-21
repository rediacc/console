# PLAN: sentence-aware wrapping for packages/www
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: 9b66577af5e330a95f7b76d2f850475c49d4740d
Record-Sig: 3e406c79

## Why
The www site has sentence-wrapping defects where a single sentence is broken across lines while sharing those lines with adjacent sentences. Measured 11 defects on /en at 1440x900 where text wraps at 'Most tools copy one | piece. We copy all of it.' The rule enforced is precise: a sentence occupying multiple lines must not share either of those lines with an adjacent sentence.
Existing CSS text-wrap heuristics (pretty, balance) only accidentally recover 3 of 11 and are not sentence-aware by design.

## Outcome
Plan remains unimplemented as of 2026-09-20. It is a design proposal specifying: (a) wrap each sentence in inline-block spans at build time via Intl.Segmenter; (b) create three components (sentences.ts, Sentences.astro, Sentences.tsx) and one rehype plugin; (c) modify 80 call sites across 34 source files; (d) add two CI gates (static check-ci-sentence-wrapping for source coverage,
browser check-ci-sentence-lines for 156-measurement matrix). Full design text preserved in git blob.

## Lessons
- The literal rule 'line must not both end one sentence and begin another' is unsatisfiable; the enforced rule is its contrapositive: broken sentences can span lines if they don't share them with neighbors.
- text-wrap: pretty and text-wrap: balance are heuristics that fail by design; they move 3 of 11 defects by accident, not by sentence awareness.
- An HTML rewrite pass at build time breaks hydration in six React islands (5 multi-sentence blocks per page inside them), requires new parser dependency, and does not run on dev server.
- Static and browser gates are both load-bearing: static catches unmarked multi-sentence strings, browser gate catches rendering defects and locale-specific variants (en 11, ja 12, zh 4, ar 8 at 1440x900).
- Measure line breaks using per-character Range rects, not Range over whole elements; per-character rects are agnostic to wrapping mechanism.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:00:43Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: scripts/gates/check-dead-css.ts
Gates: check:ci-browser-smoke, check:ci-css-dom-refs, check:ci-dead-css, check:ci-hydration-clean, check:ci-landmarks, check:ci-layout-overflow, check:ci-parity, check:ci-sentence-wrapping
Why-Source: model
Read-History: `git show 9b66577af5e330a95f7b76d2f850475c49d4740d` recovers the text; `git log --find-object=9b66577af5e330a95f7b76d2f850475c49d4740d --all` names the commit

## History
- 2026-09-20T18:00:43Z compacted by d778be9d from `draft` (record-sig 3e406c79)
