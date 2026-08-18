# RESEARCH: docs, blog, and the long-form reading surfaces

**Author:** `sx-docs` | **Date:** 2026-08-17 | **Status:** research only, zero edits made

Screenshots referenced below live in
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-docs/`.

---

## 1. Verdict

The reading surface is not over-designed, it is over-*instrumented*: `DocsLayout.astro`
is 1,230 lines of which 988 (80%) are an inline `<style>` block and four inline
`<script>` blocks, and the biggest of those scripts is a browser-side HTML-to-Markdown
converter that injects a 141px-wide bordered "Copy section ⌄" split button into every
`h2` and `h3` on every docs page. That single feature is the loudest thing on the page,
it collides with the heading text on mobile, and it pollutes every heading's accessible
name. Underneath that, the content architecture has drifted: `/[lang]/docs` is a 301
redirect so 79 docs have no index, the left sidebar shows only the current category so
the six top tabs are the sole way to change subject, and there are 9 routes (117 built
pages across 13 locales) with zero inbound links from anywhere in the codebase. The
single highest-leverage change is to **delete the per-heading share machinery and the
inline-script layer of `DocsLayout.astro` (483 script lines and roughly 130 of the 505
style lines), replacing it with per-code-block copy buttons**, which is exactly the trade
docs.claude.com makes: one `Copy page` control at the top, one `Copy code` per block,
and a 24x24 borderless anchor icon on headings.

---

## 2. What we have

### 2.1 The two layouts

| Layout | Total lines | Inside `<script>` | Inside `<style>` | Frontmatter | Markup |
|---|---|---|---|---|---|
| `src/layouts/DocsLayout.astro` | 1,230 | **483** | **505** | 85 | ~157 |
| `src/layouts/ContentLayout.astro` | 338 | 0 | 167 (`is:global`) | 72 | ~99 |

Counted by parsing the tag bodies with Python (script in session log). Consumers:

- `DocsLayout` is used by exactly two files: `src/pages/[lang]/docs/[slug].astro:3` and
  `src/components/CheatSheetGrid.astro`.
- `ContentLayout` is used by exactly **one** file: `src/pages/[lang]/blog/[slug].astro`.

**Dead code in DocsLayout**, verified by grep across `src/pages` and `src/components`:

- `variant?: 'article' | 'index'` (`DocsLayout.astro:23`) is never passed by any caller.
  Everything gated on `variant === 'index'` is unreachable: the empty-breadcrumb branch
  (`:47-62`), the `docs-article-index` class (`:121`), and the whole
  `initIndexTabActiveState` hash-tracking script in `DocsTopTabs.astro:93-119` plus its
  `href` branch at `:73-76`.
- `showTOC` (`DocsLayout.astro:26`) and `tocItems` (`:24`) are never passed. Only
  `tocTrackingSelector` is, once, at `docs/[slug].astro:57`.
- `docs/[slug].astro:55` passes `availableLanguages={translations}`, a prop
  `DocsLayout`'s `Props` interface does not declare. It is silently discarded.

**`ContentLayout.astro:169` `<style is:global>` emits 22 selectors globally**, enumerated
by parsing the block:

```
.article-container  .article-container.no-toc  .article-container.with-toc
.article-container.with-toc .article-content   .article-container.with-toc .toc-sidebar
.article-content    .article-description       .article-header   .article-meta
.article-tags       .article-title             .content-article
.content-article .toc-item a  (+ :hover, :focus-visible)
.content-article.has-toc  .meta-item  .meta-label
.tag  .tag:hover  .tag:focus-visible  .toc-sidebar
```

What it leaks, measured rather than assumed: **nothing today**. Every one of those 22
selectors targets markup authored in `ContentLayout`'s own template, not markup coming
through `<Fragment set:html={articleHtml} />` (`:148`). The markdown body is styled by
`src/styles/article-content.css`, a plain CSS import that is global anyway. So
`is:global` buys nothing and could be dropped outright.

The hazard it creates is latent and real: `DocsLayout` defines the *same generic class
names* in a scoped block with **different values**, so the two layouts disagree about
what these names mean.

| Class | `DocsLayout` (scoped) | `ContentLayout` (`is:global`) |
|---|---|---|
| `.article-title` | `clamp(1.75rem,3vw,2.5rem)` `:834` | `clamp(1.75rem,3vw,2.5rem)` `:208` (identical, duplicated) |
| `.article-description` | `font-size: 1.05rem` `:867` | `font-size: var(--font-size-lg)` `:215` |
| `.article-header` | `margin-bottom: var(--space-8)` `:823` | `margin-bottom: var(--space-12)` `:185` |
| `.toc-sidebar` | empty, inherits `sidebar-base` `:878-880` | `position: sticky; top: var(--space-8); max-height: calc(100vh - var(--space-16))` `:273-282` |

The moment anything renders both layouts' markup on one page, or anyone moves a component
between them, these silently fight. `.tag` in particular is a one-word global.

### 2.2 Navigation: five simultaneous nav surfaces on one docs page

Measured on `http://localhost:4321/en/docs/quick-start` at 1440x900
(`docs-quickstart-top.png`):

