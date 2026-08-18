# www simplification — synthesis

**Status:** research complete, plan proposed, **nothing implemented**.
**Date:** 2026-08-17. **Inputs:** the eight `RESEARCH-*.md` documents in this
directory (311 KB), each measured against the live site and both reference sites.

---

## 1. The answer in one sentence

The site is not complex because of how it looks — it is complex because **nothing
is shared**, and every domain found the same shape of defect: a shared thing
already exists, and the code goes around it.

That claim is not a metaphor. It is the literal finding in six of eight reports:

| The shared thing that exists | How it is bypassed | Evidence |
|---|---|---|
| A complete form system | **Zero components use it** | `main.css:2717-2840`; `querySelectorAll` returns 0 on four live pages |
| A `--radius-*` scale | Ignored; `100px` x6, `6px` x5, `3px` x3 hardcoded | `main.css:248-254` |
| A single `:root` token set | **Five** `:root` blocks; the last one silently wins | `BaseLayout.astro:279-414` overrides `main.css` for 17 properties |
| One primary CTA | Implemented **9 times, in two different greens** | `#556B2F` and `#4A7C3F` |
| One card | **33 card shells**, 7 radii, 2 border greys | picked by whichever stylesheet the component was born in |
| One overlay | **6 overlays**; `handleFocusTrap` byte-identical in 3 files | `body.style.overflow='hidden'` written 5x |
| **A scroll-reveal animation system** | Ships on **every page**, used on **8 elements, all below y=3,731px**; `.reveal-stagger` used **zero times** | `main.css:3348-3387` + `public/scripts/scroll-reveal.js`, wired at `BaseLayout.astro:440` |
| One lightbox | **Two.** `ImageModal.astro` + `image-modal.js` cost **~13.7 KB on every page** and fire on none of the homepage, which ships a second, weaker `<dialog>` instead | `HomeDifference.astro:95-97` |

We have a design system. It simply is not connected to anything.

**The corollary matters for sequencing:** most of the win comes from *deleting
the bypasses and connecting the existing layer*, not from designing something
new. This is a subtraction project.

---

## 2. The scorecard

From `RESEARCH-metrics.md`, measured with a fresh browser session per URL
(warm-cache runs silently report `transferSize: 0`).

| Metric | Ours | claude.com | anthropic.com | Ratio |
|---|---:|---:|---:|---:|
| **JS decoded** | **6,998,912 B** | 1,267,131 | 305,858 | **22.9x** |
| Distinct painted colors | **43** | 19 | 18 | 2.4x |
| Distinct painted `font-size` | **23** | 13 | 8 | 2.9x |
| Page height @390x844 | **11,795 px / 14 screens** | 6,608 | 6,407 | 1.8x |
| Boxed surfaces / radii / shadows / borders | **60 / 7 / 5 / 11** | 25 / 6 / 3 / 5 | 26 / **2 / 0 / 1** | — |
| Homepage sections | **9** | 3 | 4 | 3x |
| Nav bar targets | **13** | 9 | 7 | — |
| Mean nav label length | **36.8 ch** | 9.7 ch | short nouns | 3.8x |

**Where we already win, and must not "optimize" out of vanity:** unused-CSS
percentage (ours 77.1%, claude.com 87.9%), DOM nodes and depth (762/11 against
1,149/16 and 1,263/23), and fonts (ours 141 KB; claude.com ships 728 KB). Four
metrics are explicitly proposed as *non*-targets for this reason.

### A methodology conflict, reconciled rather than averaged

`sx-homepage` measured the homepage at **7,697 px** desktop / 14,496 px mobile;
`sx-metrics` measured **6,794 px** / 11,795 px. Neither is wrong. The page grows
as you scroll because `loading="lazy"` images resolve late, and `sx-metrics`
deliberately measured fresh loads for byte-accuracy while `sx-homepage`
deliberately scrolled to the bottom first.

**Rule for this program: the scrolled figure is the user-facing truth, the
fresh-load figure is the byte-accounting truth.** Any before/after comparison
must state which it used. This is written down because averaging them would have
produced a number that describes nothing.

---

## 3. The single largest number is not a design problem

**89.5% of the homepage's bytes are one file.** `assets/react.DrK1BhOX.js` is
6,673,504 B decoded, and it contains **all thirteen locale bundles** — measured:
210,674 Cyrillic characters, 165,430 Arabic, 94,399 Hangul, 93,449 CJK. The
file's first 400 characters are Arabic marketing copy.

The chain: `src/i18n/utils.ts:1-13` statically imports 13 locale JSON files
(9.28 MB on disk) -> `src/i18n/react.ts:3` -> `useTranslation` in twelve hydrated
islands (`Navigation.tsx:4`, `Footer.tsx:7`, ...) -> Rollup hoists the lot into
the shared vendor chunk that **every page loads**.

An English visitor downloads Korean, Arabic, Russian and Japanese marketing copy
to read the homepage.

This is one import chain, it is worth more than every visual change in this
document combined, and it belongs to nobody in the current ownership map. **It is
Wave 0 and it should ship on its own.**

Second-largest: the homepage `<link>`s **three solution-page stylesheets**
(`dev-environments-brief` twice, plus `disaster-recovery`) — 113,970 B, 50.4% of
all CSS parsed on that page, 77-90% of it unused.

---

## 4. The plan

Ordered by leverage. Waves are sequential; specialists inside a wave are
parallel **only where their files are disjoint**.

### Wave 0 — the byte fix (no visual change at all)

