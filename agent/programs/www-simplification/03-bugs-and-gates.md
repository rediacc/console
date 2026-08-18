# 03. Bugs and gates

Status: **verified 2026-08-17**, every high-severity item re-confirmed against
`https://www.rediacc.com` rather than the dev server. Re-verify before fixing.

Counts: **5 high, 11 medium, 8 low** from the systematic hunt, plus the anchor
class and the RTL class below. Coverage was 56 routes x 2 viewports x 2 themes,
7 locales x 5 pages, the production funnel, and every form submitted empty and
filled.

## High severity

1. **`/ar/contact` and `/ar/partners` scroll horizontally by about 10,000 px**
   (9,823 and 9,984, reproduced 3 of 3, both viewports). The honeypot is hidden
   with `left:-9999px` (`contact-modal.css:286-292`, `partners.astro:517-523`);
   under `dir=rtl` the left edge is the trailing edge, so it becomes scrollable.
   Arabic visitors scroll two lead-capture pages into a white void.
2. **The homepage and pricing page scroll horizontally on production** - 133 px at
   1440, 228 to 244 px at 390, up to **398 px in `ja`/`de`/`ru`**. Leaf cause:
   `.cf-feature-info::after` is `position:absolute; white-space:nowrap;
   opacity:0` (`pricing-page.css:1804-1820`), so a 575 px tooltip stays in layout.
3. **React hydration fails on `/install` in production.** Server commits to "All
   Methods", client to the detected platform, so React discards the whole
   `<InstallMethods>` tree. Cause: a `typeof window === 'undefined'` branch in a
   `useState` initializer (`InstallMethods.tsx:134-145`). The only JS page error
   on the entire site.
4. **An empty contact submit answers "Something went wrong. Please try again."**
   `noValidate` with no client-side replacement (`ContactForm.tsx:120`,
   `ContactModal.tsx:232`). A blank form reads as a broken site.
5. **An empty newsletter or lead-magnet submit does nothing at all** -
   `if (!email) return;` (`NewsletterSignup.tsx:45`, `LeadMagnetModal.tsx:133`).
   A dead button on the main email capture.

## The anchor class

**963 of 1,107 pages carry a dead anchor (87.0%). 8,013 of 15,521 in-page links
are dead (51.6%).** Docs 886/1015, blog 77/92. **Every locale, English included.**

Two slug algorithms over the same heading text: ids come from Astro's default
`rehypeHeadingIds` (github-slugger, Unicode-preserving, deduplicating) because
`astro.config.mjs:168-175` declares no `rehypePlugins`; hrefs come from
`stringToSlug` (`src/utils/slug.ts:6-13`) whose `[^\w\s-]` has **no `u` flag**.
`sidebar-behavior.ts:62` captures the correct id in `[^>]*` and discards it.
Scroll-spy fails for the same reason (`DocsLayout.astro:642`).

English fails by a different door: `&`, `/` and `+` leave a doubled hyphen, and
repeated headings get numbered by one slugger and not the other, so
`cli-application.md` emits `#set` several times, dead **and** ambiguous.

Same root, "locale-derived values used as identifiers":
- Translated `category` frontmatter makes every non-English docs page render
  **7 tabs instead of 6**, with `مرجع` twice in Arabic (`DocsTopTabs.astro:29-32`).
- Search computes a per-section anchor then discards it
  (`generate-search-index.js:202-217`, `SearchModal.tsx:152-153`).
- `BaseLayout.astro:65` hardcodes `currentLang === 'ar' ? 'rtl' : 'ltr'` because
  `site-locales.json` carries no direction metadata.
- `SPExploreSolutions.astro:37` and `solutions/index.astro:66` render the raw
  category **slug** as visible text (`dev env`, `multi cloud`) in all 13 locales.

The fix model already exists in-repo: `privacy-policy.astro:46` reads a stable
ASCII `id` from the catalog with only the title translated.

## RTL, underneath a correct `dir="rtl"`

The share control covers the first 40 px of **every** heading in Arabic, so
`مقدمة` renders as `دمة` (`DocsLayout.astro:990-1001`, physical `padding-right`
and `right: 0`). Code blocks inherit `direction: rtl`, reordering shell commands
with Arabic comments. The alternating zig-zag on `/pricing` no-ops in Arabic.
Site-wide: **144 physical inline-axis properties against 37 logical ones, and
exactly 6 `[dir='rtl']` rules.** `▶` chevrons are literal U+25B6 and never mirror.

