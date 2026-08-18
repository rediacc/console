# RESEARCH: site chrome (nav, mega menus, search, language, footer)

Agent: `sx-chrome`. Date: 2026-08-17. Browser session `sx-chrome`,
screenshots under
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-chrome/`.
Dev server `http://localhost:4321` was up the whole session; no route 404'd.

**Nothing was modified.** This file is the only thing written.

---

## 1. Verdict

The top bar is the problem, and it is not the number of destinations, it is the
number of *things competing for the same 56 pixels*: 13 interactive targets,
six of them bold grey nav items, three of them unlabelled icons, two of them
identical links to the homepage. Behind two of those items sit mega menus whose
21 link labels average **36.8 characters** and nine of which end in a full stop,
because `MegaMenu.tsx:38` uses each solution page's marketing H1 as its nav
label; claude.com's 51 header destinations average **9.7 characters**. The
single highest-leverage change is therefore not deleting pages, it is
**relabelling**: give every solution a 1-3 word nav label, collapse the six
top-level items to four, and delete the three utility icons from the bar (search
becomes Ctrl+K plus a docs-only affordance, theme and language move to the
footer, where a language switcher already exists). Two further things must be
fixed regardless of the redesign, because they are outright broken: **clicking
"Solutions" closes the menu it just opened** (verified with real mouse events),
and **the nav is the sole cause of horizontal page overflow on every phone
width**, which pushes the language globe off-screen at 360, 390 and 414 px. The
footer, contrary to the brief's premise, is our most restrained surface and is
measurably 4x smaller than either reference site's; leave it almost alone.

---

## 2. What we have

### 2.1 The bar

`Navigation.tsx:122-267`, rendered from `BaseLayout.astro:425` with
`client:idle`.

Measured at 1440x900 on `/en`
(`nav.querySelectorAll('a,button')` filtered by `checkVisibility()`):

| # | Target | Element | Source |
|---|---|---|---|
| 1 | hamburger (hidden >=1024px) | `button.hamburger-btn` | `Navigation.tsx:129-140` |
| 2 | logo icon -> `/en` | `a.nav-icon-link` | `Navigation.tsx:141-158` |
| 3 | wordmark "rediacc" -> `/en` | `a.nav-brand` | `Navigation.tsx:159-168` |
| 4 | Solutions (mega trigger) | `button.mega-menu-trigger` | `MegaMenu.tsx:155-179` |
| 5 | Built for you (mega trigger) | `button.persona-menu-trigger` | `PersonaMegaMenu.tsx:202-226` |
| 6 | Pricing | `a.nav-link` | `Navigation.tsx:176-184` |
| 7 | Docs | `a.nav-link` | `Navigation.tsx:185-193` |
| 8 | Blog | `a.nav-link` | `Navigation.tsx:194-202` |
| 9 | Partners | `a.nav-link` | `Navigation.tsx:203-211` |
| 10 | search icon | `button.search-btn` | `Navigation.tsx:215-240` |
| 11 | theme toggle icon | `ThemeToggle` | `Navigation.tsx:241` |
| 12 | language globe icon | `LanguageMenu variant="icon-only"` | `Navigation.tsx:242-249` |
| 13 | Get Started (solid pill) | `AccountCta` | `Navigation.tsx:251-257` |
| 14 | Log in (outline pill) | `AccountCta` | `Navigation.tsx:258-264` |

**14 in the DOM, 13 visible at 1440** (hamburger is `display:none` above
`64rem`, `main.css:1108-1110`). Bar height **56px**
(`nav.getBoundingClientRect().height`), `position: fixed`, `z-index: 30`,
background `rgb(255,255,255)` (`main.css:690-701`).

Items 2 and 3 are two separate links to the same URL sitting next to each other.

Nav link typography (`getComputedStyle('.nav-link')`): `16px / 600 /
rgb(94,94,99)`. Six semibold mid-grey items in a row.

Screenshot: `ours-nav-top.png`.

### 2.2 The two mega menus

Both are separate components with near-identical machinery: click-outside,
arrow-key roving focus, Home/End, Escape, and a hover-intent pair
(`setTimeout(onToggle, 100)` on enter, `setTimeout(onClose, 150)` on leave).

`MegaMenu.tsx:55-144` and `PersonaMegaMenu.tsx:103-194` are ~90 lines of
duplicated logic apart from the item shape.

**Solutions panel** (`#mega-menu-panel`): measured **1200 x 535 px**, 6
category groups, **21 solution links + 2 footer links = 23**. Items derive from
`SOLUTION_PAGES` (`config/solution-pages.ts:124-515`, 21 entries) grouped by
`CATEGORY_ORDER` (`solution-pages.ts:63-70`, 6 categories). Footer links: "View
All Solutions" (`MegaMenu.tsx:232-250`) and "ROI Calculator"
(`MegaMenu.tsx:251-268`).

Screenshot: `ours-megamenu-solutions.png`.

