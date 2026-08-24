# www round-5: comprehension, docs IA, and typographic enforcement

Status: drafting

## Context

`packages/www` has been through four rounds of simplification (last landed commit
`28b152649 feat(www): round-4 docs browse, thumbnails, tutorial player, voice rewrite`).
Round 5 is a comprehension and information-architecture pass, driven by twelve operator
observations made while reading the live site. The through-line is that the site is now
*correct* but still reads as machine-assembled: text-heavy sections with no visual anchor,
a docs taxonomy that exists in the data but is not surfaced, chrome that hides itself, and
line breaks that fall mid-sentence. Round 5 makes the existing structure legible and adds
CI gates so the regressions cannot come back.

Everything below was measured live against `http://localhost:4321` with `agent-browser`
on 2026-08-23, not read off a file.

## Verified findings (live measurements)

### 1. Homepage "The Difference" is a text wall (`.home-difference`)
Two bordered cards side by side, 532px tall, no visual: "Without Rediacc" with 4 sentence
pairs, "With Rediacc" with 4. No image, icon, or diagram. Contrast with the pricing
page's `No Lock-In. Ever.` section, which alternates left-text/right-visual then
right-text/left-visual with inline SVG mock-UI figures.

**Bug found in the model section**: on `/en/pricing`, the first `No Lock-In` row's visual
has a stray dashed rectangle floating outside the card frame to its right (visible at
1440x900). Fix while there.

### 2. FAQ: 12 items on `/en/pricing` (`.faq-section.section-light`)
Verified list: free trial / credit card / upgrade-downgrade / annual billing / payment
methods / how machines are counted / runs on own servers / machines per plan / what
Enterprise includes / education-nonprofit discounts / what happens if I cancel / how
cluster nodes are counted. Several are near-duplicates ("How are machines counted?" vs
"How many machines does each plan cover?" vs "How are cluster nodes counted?").
`/en/disaster-recovery` carries its own `.faq-section` too.

### 3. Header auto-hide wastes the reclaimed space
Nav is `Solutions / Built for you / Pricing / Learn / Blog / globe / Get Started`. It
hides entirely on scroll-down. Docs pages have a *second* bar (`.docs-shell-top`) with
category tabs + `Search docs...` + `Theme`. Opportunity: keep a contextual condensed bar
instead of hiding to nothing.

### 4. Line breaks fall mid-sentence - RULE CORRECTED, MECHANISM MEASURED
`main.css:582-594` already sets `h1..h6 { text-wrap: balance }` and `p { text-wrap: pretty }`.
Neither is enough: `pretty` only prevents a single-word last line, `balance` only equalises
line lengths, and neither knows what a sentence is.

**The operator's literal rule is unsatisfiable and was corrected.** "A line must not both
end one sentence and begin another" turns `.sp-slice-winner-description`, which is five
sentences on two lines, into five lines. The enforceable rule, and the one the mechanism
implements, is: **a sentence that occupies more than one line must not share either of
those lines with a neighbour.** Two whole sentences on one line is fine.

Measured on `/en` at 1440x900 with one detector, four mechanisms:

| mechanism | defects |
|---|---|
| today | 11 |
| `text-wrap: pretty !important` | 11 (moves nothing) |
| `text-wrap: balance !important` | 8 |
| **sentence spans** | **0** |

Rendered proof: "Most tools copy one / piece. We copy all of it." becomes "Most tools copy
one piece. / We copy all of it." Cross-locale: `/ja` 12 to 1, `/ar` 8 to 1, `/zh` 4 to 1,
`/en` at 390x844 18 to 1. No horizontal overflow at any viewport; page height cost at most
+1.2%.

**One of my examples was wrong.** `/en/docs` "Creating Your / First Repository" is NOT a
sentence defect: it is one sentence in a 124px `.docs-card-link` with `text-wrap: balance`
already applied. It needs a width or type fix, and this mechanism does nothing for it.

Design and gate: `agent/PLAN-sentence-aware-wrapping.md`.

### 5. Footer language switcher is white-on-white - CONFIRMED
`footer .language-trigger` computes `background-color: rgb(255,255,255)` with
`color: rgb(228,228,231)`. Contrast ratio ~1.03:1. Visually confirmed at the footer's
bottom-right pill.