**`sx-i18n-ci` found the cause is far narrower than "the site loads 13 locales".
The 6.7 MB chunk exists because TWO call sites read ONE field.**
`MegaMenu.tsx:33` and `Sidebar.tsx:145` are byte-identical
`` to(`pages.solutionPages.${config.contentKey}`) `` and use only
`content?.hero?.title`. Measured: 16 of the 18 islands need <=40 leaves each;
those two pull **6,660**. Narrow them and the entire client need is **240 keys —
15.6 KB for `en`, 224 KB for all thirteen, 2.4% of the 9.28 MB on disk.**

Safe shape, in order: (0) narrow the two `to()` calls; (1) generate
`src/i18n/client/<locale>.json` from `SITE_LOCALES` with a hard error on any it
cannot produce, plus a freshness gate shaped like `check-search-index-freshness`;
(2) `react.ts` reads the small catalogs via `import.meta.glob` eager while
`utils.ts` keeps the full ones for the 55 `.astro` consumers, so
`createTranslator` stays synchronous and no API changes.

**`client/` must be a SIBLING of `translations/`** — three gates derive www's
locale set by listing `translations/*.json`.

The gate exposure is **not** the translation gates. It is `check-locale-sources`
(proven to flag a hardcoded ARRAY but **not** a 13-key OBJECT map or
`import.meta.glob`), plus `types.ts:2`'s type-only `en.json` import and
`types.ts:26`'s compile-time permutation proof, **both of which must survive**.

**Sequencing hazard, do not lose this:** deleting a whole locale file is
invisible to completeness, placeholders and value-types. Exactly one gate catches
it (`check-locale-de-contamination`, which asserts against `@rediacc/locales`).
The other backstop today is the TS build — **and Wave 0 removes it.** Whatever
replaces the static imports must keep an equivalent hard failure.

Still zero design risk and still shippable before any other decision.

### Wave 1 — connect the layer that already exists (`sx-tokens`, then `sx-primitives`)

**These two must not run concurrently. Both edit `public/styles/main.css`.**

`sx-tokens` first, because `sx-primitives` is blocked on it: collapse to one
`:root` in `main.css`, delete the shadowing inline block at
`BaseLayout.astro:279-414`, merge the two brand greens, delete
`--sp-border-light` so it collapses onto `--color-border`, and cut the type scale
to a fixed ladder. Targets: font-sizes 23 -> 8, colors 43 -> 16, radii 11 -> 3,
shadows 6 -> 1.

Then `sx-primitives`: one `.btn`, one `.card`, one `.field` (**adopt the dead
`.form-*` system rather than writing a new one**), one `<Overlay>`, one chip, one
icon stroke weight. Deletes `contact-modal.css` (375), `search-modal.css` (331),
`region-picker.css` (180), `platform-tabs.css` (52) and ~23 KB off *every* route,
since `BaseLayout.astro:240-242` loads three modal stylesheets sitewide.

### Wave 2 — the pages (parallel, disjoint files)

`sx-hero` + `sx-homepage` on the homepage (hero above the fold, sections below);
`sx-pricing` on pricing; `sx-docs` on the docs surface. Each has its own cut list
already written. Headline cuts: `home-difference` 2,202 px -> ~600; delete
`logo-wall` (strictly subsumed by `integrations-strip`) and `metrics-bar`
(duplicates prose 2,200 px above it); 771 dead lines out of `pricing-page.css`;
`DocsLayout.astro:281-617` + `:990-1120` out (-467 lines).

### Wave 3 — turn on the motion we already own

**Corrected by `sx-motion` after this section was first written.** It said "port
claude.com's pattern (12 lines)". That was wrong: **we already ship it.**
`main.css:3348-3387` plus `public/scripts/scroll-reveal.js` (a one-shot
IntersectionObserver) load on every page via `BaseLayout.astro:440`. This is an
*adoption*, not a port — and it is the seventh instance of the thesis in §1.

Ordered: **M0** add `.reveal` above the fold (class attributes only, zero new
code) · **M1** convert icons to filled · **M2** de-text the illustrations,
573 files -> 42 · **M3** unify the 8 hand-drawn cliparts to one weight ·
**M4** the h1 word reveal as a `.reveal` variant.

**The second correction matters more.** This section previously claimed a
`prefers-reduced-motion` guard in `solution-pages.css` was a prerequisite. It is
not — `main.css:365-380` already applies a global `*` reduced-motion nuke plus
zeroed duration tokens, and our coverage (14 blocks + the nuke) sits between
anthropic.com's 5 and claude.com's 29. That is not our gap.

What *is* required is anthropic.com's inversion: the FOUC `opacity:0` rule must
live inside `@media (prefers-reduced-motion: no-preference)`, **because the nuke
zeroes durations and does not undo an opacity**. Get that backwards and a
reduced-motion visitor gets a permanently invisible headline.

**Hard sequencing dependency:** `sx-primitives` owns `main.css:3348-3387`, so the
`no-preference` + `html.js-anim` guard is theirs, and **M0 cannot land before
it** or a no-JS visitor gets a blank homepage.

### Wave 4 — verification

`sx-metrics` re-runs its own recorded snippets. It shipped `hittest.js`
specifically so a re-measurement cannot accidentally claim a fake win.

---

## 5. What the operator asked about, answered

**The anthropic.com "special component" is three stacked moves, not one.** A
word-by-word h1 reveal (~55 lines of inline JS, no library, **random** 100-500 ms
per-word delays — the randomness is why it reads as *settling* rather than
*loading*); a dark card scrubbing `max-width`/`border-radius` to full bleed over
~200 px of scroll; and a 31,754-byte generative SVG constellation costing 787 KB
of webp shown at 49x37 px.

Take the first. Skip the third unless it replaces the fake terminal — the idea is
excellent, the implementation is a bespoke engine with a hard GSAP dependency.

