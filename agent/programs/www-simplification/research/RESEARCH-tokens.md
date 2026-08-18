# RESEARCH — design tokens, theme, typography, spacing

**Domain:** the foundational visual layer — color, theme, type, spacing, radii, borders,
shadows, motion.
**Author:** `sx-tokens`
**Date:** 2026-08-17
**Files I own when implementation starts:** the `:root` block in
`src/layouts/BaseLayout.astro`, `public/styles/main.css`, `public/styles/responsive.css`,
and the token-level parts of `src/styles/`.

All measurements taken against the running dev server (`http://localhost:4321`) at viewport
1440x900 unless stated. Every "ours" claim carries `file:line`; every "theirs" claim carries
a URL and a value read out of the live page with `eval` + `getComputedStyle`.

---

## 1. Verdict

We do not have a design system with drift; we have **four parallel token systems and no
enforcement**, and the drift is what you see. 229 custom properties are defined across five
locations, 20 more are referenced and never defined at all (so those declarations are dead),
and the numbers that actually ship bypass the tokens roughly half the time: 652 `font-size`
declarations use 94 distinct values against an 8-step scale, 1,607 spacing declarations use
53 distinct raw lengths against a 13-step scale, and 388 color declarations are hardcoded hex
against 660 that use a token. The single highest-leverage change is to **collapse to ONE
`:root` in `public/styles/main.css`, delete the shadowing copies (starting with the "critical
CSS" block at `BaseLayout.astro:279-414`), and cut the type scale to a claude.com-style
fixed ladder that every rule is then forced onto** — that one move deletes the drift's
cause rather than its symptoms. Dark mode is the clearest evidence of the cost: it flips
backgrounds correctly but never redefines the brand or semantic accents, so six of twelve
accent colors fail WCAG AA on the dark surface, and all 573 illustration SVGs stay light.

---

## 2. What we have

### 2.1 The real cascade — five places declare `:root`, and the last one wins

Measured order of style sources in the served document (`eval` over
`document.querySelectorAll('link[rel=stylesheet],style')` on `/en`):

| # | source | where |
|---|---|---|
| 0 | `/styles/main.css` | `BaseLayout.astro:237` |
| 1 | `/styles/responsive.css` | `BaseLayout.astro:238` |
| 2-4 | `search-modal.css`, `contact-modal.css`, `region-picker.css` | `BaseLayout.astro:240-242` (print/onload trick) |
| 5-11 | seven Astro-bundled `src/styles/*.css` blocks | component imports |
| **12** | **inline `:root` "critical CSS"** | **`BaseLayout.astro:279-414`** |
| 13-15 | skip-nav, pricing-page, astro-island | — |

The inline block at index 12 is **last**, has the same `(0,1,0)` specificity as every other
`:root`, and therefore **overrides `main.css` for all 17 properties it redeclares**
(`BaseLayout.astro:281-299`). Two consequences I measured live, not inferred:

- **`--font-family` in `main.css:79-80` is dead.** It reads
  `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`.
  The value the page actually computes is the `BaseLayout.astro:287` one, which inserts
  `'Oxygen', 'Ubuntu', 'Helvetica Neue'`. Verified: `getComputedStyle(document.documentElement)
  .getPropertyValue('--font-family')` returns the Oxygen/Ubuntu variant.
- **`responsive.css:71-74` is dead.** It sets `--max-width: 1400px` at `min-width: 90rem`.
  At a 1600px viewport the computed `--max-width` is **`1200px`** and `.container` measures
  **1200px**, because the later unconditional `:root` at `BaseLayout.astro:294` re-pins it.
  The wide-desktop layout rule has never fired.

Two more `:root` declarations exist beyond those: `src/styles/sidebar-shared.css:6-38`
(a 14-token `--sidebar-*` / `--link-*` / `--transition-speed` namespace) and
`src/components/AnnouncementBar.astro:32` (`--announcement-bar-height`, also written by an
inline script).

### 2.2 Four token namespaces, not one

| namespace | defined in | size | overlaps |
|---|---|---|---|
| `--color-*` / `--font-*` / `--space-*` … | `public/styles/main.css:61-274` | 144 declarations | canonical |
| the 17-property "critical" copy | `src/layouts/BaseLayout.astro:281-308` | 17 + 5 dark | shadows the above |
| `--sp-*` (solution pages) | `src/styles/solution-pages.css:2105-2124` | 7 + dark + OS-dark copy | parallel palette |
| `--sp-*` again (modal) | `src/styles/lead-magnet-modal.css:66-80, 304-317` | 5, duplicated twice | copy of the copy |
| `--sidebar-*` / `--link-*` | `src/styles/sidebar-shared.css:6-38` | 14 | aliases of `--color-*` |
| `--cs-*` (cheatsheet) | `src/styles/cheatsheet.css:13, 36` | own font-size + radius | parallel |

Counts (commands in §7): **229 distinct custom properties defined**, **220 referenced**,
**20 referenced-and-never-defined**.

### 2.3 The 20 undefined tokens are dead declarations, not fallbacks

`var(--undefined)` with no fallback makes the whole declaration invalid at computed-value
time, so the property resolves to `inherit`/`unset`. These are not degradations, they are
rules that silently do nothing:

```
--accent  --announcement-bar-height  --color-bg-hover  --color-bg-secondary
--color-heading  --color-info-text  --color-surface  --color-surface-alt
--color-text-muted  --color-text-primary  --color-text-tertiary  --font-mono
--radius-xs  --rb-accent  --resource-accent  --text-base  --text-lg
--text-secondary  --text-sm  --text-xs
```

Verified live: `getPropertyValue('--font-mono')`, `('--color-text-primary')` and
`('--radius-xs')` all return the empty string on `/en`.

Two of these are **visible bugs today**:

- `public/styles/main.css:2462` (`.metric-number`) and `main.css:2519` declare
  `font-family: var(--font-mono)`. The token is spelled `--font-family-mono`
  (`main.css:81`). Both rules do nothing, and those numbers render in Inter where
  JetBrains Mono was intended.
- `public/styles/region-picker.css:61,85,91,97,104,179,185` and
  `src/styles/pricing-page.css:1728` size text with `var(--text-lg|base|sm|xs)`. That
  family does not exist (ours is `--font-size-*`). Eight declarations inherit their parent's
  size instead.

`--color-text-primary` (5 uses), `--color-text-muted` (10), `--color-surface`,
`--color-bg-secondary`, `--color-heading` are a *different design system's* naming
convention that someone wrote against — evidence the token layer has no gate.

### 2.4 Typography

**Families.** Inter (400/500/600/700) and JetBrains Mono (400/700), self-hosted,
`@font-face` at `main.css:2-48`. Only Inter-Regular and Inter-SemiBold are preloaded
(`BaseLayout.astro:132-133`). Measured on `/en`: 4 weights render (400 x160, 600 x48,
700 x43, 500 x25) — so every shipped weight is used. Measured families on `/en`:
Inter x237, JetBrains Mono x28, **`monospace` x8, `sans-serif` x3** — the last two are
inline-SVG `<text>` elements that hardcode `font-family="sans-serif"` / `"monospace"`
and never touch the type system (**70 such attributes across 3 files**, e.g.
`src/components/PricingTrustSection.astro:56,78`). On `/en/pricing` the split is
Inter x342, `sans-serif` x32, `monospace` x27, **JetBrains Mono zero**.

**The size scale.** 8 tokens: `--font-size-xs` (a `clamp`), `sm .875rem`, `base 1rem`,
`lg 1.125rem`, `xl 1.5rem`, `2xl 2rem`, `3xl 2.5rem`, `4xl 3rem`
(`main.css:84-90, 229`). Against that:

| metric | value |
|---|---|
| `font-size` declarations in the codebase | **652** |
| distinct values used | **94** |
| distinct values that are NOT a `var()` | **81** |
| declarations that use a scale token | 350 (**54 %**) |
| distinct `clamp()` one-offs | **26** |
| distinct font sizes rendering on `/en` | **22** |
| on `/en/pricing` | **18** |
| on `/en` at 390px | **20** |

The 26 hand-rolled `clamp()`s are the tell — every author who wanted fluid type wrote
their own curve (`clamp(1.75rem, 3vw, 2.5rem)`, `clamp(2rem, 3.5vw, 3rem)`,
`clamp(2.25rem, 3.8vw, 3rem)`, `clamp(2.625rem, 4.2vw, 4rem)`, …) because the scale
offers no fluid steps.

**Heading hierarchy does not exist.** Measured on `/en`:

```
  1x  H1  56px/64.4px  w700  ls -1.68px
  2x  H2  36px/43.2px  w700  ls -0.72px
  1x  H2  40px/64px    w700  ls normal
  2x  H2  64px/102.4px w600  ls normal
  4x  H3  16px/25.6px  w600  ls 0.16px
  4x  H3  18px/28.8px  w600  ls normal
  3x  H3  20px/26px    w600  ls normal
  4x  H3  32px/40px    w700  ls normal
  4x  H4  14px/22.75px w600  ls 0.7px
```

Three sizes of H2 and **four sizes of H3, the smallest of which (16px) is smaller than the
18px body copy beside it**. Each section invented its own heading treatment.

**Line-height.** 6 `--leading-*` tokens (`main.css:232-237`). 195 `line-height`
declarations, 87 use a token (**45 %**), 18 distinct literal ratios ship
(1, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6, 1.65, 1.7, 1.8, …). **30 distinct computed
line-heights render on `/en`.**

**Letter-spacing.** 6 `--tracking-*` tokens (`main.css:240-245`). 75 declarations,
**10 use a token (13 %)**; the rest are raw (`-0.02em` x16, `0.05em` x11, `0.08em` x10,
`0.06em` x7, `0.12em` x5, `0.5px` x2 …). 11 distinct computed tracking values on `/en`.

**Measure (line length).** Uncapped. Measured on `/en`:

```
600px  fs=20px  max-width:600px   ~60ch
858px  fs=18px  max-width:none    ~95ch
1168px fs=18px  max-width:none   ~130ch
640px  fs=18px  max-width:none    ~71ch
```

One paragraph in the page has a `max-width`. A 130-character line is roughly double the
comfortable measure.

### 2.5 Color

| metric | value |
|---|---|
| color-ish declarations using a `var(--color-*)` | **660** |
| color-ish declarations with a **hardcoded hex** | **388** |
| distinct hardcoded hexes | **158** |
| distinct `rgba()` literals | **124** |
| distinct **green** hexes in CSS/markup | **19** (119 occurrences) |
| distinct green hexes in SVG assets | **8** (1,935 occurrences) |
| distinct text colors rendering on `/en` | **18** |
| distinct background colors on `/en` | **19** |

**The brand green is three different greens depending on where you look.** The token says
`--color-brand-primary: #556b2f` (`main.css:74`). The illustration assets overwhelmingly use
`#2d5227` (923 occurrences) and `#4a7c3f` (858) — **neither is any token value**. The
accent token is a fourth, `#7fa03f` (`main.css:183`), which is also pasted raw into three
components as an SVG `fill`/`stroke` 72 times (`PricingTrustSection.astro:38-78`,
`SPHomeNotASlice.astro`, `SPHomeWhyNow.astro`).

**Token families with near-zero return:**

| family | defined | `var()` uses |
|---|---|---|
| `--space-*` | 13 | 1,053 |
| `--radius-*` | 7 | 191 |
| `--opacity-*` | 21 | 104 |
| `--leading-*` | 6 | 87 |
| `--container-*` | 8 | 54 |
| `--z-*` | 9 | 21 |
| `--shadow-*` | 12 | 12 |
| `--tracking-*` | 6 | 10 |
| **`--breakpoint-*`** | **5** | **0** |

`--breakpoint-xs/sm/md/lg/xl` (`main.css:125-129`) cannot ever be used: CSS custom
properties are not valid inside `@media` conditions. Every media query in the tree hardcodes
`36rem`/`48rem`/`64rem`/`75rem`/`90rem`. Five permanently dead tokens.

The 21-strong `--opacity-*` family is not a design token family at all — it is a lookup
table mapping a number to itself (`--opacity-35: 0.35`), used to build `rgba()` strings.

**One syntax defect:** `main.css:173` opens a comment it never closes
(`--z-max: 9999; /* Accessibility elements (skip links`). The next `*/` is at the end of
line 175, so it swallows the "Extended Color Palette" heading and nothing else. I verified
both `--z-max` (`9999`) and `--color-bg-light` (`#f8f9fa`) still compute, so the impact is
cosmetic — but it is a broken comment sitting in the middle of the token block.

### 2.6 Theme (light/dark)

**Implementation:** an inline pre-paint script at `BaseLayout.astro:152-163` sets
`documentElement.dataset.theme` from `localStorage` then `prefers-color-scheme`, always
landing on `'light'` or `'dark'`. The toggle is a React island,
`src/components/ThemeToggle.tsx` (87 lines), mounted at `Navigation.tsx:241`.
Dark values live in `main.css:278-320` (43 declarations), duplicated verbatim into an OS
fallback at `main.css:322-355`, with a third partial copy of 5 properties at
`BaseLayout.astro:302-308`.

**It is half-built, and here is the measurement.** The dark block redefines backgrounds,
text, borders, overlays, shadows and gradients. It redefines **no brand or semantic accent**.
Contrast ratios computed live against the two dark surfaces:

| token | value | vs `#0f0f10` | vs `#1a1a1b` |
|---|---|---|---|
| `--color-brand-primary` / `--color-primary` | `#556b2f` | 3.22 | **2.92** |
| `--color-brand-secondary` | `#4c6029` | 2.75 | **2.49** |
| `--color-brand-dark` | `#3d5217` | 2.21 | **2.00** |
| `--color-error` | `#c41e3a` | 3.28 | **2.98** |
| `--color-link-blue` | `#0066cc` | 3.44 | **3.12** |
| `--color-brand-bolt` | `#dc2626` | 3.97 | **3.60** |
| `--color-accent-green` | `#7fa03f` | 6.39 | 5.80 |
| `--color-success` | `#28a745` | 6.12 | 5.55 |
| `--color-warning-text` | `#ffc107` | 11.75 | 10.67 |
| `--color-status-blue` | `#60a5fa` | 7.54 | 6.84 |
| `--color-status-red` | `#f87171` | 6.93 | 6.29 |

**Six of twelve fail WCAG AA (4.5:1) on the dark surface; three fail even the 3:1 large-text
floor.** The brand green — the color a CTA is painted in — is 2.92:1 in dark mode.

**The OS fallback block is dead in practice.** `:root:not([data-theme])` can only match
before the inline script at `BaseLayout.astro:152` runs, i.e. sub-millisecond, or with JS
off. That accounts for ~55 duplicated declarations across `main.css:322-355`,
`solution-pages.css:2115-2124`, `lead-magnet-modal.css:73-80` and `:311-317`.

**Toggle bug.** `ThemeToggle.tsx:5-11` returns `'light'` when `data-theme` is absent. With JS
enabled the init script guarantees it is present, so this is latent — but the component's own
default disagrees with the page's, and it is one more copy of the theme decision.

**Above the fold, the toggle changes almost nothing.** Screenshots
`shots/sx-tokens/ours-home-light-1440.png` and `ours-home-dark-1440.png` are visually
identical except the nav bar: the homepage hero is hardcoded dark in both themes. A user who
clicks the moon on the landing page sees a 56px strip change color.

**Below the fold, dark mode breaks visibly.** `ours-home-dark-y2400.png` shows the two
"Difference" illustrations as bright white slabs with black text on the dark page. Cause:
they are external files loaded via `<img>` (`/assets/images/problem.svg`,
`/assets/images/solution.svg`, `src/assets/images/illustrations/*.svg`), so page CSS cannot
reach them, and **573 of the 577 SVG assets carry an opaque light background rect** (e.g.
`problem.svg:5` — `<rect width="800" height="450" fill="#f5f5f5"/>`). The DOM itself is
clean: an `eval` sweep for light-background boxes ≥30,000px² in dark mode returns **0**.
The illustrations are the entire problem.

### 2.7 Spacing, radii, shadows, motion

**Spacing.** 13 `--space-*` tokens (`main.css:99-111`), plus `--section-padding`,
`--box-padding`, `--grid-gap`, `--grid-gap-lg` and 8 `--container-*`.

| metric | value |
|---|---|
| padding/margin/gap declarations | **1,607** |
| declarations containing no `var()` at all | **747 (46 %)** |
| distinct raw length literals used in them | **53** |
| distinct computed padding values on `/en` | **19** |
| distinct computed gap values on `/en` | **10** |

**Section vertical rhythm is ad hoc.** Measured on `/en`:

```
sp-hero             48/48       logo-wall           32/32
sp-why-now          96/96       sp-not-a-slice      96/96
home-difference     64/64       metrics-bar         48/48
integrations-strip  48/48       cf-pricing-section  80/80
closing-cta         64/64
```

Five distinct section paddings (32/48/64/80/96) on one page, none derived from the
`--section-padding: 5rem 0` token that exists at `main.css:133`.

**Radii.** 7 `--radius-*` tokens plus a legacy `--box-border-radius: 15px` (`main.css:148`).
307 `border-radius` declarations, **34 distinct values**, of which the token-bypassing ones
include `12px` (x22), `8px` (x11), `6px` (x8), `100px`, `9999px` (a raw duplicate of
`--radius-full`), `15px`, `3px`, `1px`, `2px`. 9 distinct radii render on `/en`, 7 on
`/en/pricing`.

**Shadows.** 12 shadow tokens (`--shadow-sm/md/lg/xl` + `--box-shadow`, each redefined in
dark). 65 `box-shadow` declarations, **20 use a token (31 %)**, 16 distinct hand-written
shadows. 6 distinct shadows render on `/en`.

**Motion.** 3 duration tokens with a `prefers-reduced-motion` zeroing block
(`main.css:160-162, 365-370`) — the one part of the token layer that is properly built.
But 90 `transition` declarations produce **41 distinct shorthand values**, and 30 of them
hardcode a duration (`0.15s` x19, `0.2s` x8, `200ms`, `120ms`, `0.1s`) — those bypass the
reduced-motion zeroing entirely and rely on the `!important` catch-all at
`main.css:373-380`. `--transition-speed` (`sidebar-shared.css:37`) is a fifth alias.

### 2.8 Payload

| | |
|---|---|
| `public/styles/*.css` served | **104,987 bytes** (main.css alone 77,113) |
| `src/styles/*.css` on disk | **195,182 bytes** |
| inline `<style>` in `.astro` | **3,585 lines across 29 files** |
| **total hand-written CSS** | **~300 KB / ~17,100 lines** |
| stylesheet sources in the `/en` document (dev) | **16** (5 `<link>` + 11 `<style>`) |

---

## 3. What claude.com and anthropic.com do

Measured by a sub-agent with the identical audit script, viewport 1440x900, each page
scrolled to the bottom and back before measuring so lazy sections mount.

### 3.1 The headline numbers

| metric | claude.com/ | claude.com/pricing | www.anthropic.com/ |
|---|---|---|---|
| visible elements | 549 | 2,011 | 712 |
| **distinct font sizes** | **13** | **13** | **8** |
| distinct font weights | 5 | 4 | 4 |
| distinct font families | 2 | 2 | 3 |
| distinct line-heights | 20 | 16 | **12** |
| distinct letter-spacings | 2 | 3 | 4 |
| **distinct text colors** | **7** | 10 | **7** |
| **distinct background colors** | **7** | 10 | **5** |
| distinct radii | 6 | 9 | **4** |
| **distinct shadows** | 5 | 6 | **0** |
| distinct paddings | 12 | 10 | 10 |
| distinct gaps | 11 | 12 | 7 |
| `:root` custom properties | 178 | 216 | 282 |
| stylesheet sources | 6 | 86 | 13 |

anthropic.com is the tightest system of the three: **8 font sizes, 4 weights, 7 text
colors, 5 backgrounds, 4 radii, and zero box-shadows on the entire page.**

### 3.2 What their token systems contain that ours does not

- **A named grey ramp with 21 steps.** `--color-gray-000 … -1000`
  (`#fff #faf9f5 #f5f4ed #f0eee6 #e8e6dc #dedcd1 #d1cfc5 #c2c0b6 #b0aea5 #9c9a92 #87867f
  #73726c #5e5d59 #4d4c48 #3d3d3a #30302e #262624 #1f1e1d #1a1918 #141413 #000`).
  Everything greyscale on the page is one of those 21 values. We have `--color-bg`,
  `-bg-alt`, `-bg-light`, `-bg-lighter`, `-bg-dark`, `-bg-darker`, `-border`, `-hover`,
  `-text`, `-text-secondary` — ten ad-hoc greys plus 158 hardcoded hexes.
- **A semantic layer that aliases the ramp**, and is the only thing components touch:
  `--theme-background-primary/-secondary/-tertiary`,
  `--theme-foreground-primary/-secondary/-tertiary`,
  `--theme-border-primary/-secondary/-tertiary`, `--theme-accent-clay-*`, and per-variant
  button token sets (`--theme-button-primary-bg/-fg/-font-weight`, ×4 variants). We have
  raw palette tokens and no semantic layer, which is exactly why 20 semantic-sounding names
  (`--color-surface`, `--color-text-primary`) were invented ad hoc and never defined.
- **A fluid type scale where every step is a `clamp()` shipped as a token**, so nobody
  hand-rolls one: `--display-1: clamp(42px, 33.429px + 2.679vw, 72px)` down through
  `--headline-1…6`, `--body-large-1/2`, `--body-1/2/3`, `--caption`, `--micro` — each with
  a paired `--*-line-height`. 15 steps, and the page renders 13 sizes. We define 8 fixed
  steps, and 26 authors wrote 26 different `clamp()`s.
- **A line-height ladder as tokens** (`--line-height-tight 1 / -tighter 1.1 / -snug 1.2 /
  -normal 1.3 / -relaxed 1.5 / -loose 1.6 / -looser 1.7`) — we have the same idea
  (`--leading-*`) and use it 45 % of the time.
- **Measure tokenised in `ch`:** `--text-width-narrow 20ch / -headline 30ch / -title 45ch /
  -body 60ch / -wide 70ch / -prose 80ch`. Measured body column on claude.com/ is
  **660px at 17px/27.2px ≈ 72 characters**; anthropic.com's hero deck is capped by a
  `u-max-width-40ch` utility computing to **594.244px**. Ours runs to **130ch**.
- **Section rhythm as a token with few steps:** `--section-spacing-sm 64 / -md 96 /
  -main 128 / -lg 200 / -page-top 240`. claude.com/'s sections measure a symmetric
  **128px/128px**. Ours: five different values on one page, none tokenised.
- **Elevation is not a design axis.** 11 of the 12 shadow variants across the two
  claude.com pages are `0 0 0 0` + `0 0 0 1px` *rings* used as borders (so hover ring-width
  changes cause no layout shift). Only two are real drop shadows, both at
  `rgba(0,0,0,0.016)` and `rgba(0,0,0,0.05)`. anthropic.com ships **zero** shadows and
  expresses depth purely by swapping between four background values.
- **Motion tokens are easing curves, not durations:** `--ease-in-out-expo`,
  `--ease-out-quart`, `--ease-expo-out: cubic-bezier(0.16,1,0.3,1)` etc.

### 3.3 The anthropic.com hero "special component"

Structurally it is a per-word staggered reveal: the `<h1>` is split into 10
`span.animate-word` + 9 `span.animate-space`, each `inline-block` with
`opacity:0; transform:translateY(24px)` and
`transition: opacity 800ms cubic-bezier(0.16,1,0.3,1), transform 800ms …`. JS writes a
**randomized per-word `transition-delay` re-rolled on every load** (measured across two
loads: "AI" 325ms then 448ms; "products" 280ms then 149ms), so the words pop in scattered
order rather than left-to-right. No canvas, no WebGL, no SVG, no video, no `@keyframes` —
`getAnimations({subtree:true})` returns 0.

The craft is in the two details around it: a `span.u-sr-only` carries the full unsplit
sentence (links intact) so assistive tech reads one sentence, `span.animate-word
{ text-decoration: inherit }` keeps the 4.87px underline continuous across the split, and a
`prefers-reduced-motion` block disables the whole thing. Headline computes to **60.87px
`Anthropic Sans` w700, line-height 66.95px (1.1), `text-wrap: balance`** — the ragged
3-line break is browser-balanced, not hand-broken. (Full detail is in the sub-agent's
report; the hero belongs to whichever specialist owns the homepage — I record it here only
because the token values are mine.)

---

## 4. The delta

| dimension | ours | claude.com | anthropic.com | gap |
|---|---|---|---|---|
| distinct font sizes rendered | **22** (`/en`), 18 (`/en/pricing`) | 13 | **8** | **2.8× anthropic** |
| distinct font-size values in source | **94** (81 non-token) | — | — | scale is decorative |
| type scale steps defined | 8 fixed | 15 fluid (`clamp` tokens) | 18 fluid | no fluid steps → 26 hand-rolled `clamp()`s |
| distinct line-heights rendered | **30** | 20 | **12** | 2.5× |
| distinct letter-spacings rendered | **11** | **2** | 4 | 5.5× |
| heading sizes per level | H2 ×3, H3 ×4 | one per level | one per level | no hierarchy |
| distinct text colors rendered | **18** | **7** | **7** | 2.6× |
| distinct background colors | **19** | **7** | **5** | 3.8× |
| hardcoded hex in source | **158 distinct / 388 uses** | ramp only | ramp only | — |
| brand-color variants (green) | **19** in CSS + **8** in assets | 3 clay values | 2 clay values | the brand is 27 colors |
| semantic color layer | **none** (20 invented, undefined) | `--theme-*` | `--_color-theme---*` | the missing layer |
| distinct radii rendered | 9 | 6 | **4** | 2.2× |
| distinct shadows rendered | 6 | 5 | **0** | elevation is not a system |
| section vertical rhythm | 5 values, untokenised | **128/128** from one token | spacer divs, 3 heights | — |
| body measure | up to **130ch** | **72ch** (660px) | **40ch** (594px) | ~2× too wide |
| spacing declarations with no token | **747 / 1,607 (46 %)** | — | — | — |
| `:root` blocks that can win | **5** | 1 | 1 | the root cause |
| undefined tokens referenced | **20** | 0 functional (3 Webflow orphans, unreferenced) | 5 orphans, unreferenced | dead declarations |
| dark theme | accents unchanged, **6/12 fail AA** | (light only) | (light only) | half-built |

Two honest notes on this table. First, claude.com/pricing is *their* worst page (9 radii
including `8.5px`/`7.5px`/`9.6px` sub-pixel leftovers, 10 text colors) — restraint decays
with page density for them too, just from a much better floor. Second, their `:root` counts
(178/216/282) are *larger* than ours; the difference is not how many tokens exist, it is
that theirs are a closed ramp plus a semantic alias layer that components are actually
confined to, while ours are a suggestion.

---

## 5. Proposed simplification

Ordered by leverage. "Prove it" is the measurement I would re-run after the change; every
one of them has a before-number recorded above, so each is falsifiable.

### 5.1 One `:root`. Delete the shadowing copies. *(highest leverage)*

**Change.** Make `public/styles/main.css:61-274` the only unconditional `:root` in the
project. Delete the "critical CSS variables" block at `BaseLayout.astro:281-308` entirely
(both the light and the partial dark copy). Fold `--nav-top-offset` (currently only defined
there, `BaseLayout.astro:296`) into `main.css`. Move `sidebar-shared.css:6-38` and
`cheatsheet.css:13,36` to class-scoped blocks rather than `:root`.

**Files.** `src/layouts/BaseLayout.astro` (−34 lines), `public/styles/main.css`,
`public/styles/responsive.css`, `src/styles/sidebar-shared.css`, `src/styles/cheatsheet.css`.

**Delete:** 22 duplicate token declarations, the dead `responsive.css:71-74` `--max-width`
override (or reinstate it deliberately — see §7), and the broken comment at `main.css:173`.

**Risk.** Medium, and specific: the inline block exists to avoid a flash of unstyled hero
before `main.css` parses. `main.css` is already `<link rel="preload" as="style">`ed at
`BaseLayout.astro:136` and is a render-blocking `<link>`, so the tokens are available before
first paint regardless — but this must be checked with a throttled load, not asserted.
The `--font-family` value also *changes* (Oxygen/Ubuntu drop out), which is the correct
outcome but is a real rendering change on Linux.

**Prove it.** `getPropertyValue('--max-width')` at a 1600px viewport returns `1400px` (today:
`1200px`), and `--font-family` matches `main.css:79` exactly. Screenshot diff at
1440x900 and 390x844 shows no layout change. Count of `:root` blocks that can match
`document.documentElement` drops from 5 to 1.

### 5.2 Fix, then delete, the 20 undefined tokens

**Change.** Three buckets. (a) **Rename at the call site**: `var(--font-mono)` →
`var(--font-family-mono)` (`main.css:2462, 2519`); `var(--text-lg|base|sm|xs)` →
`var(--font-size-*)` (`region-picker.css:61,85,91,97,104,179,185`,
`pricing-page.css:1728`); `var(--radius-xs)` → `var(--radius-sm)`. (b) **Define once, in
the new semantic layer** (§5.3): `--color-surface`, `--color-surface-alt`,
`--color-text-primary`, `--color-text-muted`, `--color-text-tertiary`,
`--color-bg-secondary`, `--color-bg-hover`, `--color-heading`, `--color-info-text`. (c)
**Delete the caller**: `--accent`, `--rb-accent`, `--resource-accent`, `--text-secondary`
are single-component leftovers.

Also delete `--breakpoint-xs…xl` (`main.css:125-129`) — 5 tokens with 0 uses that are
unusable by construction.

**Files.** `public/styles/main.css`, `public/styles/region-picker.css`,
`src/styles/pricing-page.css`, `src/layouts/DocsLayout.astro:848-858`.

**Risk.** Low, but each fix makes a currently-inert declaration take effect, so a handful of
elements will visibly change (that is the point — `.metric-number` becomes monospace).

**Prove it.** A script that extracts every `var(--x)` and every `--x:` and diffs them
reports **zero** referenced-but-undefined properties. This is the check to keep as a gate
(§5.7): it is the one measurement that would have caught all 20 at authoring time.

### 5.3 Add the semantic layer, and cut the palette to a ramp

**Change.** Adopt the claude.com shape: a closed greyscale ramp
(`--gray-0 … --gray-1000`, ~11 steps is enough for us) plus **one** brand green and **one**
interactive/hover green, then a semantic alias layer that is the only thing rules are
allowed to reference:

```
--surface-primary / -secondary / -tertiary
--text-primary / -secondary / -tertiary
--border-primary / -secondary
--accent / --accent-hover
--status-success / -error / -warning / -info
```

Dark mode then becomes a **redefinition of the semantic layer only** — which is precisely
the block that is missing today and the reason six accents fail AA.

Pick one green and retire the rest. Today: `#556b2f` (token), `#4c6029`, `#3d5217`,
`#7fa03f` (accent token), `#4a7c3f` + `#2d5227` (the assets' greens), plus 13 more in CSS.

**Files.** `public/styles/main.css` (the palette and both theme blocks),
`src/styles/solution-pages.css:2105-2124` (delete the `--sp-*` namespace, map to semantic),
`src/styles/lead-magnet-modal.css:66-80, 304-317` (delete the duplicated copies),
`src/styles/sidebar-shared.css:11-24`.

**Delete:** the `--sp-*` namespace and its two duplicate dark blocks (~24 declarations), the
`--sidebar-*`/`--link-*` aliases (14), and the 21-member `--opacity-*` family — with a
semantic layer, `color-mix()` or a `rgb(from …)` does the job and the numbers stop being
tokens.

**Risk.** High, and this is the one to plan properly. It touches 660 `var(--color-*)` call
sites. It should be one mechanical rename pass (old token → semantic alias) with the old
names kept as aliases *inside a single commit only*, never shipped as a compatibility layer.

**Prove it.** Distinct text colors rendered on `/en` drops from 18 toward ≤10; distinct
backgrounds from 19 toward ≤7; the dark-mode contrast table in §2.6 shows every accent
≥4.5:1. Re-run the same `eval` audit on `/en`, `/en/pricing` and one solution page.

### 5.4 Replace the type scale with a fluid ladder, and fix the heading hierarchy

**Change.** Ship the scale as `clamp()` tokens with paired line-heights, claude.com-style —
roughly `--display`, `--h1…--h4`, `--body-lg`, `--body`, `--body-sm`, `--caption` (9-10
steps), each with `--*-line-height`. Then set `h1…h4` **once** globally from those tokens
and delete every per-section heading size override. Add measure tokens
(`--measure-body: 65ch`, `--measure-narrow: 45ch`) and apply `--measure-body` to prose
containers.

**Files.** `public/styles/main.css` (scale + global heading rules),
`src/styles/solution-pages.css`, `src/styles/pricing-page.css`,
`public/styles/responsive.css:79-83` (the `.section-title: 4rem` override), plus the inline
`<style>` blocks — most of the 26 hand-rolled `clamp()`s live there, which is a
cross-domain dependency (§6).

**Delete:** all 26 bespoke `clamp()` expressions, the ~81 raw font-size literals in
component CSS, `responsive.css:79-83`.

**Risk.** Medium-high — this is the change users see. Every heading resizes. Best done as
one pass with before/after screenshots of the top 10 pages.

**Prove it.** Distinct rendered font sizes on `/en` drops from 22 to ≤12 and on
`/en/pricing` from 18 to ≤12; distinct line-heights from 30 to ≤8; the heading census
(§2.4) shows exactly one size per level; the widest paragraph measures ≤75ch (today 130ch).

### 5.5 One section-rhythm token, one radius set, delete the shadow scale

**Change.** Define `--section-space: clamp(4rem, …, 8rem)` and `--section-space-sm`, and
set every section's vertical padding from them (today: 32/48/64/80/96 on one page). Collapse
radii to four (`--radius-sm/md/lg/full`), delete `--box-border-radius: 15px`,
`--radius-none`, `--radius-2xl`, `--radius-xl`, and rewrite the 34 distinct
`border-radius` values onto them. Delete `--shadow-sm/md/lg/xl` and their dark
counterparts — 12 tokens for 12 uses — and express elevation the way both reference sites
do: a background swap plus a 1px border, with at most one real drop shadow token kept for
modals.

**Files.** `public/styles/main.css:146-149, 247-260, 309-314`, `src/styles/*.css`.

**Delete:** 8 radius/shadow tokens, ~16 hand-written box-shadows, `--grid-gap` /
`--grid-gap-lg` (aliases of `--space-10`/`--space-16`), and the unused half of
`--container-*` (8 defined, 54 uses across a 600-1800px range — 4 is plenty).

**Risk.** Low-medium. Shadow removal is the most visible; it is also the change that most
directly buys the "simple like claude.com" look the operator asked for.

**Prove it.** Distinct rendered radii on `/en` drops from 9 to ≤5; distinct shadows from 6
to ≤2; distinct computed padding values from 19 to ≤10; section paddings on `/en` take at
most 2 distinct values.

### 5.6 Make dark mode real, or make it a single stylesheet

**Change.** Once §5.3 lands, dark mode is one block redefining ~15 semantic aliases —
including the accents, which is the actual fix. Then **delete the
`@media (prefers-color-scheme: dark) { :root:not([data-theme]) … }` duplicates**
(`main.css:322-355`, `solution-pages.css:2115-2124`, `lead-magnet-modal.css:73-80, 311-317`,
~55 declarations): the init script at `BaseLayout.astro:152-163` always stamps
`data-theme`, so they are unreachable with JS on, and the no-JS path already has a broken
toggle. Delete the partial dark copy at `BaseLayout.astro:302-308`. Replace the React
`ThemeToggle` island with the same button in Astro plus a 6-line inline script — it holds
one boolean and ships React for it.

**Files.** `public/styles/main.css`, `src/layouts/BaseLayout.astro`,
`src/components/ThemeToggle.tsx` (delete), `src/components/Navigation.tsx:241`,
`src/styles/solution-pages.css`, `src/styles/lead-magnet-modal.css`.

**Risk.** Low for the CSS; the `ThemeToggle` → Astro swap lands in the components
specialist's territory (§6).

**Prove it.** The §2.6 contrast table with every row ≥4.5:1; `grep -c data-theme` across the
tree drops from 29 to ~2; the light/dark screenshot pair at y=2400 differs in every region
rather than only the nav.

### 5.7 Add the gates that would have prevented all of this

There is precedent in this repo — `scripts/check-cta-bolt-uniqueness.js` already guards the
bolt-red accent (`main.css:117-120`). Three more, wired into `npm run ci`:

1. **No undefined custom property.** Extract `var(--x)` vs `--x:` and fail on the
   difference. Would have caught all 20 in §2.3.
2. **No raw hex outside the palette block.** Allow hex only inside the `:root` in
   `main.css`; everything else uses a token. Today that gate would report 388 violations,
   so it lands last, after §5.3.
3. **No raw `font-size` outside the scale.** Same shape. Today: 302 violations.

Each gate must be proven able to FIRE before it is trusted — introduce one deliberate
violation, watch it fail, remove it. A gate that has never gone red is not a gate.

---

## 6. Cross-domain consequences

Named, not touched.

- **Illustration assets are theme-blind.** 573 of 577 SVGs under `public/assets/images/`
  and `src/assets/images/` hardcode a light background rect (`problem.svg:5`:
  `<rect width="800" height="450" fill="#f5f5f5"/>`), and they are loaded via `<img>`, so
  no token can reach them. In dark mode they render as white slabs
  (`shots/sx-tokens/ours-home-dark-y2400.png`). They also carry **8 green shades that are
  not in the palette**, dominated by `#2d5227` (923 uses) and `#4a7c3f` (858) — neither is
  any token value. Fixing this means either inlining the SVGs so `currentColor` works, or
  regenerating them from the palette. **Whoever owns illustrations/assets.**
- **70 inline-SVG `font-family="sans-serif"` / `"monospace"` attributes** across
  `PricingTrustSection.astro`, `SPHomeNotASlice.astro`, `SPHomeWhyNow.astro` — text in those
  diagrams renders in the OS default, not Inter/JetBrains Mono (measured: 32 `sans-serif` +
  27 `monospace` elements on `/en/pricing`). Same three files paste `#7fa03f` raw 72 times.
  **Components specialist.**
- **The homepage hero is hardcoded dark in both themes**, so the theme toggle changes only
  the nav above the fold. **Homepage specialist.**
- **Most of the 26 bespoke `clamp()` font sizes and much of the 46 % untokenised spacing
  live in component-local `<style>` blocks** — 3,585 lines across 29 `.astro` files (the
  brief's figure of 14 counts only `src/components`). §5.4 and §5.5 cannot complete without
  those files being edited by their owners; I can supply the token mapping.
- **`ThemeToggle.tsx` is a React island for one boolean**, and `Navigation.tsx:241` mounts
  it. Converting it to Astro is a components-specialist call; the CSS side is mine.
- **`src/styles/pricing-page.css` (2,321 lines) and `solution-pages.css` (2,616 lines)** are
  40 % of the CSS and the densest source of token bypasses. They belong to the pricing and
  solution-page specialists; the `--sp-*` namespace inside `solution-pages.css:2105-2124` is
  the token-layer part and I would take that.
- **Housekeeping, not mine to fix:** three untracked screenshots from concurrent sessions
  are sitting in `packages/www/` — `docs-quickstart-mid.png`, `docs-quickstart-top.png`,
  `pricing-desktop-top.png`. They match the `sx-docs` / `sx-pricing` naming. Mine are all in
  `scratchpad/shots/sx-tokens/`. Their owners should move them before any commit.

---

## 7. Open questions for the operator

1. **Keep the olive green, or move to a warmer neutral-plus-one-accent palette?** The
   reference sites are a 21-step grey ramp plus a single clay accent used sparingly. Ours is
   olive `#556b2f` — which is the one token that fails hardest in dark mode (2.92:1) and
   forced the invention of a brighter `#7fa03f` for dark contexts. A darkened-surface/
   lightened-accent pair fixes it without changing the brand; changing the brand hue is a
   decision I will not make.
2. **Is `--max-width: 1400px` at ≥1440px wanted?** `responsive.css:71-74` asks for it and
   has never worked. Fixing the cascade turns it on. claude.com caps at 1440px,
   anthropic.com at 1432px — so the intent is defensible, but it is a live layout change on
   wide screens and I would rather confirm than surprise.
3. **Does no-JS need to work?** Deleting the `prefers-color-scheme` fallback blocks removes
   ~55 duplicated declarations. With JS off today the theme toggle does nothing anyway, so
   the fallback buys a correct-looking page with a dead button. My default if unanswered:
   **delete them** (clean break, no compatibility theater), and keep dark mode a
   JS-set `data-theme` feature.

---

## 8. Evidence appendix — commands

```bash
cd packages/www

# distinct font-size values / declarations
grep -rhoE 'font-size:[^;}]+' src/styles public/styles src/components src/layouts src/pages \
  | sed 's/font-size: *//;s/ *!important//' | sort | uniq -c | sort -rn        # 652 decls, 94 values

# hardcoded hex in colour-bearing properties
grep -rhoE '(color|background|background-color|border|border-color|fill|stroke|box-shadow|outline|--[a-z0-9-]+)\s*:[^;}]*#[0-9a-fA-F]{3,8}' \
  src/styles public/styles src/components src/layouts src/pages \
  | grep -oE '#[0-9a-fA-F]{3,8}\b' | tr 'A-F' 'a-f' | sort | uniq -c | sort -rn   # 158 distinct / 388

# token-based colour declarations
grep -rhoE '(^|[^-])(color|background|background-color|border-color|fill|stroke):[^;}]*var\(--color' \
  src/styles public/styles src/components src/layouts src/pages | wc -l           # 660

# referenced-but-never-defined custom properties
comm -13 \
  <(grep -rhoE '^\s*--[a-z0-9-]+\s*:' src/styles public/styles src/components src/layouts src/pages | tr -d ' :' | sort -u) \
  <(grep -rhoE 'var\(\s*--[a-z0-9-]+' src/styles public/styles src/components src/layouts src/pages | grep -oE '\-\-[a-z0-9-]+' | sort -u)   # 20

# spacing declarations without any token
grep -rhoE '(padding|margin|gap|row-gap|column-gap)(-[a-z-]+)?:[^;}]+' \
  src/styles public/styles src/components src/layouts src/pages \
  | sed -E 's/^[a-z-]+: *//' | grep -cv 'var('                                    # 747 of 1607

# SVG assets with an opaque light background
grep -rlEi '(rect[^>]*fill="(#f|#e|white))' public/assets/images src/assets/images --include=*.svg | wc -l   # 573 of 577
```

Live-page audits (viewport 1440x900, `AGENT_BROWSER_SESSION=sx-tokens`) used the script at
`scratchpad/audit.js`; it enumerates every visible element under `<body>` and counts distinct
computed values per property.

### Screenshots

| path | what |
|---|---|
| `scratchpad/shots/sx-tokens/ours-home-light-1440.png` | `/en` light, above fold — hero is dark |
| `scratchpad/shots/sx-tokens/ours-home-dark-1440.png` | `/en` dark, above fold — differs only in the nav |
| `scratchpad/shots/sx-tokens/ours-home-light-y2400.png` | `/en` light at y=2400 |
| `scratchpad/shots/sx-tokens/ours-home-dark-y2400.png` | `/en` dark at y=2400 — **white illustration slabs** |
| `scratchpad/shots/sx-tokens/ours-home-light-390.png` | `/en` mobile (20 distinct font sizes) |
| `scratchpad/shots/sx-tokens-ref/claude-home-top.png` | claude.com/ |
| `scratchpad/shots/sx-tokens-ref/claude-pricing-top.png` | claude.com/pricing |
| `scratchpad/shots/sx-tokens-ref/anthropic-home-top.png` | www.anthropic.com/ |

(`scratchpad` = `/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad`)