1. Global header nav (sx-chrome's).
2. `DocsTopTabs` (`DocsLayout.astro:97`), 6 category tabs.
3. `Breadcrumb` (`:122`), Home / Docs / Quick Start.
4. `DocsSidebar` (`:114`), 250px, **30 links**.
5. TOC rail (`:180`), 250px, **23 links**.

Grid is `250px 1fr 250px` (`DocsLayout.astro:754`), hardcoded, ignoring the
`--sidebar-width: 250px` token that `sidebar-shared.css:8` declares (see 2.5).

Structural problems, each verified:

- **`/[lang]/docs` is a 301 redirect.** `curl -o /dev/null -w '%{http_code} %{redirect_url}'`
  returns `301 http://localhost:4321/en/docs/quick-start`; the source is
  `src/pages/[lang]/docs/index.astro:7`, a 9-line file whose entire body is
  `Astro.redirect`. **79 documents, no index page.**
- **The sidebar shows only one category at a time.** `DocsLayout.astro:117` passes
  `visibleCategory={frontmatter.category}`, and `DocsSidebar.astro:49-51` filters the
  category list down to that one. Measured: `sidebarCats: 1`, `sidebarLinks: 30` on a
  Guides page. You cannot see the shape of the documentation from inside it.
- **Changing subject means landing on an arbitrary article.** On an article page
  `DocsTopTabs.astro:75` sets each tab's href to
  `/${lang}/docs/${getBaseSlug(firstDoc.slug)}`, the *first document of that category by
  sort order*. Clicking "Reference" does not take you to a reference index, it takes you
  to whichever reference doc sorts first.
- **The sidebar search is desktop-invisible.** `DocsSidebar.astro:242-244` sets
  `.sidebar-search-container { display: none }` and only re-enables it inside
  `@media (max-width: 48rem)` at `:333-338`. The 49-line `initSidebarSearch` function
  (`:459-507`) ships to every desktop visitor and can never run for them.
- **Category sizes are lopsided.** From `grep -h '^category:' src/content/docs/en/*.md*`:
  Guides 30, Tutorials 18, Legal 9, Concepts 8, Use Cases 8, Reference 6. Guides is a
  30-item flat list inside one collapsible.
- **Only Tutorials has a third level.** `DocsSidebar.astro:109` special-cases
  `category === 'Tutorials'` into essentials/advanced subgroups (13 advanced, 7
  essentials). So navigation depth is 2 for five categories and 3 for one.
- **Two collapse state machines in sessionStorage**, keyed `rediacc_docs_cat_<category>`
  (`:387`) and `rediacc_docs_sub_<sub>` (`:430`).

`Sidebar.tsx` (369 lines) is in my ownership list but is **not** a docs component: it is
the mobile global-nav drawer, imported only by `src/components/Navigation.tsx:10`. Flagged
under cross-domain.

### 2.3 The per-heading share menu, which is the loudest thing on the page

`DocsLayout.astro:281-617` is a 336-line inline script that, for every `h2[id]` and
`h3[id]`, builds a `<span class="heading-share">` containing a split button and a 3-item
dropdown. To make "Copy as markdown" work it ships a **complete HTML-to-Markdown
converter into the browser**: `inlineMarkdownFromNode` (`:314-328`),
`blockMarkdownFromNode` (`:330-385`, handling P/PRE/UL/OL/TABLE/H4-6/BLOCKQUOTE/HR), and
`getSectionMarkdown` (`:387-411`). The site already publishes `/[lang]/docs/<slug>.md`
(`DocsLayout.astro:43`), so this reimplements client-side what a `fetch` of the `.md`
plus a heading split would do.

Measured cost:

- 89 lines of CSS at `DocsLayout.astro:990-1120` to style it, plus
  `padding-right: 4.75rem` forced onto every `h2[id], h3[id]` (`:990-993`).
- The button is **141px wide** and permanently visible (`opacity: 1` at `:1015`, not
  hover-gated).
- **It corrupts every heading's accessible name.** `document.querySelectorAll('h2')`
  `textContent` reads:
  `"IntroductionCopy sectionvCopy section linkCopy direct URL to clipboardCopy as markdownCopy section Markdown contentView Page as MarkdownOpen the Markdown file in a new tab"`.
  That is what a screen reader announces for the heading "Introduction".
- **On mobile it overlaps the heading.** At 390x844: reserved space is
  `padding-right: 76px`, the button is 141px. `docs-mobile-code.png` shows
  "3. Add Your Server" running under the button.
- Blog posts do not get it at all (`headingShare: 0` on
  `/en/blog/fork-a-running-kubernetes-cluster`), so docs and blog headings look different
  for no reason.

### 2.4 Reading typography and code blocks, measured

`getComputedStyle` on `/en/docs/quick-start` at 1440x900:

| Property | Docs (`.article-content`) | Blog (`ContentLayout`) |
|---|---|---|
| Body font | Inter | Inter |
| Body size / line-height | 16px / 28px (1.75) | 16px / 28px |
| Column width | **800px** (`--container-md`) | **870px** (`--container-xl`, `ContentLayout.astro:180-182`) |
| **Characters per line** | **83** | **88** |
| `h1` | 40px / 50px, w700 | 40px / 50px, w700 |
| `h2` | 32px / 56px, w700, **2px border-bottom** | 32px, w700, 2px border-bottom |
| `h3` | 24px, w700 | 24px |
| Type scale h1:body | 2.5x | 2.5x |

Everything is bold 700 and the hierarchy is carried by a horizontal rule under each `h2`
(`article-content.css:15-19`). That rule is what makes the page read as a wiki.

**Code blocks.** Astro's default Shiki is in force: `astro.config.mjs:168-175` sets
`markdown.remarkPlugins` and **no `shikiConfig`**. Result, read off the DOM:

```
class="astro-code github-dark"
style="background-color:#24292e;color:#e1e4e8; overflow-x: auto;"
```

Consequences:

- `article-content.css:38-47` sets `.article-content pre { background-color: var(--color-bg-light) }`
  (`#f8f9fa`). It is **permanently dead**: an inline style always wins. `grep -rn 'astro-code\|\.shiki' src/ public/` returns **zero hits**, so nothing reclaims control.
- `pre` computes `font-family: monospace`; only the inner `code` gets JetBrains Mono
  (`public/styles/main.css:82`).
- **Zero copy buttons.** The Quick Start page has 18 `<pre>` blocks and 0 copy controls
  (`hasCopyButton: false`, `preCount: 18`).
- **Overflow is silent.** At 390 wide the first `pre` is 359px with `scrollWidth` 490px:
  content is clipped with no fade, gradient, or scroll hint. Visible in
  `docs-mobile-code.png`.
- `h2` stays **32px at 390px wide**. `DocsLayout.astro:1144` shrinks `.article-title` on
  mobile but nothing shrinks the markdown `h2`/`h3`, because those live in
  `article-content.css`, which has **zero `@media` blocks**.

Mono font is declared four times with three different fallback chains, under three
parallel token names: `--font-family-mono` (`public/styles/main.css:82`), `--sp-font-mono`
(`src/styles/solution-pages.css:33`), `--cs-font-mono` (`src/styles/cheatsheet.css:12`),
and a bare literal at `src/styles/install-page.css:228`.

### 2.5 `sidebar-shared.css`: an alias layer where two thirds is unused

`sidebar-shared.css:6-37` declares **18 custom properties on `:root`** from a docs-only
stylesheet, several with names that are not namespaced at all (`--border-radius`,
`--transition-speed`, `--link-color`, `--text-hover`). Usage counted with
`grep -rn 'var(<name>' src/ public/`:

| Uses | Tokens |
|---|---|
| **0** | `--border-radius`, `--border-width-accent`, `--border-width-thin`, `--sidebar-bg`, `--sidebar-padding`, `--sidebar-width` |
| **1** | `--link-active-bg`, `--link-active-color`, `--link-color`, `--link-hover-bg`, `--link-hover-color`, `--link-padding`, `--text-hover` |
| 2-8 | `--item-margin` (2), `--sidebar-top-offset` (2), `--sidebar-accent` (3), `--sidebar-border` (4), `--transition-speed` (8) |

**6 of 18 are dead, 7 more have exactly one consumer.** `--sidebar-width: 250px` is
particularly telling: the value it was created for is hardcoded three times in
`DocsLayout.astro:754, 1126, 253`-equivalents instead.

### 2.6 The route surface

61 `.astro` files under `src/pages`. Four are redirect shims
(`index.astro`, `contact.astro`, `legal-information.astro`, `solutions.astro`, each 5-9
lines, all `Astro.redirect(..., 301)`), one is `404.astro`. **56 real content route
templates x 13 locales.**

Full map, grouped:

| Area | Templates | Notes |
|---|---|---|
| Home | 1 | `[lang]/index.astro` |
| Docs | 2 | `docs/index.astro` (**301 redirect**) + `docs/[slug].astro` over **79 en docs** |
| Blog | 2 | `blog/index.astro` + `blog/[slug].astro` over **8 en posts** |
| Solutions | 22 | `solutions/index.astro` + **21 identical 16-line wrappers** |
| Personas | 4 | `for-ceos`, `for-ctos`, `for-devops`, `for-ai-agents`, all 16 lines |
| Resource briefs | 7 | 6 x 11-line wrappers + `nis2-directive-summary.astro` at 203 bespoke lines |
| Legal pages | 6 | `privacy-policy`, `terms-of-service`, `cookie-policy`, `refund-policy`, `telemetry-policy`, `legal-information` |
| Commercial | 5 | `pricing`, `roi-calculator`, `professional-services`, `partners`, `disaster-recovery` |
| Install/download | 2 | `install`, `downloads` |
| Company/contact | 2 | `company`, `contact` |
| Misc | 3 | `changelog`, `newsletter`, `checkout/success` |

Content collections: **1,015 markdown files under `src/content/docs`** (79 en, 78 in each
of the other 12 locales) and **92 under `src/content/blog`** (8 en). The en docs directory
is completely **flat**: `find src/content/docs/en -type d` returns one directory. 79 files,
no folders, hierarchy expressed only by a `category:` frontmatter string, which is written
inconsistently (13 files say `category: Guides`, 17 say `category: "Guides"`).

**Routes with zero inbound links from anywhere in the codebase.** Determined by
collecting every same-host `href` from header/nav/footer in the live DOM, then grepping
`src/` for each remaining route. All return HTTP 200:

| Route | Inbound links found | Locale-multiplied pages |
|---|---|---|
| `/[lang]/changelog` | **0** | 13 |
| `/[lang]/newsletter` | **0** | 13 |
| `/[lang]/resources/dev-environments-brief` | **0** | 13 |
| `/[lang]/resources/encryption-control-brief` | **0** | 13 |
| `/[lang]/resources/multi-cloud-always-brief` | **0** | 13 |
| `/[lang]/resources/nis2-directive-summary` | **0** | 13 |
| `/[lang]/resources/preemptive-defense-brief` | **0** | 13 |
| `/[lang]/resources/ransomware-survival-brief` | **0** | 13 |
| `/[lang]/resources/verified-backups-brief` | **0** | 13 |
| **Total** | | **117 built pages** |

`/[lang]/downloads` is reachable from exactly one place, `install.astro:32`.
`/[lang]/checkout/success` is a post-payment landing page, correctly unlinked.

**Overlapping surfaces.** Legal exists twice: 9 docs (`src/content/docs/en/legal-*.md`,
category `Legal`, in the docs sidebar and the docs top tabs) and 6 standalone pages using
`legal-page.css`. A visitor looking for GDPR can arrive at either.

Page bulk, measured live at 1440x900 (`document.body.scrollHeight / 900`):

| Page | Height | Screens | Top-level sections | Distinct classes in DOM |
|---|---|---|---|---|
| `/en/solutions/instant-recovery` | 11,442px | **12.7** | 15 | **262** |
| `/en/for-ceos` | 6,009px | 6.7 | 8 | 194 |
| `/en/resources/ransomware-survival-brief` | 2,986px | 3.3 | 6 | 129 |
| `/en/docs/quick-start` | 9,463px | 10.5 | n/a | n/a |

The 21 solution pages are byte-identical modulo the slug (verified by
`sed "s/<slug>//g" | md5sum | sort | uniq -c` giving a single hash class of 21). All
variance lives in `src/config/solution-pages.ts` (515 lines) and translations. That part
of the architecture is *good*: the sprawl is in the 2,617-line stylesheet and the 12.7
screens, not in the page files.

### 2.7 Per-page stylesheet census

`wc -l src/styles/*.css` (20 files, 8,806 lines) plus `public/styles/*.css` (5 files,
4,697). Import sites found with
`grep -rl "styles/<name>" src/ --include=*.astro --include=*.tsx`.

| Stylesheet | Lines | Rules | `@media` | `:root` vars | Imported by |
|---|---|---|---|---|---|
| `solution-pages.css` | **2,616** | 438 | 8 | 24 | 6 |
| `pricing-page.css` | 2,321 | 355 | 22 | 0 | 3 |
| `cheatsheet.css` | 395 | 54 | 1 | 0 | 1 |
| `newsletter.css` | 378 | 56 | 2 | 0 | 3 |
| `install-page.css` | 333 | 54 | 1 | 0 | 1 |
| `lead-magnet-modal.css` | 328 | 55 | 7 | 20 | 2 |
| `downloads-page.css` | 312 | 49 | 2 | 0 | 1 |
| `sidebar-shared.css` | 310 | 36 | 3 | 18 | 3 |
| `professional-services-page.css` | 306 | 50 | 1 | 0 | 1 |
| `legal-page.css` | 277 | 41 | 1 | 0 | **6** |
| `team-video.css` | 235 | 34 | 1 | 0 | **0 (dead)** |
| `tutorial-video.css` | 193 | 20 | 1 | 0 | 1 |
| `language-switcher.css` | 191 | 28 | 2 | 0 | 2 |
| `mega-menu.css` | 184 | 25 | 1 | 0 | 1 |
| `persona-mega-menu.css` | 173 | 24 | 1 | 0 | 1 |
| `article-content.css` | **108** | 16 | **0** | 0 | 2 |
| `persona-pages.css` | 59 | 9 | 1 | 0 | 1 |
| `platform-tabs.css` | 52 | 7 | 1 | 0 | 0 direct (2 `@import`) |
| `language-switcher-inline.css` | 34 | 5 | 1 | 0 | **0 (dead)** |
| `disaster-recovery-page.css` | **1** | 0 | 0 | 0 | 1 |

Three findings from that table:

- **`team-video.css` (235 lines) and `language-switcher-inline.css` (34 lines) are
  entirely dead.** No import, and no consumer of their classes:
  `grep -rEo '\btv-[a-z-]+' src/ --include=*.tsx --include=*.astro --include=*.ts` returns
  **1** match total against 34 distinct `.tv-*` classes; `.translation-notice` from the
  other file returns 0. `269 dead lines`.
- **`disaster-recovery-page.css` is one line**: `@import './pricing-page.css';`. Its only
  consumer, `src/pages/[lang]/disaster-recovery.astro:9-10`, imports **both** it and
  `pricing-page.css` directly, so the indirection is not even load-bearing.
- **`legal-page.css` is the only per-page stylesheet with real reuse** (6 pages).
  Every other one serves 1 page.

**Duplication estimate.** Byte-identical rule bodies across files are a weak signal (46
bodies appearing in more than one file, 168 occurrences total). The real duplication is
that each stylesheet re-invents the same primitives under page-local names. Counting
distinct class names matching each primitive across all 25 stylesheets:

| Primitive | Distinct class names |
|---|---|
| `*card*` | **75** |
| `*btn* / *button*` | **41** |
| `*title* / *heading*` | **39** |
| `*hero*` | 34 |
| `*cta*` | 34 |
| `*section*` | 33 |
| `*badge* / *tag* / *pill* / *chip*` | 22 |
| `*grid*` | 16 |

And per stylesheet, the share of lines spent restyling a generic primitive
(card/grid/btn/hero/cta/title/list/table/step/stat/item/section-header/overline):

| Stylesheet | Lines | Lines on generic primitives | Share |
|---|---|---|---|
| `cheatsheet.css` | 396 | 338 | **85%** |
| `install-page.css` | 334 | 206 | **62%** |
| `solution-pages.css` | 2,617 | 1,408 | **54%** |
| `professional-services-page.css` | 307 | 163 | 53% |
| `downloads-page.css` | 313 | 122 | 39% |
| `persona-pages.css` | 60 | 16 | 27% |
| `sidebar-shared.css` | 311 | 40 | 13% |
| `legal-page.css` | 278 | 34 | 12% |
| `article-content.css` | 109 | 9 | 8% |
| **Total (my 10 files)** | **4,727** | **2,336** | **49%** |

**Roughly 2,300 of my 4,700 stylesheet lines are page-local reimplementations of a card,
a button, a grid, a section header, or a heading.** That is the duplication figure.

On top of that, the `--sp-*` dark palette is written out **six times**: three copies in
`solution-pages.css` (`:18` light, `:2107` + `:2118` dark, `:2527` + `:2536` dark again)
and three in `lead-magnet-modal.css` (`:67`, `:75`, `:305`, `:313`). Verified with
`grep -n -- '--sp-bg-white:'`, which returns 6 hits of `#1a1a1b` across the two files.
`solution-pages.css:1564-1676` (113 lines) styles `SPSocialProof`, a component neither
`SolutionPage.astro` nor `PersonaPage.astro` imports any more (both keep it only as a
comment, `SolutionPage.astro:139`, `PersonaPage.astro:124`).

### 2.8 Token ownership, for the record

Custom properties are declared on `:root` in **7 places**:
`public/styles/main.css` (146), `src/styles/sidebar-shared.css` (18),
`BaseLayout.astro <style>` (17), `src/styles/solution-pages.css` (7),
`src/styles/lead-magnet-modal.css` (5), `public/styles/responsive.css` (1),
`src/components/AnnouncementBar.astro` (1). 174 distinct properties, **20 declared in more
than one file**, including `--color-text`, `--color-bg`, `--font-family`,
`--font-size-base`, `--space-4`. This is sx-tokens' problem, not mine, but it is the
reason nothing in my domain can be reasoned about from a single file.

---

## 3. What docs.claude.com does

All values read from the live page at 1440x900 with `getComputedStyle`. URL:
`https://platform.claude.com/docs/en/about-claude/models/overview` (docs.claude.com
redirects here). Screenshots: `claude-docs-top.png`, `claude-docs-code.png`,
`claude-docs-mobile.png`.

| Property | Value |
|---|---|
| Page background | `rgb(252, 252, 251)` (warm off-white, not `#fff`) |
| Body font | `anthropicSans` |
| Body size / line-height | **14px / 21px (1.5)** |
| Body color | `rgb(82, 81, 78)` (muted grey, not near-black) |
| Column width | 832px |
| **Characters per line** | **98** |
| `h1` | **anthropicSerif**, 28px / 36.4px, **w500** |
| `h2` | **anthropicSerif**, 24px, **w500**, `border-bottom: 0px` |
| `h3` | anthropicSerif, 22px, w500 |
| Type scale h1:body | **2.0x** |
| Inline `code` | bg `rgb(246,246,244)`, 14px, `border-radius: 8px`, no border |
| `pre` | **transparent background**, 13px / 19px, `anthropicMono`, inside a thin-bordered light container |
| Heading control | **24x24px**, `background: transparent`, `border: 0`, aria-label "Copy link to clipboard" |
| Page control | one `Copy page` split button, top-right of the title |
| Code control | one `Copy code` per block |
| Sidebar | one flat list, bold group labels, no chevrons, no numbers, no icons |
| Sidebar links visible | 22 (whole nav in view, no collapse) |
| Top nav links | 8 |
| Right TOC rail | present only above `min-[91.875rem]` (1,470px). **Hidden at 1440.** |
| Mobile (390x844) | `h2` stays 24px, `pre` 359px wide with `scrollWidth` 375px (fits) |

The moves that make it feel simple, stated as mechanisms rather than vibes:

1. **Hierarchy comes from typeface and colour, not weight and rules.** Serif headings at
   w500 against sans body at `rgb(82,81,78)`. No `border-bottom` anywhere. Our equivalent
   is 700-weight sans everywhere plus a 2px rule under every `h2`.
2. **A tighter type scale.** 2.0x h1-to-body vs our 2.5x, and 1.71x h2-to-body vs our
   2.0x. Their page has less vertical drama and therefore less to skip past.
3. **Two columns at 1440, not three.** The TOC rail only appears when the viewport can
   afford it. We show three columns at every width above 1200px.
4. **One control per scope.** Page: one `Copy page`. Block: one `Copy code`. Heading: a
   24x24 transparent icon. We have zero at block scope and a 141px permanently-visible
   split button at heading scope.
5. **Light code blocks.** Transparent `pre` inside a bordered light container, so the page
   stays one surface. Ours are `#24292e` slabs punched into a white page.
6. **Search lives in the sidebar and is always there** (`Ctrl K`). Ours is hidden on
   desktop.
7. **Denser body text is fine.** They run 98 characters per line at 14px/1.5 and it reads
   well, because the type is smaller and the colour is muted. Column width alone is not
   what makes reading pleasant.

**Measurement limitation, stated honestly:** `www.anthropic.com/news/*` and
`www.anthropic.com/engineering/*` did **not** render article body content in
`agent-browser` (0 paragraphs over 200 characters on the news article; the engineering
page yielded one paragraph at `rgb(160,160,160)` that is cookie-banner text). I have no
measured values for the Anthropic long-form blog and have not guessed any.

---

## 4. The delta

| Dimension | Ours | docs.claude.com | Gap |
|---|---|---|---|
| Docs layout file size | 1,230 lines (80% inline script + style) | n/a | The layout is the largest file in the domain |
| Heading control width | **141px**, always visible | **24px**, transparent | 6x, and ours is never not there |
| Heading accessible name | Includes 130+ chars of menu text | Clean | Broken vs correct |
| Copy buttons on code blocks | **0** of 18 | 1 per block | Missing entirely |
| Code block background | `#24292e` (Astro default, unconfigured) | transparent, light container | Uncontrolled vs designed |
| `h2` treatment | 32px w700 + 2px border-bottom | 24px w500, no border | Wiki vs document |
| Type scale h1:body | 2.5x | 2.0x | Ours shouts |
| Columns at 1440 | 3 (250 / 800 / 250) | 2 | One rail too many |
| Chars per line | 83 (docs) / 88 (blog) | 98 | Ours is *narrower*, not the problem |
| Body colour | `rgb(26,26,26)` near-black | `rgb(82,81,78)` muted | Ours has no contrast headroom for headings |
| Sidebar scope | 1 category, 30 links | whole nav, 22 links | Cannot see the shape of the docs |
| Sidebar search on desktop | **hidden** (`display:none`) | always visible | Feature shipped and disabled |
| Docs index | **301 redirect** | real landing page | 79 docs with no front door |
| `h2` size at 390px | **32px**, button overlaps text | 24px, no overlap | Mobile is broken, not just cramped |
| Code overflow at 390px | 359px box, 490px content, no hint | fits | Silent clipping |
| Per-page stylesheets | 20 files, 8,806 lines, 15 of them serve 1 page | one system | 2,336 lines re-styling primitives |
| Distinct `*card*` classes | **75** | one card | No design system |

---

## 5. Proposed simplification, ordered by leverage

### P1. Delete the per-heading share machinery; add per-code-block copy

**Change.** Remove the `heading-share` script and CSS entirely. Keep the existing
`Copy as Markdown` page button (`DocsLayout.astro:151-164`), which already works off the
published `.md`. Add a small copy button to each `pre.astro-code`, injected by one short
script or a rehype plugin.

**Files.** `src/layouts/DocsLayout.astro` only: delete `:281-617` (336 script lines) and
`:990-1120` (131 style lines), keep `:840-864` (the page-level button styles). Net **-467
lines from a 1,230-line file.**

**Risk.** Low. Nothing else references `.heading-share`
(`grep -rn 'heading-share' src/ public/` is confined to this file). The deep-link
capability is preserved by the `id` attributes, which remark generates independently.

**Proof.** Re-run the heading `textContent` probe and assert no heading contains
`"Copy section"`. Screenshot at 390x844 and confirm "3. Add Your Server" no longer
collides. Assert `document.querySelectorAll('.article-content pre button').length === 18`
on Quick Start.

### P2. Take control of code blocks

**Change.** Set `shikiConfig` in `astro.config.mjs` with an explicit theme (or a
light/dark pair), then delete the dead `pre` background rule.

**Files.** `astro.config.mjs:168-175` (**sx-primitives / build config, not mine, flagged
below**), `src/styles/article-content.css:38-47`.

**Risk.** Medium: changes the look of 1,015 markdown files at once, and dark mode has to
be checked. This is the one item where I would look at both themes before committing.

**Proof.** `getComputedStyle(pre).backgroundColor` must equal a token value, and the
element must no longer carry an inline `background-color`. Toggle the site theme and
re-read.

### P3. Give the docs a front door and a whole-shape sidebar

**Change.** Replace the `/[lang]/docs` redirect with a real index that lists the six
categories and their 79 documents. Stop passing `visibleCategory`, so the sidebar shows
every category with the current one expanded. Point the top tabs at
`/[lang]/docs#<category>` on the index rather than at an arbitrary first article, or
delete the tabs entirely once the sidebar shows everything.

**Files.** `src/pages/[lang]/docs/index.astro` (rewrite from 9 lines),
`src/layouts/DocsLayout.astro:117`, `src/components/DocsSidebar.astro:49-51`,
`src/components/DocsTopTabs.astro:71-89`.

**Risk.** Medium. 30 items in Guides makes a whole-shape sidebar long; it needs the
collapse behaviour that already exists (`DocsSidebar.astro:373-415`) to remain. Also worth
splitting Guides, which is 38% of all docs.

**Proof.** `curl -o /dev/null -w '%{http_code}' /en/docs` returns 200. Sidebar probe
returns `sidebarCats: 6`. Every top tab href resolves without a redirect.

### P4. Turn the desktop sidebar search on, or delete it

**Change.** Either drop `display: none` at `DocsSidebar.astro:243` so the search input is
always present, or delete the input, the container styles, and the 49-line
`initSidebarSearch` function.

**Files.** `src/components/DocsSidebar.astro:138-145, 242-266, 333-338, 459-507`.

**Risk.** None either way. Currently it is dead weight on desktop.

**Proof.** `getComputedStyle('.sidebar-search-container').display !== 'none'` at 1440, or
the selector returns null.

### P5. Fix the reading typography

**Change.** In `article-content.css`: drop the `border-bottom` from `h2`
(`:15-19`); move headings to w600; add the first `@media` block this file has ever had, so
`h2` drops to ~24px and `h3` to ~20px below 48rem; give `pre` an overflow affordance.
Consider a muted body colour so headings gain contrast headroom.

**Files.** `src/styles/article-content.css` (108 lines today, would grow to roughly 140).

**Risk.** Low, but it changes every doc and blog post at once. Worth a
`diff screenshot --baseline` sweep over a handful of representative docs.

**Proof.** `getComputedStyle(h2).borderBottomWidth === '0px'`; at 390 wide
`getComputedStyle(h2).fontSize` is 24px not 32px.

### P6. Collapse the layout duplication

**Change.** `ContentLayout` serves one page and duplicates `DocsLayout`'s article header.
Extract the shared article header (title, description, meta) into one component, drop
`is:global` from `ContentLayout.astro:169`, and delete the branches that can never run:
`variant === 'index'` in `DocsLayout` and `DocsTopTabs`, the `isDoc` branch in
`ContentLayout.astro:31, 51-56` (`ContentLayout` is only reachable from `blog/[slug]`), the
unused `showTOC` / `tocItems` props, and the `availableLanguages` prop passed at
`docs/[slug].astro:55` that nothing receives.

**Files.** `src/layouts/ContentLayout.astro`, `src/layouts/DocsLayout.astro`,
`src/components/DocsTopTabs.astro`, `src/pages/[lang]/docs/[slug].astro:55`.

**Risk.** Low, all of it is provably unreachable.

**Proof.** Blog and docs pages render identically before and after
(`diff screenshot --baseline`). `grep -c "variant === 'index'"` returns 0.

### P7. Delete the dead stylesheets and the dead tokens

**Delete outright:**

| File / block | Lines | Evidence |
|---|---|---|
| `src/styles/team-video.css` | 235 | 0 importers, 1 `tv-*` reference against 34 classes |
| `src/styles/language-switcher-inline.css` | 34 | 0 importers, `.translation-notice` used 0 times |
| `src/styles/disaster-recovery-page.css` | 1 | 1-line `@import` its only consumer bypasses |
| `solution-pages.css:1564-1676` (SOCIAL PROOF) | 113 | `SPSocialProof` not imported by either template |
| 6 dead tokens in `sidebar-shared.css:6-37` | ~8 | 0 `var()` uses each |
| `--sp-*` dark palette copies at `solution-pages.css:2527-2539` and `lead-magnet-modal.css:305-320` | ~30 | identical values to `:2107` |

**~421 lines deleted with zero behavioural change.**

### P8. Consolidate the primitives (the big one)

**Change.** One `card`, one `button`, one `section-header`, one `grid`, defined once in
the token/primitive layer, replacing the 75 card classes, 41 button classes, and 39 title
classes spread across 20 stylesheets. Then `solution-pages.css` shrinks from 2,617 lines
toward roughly 1,200 (the 54% measured as primitive restyling), `cheatsheet.css` from 396
toward ~60 (85%), `install-page.css` from 334 toward ~130 (62%),
`professional-services-page.css` from 307 toward ~145 (53%).

**Files.** All ten of my stylesheets, but it **cannot start in my domain**: the primitives
have to exist first, in sx-tokens' and sx-primitives' files.

**Risk.** High, and it touches every page. This is the item to sequence last and to run as
one change rather than a trickle.

**Proof.** Total CSS line count across `src/styles` + `public/styles` drops from 13,503;
`diff screenshot --baseline` over one page per family.

### P9. Route surface

**Change (recommendation, operator's call).** The 9 unlinked routes are 117 built pages
nobody can reach. If the resource briefs are ad and email landing pages, that is a
legitimate reason to keep them; if not, they are 7 templates and 91 pages of dead weight.
`/[lang]/changelog` and `/[lang]/newsletter` have no such excuse and no inbound link.
Separately, legal exists twice (9 docs plus 6 pages) and should exist once.

**Risk.** Low technically, but this is a content decision, not a code one. See open
questions.

---

## 6. Cross-domain consequences

- **`astro.config.mjs:168-175` has no `shikiConfig`.** Fixing code-block theming (P2)
  means editing the build config, which is not in my file list. Whoever owns it should
  know that `article-content.css:38-47` is currently dead because of this.
- **`src/components/Sidebar.tsx` is not a docs component.** 369 lines, imported only by
  `src/components/Navigation.tsx:10`, it is the mobile global-nav drawer. It was assigned
  to me but belongs with sx-chrome. I have not touched it and it is not in any of my
  proposals.
- **Token collisions are upstream of everything here.** 20 custom properties are declared
  in two files (`BaseLayout.astro <style>` and `public/styles/main.css`), including
  `--color-text`, `--color-bg`, `--font-family`, `--font-size-base`, `--space-4`.
  `sidebar-shared.css:6-37` adds 18 more from a docs-only stylesheet, four of them with
  unnamespaced names (`--border-radius`, `--transition-speed`, `--link-color`,
  `--text-hover`). Deleting the 6 dead ones is mine; deciding where tokens live is
  sx-tokens'.
- **P8 depends on sx-primitives.** I cannot delete 2,336 lines of card/button/grid
  restyling until there is a card, a button, and a grid to point at. My files are ready to
  be the first consumers.
- **`src/styles/pricing-page.css` (2,321 lines) is sx-pricing's**, but
  `src/pages/[lang]/disaster-recovery.astro:9-10` imports it twice (once directly, once
  through my `disaster-recovery-page.css`). When I delete that 1-line file, that page's
  import list needs the one-line touch.
- **`src/components/Breadcrumb.astro` is sx-chrome's.** It is rendered by both my layouts
  (`DocsLayout.astro:122`, `ContentLayout.astro:84`). If its markup changes, both layouts
  are affected.
- **`solution-pages.css` is shared with the homepage.** `src/pages/[lang]/index.astro`
  imports it, so P8's changes there land in sx-homepage's surface.
- **i18n.** The 79 docs exist in 13 locales (1,015 files). Any change to docs *content
  structure* (splitting Guides, adding an index) is a 13x translation obligation. Changes
  to layout, CSS, and route wiring are not.

## 7. Open questions for the operator

1. **The resource briefs.** Seven templates and 91 built pages with zero inbound links.
   Are they ad or email landing pages that are supposed to be unlinked, or are they
   orphans to delete? Same question for `/[lang]/changelog` and `/[lang]/newsletter`,
   which have no inbound link at all.
2. **Legal exists twice**, as 9 docs pages in the docs sidebar and as 6 standalone pages
   with their own stylesheet. Which one is the real one?
3. **Code blocks: light or dark?** docs.claude.com uses light code on a light page and it
   is a large part of why the page reads as one surface. Ours are `#24292e` slabs, but
   only because Astro's default was never configured. Changing it is visible on every doc
   and every blog post.
4. **Serif headings?** The single biggest visual difference from docs.claude.com is a
   serif display face at weight 500 against sans body. We ship Inter and JetBrains Mono
   only. Adding a serif is a font-loading decision, not just a CSS one, and it belongs to
   whoever owns the font budget.
