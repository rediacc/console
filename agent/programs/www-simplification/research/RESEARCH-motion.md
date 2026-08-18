# RESEARCH — icons, illustrations, motion

Specialist: `sx-motion`. Date: 2026-08-17. **Nothing in `packages/www` was modified**
(`git status --porcelain packages/www` → empty at start and at end).
Screenshots: `/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-motion/`
Browser session `sx-motion`, agent-browser 0.34.0, 1440x900.

---

## 1. Verdict

Our icons are **stroked**, theirs are **filled** — that one decision is the whole icon
delta: 121 hand-inlined SVGs across 4 unrelated sources give us **9 stroke weights, 10
viewBoxes and 10 rendered sizes**, while claude.com's 51 icons have **zero stroke-width
values, two grids and two sizes**, because a filled path has nothing to disagree about.
Our 573 illustrations bake their labels as `<text>` in **seven font stacks, none of which
is Inter**, which is both why they read as stock clipart and why there are 26 files per
drawing (13 locales x 2 viewports) to translate **92 English words**. On motion the
finding is the opposite of what I expected: we are not missing a reveal system — `.reveal`
+ `.reveal-stagger` + a one-shot IntersectionObserver already ship on **every page**
(`public/styles/main.css:3348-3387`, `public/scripts/scroll-reveal.js`), and they are used
on **8 elements, all below y=3731 px**, with `.reveal-stagger` used **zero times anywhere**.
Measured at load, our homepage runs **0 animations**; anthropic.com peaks at **22
concurrent**, all of them `opacity` + `transform`, all finished by **1,350 ms**. The single
highest-leverage change is therefore **adopt what we already own** — put `.reveal` on the
sections above the fold, add a word-level variant for the h1 — and **convert the icon set
to one filled 20x20 grid**, which deletes 9 stroke weights, 3 duplicate check marks and the
5 competing `stroke-width` rules in `solution-pages.css` in one move.

---

## 2. What we have

### 2.1 The icon system — four sources, no shared primitive

There is **no icon library, no sprite, no icon font.** `grep -inE
"lucide|heroicon|react-icons|feather|iconify|phosphor|tabler|font-awesome" package.json` →
none; `grep -rn "<use\b\|<symbol" src --include='*.astro' --include='*.tsx'` → **0**.
`public/fonts/` holds only `inter/` and `jetbrains-mono/`. **100 % of icons are
hand-inlined.**

| Source | Icons | Shape | viewBox | stroke-width | fill / stroke | size |
|---|---:|---|---|---|---|---|
| `src/components/solution-pages/icons.ts` (104 L) | **43 keys / 40 distinct glyphs** | `Record<string,string>` of raw markup, injected via `<Fragment set:html>` | `0 0 24 24` x42, `0 0 16 16` x1 (`:95`) | attr on only 18 children: `2` x17, `2.5` x1 (`:14`); **25 icons carry none** | `stroke="white"` x16 (theme-blind), `fill="rgba(255,255,255,0.15)"` x8 | 1 of 43 has `width`/`height` |
| `src/components/CategoryIcons.tsx` (91 L) | 6 | `React.FC` | `0 0 20 20` (`:13`) | **`1.75`** (`:16`); 2 dots override to `0` (`:55,:76`) | `fill:none`, `stroke:currentColor` | `size=18` default |
| `src/components/icons/PlatformIcons.tsx` (26 L) | 3 | `React.FC` | `0 0 24 24` | **none — filled** | `fill="currentColor"` | `14 x 14` hardcoded |
| `src/components/icons/ClipboardIcons.tsx` (34 L) | 2 | `React.FC` | `0 0 24 24` | `2` (`:10`) and **`3`** (`:27`) | `fill:none`, `stroke:currentColor` | `16 x 16` |

Four sources, four grids, four stroke conventions. `icons.ts` is the closest thing to a
library and it is the worst offender: 25 of its 43 icons declare **no** stroke width, so the
weight is decided by whichever of these five rules wins —
`src/styles/solution-pages.css:420` (`2`), `:714` (`2`), `:917` (`1.5`), `:1143` (`2`),
`:1452` (`2`). The same glyph renders at a different weight depending on the section it
lands in. It also contains three byte-identical pairs (`copy`/`layers`, `bolt`/`bolt-arrow`,
`arrow-right-circle`/`arrow-right-circle-nav`), so 43 keys buy 40 glyphs, for **6 call
sites** from 3 importers (`SPBenefits.astro:29`, `SPStatsBar.astro:22`,
`SPHowItWorks.astro:76,109,166,201`).

**Distributions across all 121 inline `<svg>` (37 files).** Command:
`grep -rno "<svg" src --include='*.astro' --include='*.tsx' --include='*.ts' | wc -l` →
**121**; `-rl | wc -l` → **37**. (Both numbers confirm `sx-primitives`. Caution: dropping
the `--include` filters returns 642/558 because the 521 `.svg` *assets* live under `src/` —
any "inline SVG" figure in the 550-650 range is that mistake.)

| Dimension | Distinct | Distribution |
|---|---:|---|
| viewBox | **10** | `24 24` x79 · `20 20` x15 · `16 16` x11 · `400 280` x6 · `140 100` x4 · `160 120` x3 · `200 120` x1 · `120 120` x1 · `68 48` x1 |
| stroke-width | **9** numeric + "none" | none x50 · `2` x42 · `1.5` x15 · `1.75` x10 · `2.5` x6 · `1` x6 · `3` x4 · `1.25` x3 · `0` x2 · `4` x1 |
| rendered size | **10** | none (CSS-sized) x62 · `16` x16 · `20` x14 · `18` x9 · `48` x7 · `28` x4 · `14` x4 · `12` x2 · `24`/`64`/`120` x1 |
| kind | 3 | outlined **62** · filled **20** · neither (CSS decides) **39** |