## Also confirmed

- Clicking "Solutions" **closes** the mega menu; hover-intent and `onClick` both
  call `onToggle` (`MegaMenu.tsx:128-133,159`). Mouse-only; the keyboard path works.
- **CORRECTED 2026-08-18, this document was wrong.** It said "the nav is the sole cause
  of 390 px overflow". On `/en` that is false. `w6` built a rig isolating the change and
  measured `documentElement.scrollWidth` **634 -> 375** against a 390 clientWidth, so
  overflow went **244 px -> 0**, and essentially all of it was the same
  `.cf-feature-info::after` that caused the 133 px at 1440. The nav cluster does stick
  out 15 px (`div.nav-right` right edge at 405) in all three builds, but the page does
  not scroll sideways because of it. The claim came from a sweep that could not see
  pseudo-elements, which is the recurring error in this programme.
- **Both CTAs are `display:none` on mobile**, so phones get three icons and no call to
  action. That half of the original finding stands.
- Search returns **"Pruning"** as result 1 for the query `pricing`. The index
  covers 87 pages, all docs and blog, none of the 21 solutions or pricing, and
  148 entries carry raw `{{t:...}}` placeholders.
- `#image-modal` is `aria-hidden` while holding 6 focusable buttons, on every page.
- The docs share menu corrupts every heading's accessible name.
- `announcement.enabled` is `false` in `en.json` and `true` in all twelve others.
- **2,401 locale values contain an em dash** (ru 374, ar 251, de/tr 243, en 84).
- "9 languages" is baked into all 13 catalogs; the site ships 13.
- 146 English leaves are reachable by no path (1,898 values). 520 `plans.*.features`
  strings render nowhere. 12 dead `ui.*` keys, one reading "Includes $9,999 setup
  credit".

## What survived scrutiny, so nobody "fixes" it

Zero broken routes. All 103 unique internal hrefs resolve. No broken images, no
unexpected hosts, no leaked keys beyond the public Turnstile site key. Every
fetch-backed form has a real error branch and posts to `window.location.origin`
rather than a hardcoded host, which is deliberate and documented at
`src/utils/marketing-host.ts:1-40`. The mobile drawer is correct. The production
funnel completes. **No fabricated social proof**: no testimonials, no customer
logos; `LogoWall.tsx` is misleadingly named but renders technology categories.

## The 12 gates

Each ships with the mutation that proves it fires. This repo has already paid for
the alternative: `check-docs-untranslated-text` is **proven dead** (an English
paragraph in a German doc exits 0), and `--changed` is a no-op that looks like a
feature. Nothing in `.github/workflows/ci.yml` needs to change; gates are manifest
entries in `scripts/ci-runner/manifest.ts` plus scripts.

| # | Gate | Catches | Proof it fires |
|---|---|---|---|
| G1 | `anchor-integrity` | 8,013 dead links across 963 pages | 4 plants: an `&` heading, a duplicate heading, an unknown `dist/` locale dir, a missing modelled locale |
| G2 | `layout-overflow` | the RTL 10,000 px, 133 px desktop, 398 px in ja/de/ru | plant an `opacity:0` `white-space:nowrap` pseudo-element. **Must inspect pseudo-elements.** ASSERT THE SYMPTOM (`scrollWidth > clientWidth`) AND ATTRIBUTE BY BISECTION: three causes have now been found on three pages, a pseudo-element, a table cell and a grid, and a gate written to look for any one of them would miss the others |
| G3 | `hydration-clean` | the `/install` tree discarded | plant a `typeof window` branch in a `useState` initializer |
| G4 | `client-bundle-budget` | the 6.7 MB chunk returning | set the budget below the current figure and watch it red |
| G5 | `dead-translation-keys` | 146 unreachable leaves; **no gate exists for this class** | plant an orphan key |
| G6 | fix `check-docs-untranslated-text` | it is proven dead | the same English paragraph must now red |
| G7 | widen `check-i18n-cross-locale` | it does not scan `packages/www` | plant French in `www/it.json` |
| G8 | fix `check-translation-completeness` rounding | rounds to 1dp, so 4 English-identical values pass | plant exactly 4 |
| G9 | widen the em-dash gate | 2,401 locale values carry one; it only scans docs/blog markdown | plant one in a JSON catalog |
| G10 | `form-validation` | 5 of 6 forms set `noValidate` with no replacement | plant a sixth |
| G11 | **REVISED, and DONE.** Make `--changed` report honestly | it ran all 232 gates while its note read like a narrowed run | done: with zero `paths` it now prints `SCOPED NOTHING: no gate declares paths, so all 232 gates are selected`; planting `paths` on one gate flips it to `1 gate(s) path-scoped` |
| G12 | `locale-config-divergence` | `announcement.enabled` diverging; value-types compares TYPES not VALUES | plant a boolean flip, **and** a plant where only the translated string differs, which must NOT fire |

