# 01. Verified context

Status: AS-BUILT as of 2026-08-23, branch `0823-1`, measured live with `agent-browser`
against `http://localhost:4321` in the pre-move checkout.

**Re-verify banner.** The repository moved from `~/monorepo/console` to `~/console` after
these measurements were taken, and nothing was re-run afterwards. Line numbers move. Treat
every `file:line` below as a hypothesis, confirm it, and correct this document in the same
turn when it drifts.

## Three premises the planning session got wrong

Recorded because each one would send an implementer to fix something that is not broken.

1. **The nav does not hide on scroll.** There is no direction detection anywhere in the
   codebase. `.nav` is permanently `position: fixed` (`public/styles/main.css:900`) and
   never translates as a whole. `src/components/Navigation.tsx:58-112` is one `useEffect`
   with one `requestAnimationFrame`-coalesced scroll listener that clamps
   `y = min(max(scrollY,0), 80)` and writes four CSS custom properties, then sets the body
   attribute `data-nav-collapsed` at `y >= 80`, which applies `pointer-events: none` via
   `main.css:932-934`. **The toggled thing is a body attribute, not a class**, and nothing
   is added to or removed from a `classList`. `public/scripts/main.js` is not involved.
   So "auto-hide" is really "fade the links to zero and keep an empty fixed bar", and there
   is no show-on-scroll-up behaviour to preserve.

2. **"Filter by topic" is not broken.** The planning session reported 14 checkboxes with
   empty labels and blamed a kebab-versus-camelCase key mismatch. Both halves are false.
   `makeTagLabel` (`src/utils/docs-categories.ts:141-152`) maps the kebab identifier to
   `{key:'documentation.tags.gettingStarted', en:'Getting Started'}` by design, and the
   labels render live with counts: `getting-started:5 cli:4 repositories:5 forking:3
   backup:2 storage:2 containers:6 networking:1 migration:2 security:2 operations:4`. The
   probe read empty text only because the facet is a `<details>` that is collapsed by
   default: `index.astro:130` has no `open` attribute, unlike the category group at `:107`.
   The real defect is one attribute.

3. **The five-`:root` token split is gone.** Fixed 2026-08-18. `main.css:64-67` states it
   in the source: there was a time when five `:root` blocks existed, the last in document
   order silently won, and two rules were provably dead because of it. Today there is
   exactly one unconditional `:root` (`main.css:79-442`, about 200 tokens) plus a dark
   overlay (`:466-538`), reduced-motion (`:555-562`), increased-contrast (`:652-656`), an
   RTL single token (`:446-448`), the announcement bar height
   (`AnnouncementBar.astro:32`) and one a11y string (`BaseLayout.astro:303`).
   **Plan against the single-`:root` model, and note that a token ladder already exists.**

A fourth correction, from the typography planning agent: the operator's literal wrapping
rule is unsatisfiable. See `02-marketing-comprehension.md` and
`agent/PLAN-sentence-aware-wrapping.md`.

## Measured facts by area

### Marketing surfaces

- The homepage renders these sections in order, with these computed backgrounds:
  `sp-home-hero` `rgb(17,17,19)`, `sp-not-a-slice` `rgb(247,247,248)`, `home-difference`
  `rgb(255,255,255)`, `cf-pricing-section` `rgb(247,247,248)`, `closing-cta`
  `rgba(0,0,0,0)`.
- `.home-difference` is 532px tall at 1440x900: an H2 and two bordered cards, "Without
  Rediacc" with four sentence pairs and "With Rediacc" with four. No image, icon or diagram.
- **There is no FAQ on the homepage.** `/en/pricing` carries 12 items in
  `.faq-section.section-light`. A shared component serves three rendering paths over nine
  data sets, 55 items in total. `/en/disaster-recovery` carries its own.