**Persona panel** (`#persona-menu-panel`): measured **1020 x 274 px**, 4 cards
(`PERSONA_CARDS`, `PersonaMegaMenu.tsx:83-88`): for-devops, for-ctos, for-ceos,
for-ai-agents. Each card carries an icon, a title, a tagline and its own CTA
text, so the panel holds 4 destinations in 1020px.

Screenshot: `ours-megamenu-persona.png`.

**Label length, the sharpest number in this document.** Measured over the 21
`.mega-menu-item` elements:

```
megaItems 21 | avgLen 36.8 | minLen 29 | maxLen 48 | over-20-chars 21/21 | ends-with-'.' 9/21
```

The labels are the pages' marketing headlines, because `MegaMenu.tsx:33-39`
reads `pages.solutionPages.<key>.hero.title`:

- "Keep your data as long as the law requires" (42)
- "Dev environments that match production. Exactly." (48)
- "Your infrastructure. Your choice. Always." (41)
- "Sovereign by design, not by certificate." (40)

`Sidebar.tsx:137-144` builds its Solutions section from the same config the same
way, so the mobile drawer carries the same 21 sentences.

### 2.3 Total nav surface

| Surface | Destinations |
|---|---|
| Solutions mega | 21 + 2 |
| Built for you mega | 4 |
| Direct nav links | 4 (Pricing, Docs, Blog, Partners) |
| Brand links | 2 (both `/en`) |
| **Header total** | **33 links to 30 distinct URLs** |
| Sidebar drawer (always in DOM) | 33 links / 37 interactive |
| Footer | 23 links / 26 interactive |

The sidebar is a **near-complete duplicate** of the two mega menus plus the four
direct links plus both CTAs, dumped by `Sidebar.tsx` into every page's DOM
(measured at 1440: `#navigation-sidebar` present, 33 anchors, translated
off-screen). Everything in the mega menus is reachable from the sidebar, from
`/en/solutions` (`pages/[lang]/solutions/index.astro`), and from the footer's
"Solutions" link. Nothing in the mega menus is nav-only.

### 2.4 Search

`SearchModal.tsx` (470 lines) + `public/styles/search-modal.css` (388 lines).
Fuse.js, `threshold: 0.3`, `ignoreLocation: true`, weights content .5 / body .4
/ category .1 (`SearchModal.tsx:101-113`). Per-locale index lazy-fetched on
first open (`SearchModal.tsx:96`).

**Index size on disk** (`ls -la packages/www/public/search-index-*.json`):

```
13 files, 18.10 MB total.  en = 1.22 MB.  ru = 1.82 MB (largest).
```

First open on localhost fetched `search-index-en.json`: **1254 KB, 16 ms**
(`performance.getEntriesByType('resource')`).

**What it actually indexes** (`python3` over `search-index-en.json`):

```
1435 entries, 87 distinct pages
categories: Documentation 1320, Blog 115
page prefixes: ['/en/blog', '/en/docs']
'/en/pricing'   -> []
'/en/solutions' -> []
'/en/partners'  -> []
'/en/for-*'     -> []
```

**Zero marketing pages are searchable.** Not the 21 solution pages, not
pricing, not partners, not the four persona pages, not company, contact,
roi-calculator or disaster-recovery.

Driven live, eight queries into the modal:

| Query | n | Top result | Verdict |
|---|---|---|---|
| `pricing` | 20 | **"Pruning"** | wrong; `/en/pricing` not indexed, fuzzy matched a CLI verb |
| `partners` | 4 | "Subscriptions & Plans" | wrong; `/en/partners` not indexed |
| `immutable backups` | 6 | a PCI DSS blog post | the solution page of that exact name is not indexed |
| `for devops` | 23 | "For DevOps Engineers" -> `/en/docs/development-environments` | right words, wrong page; `/en/for-devops` not indexed |
| `ransomware` | 12 | "Supply Chain Risk" | section heading, no page context |
| `kubernetes` | 10 | "Kubernetes" | fine |
| `fork` | 50 (capped) | "Fork" | fine |
| `backup` | 50 (capped) | **"8. {{t:cli.docs.sectionTitles.backup}}"** | raw i18n placeholder shown to the user |

**148 entries in the English index contain an unresolved `{{t:...}}`
placeholder**, all under `/en/docs/cli-application`. The rendered page has
**zero** (`curl -s .../docs/cli-application | grep -o '{{t:[a-zA-Z.]*}}' | wc
-l` -> `0`), so the index generator runs before the CLI-docs translation
substitution. Users see the raw keys only in search results.

Empty state: the modal is **600 x 110 px** with nothing in it. No suggestions,
no recent, no popular pages. Screenshot: `ours-search-empty.png`.

Result rows show a heading and an excerpt but never the page they belong to, so
"Why It Matters", "Hub", "Related Guides", "Blocks, not bytes" are offered as
navigable results with no context.

### 2.5 Language switcher

`LanguageMenu.tsx` (338 lines), 13 locales, rendered **twice**:

