# EXPLORE: www chrome, theming, CI gates

Read-only investigation. Repo root `/home/muhammed/monorepo/console`, all paths below
relative to `packages/www` unless prefixed. Nothing was modified.

Live-browser readings quoted below were taken by the team lead, not by this session, and
are marked LIVE. Everything else is source evidence with `file:line`.

---

## 1. Header auto-hide

### 1.1 It does not hide, and it has no direction detection

The nav is permanently `position: fixed` (`public/styles/main.css:900`) and never translates
as a whole. What moves is a SUBSET of its children, driven linearly by ABSOLUTE scroll depth
over the first 80px, then clamped. There is no "scrolling up reveals it" behaviour, no
threshold pair, no last-scroll-Y comparison. Anyone planning work here on the assumption of a
conventional hide-on-scroll-down header will be planning against something that does not exist.

### 1.2 The scroll logic

Entirely in `src/components/Navigation.tsx:58-112`: one `useEffect`, one `scroll` listener
(`:104`, `{ passive: true }`), coalesced through `requestAnimationFrame` (`:99-102`).

`public/scripts/main.js` has NOTHING to do with it. Its only scroll code is smooth-anchor
scrolling (`:15-44`) and section-link highlighting (`:328-352`).

The handler (`Navigation.tsx:63-98`) clamps `y = min(max(scrollY,0), 80)` (`:65`) and writes:

| Written | Value | Set at | Consumed at |
|---|---|---|---|
| `--nav-scroll-y` | `-y * 0.5` px | `Navigation.tsx:69` | `main.css:925` — `.nav-translate { top }` |
| `--nav-scroll-fade` | `1 - y/80` | `Navigation.tsx:70` | `main.css:926` — `.nav-translate { opacity }` |
| `--nav-wordmark-fade` | `1 - y/80` | `Navigation.tsx:88` | `main.css:1092-1093` — `inline-size` + `opacity` |
| `--nav-wordmark-w` | measured `getBoundingClientRect().width` | `Navigation.tsx:85` | `main.css:1092` |
| `body[data-nav-collapsed="true"]` | attribute, set at `y >= 80` | `Navigation.tsx:89-97` | `main.css:932` — `pointer-events: none` |

**The class toggled is not a class.** It is the body ATTRIBUTE `data-nav-collapsed`
(`Navigation.tsx:91` sets, `:96` removes), selected by `body[data-nav-collapsed='true']
.nav-translate` at `main.css:932-934`. The two element hooks are the static classes
`.nav-translate` (applied at `Navigation.tsx:236` on `.nav-links` and `:281` on
`.nav-utilities`) and `.nav-wordmark` (`:232`). Nothing is added or removed from a
`classList` anywhere in this component.

Translate range is deliberately HALF the scroll range (`* 0.5`, `Navigation.tsx:69`) so items
progressively clip against the nav's top edge instead of jumping out in the first few pixels
(`Navigation.tsx:66-68`).

### 1.3 Constraints that will bite an edit

- **`top`, not `transform`** (`main.css:915-917`, restated `:1082-1088`). A transform on
  `.nav-translate` or `.nav-wordmark` would establish a containing block, and the mega-menu
  panels are `position: fixed` and must resolve against the VIEWPORT. Changing either to a
  transform silently mispositions all three dropdowns.
- `.nav` sets `clip-path: inset(0 -100vw -100vh -100vw)` (`main.css:909`) so items visibly
  clip at the nav's top edge rather than sliding behind the announcement banner. The generous
  negative insets on the other three sides preserve the downward overflow the mega-menus need.
- The wordmark collapses via `inline-size` (`main.css:1092`), not `scale`, so the width is
  actually reclaimed. Its natural width is REMEASURED at `scrollY === 0` with the clamp
  temporarily cleared (`Navigation.tsx:71-87`) because `.nav-wordmark` steps down a font size
  below 48rem (`main.css:1130-1132`), so a literal would be wrong on phones.
- Crossing 80px force-closes all three dropdowns (`Navigation.tsx:92-94`).
- Both animations use a literal `80ms linear` (`main.css:927-929`, `:1096-1098`), deliberately
  OFF the duration token scale (`main.css:919-922`): it is a smoothing constant between scroll
  samples, not a state transition. A tokenised 150ms would make the nav visibly lag the page.
- `prefers-reduced-motion` neutralises both (`main.css:936-942`, `:1102-1108`).
- Cleanup removes the attribute and two of the four properties (`Navigation.tsx:105-111`).
  `--nav-scroll-y` and `--nav-scroll-fade` are NOT removed on unmount; they fall back to the
  `:root` defaults at `main.css:355-356`.

### 1.4 The menu DATA — where every item lives

There is **no menu config file**. Items are hardcoded JSX or module-level consts; only the
LABELS come from i18n (`src/i18n/translations/en.json`, `navigation.*`).

**Desktop bar** — `src/components/Navigation.tsx:189-308`, grid `auto auto 1fr auto auto`
(`main.css:966`), left to right:

| Slot | Element | Source |
|---|---|---|
| 1 | hamburger button | `Navigation.tsx:196-207` |
| 2 | icon link (logo SVG) | `Navigation.tsx:208-225` |
| 3 | `.nav-brand` wordmark | `Navigation.tsx:226-235` |
| 4 | `.nav-links.nav-translate` | `Navigation.tsx:236-279` |
| 5 | `.nav-right` | `Navigation.tsx:280-306` |

`.nav-links` contents, in order (`Navigation.tsx:237-278`):
1. `Solutions` — plain anchor to `/{lang}#solutions`, label `navigation.solutions`
2. `<PersonaMegaMenu>` — `:246-251`
3. `Pricing` — plain anchor to `/{lang}/pricing`, label `navigation.pricing`
4. `<LearnMenu>` — `:264-269`
5. `Blog` — plain anchor to `/{lang}/blog`, label `navigation.blog`

`.nav-right` contents (`Navigation.tsx:280-306`):
- `.nav-utilities.nav-translate` > `<LanguageMenu variant="icon-only" position="top">` (`:282-289`)
- `<NavCtaMenu>` (`:291-305`) — NOT inside `.nav-translate`, so it stays put on scroll

**PersonaMegaMenu data** — `src/components/PersonaMegaMenu.tsx:85-90`, a module const:

```ts
const PERSONA_CARDS = [
  { slug: 'for-devops',   titleKey: 'forDevops',   personaKey: 'devops',   Icon: TerminalIcon  },
  { slug: 'for-ctos',     titleKey: 'forCtos',     personaKey: 'cto',      Icon: BuildingIcon  },
  { slug: 'for-ceos',     titleKey: 'forCeos',     personaKey: 'ceo',      Icon: BriefcaseIcon },
  { slug: 'for-ai-agents',titleKey: 'forAiAgents', personaKey: 'ai-agent', Icon: CpuIcon       },
] as const;
```

Icons are inline SVG components defined immediately above (`:16-83`). Taglines and CTAs come
from `navigation.personas.<personaKey>.{tagline,cta}` in `en.json`.

**LearnMenu data** — DERIVED, not hardcoded. `src/components/LearnMenu.tsx:44-55` maps
`CATEGORY_ORDER` from `src/utils/docs-categories.ts:18-25`:

```
Tutorials, Guides, Concepts, Reference, Use Cases, Legal
```

then appends a `Browse all docs` row (`LearnMenu.tsx:50-54`). Each entry deep-links to
`/{lang}/docs?category=<encoded>` (`:48`). Labels resolve through `CATEGORY_KEYS`
(`docs-categories.ts:43-50`) to `documentation.categories.*`. The category identifiers are
English in every locale on purpose (`LearnMenu.tsx:25-26`, `docs-categories.ts:1-14`) — a
translated identifier in a query string would filter nothing.

**NavCtaMenu data** — `src/components/NavCtaMenu.tsx`. Split button: wide `Get Started`
segment plus an attached caret segment opening a 2-item panel, `Log in` and `Search`
(`MENU_ITEM_COUNT = 2` at `:50`). `Log in` stays an `AccountCta` so the region-picker
interception (`window.openRegionPicker`) is preserved (`:26-29`). The panel takes its
accessible name from the trigger via `aria-labelledby` (`:31-34`, `TRIGGER_ID` at `:53`).

**Mobile drawer** — `src/components/Sidebar.tsx:151-171`, THREE separate arrays:

```ts
topNavItems    = [ Home /{lang}, Solutions /{lang}#solutions ]                  // :151-154
personaItems   = [ for-devops, for-ctos, for-ceos, for-ai-agents ]              // :156-161
bottomNavItems = [ pricing, roi-calculator, disaster-recovery, partners,
                   blog, docs/quick-start, contact ]                            // :163-170
```

### 1.5 Desktop and mobile menus have DRIFTED (finding)

- `Sidebar.tsx:169` points `Docs` at `/{lang}/docs/quick-start` — the exact deep-link-past-
  the-index that `LearnMenu` was built to replace (`LearnMenu.tsx:10-13`).
- The drawer carries four routes the desktop bar does not: `roi-calculator`,
  `disaster-recovery`, `partners`, `contact` (`Sidebar.tsx:165-170`), plus `Downloads` and
  `Install` keys exist in `navigation.*` but appear in neither.
- The persona list is duplicated: `PERSONA_CARDS` (`PersonaMegaMenu.tsx:85-90`) and
  `personaItems` (`Sidebar.tsx:156-161`) are two hand-maintained copies of the same four
  routes. Adding a fifth persona requires editing both, and nothing fails if you edit one.

### 1.6 Popover contract (all three dropdowns)

All three are native `popover="auto"` panels, so the UA supplies light-dismiss, Escape,
top-layer stacking (no z-index race), the dimming `::backdrop`, and mutual exclusion.
`main.css:944-958` styles `[popover]::backdrop` globally at `rgb(0 0 0 / 45%)` — attached to
the attribute rather than to a component class so nav dropdowns and page dialogs dim
identically.

Open state is LIFTED into `Navigation` (`:31-33`) because FOUR dismissals are invisible to a
popover: scroll past 80px, opening the sidebar, opening search, and `astro:after-swap`
(`PersonaMegaMenu.tsx:106-112`, `Navigation.tsx:163-171`). Hand-written extras are only what
the Popover API lacks: roving Arrow/Home/End focus and focus return to the trigger on Escape
(`LearnMenu.tsx:94-133`).

`LearnMenu.tsx:65-82` positions its panel with an INLINE `left` measured from the trigger at
open time and clamped to the viewport, because a top-layer popover's containing block is the
viewport and a declarative rule cannot know where the trigger sits. The comment at `:64`
records that this mistake was already made twice in this header.

### 1.7 Per-page / contextual menus

Three, none of which interact with the header collapse:
- `src/components/DocsTopTabs.astro` — docs category tabs, rendered by
  `src/layouts/DocsLayout.astro:113`, `variant: 'article' | 'index'`. Its own inline script
  (`DocsTopTabs.astro:66+`) syncs the active tab; the header comment records that `hashchange`
  alone never worked because Astro's client router uses the History API.
- `src/components/DocsSidebar.astro` — rendered by `DocsLayout.astro:194`.
- `src/components/BlogStickyBar.tsx` — rendered by `src/layouts/ContentLayout.astro:170`.

### 1.8 AnnouncementBar interaction

**Currently DISABLED.** `src/i18n/translations/en.json` has `announcement.enabled: false`;
`AnnouncementBar.astro:22` reads the canonical EN value and `:27` gates the entire render on
it, so the bar never disagrees across locales.

- When OFF: `--announcement-bar-height` keeps its `0px` default (`main.css:250`) and `.nav`
  falls back to `top: 0` (`main.css:901` — `top: var(--announcement-bar-height, 0)`).
- When ON: the component ships a `:root { --announcement-bar-height: 2.625rem }` style block
  (`AnnouncementBar.astro:32`), then an inline script overwrites it with the MEASURED height
  via `ResizeObserver` (`:39-56`), because the text wraps to two lines on mobile.
- `.announcement-bar` is itself `position: fixed; top: 0` at `z-index: calc(var(--z-fixed) + 1)`
  (`main.css:2186-2194`), i.e. ABOVE the nav — which is why faded `.nav-translate` items are
  given `pointer-events: none` (`main.css:932`), so invisible items cannot swallow clicks.
- `--nav-top-offset` = `calc(var(--nav-height) + var(--announcement-bar-height, 0px))`
  (`main.css:251`). Consumed by `html { scroll-padding-top }` (`main.css:674`), by the two
  mega-menu panel stylesheets (`src/styles/learn-menu.css:36`,
  `src/styles/persona-mega-menu.css:54`), and by ~15 page stylesheets for hero top padding
  (e.g. `src/styles/pricing-page.css:702`, `src/styles/legal-page.css:11`,
  `src/pages/[lang]/contact.astro:63`, `src/components/solution-pages/SPHomeHero.astro:60`).

**Enabling the bar therefore reflows every hero on the site through one variable.** Two page
files hardcode a fallback (`src/pages/[lang]/partners.astro:165,503` use
`var(--nav-top-offset, 3.5rem)`), which is stale if `--nav-height` ever changes.

---

## 2. Footer language dropdown

### 2.1 Root cause

`public/styles/main.css:2797-2806` — the `.footer` rule re-points FIVE custom properties to
dark-theme values so its descendants read on the black band:

```css
.footer {
  background-color: var(--sp-bg-hero);
  padding: var(--space-20) 0 var(--space-8);
  --color-text: #e4e4e7;
  --color-text-secondary: #a1a1aa;
  --color-border: rgb(255 255 255 / 12%);
  --color-interactive-hover: rgb(255 255 255 / 8%);
  --color-interactive-active: rgb(255 255 255 / 14%);
  color: var(--color-text);
}
```

**It does not re-point `--color-bg-alt`.** The language switcher paints its own surface from
exactly that token, so the surface stays light-theme while the inherited text goes dark-theme:

| Rule | file:line | Declaration |
|---|---|---|
| `.language-trigger` background | `src/styles/language-switcher.css:15` | `background: var(--color-bg-alt)` |
| `.language-trigger` color | `src/styles/language-switcher.css:18` | `color: var(--color-text)` |
| `.language-trigger` border | `src/styles/language-switcher.css:16` | `border: 1px solid var(--color-border)` |
| `.language-menu` background | `src/styles/language-switcher.css:88` | `background-color: var(--color-bg-alt)` |
| `.language-option` color | `src/styles/language-switcher.css:122` | `color: var(--color-text)` |