**G11 was specified wrongly and the code corrected it.** This document originally
said "declare `paths:` in the manifest". Reading `scripts/ci-runner/manifest.ts:70-76`
and `run.ts:193-196` showed that is the one thing the design forbids: an entry
without `paths` is deliberately ALWAYS selected, because *"a half-populated path
table would make `--changed` drop gates silently, which is the vacuity failure
this design exists to prevent."* Declaring paths piecemeal would have introduced
exactly the failure the twelve gates exist to catch.

The real defect was narrower and is now fixed: the selection was safe, but the
note read like a narrowed run, which is how a research pass concluded the flag
was broken. `--changed` now says out loud when it scoped nothing. An instrument
that reports work it did not do is the same class of defect as a gate that cannot
fail, which is the whole subject of this document.

The cost concern stands and is unresolved by that fix: the full serial suite
costs 5,694 s and `quality-i18n` pays about 100 s of R2 restore before any i18n
gate runs. Path scoping remains desirable, but only as a COMPLETE table, which is
its own piece of work and is not in this program's scope.

**G1, G2, G3, G6, G7, G8, G9 encode bugs that exist today**, so they land RED
before their fixes. G4 and G11 follow Wave 1. G5, G10 and G12 can land any time.

## G13, added late: an SVG that asks for a theme token it can never receive

**Status: WRITTEN, wired, and proven by a plant.**
`scripts/check-svg-theme-reach.ts`, `check:ci-svg-theme-reach`, a real
`SVG theme reach` step in `quality-content`.

This gate came from the Stop hook's regression judge rather than from the
research pass, and it names a blind spot the twelve above genuinely share. All
521 illustrations shipped with a hardcoded `#f5f5f5` ground and no dark-mode
hook. That reads like theming nobody had got round to. It was not: an SVG loaded
through `<img src="...">` is a SEPARATE DOCUMENT, so a `var(--illustration-ink)`
written inside it resolves against nothing at all. Meanwhile Wave 3 had declared
`--illustration-*` and the census recorded zero consumers.

Two instruments covered the two halves and both were green. One confirmed the
tokens were declared. Another confirmed the assets were present. What was broken
was the CONNECTION between them, which is not a property of either half, so
neither could ever have seen it. That is the shape worth carrying forward: a gate
per artifact is not coverage of the relationship between artifacts.

The invariant is deliberately narrower than the judge asked for. The judge wanted
external SVGs flagged on theme-sensitive paths, which would red the logo and the
favicon, both of which are correct as external images with literal colours. The
gate instead fires only when an externally-referenced SVG contains `var(--`,
which is broken by construction and cannot be a false positive.

The plant took two attempts and the first failure is the instructive one.
Planting `var(--illustration-ink)` into `favicon.svg` did NOT fire, and for a
moment that looked like a gate that could not fail. It was the control that was
wrong: the favicon is a `<link rel="icon">`, never an `<img src>`, so the gate
was right to ignore it. Re-planting into `icon-rediacc.svg`, which
`Navigation.tsx:137` and `Footer.tsx:31` both load through `<img src>`, fired
exit 1 naming both call sites, and restoring the file returned exit 0. A control
that does not fire is a claim about the control before it is a claim about the
gate.

## G14, found while verifying my own work: biome could not see a single gate script

**Status: FIXED.** `biome.json` includes `scripts/**/*.ts`; 99 files brought to
clean; the last one needed a hand edit the formatter would not apply.

I passed five edited files to `npx biome check` and it answered
`Checked 1 file`. Four of the five were under `scripts/`. The include list at
`biome.json:53` reads `scripts/**/*.js`, and **there are zero `.js` files under
`scripts/`** and 99 `.ts` files. The pattern matched nothing, and had matched
nothing for as long as it had been there, while `.ci/**/*.ts` two lines below was
correctly in scope. So every gate script in this repository, including the twelve
this programme wrote to catch regressions, was outside the linter.