- `Navigation.tsx:242-249` as `variant="icon-only"` (globe) in the primary bar
- `Footer.tsx:338-345` as `variant="flag-name"` ("English" + flag) in the footer

The footer instance is the discoverable one. The nav globe is an unlabelled icon
that costs a full slot in the bar and, on phones, is unreachable (section 2.8).

### 2.6 Footer

`Footer.tsx` (371 lines). Measured on `/en`: **632 px tall**, **6
`.footer-column` blocks** (the brief said four; four of the six are `<nav>`),
**23 links / 26 interactive**.

| Column | Links | Source |
|---|---|---|
| logo | 1 | `Footer.tsx:22-38` |
| unnamed nav (Home, Blog, Docs, Contact) | 4 | `Footer.tsx:41-88` |
| PRODUCT | 6 | `Footer.tsx:91-163` |
| ORGANIZATION | 3 | `Footer.tsx:166-205` |
| NEWSLETTER | 0 (+ input + submit) | `Footer.tsx:208-210` |
| LEGAL | 6 | `Footer.tsx:213-285` |
| bottom bar | 2 social + 1 legal-disclosure + language menu | `Footer.tsx:289-365` |

Duplication inside the footer: Contact appears in both the unnamed nav column
and ORGANIZATION (`Footer.tsx:76-86` and `Footer.tsx:193-203`, same href);
"About Us" also points at `/contact` (`Footer.tsx:172-180`); Legal Information
appears in the LEGAL column and again in the disclosure line
(`Footer.tsx:273-283`, `Footer.tsx:355-363`).

Two footer product links are homepage anchors, not pages:
`/{lang}#problem` and `/{lang}#pricing` (`Footer.tsx:109`, `Footer.tsx:120`),
while the bar's Pricing item points at the real `/{lang}/pricing`. Same word,
two destinations.

Screenshot: `ours-footer.png`. It looks good: five readable columns, generous
spacing, one visual weight.

### 2.7 Announcement bar and breadcrumb

`AnnouncementBar.astro` (58 lines), rendered at `BaseLayout.astro:424`, gated on
`en.announcement.enabled` which is **`false`**
(`src/i18n/translations/en.json:350`). It renders nothing today and I measured
nothing on the homepage. It is 58 lines plus 21 lines of CSS in `main.css` plus
a `--announcement-bar-height` variable that `.nav`'s `top` still reads
(`main.css:692`). Cheap, dormant, correctly built. Not a deletion candidate on
complexity grounds.

`Breadcrumb.astro` (147 lines) is used by `DocsLayout`, `ContentLayout`, 404,
roi-calculator, changelog, newsletter, `SolutionPage.astro` and
`PersonaPage.astro`. It emits BreadcrumbList structured data via
`StructuredData.astro` (`Breadcrumb.astro:36-38`). **Keep it.** It is the one
piece of chrome that adds orientation instead of consuming it, and deleting it
would cost SEO.

### 2.8 Mobile, 390x844

Visible nav targets: **6** (hamburger, logo icon, wordmark, search, theme,
language). Both CTAs are `display: none`:

```
getStartedDisplay: "none"   loginDisplay: "none"
```

So on the primary mobile viewport the chrome offers **three utility icons and
zero calls to action**.

**And the nav overflows the viewport.** Scanning every element for
`right > viewport`, at 390px:

```
7 offending elements, ALL of them nav chrome:
  div.nav-right                  x=233  right=425
  div.nav-utilities              x=233  right=425
  div.language-selector          x=377  right=425
  button.language-trigger-icon   x=377  right=425
  (+ its 3 svg children)
container width = 375, viewport = 390
```

Re-verified with a fresh reload at each width:

| viewport | `.nav-container` w | globe x..right | off-screen? |
|---|---|---|---|
| 360 | 345 | 377..425 | **yes** |
| 390 | 375 | 377..425 | **yes** |
| 414 | 399 | 377..425 | **yes** |
| 768 | 753 | 507..555 | no |

The language globe is unreachable on every common phone width, and the nav is
the only thing on the homepage causing horizontal page scroll.

Root cause: `.nav-container` is `grid-template-columns: auto auto 1fr auto auto`
(`main.css:729-737`) and the wordmark is only hidden between `30rem` and `40rem`
(`main.css:894-898`). Below `30rem` the wordmark comes back while three 48px
utility icons stay, and `auto` tracks will not shrink below their content.

Screenshots: `ours-nav-mobile.png`, `ours-nav-mobile-390-overflow.png`,
`ours-sidebar-mobile.png` (drawer open, 375px wide, 33 links).

### 2.9 The scroll collapse (judgement, as asked)

Mechanism understood and not re-opened: `Navigation.tsx:31-63` +
`main.css:708-728`. At `scrollY >= 80` the nav sets
`--nav-scroll-fade: 0`, `body[data-nav-collapsed]`, and `pointer-events: none`
on `.nav-translate`.