### 6. Section surfaces are ad hoc - CONFIRMED with numbers
Six distinct surface colors in use with no ladder:
| color | where |
|---|---|
| `rgb(17,17,19)` | `sp-home-hero`, `sp-bottom-cta` |
| `rgb(26,26,26)` | `section-dark`, `sp-benefits` |
| `rgb(255,255,255)` | `home-difference`, `sp-how-it-works` |
| `rgb(247,247,248)` | `section-light` and most others |
| `rgb(238,243,234)` | `sp-stats` only |
| `rgba(0,0,0,0)` | `closing-cta`, and `pricing-hero.section-dark` |

Concrete defects:
- Two near-identical darks adjacent on `/en/for-devops`: `sp-benefits` #1a1a1a then
  `sp-bottom-cta` #111113 - a visible seam.
- `/en/pricing` runs **six consecutive** `section-light` sections at the same #f7f7f8, so
  nothing reads as a section boundary.
- `/en/disaster-recovery`: `pricing-hero` carries `section-dark` but computes
  **transparent** - the class provides no background there.
- Homepage sections bypass the `section-light`/`section-dark` system entirely with
  bespoke classes and hardcoded backgrounds.

### 7. Docs taxonomy exists in the schema but is only half-surfaced
`packages/www/src/content/config.ts` docs schema:
- `category`: enum of exactly 6 - Tutorials, Guides, Concepts, Reference, Use Cases, Legal.
- `tags`: array from `DOC_TAGS` in `src/utils/docs-categories.ts` (14 values, kebab-case:
  `getting-started`, `cli`, `repositories`, `forking`, `backup`, `storage`, `containers`,
  `networking`, `migration`, `security`, `compliance`, `operations`, `account`, `ai-agents`).
- `subcategory`: enum of **only** `essentials | advanced`.

Consequences measured live:
- Sidebar on a Tutorials doc groups into `ESSENTIALS` / `ADVANCED`. Sidebar on a Guides
  doc is **one flat list of 30 items** under a single `GUIDES` heading. Same for the other
  four categories, because `subcategory` has no vocabulary for them.
- **STRUCK. My first reading of "Filter by topic" was wrong and is recorded here so
  nobody re-fixes a working lookup.** I reported empty labels with a kebab-vs-camelCase
  root cause. Both halves are false. `makeTagLabel`
  (`src/utils/docs-categories.ts:141-152`) maps kebab to
  `{key:'documentation.tags.gettingStarted', en:'Getting Started'}` deliberately, and the
  labels render live with counts: `getting-started:5 cli:4 repositories:5 forking:3
  backup:2 storage:2 containers:6 networking:1 migration:2 security:2 operations:4`. My
  probe read empty text only because the facet is a `<details>` collapsed by default
  (`index.astro:130` has no `open`, unlike the category group at `:107`). The real gap is
  item 7c, one attribute.
- Browse cards show only the category ("Tutorials"), never the topic.
- Category counts on `/en/docs`: Tutorials 18, Guides 30, Concepts 8, Reference 6,
  Use Cases 8, Legal 9 = **79** English docs.

### 8. `/en/docs/tutorial-installation` proportions
Content column runs x=440..1095 (655px) but the prose paragraph wraps at ~955px while the
video player fills the whole 765px column width. Player is column-width; operator wants a
px cap plus <=80% of the column. Prose wants +25-30% measure.

### 9. `/en/docs` (the "nice navigation page") vs `/en/docs/<slug>`
"Learn" in the nav is just six links to `/en/docs?category=<X>` plus "Browse all docs".
The browse page has SVG thumbnails, faceted filters, and counts. The article page has a
plain sidebar. Reference target `/tmp/aim.png` (code.claude.com docs) adds, versus ours:
grouped+labelled sidebar sections, an eyebrow category label above H1, an "Ask Assistant"
entry point, an inline language dropdown in the header, a nested collapsible TOC, a
persistent "Ask a question…" composer, and a "What's next" pair of cards at page end.
We already have: category tabs, `Copy as Markdown`, `Theme` menu, right-hand TOC.

