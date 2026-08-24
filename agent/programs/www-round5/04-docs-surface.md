# 04. Docs surface (Wave C)

Status: planned, not started. Covers operator items 7, 8, 9, 10.

**File ownership for this wave.** Everything under `src/pages/[lang]/docs/`,
`src/components/Docs*`, `src/utils/docs-categories.ts`, `src/content/config.ts`,
`src/content/docs/**`, `src/styles/sidebar-shared.css`, `src/styles/article-content.css`,
`src/styles/docs-browse.css`, `src/layouts/DocsLayout.astro`.
**`public/styles/main.css` belongs to wave A** and must not be touched here.

## Item 7: surface the taxonomy that already exists

Read `01-verified-context.md` first for the two-field correction and the matrix. The short
version: `tags` is the topic axis and lives only in the browse rail; `subcategory` is
`essentials | advanced` and lives only in the Tutorials sidebar; **61 of 79 English docs
have no subcategory at all**, which is why Guides renders as one flat list of 30.

**7a. Widen the vocabulary.** Replace the two-value `subcategory` enum in
`src/content/config.ts` with a per-category vocabulary defined once in
`src/utils/docs-categories.ts`, alongside `CATEGORY_ORDER` and `DOC_TAGS`. That module is
already the single-source home for exactly this kind of table and says so in its own header
comment: it exists because the same lookup was about to be written twice. Put the labels
under `documentation.subcategories.*` in all 13 catalogs. Then assign a subcategory to all
61 unset docs.

Ungate `DocsSidebar.astro:106`, which currently reads
`category === 'Tutorials' ? ... : null`, so every category groups. Remove the `'essentials'`
default at `:86` while you are there: it is harmless today only because of that gate, and
becomes a silent mis-grouping the moment the gate goes.

Grouping code is entirely in `DocsSidebar.astro`: `:69-92` keys, order, label and
`groupBySubcategory`; the gate at `:106`; render at `:163-200`; CSS at `:241-288`; JS at
`:379-413`.

**Group on `subcategory`, not on `tags`.** 66 docs carry two tags, so tag-grouping would
put a doc under two headings.

**7b. Show the topic on the card.** Cards render the category chip only. Add the
subcategory, and the tags. Note there is no card component: the markup is inlined at
`index.astro:190-243` and styled from `docs-browse.css:233`. Extract it into a component
while adding the field, rather than editing inline markup a gate then has to parse.

**7c. Open the topic facet.** `index.astro:130` has no `open` attribute while the category
group at `:107` does. That single omission is why "Filter by topic" reads as an empty
heading. One attribute.

**7d.** Wave D gate 2 enforces this for every future doc. See `05-gates.md`.

## Item 8: proportions

At 1920 a **1245px player sits above 544px-wide text in the same 1245px column**. Prose uses
43.7% of its own column; the player uses 100%.

Both edits land in `src/layouts/DocsLayout.astro`; `src/styles/article-content.css` has zero
width rules.

- **Prose measure:** `:704` `--docs-prose: 34rem` becomes `43rem` (+26.5%, inside the
  requested 25-30%). It is applied at `:1051-1056` as
  `max-inline-size: var(--docs-prose); margin-inline: auto` on `.article-content > *` plus
  `.breadcrumb`, `.fallback-notice` and `.article-header`.
- **Player cap:** `:1059-1063` currently sets `max-inline-size: none` on
  `.article-content > .tutorial-video-container`. **Split `.tutorial-video-container` out of
  that selector before changing the value**: `.cs-cards` and `.print-page-header` share the
  rule and must not be capped. Add `margin-inline: auto`.
  Prefer this rule over `src/styles/tutorial-video.css`: it IS the tutorial-specific opt-out,
  it already carries the `:not(.docs-shell-browse):not(.docs-shell-embed)` guards, and
  `tutorial-video.css` is also loaded in contexts the layout does not own.
  `tutorial-video.css:5-14` gives `.tvp-root` only `max-width:100%` and `aspect-ratio:16/9`,
  no px cap. Also note `DocsLayout.astro:729-732`
  `:has(.tutorial-video-container){--docs-measure:1fr;--docs-slack:0px}`: tutorial pages
  already run full width, which is half of why this looks wrong.

**HAZARD, and it is open decision point 5.** Plain `min(960px, 80%)` gives 960px at 1920
(good) but **612px at 1440, narrower than the 688px paragraph above it and narrower than
today**. "80% of the column" only reads well while the column is much wider than the prose,
which is true at 1920 and false at 1440. RECOMMENDED: `min(960px, max(80%, var(--docs-prose)))`.

Target after both edits, live-measured: prose 688 at both widths; player 612x344 at 1440 and
960x540 at 1920 under plain 80%, and never below 688 wide under the recommendation. No
horizontal overflow at either width.

## Item 10: put the illustrations on the page

`public/img/docs-thumbs/<slug>.svg` already exists at **100% coverage**: 79 git-tracked
files resolved by filename convention through `getBaseSlug`, so all 1,015 rendered docs
across 13 locales have one. **The browse card is their only consumer in the entire
codebase.** They never appear on `/en/docs/<slug>`.