Their hero *proper* is **390 px, 34 words, zero buttons**; its only CTAs are two
underlined words inside the headline. Ours is 910 px, 117 words, 7 focal points.

**Two premises we started with were wrong, and both were corrected by
measurement rather than argued:**

1. *"Their footers are restrained."* They are not. Ours is 23 links / 632 px;
   claude.com is **161 links / 1,070 px**. Their *bars* are restrained, not their
   footers. Our footer is the smallest of the three and is not a problem.
2. *"claude.com/pricing is the exemplar."* It is not. 2,750,570 B of CSS parsed,
   94.7% unused, 6,942 DOM nodes. Our pricing page beats it on everything except
   box density and LCP. Its row count (50 vs our 20) is not its lever either — no
   hero, no billing toggle, and all categories open by default are.

---

## 5b. Icons, drawings and motion (`RESEARCH-motion.md`)

**One decision explains the entire icon delta: they draw FILLED icons, we draw
STROKED ones.**

| | Ours | claude.com | anthropic.com |
|---|---:|---:|---:|
| Inline SVGs | 121, from 4 unrelated sources | 51 | 40 (**0 `<img>` on the page**) |
| Filled : outlined | **20 : 62** | **51 : 0** | 37 : 2 |
| Distinct `stroke-width` | **9** | **0** | 1, and it is a *token* |
| Distinct viewBoxes / rendered sizes | **10 / 10** | 1 / 2 | 3 utilities |

anthropic.com's single stroke weight is
`--nav--icon-thickness: var(--border-width--main)` = 1px — **icon stroke and
border thickness are the same token**. Even their arrow is a filled path with
`stroke: none`.

Ours: **13 duplicated `<path d>` strings**. The check mark is drawn **four
different ways at three weights**; the CTA arrow appears in 5 files.

**Their motion, sampled rather than described** (`document.getAnimations()` every
150 ms): anthropic.com peaks at **22 concurrent**, only ever
`CSSTransition:opacity` and `CSSTransition:transform`, and reaches **zero by
t=1350 ms**. Not one `CSSAnimation`. **81% of transitions are 0.2s, 91% are
`ease`.** claude.com's 11 content keyframes are 9x the *same* animation:
`opacity 0->1` plus `translateY(N)->0`, nothing travelling more than ~20px.

**Ours: `document.getAnimations()` returns 0 at load. Nothing moves, ever.**

**573 illustration files exist to translate 92 words.** `diff` of
`environment-cloning.svg` against its `.de.svg` with `<text>` masked is
byte-identical — the geometry is the same, only baked-in labels differ, in
**7 font stacks none of which is Inter** (0 of 573) at 13 font sizes. That is why
they read as clipart and why there are 26 files per slug. claude.com's three
drawings use `viewBox="0 0 500 500"`, two fills, and **zero `<text>`**.

Dark mode: **521 of 521 open with `<rect fill="#f5f5f5">`**, none use
`currentColor`, none have a theme hook. The favicon is the only theme-switching
SVG in the repo.

We already win on bytes (17.9 KB per homepage against their 56.7 KB), so this is
a coherence problem, not a weight one.

**i18n cost, and the specialist's own default:** de-texting moves 92 strings x 13
locales = **1,196 values** into the pipeline. They already exist inside the SVGs,
so it is an import of real translations rather than net-new copy — but no tool
does that import today. Default if the operator does not rule: do the 4 homepage
drawings only (182 values), prove it, then the 17 solution drawings.
**Superseded — the operator chose the full 573 -> 42 de-texting (§9a.3). All 21
are in; the 4 homepage drawings are simply the first ones through the importer,
because that is where the importer gets proven, not because the rest are
optional.**

---

## 5c. The i18n gates, and what they do NOT catch (`RESEARCH-i18n-ci.md`)

**Every verdict below came from mutating a scratch mirror and running the gate.
None came from reading code.** 20 gate rows, 18 touch www: **15 PROVEN LIVE**,
**1 PROVEN IT CANNOT FIRE**, 2 unproven, 2 CLI-scoped.

**The dead one: `check-docs-untranslated-text`.** A wholly English paragraph was
appended to `content/docs/de/quick-start.md`. Exit 0, "All non-English
documentation appears to be properly translated".

**Three blind spots, all proven:**

1. `check-i18n-cross-locale` **does not scan `packages/www`** — its
   `LOCALE_ROOTS` (`:60-64`) lists cli + account-web + account-src. German *and*
   French planted in `www/it.json` both returned "No cross-locale contamination".
   www is protected against German only, by the separate de-contamination gate.
2. `check-translation-completeness` **rounds untranslated% to one decimal before
   comparing to 0**, so up to 4 English-identical values per locale pass. Measured:
   1/4/5 keys -> exit 0 "(0.0%)"; 9 keys -> exit 1.
3. The naturalization ledger covers **1,864 of 8,469 English keys (22.0%)**.
   Editing a covered key stales all 12 locales at once; editing any of the other
   **6,605 produces zero gate pressure**.

**Deleting keys has no tooling** — `i18n:sync` only adds. The rehearsed procedure:
deletion reds `check-translation-hashes` ("Keys removed from English"),
`i18n:generate-hashes` clears it, and `check-translation-completeness` is the real
safety net because it names every file with its exact orphan keys. Two mechanical
traps hit for real: a trailing comma when the deleted member is last, and **locale
files are alphabetically sorted while `en.json` is authored-order** — locate by
key name, never by position. Confirmed caution: `generate-hashes` also rewrote
`$meta.sourceCommit` in `packages/cli`'s manifest and writes through into
`private/account`.