### 10. Per-doc SVGs exist but only on browse cards
The browse grid renders a distinct SVG thumbnail per doc. The article page shows none.

## Operator decisions (2026-08-23)

- **Do not start implementing.** The operator is finishing other work and will hand over a
  clean worktree. Changes stay local and uncommitted; the operator runs `/pr-babysit` at
  the end. This plan is the deliverable for now.
- **Item 3 header**: condense to a persistent slim context bar on scroll-down (logo,
  breadcrumb of where you are, search, primary CTA); full nav returns on scroll-up.
  Nothing is ever blanked.
- **Item 2 FAQ**: score every question on buying-decision value, merge the duplicate
  clusters, cut to about six. Prune the orphaned keys from all 13 locales.
- **Item 9 Ask Assistant**: build it THIS round with **zero API spend**. It must forward
  the question to the *user's own* AI provider account by deep-linking with a prefilled
  prompt. Ship at least Claude and ChatGPT, behind an abstraction that takes more
  providers later.

### Infrastructure that already exists for Ask Assistant
- `packages/www/src/pages/[lang]/docs/[slug].md.ts` already serves per-page **Markdown**,
  and `[slug].txt.ts` serves plain text. The `Copy as Markdown` button on doc pages uses
  this.
- `dist/llms.txt` and `dist/llms-full.txt` are already generated.
So the deep-link prompt can be short and cheap: *"Read <site>/en/docs/<slug>.md and answer:
<question>"* - no page content needs to go in the URL.

## Corrections to my own first reading (from the explore sweep)

Three of my initial premises were wrong. They are corrected here so nothing is built on them.

1. **The nav does not hide.** There is no scroll-direction detection anywhere. `.nav` is
   permanently `position: fixed` (`main.css:900`); `Navigation.tsx:58-112` fades and
   nudges a SUBSET of children linearly over the first 80px of absolute scroll, then sets
   `body[data-nav-collapsed="true"]` which applies `pointer-events: none`
   (`main.css:932-934`). So "auto-hide" is really "fade the links to zero and keep an
   empty fixed bar". The context-bar work replaces the fade-to-nothing with a
   fade-to-condensed, and there is no existing show-on-scroll-up to preserve.
2. **The five-`:root` token split is gone**, fixed 2026-08-18. There is exactly one
   unconditional `:root` (`main.css:79-442`) plus theme/media/RTL overlays. Plan against
   the single-`:root` model, and a token ladder DOES exist.
3. **"Filter by topic" is not broken.** Its labels resolve correctly through
   `makeTagLabel` in `src/utils/docs-categories.ts`; the facet is simply a
   `<details class="docs-rail-group">` that is collapsed by default, which is why
   `innerText` read empty. The real item-7 gap is that topics are a *filter* only and are
   never used as *structure* (sidebar groups, card metadata).

## Root causes now pinned

- **Footer language switcher (item 5).** `main.css:2797-2806` re-points five tokens on
  `.footer` for the dark band but not `--color-bg-alt`, and
  `src/styles/language-switcher.css:15` paints the trigger from exactly that token. Light
  theme therefore renders `#e4e4e7` text on `#ffffff`, ~1.13:1, with a
  `rgb(255 255 255 / 12%)` border that is invisible on white. Dark theme is fine at
  13.7:1, so this is a **light-theme-only** bug. Fix: add `--color-bg-alt` and
  `--color-hover` to the `.footer` token block. Do NOT edit `language-switcher.css` -
  that would break the header mount, which uses the same component with different
  styling.
- **No reusable alternating text/visual component exists.** The pricing
  `No Lock-In. Ever.` pattern is the site's only one
  (`src/styles/pricing-page.css:1252-1258` + `PricingTrustSection.astro:51,119,180`), its
  alternation is hard-coded rather than index-derived, and it uses a `direction: rtl`
  hack that **breaks the alternation on `/ar/`**. Meanwhile
  `main.css:1956-2090` still holds `.difference-row*` / `.difference-zoom*`, the dead
  remains of a previous alternating implementation of the Difference section, with no
  consumer.
- **FAQ**: no FAQ on the homepage. A shared component serves three rendering paths over
  nine data sets, 55 items total; `/en/pricing` carries 12.