**13 `<path d>` strings are duplicated; 7 of them across 2+ files, 23 occurrences.**
Headline duplicates: the CTA arrow `M3 8h10m0 0L9 4m4 4L9 12` in **5 files**
(`PersonaMegaMenu.tsx`, `SPBottomCta.astro`, `SPHero.astro`, `SPShareWithTeam.astro`,
`icons.ts`); the close-x in **4**; the copy icon in `ClipboardIcons.tsx` + 3 keys of
`icons.ts`. **The check mark is drawn four different ways** (`M8 12l3 3 5-5`,
`M16.707 5.293…`, `polyline 20 6 9 17 4 12`, `polyline 9 14 11.5 16.5 16 11`) at **three
different stroke weights**. (Lower bound — only `<path d>` ≥12 chars was matched;
`icons.ts` draws heavily with `<circle>`/`<polyline>`/`<rect>`, whose duplicates are not
counted.)

**Six of the nine stroke weights live in two homepage files.**
`SPHomeNotASlice.astro` (5 SVGs at `:29,38,47,60,83`) and `SPHomeWhyNow.astro` (3 at
`:29,41,48`) between them use `1`, `1.25`, `1.5`, `1.75`, `2`, `2.5` — and two of them
hardcode `stroke="#7fa03f"`, a green that is in neither `:root` block.

### 2.2 The illustrations — 573 files to translate 92 words

| Fact | Value | Command |
|---|---|---|
| `.svg` under `src` + `public` | **637** (1,987,397 B) | `find src public -name '*.svg' \| wc -l` |
| `src/assets/images/illustrations/` | **521** (1,450,839 B) | `ls …/*.svg \| wc -l` |
| + `public/assets/images/problem*.svg` + `solution*.svg` | 26 + 26 = **52** | `ls public/assets/images/problem*.svg \| wc -l` |
| **Illustration total** | **573** | 521 + 52 — reconciles `sx-tokens` exactly |
| Distinct slugs | **21** | slug-strip + `sort -u` |
| Files per slug | **26** (13 locales x {desktop, mobile}) | per-slug `ls \| wc -l` |
| mean / median / max bytes | 2,785 / 2,616 / 4,842 | `find -printf '%s\n' \| awk` |
| **English `<text>` label strings** | **92** across the 21 English desktop files | `grep -c '<text'` per file |
| **Distinct `font-family` stacks** | **7** | `grep -ho 'font-family="[^"]*"' … \| sort \| uniq -c` |
| **Files using Inter** | **0 of 573** | `grep -l 'Inter' … \| wc -l` |
| Distinct `font-size` values | **13** (13,15,16,17,18,20,28,29,30,32,34,40,46) | `grep -o 'font-size="[0-9.]*"'` |
| Orphans in this directory | **0** | see below |

**The 26-files-per-slug explosion is caused by baked-in text, and by nothing else.**
`diff` of `environment-cloning.svg` against `environment-cloning.de.svg`, with every
`<text>…</text>` masked, differs only in whitespace, comments and the `aria-label`. The
geometry is byte-identical. 521 files exist to carry **92 short strings**.

The labels are set in `font-family="Arial, 'Helvetica Neue', sans-serif"` (1,496 + 173
occurrences) or a CJK/Arabic fallback stack — **never Inter**, the font the site preloads
at `BaseLayout.astro:131-133`. That is the mechanical reason the drawings read as clipart
rather than as part of the design: they are set in a different typeface, at a bold weight,
in 13 sizes, in a palette (`#8b0000`, `#2d5227`, `#7fa03f`) that no token declares.

It also produces a visible **layout defect**: `public/assets/images/solution.svg` places
`<text x="395" … text-anchor="start" font-size="32" font-weight="700">Under a minute</text>`
against a checkmark badge at `<circle cx="720" cy="130" r="28">`. Because the string's
extent depends on a font stack the browser may not have, it overruns into the right-hand
panel — visible in `ours-2732.png` and `ours-dark-difference.png`. *(Caveat: headless
Chrome on Linux substitutes Liberation Sans for Arial, which is wider, so the exact overrun
is environment-dependent. The root cause — an unmeasurable string baked into fixed
geometry — is not.)*

**Orphan audit.** A naive per-filename grep reports 520 orphans in
`src/assets/images/illustrations/`. That is **wrong**:
`src/utils/solution-illustration.ts:14-19` uses an **eager** `import.meta.glob`, and
reachability is a function of `(slug, lang, mobile)` at `:23-28`. All 21 slugs are live
solution pages (`src/config/solution-pages.ts:125-497`). **Corrected orphan count: 0.**
Same false positive on `public/assets/images/`: 52 of 53 files show `direct=0` but are
referenced by string interpolation at `HomeDifference.astro:19-31`
(`` `/assets/images/problem${sfx}.svg` ``). **Real orphans, confirmed:**

| File | Bytes |
|---|---:|
| `public/assets/banner-{facebook,x,reddit,discord,github,youtube}.svg`, `linkedin-banner.svg` | **68,509** |
| `public/img/{arch-operating-modes,hub-architecture,backup-strategy-flow}.svg` | 30,137 |
| 2 tutorial SVGs | — |

*Undetermined:* whether Astro tree-shakes the eager glob per page. No build was run
(read-only rule), so the on-the-wire figure below is disk size, not `dist/` output.

**`kubernetes-cluster-mobility` is the one slug with no localized and no mobile variant**
(1 file, not 26) — 12 of 13 locales fall back to the English drawing and every viewport gets
the desktop asset. It also carries **17 `<text>` elements**, against a mean of 3.9.

`scripts/scale-svg-viewbox.cjs` (`npm run scale:svg`) names assets in its hardcoded `FILES`
list that no longer exist in the directory. It is stale. Not run (read-only).

### 2.3 Dark mode: the illustrations do not adapt

| Check | Result |
|---|---|
| `prefers-color-scheme` inside the 573 | **0** |
| `currentColor` inside the 573 | **0** |
| `<style>` or `class=` hooks in the 521 | **0** |
| Opaque `fill="#f5f5f5"` full-bleed background rect | **521 of 521** |
| CSS anywhere targeting them by theme | **0 rules** |

`public/favicon.svg:5` is the **only** SVG asset in the repo that theme-switches. Confirmed
visually at `ours-dark-difference.png`: on a `rgb(26,26,27)` page the homepage shows **six
bright `#f5f5f5` slabs**. `sx-tokens` is correct.

