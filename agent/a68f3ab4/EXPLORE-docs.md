# EXPLORE-docs — docs surface taxonomy + layout

Read-only investigation, 2026-08-23. Repo root `/home/muhammed/monorepo/console`, site
`packages/www`. All paths below are relative to `packages/www/` unless absolute.

Measurements are live: dev server on `http://localhost:4321`, driven with `agent-browser`
(session `expdocs`) at 1440x900 and 1920x1080. Nothing in the repo was modified; the two CSS
experiments in section 4.5 were applied in the browser only and discarded with the session.

---

## 1. The docs taxonomy

### 1.1 Where the content lives

`src/content/docs/<lang>/<slug>.{md,mdx}` — **13 locale directories, not one flat dir.**

| locale | files |
|---|---|
| en | **79** (61 `.md`, 18 `.mdx`) |
| ar de es et fr it ja ko pt ru tr zh | 78 each |

`79 + 78x12 = 1,015` — that is where the "~1,015 flat markdown files" number comes from. It
is 79 *documents* rendered in 13 locales, not 1,015 distinct documents. The only doc missing
a translation is `siem-integration` (present in `en` only).

All 18 `.mdx` files are the tutorials (they need `import TutorialStep from
'../../../components/tutorial/TutorialStep.astro'` and JSX component calls, which `.md`
cannot carry).

### 1.2 Frontmatter schema

`src/content/config.ts:21-48` (`docsCollection`):

```ts
title:       z.string()
description: z.string()
category:    z.enum(['Tutorials','Guides','Concepts','Reference','Use Cases','Legal'])
tags:        z.array(z.enum(DOC_TAGS)).default([])
subcategory: z.enum(['essentials','advanced']).optional()      // config.ts:38
order:       z.number().optional()
toc:         z.boolean().default(true)
cardGrid:    z.boolean().default(false)                        // CheatSheetGrid render mode
language:    z.enum(LANGUAGES).default('en')
sourceHash:  z.string().optional()
```

`category` and `tags` are **English identifiers in every locale** — routing/filter keys, not
display text. Translated labels live under `documentation.categories.*` and
`documentation.tags.*`. The single source for both vocabularies plus their label maps is
`src/utils/docs-categories.ts` (`CATEGORY_ORDER:17-24`, `CATEGORY_KEYS:44-51`,
`DOC_TAGS:99-114`, `TAG_KEYS:124-139`, `CATEGORY_GLYPHS:180-194`).

`content/config.ts` imports `DOC_TAGS` directly, so an unknown tag fails the build rather
than creating an unreachable filter.

### 1.3 CRITICAL: there are TWO sub-grouping fields, and they are different things

The brief assumed "Essentials"/"Advanced" is what `/en/docs?category=Tutorials` shows under
"Filter by topic". It is not.

| what the operator sees | field | vocabulary | where it renders |
|---|---|---|---|
| "Filter by topic" on `/en/docs` | **`tags`** | 14 values | browse rail ONLY — `src/pages/[lang]/docs/index.astro:130-145` |
| "Essentials" / "Advanced" | **`subcategory`** | 2 values | **left sidebar ONLY, Tutorials ONLY** — `src/components/DocsSidebar.astro:106` |

Verified live on `/en/docs?category=Tutorials`: the two `.docs-rail-summary` elements read
exactly `"Filter by category"` and `"Filter by topic"`, and the topic list renders **11 tag
rows** with live counts:

```
getting-started:5  cli:4  repositories:5  forking:3  backup:2  storage:2
containers:6  networking:1  migration:2  security:2  operations:4
```

Essentials/Advanced do not appear on the browse page at all. (The topic `<details>` group is
collapsed by default — `index.astro:130` has no `open` attribute, unlike the category group
at `:107`. The labels themselves render correctly.)

English strings (`src/i18n/translations/en.json`):
- `documentation.browse.filterLabel` = "Filter by category"
- `documentation.browse.topicLabel`  = "Filter by topic"
- `documentation.subcategories.essentials` = "Essentials", `.advanced` = "Advanced"
- `documentation.tags.*` = Accounts, AI Agents, Backup, CLI, Compliance, Containers,
  Forking, Getting Started, Migration, Networking, Operations, Repositories, Security,
  Storage

### 1.4 Matrix: category -> tag -> count (English, 79 docs)

66 docs carry **2** tags, 12 carry **1**, 1 carries **none**, so rows sum to 158 > 79.

```
tag               Tutorials  Guides  Concepts  Reference  Use Cases  Legal   TOTAL
account                   .       7         1          1          .      .       9
ai-agents                 .       4         1          2          .      .       7
backup                    2       1         .          .          4      .       7
cli                       4       8         3          2          .      .      17
compliance                .       .         1          .          .      9      10
containers                6       7         2          .          1      .      16
forking                   3       .         .          2          4      .       9
getting-started           5       4         .          .          .      .       9
migration                 2       2         .          .          3      .       7
networking                1       2         1          .          .      .       4
operations                4       9         4          .          1      .      18
repositories              5       2         1          1          .      .       9
security                  2       6         2          .          .      3      13
storage                   2       2         .          2          3      .       9
------------------------------------------------------------------------------------
(no tag)                  .       .         .          1          .      .       1
DOCS                     18      30         8          6          8      9      79
```