## Item 11 - defects found on the way (axe-core 4.12.1 on `/en`, 1440x900)

2 violations, 4 incomplete, 45 passes. All of these are in scope and get fixed:

| Severity | Rule | Nodes |
|---|---|---|
| serious | `color-contrast` | `.form-input`, `.footer-version`, `.language-name` |
| moderate | `heading-order` | `#footer-product-heading` skips a level |
| critical (incomplete) | `aria-valid-attr-value` | `.persona-menu-trigger`, `#learn-menu-trigger`, `#nav-cta-caret` |
| serious (incomplete) | `aria-prohibited-attr` | 15 `.cf-feature-info` divs carrying `aria-label` with no role |
| serious (incomplete) | `color-contrast` | `.cx-centre` and 3 SVG `<text>` nodes |
| minor (incomplete) | `aria-allowed-role` | `#navigation-sidebar` |

`.language-name` is axe independently confirming item 5, which is a useful control: the
same fix must clear that node.

Also found: the first `No Lock-In` row on `/en/pricing` renders a stray dashed rectangle
floating outside its card frame, and the pricing alternation is broken under `/ar/`.

## Execution shape

Four waves. **`public/styles/main.css` is owned by wave A alone** - it is a 3,421-line
shared file and two concurrent writers corrupt it. Every other wave uses component-scoped
styles or its own stylesheet. At most two writer agents run at once (house rule), with the
exact file list stated per agent and everything else forbidden.

Nothing starts until the operator hands over a clean worktree. Work stays uncommitted; the
operator runs `/pr-babysit` at the end.

### Wave A - chrome and surfaces
Owns: `src/components/Navigation.tsx`, `src/components/Footer.astro`,
`public/styles/main.css`, `src/styles/language-switcher.css`,
`src/styles/solution-pages.css`.

- **Item 5, footer language switcher.** Add `--color-bg-alt` and `--color-hover` to the
  `.footer` token block at `main.css:2797-2806`, pointing at the dark values already
  present at `main.css:471,477`. One edit fixes the trigger, the panel and every row.
  Control: re-run `agent-browser a11y` and confirm the `.language-name` node clears.
- **Item 3, condense instead of blank.** Today `Navigation.tsx:58-112` fades
  `.nav-translate` and `.nav-wordmark` to zero over the first 80px and then applies
  `pointer-events: none` (`main.css:932-934`), leaving a fixed empty bar. Replace the
  fade-to-nothing with a **cross-fade to a condensed row**: as the full nav fades out, a
  slim row fades in carrying the mark, a breadcrumb of the current page, the search
  trigger and the primary CTA. Keep the existing single `requestAnimationFrame`-coalesced
  scroll listener and the CSS-custom-property drive - do not add a second listener. Drop
  the `pointer-events: none` rule, since the bar is now interactive at every scroll depth.
  Reuse the docs breadcrumb rather than inventing a second one.
- **Item 6, one surface ladder.** A token ladder already exists; three unreconciled
  mechanisms sit on top of it (see `EXPLORE-chrome.md` 3.3). Reduce to one:
  - collapse the two near-identical darks (`#111113` and `#1a1a1a`) to a single token, so
    the `sp-benefits` to `sp-bottom-cta` seam on `/en/for-devops` disappears;
  - give `/en/pricing` real alternation instead of six consecutive `#f7f7f8` sections;
  - fix `.pricing-hero.section-dark` on `/en/disaster-recovery`, which currently computes
    transparent, so a dark-classed hero renders light;
  - migrate the homepage's bespoke `sp-not-a-slice` / `home-difference` /
    `cf-pricing-section` backgrounds onto the `section-light` / `section-dark` system;
  - fold the one-off `#eef3ea` on `sp-stats` into the ladder or delete it.
- **a11y sweep in owned files**: `heading-order` on `#footer-product-heading`,
  `aria-valid-attr-value` on `.persona-menu-trigger` / `#learn-menu-trigger` /
  `#nav-cta-caret`, `aria-allowed-role` on `#navigation-sidebar`, `.footer-version` and
  `.form-input` contrast.
- Delete the dead `.difference-row*` / `.difference-zoom*` block at `main.css:1956-2090`
  once wave B has landed its replacement, and confirm `check:ci-dead-css` and
  `check:ci-css-dom-refs` stay green.