Put the thumbnail at the head of the article. Two things travel with it:

1. **The dark-theme inversion.** These are `<img>`-referenced SVGs, so they are isolated
   documents that cannot see `--docs-hue`, `currentColor` or `:root[data-theme]`. Dark mode
   is handled by one rule at `docs-browse.css:337-339`
   (`filter: invert(1) hue-rotate(180deg) brightness(0.82) saturate(1.15)`). Without it,
   dark articles get glaring light panels.
2. **There is no regenerate script.** The generator that drew them from (category, tags) is
   gone; they are hand-authored. A new doc needs a hand-authored file, which is why wave D
   gates coverage.

## Item 9: close the article/browse gap

There is no separate Learn landing page. "Learn" is six links to `/en/docs?category=<X>`
plus "Browse all docs", so the page the operator admires is the browse page.

What the article page lacks that the browse page proves is **already built and already fed
by existing frontmatter**: the per-doc thumbnail, the category-hued glyph chip, and any
surfacing of `tags` whatsoever.

**Blocker to clear first.** `DocsLayout.astro:15-19` declares `Props.frontmatter` as only
`{ title, description, category? }`. `[slug].astro:52` passes `doc.data` whole, so the
values are present at runtime, but `tags` and `subcategory` must be added to that interface
before anything can read them type-safely.

Toward the `/tmp/aim.png` reference, add: a category eyebrow above the H1, the grouped
sidebar from 7a, a nested TOC, prev/next plus a **What's next** pair of cards at the foot,
`Ctrl/Cmd+K` on the search trigger, and the inline language picker. Open decision point 6
covers how far to take it; the recommendation leaves the persistent floating composer out.

### Ask Assistant, at zero API spend

**Locked by the operator:** no LLM API spend. The button forwards the question to the
**user's own** AI provider account, and the provider set is abstract so more can be added.

The plumbing already exists and is currently invisible: `[slug].md.ts` serves per-page
Markdown, `[slug].txt.ts` serves plain text, `llms.txt` and `llms-full.txt` are already
generated, and `DocsLayout.astro:99` already emits
`<link rel="alternate" type="text/markdown">`.

Verified provider templates. Full sources and per-claim confidence in
`evidence/RESEARCH-ai-deeplinks.md`.

| Provider | Template | Auto-submits | Confidence |
|---|---|---|---|
| ChatGPT | `https://chatgpt.com/?q={enc}` (`&hints=search` optional) | likely with `hints=search` | HIGH param, MED submit |
| Claude web | `https://claude.ai/new?q={enc}` | reported | MED, undocumented |
| Claude desktop | `claude://claude.ai/new?q={enc}` | no, prefill only | HIGH, vendor documented |
| Perplexity | `https://www.perplexity.ai/search?q={enc}` | yes | HIGH |
| Grok | `https://grok.com/?q={enc}` | yes on load | MED |
| Copilot | `https://copilot.microsoft.com/?q={enc}` | yes, no interaction | **OUT: this is CVE-2026-24307** |
| Gemini, AI Studio, Mistral | no native prefill | n/a | OUT |

`chat.openai.com` redirects to `chatgpt.com`. ChatGPT ignores `model=` when `q` is present.
Claude desktop truncates `q` at about 14,000 characters.

**Safe URL length is 2,000 characters for the whole URL.** Browsers are not the limit
(Chrome handles about 2MB); origin servers are, at roughly 4,096 for nginx and IIS and 8,192
for Apache. Encoding costs about 3x on newlines and non-ASCII, so 2,000 characters carries
only 1,200 to 1,500 readable prompt characters, fewer in a non-English locale.

**Send a pointer, never the page body.** A doc page is 5-50KB and will not fit, and
truncating it is worse than not sending it. Prompt shape, under 500 characters:

> Read https://rediacc.com/docs/<page>.md and answer using it. Full index:
> https://rediacc.com/llms.txt. My question: <text>

Shape of the implementation:

- `src/utils/ai-providers.ts`: a table of `{ id, label, icon, buildUrl(prompt) }` so adding
  a provider is one entry.
- The button opens a small menu. Fold the existing `Copy as Markdown` control into it, add
  `View as Markdown` pointing at the `.md` route, then the providers. A user with no
  provider account still gets something useful.
- Remember the last provider in `localStorage`. Never send anything to our own servers.
- Advertise the machine-readable surface: `llms.txt` in `robots.txt`, and a mirror at
  `/.well-known/llms.txt` per the convention.

**Two gaps to close with ten minutes of `agent-browser` before shipping.** `claude.ai/new?q=`
is undocumented for web and one source claims it was removed in October 2025 while 2026
writeups say it works; it could not be verified headlessly because claude.ai returns 403 to
non-browser fetches. And the exact URLs Vercel and Mintlify build are client-side and
unpublished, so read them off a live docs page with devtools.

## Also in this wave

`/en/docs` renders "Creating Your / First Repository" badly, but that is **not** a sentence
defect: it is one sentence in a 124px `.docs-card-link` that already has
`text-wrap: balance`. It is a card width or type-scale fix, and it belongs here.