Adding the pattern surfaced 119 diagnostics. Every one was formatting or import
ordering, with no semantic lint error anywhere in the 99 files, which is the
reassuring half of the result: the scripts were unlinted but not wrong.
`biome check --write` fixed 86 files; `check-external-links.ts` kept one
multi-line signature the formatter reported but would not rewrite, so that one was
collapsed by hand.

**Proof the bulk rewrite did not break the instruments**, which matters more than
the formatting: twelve gates re-run afterwards, all exit 0, and their control
counts intact (`locale-sources` 14, `de-contamination` 10, `svg-theme-reach` 10,
`css-dom-refs` 6, `config-divergence` 6, `parity` 5). A formatter that had damaged a
selftest would show up as a control that stopped firing, not as a crash.

**A smaller lesson from the same hour.** My first attempt to count those controls
grepped `'^  PASS'` and returned 0 for gates that were visibly printing five PASS
lines. The colour escape sits BETWEEN the indent and the word, so the anchor never
matched. I was two minutes from recording "these gates lost their controls" as a
finding. When a count contradicts what the raw output plainly shows, distrust the
count first: `cat -A` settled it immediately.

## G15, the gate this programme most obviously needed and did not have

**Status: WRITTEN, wired, baselined at 95.** `scripts/check-dead-css.ts`,
`check:ci-dead-css`, a real `Dead CSS` step in `quality-content`.

The repo gates dead bash, dead case arms, dead service methods and dead
translation keys. It did not gate dead CSS, which is the largest surface this
programme touches and the one where every wave has been deleting by hand.

`.cta-bolt` is the specimen and it is a good one: styled in `main.css`, applied to
no element anywhere in `packages/www`, and guarded by its own dedicated CI gate
(`check:ci-cta-bolt`) enforcing the uniqueness of a class nobody uses. A gate
protecting dead code is worse than no gate, because it reads as evidence the code
matters.

**Why this is NOT a hole in `check-css-dom-refs`,** which I briefly and wrongly
called one. That gate's header says plainly that it asks "is this USE still styled"
and that dead-CSS detection asks the opposite question. It behaves exactly as
documented. The two gates are complements: one catches a deletion that unstyles a
live element, the other catches a rule outliving its element. Neither implies the
other.

**Conservative by construction, because the failure directions are not symmetric.**
For `css-dom-refs` a miss is a false negative. Here a false positive would delete
live styling, so a class counts as ALIVE if its name appears anywhere in any source
file, not merely inside a `class` attribute. A name in a comment, a doc, or a
runtime template literal keeps its rule. That over-counts life on purpose: 1,390
defined classes reduce to 95 dead, not the 562 a naive attribute-only comparison
would have claimed.

**Proof it can fail**, since a shrink-only gate that starts green is exactly the
shape that never fires: planting `.zzz-gate-probe-never-used` in a new stylesheet
made it exit 1 naming that class and file; removing the file returned exit 0. The
negative direction was checked on the real tree too, with five known-live classes
(`segmented__item`, `install-methods`, `footer-copyright`, `container`, `chip`) all
correctly absent from the dead list.

## G16, surfaced by a translator sub-agent while it was doing something else

**Status: DATA FIXED. GATE DELIBERATELY NOT CHANGED, with the reason measured.**

A sonnet translator, mining precedent for unrelated strings, reported that the English
word `Test` sat untranslated in two `howItWorks` step titles across eight locales.
Verified exactly: `pages.solutionPages.integrations.howItWorks.steps[2].title` and
`pages.solutionPages.safeOsTesting.howItWorks.steps[1].title` were the literal string
`Test` in ar, de, es, fr, ja, ru, tr and zh, while et, it, ko and pt had translated
both.

Fixed for the five where the locale has an established native word and the sibling
steps show the shape to match: `ar` verbal nouns took اختبار, `es` infinitives
(Conectar / Activar / Clonar / Confirmar) took **Probar** rather than the noun Prueba,
`ja` nouns took テスト, `ru` noun-dominant took Тестирование, `zh` verbs took 测试.
Left alone in de, fr and tr, where `Test` is a genuine native word rather than an
untranslated leftover.