### Wave B - marketing comprehension
Owns: `src/components/solution-pages/SPHomeNotASlice.astro`, the `HomeDifference`
component, `src/components/**` FAQ component, `PricingTrustSection.astro`,
`src/styles/pricing-page.css`, `src/i18n/translations/*.json`.

- **Item 1, visualise the Difference.** Extract the pricing `No Lock-In. Ever.` pattern
  into a real reusable component (`{title, description, visual}` per row, alternation
  derived from the row index, `order` / `grid-column` instead of the `direction: rtl`
  hack). Point BOTH the pricing section and the Difference section at it. This
  simultaneously fixes the broken `/ar/` alternation and retires the dead CSS in wave A.
  Then cut the Difference section from eight text lines to **four before/after rows**,
  each with a visual: copy-in-60-seconds, hourly backups, tested recovery, per-dev copies.
  Fix the stray dashed rectangle on the first pricing row while in there.
  Source SVGs from `src/assets/images/illustrations/` (22 available) or author new ones in
  the same stroke-only house style; see `EXPLORE-home.md` section D for the inventory and
  the two embedding mechanisms.
- **Item 2, FAQ.** Score all 12 pricing questions on buying-decision value, merge the
  three machine-counting duplicates into one and the two billing ones into one, cut to
  about six. Prune the orphaned keys from all 13 locales - `check-dead-translation-keys.ts`
  will otherwise fail. `EXPLORE-home.md` section C has the full 55-item inventory across
  nine data sets and the exact deletion cost.
- **Item 4 fixes** in these files, once wave D's mechanism exists.

### Wave C - docs surface
Owns: everything under `src/pages/[lang]/docs/`, `src/components/Docs*`,
`src/utils/docs-categories.ts`, `src/content/config.ts`, `src/content/docs/**`,
`src/styles/sidebar-shared.css`, `src/styles/article-content.css`.
Full evidence in `agent/a68f3ab4/EXPLORE-docs.md`.

**Correction that reframes item 7.** There are TWO sub-grouping fields and they are not the
same thing. "Filter by topic" on the browse page is `tags` (14 values, browse rail only,
`index.astro:130-145`). "Essentials"/"Advanced" is `subcategory` (2 values, left sidebar
only, and gated on `category === 'Tutorials'` at `DocsSidebar.astro:106`). The subcategory
matrix is stark:

```
category      essentials   advanced   (unset)   total
Tutorials              7         11         0      18
Guides                 0          0        30      30
Concepts               0          0         8       8
Reference              0          0         6       6
Use Cases              0          0         8       8
Legal                  0          0         9       9
                       7         11        61      79
```

**61 of 79 English docs have no subcategory at all.** That is the actual gap.

- **Item 7a, widen the vocabulary.** Replace the two-value `subcategory` enum in
  `src/content/config.ts` with a per-category vocabulary defined once in
  `src/utils/docs-categories.ts` (alongside `CATEGORY_ORDER` and `DOC_TAGS`, which is
  already the single-source home for exactly this kind of table), with its labels under
  `documentation.subcategories.*` in all 13 catalogs. Assign a subcategory to all 61
  unset docs. Ungate `DocsSidebar.astro:106` so every category groups, and remove the
  `'essentials'` default at `:86` which is only harmless today because of that gate.
- **Item 7b, show the topic on the card.** Browse cards render the category chip only.
  Add the subcategory (and the tags) to the card. Note `EXPLORE-docs.md` 2.3: there is no
  card component, the markup is inline in `index.astro` - extract it while adding the
  field.
- **Item 7c, open the topic facet.** `index.astro:130` has no `open` attribute while the
  category group at `:107` does, so "Filter by topic" is collapsed by default and reads as
  empty. Give it `open`.
- **Item 7d, the gate.** Wave D gate 2: every doc carries a subcategory valid for its
  category, and every browse card renders it. No exception, enforced for future docs.