### 2.4 The motion inventory — the system exists and is unused

**Static counts.**

| Thing | Count | Command |
|---|---:|---|
| `@keyframes` declared | **19**, in 10 files | `grep -rn '@keyframes' src public --include='*.css' --include='*.astro' --include='*.tsx' \| wc -l` |
| `transition:` declarations | **145**, in 32 files | `grep -rn 'transition:' … \| wc -l` |
| Distinct transition *values* | **41** | `grep -rho 'transition:[^;]*' … \| sort \| uniq -c` |
| Duration tokens | 3 (`--transition-duration-{fast,base,slow}` = 0.15s / 0.2s / 0.3s, `main.css:160-162`) | — |
| Hardcoded durations bypassing them | `0.15s` x9, `0.2s` x6, `120ms` x8, `200ms`, `0.1s`, `80ms` | — |
| `prefers-reduced-motion` blocks | **17** across 13 files | `grep -rn 'prefers-reduced-motion' src public` |

**Live on `http://localhost:4321/en`, 1440x900**, harvested by walking `document.styleSheets`:

| Measurement | Value |
|---|---|
| `@keyframes` reaching the homepage | **18** |
| Rules with an `animation` bound | **6** (`newsletter-spinner`, `blog-sticky-bar-wrapper`, 3 lead-magnet, `sp-terminal-cursor`) |
| Transition rules | 32 |
| Distinct durations | 7 (`0.15s` x10, `0.2s` x15, `0.5s` x2, `80ms` x2, `200ms`, `0s` x9, `0.01ms`) |
| Distinct easings | **2** (`ease` x37, `linear` x2) |
| Animated properties | `transform` x6, `opacity` x5, `box-shadow` x4, `color` x4, `border-color` x3, `background-color` x3, `top`, `margin-top`, `all` x2 |
| `prefers-reduced-motion` blocks reaching the page | **14** |
| **`document.getAnimations().length` at load** | **0** |
| **Total across all elements** | **0** |

**We already own claude.com's `AnimatedReveal`.** `public/styles/main.css:3348-3387`:

```css
.reveal            { opacity: 0; transform: translateY(20px);
                     transition: opacity 0.5s ease, transform 0.5s ease; }
.reveal.visible    { opacity: 1; transform: translateY(0); }
.reveal-stagger > .reveal:nth-child(1..6) { transition-delay: 0 / .1 / .15 / .2 / .25 / .3s }
@media (prefers-reduced-motion: reduce) { .reveal { opacity:1; transform:none; transition:none } }
```

driven by `public/scripts/scroll-reveal.js` (24 lines: one-shot `IntersectionObserver`,
`threshold: 0.1`, `rootMargin: '0px 0px -50px 0px'`, `unobserve` on fire, `disconnect` when
drained), loaded on **every** page at `BaseLayout.astro:440`.

Adoption, measured live:

| | |
|---|---|
| `.reveal` elements on the homepage | **8** |
| Topmost one | **y = 3,731 px** (`metrics-bar-inner`) — nothing in the first 3,731 px |
| `.reveal-stagger` in markup, entire repo | **0** (`grep -rn 'reveal-stagger' src public` minus `main.css` → 0 hits) |
| `.reveal` call sites | 7 files: `MetricsBar.astro:15`, `IntegrationsStrip.astro:16,17,18`, `SPHomeBottomCta.astro:16`, `PricingPreview.astro:62,66` |

So **18 lines of the stagger ladder (`main.css:3362-3379`) are dead**, and the reveal fires
only on content the user has already scrolled 3,700 px to reach — which is the one place a
reveal adds nothing.

### 2.5 Two lightboxes, one of which is dead weight everywhere

| Lightbox | Files | Size | Trigger | Features |
|---|---|---|---|---|
| `ImageModal` | `src/components/ImageModal.astro` (167 L, 35 markup + **132 CSS**) + `public/scripts/image-modal.js` (326 L, 9,363 B) | **~13.7 KB on every page** (`BaseLayout.astro:430,438`) | delegated click on `.sp-illustration-trigger` (`image-modal.js:312-320`), i.e. `SPProblem.astro:62-68` | zoom, pan, drag, touch, keyboard, prev/next |
| `HomeDifference` `<dialog>` | `HomeDifference.astro:95-97` markup, `:160-181` script | in-file | click on `.difference-row-zoom` (`:167`) | `showModal()` / close. No zoom, no pan, no nav |

The homepage ships **both**. `image-modal.js`'s 326 lines are never triggered on `/[lang]/`;
the homepage instead re-implements a strictly weaker dialog. Also flagged by `sx-metrics`
and `sx-chrome` territory: `#image-modal` is `aria-hidden` while containing focusable
buttons, on every page (`BaseLayout.astro:430`).

### 2.6 The homepage graphic budget, measured

`HomeDifference.astro` is the **only** component in the homepage tree with image tags:
6 `<picture>` elements → 12 asset URLs, **6 delivered per viewport**.

| Viewport (en) | Bytes |
|---|---:|
| desktop (6 files) | **17,928** |
| mobile (6 files) | 16,835 |

A solution page ships exactly **1** illustration (`SPProblem.astro:51-78`), ~2.5 KB. Both
pull the same eager glob of 521.

Live counts on `/en`: **25 inline SVGs, 6 viewBoxes, 8 stroke-widths, 6 rendered sizes**;
17 stroked, 6 mixed, 2 filled.

---

## 3. What claude.com and anthropic.com actually do

### 3.1 The icon system — filled, one grid, sized by a utility class

**claude.com** (`https://claude.com/`, 1440x900, 51 `<svg>`):

| Dimension | Value |
|---|---|
| filled / outlined | **51 / 0** |
| **distinct `stroke-width` values** | **0** — no element on the page has a stroke |
| viewBox | `0 0 20 20` **x42**, `0 0 16 16` x4, `0 0 17 16` x1, 2 logos (`108 12`, `573 125`) |
| rendered size | **20x20 x36, 16x16 x10** + 3 logos |
| icons that are duplicates of each other | irrelevant — they come from one component set |