**Two corrections to the record, both worth more than the fix.**

First, the sub-agent's explanation was wrong in a way that sounded authoritative: it
said the gate is blind here because `LOCALE_ROOTS` excludes `packages/www`. It does
not exclude it, and the same gate's findings that morning were in `zh.json` and
`ar.json`. The claim came from `.claude/agents/i18n-guardian.md`, which said exactly
that and had gone stale. **A knowledge file that is confidently wrong is worse than
one that is silent**, because it manufactures a plausible reason to stop looking. The
file is corrected.

Second, the REAL blind spot is `MIN_LENGTH = 12` at `check-i18n-cross-locale.ts:93`.
`Test` is four characters, so the scan skips it before any signal runs. The obvious
fix is to lower the threshold for script locales, where a value with no own-script
character looks like unambiguous contamination. **Measured before changing anything:
that surfaces about 1,700 short values per script locale, and the visible ones are
`Docker`, `PostgreSQL`, `Linux`, `macOS` and `/account/`.** The threshold is
load-bearing and the honest move is to leave it and say so. Closing this class needs
an instrument that can tell an English word from a product name, which this gate is
not and should not become.

## G17 and G18, added after the operator found what 250 static gates could not

The operator opened `/ar/docs/quick-start` in a browser and reported three things: a
console full of `jsxDEV is not a function`, no top menu, and a language switcher that
did nothing. Every gate in this repo was green.

**What was actually wrong, in two parts.**

The three symptoms came from a dev server on port 4321 that had been running since
Aug 17 while the tree churned underneath it, the same staleness already documented in
the execution guide for port 4802. On a clean server the same page reported zero console
errors, 103 visible nav links with the Arabic labels, and clicking the English option
navigated to `/en/docs/quick-start`.

But underneath it there was a real defect of exactly the shape the operator suspected.
`check:ci-hydration-clean` was RED and had been left that way as a later wave's problem:
four React islands computed a different initial state on the server than in the browser,
so React discarded their server-rendered subtrees. Fixed in
`BlogStickyBar.tsx:12`, `solution-pages/LeadMagnetButton.tsx:29`, `ThemeToggle.tsx:18`
and `InstallMethods.tsx:134`, each by giving the initializer one value both renders agree
on and moving the browser-only refinement into an effect. That gate is now exit 0 across
all 26 components.

**G17, `check:ci-browser-smoke`.** The lasting fix is that something now loads a page.
Not one of the 250 gates did, which is how a site can satisfy every static check and
still show a visitor a blank nav. It serves `packages/www/dist` with real 404s and drives
six routes including `/ar/docs/quick-start`, asserting zero console and page errors, a nav
that renders links, and a language switcher that opens AND actually changes locale.
Proved able to fail by planting a throwing script into the built Arabic page.

It runs inside `mcr.microsoft.com/playwright:v<derived>-noble` rather than on the bare
runner, at the operator's instruction. Two details matter: the tag is READ from the
installed playwright package at run time, so the image cannot drift from the npm
dependency; and MCR serves anonymously without rate limiting, so this needs no
`docker login` and cannot fail with `toomanyrequests`, unlike Docker Hub.

**G18, `check:ci-docker-image-freshness`.** Container images were the only kind of pin
with no freshness gate: npm packages, embedded binaries and GitHub Actions all shared one
soak window and images watched nothing. It found `python:3.9-slim` years past that
series' end of life, plus three more. The existing debt is baselined shrink-only rather
than bumped, because a major base-image jump inside a submodule is a decision with real
blast radius and not a side effect of installing a watchdog.

It inherits the anti-vacuity rule `check-actions.ts` paid for: when its lookups were rate
limited that gate once printed "all up-to-date (14 unknown)" and exited 0, reporting
freshness it had verified for nothing. Here an image whose tags cannot be listed is a
FAILURE, and `DOCKERHUB_TOKEN` is wired into the workflow so the anonymous limit cannot
make it silent.

**The control that nearly did not happen.** The first plant for G18 was named
`__gate_probe_Dockerfile` and the gate did not fire, because its glob matches basenames
that START with `Dockerfile`. For a moment that looked like a gate that could not fail.
Renaming the probe to `Dockerfile.gateprobe` made it exit 1 immediately. A control that
does not fire is a claim about the control before it is a claim about the gate, and that
is now the second time this session that exact lesson was paid for.
