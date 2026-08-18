---
name: www-site
description: The packages/www Astro marketing and docs site - where its CSS and theming layer actually lives (not where you would look), the solution/persona/resource template families and their 515-line config, the docs surface and its 1,015 flat markdown files, the build hazards that corrupt a shared working tree, and the measured baseline this site is judged against. Use for any change to www styling, components, layouts, routes, or content, and before running a www build in a tree another session is using.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You work on the marketing and docs site. Every fact below was measured against the live
site or a live crawl on 2026-08-17, not read off a file. Treat the numbers as a dated
baseline: re-measure before quoting one as current, but trust the *shapes* - they are
structural and change slowly.

## Where things actually are

**The main stylesheet is not in `src/`.** `src/layouts/BaseLayout.astro:237-242` links
`/styles/main.css` (3,421 lines) and `/styles/responsive.css` from `public/styles/`, plus
three more via the `media="print"` onload trick (`search-modal.css`, `contact-modal.css`,
`region-picker.css`) which therefore load on **every route**.

**Design tokens are split across five `:root` blocks and the last one wins.** The inline
block at `BaseLayout.astro:279-414` is the *last* style source in the document and has the
same `(0,1,0)` specificity as every other `:root`, so it silently overrides `main.css` for
all 17 properties it redeclares. Two consequences proven live:

- `--font-family` in `main.css:79-80` is **dead**; the computed value is the
  `BaseLayout.astro:287` one.
- `responsive.css:71-74` is **dead**: it sets `--max-width: 1400px` above 90rem, but the
  later unconditional `:root` re-pins 1200px, so the wide-desktop rule has never fired.

Also declaring `:root`: `src/styles/sidebar-shared.css:6-38`, `solution-pages.css`,
`lead-magnet-modal.css`, `AnnouncementBar.astro:32`.

Component count is **80**, not the 43 you get from globbing `src/components/*` - five
subdirectories exist, and `solution-pages/` alone holds ~34 files.

## The template families

- **21 solution pages** are byte-identical 16-line wrappers (verified: strip the slug,
  hash, one hash class). All variance lives in `src/config/solution-pages.ts` (515 lines).
  `SolutionPage.astro` renders **16 conditional section blocks**.
- **4 persona pages** and **6 resource briefs** follow the same shape.
  `nis2-directive-summary.astro` is a 203-line bespoke outlier among 11-line siblings.
- Five 12-line `SPHome*.astro` files are pure re-export wrappers.
- `SPSocialProof.astro` is **deliberate dead code** kept with re-enable instructions,
  tied to rediacc/console#519 (fabricated social proof). **Do not sweep it up.**
- Each solution carries **216-363 leaf translation keys** (mean 314) - about 6,600 in
  `en.json` alone, ~86,000 across 13 locales.

## Docs

`DocsLayout.astro` is 1,230 lines of which 483 are inline `<script>` and 505 inline
`<style>`. **1,015 markdown docs sit in one flat directory**; hierarchy is a `category:`
frontmatter string, written two ways (`Guides` and `"Guides"`). `/[lang]/docs` is a 301
redirect, so those docs have no index page. Nine routes have zero inbound links anywhere
in the codebase and still build (117 pages).

## Build hazards - read before you run a build

**`npm run build:www` deletes 14 TRACKED files from the shared tree.**
`astro.config.mjs:26` runs `scripts/generate-search-index.js` on `astro:build:start`; it
resolves output to `packages/www/public/` (**never the outDir**), `fs.unlinkSync`s every
`search-index*.json` at `:82`, then rewrites them. All 14 are in `git ls-files`. During
that window every dev server 404s on `/search-index-<lang>.json`. The `catch {}` in
`astro.config.mjs:28` means a lost index still exits 0. The `mutex: ['www-dist']` that
looks like protection is a process-local `Set` and holds nothing between two agents.

**`.astro/` is hardcoded and shared.** `node_modules/astro/dist/core/config/settings.js:21`
derives it from `config.root` with no override. A concurrent `astro build` rewrites
`content-modules.mjs`, `content.d.ts` and `collections/` under a running dev server.

**Serialising builds needs a gate that can say "free", and the obvious ones cannot.**
Measured with NO build running, each probe in its own process:

| probe | result |
|---|---|
| `pgrep -acf "node .*astro.* build"` | **1**, a self-match |
| `ps -eo args \| grep -c '[a]stro build'` | 0, correct |
| a `/proc/<pid>/cmdline` walk restricted to `pgrep -x node` | 0, correct |

`pgrep -f` matches its own command line and has no equivalent of grep's `[a]` bracket
trick, because the pattern text is itself part of the argv it searches.