**146 English leaves are reachable by no path (146 x 13 = 1,898 values)**, from a
conservative analyzer that marks anything a dynamic stem could reach as
UNCERTAIN. **There is no gate for this class at all.** Confirms `sx-pricing`
(`plans.*.features` = 40 strings / 520 values, rendering nowhere; the 12 dead
`ui.*` keys including "Includes $9,999 setup credit") and `sx-docs` (148 of 1,408
search-index entries carry raw `{{t:...}}`, x14 files = 2,072; root cause is
`generate-search-index.js` reading raw markdown without the remark resolution).

**Four data defects no gate can see:**

- **`announcement.enabled` is `false` in `en.json` and `true` in all twelve other
  locales.** English visitors get no announcement bar; everyone else does.
  `value-types` compares types, not values. Lands in `sx-chrome`.
- **2,401 locale values contain an em dash** (ru 374, ar 251, de/tr 243, en 84).
  The gate exists and fires at ERROR on markdown, but `check-content-quality.sh:29-32`
  scans only `content/{docs,blog}` `*.md`/`*.mdx` — the JSON catalogs and 21
  `.astro`/`.tsx` files are outside it.
- **"9 languages" is baked into all 13 catalogs** at
  `pages.pricing.comparison.allPlansInclude` (9 Sprachen, 9 langues, 9 lenguas,
  9 言語, ...), plus `en.json:598` and a hardcoded string at `changelog.astro:67`.
  26 values plus one component string — and `allPlansInclude` is ledger-covered,
  so fixing it stales 12 translations.
- `CONVENTIONS.md` section 3 names eslint rules configured for cli and the account
  portal but **not for www**.

**A live Wave 2 constraint:** three SEO rules DO apply to www's locale JSON at
ERROR — `meta.title` 30-60 chars and `meta.description` 50-160, **in all 13
locales**. Shortening an English meta title reds twelve more files.

**Cost model correction:** the ledger's `$meta.models` records `claude-sonnet-5`
for all twelve languages, not haiku. The last full run was not the cheap one
`CONVENTIONS.md` describes.

Nothing in `.github/workflows/ci.yml` needs to change for any proposed gate fix.

---

## 5d. The anchor bug is site-wide, not a non-Latin bug (`RESEARCH-rtl-anchors.md`)

**Correcting my own earlier framing.** I reported "5 of 13 locales broken, 8
fine, split on Latin vs non-Latin script". That was wrong, and it was wrong
because my metric — TOC hrefs that are empty or digits-only — only detects
*total script loss*. Live-crawled across every page and locale:

**1,107 pages, 963 carrying a dead anchor (87.0%). 15,521 in-page links, 8,013
dead (51.6%).** Docs 886/1015, blog 77/92. **Every locale is broken, English
included.**

**Root cause: two slug algorithms over the same heading text.**

- The **id** comes from Astro's default `rehypeHeadingIds` (github-slugger),
  because `astro.config.mjs:168-175` sets `remarkPlugins` and **no
  `rehypePlugins`**. It preserves Unicode and deduplicates.
- The **href** comes from `stringToSlug` (`src/utils/slug.ts:6-13`), called at
  `src/utils/sidebar-behavior.ts:86`. Its `.replaceAll(/[^\w\s-]/g,'')` has **no
  `u` flag**, so `\w` is exactly `[A-Za-z0-9_]` and every non-ASCII character is
  deleted. It also does not deduplicate.

**The kicker:** `generateTOCFromHtml`'s regex
`/<h([2-6])[^>]*>(.*?)<\/h\1>/gi` (`sidebar-behavior.ts:62`) **captures the
attributes in `[^>]*` and discards them**, then re-derives an id from the text.
The correct id was already in the tag it just matched.

English fails through the same function by a different door: `&`, `/` and `+`
leave a doubled hyphen (`members--roles` vs `members-roles`), and repeated
headings get numbered `-1`/`-2` by github-slugger but not by `stringToSlug`, so
`cli-application.md` emits `#set` several times — dead **and** ambiguous. 18 of
79 English docs pages, 36 dead links, 28 duplicate fragments. Accented Latin
locales fail the same way (`größe-ändern` -> `gre-ndern`).

**The "baseline of 1" in every locale is the `&` family — the same bug's ASCII
face, not a separate smaller bug.**

Third symptom, one cause: scroll-spy at `DocsLayout.astro:642` looks up
`a[href="#${id}"]` with the real id and never matches. Proven live: English
highlights the current section, Arabic highlights nothing.

**Rest of the class:**

- **`category` frontmatter is translated** in `cli-application.md` in all 12
  locales, and `DocsTopTabs.astro:29-32` falls back to the raw string — so every
  non-English docs page renders **7 tabs instead of 6**, and in Arabic the label
  `مرجع` appears twice.
- **Search discards the anchor it computed.** `generate-search-index.js:202-217`
  indexes per-section but writes `page` with no fragment; `SearchModal.tsx:152-153`
  then dedupes by page. Search knows the section and always lands you at the top.
- **`BaseLayout.astro:65` hardcodes `currentLang === 'ar' ? 'rtl' : 'ltr'`** —
  `site-locales.json` carries no direction metadata, so there is nowhere correct
  to read it from. A hand-rolled locale check, the exact shape this repo has
  been burned by before.
- **The fix model already exists in-repo:** `privacy-policy.astro:46` reads a
  stable ASCII `id` from the catalog, identical in all 13 locales, with only the
  `title` translated.
- Clean: zero DOM id collisions, all `aria-labelledby` resolve.