- **No reusable alternating text/visual component exists.** The pricing
  `No Lock-In. Ever.` section is the site's only one
  (`src/styles/pricing-page.css:1252-1258` plus `PricingTrustSection.astro:51,119,180`),
  its alternation is hard-coded rather than index-derived, and it uses a `direction: rtl`
  hack that **breaks the alternation under `/ar/`**. Meanwhile `main.css:1956-2090` still
  holds `.difference-row*` and `.difference-zoom*`, the dead remains of a previous
  alternating implementation of the Difference section, with no consumer.
- `src/assets/images/illustrations/` holds 22 SVGs, embedded by two mechanisms that both
  inline the source. `public/img/` holds 23 more, referenced by URL.

### Chrome and surfaces

- **Footer language switcher, light theme only.** `main.css:2797-2806` re-points five
  tokens on `.footer` for the dark band but not `--color-bg-alt`, and
  `src/styles/language-switcher.css:15` paints the trigger from exactly that token. Light
  theme renders `#e4e4e7` on `#ffffff`, about **1.13:1**, with a
  `rgb(255 255 255 / 12%)` border that is invisible on white, so the control reads as a
  blank white pill. Dark theme is 13.7:1 and correct. Two corroborating tells:
  `.language-option.active` uses the brand green, so the selected row is the only readable
  one; and `:hover` uses `--color-hover`, which `.footer` also does not re-point.
  **Do not edit `language-switcher.css`**: the same component mounts in the header with
  different styling.
- **Six surface colours are in use with three unreconciled mechanisms on top of one token
  ladder**: `#111113` (hero and bottom CTA), `#1a1a1a` (`section-dark`, `sp-benefits`),
  `#ffffff`, `#f7f7f8` (`section-light` and most others), `#eef3ea` (`sp-stats` only), and
  transparent (`closing-cta`, and `pricing-hero` on `/en/disaster-recovery`).
  Concrete defects: two near-identical darks sit adjacent on `/en/for-devops`
  (`sp-benefits` then `sp-bottom-cta`), `/en/pricing` runs **six consecutive**
  `section-light` sections at the same `#f7f7f8` so nothing reads as a boundary,
  `.pricing-hero.section-dark` on `/en/disaster-recovery` computes **transparent** so a
  dark-classed hero renders light, and the homepage bypasses the system entirely.

### Docs

- English browse counts: Tutorials 18, Guides 30, Concepts 8, Reference 6, Use Cases 8,
  Legal 9 = **79**. Across 13 locales that is 1,015 rendered docs.
- **Two different sub-grouping fields, and they are not the same thing.** `tags` (14
  values, `DOC_TAGS` in `src/utils/docs-categories.ts`) is the topic axis and renders only
  in the browse rail (`index.astro:130-145`). `subcategory` (`essentials | advanced`, two
  values) renders only in the left sidebar and only for Tutorials, gated at
  `DocsSidebar.astro:106`.

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

  **61 of 79 English docs have no subcategory at all.** That is the actual item-7 gap.
  78 of 79 carry at least one tag (`cli-application` in Reference carries none); **66 carry
  two tags and 12 carry one**, which is the argument for grouping the sidebar on the
  single-valued `subcategory` and leaving `tags` as the browse facet.
- **Proportions.** At 1920 a **1245px player sits above 544px-wide text in the same 1245px
  column**: prose uses 43.7% of its own column, the player uses 100%.

| | 1440x900 | 1920x1080 |
|---|---|---|
| `.docs-content` | 765 | 1245 |
| prose, h2, article header, slide SVG | 544 (34rem) | 544 |
| `.tvp-root` player | 765 x 430 | 1245 x 700 |

- **Thumbnails already exist at 100% coverage.** `public/img/docs-thumbs/<slug>.svg`, 79
  git-tracked files, `viewBox="0 0 320 120"`, about 800 bytes each, resolved by filename
  convention through `getBaseSlug` so all 13 locales share them. **The browse card is their
  only consumer anywhere in the codebase.** They carry their category hue as literal hex
  because an `<img>`-referenced SVG cannot see CSS variables, and dark theme is handled by
  one `filter: invert(1) hue-rotate(180deg)` rule at `docs-browse.css:337-339`.