Token resolution:
- `--color-bg-alt` light = `var(--gray-0)` = `#ffffff` (`main.css:130` -> `main.css:87`)
- `--color-bg-alt` dark  = `#1a1a1b` (`main.css:471`)
- inherited `--color-text` inside `.footer` = `#e4e4e7` in BOTH themes (`main.css:2800`)

**LIGHT theme: `#e4e4e7` on `#ffffff` ≈ 1.13:1** — the trigger label and every row of the open
panel. The border is `rgb(255 255 255 / 12%)` on white, so the control has no visible edge
either: it reads as a blank white pill.

**DARK theme: `#e4e4e7` on `#1a1a1b` ≈ 13.7:1** — correct. **The bug is light-theme-only.**

LIVE CONFIRMATION (team lead): footer `.language-trigger` computes
`background rgb(255,255,255)` with `color rgb(228,228,231)`. `rgb(228,228,231)` is `#e4e4e7`
exactly, and `rgb(255,255,255)` is `--gray-0`. This matches the source derivation on both
halves.

### 2.2 Two corroborating tells

These confirm the diagnosis is the token gap and not something incidental:

1. `.language-option.active` sets `color: var(--color-brand-primary)` = `#4a7c3f`
   (`language-switcher.css:136-140`), so **the currently-selected language is the one readable
   row** in an otherwise invisible panel.
2. `.language-option:hover` uses `--color-hover` = `--gray-100` = `#f7f7f8`
   (`language-switcher.css:133`, `main.css:136` -> `:88`), which `.footer` also does not
   re-point, so hovering does not rescue it either.

### 2.3 Fix shape (not applied)

Add `--color-bg-alt` (and, for the hover wash, `--color-hover`) to the `.footer` token block
at `main.css:2797-2806`, pointing at the dark-theme values `#1a1a1b` / `#1f1f23` already
measured in `main.css:471,477`. This is consistent with the block's own stated design
(`main.css:2787-2792`): re-point tokens on the container rather than editing the thirty
`.footer-*` rules. It fixes the trigger, the panel and every row in one edit, and it stays
reversible. Do NOT patch `language-switcher.css` — that would break the header mount.

### 2.4 The same component elsewhere — YES, styled differently in the header

`LanguageMenu` mounts at four sites:

| Mount | file:line | variant | Affected? |
|---|---|---|---|
| Header nav | `src/components/Navigation.tsx:282-289` | `icon-only`, `position="top"` | **No** |
| Footer | `src/components/Footer.tsx:354-361` | `flag-name`, `position="bottom"` | **YES — the bug** |
| Tutorial player | `src/components/TutorialVideoPlayer.tsx:557` | `flag-name`, `position="top"`, `persistPreference={false}` | No |
| Solution video player | `src/components/solution-pages/SolutionVideoPlayer.tsx:139` | `flag-name`, `position="top"`, `persistPreference={false}` | No |

The header escapes for TWO independent reasons, either of which alone would be enough:

1. **Different variant, different CSS path.** `variant="icon-only"` renders
   `.language-trigger-icon` (`LanguageMenu.tsx:197-226`), which is `background: transparent`
   (`language-switcher.css:37`) and never reads `--color-bg-alt`. The `flag-name` /
   `full-list` variants render `.language-trigger` (`LanguageMenu.tsx:230-259`), which does.
2. **Different token scope.** The header mount is not a descendant of `.footer`, so
   `--color-text` is the normal semantic value for the active theme.

Note `.language-trigger-icon` is styled TWICE: `language-switcher.css:30-45` and, as part of
the shared `.btn--icon` / `.hamburger-btn` / `.sidebar-close-btn` family, `main.css:1506-1532`
(hover `:1534-1541`, active `:1543-1549`, focus `:1551-1557`). Built pages load `main.css`
first and component CSS after (verified against `dist/en/pricing/index.html`, section 4.2
below), so the component sheet wins on conflicting properties. Any edit to the icon variant
must account for both blocks.

### 2.5 Structure reference

`LanguageMenu.tsx` renders `.language-selector` > trigger + (when open)
`.language-menu.{top|bottom}` > N × `.language-option` (`:340-349`). `position` only selects
`top: 100%` (`language-switcher.css:99-103`) vs `bottom: 100%`
(`language-switcher.css:106-110`); it has no colour effect. The panel is conditionally
mounted (`:344`), i.e. NOT a native popover — unlike the three header dropdowns it uses a
`mousedown` outside-click handler (`:86-101`) and its own keydown handler (`:110-154`).

---

## 3. Section background colours

### 3.1 CORRECTION to the briefing premise

The briefing said design tokens are split across FIVE `:root` blocks with the last winning,
and that the inline block in `BaseLayout.astro` (~279-414) overrides `main.css`.

**That was fixed on 2026-08-18 and is no longer true.** Verified two ways:

- `main.css:64-67` states it: *"This is the ONLY unconditional `:root` in the project. Before
  2026-08-18 there were five, the last one in the document silently won, and two rules were
  provably dead because of it."*
- `BaseLayout.astro:339-348` documents the removal by name: the embed-mode block *"used to
  also carry a 17-token `:root` copy plus scoped duplicates of `.nav`, `.nav-container`,
  `.nav-brand`, `.logo`, `.nav-wordmark`, `.container`, `*`, `body` and `main`... Both are
  gone; the tokens live in exactly one place now."*

A full grep of `src/` and `public/styles/` for `:root` returns only:

| Block | file:line | Scope |
|---|---|---|
| The token layer | `public/styles/main.css:79-442` | unconditional, ~200 tokens |
| Dark theme | `public/styles/main.css:466-538` | `:root[data-theme='dark']`, semantic layer only |
| Reduced motion | `public/styles/main.css:555-562` | inside `@media (prefers-reduced-motion: reduce)`, 6 tokens |
| Increased contrast | `public/styles/main.css:652-656` | inside `@media (prefers-contrast: more)`, 3 tokens |
| RTL | `public/styles/main.css:446-448` | `[dir='rtl']`, 1 token (`--motion-nudge`) |
| Announcement height | `src/components/AnnouncementBar.astro:32` | 1 token, only when the bar renders |
| a11y string | `src/layouts/BaseLayout.astro:303` | 1 token (`--a11y-opens-in-new-tab`) |

`public/styles/responsive.css:72-73` records that its own `:root { --max-width: 1400px }` was
DEAD for the same reason and has been deleted. **Plan against the single-`:root` model.**

### 3.2 Is there a token ladder? YES

`main.css:79-442` is an explicit three-layer design system, numbered in 19 commented sections:

1. **RAMP** (`:82-94`) — the closed greyscale, 8 steps, deliberately sparse:
   `--gray-0 #ffffff`, `--gray-100 #f7f7f8`, `--gray-400 #d2d2d7`, `--gray-500 #a1a1aa`,
   `--gray-600 #6e6e73`, `--gray-700 #5e5e63`, `--gray-900 #1a1a1a`, `--gray-950 #111113`.