**RTL, underneath a correct `dir="rtl"`:** the share control covers the first
40px of **every** h2/h3 in Arabic (`DocsLayout.astro:990-1001` uses physical
`padding-right` and `right: 0`; `مقدمة` renders as `دمة`); code blocks inherit
`direction: rtl` so a shell command with an Arabic comment reorders; the
alternating zig-zag layout on `/pricing` no-ops in Arabic (measured: English
alternates, Arabic is `[721,113]` six times); **144 physical inline-axis CSS
properties against 37 logical ones, and exactly 6 `[dir='rtl']` rules site-wide**;
`▶` chevrons are literal U+25B6 and never mirror; `ar.json` holds 31 `→` and 28
`←`, half-mirrored by the translator.

**How claude.com solves it:** `docs.claude.com/ja/docs/get-started` has Japanese
headings and **English fragments identical to the `/en` page**
(`#prerequisites`, `#call-the-api`), 0 broken. They slug the English source once
and carry it across locales.

**No gate validates that an in-page fragment resolves, and neither slug function
has a unit test.** Proposed `gate-test:anchor-integrity` with four mutation
plants that must all fire, including an unknown `dist/` locale dir and a missing
modelled locale, deriving its locale set from `@rediacc/locales`.

**Fix, not implemented.** F1 is small: have `generateTOCFromHtml` read the `id`
it already matched. `stringToSlug` then has zero callers and is deletable.
F2 is durable: stable English fragments per docs.claude.com — feasible, since
**920 of 936 translated files (98.3%) already have the same heading count as
their English counterpart**, leaving 16 for a hand pass.

---

## 5e. The bug hunt (`RESEARCH-bugs.md`)

**5 high, 11 medium, 8 low.** Coverage: 56 routes x 2 viewports x 2 themes, plus
7 locales x 5 pages x 2 viewports, the production funnel, and every form
submitted both empty and filled. **Every high was re-confirmed against
`www.rediacc.com`**, so none is a dev-server artifact.

1. **`/ar/contact` and `/ar/partners` have ~10,000px of blank horizontal
   scroll** (9,823 and 9,984 px, 3/3 reproductions, both viewports). The honeypot
   is hidden with `left:-9999px` (`contact-modal.css:286-292`,
   `partners.astro:517-523`); under `dir=rtl` the left edge is the *trailing*
   edge, so it becomes scrollable. Arabic visitors scroll the two lead-capture
   pages into a white void.
2. **The homepage and pricing page scroll horizontally on production** — 133px at
   1440, 228-244px at 390, **up to 398px in `ja`/`de`/`ru`**. Leaf cause:
   `.cf-feature-info::after` is `position:absolute; white-space:nowrap;
   opacity:0` (`pricing-page.css:1804-1820`), so a 575px tooltip stays in layout.
3. **React hydration failure on `/install`, on production.** The server commits to
   "All Methods" and the client to the detected platform, so React discards the
   whole `<InstallMethods>` tree. Cause: the `typeof window === 'undefined'`
   branch in a `useState` initializer (`InstallMethods.tsx:134-145`). **It is the
   only JS page error on the entire site.**
4. **An empty contact submit answers "Something went wrong. Please try again."**
   — `noValidate` with no client-side replacement (`ContactForm.tsx:120`,
   `ContactModal.tsx:232`). A blank form reads to the user as a broken site.
5. **An empty newsletter or lead-magnet submit does nothing at all** —
   `if (!email) return;` (`NewsletterSignup.tsx:45`, `LeadMagnetModal.tsx:133`).
   A dead button on the site's main email capture.

**Two whole classes, not five instances:**

- **Hidden without being removed from layout.** #1 and #2 are the same mistake
  twice: invisible by offset or by opacity, still occupying scroll extent. Sweep
  every `opacity:0` pseudo-element and every negative-offset hide, and check each
  under `dir=rtl`.
- **Validation switched off with no replacement.** Five of six forms set
  `noValidate`; exactly one (`PartnerApplicationForm.tsx:147-156`) then implements
  the check it disabled. The pattern to adopt already exists in the repo — §1's
  shape again.

**Reconciling an apparent conflict, because two specialists disagreed.**
`sx-process` and I both scanned `/en` at 1440 for elements exceeding the viewport
and both found **none**, concluding the off-canvas `aside.sidebar` was the cause.
`sx-bughunt` traced it to `.cf-feature-info::after`. Both scans were wrong in the
same way: **`querySelectorAll('*')` does not return pseudo-elements**, and
`::after` is where the overflow actually lives. Treat `sx-bughunt`'s leaf cause as
authoritative and the "zero visible offenders" result as an artifact of the
method, not evidence.

**What survived scrutiny, and is worth knowing before anyone rewrites things:**
zero broken routes, all 103 unique internal hrefs resolve, no broken images, no
unexpected hosts, no leaked keys, and every fetch-backed form has a real error
branch. The mobile drawer is correct (focus, scroll lock, Escape,
`tabindex="-1"` when closed). The mega menu **opens fine from the keyboard** — the
known "clicking Solutions closes it" defect is mouse-only. The production funnel
completes and carries the plan.

---

## 5f. The solution constellation (`RESEARCH-navigator.md`)

**Two corrections to the premise, both from driving the live site.**

1. **The constellation is not in anthropic.com's hero.** It starts at document
   Y≈958, inside the dark "hard questions" card. The actual hero is a headline
   and a paragraph, nothing else.
2. **It is not clickable.** Measured `pointer-events: none` on both
   `.ktve-stage` and `svg.ktve-net`, with `aria-hidden="true"` on the stage. So
   an interactive version is something *they did not build*, and every
   accessibility question it raises is ours to answer from scratch.