**anthropic.com** (`https://www.anthropic.com/`, 40 `<svg>`, **0 `<img>`**):

| Dimension | Value |
|---|---|
| filled / outlined / both | **37 / 2 / 1** (the "both" is the constellation) |
| stroke-width, computed | `1px` on 28 elements — all 28 are constellation lines. The other 2 read `var(--nav1--icon-thickness)` |
| rendered size | `14x14` x8, `16x16` x6, `24x24` x3, `12x24` x3 |
| sizing mechanism | utility classes: `.u-icon-16 {width:16px;height:16px}`, `.u-icon-24 {1.5rem}`, `.u-icon-32 {2rem}` |

**The token that makes it one weight.** Read out of their `:root`:

```css
--border-width--main: .0625rem;                       /* = 1px */
--nav--icon-thickness: var(--border-width--main);
--nav--hamburger-thickness: var(--nav--icon-thickness);
```

**Icon stroke thickness and border thickness are the same token.** A hairline is a
hairline whether it is a box edge or an icon. (Their markup references
`--nav1--icon-thickness` — with a stray `1` — which does not resolve, so that one hamburger
falls back. Their bug, not a pattern.)

**Their arrow is a filled path.** The `→` in "Model details" / "Read announcement", read
off the live DOM:

```html
<svg width="30" viewBox="0 0 30 30" fill="none" class="g_svg">
  <path d="M25.9758 15.6633L17.5383 24.1008A…Z" fill="currentColor"></path>
</svg>
```

Computed: `fill: rgb(20,20,19)`, `stroke: none`, rendered **16x16** inside a `.u-icon-16`
slot. Everyone else draws that arrow as a 2 px stroke; they draw it as one filled outline.
**That is the entire icon philosophy: one filled path, `currentColor`, no stroke-width to
disagree about.**

**Their button has two optional icon slots.** `.btn_main_wrap` children, live:
`.u-hide-if-empty.u-icon-16` → `.btn_main_text` → `.u-hide-if-empty.u-icon-16`. An empty
slot collapses. One button component, leading and trailing 16 px icon, both optional.

### 3.2 The drawings