- **Item 8, proportions.** Live-tested; two lines in `DocsLayout.astro`. Today at 1920 a
  **1245px player sits above 544px-wide text in the same 1245px column** - prose uses 43.7%
  of its column, the player uses 100%.
  - `--docs-prose: 34rem` -> `43rem` at `:704` (+26.5%, inside the requested 25-30%).
  - The player cap at `:1059-1063`: `max-inline-size: none` -> a capped value plus
    `margin-inline: auto`. **Split `.tutorial-video-container` out of that selector first**
    - `.cs-cards` and `.print-page-header` share the rule and must not be capped.
  - **Hazard, decide before implementing.** Plain `min(960px, 80%)` gives 960px at 1920
    (good) but **612px at 1440, which is narrower than the 688px paragraph above it** and
    narrower than today. Take `min(960px, max(80%, var(--docs-prose)))` so the player is
    never narrower than the text it illustrates.
  - Caveat: `public/assets/tutorials/` is gitignored and R2-hosted, so the player box is
    black locally. Sizing still measures correctly; run
    `.ci/scripts/deploy/sync-media-from-r2.sh` for a real visual check.

- **Item 10, the illustrations already exist and are 100% covered.**
  `public/img/docs-thumbs/<slug>.svg`, 79 files, git-tracked, `viewBox="0 0 320 120"`,
  resolved by filename convention through `getBaseSlug`, so all 13 locales and all 1,015
  rendered docs have one. **Their only consumer is the browse card.** Put the thumbnail at
  the head of the article page. Two things travel with it: the dark-theme inversion filter
  (`docs-browse.css:337-339`), or dark articles get glaring light panels; and there is no
  regenerate script, so a new doc needs a hand-authored file - which the wave D gate should
  also enforce.

- **Item 9, close the article/browse gap.** The "nice navigation page" is the browse page;
  "Learn" has no landing page of its own. Concretely, the article page lacks three things
  the browse page proves are already built and already fed by existing frontmatter: the
  per-doc thumbnail, the category-hued glyph chip, and any surfacing of `tags`.
  Toward the `/tmp/aim.png` reference, add: a category eyebrow above the H1, the grouped
  sidebar from item 7a, a nested TOC, prev/next plus a **What's next** pair of cards at the
  foot, `Ctrl/Cmd+K` on the search trigger, and the inline language picker.
  **Blocker to clear first**: `DocsLayout.astro:15-19` declares
  `Props.frontmatter` as only `{ title, description, category? }`. `[slug].astro:52` passes
  `doc.data` whole so the values exist at runtime, but `tags` and `subcategory` must be
  added to that interface before anything can read them type-safely.

### Wave D - gates
Owns: `scripts/check-*.ts`, root `package.json`, `scripts/ci-runner/manifest.ts`,
`.github/workflows/ci.yml`, `scripts/data/*baseline*.json`.

Three-point wiring per `EXPLORE-chrome.md` 4.1-4.3, copying `check:ci-layout-overflow`
verbatim as the template, `check:ci-parity` enforcing all three edits bidirectionally, and
every gate carrying a `--selftest` control that proves it can fail.

Gates to add:
1. **Sentence-aware wrapping** (item 4) - design is `agent/PLAN-sentence-aware-wrapping.md`.
2. **Docs topic coverage** (item 7) - every doc must carry a subcategory valid for its
   category, and every browse card must render it. No exception, enforced for future docs.
3. **Accessibility** - axe-core over a route sample with a shrink-only baseline, seeded at
   today's count so it can only improve.
4. **Section surface** - assert every `<section>` resolves to a token in the ladder and
   that no two adjacent sections resolve to the same surface.

### Ask Assistant, at zero API spend

The operator's constraint: no budget for an LLM backend, so the button must **forward the
question to the user's own AI provider account**, and the provider set must be abstract so
more can be added.

The plumbing already exists and is currently invisible: `[slug].md.ts` serves per-page
Markdown, `[slug].txt.ts` serves plain text, and `llms.txt` / `llms-full.txt` are already
generated. So the prompt can stay short - a question plus the absolute URL of the page's
`.md` - and no page content has to travel in the URL, which is what keeps this inside every
browser and host URL-length limit.

Shape:
**Verified provider templates** (full sources and per-claim confidence in
`agent/a68f3ab4/RESEARCH-ai-deeplinks.md`):