**Is there structure worth encoding? Yes — but not the shipped taxonomy.** The 21
pages are three verbs on one primitive, which is the hero sentence itself:
**Copy (4) -> Test (7) -> Recover (5)**, plus 5 pages that are platform
*properties* rather than uses. The shipped six-category taxonomy is a
market-segment split and is wrong in at least two places: `migration-safety` is
filed under `encryption` (`solution-pages.ts:215-217`) while making no encryption
claim, and `rapid-recovery`/`instant-recovery` are near-twins in different
categories. **A constellation laid out on the shipped categories would be
decoration with extra steps.**

**The design.** Two layers. The SVG carries **only** the 29 hair-thin edges and
stays `aria-hidden` + `pointer-events:none`, exactly as decorative as theirs. The
nodes are **real HTML `<a>` elements** in a `<nav aria-label="Solutions">`,
absolutely positioned from the same build-time coordinate array — which buys real
focus rings, middle-click, crawlable hrefs, native per-locale text wrapping, and
no SVG-text RTL hazard. Layout is deterministic polar math from a new `role`
field. The popup is one reused platform `<div popover>` that always opens **in
the empty centre**, which removes any need for CSS anchor positioning (not
baseline). **No idle breathe loop** — the single biggest departure from theirs: a
target that drifts under the cursor is a Fitts's-law tax. All motion stops by
~1,400 ms. Budget: **~4.0 KB raw, 1.6 KB of it JS, zero images**, against their
31,754-byte IIFE plus 787 KB of webp.

**What it replaces:** the `/solutions` index (125 L), `SPExploreSolutions` (48 L),
`SPRelatedSolutions` (49 L), `.sp-explore*` CSS (97 L), `MegaMenu.tsx` (276 L),
`mega-menu.css` (184 L), the Sidebar solutions accordion (~80 L) and its CSS
(116 L) — **-975 lines / -27.1 KB of source.**

**The real prize is i18n, and it is large.** `explore.solutions[]` is a
denormalised table storing every short label an average of **9 times** (180
entries over 20 slugs; three slugs appear 21x each) = **540 values x 13 locales =
7,020**, replaced by 42 keys x 13 = 546. **Net -6,474 locale values** — and the
546 replacements **already exist and are already naturalized**, verified in
de/ja/ar/tr. Only two need a human: `data-sovereignty` has no short label
anywhere, and `vendor-lock-in` has two divergent English titles.

**The honest argument against, which the specialist made itself:** it does not
solve the measured problem. The 36.8-character nav labels are fixed by the label
harvest alone, with **zero new components**. Spatial navigation is worse than a
list for finding a *known* item, and `RESEARCH-chrome.md` measured **zero
marketing pages in the search index**, so if this becomes the primary path to 21
pages there is no fallback. It only subtracts if three separate deletion
decisions are taken; take none and the site gains a **fourth** nav system on top
of three.

**ORDERING, NOT DESCOPING.** The specialist's recommendation was phrased as
"build the 4-node variant and defer the 21-node one". **That framing is rejected**
— the operator runs big-bangs and does not accept deferral, and this repo's
standing rule is that an approved big-bang is never quietly descoped. Both
variants are IN. What the finding actually establishes is a **dependency order
inside the one change**:

1. `role` re-taxonomy (Copy / Test / Recover / property) — the constellation's
   geometry is meaningless without it.
2. Label harvest — normalise `explore.solutions[]` into 42 keys. **-6,474 locale
   values**, replacements already naturalized, 2 need a human.
3. Full 21-node constellation, built on the two above.
4. The compact 4-node variant is the *same component* with a filtered node set,
   dropped into the hero slot the deleted terminal vacates. It is a render mode,
   not a smaller substitute.

Steps 1 and 2 are prerequisites because the thing cannot be built correctly
without them, which is a different statement from "do them first and see how we
feel."

**Two defects found in passing:** `SPExploreSolutions.astro:37` and
`solutions/index.astro:66` render the raw category **slug** as visible text
(`dev env`, `multi cloud`) in all 13 locales — **180 untranslated strings per
locale** — while the correctly translated `solutions.categories.*` labels are used
three lines away. No i18n gate catches it because the string is derived at
runtime. And the six category colours are literal hex at
`solution-pages.css:1853-1870`, with no token and no dark-mode variant.

---

## 6. Correctness findings — separate from the design work

These are defects, not opinions. They do not get fixed by simplification and must
not be lost inside it.

**Live on production, verified by `curl` against `www.rediacc.com`:**

- **`<div class="cf-badge">Strategic anchor</div>` ships on the Enterprise card**
  of `/en/disaster-recovery`, beside a `Best Value` badge on Business. That is
  the internal term for a decoy tier, rendered as visitor-facing copy. Confirmed
  a genuine defect.
- **CORRECTED by the operator, 2026-08-17.** This section previously called the
  `/en/disaster-recovery` prices ($1,299 / $3,999 against `/en/pricing`'s
  $49 / $59) a contradiction. **They are not.** Disaster recovery is a
  **human-delivered services offer**, not the software subscription, so the
  prices are correct and intentional. `sx-pricing` inferred a bug from the price
  gap alone; the gap was the point.

  What survives is narrower and still real: the page renders those services
  through the **same `CfPricingCard` component under the identical plan names**
  — `Professional`, `Business`, `Enterprise` — as the software page, with
  nothing on the card saying one is a service engagement and the other a
  subscription. That is a labelling problem, not a pricing one. Fix the label,
  never the number.

- **WITHDRAWN, corrected by the operator.** The "3.2 TB in 4.7 s vs 241 GB in
  under 60 s" contradiction is not a contradiction: **they are different tests
  and both figures are stable.** Do not re-file this. The only residue is
  editorial — two benchmarks with very different per-byte rates sit 4,934px apart
  with no context tying them together — and that is a copy decision, not a defect.

