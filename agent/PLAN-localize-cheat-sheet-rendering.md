# PLAN: Localize the rendered RDC cheat sheet by deleting its private rendering path
Status: compacted
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-localize-cheat-sheet-rendering.md
Full-Text-Blob: f109c90887d63c381f47f648b684bcf281a24c53
Record-Sig: c6284ed5

## Why
The rendered RDC cheat sheet was not a localization bug, it was a SECOND DOCUMENT.
`packages/www/src/marp/rdc-cheat-sheet.marp.md` was a 371-line English-only file that no
gate scanned and no translator touched, and it was what every reader saw in all 13
locales, while a fully translated `packages/www/src/content/docs/<lang>/rdc-cheat-sheet.md`
reached the .md and .txt exports, the ZIP and the search index but never a rendered page.
Same URL family, same build, two different languages, with every gate green because both
CLI validators and the freshness check root at the content collection and cannot see
`src/marp/`. The fix was to DELETE the marp path rather than teach it about locales.

## Outcome
SHIPPED. THE HEADER SAYS "accepted, scheduled post-push" AND THE TREE SHOWS IT EXECUTED.
Measured 2026-09-06.

- `packages/www/src/marp/` DOES NOT EXIST, and neither does
  `packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro`. The literal route that
  shadowed the collection entry is gone, so `[slug].astro` (blob
  ee01bd0b126dae0666e6b8acfd12602346e22958) now serves the page; all 13
  `content/docs/*/rdc-cheat-sheet.md` files are still present.
- Gate 1 shipped: `scripts/gates/check-docs-render-parity.ts` (blob
  962bb9e68122b54816427429562398204421543c), wired as `check:ci-docs-render-parity`
  (`package.json:231`), with the control the plan demanded at
  `scripts/__tests__/check-docs-render-parity.control.ts` (blob
  0b05a601554bca6d0d855dba06e688d46271fdb3), chained into `check:i18n`.
- Gate 2 shipped as its own script rather than a grep rule:
  `scripts/gates/check-page-locale-imports.ts`, wired as `check:ci-page-locale-imports`
  (`package.json:232`), with `scripts/__tests__/check-page-locale-imports.control.ts`
  (blob a29992b00edf066c69a9bfff3b0615d3edafa864) also chained into `check:i18n`. It is
  now GREEN with zero suppressions: `grep -rn '?raw' packages/www/src/pages
  packages/www/src/layouts` returns nothing at all.
- Landing: console commit 6a06faf33, "fix(www): the cheat sheet was a second document,
  and it shipped in English" (2026-08-18), which added the parity gate and reworked
  `[slug].astro`. The 371-line deletion is visible with
  `git log -S 'marp/rdc-cheat-sheet.marp.md'`. NOTE FOR ANY LATER READER:
  `git log --diff-filter=D` on the marp path answers `3af439de5`, whose subject is
  "chore: account pointer + record backup browse in the program doc" and has nothing to
  do with this work. Content-history search is the reliable instrument here.

## Lessons
- A green gate is a statement about the corpus it roots at, and nothing more. Three
  validators and a freshness check all passed over a page whose body no reader in twelve
  locales could understand.
- The gate was the DELETION. Divergence between two documents was not policed, it was
  made unrepresentable by removing one of them, and the render-parity gate exists for the
  surviving CLASS of bug rather than for this instance.
- Gate 2 was deliberately introduced RED and landed only when the tree could satisfy it.
  A gate introduced pre-satisfied proves nothing about the day it was written.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: accepted
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:32:37Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: packages/www/scripts/validate-docs-cli-usage.js, packages/www/scripts/validate-content-accuracy.js, packages/www/scripts/generate-search-index.js, packages/www/src/content/docs/de/rdc-cheat-sheet.md, packages/www/scripts/lib/cli-reference-catalog.js, packages/www/src/content/docs/en/rdc-cheat-sheet.md, .github/workflows/ci-quality.yml, packages/www/src/layouts/DocsLayout.astro, package.json
Gates: check:ci-dead-css, check:ci-docs-render-parity, check:ci-parity, check:ci-retired-commands, check:ci-seo, check:cli-docs, check:cli-examples, check:i18n
Why-Source: author
Read-History: `git show f109c90887d63c381f47f648b684bcf281a24c53` recovers the text; `git log --find-object=f109c90887d63c381f47f648b684bcf281a24c53 --all` names the commit

## History
- 2026-09-06T17:32:37Z compacted by 8f55d4f0 from `accepted` (record-sig c6284ed5)