**anthropic.com's homepage has no drawings outside the hero card.** `document.querySelectorAll('img').length` → **0**; `canvas` → 0; `video` → 0. The whole page is
**3,211 px** with five content blocks (nav 68, hero 390, one CTA section 767, "Latest
releases" 604, mission 458, footer 923). The "Latest releases" cards
(`anth-latest-releases.png`) carry **zero icons and zero images** — a heading, a paragraph,
two hairline-ruled metadata rows and one filled arrow. The mission section
(`anth-mission.png`) is a plain link list with hairline rules and no icons at all. The only
drawing on the page is the constellation `<svg viewBox="0 0 1440 704">` already dissected in
`RESEARCH-hero.md` §3.4 (31,754 B of JS + 787 KB of webp tiles — the one thing on either
site I would not copy).

**claude.com's homepage has exactly three drawings**, and they are the closest analogue to
our illustrations:

| Asset | Bytes | Rendered | Fills |
|---|---:|---|---|
| `NodeSprout.719714b9.svg` | 13,413 | 64x64 | `#141413`, `#E7E5DB` |
| `NodePlant.10c0a4fd.svg` | 22,979 | 64x64 | same two |
| `NodeTree.a350eba8.svg` | 20,355 | 64x64 | same two |

`viewBox="0 0 500 500"`, **two colors, zero `<text>` elements**. They sit at the top of the
Free / Pro / Max pricing cards (`claude-plan-nodes.png`) as a sprout → plant → tree
progression. Plus one `<video>` in the hero
(`assets.claude.ai/videos/cowork-login-hero.mp4`, 632x724, 25.57 s, autoplay/loop/muted, no
poster) and ~36 checkmarks.

**On illustration bytes we already win** — 56.7 KB for their three against our 17.9 KB for
six. Our problem is not weight. It is that theirs are one ink, no type, and locale-free,
while ours are six inks, 13 type sizes in a foreign typeface, and 26 files each.

### 3.3 The motion, quantified

Harvested by walking `document.styleSheets` on each live page and counting declarations.

| | Ours (`/en`) | anthropic.com | claude.com |
|---|---:|---:|---:|
| Transition rules | 32 (145 in repo) | **63** | 117 |
| Distinct durations | 7 | 8 | 13 |
| **Dominant duration** | `0.2s` (15/45) | **`0.2s` (78/96 = 81 %)** | `0.2s` (80/175 = 46 %) |
| Distinct easings | **2** | 5 | 9 |
| **Dominant easing** | `ease` (37/39 = 95 %) | **`ease` (87/96 = 91 %)** | `ease` (142/184 = 77 %) |
| `@keyframes` on the page | **18** | **5** (4 are Webflow boilerplate) | 23 |
| Animation rules bound | 6 | 3 | 15+ |
| `prefers-reduced-motion` blocks | 14 | **5** | 29 |
| Global `*` reduced-motion nuke | **yes** (`main.css:365-380`) | **no** | yes |
| **Animations running at load (peak)** | **0** | **22** | (hero settled before sampling) |
| Time until motion stops | n/a — never starts | **1,350 ms** | ~1.3 s |

**Only two properties move on anthropic.com.** Sampling `document.getAnimations()` every
150 ms from navigation start:

| t (ms) | count | kinds |
|---:|---:|---|
| 0 | 20 | `CSSTransition:opacity`, `CSSTransition:transform` |
| 300 | **22** | same two, nothing else |
| 1050 | 14 | same |
| 1200 | 8 | same |
| **1350** | **0** | — |

Not a single `CSSAnimation` in the load sequence. Twenty-two words, each doing
opacity + transform, staggered `[100, 500) ms`, 800 ms each, done at 1.3 s, then the page is
still. Their declared transition properties across the whole stylesheet are `color` (32),
`background-color` (18), `border-color` (11), `opacity` (9), `transform` (9), `box-shadow`
(3), `text-decoration-color` (4), `all` (5) — plus one `height` and one padding pair.
**Nothing that triggers layout.**

**Nine of claude.com's eleven content keyframes are the same animation.** Extracted
verbatim:

| Keyframe | Body | Travel |
|---|---|---:|
| `hudFadeIn` | `opacity 0→1; translateY(-4px)→0` | 4 px |
| `tabFadeUp` (x2) | `opacity 0→1; translateY(10px)→0` | 10 px |
| `cardRaise` | `opacity 0→1; translateY(16px)→0` | 16 px |
| `itemFadeUp` | `opacity 0→1; translateY(20px)→0` | 20 px |
| `navSlideDown` | `opacity 0→1; translateY(-20px)→0` | 20 px |
| `lineRise` | `opacity 0→1; translateY(45%)→0` | ~30 px |
| `panelOpen` | `clip-path: inset(0 0 100%) → inset(0 0 0)` | — |
| `scrollNudge` | `translate(0) ↔ translate(5px)` | 5 px |
| `drift` | `scale(1.12) translate(-1.4%,-2.5%) → (1.4%,2.5%)` | ~2 % |
| `sweepAcross` | `left: 0 → 100%` | full width |

Two properties, `opacity` and `transform`. **Nothing travels more than ~20 px.** Timing on
the hero: `HeroPanel__lineRise 1.05s cubic-bezier(0.16, 1, 0.3, 1) 0.24s 1 both` — the same
expo-out curve anthropic uses on the word reveal, which is GSAP's `expo.out`: ~90 % of the
travel in the first ~25 % of the duration, so words *land* rather than glide.

**Their hover is one property.** Measured on anthropic's "Read announcement" button by
moving the mouse onto it and re-reading `getComputedStyle`:

| State | `background-color` | `transform` | `transition` |
|---|---|---|---|
| rest | `rgb(20, 20, 19)` | `none` | `border-color, color, background-color` / `0.2s, 0.2s, 0.2s` / `ease, ease, ease` |
| hover | `rgb(61, 61, 58)` | `none` | same |

No lift, no shadow, no scale, no arrow slide. Ours declares `transform` in 6 transitions
and `box-shadow` in 4 on the homepage alone.

### 3.4 `prefers-reduced-motion` — tested, and they differ from each other

Emulated with `agent-browser set media reduced-motion` and re-loaded.

**anthropic.com has 5 blocks, each containing exactly one rule, and no `*` nuke:**

```css
@media (prefers-reduced-motion: no-preference) { html.js-anim h1:not(.no-animate), … { opacity: 0 } }
@media (prefers-reduced-motion: reduce)        { .animate-word, .rotating-text-item { transition:none!important; opacity:1!important; transform:translateY(0)!important } }
@media (prefers-reduced-motion)                { .logo_marquee_logo_component { animation-play-state: paused } }
@media (prefers-reduced-motion: no-preference) { html.w-mod-js:not(.wf-design-mode) [data-scroll="section"] [data-scroll="title"|"subtitle"|"button"] { opacity: 0 } }
@media (prefers-reduced-motion: reduce)        { [data-scroll="bg"] { border-radius:0; margin:0; max-width:100% } }
```

They kill **entrance** motion and deliberately keep **feedback** motion — the 0.2 s hover
colour change still runs. Note the inversion worth stealing: the FOUC-hiding rules live
under `no-preference`, so a reduced-motion or no-JS visitor is never shown a hidden
heading.

**claude.com** ships both the `*` nuke (`transition-duration/animation-duration: 0.01ms
!important`) **and 29 per-component blocks**. Verified: under reduced motion its `h1`
computes `opacity: 1`, `animation-name: none`, `transform: none`
(`claude-1440-reducedmotion.png`).

**We are already in claude.com's camp.** `public/styles/main.css:365-380` zeroes the three
duration tokens and applies the `*, *::before, *::after` nuke, plus 13 targeted blocks.
This **corrects the practical implication of `RESEARCH-hero.md` §6-P3**: it is true that
`solution-pages.css` contains no reduced-motion guard, but the global nuke in `main.css`
already covers anything declared there, so a reduced-motion block is *not* a prerequisite
for animating the hero. What **is** required is anthropic's inversion: any FOUC-hiding rule
(`opacity: 0` before JS runs) must sit inside `@media (prefers-reduced-motion:
no-preference)`, because the `*` nuke sets *durations* to 0.01 ms and does not undo an
`opacity: 0`.

### 3.5 What makes their movement read as "simple" — the five numbers

1. **Two properties.** `opacity` and `transform`. Both composite-only; neither reflows.
2. **One duration.** 81 % of anthropic's transitions are `0.2s`; the only exception is the
   one signature move at 800 ms.
3. **One easing.** 91 % `ease`; the signature move uses `cubic-bezier(0.16, 1, 0.3, 1)`.
4. **Short travel.** 4-20 px. Never a screen, never a section.
5. **A finish line.** All motion stops at 1,350 ms and the page is dead still until you
   interact.

---

## 4. The delta

| Measurement | Ours | anthropic.com | claude.com | Gap |
|---|---:|---:|---:|---|
| Icon sources | **4** (+121 one-offs) | 1 | 1 | — |
| **Distinct `stroke-width`** | **9** | **1** (a token) | **0** | 9x / infinite |
| Distinct icon viewBox | **10** | 9 (2 real: 12x13, 12x24) | **2** (`20 20`, `16 16`) | 5x |
| Distinct rendered icon size | **10** | 4 (`14,16,24,12x24`) | **2** (`20`, `16`) | 5x |
| Filled : outlined | **20 : 62** | **37 : 2** | **51 : 0** | inverted |
| Icon sizing mechanism | 62 CSS-sized + 59 hardcoded | `.u-icon-{16,24,32}` | component prop | none |
| Duplicated `<path d>` | **13** (4 check marks) | n/a | n/a | — |
| Homepage `<svg>` viewBoxes | **6** | — | — | — |
| Homepage `<svg>` stroke-widths | **8** | — | **0** | — |
| Illustration files | **573** | 0 (+28 tiles) | **3** | 191x |
| Illustration `<text>` elements | **92** (→ x26 files) | 0 | **0** | — |
| Illustration font stacks | **7**, none Inter | n/a | n/a | — |
| Illustration font sizes | **13** | n/a | n/a | — |
| Illustration inks | **6+** (`#1a1a1a #f5f5f5 #8b0000 #2d2d2d #4a7c3f #556b2f`) | n/a | **2** | 3x |
| Illustrations adapt to dark | **0 of 573** | n/a | n/a | — |
| Illustration bytes / homepage | **17,928** | 787,000 (card) | 56,747 | *we win* |
| `@keyframes` on the page | **18** | **5** | 23 | 3.6x anthropic |
| Distinct easings | **2** | 5 | 9 | *we win* |
| Distinct durations | 7 | 8 | 13 | *we win* |
| `transition: transform` rules | **6** | 9 | 30 | — |
| `transition: box-shadow` rules | **4** | 3 | 14 | — |
| Hover vocabulary | colour + lift + shadow | **colour only** | colour + lift | — |
| **Animations at load** | **0** | **22, done at 1,350 ms** | ~1.3 s | we have none |
| Scroll-reveal system | **exists, 8 uses, all >3,731 px** | 3 `[data-scroll]` targets | `AnimatedReveal` sitewide | not adopted |
| `.reveal-stagger` uses | **0** (18 dead lines) | — | index ladder, live | dead |
| reduced-motion blocks | **14** | 5 | 29 | *adequate* |
| Lightboxes | **2** | 0 | 0 | delete one |

Read the "we win" rows carefully: **on easing count, duration count, illustration bytes and
reduced-motion coverage we are already at or ahead of the reference sites.** The gap is not
discipline in the CSS. It is that our icons are stroked instead of filled, our drawings
carry type, and our motion system is installed but not switched on.

---

## 5. Proposed simplification, ordered by leverage

### M0 — Turn on the reveal we already ship. *(no new code, highest payoff/byte)*

**Change.** Add `reveal` to the section wrappers of the first three homepage sections
(`sp-why-now`, `sp-not-a-slice`, `home-difference`) and `reveal-stagger` to the two card
grids inside them, so the observer that is already running has something above y=3,731 px to
observe. Everything needed already exists: `main.css:3348-3360`, the stagger ladder at
`:3362-3379`, the reduced-motion guard at `:3381-3387`, and
`public/scripts/scroll-reveal.js` on every page.

**Files.** `src/components/solution-pages/SPHomeWhyNow.astro`,
`SPHomeNotASlice.astro`, `src/components/HomeDifference.astro` — class attributes only.
No CSS, no JS, no i18n.

**Risk.** Low. The one thing to check: `.reveal` sets `opacity: 0` with no `no-preference`
guard, so a **no-JS** visitor sees nothing. Today that affects 8 elements deep in the page;
promoting it above the fold makes it a first-paint problem. Fix by moving the initial
`opacity: 0` behind `@media (prefers-reduced-motion: no-preference)` **and** a
`html.js-anim` class removed by a 1500 ms `setTimeout`, exactly as anthropic does. That is
~6 lines in `main.css` and `BaseLayout.astro` — and it belongs to `sx-tokens` /
`sx-primitives`; see §6.

**Proof.** Three states in the browser, not read: (1) default — `document.getAnimations()`
non-empty within 400 ms of scrolling to y=900, and 0 again within 1,500 ms; (2)
`agent-browser set media reduced-motion` — every `.reveal` computes `opacity: 1`,
`transition-duration: 0s`, and the t=0/t=1500 screenshots are pixel-identical; (3)
`agent-browser network route "**/*.js" --abort` — every section is visible. **(3) is the
control**: it is the state that fails today if the `no-preference` guard is not added.

### M1 — Convert the icon set to one filled glyph on one grid.

**Change.** One rule, taken from both reference sites: **`viewBox="0 0 20 20"`,
`fill="currentColor"`, no `stroke`, no `stroke-width`, rendered at 20 px or 16 px by a
utility class.** Concretely:

- Rewrite `src/components/solution-pages/icons.ts` (104 L) as 40 filled 20x20 glyphs —
  the 43 keys already collapse to 40 (3 byte-identical pairs). Delete
  `stroke="white"` from all 16 that hardcode it.
- Delete the five competing weight rules `solution-pages.css:420, 714, 917, 1143, 1452`.
  With filled icons there is nothing for them to set.
- Fold `CategoryIcons.tsx` (6, `1.75`), `PlatformIcons.tsx` (3, filled, 24-grid),
  `ClipboardIcons.tsx` (2, weights `2` and `3`) into the same set — 11 more glyphs, all
  regridded to 20.
- De-duplicate the 13 repeated paths: **one** arrow (currently in 5 files), **one** close-x
  (4 files), **one** check (currently four different drawings at three weights), one copy,
  one search, one shield.
- Add two sizing utilities, anthropic's exact shape: `.icon-16 { width:16px; height:16px }`,
  `.icon-20 { width:20px; height:20px }`. Delete the 59 hardcoded `width`/`height` pairs.

**Files.** `src/components/solution-pages/icons.ts`, `src/components/CategoryIcons.tsx`,
`src/components/icons/{PlatformIcons,ClipboardIcons}.tsx`, the inline `<svg>` blocks in the
33 remaining files, and the five `stroke-width` rules in `src/styles/solution-pages.css`.

**Risk.** Medium and mechanical. Filled glyphs at small sizes read heavier than 1.5 px
strokes; the 20x20 grid is chosen because that is what claude.com uses at both 20 px and
16 px and it survives the downscale. The 6 large clipart SVGs in `PricingTrustSection.astro`
(`0 0 400 280`) and the 9 in `SPHomeNotASlice`/`SPHomeWhyNow` are **drawings, not icons** —
they keep their strokes; see M3.

**Proof.** Re-run the live harvest on `/en`, `/en/pricing` and one solution page and assert:
`strokeWidths` object is **empty** for every icon-sized `<svg>` (box ≤ 24 px);
`viewBoxes` for that same set has **1** key; `renderedSizes` has **2**. Command is the
`document.querySelectorAll('svg')` walk recorded in §2.6 — it is the instrument that
produced the 9/10/10 baseline, so it can fire.

### M2 — Take the labels out of the illustrations. *(573 files → 42)*

**Change.** Delete every `<text>` element from the 21 English drawings (92 strings), move
the labels into the `<figure>` markup as positioned HTML in **Inter**, and let the SVG carry
geometry only. Then delete the 12 locale copies and the 26-file-per-slug fan-out: **573
files → 42** (21 desktop + 21 mobile), and adding a 14th locale costs **0** new files
instead of 40.

Two things fall out for free:

- **Dark mode.** With no text and geometry-only fills, swap the six hardcoded inks for
  `currentColor` and two CSS custom properties, and drop the full-bleed
  `<rect fill="#f5f5f5">` present in **521 of 521** files. That is the fix for
  `sx-tokens`' "573 illustrations stay light" finding, and it is the only fix — no CSS
  filter hack survives a `#8b0000` panel.
- **The typeface.** The labels become Inter, at the site's own type scale, instead of 7
  font stacks and 13 sizes. This is what will stop them reading as clipart.
  `ours-2732.png` vs `claude-plan-nodes.png` is the comparison.

**Files.** `src/assets/images/illustrations/*.svg` (521 → 42),
`public/assets/images/{problem,solution}*.svg` (52 → 4),
`src/utils/solution-illustration.ts:14-28` (the `(slug, lang, mobile)` resolver loses its
`lang` axis), `src/components/HomeDifference.astro:19-31`,
`src/components/solution-pages/SPProblem.astro:51-78`, plus 92 new i18n keys.

**Risk.** **High, and this is the one item I would put in front of the operator before
starting.** It is a large mechanical rewrite of hand-authored artwork, the label positions
must be re-derived per drawing, and 92 English strings x 13 locales = **1,196 naturalized
values** enter the i18n pipeline (`check-i18n-naturalization` is a blocking gate). Against
that: the 1,196 strings *already exist* inside the 521 SVGs, so this is a migration of
translations that were never in the pipeline, not net-new copy — and it is the only route to
dark-mode illustrations, correct typography, and a locale count that does not multiply the
asset tree. Deliverable is naturally splittable: the 4 homepage drawings first (visible win,
~14 strings), the 17 solution drawings after.

**Proof.** `find src/assets/images/illustrations -name '*.svg' | wc -l` → 21 (+21 mobile);
`grep -rl '<text' src/assets/images/illustrations/` → **0**;
`grep -rl 'fill="#f5f5f5"' …` → **0**; and a dark-mode screenshot of `/en` at y=2732 where
no region measures brighter than the page background — the assertion that
`ours-dark-difference.png` fails today.

### M3 — Unify the eight hand-drawn cliparts to one weight.

**Change.** `SPHomeNotASlice.astro` (5 SVGs) and `SPHomeWhyNow.astro` (3) are the only
drawings on the site that already look like claude.com's Node illustrations — hairline,
single ink, restrained (`ours-1840.png`). They are undermined by using **six different
stroke weights across eight drawings in two adjacent sections** (`1`, `1.25`, `1.5`, `1.75`,
`2`, `2.5`) and two hardcoded `stroke="#7fa03f"` greens. Set all eight to a single
`stroke-width: 1.5` and `stroke="currentColor"`. Keep the strokes — these are drawings, not
icons.

**Files.** `src/components/solution-pages/SPHomeNotASlice.astro:29,38,47,60,83`,
`SPHomeWhyNow.astro:29,41,48`.

**Risk.** Very low. Eight elements, visual only.

**Proof.** The live harvest's `strokeWidths` for `/en` drops from 8 keys to 2 (icons
contribute 0 after M1, drawings contribute `1.5`).