- **There is no separate Learn landing page.** The "Learn" menu is six links to
  `/en/docs?category=<X>` plus "Browse all docs". The "nice navigation page" the operator
  admires is the browse page itself.
- **There is no card component.** The browse card markup is inlined at
  `index.astro:190-243` and styled from `src/styles/docs-browse.css:233`.

## Accessibility baseline

axe-core 4.12.1 on `/en` at 1440x900: **2 violations, 4 incomplete, 45 passes.**

| Severity | Rule | Nodes |
|---|---|---|
| serious | `color-contrast` | `.form-input`, `.footer-version`, `.language-name` |
| moderate | `heading-order` | `#footer-product-heading` skips a level |
| critical (incomplete) | `aria-valid-attr-value` | `.persona-menu-trigger`, `#learn-menu-trigger`, `#nav-cta-caret` |
| serious (incomplete) | `aria-prohibited-attr` | 15 `.cf-feature-info` divs with `aria-label` and no role |
| serious (incomplete) | `color-contrast` | `.cx-centre` and 3 SVG `<text>` nodes |
| minor (incomplete) | `aria-allowed-role` | `#navigation-sidebar` |

`.language-name` is axe independently confirming the item-5 bug, which makes it a free
control: the wave A fix must clear that node.

## Incidental findings

- The first `No Lock-In` row on `/en/pricing` renders a stray dashed rectangle floating
  outside its card frame at 1440x900.
- `/zh` renders the untranslated English string "Product news and self-hosting tips." at
  `p.newsletter-footer-desc`.
- `-webkit-line-clamp` at `src/styles/docs-browse.css:289-290` is the site's only
  `display: -webkit-box` and is fragile with `inline-block` children, so it interacts with
  the item-4 mechanism directly.

## Environment notes that cost time to learn

- `/en` works; **`/en/` with a trailing slash returns 404.**
- Element-scoped `agent-browser screenshot <selector>` came back blank on tall sections.
  Scroll the element to centre, settle, then take a viewport screenshot.
- The page grows as you scroll: `loading="lazy"` images resolve late, so a `scrollIntoView`
  computed before a full-page scroll lands in the wrong place. Scroll, settle, recompute.
- `packages/www/public/assets/tutorials/` is gitignored and R2-hosted, so the video box is
  black in dev. Sizing still measures correctly because `.tvp-root` is `aspect-ratio`-driven.
  Run `.ci/scripts/deploy/sync-media-from-r2.sh` for a real visual check.
- `npm run build:www` deletes 14 tracked `search-index*.json` from the shared tree while it
  runs, and a concurrent build corrupts `dist/`. One build at a time, and never while
  another session is building.

---

## Corrections applied 2026-08-23 by the executing session (b7baf3ee)

The re-verify banner above says to correct this document in the same turn when it
drifts. These are the drifts found while executing, each measured rather than
argued. Recorded by the lead because the wave A writer's file ownership did not
include this document.

1. **Item-6 defect 3 in `03-chrome-and-surfaces.md` is DISPROVEN.**
   `.pricing-hero.section-dark` on `/en/disaster-recovery` does NOT render light.
   It is painted by `background: var(--gradient-dark)`, a background-IMAGE, and
   the planning probe read `backgroundColor` only. Measured live:

       backgroundColor  rgba(0, 0, 0, 0)
       backgroundImage  linear-gradient(135deg, rgb(17,17,19), rgb(17,17,19))

   The same artifact affects `ps-hero` and `downloads-hero`. The homepage
   `closing-cta` was the one genuinely unpainted section. **A probe that reads
   only `backgroundColor` cannot see a gradient**, so it reports every
   gradient-painted section as transparent.