Measured at `scrollY = 900` on `/en`:

```
stillVisible: ["Rediacc logo", "rediacc", "Get Started", "Log in"]
```

**9 of 13 targets are gone, including all six nav items and search.** Screenshot
`ours-nav-scrolled.png` shows a bar containing only the brand and two buttons.

**My judgement: this is a bad idea and I would delete it.** Three reasons, two
of them measured:

1. Neither reference site does it. claude.com at `scrollY = 900`: all 9 targets
   visible, `opacity: 1`, `top: 0`. anthropic.com at `scrollY = 600`: all 6 nav
   items `opacity: 1`, `y = 0`. A sticky bar that keeps its navigation is the
   norm these two set.
2. It solves a problem we would not have after simplification. The collapse
   exists because 13 items in a 56px bar feel heavy. Removing five items removes
   the motivation.
3. It is unrecoverable without scrolling back to the top. There is no
   scroll-up-to-reveal; the only way to reach Docs from the middle of a solution
   page is to scroll to `y < 80`. The mechanism also has to fight itself: it
   needs `pointer-events: none` so invisible items do not eat clicks
   (`main.css:717-719`), a `clip-path` on `.nav` so items clip rather than
   vanish behind the banner (`main.css:700`), a `top`-not-`transform` choice so
   mega-menu `position: fixed` still resolves to the viewport
   (`main.css:706-712`), and a reduced-motion escape hatch (`main.css:720-727`).
   Four separate accommodations for an effect that removes function.

Deleting it removes `Navigation.tsx:26-63` (38 lines), `main.css:696-728` (33
lines), the `.nav-translate` class from two JSX call sites, and the `clip-path`
workaround.

### 2.10 Two defects found while driving the chrome

**(a) Clicking a mega-menu trigger closes the menu.** Verified with real CDP
mouse events, not synthetic ones:

```
mouse move 700,600            -> panel absent
mouse move 304,28 (trigger)   -> wait 1s -> panel PRESENT   (hover-intent opened it)
mouse down left; mouse up left -> panel ABSENT              (the click closed it)
```

And a fast click (move + click inside 100ms) opens then closes 100ms later:
`agent-browser click ".mega-menu-trigger"` left `#mega-menu-panel` absent every
time, while `el.click()` (no mouseenter) opened it reliably.

Cause: `onMouseEnter` schedules `onToggle` after 100ms
(`MegaMenu.tsx:128-133`) **and** `onClick` calls `onToggle`
(`MegaMenu.tsx:159`). Both fire for a mouse user, so the two toggles cancel.
The button is `aria-haspopup="menu"` with `aria-expanded`, which tells assistive
tech and every keyboard user that clicking is the way to open it. Identical bug
in `PersonaMegaMenu.tsx:178-183` and `PersonaMegaMenu.tsx:207`.

**(b) The nav overflows the viewport on phones** and strands the language globe
off-screen at 360/390/414. Measured in section 2.8.

Both are in files I own. Neither was fixed, because the brief's hard rule is
"DO NOT MODIFY ANYTHING". They are carried forward to implementation as items 0
and 1.

### 2.11 Chrome CSS inventory

| File | Lines | Note |
|---|---|---|
| `public/styles/main.css` (chrome blocks only) | **735** | measured by parsing top-level blocks whose selector starts with a chrome prefix: `.sidebar` 229, `.nav` 183, `.footer` 167, `.hamburger` 45, `.language` 32, `.search-btn` 27, `.theme-toggle` 26, `.announcement` 21, `.logo-icon` 5. That is **21.5% of main.css's 3421 lines**. |
| `public/styles/search-modal.css` | 388 | loaded via the `media="print"` onload trick, `BaseLayout.astro:237-242` |
| `src/styles/sidebar-shared.css` | 310 | |
| `src/styles/language-switcher.css` | 191 | imported by `Footer.tsx:10` |
| `src/styles/mega-menu.css` | 184 | imported by `MegaMenu.tsx:6` |
| `src/styles/persona-mega-menu.css` | 173 | imported by `PersonaMegaMenu.tsx:4` |
| `public/styles/responsive.css` | 16 chrome lines of 249 | |
| `BaseLayout.astro` inline `<style>` | 8 chrome lines | |
| **Total chrome CSS** | **~2,005 lines across 7 files** | |

---

## 3. What claude.com and anthropic.com do

All values read from the live pages with `eval` + `getComputedStyle` /
`getBoundingClientRect` at 1440x900.

### 3.1 claude.com top bar

```
header height 84px, position: fixed, background rgb(250,249,245)
visible in bar: 9
  [logo] Meet Claude | Platform | Solutions | Pricing | Resources | Login | Contact sales | Try Claude
DOM targets inside header (incl. collapsed dropdown panels): 58
```

**Zero utility icons. No search, no theme toggle, no language switcher.**

Nav trigger typography: `15px / 400 / rgb(48,48,46)`. Regular weight, near-black.
Primary CTA "Try Claude": `rgb(20,20,19)`, `border-radius: 8px`, `15px`.

