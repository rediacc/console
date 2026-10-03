# w-homepage-pricing

Removed the redundant pricing preview section from the homepage. Measured 2026-08-27.

## What was removed

- `packages/www/src/components/PricingPreview.astro` (43 lines) DELETED. It was the only
  render site of the section and the only consumer of the `pricingPreview.*` namespace.
- `packages/www/src/components/solution-pages/SPHomePage.astro`: dropped the import and the
  `<PricingPreview lang={lang} />` render, and recorded the removal in the file's existing
  "what left and why" header block, matching the shape used for `logo-wall` and `metrics-bar`.
- i18n: the `pricingPreview` branch spliced out of all 13 locale catalogs.
  **3 English leaves x 13 locales = 39 values deleted.** Byte splice, not a reserialize:
  `git diff` shows exactly 5 removed lines and 0 added lines per catalog attributable to
  this change.
- `packages/www/src/i18n/translations/.translation-hashes.json`: 3 hash entries removed,
  `$meta.keyCount` 6215 -> 6212.
- `packages/www/src/i18n/translations/.naturalized-hashes.json`: 36 stale ledger entries
  removed (3 keys x 12 maintained locales).

## CSS that became dead and was removed

`check:ci-dead-css` caught one class the plan did not anticipate.

- `public/styles/main.css`: `.pricing-preview-compare` and `.pricing-preview-compare:hover`.
- `src/styles/pricing-page.css`: `.cf-pricing-section` (base rule plus its `max-width: 40rem`
  override). Its comment banner "Cloudflare-style pricing cards (homepage embed)" lost the
  "(homepage embed)" qualifier since the remaining cards are the pricing page's own.
- `.section-subtitle` was rendered ONLY by `PricingPreview.astro`. Three rules died with it:
  `public/styles/main.css` (base plus wide-desktop override) and
  `public/styles/responsive.css` (mobile override). `responsive.css` was outside the stated
  file ownership; the edit is one four-line rule and was required to keep the gate green.
  `.section-title` and `.section-header` survive, both still rendered elsewhere.

No baseline draining was needed. `dead-css-baseline.json` went 63 dead classes back to its
frozen 62 and none of the deleted classes were ever baselined. `em-dash-surfaces-baseline.json`
carries zero `pricingPreview` and zero `PricingPreview` entries, so nothing was drained there
either.

## The homepage still routes to /pricing

Yes, by three independent paths, so no STOP condition:

- `src/components/Navigation.tsx:356` header nav, `href={`/${currentLang}/pricing`}`
- `src/components/Sidebar.tsx:164` mobile drawer, same target
- `src/components/Footer.tsx:136` footer, after the repoint below

## Three inbound `#pricing` fragment links repointed (outside stated ownership)

The deleted section carried `id="pricing"`. Three call sites aimed at it and would have
become dead fragments. All three now point at the real route:

- `src/components/Footer.tsx:136`: `/${currentLang}#pricing` -> `/${currentLang}/pricing`
- `src/pages/[lang]/refund-policy.astro:20`: `/${lang}#pricing` -> `/${lang}/pricing`
- `src/config/persona-pages.ts:41`: `ceo: '#pricing'` -> `ceo: '/pricing'`, plus the
  now-false doc comment above `PERSONA_CTA_MAP` that described anchor-only entries

`Footer.tsx`, `refund-policy.astro` and `persona-pages.ts` were not in the stated file list.
Each edit is a single string. Shipping without them would have left the footer's Pricing link
and the CEO persona CTA pointing at an id nothing emits.

## Gate exit codes

| gate | exit |
|---|---|
| `check:i18n:completeness` | 0 |
| `check:i18n:hashes` | 1, NOT this change (see below) |
| `check:ci-dead-translation-keys` | 0 (6696 keys reachable, baseline 192 unchanged) |
| `check:ci-dead-css` | 0 (62 dead, baseline 62) |
| `check:ci-css-dom-refs` | 0 (31 unstyled, baseline 31) |
| `check:format` | 0 (2191 files, no fixes) |
| `check:i18n:key-usage` | 0 (extra, both directions) |
| `check:ci-em-dash-surfaces` | 1, NOT this change (see below) |
| `check:ci-client-i18n` | 1, NOT this change (see below) |
| `check-i18n-naturalization` | 0 |

`i18n:generate-hashes` was deliberately NOT run. See the collision note.

## Found, not owned

1. **`check:i18n:hashes` fails on another wave's in-flight work.** 253 keys removed, 24 added,
   2 English values changed, and a programmatic diff of `en.json` against the manifest confirms
   **all 279 are under `pages.solutionPages.*`**, zero under `pricingPreview`. Running
   `npm run i18n:generate-hashes` would re-baseline that wave's unfinished English edits and
   mark 12 locales' stale translations as fresh, defeating `check-i18n-naturalization`. So the
   3 `pricingPreview` entries were spliced out by hand instead and the rest left for its owner.
2. **A concurrent writer clobbered the catalog deletion once.** All 13 locale files were
   rewritten in the same second (mtime 1787859661) by another session's bulk pass, restoring
   `pricingPreview` and carrying that wave's solution-page changes. Detected because
   `check:i18n:hashes` flipped from "3 keys removed" to "pricingPreview is a NEW key". The
   deletion was re-applied on top of their content with a parsed-JSON equality assert, so their
   work is intact. Confirms the knowledge file: the catalogs need one serialising owner.
3. **`check:ci-em-dash-surfaces` exit 1 on `.claude/hooks/stop/wl_admit.py`**, one finding,
   `73954354b706`, an em dash inside a regex character class. Unrelated to www.
4. **`check:ci-client-i18n` exit 1**, all 13 generated client bundles stale. Every one
   REGENERATES LARGER than committed, so it is additive drift, not this deletion, and
   `grep -c pricingPreview src/i18n/client/*.json` is 0 everywhere. Consistent with the peer
   session adding form-validation keys. Its owner should run
   `npm run i18n:generate-client -w @rediacc/www`.

## Not run

No build. `check:ci-browser-smoke`, `check:ci-landmarks`, `check:ci-anchor-integrity` and
`check:ci-layout-overflow` all need `dist/`, and a build here both deletes 14 tracked
search-index files and races the other live waves. Note for whoever builds next: this change
removes `pricing-page.css` from the homepage's imported set, which may move the known 133px
horizontal overflow on `/en` caused by `.cf-feature-info::after` in that sheet. If
`check:ci-layout-overflow` reports a baselined `/en` finding as FIXED, that is this change and
the baseline needs draining.