2. **The accessibility baseline in this file is STALE.** `.form-input` and
   `.language-name` `color-contrast`, and all three `aria-valid-attr-value`
   incompletes (`.persona-menu-trigger`, `#learn-menu-trigger`, `#nav-cta-caret`),
   were ALREADY clear on `/en` before wave A did any work. Seeding wave D's
   shrink-only accessibility baseline from the table above would have enshrined
   defects that no longer exist.

3. **`main.css` was 3,135 lines pre-edit, not 3,421.** Every planning line number
   in this suite drifted with it.

4. **`/[lang]/docs` is a 200 browse page, not a 301.**

5. **`Navigation.tsx` already had the SSR `lang` prop and the wordmark collapse**
   at handoff, so premise 1's "empty fixed bar" was already half-fixed: the icon
   and CTA persisted, and only the breadcrumb and the scroll-up return were
   missing.

### One deviation from `03`, kept deliberately

`03` said to drop `pointer-events: none` from the faded links. Wave A KEPT it,
and added `visibility: hidden`. The condensed elements were never inside
`.nav-translate`, so the rule is what stops invisible links swallowing clicks;
without `visibility: hidden` those invisible links were also still in the TAB
ORDER. Removing the rule as written would have introduced two accessibility
defects while fixing none, and it also fixed a live reduced-motion bug where
visible links were unclickable at depth.

### For wave D's section-surface gate

After wave A, the only adjacent-same surface pairs remaining are DELIBERATE dark
band merges (`/en` closing band into the footer, `/en/for-devops` benefits + cta
+ footer as one band). The gate needs an exemption for a deliberate merge, or it
will report the fixed state as broken.

### Four more environment facts, measured during execution (wave B and the lead)

These cost real time and are not obvious from any file.

6. **`agent-browser screenshot` with a RELATIVE path reports success and writes
   the file somewhere else.** `agent-browser screenshot test1.png` prints
   `✓ Screenshot saved to test1.png` and the file is not in the cwd; five
   baseline screenshots landed in the repo ROOT. Always pass an absolute path.

7. **The dev server can serve fresh SSR HTML and STALE scoped CSS at the same
   time.** For several minutes `curl /en` returned a new
   `.home-difference[data-astro-cid-...]` rule while the browser, on the same URL
   with a unique cache-busting query, still had the previous rule AND the
   previous computed values. No service worker, no HTTP cache. `touch`ing the
   `.astro` file and waiting ~3s cleared it every time. Without knowing this, a
   measurement looks exactly like a code defect.

8. **The browser is genuinely shared and other waves navigate it mid-probe.**
   Two probes returned data from a different wave's page. Any measurement here
   should assert `location.href` before AND after settling and retry on
   mismatch, or it will publish another wave's page as its own.

9. **A content-schema rejection does not necessarily change the HTTP status.**
   Planting an illegal `subcategory` produced a 404 for one session and a 200 for
   another; the dev server serves cached output while logging the error. The
   oracle is the `InvalidContentEntryDataError` in the dev-server log, not the
   status code. In a build it is fatal, which is what the gates rely on.

### The `.difference-row*` dependency did not exist

03 gated wave A's deletion of the dead `.difference-row*` / `.difference-zoom*`
CSS on wave B landing its replacement, and that ordering shaped the whole
A-then-B sequencing. The block is absent from `main.css` on this branch AND on
`origin/main`, and `git log -S'difference-row'` finds no commit removing it here.
It was already gone before the wave began. The body of this file still cites it
at `main.css:1956-2090`, measured in the pre-move checkout.

### RTL illustrations are a DECISION, not a patch (open)

Under `/ar` the alternating rows mirror but the illustrations keep pointing
left-to-right, so a before/after arrow runs against the reading direction. The
obvious `[dir="rtl"] svg { transform: scaleX(-1) }` would fix the arrows and
BREAK three of the four drawings, which contain a clock face or a circular arrow
whose direction is intrinsic. The real fix is per-illustration RTL variants --
`instant-recovery.mobile.svg` already establishes the variant-file convention --
which means authoring new files under `src/assets/images/illustrations/` and it
affects the solution pages too.