**The second-order half is what actually bites.** Put the correct probe in a command whose
OTHER text contains the literal `astro build` (an `echo` explaining what you are checking,
a comment, a second candidate probe) and `ps` sees your own wrapper's argv and returns a
false positive. One session ran the correct `[a]stro` probe alongside an
`echo "any astro build running?"` and got **2** with nothing building. Probe one gate per
process, and keep the words out of it. A gate that never reports free is indistinguishable
from a busy tree; a gate that wrongly reports free is how two builds end up writing one
`dist/`.

**And when two do collide, the damage is silent.** A wave measuring a fresh `dist/` had it
wiped three times mid-measurement by other waves' builds, and a page count taken from the
result read 1,842 against a true 1,814: stale files from the previous build lingering
beside the new ones. A page count that does not match the build's own reported total means
you are reading a mixed tree, not a finished one.

**Cold start is ~56s of content sync**, not a hang. `dist/` is 7.1 GB because
`public/assets/{videos,tutorials}` (6.9 GB, gitignored) is copied verbatim - but a build
does not need them, so a portable rig payload is only **112 MB**.

## Traps that have already cost sessions

- **The page grows as you scroll**: `loading="lazy"` images resolve late. The homepage
  reads 6,794px on fresh load and 7,697px after scrolling to the bottom. Scroll and settle
  before recording any height.
- **`/en` overflows horizontally by 133px even at 1440**, and the culprit is a
  **pseudo-element** (`.cf-feature-info::after`, `pricing-page.css:1804-1820`:
  `position:absolute; white-space:nowrap; opacity:0`). Two independent scans reported
  "no offending elements" because `querySelectorAll('*')` does not return pseudo-elements.
- The black chip at the bottom of desktop screenshots is `<astro-dev-toolbar>`, not site
  content.
- Heading anchors and TOC links use **two different slug algorithms**, so 8,013 of 15,521
  in-page links are dead across 963 of 1,107 pages, English included. Ids come from
  Astro's default `rehypeHeadingIds` (`astro.config.mjs:168-175` sets no `rehypePlugins`);
  hrefs come from `stringToSlug` (`src/utils/slug.ts:6-13`, `[^\w\s-]` with **no `u`
  flag**). `sidebar-behavior.ts:62` captures the correct id in `[^>]*` and discards it.

## The state of the design system

**Corrected 2026-08-18.** This section used to say "there is one, and almost nothing uses
it", listing a form system with zero consumers, a `--radius-*` scale nobody read, the
primary CTA implemented nine times in two different greens, 33 card shells and six overlay
implementations. **That was true and has largely been fixed** by the simplification
programme: the token layer collapsed to one `:root`, the dead form system was adopted, the
overlays were consolidated behind one `Overlay.tsx` primitive that owns backdrop, focus
trap and a reference-counted scroll lock, and the CTA greens were unified.

What survives from the old lesson, and is still the most useful sentence here:

**Before adding a component, grep for the one that already exists.** The recurring defect
on this site is not a missing abstraction, it is a present abstraction the code walks
around. Proven popover patterns exist and should be reused rather than re-implemented:
`PersonaMegaMenu.tsx` for a menu anchored to the nav (click-outside, Escape, roving arrow
keys, and a hover-intent guard written to fix a real hover-then-click bug),
`LanguageMenu.tsx` for a small control anchored to its own button, and `Overlay.tsx` for
anything modal.

**But grep is only half of it.** A wave reused an existing global class name, assumed the
name meant what it looked like, and broke an unrelated component: a shared name in a global
stylesheet is an implicit export with no import to review. So grep for it, **then read what
it does**, and prefer a component-scoped or clearly-prefixed name over reusing a generic
one.

## Where the numbers actually stand

**This section replaced a "baseline to beat" that had gone stale and was actively
misleading**: it still described the pre-simplification site, so an agent reading it would
chase problems that were solved. Re-measure before trusting any figure here; the point of
the correction is that a confidently wrong knowledge file is worse than a silent one.

After the 2026-08 simplification programme, measured on the production build:

- Homepage JS decoded **425,776 B**, down from 6,998,912. That is lighter than claude.com
  (1,267,131) and about 1.4x anthropic.com. **Do not go hunting for the locale-bundle
  problem; it is fixed** - per-locale chunking landed and `/ar/pricing` now ships the same
  bytes as `/en/pricing`.
- Homepage painted colours **12** (target was 16), painted box-shadow **1**, font sizes
  **11** (target 8), radii **4** (target 3). Two of four targets met, two missed narrowly.
- Homepage height **4,222 px** desktop and 8,303 mobile, down 45% and 43%.
- Zero console errors and zero broken in-page anchors across all built pages.

**Where the entropy still lives:** the solution pages. `/en/solutions/encryption` paints
far more colours than `/en`, and `src/styles/solution-pages.css` is the largest remaining
pocket of hardcoded values. Some of those literals are **deliberate and must not be
tokenised**: third-party BRAND colours (GitLab, Nextcloud, WordPress) and a macOS/terminal
chrome imitation, both carrying `LITERAL ON PURPOSE` comments. A brand colour is identity,
not theme.

