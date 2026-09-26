# PLAN: the nav server-renders in English on all 12 non-English locales
Status: compacted
First-Seen: 2026-09-17
Owner: e6500e92
Full-Text: f7a5351a9 agent/PLAN-ssr-nav-locale.md
Full-Text-Blob: 607afdb545574a449e1959a5adfa926879358bc0
Record-Sig: 3d8aec74

## Why
The nav server-rendered in English on all 12 non-English locales. `packages/www/src/hooks/useLanguage.ts:12` returns `'en'` when there is no `window`, and BaseLayout mounted `<Navigation client:idle />` with no `lang` prop, so six SSR'd islands emitted English into `dist/<lang>/index.html` while the Astro-rendered parts of the same page were translated.

## Outcome
SHIPPED. Measured against the tree 2026-09-06, NOT read off the header, which still says `proposed` and is wrong. `packages/www/src/layouts/BaseLayout.astro:377` passes `lang={currentLang}` to Navigation and the five other SSR'd islands; `packages/www/src/components/Navigation.tsx:41` prefers the prop over the hook. The gate the plan called the half that matters exists as
`scripts/gates/check-ssr-locale.ts`, wired as `check:ci-ssr-locale`. Landed in f7a5351a9. The hook itself is deliberately unchanged, as the plan said.

## Lessons
- Three lines of fix; the durable half is the gate that reads built HTML,
because browser-smoke is blind to SSR output by construction.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: proposed
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:05:28Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: packages/www/src/hooks/useLanguage.ts, packages/www/src/layouts/BaseLayout.astro
Gates: check:ci-browser-smoke, check:ci-hydration-clean, check:i18n:key-usage
Why-Source: author
Read-History: `git show 607afdb545574a449e1959a5adfa926879358bc0` recovers the text; `git log --find-object=607afdb545574a449e1959a5adfa926879358bc0 --all` names the commit

## History
- 2026-09-06T17:05:28Z compacted by 8f55d4f0 from `proposed` (record-sig 3d8aec74)