**Elsewhere:**

- Clicking "Solutions" **closes** the mega menu — hover-intent and `onClick` both
  call `onToggle` (`MegaMenu.tsx:128-133,159`). The trigger advertises
  `aria-haspopup="menu"`.
- The nav is the **sole cause of horizontal overflow at 390 px**; the language
  globe is off-screen at 360, 390 and 414 px, and **both CTAs are
  `display:none` on mobile** — phones get three icons and no call to action.
- The homepage claims **3.2 TB in 4.7 s** (hero) and **241 GB in under 60 s**
  (`metrics-bar`) — ~170x apart per byte. "241 GB" has no provenance outside
  `en.json`.
- Site search returns **"Pruning"** as result #1 for the query `pricing`. Its
  index covers 87 pages, all `/docs` and `/blog` — zero of the 21 solution pages,
  pricing, partners or personas — and 148 entries carry raw `{{t:...}}`
  placeholders.
- `#image-modal` is `aria-hidden` while containing focusable buttons, on **every
  page** (`BaseLayout.astro:430`).
- The docs share menu **corrupts every heading's accessible name**:
  `h2.textContent` reads `"IntroductionCopy sectionvCopy section link..."`.

**Dead code that is dead for a reason — do not sweep it up.**
`SPSocialProof.astro` and its re-enable comments are a deliberate record tied to
rediacc/console#519 (fabricated social proof). `sx-homepage` separately confirmed
there is **no fabricated social proof on the homepage today**: no testimonials, no
customer logos, and `LogoWall.tsx` renders technology categories despite its name.

---

## 7. Two instruments that lied, recorded so they are not trusted again

- **`agent-browser a11y` reported `violations: 0`** on our hero. It had silently
  downgraded all 30 nodes to *incomplete* because two decorative gradient
  pseudo-elements defeated its backdrop resolution. Four contrast failures were
  then measured by hand (3.72:1, 2.24:1, 3.37:1, 3.82:1).
- **`AGENT_BROWSER_SCREENSHOT_DIR` is ignored** by `agent-browser 0.34.0` — a bare
  filename resolves against the working directory. It put three untracked PNGs
  into `packages/www/` before it was caught. Absolute paths only; see `00-BRIEF.md`.

- **`agent-browser diff screenshot --output <path>` writes no file.** It prints
  `Diff image: <path>` and nothing is there, verified twice. The **verdict** is
  sound — a control fired at 100.00% and at 0% — only the image is fiction. Use
  ImageMagick `compare a.png b.png diff.png`.
- **`npm run ci --changed` is a no-op.** The manifest declares zero `paths:`
  entries, and `run.ts:194-197` always selects an entry with no declared paths,
  so it runs all 232 gates (~95 min serial). `--only <glob>` is the real knob —
  but `ci:list` short-circuits before `select()`, so `ci:list --only ...` prints
  every gate and misrepresents what would run.
- **`agent-browser errors --clear` does not clear.** Proven: 3 errors, clear,
  still 3. `sx-bughunt`'s first sweep reported errors on **47 of 56 routes**, and
  all 47 were the same retained `/install` error. Use a cumulative delta.
  `console --clear` does work.

Three near-misses worth the same treatment:

- The naive above-fold interactive count read **51 for us against 18 and 17** — a
  flattering 3x. Hit-testing with `elementFromPoint` gives **15 vs 17 vs 17**. The
  gap was pre-rendered mega-menu DOM, not visual density.
- A naive `aria-hidden` + focusable scan **over-reports by 2x** unless it filters
  on `tabIndex >= 0`. `#navigation-sidebar` is clean; `#image-modal` genuinely
  puts 6 invisible buttons in the tab order of every page.
- **`querySelectorAll('*')` does not return pseudo-elements**, which is why two
  independent scans for horizontal-overflow culprits both returned "none" while
  the real culprit was an `::after`. Any overflow hunt must inspect pseudo-elements
  separately.

---

## 7b. Regression gates — the operator asked for these explicitly

*"Wouldn't it be nice if we also enhance `.github/workflows/ci.yml` for
regression?"* Yes, and it is the half of this program that makes the other half
stick. Every bug below was found by hand because **no gate could have caught it**.
`sx-i18n-ci` confirmed nothing in `.github/workflows/ci.yml` itself needs to
change: gates are reached through `npm run ci` and the manifest at
`scripts/ci-runner/manifest.ts`, so these are new manifest entries plus scripts.

**Each gate must ship with the mutation that proves it fires.** This repo has
already paid for the alternative: `check-docs-untranslated-text` is PROVEN dead,
and `--changed` is a no-op that looks like a feature.