- **Docs with >= 1 tag: 78 / 79.**
- **Docs with no tag: 1** — `cli-application` (Reference).
- **Every category has tags.** No category is tag-free.
- Category totals match the browse page's own counts, verified live:
  Tutorials 18 / Guides 30 / Concepts 8 / Reference 6 / Use Cases 8 / Legal 9 = 79.

### 1.5 Matrix: category -> subcategory -> count

```
category      essentials   advanced   (unset)   total
Tutorials              7         11         0      18
Guides                 0          0        30      30
Concepts               0          0         8       8
Reference              0          0         6       6
Use Cases              0          0         8       8
Legal                  0          0         9       9
--------------------------------------------------------
                       7         11        61      79
```

**Only Tutorials uses `subcategory`. All 61 non-tutorial docs have it unset**, and the
sidebar's `groupBySubcategory` defaults a missing value to `'essentials'`
(`DocsSidebar.astro:86`) — harmless today only because the grouping is gated on
`category === 'Tutorials'` at `:106`.

### 1.6 Per-doc listing (English)

**Tutorials (18)** — `order`, slug, subcategory, tags:

```
 1 tutorial-installation        essentials  getting-started, cli
 2 tutorial-ssh-keys            essentials  getting-started, security
 3 tutorial-add-server          essentials  getting-started, repositories
 4 tutorial-create-repo         essentials  getting-started, repositories
 5 tutorial-deploy-app          essentials  getting-started, containers
 6 tutorial-work-with-repo      essentials  repositories, containers
 7 tutorial-vscode-browser      essentials  cli, containers
 8 tutorial-forking             advanced    forking, repositories
 9 tutorial-fork-isolation      advanced    forking, security
10 tutorial-managing-secrets    advanced    security, cli
11 tutorial-backup-restore      advanced    backup, storage
12 tutorial-networking          advanced    networking, containers
13 tutorial-production-mode     advanced    operations, containers
14 tutorial-monitoring          advanced    operations, cli
15 tutorial-branching           advanced    forking, repositories
16 tutorial-live-migration      advanced    migration, operations
17 tutorial-delta-transfer      advanced    backup, migration
18 tutorial-storage-management  advanced    storage, operations
```

**Guides (30):** quick-start(-1), requirements(0), installation(1), rdc-cheat-sheet(3,
`cardGrid: true` — the only one), setup(3), repositories(4), autostart-recovery(5),
on-premise(5), rules-of-rediacc(5), services(5), kubernetes(6), networking(6),
backup-restore(7), subscription-licensing(7), config-storage(8), license-chain(8),
web-console(8), monitoring(9), tools(9), troubleshooting(10), migration(11),
account-management(12), pruning(12), account-security(13), hub(14), siem-integration(15),
ai-agents-overview(30), ai-agents-claude-code(31), ai-agents-cursor(32), ai-agents-mcp(33)

**Concepts (8):** architecture(0), rdc-vs-renet(1), experimental-vms(2),
release-channels(2), data-regions(3), server-reference(3), proxy-and-executor(4),
ai-agents-safety(35)

**Reference (6):** cli-application(2, **untagged**), repo-diff(40), repo-branching(41),
agents-md-template(50), ai-agents-json-output(51), limits(99)

**Use Cases (8):** dynamic-resource-scaling(1), time-travel-recovery(2),
legacy-database-scaling(3), risk-free-upgrades(4), cross-backup(5), blackout(6),
zero-cost-backup(7), development-environments(10)

**Legal (9):** legal-overview(0), legal-gdpr(1), legal-soc2(2), legal-hipaa(3),
legal-ccpa(4), legal-iso27001(5), legal-pci-dss(6), legal-data-sovereignty(7),
legal-nis2-dora(8)

### 1.7 Two different category orders, on purpose

- Browse + Learn menu + top tabs: `CATEGORY_ORDER` = Tutorials, Guides, Concepts,
  Reference, Use Cases, Legal (`docs-categories.ts:17-24`)
