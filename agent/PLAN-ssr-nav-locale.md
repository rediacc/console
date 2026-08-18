# PLAN: the nav server-renders in English on all 12 non-English locales

Status: proposed
Owner: e6500e92
Verified against the tree 2026-08-18, branch `main`, everything uncommitted.

## The defect

`packages/www/src/hooks/useLanguage.ts:11-12`:

```ts
let currentLanguage: Language =
  typeof window === 'undefined' ? 'en' : getLanguageFromPath(window.location.pathname);
```

On the server there is no `window`, so **every island using this hook renders English**,
whatever the locale. `packages/www/src/layouts/BaseLayout.astro:364` mounts
`<Navigation origin={Astro.url.origin} client:idle />` with no `lang` prop, so the nav has
no other way to know.

Measured on the 19:41 build, not inferred:

- `dist/de/index.html` and `dist/ar/index.html` both render `Built for you` and
  `Get Started`, while `de.json` holds `Jetzt starten` and `Preise`.
- The Astro-rendered parts of the same page ARE translated
  (`Zum Hauptinhalt springen`), which is what makes it look like a translation gap rather
  than a rendering one.

**Pre-existing, not caused by rounds 1 or 2.** `useLanguage.ts` is unmodified this session,
so `HEAD` is a valid baseline for it, and `git show HEAD:BaseLayout.astro` mounts
`<Navigation>` the same way. (`HEAD` is NOT a valid baseline for files round 1 rewrote, see
the execution guide.)

## Impact

- Crawlers index an English nav on 12 locales.
- No-JS visitors get a permanently English nav.
- Every non-English page flashes English until the island hydrates, then re-renders.

Six islands are SSR'd from `BaseLayout` (`:364-374`): `Navigation`, `ContactModal`,
`RegionPickerModal`, `NewsletterReturnPopup`, `LeadMagnetModal`, `Footer`. Fourteen
components call `useLanguage()`. **Scope the fix by measuring which of the six actually
emit locale text into the HTML** rather than assuming all six.

## The fix

`BaseLayout.astro:52` already computes `const currentLang = lang || getLanguageFromPath(Astro.url.pathname)`.
It is right there and unused by the mounts.

1. Pass it: `<Navigation lang={currentLang} origin={...} client:idle />`, same for each
   affected island.
2. In each island, prefer the prop and fall back to the hook:
   `const currentLang = langProp ?? useLanguage()`. Keep the hook so nothing that mounts
   without a prop regresses.

**Why a prop rather than fixing the hook:** the hook cannot know the path on the server;
Astro can. Any server-side guess inside the hook would re-derive what the layout already
has. Making the prop authoritative also makes server and client agree, which removes a
latent hydration mismatch rather than adding one.

**The store machinery is already moot.** `useLanguage` is a `useSyncExternalStore` that
updates on `astro:after-swap` and `popstate`. `w3-docs` established that **no page renders
`<ClientRouter />`** (the only mention is the comment at `BaseLayout.astro:15-19`
documenting its absence), so `astro:after-swap` never fires. Do not preserve that path at
the cost of a clean prop.

## Tests, each of which must FIRE on a planted defect

This is the half that matters; the fix is three lines.

1. **A gate over the BUILT output.** For each of the 13 locales, assert a known nav string
   in `dist/<lang>/index.html` equals that locale's catalog value, not English. Control:
   plant `en`'s value into the German assertion and require it to fail. This is the check
   that would have caught the defect at any point in its life, and nothing in the current
   suite does: `check:ci-browser-smoke` drives a browser where hydration has already
   corrected the text, so it is blind here by construction.
2. Extend it to every island the measurement in **Impact** shows emits locale text.
3. Re-run `check:ci-hydration-clean`; server and client agreeing should leave it green.

## Verification

`cd packages/www && npm run build`, then the new gate across all 13 locales, plus
`check:ci-browser-smoke`, `check:i18n:key-usage` and `check:ci-hydration-clean`.
Read `dist/ar/index.html` by hand once: RTL plus a non-Latin script is where a
half-applied locale is most visible.

## Not in scope

Fixing `useLanguage` for client-only islands, which already work. Adopting
`<ClientRouter />`. Both are separate decisions.