2. **BRAND** (`:96-126`) — one green, split into `--color-brand-fill` (carries white text) and
   `--color-brand-primary` (text/icon on a surface), because no single value satisfies both
   contrast constraints. Plus `--color-brand-bolt #dc2626`, reserved for THE single
   highest-intent CTA per page and gated by `check:ci-cta-bolt`.
3. **SEMANTIC** (`:128-152`) — surfaces, foregrounds, borders, which alias the ramp.

The stated rule (`main.css:464-465`): *"Rules must reference the SEMANTIC names, never
`--gray-*` directly: the ramp is authoring input for the light theme and does not flip."*
Dark mode (`:466-538`) redefines the semantic layer ONLY — accents included, which is what
finally made the accents flip.

The ladder is real and mostly honoured. The defects below are all cases where a consumer
either bypassed the semantic layer or picked the wrong semantic name.

### 3.3 Three parallel, unreconciled mechanisms

| # | Mechanism | Declared at | Used by |
|---|---|---|---|
| 1 | `.section-light` / `.section-dark` utilities | **`public/styles/main.css:1336-1344`** | 10 files only |
| 2 | `--sp-*` namespace + per-component scoped `<style>` | aliases `main.css:401-428` | homepage, all solution pages, persona pages |
| 3 | ad-hoc `background: var(--color-bg…)` in page CSS | scattered | `pricing-page.css`, `main.css` component rules |

```css
/* public/styles/main.css:1335-1344 */
/* Section Background Utilities */
.section-light {
  background: var(--color-bg-light);
  color: var(--color-text);
}

.section-dark {
  background: var(--color-bg-dark);
  color: white;
}
```

Mechanism 1 consumers (all `.astro`): `pages/[lang]/pricing.astro`, `downloads.astro`,
`disaster-recovery.astro`, `professional-services.astro`, `install.astro`,
`resources/nis2-directive-summary.astro`, `components/resources/ResourceBriefPage.astro`,
`components/FAQSection.astro:22`, `components/PricingComparison.astro:35`,
`components/PricingTrustSection.astro:16`.

**Mechanism 1 is the LOWEST-priority layer.** Page-scoped CSS loads after `main.css`
(verified, section 4.2), so a page stylesheet silently beats the utility at equal specificity.

### 3.4 Token resolution table

| Token | Declared | Light | Dark |
|---|---|---|---|
| `--color-bg` | `main.css:129` | `#f7f7f8` | `#0f0f10` (`:470`) |
| `--color-bg-alt` | `main.css:130` | `#ffffff` | `#1a1a1b` (`:471`) |
| `--color-bg-light` | `main.css:131` | `#f7f7f8` | `#141416` (`:472`) |
| `--color-bg-dark` | `main.css:132` | `#1a1a1a` | `#0a0a0b` (`:473`) |
| `--color-bg-secondary` | `main.css:134` | `#f7f7f8` | `#141416` (`:475`) |
| `--color-surface-alt` | `main.css:138` | `#f7f7f8` | `#141416` (`:479`) |
| `--color-brand-tint` | `main.css:112` | `#eef3ea` | `#1a2118` (`:502`) |
| `--sp-bg-hero` | `main.css:409` = `var(--gray-950)` | `#111113` | **`#111113` (does not flip)** |
| `--sp-bg-dark` | `main.css:410` = `var(--gray-900)` | `#1a1a1a` | **`#1a1a1a` (does not flip)** |
| `--sp-bg-light` | `main.css:411` = `var(--color-bg-light)` | `#f7f7f8` | `#141416` |
| `--sp-bg-white` | `main.css:412` = `var(--color-bg-alt)` | `#ffffff` | `#1a1a1b` |
| `--sp-bg-stats` | `main.css:413` = `var(--color-brand-tint)` | `#eef3ea` | `#1a2118` |
| `body` background | `main.css:705` = `var(--color-bg-alt)` | `#ffffff` | `#1a1a1b` |

LIVE (team lead): six surface colours actually in use are `#111113`, `#1a1a1a`, `#ffffff`,
`#f7f7f8`, `#eef3ea`, and `transparent`. That matches this table's LIGHT column exactly, plus
`transparent` — see 3.5(f) for where `transparent` comes from.

### 3.5 Concrete inconsistencies

**(a) Four tokens collapse to ONE value in light and split into TWO in dark.**
`--color-bg`, `--color-bg-light`, `--color-bg-secondary` and `--color-surface-alt` are all
`--gray-100 #f7f7f8` in light (`main.css:129,131,134,138`) but `#0f0f10` vs `#141416` in dark
(`main.css:470,472,475,479`). Two sections that are pixel-identical in light become visibly
different bands in dark. Live on the homepage: `.sp-not-a-slice` uses `--sp-bg-light`
(`src/components/solution-pages/SPHomeNotASlice.astro:112`) while `.cf-pricing-section` uses
`--color-bg` (`src/styles/pricing-page.css:842`).

**(b) `--sp-bg-hero` and `--sp-bg-dark` bypass the semantic layer and therefore do not flip.**
`main.css:409-410` declares them as `var(--gray-950)` / `var(--gray-900)`, breaking the rule
stated 55 lines later at `main.css:464-465`. Worse, `main.css:535-537` claims *"Every `--sp-*`
alias follows from the semantic tokens above"* — which is FALSE for exactly these two.

Consequence in dark mode: `.sp-benefits` = `#1a1a1a` (`src/styles/solution-pages.css:1176`)
while the sections above and below it use `--sp-bg-white` = `#1a1a1b`. **One unit of blue
channel.** The dark "Benefits" band on every solution page is effectively INVISIBLE in dark
mode, while its heading is still `--sp-text-white` = `#ffffff`
(`solution-pages.css:1188`) — styled for a contrast that is no longer there.

This is the single sharpest defect in area 3.

**(c) Two different blacks stack at the bottom of the pricing page.**
`.pricing-cta` carries `.section-dark` (`pages/[lang]/pricing.astro:153`) →
`--color-bg-dark` = `#1a1a1a`; the `.footer` immediately below is `--sp-bg-hero` = `#111113`.
The footer's own comment (`main.css:2783-2785`) says it shares its token with `.sp-bottom-cta`
*specifically* so the closing CTA and footer read as ONE continuous black band. Solution pages
honour that (`solution-pages.css:1453`); **pricing does not**, producing a visible seam
between two near-identical blacks.

**(d) Six consecutive `.section-light` sections on `/en/pricing`** — no alternation at all,
one continuous `#f7f7f8` slab. LIVE-confirmed by the team lead; the six are three inline plus
three from embedded components:

| # | Section | file:line |
|---|---|---|
| 1 | `.pricing-content` | `pages/[lang]/pricing.astro:72` |
| 2 | `.roi-cta-section` | `pages/[lang]/pricing.astro:96` |
| 3 | `.edge-channel-section` | `pages/[lang]/pricing.astro:111` |
| 4 | `.pricing-trust-section` | `components/PricingTrustSection.astro:16` (rendered `pricing.astro:130`) |
| 5 | `.comparison-section` | `components/PricingComparison.astro:35` (rendered `pricing.astro:133`) |
| 6 | `.faq-section` | `components/FAQSection.astro:22` (rendered `pricing.astro:136`) |