| # | Gate | Catches (all found by hand this session) | Proof it fires |
|---|---|---|---|
| G1 | `anchor-integrity` | 8,013 dead in-page links across 963 pages | 4 plants: a `&` heading, a duplicate heading, an unknown `dist/` locale dir, a missing modelled locale |
| G2 | `layout-overflow` | ~10,000px RTL scroll on `/ar/contact`; 133px desktop; 398px in `ja`/`de`/`ru` | plant an `opacity:0` `white-space:nowrap` pseudo-element. **Must inspect pseudo-elements** — `querySelectorAll('*')` misses them, which is why two scans reported "none" |
| G3 | `hydration-clean` | the `/install` React tree discarded in production | plant a `typeof window` branch in a `useState` initializer |
| G4 | `client-bundle-budget` | the 6.7 MB chunk returning after Wave 0 | raise the budget below the current figure and watch it red |
| G5 | `dead-translation-keys` | 146 unreachable English leaves = 1,898 values. **No gate exists for this class at all** | plant an orphan key |
| G6 | fix `check-docs-untranslated-text` | it is PROVEN dead — an English paragraph in `content/docs/de/quick-start.md` exits 0 | the same paragraph must now red |
| G7 | widen `check-i18n-cross-locale` | it does not scan `packages/www`; French planted in `www/it.json` passed | plant French in `www/it.json` |
| G8 | fix `check-translation-completeness` rounding | it rounds to one decimal before comparing to 0, so 4 English-identical values pass | plant exactly 4 |
| G9 | widen the em-dash gate | **2,401 locale values contain one**; the gate only scans `content/{docs,blog}` markdown | plant one in a JSON catalog |
| G10 | `form-validation` | 5 of 6 forms set `noValidate` with no replacement | plant a sixth |
| G11 | declare `paths:` in the manifest | `--changed` runs all 232 gates (~95 min) because zero entries declare paths | touch one file, assert the selected set shrinks |
| G12 | `locale-config-divergence` | **operator-requested.** `announcement.enabled` is `false` in `en.json` and `true` in all twelve others; `check-translation-value-types` compares TYPES, not VALUES, so a config flag can diverge silently | plant a boolean flip in one locale, and a second plant where only the *string* differs to confirm the gate does not fire on ordinary translated copy |

**Sequencing:** G1-G3, G6-G9 encode bugs that exist **today**, so they go in
RED-first, before the fix, and turn green as each fix lands — that is the proof
the fix worked. G4 and G11 are budgets and go in after Wave 0. G5 and G10 can
land any time.

**Cost constraint:** `.ci/cache/gate-durations.json` puts the full serial suite at
**5,694 s (95 min)**, and `quality-i18n` already pays a ~100s R2 restore before
any i18n gate runs. Adding eleven gates without declaring `paths:` (G11) makes
every run slower for everyone, so **G11 is a prerequisite, not a nice-to-have.**

---

## 8. Ownership gaps to close before Wave 1

Three files no specialist claimed: `PartnerApplicationForm.tsx` (441 lines, the
largest form) with `partners.astro`, `SearchModal.tsx` with `search-modal.css`,
and `scripts/generate-search-index.js` (required for the search fix). Plus the
Wave 0 i18n chunking, which sits outside every current boundary.

---

## 9a. DECIDED by the operator, 2026-08-17

These are settled. Do not re-open them, and do not quietly descope them.

1. **Scope: EVERYTHING rides one big-bang change.** Design simplification + all
   24 bugs + the 11 regression gates of §7b, on one branch. Gates go in
   **RED-first** where they encode a bug that exists today, so each fix turns one
   green and the gate and the fix prove each other.
2. **Anchors: F1 AND F2 together.** Read the id already matched (deleting
   `stringToSlug`), *and* move to stable English fragments across all locales as
   `docs.claude.com` does. This also fixes the 30 hand-written dead anchors and
   makes the search fragment locale-independent by construction. 16 of 936 files
   need a hand pass.
3. **Illustrations: the full de-texting, 573 files -> 42.** 92 strings become
   live text, **1,196 locale values enter the pipeline**, 531 files deleted.
   Note the hard part, which is not the SVGs: the translations already exist
   *inside* the SVGs and **no tool imports them**, so that importer is part of
   the work, not an afterthought. This also resolves the dark-mode failure, since
   521 of 521 currently open with a hardcoded `#f5f5f5` background.
4. **The hero's fake terminal: DELETE it.** Largest object above the fold, fails
   contrast in three classes, breaks at 390px, and ships a disclaimer apologising
   for being simulated. Neither reference site puts a simulated artifact in its
   hero.

5. **Disaster recovery: rename the service tiers.** Give the engagement its own
   tier names so nothing collides with the subscription plans. No shared-component
   surgery, and it removes the price confusion at the source.
6. **`announcement.enabled`: off everywhere.** English is correct; the twelve
   other locales are stale and get set `false`. **The operator explicitly asked
   for a CI check so this class cannot regress** — see G12 in §7b.
7. **Community: keep it hidden.** It is a real state, not a product — the
   operator confirms `private/account` **switches an account back to community
   when payment lapses or a trial is cancelled**. So it must not be marketed:
   remove the full comparison column it currently occupies, and do not add a
   card or a signup path. Its FAQ entry, which contradicts that table on three
   points, goes with it.

**Consequence to carry into planning:** decisions 2 and 3 together put roughly
**1,200 locale values plus a 16-file hand pass** into the i18n pipeline.

**Correction to §5c's cost note, from the operator:** the ledger recording
`claude-sonnet-5` for all twelve languages is **deliberate, not drift**. They run
translations through **sub-agents on sonnet to save cost**, which is cheaper in
practice than the per-key model the ledger implies. Do not "fix" this back to
haiku.

---

## 9. Decisions still genuinely the operator's

1. **The disaster-recovery prices.** What should they be? Nothing proceeds on
   that page without a number.
2. **The fake terminal in the hero.** Delete it, or fix its contrast and mobile
   wrapping? It is the largest object above the fold, fails contrast in three
   classes, breaks at 390 px, and ships a disclaimer apologising for being
   simulated. Neither reference site puts a simulated artifact in its hero. This
   is positioning, not design.
3. **The nav label bill.** Relabelling 21 solution pages to short nav labels costs
   21 keys x 13 locales = **273 naturalized strings**. The cheaper alternative is
   collapsing the mega menu to its 6 category links plus "View all".
4. **Blog and Partners** — demote from the bar to the footer they are already in?
5. **`sp-why-now`** (786 px) — subpage or cut?
6. **Community** — is it a plan or a state? It has a full comparison column, no
   card, and no way to obtain it.