Behind the 5 triggers sit **48 destinations**:

| Trigger | Destinations |
|---|---|
| Meet Claude | 15 |
| Platform | 8 |
| Solutions | 14 |
| Pricing | 2 |
| Resources | 9 |

Label discipline over all 51 header anchors (`textContent`, since collapsed
panels return empty `innerText`):

```
n=51 | avgLen 9.7 | maxLen 24 ("Claude for Microsoft 365")
```

Every one is a noun phrase: "Coding", "Legal", "Healthcare", "Nonprofits",
"Developer docs", "Customer stories". Not one is a sentence.

At `scrollY = 900`: **all 9 targets still visible, `opacity: 1`, `top: 0`.**

Screenshots: `claude-nav-top.png`, `claude-nav-scrolled.png`.

### 3.2 anthropic.com top bar

```
.nav_component.is-desktop: height 68px, position: sticky
visible in bar: 7
  [logo] Research | Policy | Commitments | Learn | News | Try Claude
```

Three of the five nav items are plain links (Research, Policy, News), two have
dropdowns (Commitments, Learn). One CTA. Again **no search, no theme toggle, no
language switcher anywhere on the page** (`footer.querySelectorAll('select,
[class*=lang]')` -> `0`).

At `scrollY = 600`: all 6 items `opacity: 1`, `y = 0`.

Screenshot: `anthropic-nav-top.png`.

### 3.3 Their footers, and a correction to the brief

The brief says claude.com's and anthropic.com's footers are "notably
restrained". **Measured, they are the opposite of restrained, and ours is far
smaller than either.**

| Site | Footer height | Links | Interactive | Column headings |
|---|---|---|---|---|
| claude.com | **1070 px** | **161** | 171 | 10 |
| anthropic.com | **923 px** | **90** | 98 | 8 |
| **ours** | **632 px** | **23** | 26 | 4 |

claude.com's footer headings: Products, Features, Models, Solutions, Claude
Platform, Resources, Company, Programs, Help and security, Terms and policies.

Screenshots: `claude-footer.png`, `anthropic-footer.png`, `ours-footer.png`.

**The portable lesson is the inverse of the brief's premise.** These sites do
not feel simple because they publish few links. claude.com exposes 51
destinations in its header and 161 in its footer, against our 33 and 23. They
feel simple because **the bar is a short list of short nouns and the sprawl
lives in the footer**, where nobody has to parse it to get on with the page.
Our bar is doing the footer's job.

### 3.4 docs.claude.com search

`https://docs.claude.com/` redirects to `https://platform.claude.com/docs/en/home`.
Search is a **Ctrl+K command palette**, not a modal with an icon in the primary
site nav.

Three differences that matter, read from the accessibility tree:

1. **The empty state is not empty.** Before typing, the listbox already offers
   12 suggestions: three content pages plus nine navigation targets ("Console >
   Dashboard", "Console > Build > Skills", "Console > Organization settings >
   General"). Ours is a 600x110 blank box.
2. **Every result carries its path.** `"Get started with Claude — Messages >
   First steps — Make your first API call..."`, `"Models overview — Models &
   pricing > Models — ..."`. You always know which page a hit lives on. Ours
   shows a bare heading.
3. **It indexes navigation, not only prose.** Console routes are results.

Query `pricing`:

| | #1 result |
|---|---|
| docs.claude.com | **"Pricing — Models & pricing > Models — Learn about Anthropic's pricing structure"** |
| ours | **"Pruning"** |

Screenshots: `claude-docs-search-empty.png`, `claude-docs-search-pricing.png`.

---

## 4. The delta

| Measure | Ours | claude.com | anthropic.com | Gap |
|---|---|---|---|---|
| Bar height | 56 px | 84 px | 68 px | we are the *tightest* bar carrying the *most* items |
| Visible targets in bar | **13** | 9 | 7 | +4 / +6 |
| Top-level nav items | **6** | 5 | 5 | +1 |
| Utility icons in bar | **3** (search, theme, globe) | **0** | **0** | +3 |
| Links to the homepage | **2** (icon + wordmark) | 1 | 1 | +1 |
| CTAs in bar | 2 | 3 | 1 | fine |
| Nav link weight / colour | 600 / `rgb(94,94,99)` | 400 / `rgb(48,48,46)` | n/a | ours is bolder *and* lower contrast |
| Header destinations | 33 | 51 | ~35 | **we expose fewer, and it feels like more** |
| Mean nav label length | **36.8 chars** | **9.7 chars** | short nouns | **3.8x** |
| Longest nav label | 48 chars | 24 chars | | 2x |
| Nav labels that are sentences | 21/21, 9 ending in "." | 0/51 | 0 | the whole gap |
| Nav on scroll (y=900) | **9 of 13 hidden** | all visible | all visible | outlier |
| Site-wide search in nav | icon, always | none | none | |
| Search covers marketing pages | **no (0 of 26)** | n/a | n/a | |
| Search empty state | blank, 600x110 | 12 suggestions (docs) | n/a | |
| Locale switcher in bar | globe icon | none | none | they are English-only; not a fair comparison |
| Footer height | **632 px** | 1070 px | 923 px | ours is smallest |
| Footer links | **23** | **161** | **90** | ours is 1/7 of claude.com's |
| Mobile: CTAs in chrome | **0** | (not measured) | | |
| Mobile: horizontal overflow | **yes, caused by nav** | | | broken |

---

## 5. Proposed simplification

Ordered by leverage. Every item names its files, its risk, and its proof.

### Item 0 (not optional): fix the mega-menu click

**Change:** stop `onClick` and hover-intent both calling `onToggle`. Hover
should *open only* (`if (!isOpen) onToggle()` already guards on enter; the leave
timer is fine), and the click handler should open when closed and close when
open without the enter-timer racing it. Simplest correct shape: cancel the
pending hover timer inside `onClick` before toggling, and have the hover timer
call an `open()` rather than a `toggle()`.

**Files:** `MegaMenu.tsx:128-140,159`, `PersonaMegaMenu.tsx:178-190,207`.

**Risk:** low, isolated to two components.

**Proof:** re-run the CDP sequence from 2.10(a). `mouse move` onto the trigger
then `mouse down/up` must leave the panel **present**; a second click must
close it. Also `agent-browser click ".mega-menu-trigger"` must leave the panel
present.

### Item 1 (not optional): fix the mobile nav overflow

**Change:** delete the three utility icons from the bar (item 3 does this
anyway), which removes 144 px of the ~50 px overflow with room to spare. If any
utility survives, also give `.nav-container` a `minmax(0, 1fr)` brand track so
the wordmark can shrink, and widen the wordmark-hiding media query from
`(min-width: 30rem) and (max-width: 40rem)` to `(max-width: 40rem)`.

**Files:** `Navigation.tsx:214-250`, `public/styles/main.css:729-737`,
`main.css:778-790`, `main.css:894-898`.

**Risk:** low. The wordmark-hiding query has a comment justifying its lower
bound (`main.css:891-893`) that stops being true once the utilities leave.

**Proof:** at 360, 390 and 414, `document.querySelectorAll('*')` filtered by
`right > innerWidth` must return **0** elements, and
`document.documentElement.scrollWidth` must equal `innerWidth`.

### Item 2: relabel the solution nav entries (highest leverage)

**Change:** add a short `navLabel` to each solution's translation content and
use it in the mega menu and the sidebar instead of `hero.title`. Target 1-3
words, no terminal punctuation, matching claude.com's 9.7-char mean:

| slug | today (chars) | proposed |
|---|---|---|
| `immutable-backups` | "Backups that ransomware can't touch" (35) | Immutable backups |
| `kubernetes-cluster-mobility` | "Fork or move a running Kubernetes cluster" (41) | Kubernetes mobility |
| `data-sovereignty` | "Sovereign by design, not by certificate." (40) | Data sovereignty |
| `production-parity` | "Dev environments that match production. Exactly." (48) | Production parity |
| `retention-compliance` | "Keep your data as long as the law requires" (42) | Retention & compliance |

The slugs are already the right labels. In 19 of 21 cases the nav label is the
slug with spaces and a capital.

**Files:** `MegaMenu.tsx:33-39`, `Sidebar.tsx:137-150`, plus a new
`navLabel` key per solution in `src/i18n/translations/en.json`.

**Risk:** this is the one item with real cost outside my domain: 21 new keys x
13 locales = **273 translations** through the naturalization pipeline. Mitigation
worth considering: derive the label from the slug in code and translate nothing
(`kubernetes-cluster-mobility` -> "Kubernetes cluster mobility"), which is
English-only and wrong for 12 locales; or reuse an existing short key if the
content team already has one. **Operator question in section 7.**

**Proof:** re-run the label measurement. `avgLen` must fall below 20 and
`ends-with-'.'` must be 0.

### Item 3: strip the bar to 4 nav items + 1 CTA, delete the three icons

**Change, target bar (7 visible targets, down from 13):**

```
[logo+wordmark as ONE link]  Solutions  Product/Docs  Pricing  Company   [Log in] [Get Started]
```

Concretely:

- **Merge** `a.nav-icon-link` and `a.nav-brand` into one link. Two adjacent
  anchors to `/en` is a bug of the "no keyboard user wants to tab twice" kind.
  Deletes `Navigation.tsx:141-158` or `159-168`.
- **Delete** the search icon from the bar (`Navigation.tsx:215-240`). Keep the
  modal, keep the `search:open` hotkey listener (`Navigation.tsx:107-118`), and
  surface the affordance where it belongs: a Ctrl+K hint in the docs layout, as
  docs.claude.com does. See item 4 first: today the search is not good enough to
  earn a permanent slot.
- **Move** the theme toggle to the footer (`Navigation.tsx:241`). Neither
  reference site exposes one at all; the footer is where a preference control
  belongs.
- **Delete** the nav language globe (`Navigation.tsx:242-249`). The footer
  already renders `LanguageMenu variant="flag-name"` (`Footer.tsx:338-345`),
  which is the labelled, discoverable instance. This is not a comparison with
  claude.com/anthropic.com, which are English-only; it is an argument that one
  switcher beats two and the labelled one should win.
- **Fold** "Built for you" into the Solutions menu as a fifth column, or drop
  the trigger and rely on the persona cards already present in the sidebar and
  on `/en/solutions`. Four destinations do not justify a top-level trigger and a
  1020x274 panel. If dropped, `PersonaMegaMenu.tsx` (283 lines) and
  `persona-mega-menu.css` (173 lines) **delete entirely**.
- **Move** Blog and Partners into the footer, which already links both
  (`Footer.tsx:54-64`, `Footer.tsx:151-161`). Neither is a primary journey.

**Files:** `Navigation.tsx:120-267`, `PersonaMegaMenu.tsx` (delete),
`src/styles/persona-mega-menu.css` (delete), `Footer.tsx` (gains theme toggle),
`main.css:778-790`.

**Risk:** medium, and it is a content/analytics judgement as much as a design
one. Blog and Partners have `data-track-dest` attributes, so demotion is
measurable after the fact.

**Proof:** visible-target count in `nav.nav` must be **<= 8** at 1440 and the
same screenshot pair (`ours-nav-top.png`) re-taken side by side with
`claude-nav-top.png`.

### Item 4: fix search, or remove it from the chrome

Search is currently worse than useless on marketing pages: it confidently
returns "Pruning" for "pricing". Two acceptable outcomes; pick one.

**(a) Fix the index.** Add the marketing routes (21 solutions, pricing,
partners, 4 personas, company, contact, roi-calculator, disaster-recovery,
professional-services) to `scripts/generate-search-index.js`, and run the
generator *after* the CLI-docs translation substitution so the 148 `{{t:...}}`
entries disappear. Add a `page` breadcrumb to each result row in
`SearchModal.tsx:452-457`. Give the empty state a handful of suggested
destinations instead of 110px of nothing.

**(b) Demote it.** Delete the bar icon, keep Ctrl+K, scope search to `/docs`.

I recommend **(a) then (3)**: fix the index, keep the modal, take the icon out
of the marketing bar and show it in `DocsLayout`.

**Files (mine):** `SearchModal.tsx:319-467`, `public/styles/search-modal.css`.
**Files (not mine):** `scripts/generate-search-index.js`, `DocsLayout.astro`.

**Proof:** the eight-query battery in 2.4 re-run. `pricing` must return
`/en/pricing` at #1; `partners` must return `/en/partners`; `immutable backups`
must return `/en/solutions/immutable-backups`; and
`grep -c '{{t:' public/search-index-en.json` must be **0**.

### Item 5: delete the scroll collapse

Argued in 2.9. **Deletes** `Navigation.tsx:26-63` (38 lines),
`main.css:696-728` (33 lines), the `clip-path` on `.nav` (`main.css:700`), the
`.nav-translate` class from `Navigation.tsx:169` and `Navigation.tsx:214`, and
the `body[data-nav-collapsed]` contract.

**Risk:** low once item 3 has thinned the bar; do it *after* item 3, not before.

**Proof:** at `scrollY = 900`, the visible-target list must equal the list at
`scrollY = 0`.

### Item 6: the footer, lightly

Our footer is the smallest of the three by a wide margin. **Do not shrink it;
it is where the demoted items go.** Two small corrections only:

- Collapse the duplicate Contact entries (`Footer.tsx:76-86` vs
  `Footer.tsx:193-203`) and point "About Us" at something that is not
  `/contact` (`Footer.tsx:172-180`).
- Make the footer's "Pricing" (`Footer.tsx:120`, `/{lang}#pricing`) point at
  `/{lang}/pricing` like the nav does, and decide whether
  `/{lang}#problem` ("Overview") is a real destination (`Footer.tsx:109`).

Then **add** the items demoted from the bar: Blog, Partners, the four personas,
and the theme toggle. Post-change the footer lands near 30 links, still under
a fifth of claude.com's.

**Files:** `Footer.tsx`. **Risk:** trivial. **Proof:** no `href` in the footer
resolves to a 404; count of distinct footer destinations goes up, not down.

### Deletion summary

| Deleted | Lines |
|---|---|
| `PersonaMegaMenu.tsx` (if item 3 folds personas in) | 283 |
| `src/styles/persona-mega-menu.css` | 173 |
| Scroll-collapse effect + CSS + clip-path | ~71 |
| Duplicate brand link | ~18 |
| Search / theme / language markup in the bar | ~36 |
| `.search-btn`, `.theme-toggle`, `.language` blocks in `main.css` (if fully relocated) | ~85 |
| **Total** | **~666 lines**, plus 3 targets off the bar and 1 whole component |

---

## 6. Cross-domain consequences

Named, not touched.

1. **`scripts/generate-search-index.js` is not mine.** It emits 148 unresolved
   `{{t:...}}` placeholders into `search-index-en.json` and indexes zero
   marketing routes. Item 4(a) cannot be done without it. Whoever owns build
   scripts, or the operator, needs to take this.
2. **`Sidebar.tsx` is not in my file list but is chrome.** It renders 33 links
   into every page's DOM and duplicates both mega menus. Item 2's relabel is
   only half done without `Sidebar.tsx:137-150`, which reads the same
   `hero.title`. Ownership needs assigning before implementation.
3. **i18n: item 2 costs 21 new keys x 13 locales = 273 naturalized strings.**
   Owner of `src/i18n/translations/*` must be looped in; `en.json` changes
   require `npm run i18n:generate-hashes` and a delta re-naturalization.
4. **`config/solution-pages.ts` is shared by 11 files.** Adding a `navLabel`
   there (rather than in translations) would touch `SPRelatedSolutions.astro`,
   `SPTechStrip.astro`, `solutions/index.astro` and others. I would put the
   label in translations, not in the config, for exactly this reason.
5. **`AccountCta`, `ThemeToggle`, `NewsletterSignup`, `CategoryIcons` are not
   mine** and are consumed by my files. Moving `ThemeToggle` to the footer
   changes `Footer.tsx` (mine) but not `ThemeToggle.tsx` (not mine).
6. **`BaseLayout.astro` is not mine** but owns the `media="print"` onload load
   of `search-modal.css` (`BaseLayout.astro:237-242`), the
   `--announcement-bar-height` token, and 8 inline chrome CSS lines. Item 3 and
   item 5 both want small edits there.
7. **Tokens specialist:** the bar uses `--z-fixed: 30`, `--nav-height`,
   `--announcement-bar-height`, `--nav-scroll-y`, `--nav-scroll-fade`. Item 5
   deletes the last two. `--color-text-secondary` = `rgb(94,94,99)` is what
   makes our nav links lower-contrast than claude.com's; changing nav links to
   `--color-text` is a token-adjacent decision.
8. **Homepage/hero specialist:** the 3 utility icons are the only elements
   overflowing the viewport at 390px. Once removed, any *remaining* horizontal
   scroll on mobile is content, not chrome, and should be re-measured.

---

## 7. Open questions for the operator

Only three, and each changes what gets built.

1. **Item 2's translation bill.** Short nav labels for 21 solutions means 273
   naturalized strings across 13 locales. Options: (a) pay it, best result;
   (b) derive labels from slugs in code, free but English-shaped in 12 locales;
   (c) reduce the mega menu to the 6 category links plus "View all solutions",
   which needs **6** short labels instead of 21 and is the closest structural
   match to claude.com's Solutions dropdown. My recommendation is **(c) then
   (a)**: ship the 6-category menu first, add per-solution labels later.
2. **Blog and Partners: demote to the footer, or keep in the bar?** Both are in
   the footer already. Demoting them is the difference between 4 and 6
   top-level items. This is a business call about how much traffic Partners is
   meant to receive, not a design one.
3. **Language globe: delete from the bar, or keep?** Neither reference site has
   one because both are English-only, so they give no guidance. We ship 13
   locales and already have a labelled switcher in the footer. I would delete
   the nav globe; if international traffic is a live priority the counter-case
   is real and I will keep it (in which case item 1's grid fix becomes
   mandatory rather than incidental).

---

## Appendix: screenshots

All under
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-chrome/`.

| File | What |
|---|---|
| `ours-nav-top.png` | our bar, 1440x900, `/en` |
| `ours-nav-scrolled.png` | our bar at `scrollY=900`: brand + 2 buttons only |
| `ours-megamenu-solutions.png` | 1200x535 panel, 21 sentence-length labels |
| `ours-megamenu-persona.png` | 1020x274 panel, 4 cards |
| `ours-footer.png` | our footer, 632px, 23 links |
| `ours-nav-mobile.png` | 390x844 bar |
| `ours-nav-mobile-390-overflow.png` | same, showing the globe clipped off-screen |
| `ours-sidebar-mobile.png` | drawer open, 375px, 33 links |
| `ours-search-empty.png` | 600x110 blank empty state |
| `claude-nav-top.png` | claude.com bar, 9 targets |
| `claude-nav-scrolled.png` | claude.com at `scrollY=900`, all 9 still there |
| `claude-footer.png` | claude.com footer, 1070px, 161 links |
| `anthropic-nav-top.png` | anthropic.com bar, 7 targets |
| `anthropic-footer.png` | anthropic.com footer, 923px, 90 links |
| `claude-docs-search-empty.png` | command palette with 12 pre-typed suggestions |
| `claude-docs-search-pricing.png` | `pricing` -> "Pricing" at #1 |