None of the six page-level classes declares its own background (`pricing-page.css:69`, `:592`,
`:628` set padding only), so `.section-light` is what paints, six times in a row. Then
`.ps-teaser-section` and `.pricing-cta` are two consecutive `.section-dark`
(`pricing.astro:139,153`).

The same shape recurs on solution pages: `.sp-cost-section` and `.sp-how-it-works` are both
`--sp-bg-white` (`solution-pages.css:435,633`), and `.sp-social-proof` and `.sp-sources` are
both `--sp-bg-light` (`solution-pages.css:1340,2149`).

**(e) `.section-dark` hardcodes `color: white`** (`main.css:1343`) where the footer — the same
visual treatment — uses `#e4e4e7` (`main.css:2800`). Two answers to one question.

**(f) `.pricing-hero.section-dark` computes `transparent`** — LIVE on `/en/disaster-recovery`.
Mechanism confirmed from source: `.pricing-hero` sets `background: var(--gradient-dark)`
(`pricing-page.css:40`), and `--gradient-dark` (`main.css:397`) is a `linear-gradient`, i.e. a
background-IMAGE. The `background` shorthand resets `background-color` to `transparent`, so
the element paints its gradient while `background-color` reads `transparent` and
`.section-dark`'s `background: var(--color-bg-dark)` is fully overridden. `disaster-recovery.astro:71`
carries BOTH classes, so the `.section-dark` on that element is decorative — it contributes
only `color: white`. This is the clearest live proof that mechanism 1 loses to page CSS.

**(g) Minor:** `.sp-tech-detail-col-header.traditional` uses `--color-bg-light`
(`solution-pages.css:1151`) where every sibling in that file uses `--sp-bg-light`. Same value
today, inconsistent naming, and it would diverge if either alias were re-pointed.

### 3.6 Full band survey

**Solution page** (`src/styles/solution-pages.css`, top to bottom):

| Order | Selector | file:line | Token | Light | Dark |
|---|---|---|---|---|---|
| 1 | `.sp-page > nav.sp-breadcrumb` | `:29` | `--sp-bg-hero` | `#111113` | `#111113` |
| 2 | `.sp-hero` | `:63` | `--sp-bg-hero` | `#111113` | `#111113` |
| 3 | `.sp-stats` | `:137` | `--sp-bg-stats` | `#eef3ea` | `#1a2118` |
| 4 | `.sp-problem` | `:188` | `--sp-bg-light` | `#f7f7f8` | `#141416` |
| 5 | `.sp-cost-section` | `:435` | `--sp-bg-white` | `#ffffff` | `#1a1a1b` |
| 6 | `.sp-how-it-works` | `:633` | `--sp-bg-white` | `#ffffff` | `#1a1a1b` |
| 7 | `.sp-tech-detail` | `:1109` | `--sp-bg-light` | `#f7f7f8` | `#141416` |
| 8 | `.sp-benefits` | `:1176` | `--sp-bg-dark` | `#1a1a1a` | `#1a1a1a` ← invisible |
| 9 | `.sp-comparison-section` | `:1240` | `--sp-bg-white` | `#ffffff` | `#1a1a1b` |
| 10 | `.sp-social-proof` | `:1340` | `--sp-bg-light` | `#f7f7f8` | `#141416` |
| 11 | `.sp-sources` | `:2149` | `--sp-bg-light` | `#f7f7f8` | `#141416` |
| 12 | `.sp-bottom-cta` | `:1453` | `--sp-bg-hero` | `#111113` | `#111113` |
| 13 | `.footer` | `main.css:2798` | `--sp-bg-hero` | `#111113` | `#111113` |

Also `.sp-page > .sp-page-header` `--sp-bg-hero` (`:36`) on pages that use it, and
`.sp-roi-section` `--sp-bg-white` (`:1658`), `.sp-download-short` / `.sp-downloads-row`
`--sp-bg-light` (`:2059`, `:2071`).

**Homepage `/en/`** — composed by `src/pages/[lang]/index.astro:23` →
`src/components/solution-pages/SPHomePage.astro:55-63`:

| Order | Component | Selector | file:line | Token |
|---|---|---|---|---|
| 1 | `SPHomeHero` | `.sp-home-hero` | `SPHomeHero.astro:59` | `--sp-bg-hero` `#111113` |
| 2 | `SolutionConstellation` | `.cx-*` | — | none (inherits body `#ffffff`) |
| 3 | `SPHomeNotASlice` | `.sp-not-a-slice` | `SPHomeNotASlice.astro:112` | `--sp-bg-light` `#f7f7f8` |
| 4 | `HomeDifference` | `.home-difference` | `main.css:2121` | `--color-bg-alt` `#ffffff` |
| 5 | `PricingPreview` | `.cf-pricing-section` | `pricing-page.css:842` | `--color-bg` `#f7f7f8` |
| 6 | `SPHomeBottomCta` | `.closing-cta` | `main.css:2212-2214` | none (inherits body `#ffffff`) |
| 7 | `Footer` | `.footer` | `main.css:2798` | `--sp-bg-hero` `#111113` |

Light reads as a clean alternation. Dark does not: bands 3 and 5 are `#141416` and `#0f0f10`
for what light renders as one identical value — defect (a).

`.closing-cta` is declared twice (`main.css:2038-2042` sets `content-visibility`,
`:2212-2214` sets padding). Complementary, not conflicting; noted so a future reader does not
"fix" it.

**Pricing `/en/pricing`** — six `.section-light`, then two `.section-dark`, then footer. See 3.5(d).

**Docs `/en/docs`** — `src/layouts/DocsLayout.astro` has NO alternating section bands. It is
`--color-bg-alt` chrome throughout (`:799`, `:828`, `:922`), with `--color-hover` for row
states (`:945`, `:950`) and `--color-surface` for cards (`:1129`). Area 3 does not apply here.

---

## 4. CI gate infrastructure

### 4.1 The three-point wiring

Adding a blocking gate requires exactly THREE edits, and `check:ci-parity` enforces all three
bidirectionally. Miss any one and that gate fails.

#### Edit 1 — root `package.json`

Add a `check:ci-<name>` key. 175 `check:*` keys exist today. Convention:

```json
"check:ci-foo": "tsx scripts/check-foo.ts"
```

CONTROL-FIRST variant, used by every gate that has a self-test — strongly preferred:

```json
"check:ci-foo": "tsx scripts/check-foo.ts --selftest && tsx scripts/check-foo.ts"
```

Live examples of the control-first form: `check:ci-dead-css`, `check:ci-css-dom-refs`,
`check:ci-svg-theme-reach`, `check:ci-landmarks`, `check:ci-tutorial-card-fonts`,
`check:ci-solution-videos`, `check:ci-client-i18n`.

`packages/www/package.json` owns **no** `check:ci-*` keys. It uses `validate:*`, `i18n:*`, and
a single `check:cta-bolt`. Root reaches into the workspace two ways:
- delegate: `"check:ci-cta-bolt": "npm run check:cta-bolt -w @rediacc/www"`
- direct path: `"check:ci-tutorial-parity": "tsx packages/www/scripts/check-tutorial-parity.ts"`