| Provider | Template | Auto-submits | Confidence |
|---|---|---|---|
| ChatGPT | `https://chatgpt.com/?q={enc}` (`&hints=search` optional) | likely with `hints=search` | HIGH param, MED submit |
| Claude web | `https://claude.ai/new?q={enc}` | reported | MED, undocumented |
| Claude desktop | `claude://claude.ai/new?q={enc}` | no, prefill only | HIGH, vendor documented |
| Perplexity | `https://www.perplexity.ai/search?q={enc}` | yes | HIGH |
| Grok | `https://grok.com/?q={enc}` | yes on load | MED |
| Copilot | `https://copilot.microsoft.com/?q={enc}` | yes, no interaction | **do not ship, this is CVE-2026-24307** |
| Gemini, AI Studio, Mistral | no native prefill | n/a | do not ship |

`chat.openai.com` redirects to `chatgpt.com`. ChatGPT ignores `model=` when `q` is present.

**Safe URL length is 2,000 characters for the whole URL.** Browsers are not the limit
(Chrome handles ~2MB); origin servers are, at ~4,096 for nginx and IIS. Encoding costs
roughly 3x on newlines and non-ASCII, so 2,000 characters carries only ~1,200-1,500
readable prompt characters, and fewer in a non-English locale. **Send a pointer, never the
page body**: a doc page is 5-50KB and truncating it is worse than not sending it.

Prompt shape, under 500 characters: *"Read https://rediacc.com/docs/<page>.md and answer
using it. Full index: https://rediacc.com/llms.txt. My question: <text>"*

**Two gaps to close with ten minutes of `agent-browser` before shipping**: `claude.ai/new?q=`
is undocumented for web and one source claims it was removed in October 2025 while
2026 writeups say it works (claude.ai returns 403 to non-browser fetches, so it could not
be verified headlessly); and the exact URLs Vercel and Mintlify build are client-side and
unpublished, so read them off a live docs page with devtools.

- A `src/utils/ai-providers.ts` table of `{ id, label, icon, buildUrl(prompt) }`, so adding
  a provider is one entry. Ship Claude and ChatGPT first; the research file
  `agent/a68f3ab4/RESEARCH-ai-deeplinks.md` carries the verified URL templates, which
  parameter each host takes, whether it auto-submits, and the real-world safe URL length.
- The button opens a small menu (provider list plus "Copy prompt"), so a user with no
  account still gets something useful, and the existing `Copy as Markdown` button becomes
  the third member of that menu rather than a separate control.
- Remember the last provider in `localStorage`; never send anything to our own servers.
- Advertise the machine-readable surface while there: `llms.txt` in `robots.txt`, and the
  `<link rel="alternate" type="text/markdown">` that doc pages already emit at
  `DocsLayout.astro:99` should be surfaced as a visible "View as Markdown" link.

## Incidental findings picked up by the agents

- `/zh` renders the untranslated English string "Product news and self-hosting tips." at
  `p.newsletter-footer-desc`. A missing locale value, not a wrapping defect.
- 78 of 79 English docs carry at least one tag; `cli-application` (Reference) carries none.
  **66 docs carry TWO tags and 12 carry one**, which matters if the sidebar is ever grouped
  by tag rather than by subcategory: a two-tag doc would appear under two headings. This is
  the argument for grouping the sidebar on `subcategory` (single-valued) and leaving `tags`
  as the browse facet.
- `-webkit-line-clamp` at `src/styles/docs-browse.css:289-290` is the site's only
  `display: -webkit-box` and is fragile with `inline-block` children, so it interacts with
  the item-4 mechanism. Check it explicitly.

## Item 12 - what else is worth doing

- Surface the existing per-page markdown route (`[slug].md.ts`) as a visible link beside
  `Copy as Markdown`, and advertise `llms.txt` from `robots.txt` plus a
  `<link rel="alternate" type="text/markdown">` on doc pages. The plumbing exists and is
  currently invisible.
- Docs prev/next pager at the article foot, which is also what the reference page's
  `What's next` cards are.
- `Ctrl/Cmd+K` on the docs search trigger, matching the reference, and a visible hint chip.
- Retire the second docs bar by folding its tabs into the condensed context bar from
  item 3, so docs pages stop paying for two stacked chromes.