### M4 — Add ONE signature move: the word reveal on the h1.

Already specified in `RESEARCH-hero.md` §6-P3, and I do not repeat it. Three amendments
from this side of the fence:

1. **Build it as a variant of `.reveal`, not as new code.** The transition, the observer and
   the reduced-motion guard exist; the word reveal needs only the text-splitting step and a
   `transition-delay` per word.
2. **Use anthropic's random delay, not claude's index ladder.** Measured on the live page:
   uniform in `[100, 500)` ms per word, out of reading order. A left-to-right stagger reads
   as a typewriter, which reads as loading. Our `.reveal-stagger` ladder is the index
   variant and is the right tool for *lists*; the h1 wants randomness.
3. **Cap the duration at 800 ms / `cubic-bezier(0.16, 1, 0.3, 1)` and the travel at 24 px** —
   both sites' exact constants, and consistent with the 4-20 px band everything else on
   claude.com travels.

### What gets deleted, in total

| Deletion | Where | Size |
|---|---|---|
| 3 byte-identical icon keys | `icons.ts:19,25,47,91,44,89` | 3 glyphs |
| 5 competing `stroke-width` rules | `solution-pages.css:420,714,917,1143,1452` | 5 rules |
| 8 of 9 stroke weights | across 37 files | — |
| 12 of 13 duplicated `<path d>` occurrences | 7 files | 12 paths |
| 59 hardcoded `width`/`height` attribute pairs | 37 files | — |
| `.reveal-stagger` ladder **or** its first user | `main.css:3362-3379` | 18 dead lines |
| **531 illustration SVG files** | `src/assets/images/illustrations/`, `public/assets/images/` | 573 → 42 |
| 92 `<text>` elements x 13 locales | same | — |
| 6 illustration font stacks + 12 font sizes | same | — |
| 521 `<rect fill="#f5f5f5">` backgrounds | same | — |
| **7 orphaned social banners** | `public/assets/banner-*.svg`, `linkedin-banner.svg` | **68,509 B** |
| 3 orphaned docs diagrams | `public/img/{arch-operating-modes,hub-architecture,backup-strategy-flow}.svg` | 30,137 B |
| One of the two lightboxes | `HomeDifference.astro:95-97,160-181` **or** `ImageModal.astro` + `image-modal.js` | up to **13.7 KB on every page** |
| Stale `FILES` list | `scripts/scale-svg-viewbox.cjs` | whole script |