#### Edit 2 — `scripts/ci-runner/manifest.ts`

Add a `GateSpec`. Interface at `scripts/ci-runner/manifest.ts:27-58`:

```ts
export interface GateSpec {
  id: string;                 // npm script key, or synthetic node id like 'build:packages'
  run: string;                // exact command; also the rerun line printed on failure
  gate: boolean;              // false only for prerequisite nodes that validate nothing
  needs?: string[];           // ordering edges
  mutex?: string[];           // mutual-exclusion groups
  weight?: number;            // scheduler slots, default 1
  heavy?: boolean;            // >=4 GB heap, bounded by --heavy-limit
  paths?: string[];           // repo-relative globs; powers --changed
  qualityGateTest?: boolean;  // set on the 57 entries flattened from .ci/scripts/test/gates/
  leaves: string[];           // leaf commands, NOT the npm key
  ci: CiCoverage;
}
```

`CiCoverage` has three variants (`manifest.ts:60-69`):

```ts
| { kind: 'step'; workflow: string; job: string; step: string }   // verified against parsed YAML
| { kind: 'test'; test: string; blocker: string }                 // a gate test drives the REAL scan
| { kind: 'local-only'; blocker: string }                         // deliberately local-only
```

`leaves` is compared, NOT the npm key (`scripts/check-ci-parity.ts:119-125`): CI frequently
invokes the same underlying script under a different key (`npm run typecheck` vs
`check:types`), and a key-level comparison reports those as breaks.

`needs: ['build:www']` is REQUIRED if the gate reads `packages/www/dist`. `manifest.ts:1626`
states why it is not an optimisation: without `dist` these gates REFUSE rather than
self-skipping. The `build:www` node itself is at `manifest.ts:2364-2377`
(`gate: false`, `mutex: ['www-dist']`, `heavy: true`).

#### Edit 3 — `.github/workflows/ci-quality.yml`

Add a step whose `name:` matches the manifest `step` EXACTLY, inside the job named in the
manifest. Standard guard:

```yaml
      - name: Foo
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: npm run check:ci-foo
```

The ten quality jobs:

| Job id | `name:` | file:line | Runner | Purpose |
|---|---|---|---|---|
| `quality-static` | Static | `:123` | ubuntu-slim | 12 min |
| `quality-branch` | — | `:390` | | branch/history checks |
| `quality-submodule-branches` | — | `:458` | | |
| `quality-code` | — | `:501` | | |
| **`quality-content`** | **Content** | **`:734`** | ubuntu-latest, 15 min | **source-level www/content gates** |
| `quality-packages` | — | `:968` | | |
| `quality-i18n` | i18n | `:1070` | ubuntu-latest, 15 min | needs `fetch-depth: 0`, account submodule, built packages, ~100s R2 audio restore |
| **`quality-www-build`** | **Built-www Gates** | **`:1208`** | ubuntu-latest | runs `build:www`, then gates reading `dist/` |
| `quality-security` | Security | `:1323` | | hosts `run-all.sh`'s 57 gate tests |
| `quality-go` | — | `:1434` | | |

`.github/workflows/ci.yml:479` calls the whole workflow via
`uses: ./.github/workflows/ci-quality.yml`.

**For a CSS / theming / section-colour gate, use `quality-content`.** Its existing neighbours
are exactly the right company — steps "CSS DOM references", "SVG theme reach", "Dead CSS"
(`ci-quality.yml` job `quality-content`) running `check:ci-css-dom-refs`,
`check:ci-svg-theme-reach`, `check:ci-dead-css`. Only use `quality-www-build` if the gate
needs built HTML.

### 4.2 Worked example — copy `check:ci-layout-overflow` VERBATIM

This is the gate to clone for anything that scans stylesheets. It is a source-level CSS scan
with a shrink-only baseline, a self-test, and a `--root` seam.

**Edit 1** — `package.json:229`:

```json
"check:ci-layout-overflow": "tsx scripts/check-layout-overflow.ts",
```

**Edit 2** — `scripts/ci-runner/manifest.ts:2261-2272`:

```ts
  {
    id: 'check:ci-layout-overflow',
    run: 'npm run check:ci-layout-overflow',
    gate: true,
    leaves: ['scripts/check-layout-overflow.ts'],
    ci: {
      kind: 'test',
      test: '.ci/scripts/test/gates/test-layout-overflow.sh',
      blocker:
        'BLOCKER: no quality lane owns CSS overflow, and the two shapes this gate detects are invisible to a browser scan because querySelectorAll returns no pseudo-elements; test-layout-overflow.sh:66 runs the gate seam-free against the real stylesheets inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real parse of every declaration block executes every CI run, and the mutant case beside it strips the nowrap detector and requires the gate\'s own controls to go red',
    },
  },
```

**Edit 3** — none, because this one uses `kind: 'test'`: its CI coverage comes from
`.ci/scripts/test/gates/test-layout-overflow.sh` running inside `run-all.sh` in the
`quality-security` job. Note the `blocker` string NAMES THE LINE (`test-layout-overflow.sh:66`)
that proves the real scan executes. That is mandatory and is never inferred — see 4.4.

**Simpler alternative if you want a plain workflow step** — copy
`check:ci-landmarks` instead (`manifest.ts:1741-1752`):

```ts
  {
    id: 'check:ci-landmarks',
    run: 'npm run check:ci-landmarks',
    gate: true,
    leaves: ['scripts/check-landmarks.ts'],
    ci: {
      kind: 'step',
      workflow: '.github/workflows/ci-quality.yml',
      job: 'quality-www-build',
      step: 'Landmarks',
    },
  },
```

paired with `ci-quality.yml` job `quality-www-build` step:

```yaml
      - name: Landmarks
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: npm run check:ci-landmarks
```

**Stylesheet load order, verified**, from `dist/en/pricing/index.html`:

```html
<link rel="stylesheet" href="/styles/main.css">
<link rel="stylesheet" href="/styles/responsive.css">
<link rel="stylesheet" href="/assets/dev-environments-brief.B5q6um9Y.css">
<link rel="stylesheet" href="/assets/disaster-recovery.C_pPX7Vg.css">
```

Page/component CSS always follows `main.css`. Any gate reasoning about which rule wins must
model this.

### 4.3 Shrink-only baseline — the pattern precisely

Composition logic is SHARED, not copied: `scripts/lib/shrink-only-baseline.ts`.

**Seven consumers today:** `check-cli-docs.ts`, `check-css-dom-refs.ts`, `check-dead-css.ts`,
`check-docker-image-freshness.ts`, `check-em-dash-surfaces.ts`, `check-layout-overflow.ts`,
`check-locale-de-contamination.ts`.

**Named example to copy: `scripts/check-em-dash-surfaces.ts`, baseline
`scripts/data/em-dash-surfaces-baseline.json` (a JSON list, 2,718 entries).**

Baselines live in `scripts/data/<name>-baseline.json`. Two shapes:

| Shape | Files | Growth check |
|---|---|---|
| list of finding ids | `em-dash-surfaces-baseline.json` (2718), `dead-css-baseline.json` (62), `docker-image-freshness-baseline.json` (3), `locale-de-contamination-baseline.json` (0) | `baselineAdditions()` — `shrink-only-baseline.ts:36-54` |
| per-file count map | `css-dom-refs-baseline.json`, `static-nowrap-baseline.json` | `countAdditions()` — `shrink-only-baseline.ts:65-74` |

**Read path:** any finding NOT in the baseline fails; a baselined finding that no longer
reproduces ALSO fails, forcing a drain. Both directions, or it stops shrinking.

**Write path:** `--write-baseline` REFUSES to reseed if the new set contains any id absent from
the old one. This is the whole point of the shared module. From its header
(`shrink-only-baseline.ts:1-34`):

> shrink-only, as enforced: the TOTAL cannot grow without someone noticing.
> shrink-only, as promised:  the SET can only lose members.

All seven gates enforced only the first. A real drain printed `2,189 -> 2,160` and went green
while the set diff showed 30 removed and ONE ADDED. A later em-dash drain (`2,876 -> 2,844`)
was caught only because that session snapshotted the file and diffed by hand.

**There is deliberately NO `--force`** (`shrink-only-baseline.ts:29-33`). The only permitted
growth is a narrow, named `--seed-surface <dir>` (`check-em-dash-surfaces.ts:32`), and the
seed comparison is on the PATH half of the id using `lastIndexOf(':')`, not `indexOf`, so a
colon-bearing location cannot silently widen the exemption
(`shrink-only-baseline.ts:47-51`).

Two more rules a new baseline gate must follow:

- **Finding ids must survive a line move** (`check-em-dash-surfaces.ts:434-435`), or the
  baseline churns on unrelated edits and gets regenerated wholesale — which is how a
  shrink-only baseline quietly stops shrinking.
- **Surfaces declare a `minFiles` floor** so a collapsed glob FAILS instead of passing
  (`check-em-dash-surfaces.ts:89-104`). Nested surfaces disjoint only by extension are
  checked by `nestedSurfaceOverlap()` (`:103`), because double-counting a finding breaks the
  baseline arithmetic (`:449-458`).

`.ci/scripts/test/gates/test-shrink-only-composition.sh` is the meta-gate over this module.

### 4.4 The parity gates

**`check:ci-parity`** — `scripts/check-ci-parity.ts` (878 lines). Wired at `package.json`,
manifest, and `ci-quality.yml` job `quality-content` step *"Validate parity between the local
gate set and the CI quality surface"*.

Three relations across three sets — K (`check:ci-*` keys in package.json), C (what a local run
executes), W (what the CI quality surface executes) — `check-ci-parity.ts:5-11`:

| Rel | Direction | Claim | Predecessor |
|---|---|---|---|
| R1 | K → C | a defined gate must actually run | `check-gate-reachability.ts` |
| R2 | W → C | a CI-run gate must run locally too | `check-ci-chain-parity.ts` |
| R3 | C → W | a locally-run gate must run in CI | **NOBODY — this is #549** |

**C is the MANIFEST, not a string** (`check-ci-parity.ts:18-21`). Both predecessors parsed the
`&&` chain at `package.json scripts.ci`. Once that key became a runner invocation the chain is
empty and both would have passed over everything — manufacturing #549 at scale.

Seven assertions, all evaluated before exit so one run reports everything:

1. Preflight anti-vacuity — `:794-802`; refuses if the manifest declares zero gates
2. Tautology guard — `:394-405`; `npm run ci` / `npm run quality` inside the surface is an
   ERROR, never coverage, because it would make every other assertion vacuous
3. R1 — `:406`
4. R2 — `:416`
5. R3, re-verifying every declared step against the parsed workflow — `:432-481`
6. Manifest hygiene incl. cycle detection — `:482-536`
7. Flattened-battery equality against the on-disk `run-all.sh` glob — `:537-540`

**The measurement trap it exists to avoid** (`:23-33`): the first version regexed whole
workflow FILE TEXT for `npm run <key>`, and `ci-quality.yml` carried a step whose NAME
contained the literal `npm run ci`. So it parses `run:` blocks only, never whole-file text — a
step `name:`, an `env:` value, an `if:` expression and a YAML comment are not invocations.

**Coverage via a test is DECLARED, never INFERRED** (`:35-41`): `run-all.sh` runs 57 gate
tests, and grepping them for a script name is precisely how #549 would have been greenwashed —
`check-jq-boolean-default.ts` is NAMED by `test-gate-anti-vacuity.sh:104` and that test ran
green in CI for weeks while the real scan never executed once. Mentioning a script is not
executing it. Hence the mandatory `blocker` on `ci.kind: 'test'`.

A five-leg control runs BEFORE the real check on every invocation (`:651-696`), including a
leg that exercises the escape hatch itself — an exemption that does not silence a finding
means the file is decorative.

**Escape hatch:** `/home/muhammed/monorepo/console/.ci-parity-exempt`, direction-tagged
(`ci-only` / `local-only`) and BLOCKER-gated via `scripts/lib/blocker-validator.ts`. Bar for
`ci-only` is *"this cannot run on a developer machine at all"*, not *"it is slow"*. Prefer
`ci: { kind: 'local-only' }` in the manifest over an entry here.

**Test seams:** `CI_PARITY_ROOT` overrides the repo root; `CI_PARITY_MANIFEST` reads the gate
list from JSON, so a fixture drives both inputs without touching a tracked file (`:43-45`).

**`check:ci-gate-reachability-coverage`** — a DIFFERENT thing. `package.json:96` →
`.ci/scripts/quality/check_gate_reachability_coverage.py`, run at `ci-quality.yml:305`,
manifest entry `manifest.ts:906-907`. It holds the STOP HOOK's
`.claude/hooks/stop/wl_reggate.py::gate_reachable()` probe honest against actual registrations.

Three assertions:
1. **FLOOR** — the probe discovers ≥ 40 manifest gates (`MIN_MANIFEST_GATES`), so assertion 2
   is not vacuously true. Without this the gate reproduces inside itself the failure shape it
   exists to prevent.
2. **AGREEMENT** — every manifest gate with a `check:*` npm key is reported reachable.
3. **CONTROL** — a fabricated key is reported UNREACHABLE, so "reachable" has not widened
   into "always true".

Control-first: it simulates the pre-fix probe (manifest awareness removed) and requires
assertion 2 to FAIL against it; if the planted defect passes, the gate declares itself broken.

Origin (`check_gate_reachability_coverage.py:4-17`): on 2026-08-07 the probe returned False
for EVERY gate — all 191 registrations — because it walked `npm run X` edges from `ci`, and
`ci` is `tsx scripts/ci-runner/run.ts`, whose body contains no `npm run` references. The cost
was not a missed defect but a MANUFACTURED one: it told two consecutive sessions that
correctly-wired gates were "defined but never run". *"A probe that cannot pass is the same
class as a check that cannot fail, and it is more expensive, because it spends real work
denying something true."*

### 4.5 Existing www content / i18n gates