## Verification

Every claim below gets driven, not read. Run each with the dev server up
(`cd packages/www && npm run dev`, `http://localhost:4321`, note `/en/` with a trailing
slash 404s) and a distinct `AGENT_BROWSER_SESSION` per agent so concurrent browsers do not
collide.

**Before/after measurement, per item**
- Item 1: screenshot `.home-difference` at 1440x900 and 390x844 before and after; the
  section must show four visual rows, and `/ar/` must alternate in the mirror direction.
- Item 2: assert the pricing FAQ item count drops to about six and that
  `npm run check:i18n` plus `check-dead-translation-keys` stay green after the locale prune.
- Item 3: at `scrollY` 0, 40, 200 and 800, assert the condensed bar is present and
  `pointer-events` is not `none`; assert the primary CTA is clickable at depth 800.
- Item 4: the gate from `agent/PLAN-sentence-aware-wrapping.md`, plus a manual re-read of
  the four known strings at 1440 and 390.
- Item 5: re-run `agent-browser a11y http://localhost:4321/en` and confirm the
  `.language-name`, `.footer-version` and `.form-input` contrast nodes clear, in BOTH
  themes (`agent-browser set media light|dark`).
- Item 6: re-run the section survey that produced the six-colour table and assert no two
  adjacent sections resolve to the same surface on `/en`, `/en/pricing`, `/en/for-devops`,
  `/en/disaster-recovery`.
- Items 7 and 10: assert 79/79 English docs have a subcategory and a thumbnail, that the
  sidebar groups on a Guides doc as well as a Tutorials one, and that the topic facet is
  expanded on first paint.
- Item 8: re-measure `.docs-content`, prose and `.tvp-root` at 1440 and 1920 and match the
  target table; assert `documentElement.scrollWidth` shows no horizontal overflow at either.
- Item 9: `Ctrl+K` opens search; the What's next cards resolve to real routes in every
  locale; the Ask Assistant deep link opens with the prompt prefilled.

**Gates**
`npm run ci` for the full set. At minimum, name the result of `check:lint`, `check:i18n`,
`check:ci-parity`, `check:ci-dead-css`, `check:ci-css-dom-refs`,
`check:ci-anchor-integrity`, `check:ci-layout-overflow`, `check:test-www` and `build:www`,
and run each NEW gate's `--selftest` control to prove it can fail.

**Build hazard**: `npm run build:www` deletes 14 tracked `search-index*.json` from the
shared tree while it runs and a concurrent build corrupts `dist/`. Only one build at a time,
and never while another session is building.

## Where this stands

- Planning is complete. **No implementation has started**, at the operator's instruction.
- The repository moved from `~/monorepo/console` to `~/console` on 2026-08-23. Every path
  in this document is relative to the repo root unless it starts with `~`.
- Nothing in `packages/www` has been modified. The working tree changes that exist belong
  to other sessions (CI scripts, hooks, the git-history media rewrite).
- The operator will run `/pr-babysit` once the work is done. Until then everything stays
  uncommitted.

## Companion documents

- `agent/a68f3ab4/EXPLORE-home.md` (612 lines) - Difference and No-Lock-In components, the
  full 55-item FAQ inventory with key paths, the illustration inventory, and the proof that
  no reusable alternating component exists.
- `agent/a68f3ab4/EXPLORE-chrome.md` (946 lines) - nav scroll mechanics, the footer token
  gap, the surface-colour survey, and the three-point gate wiring with a worked example.
- `agent/a68f3ab4/EXPLORE-docs.md` (713 lines) - taxonomy matrices, browse and sidebar
  internals, the live-tested item-8 measurements and their hazard, thumbnail coverage.
- `agent/a68f3ab4/RESEARCH-ai-deeplinks.md` (347 lines) - verified provider URL templates
  for Ask Assistant, the safe URL length with its real limiting factor, and how Vercel,
  PostHog, Cloudflare and Mintlify sites do it.
- `agent/PLAN-sentence-aware-wrapping.md` (439 lines, Status: draft) - the item-4 mechanism
  decision with its browser evidence, the sweep, and both gates with their controls.

All five are in the repo and survive a lost session.