---

## 6. Cross-domain consequences

- **`sx-tokens` — owns `main.css`'s token layer.** Three things I need and must not write:
  (a) **an icon-thickness token**. anthropic derives `--nav--icon-thickness` from
  `--border-width--main`, so a hairline is a hairline whether it is a box edge or an icon
  stroke. After M1 only the 8 drawings need it, but the token is theirs to declare.
  (b) The **illustration ink pair** for M2 — the six hardcoded inks (`#1a1a1a`, `#f5f5f5`,
  `#8b0000`, `#2d2d2d`, `#4a7c3f`, `#556b2f`) must collapse onto declared tokens with dark
  variants, and `#7fa03f` in `SPHomeNotASlice`/`SPHomeWhyNow` is in **neither** `:root`
  block. (c) `--transition-duration-{fast,base,slow}` (`main.css:160-162`) exist and are
  bypassed by `120ms` x8, `0.15s` x9, `0.2s` x6, `200ms`, `80ms` x2, `0.1s` hardcoded.
  Named, not touched.
- **`sx-primitives` — owns the primitive rules and `main.css:3348-3387`.** The `.reveal`
  block, its stagger ladder and `scroll-reveal.js` sit in their file, not mine. M0's
  `no-preference` guard and the `html.js-anim` FOUC class are edits to
  `main.css` + `BaseLayout.astro` and must be **theirs**. I own the class attributes in the
  components. This is a hard sequencing dependency: **M0 cannot land before that guard
  exists**, or a no-JS visitor gets a blank homepage.