**Typography — the em-dash gate exists.** `check:ci-em-dash-surfaces`, `package.json:224` →
`scripts/check-em-dash-surfaces.ts`, manifest `:2197-2207`, `ci-quality.yml` job `quality-i18n`
step `i18n`. Reached through the `check:i18n` `&&` chain (`package.json:170`) as well as
directly. Baseline 2,718.

Three surfaces (`check-em-dash-surfaces.ts:89-104`):

```ts
{ dir: 'packages/www/src/i18n/translations', kind: 'catalog', exts: ['.json'],           minFiles: 10 }
{ dir: 'packages/www/src',                    kind: 'source',  exts: ['.astro','.tsx'],  minFiles: 50 }
{ tutorial narration JSON — scoped to only the locales where the rule applies }
```

The third is scoped deliberately: the rule removes an English AI tell, and Russian narration
keeps 36 dashes ON PURPOSE — `Репозиторий — это ...` is the copula dash, grammatically
required where English uses "is" (`:105-111`). Applying an English style rule across locales
is a failure class this pipeline has been bitten by before, so the exemption is expressed as a
NARROWER SURFACE rather than baseline entries.

**Root `scripts/` gates that touch www** (all exposed as `check:ci-*`):

| Gate | Script | Purpose |
|---|---|---|
| `check:ci-dead-css` | `check-dead-css.ts` | a CSS rule whose class nothing renders is dead weight |
| `check:ci-css-dom-refs` | `check-css-dom-refs.ts` | every class a component RENDERS must still have a rule — the inverse question |
| `check:ci-svg-theme-reach` | `check-svg-theme-reach.ts` | an SVG expecting theme tokens must be INLINE; an external `<img>` can never see them |
| `check:ci-layout-overflow` | `check-layout-overflow.ts` | the two CSS shapes that make the site scroll sideways |
| `check:ci-design-tree` | `check-design-tree.ts` | design doc §1 must be a transcript of the shipped CLI |
| `check:ci-anchor-integrity` | `check-anchor-integrity.ts` | every in-page fragment link must land on something, every page, every locale |
| `check:ci-hydration-clean` | `check-hydration-clean.ts` | a React island's INITIAL state must not depend on being in a browser |
| `check:ci-landmarks` | `check-landmarks.ts` | exactly one `<main>` landmark per built page |
| `check:ci-seo` | `check-seo.ts` (+ client bundle budget) | SEO validation over built output |
| `check:ci-redirects` | `check-redirect-integrity.ts` + anchor integrity | redirect map integrity |
| `check:ci-ssr-locale` | `check-ssr-locale.ts` | server-rendered locale correctness |
| `check:ci-docs-render-parity` | `check-docs-render-parity.ts` | docs render identically across locales |
| `check:ci-cta-bolt` | `check-cta-bolt-uniqueness.js` (www) | the bolt-red accent is used on at most one CTA per page |
| `check:i18n:components` | `check-component-hardcoded-strings.ts` | no hardcoded user-facing strings in components |
| `check:ci-em-dash-surfaces` | `check-em-dash-surfaces.ts` | **typography** — em dashes in www surfaces |
| `check:ci-dead-translation-keys` | `check-dead-translation-keys.ts` | English keys nothing references |
| `check:ci-i18n-placeholders` | `check-i18n-placeholders.ts` | `{{placeholder}}` parity across locales |
| `check:ci-i18n-untranslated` | `check-i18n-untranslated.ts` | untranslated values |
| `check:ci-i18n-cross-locale` | `check-i18n-cross-locale.ts` | cross-locale contamination |
| `check:ci-locale-de-contamination` | `check-locale-de-contamination.ts` | German contamination, shrink-only baseline (currently 0) |
| `check:ci-directive-quotes` | `check-directive-quotes.ts` | verbatim NIS2 quotations match the official source |
| `check:ci-docs-untranslated-text` | `check-docs-untranslated-text.ts` | untranslated text in documentation |

**`packages/www/scripts/` gates:**

| Script | Purpose |
|---|---|
| `check-client-i18n-freshness.ts` | `src/i18n/client/*.json` freshness |
| `check-locale-tutorial-assets.ts` | per-(locale, tutorial) asset existence, via the manifest |
| `check-solution-videos.ts` | every solution page has its localized videos published |
| `check-solution-video-engine.ts` | every published solution video narrated by the CURRENT TTS engine |
| `check-tutorial-caption-sync.ts` | published word-timing sidecars match real ASR alignment |
| `check-tutorial-card-fonts.ts` | every character on a title/outro card exists in the font |
| `check-tutorial-parity.ts` | parity across the four sources describing a tutorial |
| `check-cta-bolt-uniqueness.js` | two invariants on rendered HTML for the bolt accent |
| `validate-*.js` × 9 | cli-docs, content, content-accuracy, comparison-refs, docs-cli-usage, landing-cli-usage, translation-freshness, tutorial-audio, tutorial-cast-output, tutorial-transcripts |

### 4.6 Recommendation for a section-colour gate

A source-level stylesheet scan is the right instrument and a browser run is not, for the same
reason `check-layout-overflow.ts:19-25` gives: two independent browser-driven hunts reported
"no offending elements" on a page that overflows by 133px, because
`document.querySelectorAll('*')` does not return pseudo-elements. Here the analogous blind
spot is that a computed `background-color` of `transparent` (defect 3.5(f)) tells you nothing
about which rule won.

Copy `scripts/check-layout-overflow.ts` for its skeleton — it already has the right file set:

```ts
const STYLE_DIRS = ['src/styles', 'public/styles'];   // :53-54  (main.css is NOT under src/)
const INLINE_STYLE_DIRS = ['src'];                    // :55     (.astro <style> blocks)
```

Candidate assertions, each backed by a defect above:
- no rule may reference `--gray-*` outside the `:root` token layer (defect 3.5(b);
  the rule is already written down at `main.css:464-465` and is currently unenforced)
- a section-level background must come from the semantic layer, not `--color-bg` and
  `--color-bg-light` interchangeably (defect 3.5(a))
- adjacent sections in a page's component chain must not resolve to the same token
  (defects 3.5(d))

Seed a shrink-only baseline per 4.3, add `--selftest` with a planted defect, and wire the
three points per 4.2 into `quality-content`.

---

## 5. Incidental findings (not asked for)

**5.1 `check:ci-landmarks` and `check:ci-browser-smoke` are missing `needs: ['build:www']`.**
`manifest.ts:1729-1739` (browser-smoke) and `:1741-1752` (landmarks). Both sit in the
`quality-www-build` job and read `packages/www/dist`. Their immediate neighbour
`check:ci-redirects` declares it (`:1720`), and eight other entries do. `check-landmarks.ts:81-86`
hard-exits when `dist/` is absent rather than self-skipping, so the local runner can schedule
it before `build:www` and produce a **false RED**, not a false green. Severity low; the fix is
one line each.

**5.2 `main.css:535-537` makes a false claim.** *"Every `--sp-*` alias follows from the
semantic tokens above"* — `--sp-bg-hero` (`:409`) and `--sp-bg-dark` (`:410`) reference
`--gray-950` / `--gray-900` directly. A future reader trusting that comment will assume the
solution-page palette flips with the theme. It does not. See defect 3.5(b).

**5.3 Desktop and mobile menus have drifted.** See 1.5.