- Sidebar: Guides(0), Concepts(1), Reference(2), Tutorials(3), Use Cases(4), Legal(5)
  (`DocsSidebar.astro:42-49`) — documented at `:37-41` as deliberate ("the sidebar opens on
  Guides because that is where a reader already inside the docs continues").

---

## 2. The docs browse page

### 2.1 It is NOT a redirect any more

`src/pages/[lang]/docs/index.astro` — **381 lines.** The `Astro.redirect('/<lang>/docs/quick-start', 301)`
is history, documented in the file's own header at `:5-7`. Verified: `GET /en/docs` -> 200,
435,283 bytes.

There is no separate `browse` route.

### 2.2 Structure

```
DocsLayout variant="index" showTOC={false}          index.astro:69-75
  .docs-browse                        (styles/docs-browse.css:6, max-width 84rem, centred)
    header.docs-browse-hero           :79-85   glyph + h1 + lede
    .docs-browse-body                 :87      grid 15rem / minmax(0,1fr), gap --space-10
      aside.docs-rail                 :92-150  sticky filter rail
        label.docs-rail-search        :95-103  <input type=search>
        details.docs-rail-group--primary[open]  :107-126  "Filter by category"
        details.docs-rail-group                 :130-145  "Filter by topic"  (collapsed by default)
        button.docs-browse-clear      :147-149
      .docs-browse-results            :152
        p.docs-browse-status > output.docs-browse-tally   :153-155   "18 / 79"
        section.docs-browse-group[data-category] x6       :158-249
          h2.docs-browse-group-title
          ul.docs-browse-grid                             :165
            li.docs-browse-item[data-category][data-tags][data-text]  :184-189
              div.docs-card                                          :190-243
        p.docs-browse-empty[hidden]   :252
```

### 2.3 There is no card COMPONENT

The card is **inlined** at `index.astro:190-243`. Styling lives in
`src/styles/docs-browse.css` (`.docs-card` at line 233). If a topic chip is wanted, the edit
site is `index.astro`, not a component file.

### 2.4 What a card renders today

Verified against the served HTML for `tutorial-installation`:

1. `<img class="docs-card-thumb" src="/img/docs-thumbs/tutorial-installation.svg" alt="" width="320" height="120" loading="lazy">` — `index.astro:199-207`
2. `<h3 class="docs-card-title"><a class="docs-card-link" href="/en/docs/tutorial-installation">Installation</a></h3>` — `:208-217`
3. `<span class="docs-card-chip"><svg class="docs-chip-glyph"><path d="M9 6.5 17.5 12 9 17.5Z"/></svg> Tutorials</span>` — `:218-223`
   **This is the only metadata chip. Category and nothing else.**
4. `<p class="docs-card-description" id="docdesc-...">` — absolutely positioned overlay at
   `opacity:0`, revealed on hover / focus-within / `.is-revealed`
   (`docs-browse.css:387-408`), kept in the a11y tree deliberately.
5. `<button class="docs-card-info">` — the touch path to (4), a SIBLING of the stretched
   link so it is valid HTML (`:230-242`).

The tags **are already in the DOM**, as `data-tags="getting-started cli"` on the `<li>`
(`index.astro:187`), consumed only by the filter script. Nothing renders them.

Adding a topic chip needs **no data plumbing**: `const tags = doc.data.tags ?? []` is already
bound at `index.astro:168`, and `tagLabel` at `:47`.

### 2.5 Filter mechanics

`index.astro:258-381`, plain TS in an Astro `<script>`:

- OR within an axis, AND across axes, plus a free-text pass over `data-text` (`matches()` at `:279-285`)
- URL state `?category=a,b&tag=c,d&q=...` written with `history.replaceState` (`:329-340`)
- Facet counts recomputed with that facet's own selection removed, so a count means "how
  many would I get if I ticked this" (`:308-322`)
- A topic row whose count is 0 and which is unchecked is `hidden` (`:321`) — this is what
  makes the topic list behave as a sub-group of the chosen category
- Deep links resolve on load; unknown values are dropped rather than hiding everything (`:366-380`)
- Progressive enhancement: with JS off every card is server-rendered and visible

### 2.6 Colour system

One hue per category as a CSS custom property on the group
(`docs-browse.css:311-333`): Tutorials 150, Guides 220, Concepts 280, Reference 185,
Use Cases 35, Legal 345. It drives `.docs-chip-glyph`'s stroke only
(`hsl(var(--docs-hue) 45% 38%)`, dark `68%`). The thumbnails cannot read it (see 5.1).

### 2.7 Measured (1920x1080, `?category=Tutorials`)

```
.docs-content        1873px   (one grid track — see 4.2)
.docs-browse         1344px   (84rem cap, centred)
.docs-rail            240px
.docs-browse-results 1064px
.docs-browse-grid    246px 246px 246px 246px   (4 across)
visible cards        18   tally "18 / 79"
.docs-sidebar        absent   .docs-top-tabs absent   .toc-sidebar absent
```

Breakpoint: `docs-browse.css:145` — below 60rem the rail stacks above the grid and loses
`position: sticky`.

---

## 3. The left sidebar

`src/components/DocsSidebar.astro` — 457 lines.

### 3.1 How it groups today

- Loads all docs, then filters **`doc.data.language === currentLang` with NO English
  fallback** (`:20`). Contrast `index.astro:54-60`, which does fall back. A locale missing a
  doc simply shows one fewer sidebar entry.
- Sorts by `category.localeCompare` then `order ?? 999` (`:21-27`), buckets into
  `docsByCategory` (`:30-35`), then orders the buckets by the sidebar-specific map at
  `:42-49`.
- `visibleCategory` prop (`:12`, `:56-58`) filters to ONE category. `DocsLayout.astro:197`
  passes `frontmatter.category`, so an article page's rail shows only the current category.
  Verified on `/en/docs/tutorial-installation`: one category item, 18 doc links,
  `essentials:7` / `advanced:11`.
- Expansion defaults (`:95-104`): expanded if it holds the active doc, or has <= 3 items,
  or is `Guides`. State persisted in `sessionStorage` under `rediacc_docs_cat_<category>`
  (`:346`).
- `revealActiveDoc()` (`:424-438`) scrolls the rail's own `scrollTop` rather than using
  `scrollIntoView`, which would have moved the article too.

### 3.2 The subcategory grouping code

All of it, in one component:

| lines | what |
|---|---|
| `:69-72` | `SUBCATEGORY_KEYS` -> `documentation.subcategories.{essentials,advanced}` |
| `:73-76` | `SUBCATEGORY_ORDER` = essentials 0, advanced 1 |
| `:77-80` | `subcategoryLabel(sub)` |
| `:83-92` | `groupBySubcategory(entries)` — buckets on `doc.data.subcategory ?? 'essentials'` |
| **`:106`** | **`const subgroups = category === 'Tutorials' ? groupBySubcategory(...) : null`** — the hardcoded gate |
| `:107-117` | builds `{key, groupId, label, entries, expandedAttr}`; essentials open by default |
| `:163-200` | renders `li.subcategory-item > button.subcategory-header + ul.doc-list` |
| `:201-217` | the flat fallback for every other category |
| `:241-279` | subcategory CSS (uppercase 600-weight `--font-size-xs` header, chevron, collapse) |
| `:281-288` | `.doc-link-num` — the `order` prefix, tutorials only in practice |
| `:379-413` | `initCollapsibleSubcategories()`; `sessionStorage` key `rediacc_docs_sub_<sub>` (`:389`) |

### 3.3 What grouping by topic would take

Small: swap `groupBySubcategory` (`:83-92`) for a tag-based grouper and delete the
`=== 'Tutorials'` gate at `:106`. Everything downstream (`:163-200`) is already generic over
`{key, groupId, label, entries, expandedAttr}`, and `makeTagLabel` from
`utils/docs-categories.ts:141-152` supplies the labels.

Two real snags:

1. **66 of 79 docs carry two tags.** A doc would appear under two headings unless a primary
   tag is chosen (first tag wins, or a new `primaryTag` field, or reuse `order`).
2. **The `sessionStorage` key at `:389` is `rediacc_docs_sub_<sub>` — global, not
   per-category.** Two categories sharing a tag would share collapse state. Prefix it with
   the category if the vocabulary widens from 2 values to 14.

---

## 4. Tutorial doc page layout — exact CSS and measurements

### 4.1 Where the width control actually lives

**Two files, and only two.** `src/styles/article-content.css` (116 lines) has **no** width
constraints at all — its only `width` hits are two `scrollbar-width: thin` at `:53` and
`:86`. It is not a factor.

`--docs-prose`, `--docs-measure`, `--docs-tracks` are grepped across the whole of `src/`:
**every occurrence is inside `src/layouts/DocsLayout.astro`.** Nothing else reads them.

### 4.2 `src/layouts/DocsLayout.astro` scoped `<style>` (1470 lines total; style block `:664-1442`)

| line | declaration | value |
|---|---|---|
| `:672` | `.docs-shell { padding: ... var(--space-4) ... }` | 16px inline each side |
| `:678` | `--sidebar-top-offset` | `calc(var(--docs-chrome-height,3rem) + var(--space-4) + var(--space-4))` |
| `:680` | `--docs-rail-nav` | **`250px`** |
| `:681` | `--docs-rail-toc` | **`250px`** |
| `:682` | `--docs-measure` | **`800px`** |
| `:683` | `--docs-slack` | **`1fr`** |
| `:692-696` | `--docs-tracks-body` | `var(--docs-rail-nav) minmax(0,var(--docs-slack)) minmax(0,var(--docs-measure)) minmax(0,var(--docs-slack))` |
| `:697` | `--docs-tracks` | `var(--docs-tracks-body) var(--docs-rail-toc)` |
| **`:704`** | **`--docs-prose`** | **`34rem`** — the PROSE cap |
| `:716-719` | `.docs-shell:has(.cs-cards)` | `--docs-measure: 1fr; --docs-slack: 0px` |
| **`:729-732`** | **`.docs-shell:has(.tutorial-video-container)`** | **`--docs-measure: 1fr; --docs-slack: 0px`** — tutorial pages already go full width |
| `:739-741` | `.docs-shell-browse` | `--docs-tracks: minmax(0,1fr)` (one track) |
| `:771-774` | `.docs-shell-embed .docs-layout` | `grid-template-columns: minmax(0,1fr); gap: 0` |
| `:976-981` | `.docs-layout` | `display:grid; grid-template-columns: var(--docs-tracks); gap: var(--space-8)` |
| `:990-992` | `.docs-shell-no-toc` | `--docs-tracks: var(--docs-tracks-body)` (drops track 5 AND its gap) |
| `:1000-1010` | placement | sidebar `grid-column:1`, content `3`, toc `5` |
| **`:1051-1056`** | **the PROSE cap application** | see below |
| **`:1059-1063`** | **the player's opt-out** | see below |
| `:1320-1343` | `@media (max-width: 75rem)` | `.docs-layout { grid-template-columns: var(--docs-rail-nav) minmax(0,1fr) }`, all `grid-column: auto` |
| `:1345-1383` | `@media (max-width: 48rem)` | `.docs-layout { grid-template-columns: minmax(0,1fr) }`, rail becomes an off-canvas drawer (`:1427-1433`) |

The two rules that matter for the ask, verbatim:

```css
/* DocsLayout.astro:1051-1056 — the PROSE cap */
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .article-content > :global(*),
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .docs-article > :global(.breadcrumb),
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .docs-article > .fallback-notice,
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .docs-article > .article-header {
  max-inline-size: var(--docs-prose);   /* = 34rem = 544px */
  margin-inline: auto;
}

/* DocsLayout.astro:1059-1063 — the VIDEO PLAYER opt-out */
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .article-content > :global(.tutorial-video-container),
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .article-content > :global(.cs-cards),
.docs-shell:not(.docs-shell-browse):not(.docs-shell-embed) .article-content > :global(.print-page-header) {
  max-inline-size: none;                /* <- the player is UNCAPPED */
}
```

The cap deliberately sits on the article's flow CHILDREN, not on `.article-content` itself
— documented at `:1035-1050`. That is what lets the player opt out while the words stay
capped.

Tokens (`public/styles/main.css`): `--space-4: 1rem` (`:236`), `--space-8: 2rem` (`:241`),
`--docs-chrome-height: 3rem` (`:254`),
`--nav-top-offset: calc(var(--nav-height) + var(--announcement-bar-height,0px))` (`:251`),
`--font-size-base: 1rem` (`:199`). `main.css` is served from `public/styles/`, **not**
`src/styles/` — the site's token layer is not where you would look.

### 4.3 The player component and its CSS

DOM (verified in the live page):

```
div.tutorial-video-container[data-video-src=...]   <- emitted by src/plugins/remark-tutorial-embed.ts:130
  div.tvp-shell                                    <- React root mounts ONTO the container
    div.tvp-toolbar                                   (createRoot(el), src/scripts/tutorial-video-hydrate.ts:49)
    div.tvp-root                                   <- 16/9 box; Plyr lives inside
```

Component: `src/components/TutorialVideoPlayer.tsx` (Plyr-based; `.tvp-shell` at `:540`,
`.tvp-root` at `:581`).

`src/styles/tutorial-video.css`:

```css
.tvp-root {          /* lines 5-14 */
  position: relative;
  max-width: 100%;   /* <- NO px cap anywhere */
  margin: 1.5rem 0;
  aspect-ratio: 16 / 9;
  background: #000;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.tvp-shell { margin: 1.5rem 0; }   /* ~line 207 — no cap either */
.tvp-shell .tvp-root { margin: 0; }
```

So the player's rendered width is whatever `.docs-content` gives it, full stop.

### 4.4 Measured on `/en/docs/tutorial-installation`

| | 1440x900 | 1920x1080 |
|---|---|---|
| scrollbar | 15px | 15px |
| `.docs-shell` | 1425 | — |
| `.docs-layout` | 1393 | — |
| computed `grid-template-columns` | `250px 0px 765px 0px 250px` | `250px 0px 1245px 0px 250px` |
| `.docs-sidebar` | 250 | 250 |
| **`.docs-content` / `.docs-article` / `.article-content`** | **765** | **1245** |
| `.toc-sidebar` | 250 | 250 |
| **paragraph / h2 / `.article-header`** | **544** (34rem) | **544** |
| inline slide SVGs | 544 | 544 |
| **`.tvp-root` player** | **765 x 430** | **1245 x 700** |

Arithmetic that reproduces it: `content = viewport - scrollbar - 2*16 (shell padding)
- 250 - 250 - 4*32 (gaps)`. At 1440: `1440-15-32-500-128 = 765`. At 1920: `1245`.

**The defect in one line: at 1920 the page shows a 1245px video sitting above 544px-wide
text in the same 1245px column.** Prose uses 43.7% of its own column; the player uses 100%.

Note the `:723-728` comment already anticipated half of this — it released
`--docs-measure` for tutorial pages precisely so the recorded 107-column terminal would not
be crushed. What it did not do is give the *prose* any of that width back, or stop the
player from growing without bound.

### 4.5 The requested change, live-tested

Both edits land in **one file, two lines**:

```diff
- /* DocsLayout.astro:704 */   --docs-prose: 34rem;
+ /* DocsLayout.astro:704 */   --docs-prose: 43rem;        /* +26.5%, inside 25-30% */

  /* DocsLayout.astro:1059-1063 */
- max-inline-size: none;
+ max-inline-size: min(960px, 80%);
+ margin-inline: auto;
```

Prefer `DocsLayout.astro:1059-1063` over `tutorial-video.css` for the player cap: that rule
IS the tutorial-specific opt-out, it already carries the
`:not(.docs-shell-browse):not(.docs-shell-embed)` guards, and `tutorial-video.css` is also
loaded by the component in contexts the layout does not own. **Note the `.cs-cards` and
`.print-page-header` selectors share that rule** — split the `.tutorial-video-container`
selector out before changing its value, or cheat sheets and print headers get capped too.

Measured with those two applied in-browser:

| | 1440x900 | 1920x1080 |
|---|---|---|
| `.docs-content` | 765 | 1245 |
| prose / h2 / header / slide SVG | **688** (43rem) | **688** |
| `.tvp-root` | **612 x 344** | **960 x 540** |
| `documentElement.scrollWidth` | 1425 (no overflow) | 1905 (no overflow) |

### 4.6 HAZARD — decide this before implementing

At 1920, `80%` of 1245 = 996, so the 960px ideal wins: player 960, prose 688. Good.

**At 1440, `80%` of 765 = 612, and 612 < 688.** The player ends up *narrower than the
paragraph above it*, and narrower than today's 765px — a visible regression at the most
common desktop width. "80% of the column" only reads well while the column is much wider
than the prose, which is true at 1920 and false at 1440.

Options:
- `max-inline-size: min(960px, max(80%, var(--docs-prose)))` — never narrower than the text
- `max-inline-size: min(960px, calc(var(--docs-prose) * 1.4))` — tie the player to the prose
  rather than to the column, so the two scale together
- keep `80%` and accept 612px at 1440

### 4.7 Local rendering caveat (not a bug anyone introduced)

`packages/www/public/assets/tutorials/` **does not exist** in this checkout — it is
gitignored and R2-hosted (`packages/www/.gitignore`, CLAUDE.md "Media Assets"). With
`PUBLIC_VIDEO_CDN_BASE_URL` unset in dev, `remark-tutorial-embed.ts` emits the relative
`/assets/tutorials/video/en/tutorial-installation.mp4`, which 404s. The player still mounts
and still sizes correctly (`.tvp-root` is `aspect-ratio`-driven), so every measurement above
holds — but the box is black. Restore with `.ci/scripts/deploy/sync-media-from-r2.sh` if a
visual check is wanted.

---

## 5. Per-doc illustrations

Three separate SVG families. Only the first is per-doc.

### 5.1 `public/img/docs-thumbs/<slug>.svg` — the per-doc thumbnails

- **79 files, all git-tracked** (`git ls-files packages/www/public/img/docs-thumbs | wc -l`
  = 79), 320 KB total, ~800 bytes each, `viewBox="0 0 320 120"`.
- **Coverage: 79 / 79 English docs = 100%.** Zero missing, zero orphaned.
- Because the browse page resolves them through `getBaseSlug(doc.slug)`
  (`index.astro:167`, `:201`), **all 13 locales share the same 79 files** — so
  **1,015 / 1,015 rendered docs have one, also 100%.**
- **Referenced by filename convention only.** No frontmatter field, no map file, no
  manifest. The path is built inline: `` src={`/img/docs-thumbs/${slug}.svg`} `` at
  `index.astro:201`.
- **The ONLY consumer in the entire codebase is the browse card.** Full grep for
  `docs-thumbs` returns: `index.astro:192` (comment), `index.astro:201` (the reference),
  `styles/docs-browse.css:301`, `:305` (comments), `utils/docs-categories.ts:176` (comment).
  **They appear nowhere on `/en/docs/<slug>`.** The `docs-categories.ts:176` mention is
  prose inside the `CATEGORY_GLYPHS` doc comment, not a code path.
- Hand-authored, each carrying its category's hue as **literal hex** — an `<img>`-referenced
  SVG is an isolated document and cannot see `--docs-hue`, `currentColor`, or
  `:root[data-theme]`. Documented at `docs-browse.css:301-306`, which also warns that
  changing a category hue means editing the affected files by hand.
- Dark theme is one rule: `:root[data-theme='dark'] .docs-card-thumb { filter: invert(1)
  hue-rotate(180deg) brightness(0.82) saturate(1.15) }` (`docs-browse.css:337-339`).
- They **replaced** a build-time generator that drew abstract geometry from (category,
  tags); that generator is gone (`docs-categories.ts:170-178`, `index.astro:191-198`). There
  is no regenerate script — new docs need a hand-authored file.
- If reused on doc pages: the inversion filter must travel with them, or dark-mode article
  pages get glaring light panels.

### 5.2 `public/img/*.svg` — 23 architecture / flow diagrams

`arch-*` (4), `account-*` (8), `backup-*` (2), plus `blackout-continuity`, `cross-backup`,
`dev-environments`, `hub-architecture`, `hybrid-cloud-scaling`, `legacy-scaling`,
`repo-migrate-flow`, `risk-free-upgrades`, `time-travel-recovery`.

Embedded inline in doc bodies as markdown images. **20 of 23 are referenced by an English
doc; 3 are orphaned:** `arch-operating-modes.svg`, `backup-strategy-flow.svg`,
`hub-architecture.svg`.

### 5.3 `public/img/tutorials/<slug>/slide-N.svg` — 28 tutorial slides

19 directories (18 tutorials + `_template`):

```
_template                   title-card.svg, outro-card.svg
tutorial-forking            slide-1..6      (6)
tutorial-managing-secrets   slide-1..3      (3)
tutorial-installation       slide-1..2      (2)
the other 15 tutorials      slide-1         (1 each)
```

Embedded in the `.mdx` body, e.g. `src/content/docs/en/tutorial-installation.mdx:23`
(`![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)`). Rendered at
the prose width — measured 544px today, 688px under the 4.5 change.

Each tutorial `.mdx` also opens with an asciinema cast reference, e.g.
`![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)` at
`tutorial-installation.mdx:15`, which `remark-tutorial-embed.ts` rewrites into the
`.tutorial-video-container` placeholder.

---

## 6. The "Learn" nav submenu

### 6.1 There is no separate Learn landing page — it is the browse page

`src/components/LearnMenu.tsx:44-55` builds exactly seven entries:

```ts
...CATEGORY_ORDER.map(category => ({
  key: category,
  label: t(CATEGORY_KEYS[category]),
  href: `/${lang}/docs?category=${encodeURIComponent(category)}`,   // :48
})),
{ key: 'all', label: t('navigation.browseAllDocs'), href: `/${lang}/docs` }   // :50-54
```

Mounted from `src/components/Navigation.tsx:264-269`, beside `PersonaMegaMenu` and
`NavCtaMenu`. It is a native `popover="auto"` panel: the UA supplies light-dismiss, Escape,
top-layer stacking and mutual exclusion; the component hand-writes only roving
arrow/Home/End focus (`:94-126`) and the focus return on Escape (`:100-104`). The inline
`left` at `:65-82` is required because a top-layer popover's containing block is the
viewport.

`src/pages/[lang]/resources/` holds 7 unrelated lead-magnet brief pages; they are not in the
Learn menu.

So the contrast the operator is drawing is **`/en/docs?category=X` (browse,
`variant="index"`) versus `/en/docs/<slug>` (article, `variant="article"`) — the SAME
`DocsLayout` taking two very different branches**, switched on
`const isBrowse = variant === 'index'` (`DocsLayout.astro:84`).

### 6.2 What the browse page has that DocsLayout's article path lacks

| | browse (`variant="index"`) | article (`variant="article"`) |
|---|---|---|
| grid | `--docs-tracks: minmax(0,1fr)` — ONE track, measured **1873px** at 1920 (`:739-741`) | 5 tracks; content 1245px, prose capped 544px |
| left sidebar | **omitted** — `:183-199` gated on `!isBrowse` | `DocsSidebar`, scoped to one category |
| TOC rail | **omitted** — `showTOC={false}` (`index.astro:74`), `hasTOC` false (`:79`) | 250px rail (`:264-277`) |
| top tabs | **omitted** — `:112-118` | `DocsTopTabs`, 6 links |
| **faceted filtering** | **category + topic checkboxes, live recomputed counts, URL-linkable** | none |
| **visual index** | **79 thumbnail cards, category-hued glyph chips, hover description overlay, info button** | none |
| hero | glyph + H1 + lede (`index.astro:79-85`) | breadcrumb + H1 + description + "Copy as Markdown" (`:207-256`) |
| result tally | `<output aria-live="polite">` "18 / 79" | n/a |
| in-page search | `?q=` over titles + descriptions + slug, both hyphenated and spaced (`index.astro:173-182`) | n/a |
| structured data | none | `StructuredData type="techarticle"` (`:209-218`) |
| markdown alternate | none | `<link rel=alternate type=text/markdown>` (`:99`) + copy button |
| shared by both | docs search trigger + Light/Dark/Auto theme menu (`DocsLayout.astro:119-171`) | same |

**Concretely, what an article page lacks that the browse page proves is already built and
already fed by existing frontmatter: the per-doc thumbnail, the category-hued glyph chip,
and any surfacing of `tags` whatsoever.**

One blocker for reusing them: `DocsLayout`'s `Props.frontmatter` interface declares only
`{ title, description, category? }` (`DocsLayout.astro:15-19`). `[slug].astro:52` passes
`doc.data` whole, so the values are present at runtime — but `tags` and `subcategory` must
be added to that interface before they can be read type-safely.

### 6.3 Related: `DocsTopTabs.astro` (170 lines)

`variant="article"` -> each tab links to the FIRST doc of that category (`:48-50`).
Measured: Tutorials -> `/en/docs/tutorial-installation`, Guides -> `/en/docs/quick-start`,
Concepts -> `/en/docs/architecture`, Reference -> `/en/docs/cli-application`, Use Cases ->
`/en/docs/dynamic-resource-scaling`, Legal -> `/en/docs/legal-overview`.

`variant="index"` -> `#<categoryAnchor>` fragments, but the browse page does not render this
component at all (`DocsLayout.astro:112`), so that branch is currently dead. The anchors it
would target DO exist (`index.astro:161`).

`categoryLabel` here **throws** on an unknown category (`:34`) rather than falling back —
deliberate, because navigation chrome ships on 1,015 pages.

---

## 7. Assorted findings worth surfacing

1. **The sidebar has no English fallback; the browse page does.** `DocsSidebar.astro:20`
   vs `index.astro:54-60`. In `tr`, `siem-integration` is absent from the sidebar but
   present (in English) on the browse page. Inconsistent, and the browse page's behaviour is
   the better one.
2. **3 orphaned diagram SVGs** (5.2): `arch-operating-modes.svg`,
   `backup-strategy-flow.svg`, `hub-architecture.svg`.
3. **`cli-application` is the only untagged doc**, so it can never be reached through the
   topic filter.
4. **`DocsTopTabs`' `variant="index"` branch is dead code** (6.3).
5. **`docs-browse.css:207-211`'s comment is now stale.** It reasons about a 765px column
   ("its grid reserves a 250px table-of-contents track even on this page"), but
   `.docs-shell-browse` (`DocsLayout.astro:739-741`) since removed that track — the measured
   results column is 1064px at 1920, fitting 4 cards, not the 3 the comment describes.
6. **`subcategory` defaults to `'essentials'` in `groupBySubcategory`**
   (`DocsSidebar.astro:86`). Safe only because of the `=== 'Tutorials'` gate at `:106`;
   removing that gate without also handling the 61 unset docs would file them all under
   "Essentials".

---

## 8. File index (all absolute)

```
/home/muhammed/monorepo/console/packages/www/src/content/config.ts
/home/muhammed/monorepo/console/packages/www/src/content/docs/<lang>/*.{md,mdx}
/home/muhammed/monorepo/console/packages/www/src/utils/docs-categories.ts
/home/muhammed/monorepo/console/packages/www/src/pages/[lang]/docs/index.astro     (browse; card inlined :190-243)
/home/muhammed/monorepo/console/packages/www/src/pages/[lang]/docs/[slug].astro
/home/muhammed/monorepo/console/packages/www/src/layouts/DocsLayout.astro          (1470 lines)
/home/muhammed/monorepo/console/packages/www/src/components/DocsSidebar.astro      (457 lines)
/home/muhammed/monorepo/console/packages/www/src/components/DocsTopTabs.astro      (170 lines)
/home/muhammed/monorepo/console/packages/www/src/components/LearnMenu.tsx
/home/muhammed/monorepo/console/packages/www/src/components/Navigation.tsx
/home/muhammed/monorepo/console/packages/www/src/components/TutorialVideoPlayer.tsx
/home/muhammed/monorepo/console/packages/www/src/plugins/remark-tutorial-embed.ts
/home/muhammed/monorepo/console/packages/www/src/scripts/tutorial-video-hydrate.ts
/home/muhammed/monorepo/console/packages/www/src/styles/docs-browse.css
/home/muhammed/monorepo/console/packages/www/src/styles/tutorial-video.css
/home/muhammed/monorepo/console/packages/www/src/styles/article-content.css        (no width rules)
/home/muhammed/monorepo/console/packages/www/src/styles/sidebar-shared.css
/home/muhammed/monorepo/console/packages/www/public/styles/main.css                (design tokens)
/home/muhammed/monorepo/console/packages/www/public/img/docs-thumbs/               (79 svg)
/home/muhammed/monorepo/console/packages/www/public/img/*.svg                      (23 diagrams)
/home/muhammed/monorepo/console/packages/www/public/img/tutorials/<slug>/slide-N.svg (28)
```