- **`sx-primitives` again — the button icon slot.** anthropic's `.btn_main_wrap` carries two
  `u-hide-if-empty` 16 px slots. If they are building one `.btn`, the leading/trailing icon
  slot should be in it, and my 5-way-duplicated CTA arrow becomes its default trailing icon.
- **`sx-hero`.** Two corrections to `RESEARCH-hero.md` §6-P3, both measured:
  (1) the claim "`solution-pages.css` currently has no reduced-motion guard at all" is true
  of that file but the **practical implication is wrong** — `main.css:365-380` applies a
  global `*, *::before, *::after` nuke plus zeroed duration tokens, which already covers
  anything declared in `solution-pages.css`. The real prerequisite is the *inverse* guard:
  any `opacity: 0` FOUC rule must sit under `@media (prefers-reduced-motion: no-preference)`,
  because the nuke zeroes durations and does not undo an opacity.
  (2) "port claude.com's `AnimatedReveal` pattern (12 lines)" — **we already have it**, at
  `main.css:3348-3387` + `scroll-reveal.js`, shipping on every page since before this
  program. Wave 3 is an adoption, not a port. This also changes the synthesis' Wave 3
  cost estimate downward.
- **`sx-homepage`.** M0 and M3 touch `SPHomeWhyNow.astro`, `SPHomeNotASlice.astro` and
  `HomeDifference.astro`, which are their sections. If `home-difference` is cut to ~600 px
  as they propose, M2's homepage half shrinks with it — coordinate before either starts.
  Also: `HomeDifference.astro` contains the **second** lightbox; whichever of us deletes one
  must not leave `.difference-row-zoom` without a handler.
- **`sx-pricing`.** M1 regrids `CategoryIcons.tsx` and the 6 `0 0 400 280` SVGs in
  `PricingTrustSection.astro:30,68,103,146,191,227` (weights `1`, `1.5`, `2.5`, `3` in one
  file). Those are drawings, so M3's rule applies to them too — but the file is arguably
  theirs. Flagging.
- **i18n.** M2 moves **92 English strings x 13 locales = 1,196 values** into
  `en.json` + 12 locales. Per `CLAUDE.md` this needs `npm run i18n:generate-hashes` and a
  delta re-naturalisation via `private/growth/i18n_pipeline`, and
  `check-i18n-naturalization` is a blocking gate. The strings already exist inside the SVGs
  in every locale, so the pipeline is seeding from real translations rather than
  re-translating — but they must be *imported*, and no tool does that today. **This is the
  single largest hidden cost in my proposal and it belongs in the operator's decision, not
  in an implementation session's lap.**
- **Accessibility, not mine to fix.** `#image-modal` is `aria-hidden` while containing
  focusable buttons on every page (`BaseLayout.astro:430`) — already recorded by the
  synthesis. Adding: the 521 illustrations carry good `role="img"` + `<title>` +
  `aria-label` narration, and **M2 must preserve it** — moving labels to HTML makes the
  `<title>` redundant for the labels but not for the scene description.

---

## 7. Open questions for the operator

1. **M2 is the big one: do we rebuild the 21 illustrations without baked text?** It is 573
   files → 42, it is the only route to dark-mode drawings and to labels set in Inter, and it
   removes an entire locale axis from the asset tree forever. It also costs a rewrite of
   hand-authored artwork and puts 1,196 existing translated strings through the i18n
   pipeline for the first time. **My default if unanswered: do the 4 homepage drawings only**
   (~14 strings x 13 = 182 values), prove the pattern, and leave the 17 solution drawings
   for a second pass. That is the version I would ship this session.
2. **Filled or stroked icons?** I am recommending filled/20x20 because it is what *both*
   reference sites do and because it deletes the 9-weight problem by construction rather
   than by discipline. The counter-argument is that filled glyphs read heavier at 16 px and
   our current 1.5 px outline set is quieter. This is a taste call and I would rather have
   it made once than discovered at review.
3. **Which lightbox survives?** `ImageModal` is the capable one (zoom, pan, keyboard, ~13.7
   KB) but ships on **every page** and is triggered on none of the homepage. The
   `HomeDifference` `<dialog>` is 20 lines and does nothing but open. Cheapest answer: keep
   the `<dialog>`, delete `ImageModal` + `image-modal.js`, and wire `SPProblem`'s trigger to
   the `<dialog>` — saving 13.7 KB sitewide at the cost of zoom on solution pages. Whether
   zoom matters on a 2.5 KB vector is a product call.