## Shared files, and who gets hurt

The recurring way this site breaks is a shared file edited by someone who thought it was
local. Before editing any of these, know what else consumes them:

- **`public/styles/main.css`** is the single global sheet: tokens, nav, buttons, search
  modal, dark-theme overrides. Treat it as owned by ONE writer at a time. Two agents in it
  concurrently has already corrupted this tree once.
- **`.chip` is a site primitive** and appears in grouped selectors with component classes.
  When deleting a component, remove only ITS half of the selector list, never the rule.
- **Icon buttons share one grouped rule set** (`.btn--icon, .search-btn, .hamburger-btn,
  .sidebar-close-btn, .language-trigger-icon` and formerly the theme toggle). Strip the
  selector, never delete the rule.
- **`src/styles/sidebar-shared.css` is shared by docs AND blog.** `ContentLayout` also
  opens a `<style is:global>` that redefines `.toc-sidebar` with a conflicting model, so
  the blog's behaviour currently depends on emitted stylesheet order. Any change to
  `.sidebar-base` reaches every blog post.
- **`src/styles/article-content.css`** is imported by both the docs and blog layouts.
- **`.nav-translate` uses `top`, not `transform`, ON PURPOSE.** A transform there
  establishes a containing block and silently breaks the `position: fixed` mega-menu
  panels. There is exactly ONE header scroll listener; extend it rather than adding a
  second.
- **`SPHero.astro` is shared by 25 pages** (21 solutions + 4 personas) at
  `min-height: 100dvh`.

## Islands server-render in ENGLISH, on every locale

`src/hooks/useLanguage.ts` opens with
`typeof window === 'undefined' ? 'en' : getLanguageFromPath(window.location.pathname)`.
There is no `window` on the server, so **every island using that hook emits English into
the HTML whatever the locale**, and `BaseLayout.astro` mounts `<Navigation client:idle />`
with no `lang` prop to tell it otherwise. Measured on a real build: `dist/de/index.html`
and `dist/ar/index.html` both render `Built for you` and `Get Started`, while `de.json`
holds `Jetzt starten` and `Preise`. The Astro-rendered parts of the same page ARE
translated, which is what makes it read as a translation gap rather than a rendering one.

Fourteen components call that hook and six islands are SSR'd from `BaseLayout`. If you are
adding or moving an island that shows locale text, pass `lang` explicitly:
`BaseLayout` already computes `currentLang` and simply does not hand it down.

**Two gates that look like they cover this and do not.** `check:ci-hydration-clean` fails
on a `useState` INITIALIZER that reads `window`; this read is at module scope inside a
store factory, a different shape of the same family, and the gate is blind to it.
`check:ci-browser-smoke` drives a real browser, where hydration has already corrected the
text before it looks. The defect is only visible in the built HTML, which is exactly what
a crawler and a no-JS visitor get. Plan and gate design: `agent/PLAN-ssr-nav-locale.md`.

## The gate surface you are working against

Roughly a dozen gates now police this package, and several were written specifically
because a defect survived nine waves of review. The ones that will catch you:

- `check:ci-browser-smoke` drives six real routes in a Playwright container, including
  `/ar/docs/quick-start`, asserting zero console errors, a nav that renders, and a
  language switcher that actually navigates. **It has a hardcoded route list** - deleting a
  page without updating it is a guaranteed red.
- `check:ci-landmarks` asserts exactly one `<main>` per built page.
- `check:ci-dead-css` (styled but never rendered) and `check:ci-css-dom-refs` (rendered but
  never styled) ask OPPOSITE questions; you generally need both green.
- `check:ci-hydration-clean` fails on a `useState` initializer that reads `window`,
  `document`, `localStorage` or `sessionStorage`. Give the initializer one value both
  renders agree on and move the browser-only refinement into an effect.
- `check:ci-dead-translation-keys` and `check:i18n:key-usage` are the two directions of the
  same question. **Deleting a component without deleting its i18n keys is a red build**,
  and so is the reverse.
- `check:ci-em-dash-surfaces`, `check:ci-layout-overflow` and `check:ci-dead-css` all carry
  SHRINK-ONLY baselines: a baselined finding that gets FIXED is a hard error until drained.

**The catalogs are serialised.** Thirteen locale files under `src/i18n/translations/`; when
several waves each orphan keys, ONE owner applies every deletion in a single pass and runs
`i18n:generate-hashes` ONCE. Never parse-and-reserialize a catalog: no formatter in this
repo reproduces their shape (prettier and biome both expand the inline arrays), so a round
trip rewrites about 1,700 lines per file. Splice bytes.
