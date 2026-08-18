# RESEARCH — hero (`/en` above-the-fold)

Specialist: `sx-hero`. Date: 2026-08-17. Nothing in `packages/www` was modified.
Screenshots: `/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-hero/`

---

## 1. Verdict

Our hero is locked to `min-height: 100dvh` (`src/styles/solution-pages.css:86`) and spends all
910 px of it on **117 words, 7 competing focal points, and a fake terminal that fails WCAG AA and
line-wraps into gibberish on mobile** — while anthropic.com spends 390 px on 34 words and two
focal points. The single highest-leverage change is **deletion plus unlocking the height**: remove
the eyebrow pill, the third subhead sentence, the secondary CTA, and the "* Illustrative output"
disclaimer, drop `min-height`, and let the next section be visible above the fold. The "special
component" the operator likes is not one component but a **three-layer move** — a word-by-word
headline reveal, a dark card that grows from inset-rounded to full-bleed as you scroll, and a
generative SVG constellation drawn inside it; all three are dissected in §3 with the exact
constants. Of the three, the **word reveal is the highest payoff per byte** (~50 lines total, no
dependency, no images, perfect no-JS and reduced-motion fallbacks) and is what I would build
first. There is also a live layout bug: our eyebrow pill sits *underneath* the fixed header on
both desktop and mobile.

---

## 2. What we have

### 2.1 Composition

| File | Role |
|---|---|
| `src/pages/[lang]/index.astro:14-26` | Hard-codes the 11 fake terminal lines as a JS array |
| `src/pages/[lang]/index.astro:38` | Renders `SPHomePage` |
| `src/components/solution-pages/SPHomePage.astro:34-40` | Assembles `homeHero` from 5 i18n keys |
| `src/components/solution-pages/SPHomePage.astro:44-50` | Renders `SPHero` |
| `src/components/solution-pages/SPHero.astro:30-59` | The hero markup (badge, h1, sub, 2 CTAs, terminal slot) |
| `src/components/solution-pages/SPTerminalMockup.astro:46-121` | The fake terminal + disclaimer + optional CLI-reference link |
| `src/styles/solution-pages.css:84-210` | `.sp-hero*` and the two shared button classes |
| `src/styles/solution-pages.css:212-250` | `.sp-hero-visual*` terminal chrome |
| `src/styles/solution-pages.css:2020-2033` | The only hero media query (`max-width` breakpoint) |

`SPHero` is shared with every solution page and with `PersonaPage`; the homepage is one caller.
`SPTerminalMockup` is likewise shared. Neither is homepage-only — see §6.

### 2.2 Measured, at 1440×900, `http://localhost:4321/en`

Commands: `agent-browser set viewport 1440 900`, then `eval` with `getBoundingClientRect` /
`getComputedStyle` (session `sx-hero`).

| Measurement | Value |
|---|---|
| Hero height | **910 px** (`min-height: 100dvh`, `solution-pages.css:86`) |
| Viewport height | 900 px |
| Next section (`.sp-why-now`) top | **910 px** — nothing real is above the fold |
| Words in hero | **117** |
| h1 | 4 words, 56 px / 64.4 px, Inter 700, `#fff` on `#111` |
| Subhead | 30 words, 20 px, `#a0a0a5` |
| Focal points in `.sp-hero-content` | **7**: badge, h1, subhead, primary CTA, secondary CTA, terminal card, disclaimer |
| Decorative layers | **2** pseudo-elements: a 32 px dot grid (`:96-103`) and a 600×400 green radial glow (`:104-114`) |
| Terminal card | 800 × 371 px, top at y=491 |
| Hero DOM elements | 54 |
| Entrance animation | **none** — only two hover transitions, on `.sp-btn-primary` and `.sp-btn-secondary-dark` |
| Page DOM elements | 792 |
| Full page height | 6794 px |

### 2.3 Three defects found while measuring

**(a) The eyebrow pill is clipped by the fixed header.** Measured: `.sp-hero-badge`
`getBoundingClientRect().top = 49`, header `position: fixed`, height 56, `bottom = 56`. The pill's
top 7 px are behind the header on desktop. On mobile (390×844) it is worse — the pill's first line
is fully hidden and only the word "SERVERS" is visible (`ours-390-top.png`). Root cause:
`.sp-hero` is `min-height: 100dvh` with `justify-content: center` and a flat `padding: 48px 48px`
(`solution-pages.css:84-95`) — it never accounts for the fixed header, unlike
`.sp-page > nav.sp-breadcrumb` which does (`padding: calc(var(--nav-top-offset, 3.5rem) + 24px)…`,
`solution-pages.css:56`).

**(b) Contrast failures inside the terminal.** Effective backdrop is `.sp-hero-visual`
`background: rgb(30,30,30)`. Computed ratios (WCAG formula, normal text needs 4.5:1):

| Element | Color | Size | Ratio | Verdict |
|---|---|---|---|---|
| `.sp-terminal-line` (body text) | `#777777` | 14 px | **3.72** | fails AA |
| `.sp-terminal-dots` (leader dots) | `#555555` | 14 px | **2.24** | fails AA |
| `.sp-terminal-check` (✓ glyph) | `#4a7c3f` | 14 px | **3.37** | fails AA |
| `.sp-hero-badge` on `#111` | `#4a7c3f` | 12 px bold | **3.82** | fails AA |

`agent-browser a11y --selector ".sp-hero" --tags wcag2a,wcag2aa` returns
`violations: 0  incomplete: 1` — a *serious* `color-contrast` incomplete over **30 nodes**,
including all of the above. axe cannot auto-resolve the backdrop because of the two gradient
pseudo-elements, so it downgrades to "needs manual review". That is exactly the shape of a check
that looks green and is not: the audit's clean `violations: 0` line is an artifact of the
decorative layers, not evidence of passing contrast.

**(c) The terminal is structurally broken at 390 px.** `ours-390-top.png`: hero grows to
**1201 px** (1.42 viewports), terminal wrapper is 598 px tall, and the monospace lines wrap. The
line `✓ Cloning production (3.2 TB) ... done in 4.7s` renders across three lines with the leader
dots stranded mid-block. It reads as broken output rather than as a terminal. There is no mobile
handling for `.sp-terminal-*` — the only hero media query
(`solution-pages.css:2020-2033`) touches `.sp-hero`, `h1`, `.sp-hero-sub`, `.sp-hero-ctas` only.

### 2.4 Copy (i18n keys the implementation will touch)

```
hero.eyebrow          = "SELF-HOSTED · RUNS ON YOUR OWN SERVERS"
hero.title            = "Clone Production."
hero.titleHighlight   = " Break Nothing."
hero.subtitle         = "Rediacc is software you install on your own servers. It copies your
                         whole live system in seconds: apps, databases, and settings. Then you
                         can test, back up, and recover fast."   (30 words, 3 sentences)
hero.cta.getStarted   = "Start free trial"
hero.cta.readDocs     = "Read the Docs"
common.terminalSimulationDisclaimer = "Illustrative output; actual runs may include extra logs."
```

`hero.titleHighlight` is named "highlight" but is concatenated as plain text
(`SPHomePage.astro:36`) — nothing highlights it. That is a leftover.

---

## 3. The anthropic.com hero component, dissected

Measured live at `https://www.anthropic.com/`, 2026-08-17, Chrome headless via `agent-browser`.
Screenshots: `anthropic-1440-top.png`, `anthropic-cta-t0.png`, `anthropic-cta-t3.png`,
`anthropic-cta-t6.png`, `anthropic-card-mid-scroll.png`, `anthropic-390-top.png`,
`anthropic-390-cta.png`, `anthropic-1440-reducedmotion.png`.

**There is no single "special component". There are three stacked moves**, and the impression the
operator has comes from all three firing in sequence within the first screen and a half. Taken
apart:

### 3.1 The page is Webflow, and the effects are hand-written embeds

`document.body.children` → `MAIN.page_wrap`, class names in Webflow's `block_element` convention,
`html` carries `w-mod-js w-mod-ix w-mod-ix3`. Total page: **1262 DOM elements**, 49 network
requests. GSAP + ScrollTrigger + SplitText + TextPlugin are loaded globally
(`typeof window.gsap !== 'undefined'` → true, `window.ScrollTrigger` → true). The two hero effects
are hand-written `<script>` embeds sitting inside Webflow's `w-embed` blocks, not Webflow
interactions. **Only the third effect (§3.4) uses GSAP; the first two do not.**

Structural note worth copying: the whole `<header class="hero_wrap">` is **just an h1 and a
paragraph**. Height **390 px**, `top: 68` (nav), so at a 900 px viewport the next section already
starts at **y = 458** — the second section is half visible on first paint. There is **no eyebrow
pill, no button, and no image in the hero.** The only two calls to action in the hero are the
words `research` and `products`, underlined inside the headline itself, linking to
`/research` and `claude.com/product/overview`.

### 3.2 Move 1 — the word-by-word headline reveal (`.animate-word`)

**What you see:** the headline's words fade up into place at slightly different moments, so the
line assembles rather than appears. It fires once, on load.

**Mechanism: plain DOM + CSS transitions. No GSAP, no canvas, no library.** ~55 lines of inline
JS in the footer plus ~12 lines of CSS in `<head>`.

Rendered markup (measured `h1.outerHTML`):

```html
<h1 class="u-display-xl word-animation-processed">
  <span class="u-sr-only">AI <a href="/research">research</a> and <a …>products</a> that put safety at the frontier</span>
  <span class="animate-word" style="transition-delay: 324.089ms; opacity: 1; transform: translateY(0px); will-change: auto;">AI</span>
  <span class="animate-space" style="opacity: 1;"> </span>
  <a href="/research"><span class="animate-word" style="transition-delay: 230.084ms; …">research</span></a>
  …
</h1>
```

CSS (read out of `document.styleSheets`, verbatim):

```css
.animate-word {
  display: inline-block;
  opacity: 0;
  transform: translateY(24px);
  transition: opacity   800ms cubic-bezier(0.16, 1, 0.3, 1),
              transform 800ms cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}
.animate-space { display: inline; opacity: 0; }
span.animate-word { text-decoration: inherit; }   /* keeps the link underline unbroken */
.word-animation-processed { opacity: 1 !important; }

@media (prefers-reduced-motion: reduce) {
  .animate-word { transition: none !important; opacity: 1 !important; transform: translateY(0) !important; }
}
```

The FOUC guard, inline in `<head>`:

```html
<script>
  document.documentElement.classList.add('js-anim');
  setTimeout(function () { document.documentElement.classList.remove('js-anim'); }, 1500);
</script>
<style>
  @media (prefers-reduced-motion: no-preference) {
    html.js-anim h1:not(.no-animate),
    html.js-anim .u-display-xxl:not(.no-animate),
    html.js-anim .u-display-xl:not(.no-animate),
    html.js-anim .u-animated-text { opacity: 0; }
  }
</style>
```

The JS (recovered from the inline footer script, abridged):

```js
const CONFIG = {
  selector: "h1:not(.no-animate), .u-display-xxl:not(.no-animate), .u-display-xl:not(.no-animate), .u-animated-text",
  minDelay: 100, maxDelay: 500,
};
// for each matching element:
//   skip if aria-hidden="true" or already .word-animation-processed  (double-run guard)
//   clone innerHTML into a <span class="u-sr-only"> and prepend it
//   walk the child nodes; every TEXT_NODE is split on /\S+/ into
//     <span class="animate-word"> per word and <span class="animate-space"> per gap,
//     ELEMENT_NODEs are cloned shallow and recursed  → inline <a> survives intact
//   wordSpan.style.transitionDelay = `${Math.random() * (maxDelay - minDelay) + minDelay}ms`
//   element.classList.add("word-animation-processed")
//   new IntersectionObserver(…, { threshold: 0.2 }) → on intersect,
//     requestAnimationFrame(() => { set opacity:1 and transform:translateY(0) on every word/space;
//                                   on transitionend set willChange:'auto' })
//     observer.disconnect()
document.documentElement.classList.remove("js-anim");   // reveal, before the 1.5s safety timeout
// runs immediately (footer script, hero already parsed); falls back to DOMContentLoaded
```

**Measured constants:** delay ∈ [100, 500) ms, **uniformly random per word, not sequential** (the
10 live values ranged 113.104 → 436.424 ms and were out of reading order). Duration 800 ms.
Easing `cubic-bezier(0.16, 1, 0.3, 1)` — that is GSAP's `expo.out` curve; it means ~90 % of the
travel happens in the first ~25 % of the duration, so the words *land* rather than glide. Travel
24 px upward. Total wall time ≈ 500 + 800 = 1.3 s.

**Why the randomness matters:** a left-to-right stagger reads as a typewriter, which reads as a
loading state. Random per-word delays read as the sentence *settling*, which reads as finished.
This is the whole trick and it costs one `Math.random()`.

**Degradation, verified:**
- `prefers-reduced-motion: reduce` — measured `opacity: 1`, `transform: matrix(1,0,0,1,0,0)`,
  `transition-duration: 0s`. Words are instant, and the `js-anim` FOUC rule never applies because
  it is nested inside `@media (prefers-reduced-motion: no-preference)`.
- **No JS** — `js-anim` is never added, so the headings are never hidden. Fully readable.
- **Broken/slow JS** — the 1500 ms `setTimeout` removes `js-anim` unconditionally.
- **Screen readers** — the intact sentence is duplicated into a `u-sr-only` span before the words.

### 3.3 Move 2 — the dark card that grows to full bleed on scroll

**What you see:** below the hero sits a dark, rounded, inset card. As you scroll, it grows outward
until it is a full-bleed black band. The page appears to open.

**Mechanism: GSAP ScrollTrigger scrubbing `max-width`, `border-radius` and vertical margin.**
Measured on `.big-cta_scroll-bg.is-kt3` by scrolling and reading `getComputedStyle` after settling:

| `window.scrollY` | `max-width` | `border-radius` | margin-top/bottom | rendered box |
|---|---|---|---|---|
| 0 | 89.2042 % | 24 px | 61 px | 1285 × 645 |
| 200 | 89.2042 % | 24 px | 61 px | 1285 × 645 |
| 400 | 99.8615 % | 0 px | 1 px | 1438 × 768 |
| 600 | 100 % | 0 px | 0 px | 1440 × 773 |
| 800 / 1000 | 100 % | 0 px | 0 px | 1440 × 773 |

So the entire transition happens over roughly 200 px of scroll, between y≈200 and y≈600. The card
is `overflow: hidden; background-color: var(--swatch--slate-dark, #141413)`.

Under `prefers-reduced-motion: reduce` the card is measured at `max-width: 100%`, `radius: 0`,
`margin-top: 0` at scroll 0 — it starts at its end state and never moves. Their CSS states this
explicitly:

```css
@media (prefers-reduced-motion: reduce) {
  [data-scroll='bg'] { border-radius: 0; margin-bottom: 0; margin-top: 0; max-width: 100%; }
}
```

Note the inverse guard on the copy inside it — content is hidden **only** when motion is allowed
**and** JS is alive:

```css
@media (prefers-reduced-motion: no-preference) {
  html.w-mod-js:not(.wf-design-mode) [data-scroll='section'] [data-scroll='title'],
  … [data-scroll='subtitle'], … [data-scroll='button'] { opacity: 0; }
}
```

### 3.4 Move 3 — the generative SVG constellation (`.ktve-stage`)

**What you see:** inside the dark card, a field of ~28 small photographic tiles connected by hair-
thin lines to five serif question labels ("How does AI work?", "How should I use AI?", "Who should
govern AI?", "How does AI affect the economy?", "What is AI's impact on society?"). It draws
itself in when scrolled to, then breathes almost imperceptibly. See `anthropic-card-mid-scroll.png`
for the full field.

**Mechanism: one self-contained 31,754-byte IIFE that builds an inline SVG and drives it with
GSAP + ScrollTrigger.** Not canvas, not WebGL, not video — `document.querySelectorAll('canvas')`
→ 0, `'video'` → 0.

**Structure it builds** (measured off the live DOM):

```html
<div class="ktve-stage" aria-hidden="true">
  <svg class="ktve-net" viewBox="0 0 1440 704" preserveAspectRatio="xMidYMid slice" focusable="false">
    <g>  <!-- 28 × <line stroke="#faf9f5" stroke-width="1"
                        style="stroke-dasharray:9.2661; stroke-dashoffset:0; stroke-opacity:0.256"> -->
    <g>  <!-- 28 × (<rect fill="#c6c4ba">, <image preserveAspectRatio="xMidYMid slice">) pairs -->
    <g>  <!-- 5 × <text text-anchor="middle"> with two <tspan> lines each -->
  </svg>
</div>
```

Each tile is a `<rect>` in `#c6c4ba` with an `<image>` drawn on top at the same x/y/w/h — the rect
is the backing colour so a slow image never shows a hole. Sample tile: `x=262.01 y=281.53
w=49.24 h=36.93`, image from `cdn.prod.website-files.com`, `.webp`.

**Configuration constants, verbatim from the source:**

```js
const Re = "#faf9f5";                                          // line + label ink
const xe = { pace: 5.635, drift: 0.3375, scale: 1.408, lines: 0.4 };
const Ae = { density: 0.55, lines: 0.8, seed: 0 };
const ye = 0.8 * xe.lines * Ae.lines;                          // = 0.256  final stroke-opacity
const X  = 350;                                                // ScrollTrigger start offset, px
const pe = "70%";                                              // …of viewport
const Fe = 1370, Ce = 64;
const He = [["understanding","How does","AI work?"],
            ["using","How should","I use AI?"],
            ["governing","Who should","govern AI?"],
            ["economy","How does AI affect","the economy?"],
            ["society","What is AI’s","impact on society?"]];
const at = ["1:1","4:3","4:5"];                                // tile aspect ratios, viewBox units
const ge = { "1:1": {w:30.857, h:30.857},
             "4:3": {w:34.971, h:26.229},
             "4:5": {w:28.8,   h:36} };
const Oe = "u1,u1,u1,u2,…";                                    // compact tile→cluster assignment
```

**The reveal timeline** (`ft()`), a paused GSAP timeline on a ScrollTrigger:

```js
I = gsap.timeline({
  paused: true,
  scrollTrigger: {
    trigger: oe,                       // the .big-cta_scroll-bg card
    start: "top+=350px 70%",
    toggleActions: "none none none none",
    onEnter:     function () { if (je) I.play(); },   // je = "user has scrolled down ≥1px"
    onLeaveBack: function () { I.reverse(); },
    invalidateOnRefresh: true,
  },
});
const i = 2.6, y = 0.36, x = w => (w - y) * i;       // timeline is authored in 0..1 then scaled ×2.6
// tiles: staggered by distance d from the cluster centre
sats.forEach(s => I.to(s, { e: 1, duration: 0.22*i, ease: "power2.out" },
                          x(0.4 + 0.26 * (s.d / dMax))));
I.to(labels,            { opacity: 1,         duration: 0.20*i, ease: "power2.out"  }, x(0.42));
I.to(lineEls,           { strokeDashoffset: 0, strokeOpacity: ye,
                          duration: 0.42*i, ease: "power2.inOut" },                    x(0.58));
I.to($e,                { v: 1,                duration: 0.40*i, ease: "power2.out"  }, x(0.55));
```

Total ≈ 1.7 s. Lines use the classic `stroke-dasharray = length; stroke-dashoffset: length → 0`
draw-on. `$e.v` is the global drift amplitude, ramped 0→1 so the field only starts breathing once
it has finished arriving.

**Gate worth stealing:** `je` starts `false` and is set `true` by a one-shot `scroll` listener that
fires only on a **downward** scroll of ≥1 px, after which it removes itself. The animation
therefore never plays for a visitor who has not yet scrolled, even if the card is already in
view. It is an intent gate, not a visibility gate.

**The ambient drift** (`it()` + the ticker `qe()`), decoded:

```js
function qe() {                                   // added to gsap.ticker
  const h = performance.now();
  if (Be === null) Be = h;
  Ve += (h - Be) * xe.pace;                       // Ve = phase accumulator, pace = 5.635 /ms
  Be = h;
  it();
}

function it() {
  const amp = 6 * xe.drift * $e.v;                // = 2.025 viewBox units at full ramp
  sats.forEach((s, y) => {
    const wx    = 0.00045 + 0.00008 * (y % 5);    // two incommensurate frequencies…
    const wy    = 0.00038 + 0.00007 * ((y + 2) % 6);
    const phase = y * 2.399;                      // …and a golden-angle-ish phase per tile
    const dx = amp * Math.sin(Ve * wx + phase);
    const dy = amp * Math.sin(Ve * wy + phase * 1.7);
    const sc = 1.3 - 0.3 * s.e;                   // reveal: starts 1.3× and settles to 1.0
    // opacity = s.e, transform = translate(dx + cx*(1-sc), dy + cy*(1-sc)) scale(sc)
    //   → the translate term makes scale() pivot about the tile's own centre (cx, cy)
    // each attached line's (x2, y2) endpoint is nudged by the same (dx, dy)
  });
}
```

Angular rate = `5.635 × 0.00045 ≈ 0.00254 rad/ms` → **period ≈ 2.5 s**, amplitude **±2.025 of
1440 viewBox units ≈ ±2 CSS px on a 1440 px viewport**. Two different frequencies per axis give
each tile a slow Lissajous wander that never repeats in phase with its neighbours. Confirmed
empirically: `anthropic-cta-t0.png` vs `anthropic-cta-t6.png`, six seconds apart, differ by ~4-6 px
of tile position and nothing else.

**Write discipline worth copying:** `it()` stringifies each `transform` / `opacity` / `x2` / `y2`
and compares against a cached previous string (`s.wTr`, `s.wOp`, `k.wX2`, `k.wY2`) before calling
`setAttribute`. At ±2 px of motion most frames write nothing.

**Perf gating, verified in source:**
- `new IntersectionObserver(…, { threshold: 0.25 })` adds `qe` to `gsap.ticker` when the stage is
  ≥25 % visible and **removes it** when it is not. The rAF loop does not run off-screen.
- `resize` handler only rebuilds when the SVG's own box actually changed by ≥1 px, and restores
  timeline progress afterwards.
- `matchMedia('(prefers-reduced-motion: reduce)')` has a live `change` listener that kills the
  timeline and the ticker and re-lays-out statically.

**Degradation, verified:**
- **Reduced motion** (`anthropic-1440-reducedmotion.png`): the SVG is still built with all 28
  tiles, rendered fully opaque, lines fully drawn, card already full-bleed. Identical information,
  zero motion. This is the right answer — they did not hide the graphic, they froze it.
- **Mobile 390×844** (`anthropic-390-top.png`, `anthropic-390-cta.png`): hero is 510 px, h1 drops
  to 40.29 px / 44.32 px. The stage switches from `position: absolute; inset: 0` to
  `position: relative; aspect-ratio: 1440 / 704` at `max-width: 676px`, so the constellation stops
  being a backdrop behind the copy and becomes a separate banner strip. The text block sits on
  plain dark. Good call — the tiles would have destroyed legibility behind 390 px of copy.
- **No JS**: the stage is created *by* the script, so with JS off the card is simply a flat dark
  band with its copy. Nothing breaks; the decoration is purely additive. The stage carries
  `aria-hidden="true"` and `pointer-events: none`.

**Honest cost assessment.** This is **expensive and fragile**, and I would not rebuild it verbatim:

| Cost | Measured |
|---|---|
| Bespoke JS | 31,754 bytes uncompressed, inline in the page |
| Dependency | GSAP core + ScrollTrigger (also SplitText, TextPlugin loaded page-wide) |
| Tile images | **787 KB** across 28 `.webp` files (measured with `curl -sIL … content-length`; sample tile 30,498 bytes) |
| Displayed size of a 30 KB tile | ~49 × 37 CSS px |

787 KB of imagery to decorate a background is indefensible on its own terms — the assets are
full-resolution and displayed at thumbnail size. The *idea* is excellent; the *implementation* is
a bespoke engine with a hard GSAP dependency and no content pipeline. Note also that anthropic's
Resource Timing is 44/49 opaque (no `Timing-Allow-Origin`), so any payload number that is not
`curl`-measured on that page is a guess.

**The cheapest faithful version of the same idea, for us.** The idea is: *a quiet field of many
small artifacts, joined by thin lines, that draws itself in and then breathes.* Our product-true
content for that grammar is **forks** — one production node, thin lines out to fork nodes. It can
be built with:
- inline SVG emitted at build time by Astro (no runtime layout pass, no images at all — labels and
  1-px strokes only),
- the `stroke-dasharray → stroke-dashoffset: 0` draw-on as a **pure CSS transition** toggled by a
  single `IntersectionObserver`, no GSAP,
- the drift as one CSS `@keyframes` per column with different durations and negative
  `animation-delay`s (the Lissajous wander is what buys their organic feel, but two out-of-phase
  keyframed translations at ~2.5 s and ~3.1 s get 80 % of it for 0 bytes of JS).

Estimate: ~120 lines of SVG-generating Astro, ~40 lines of CSS, ~15 lines of JS, **0 KB of images,
0 dependencies** — against their 31.7 KB of JS + GSAP + 787 KB of images.

---

## 4. What claude.com does

Measured at `https://claude.com/`, 1440×900. Screenshot `claude-1440-top.png`.

| Measurement | Value |
|---|---|
| Hero height | 876 px, `top: 0` |
| Words in hero | **39** |
| h1 | **4 words** — "Think fast, build faster" — 72 px / 79.2 px, `anthropicSerif`, **weight 330**, `#141413` |
| Subhead | 6 words — "Brainstorm in chat, build in Cowork" |
| Page background | `rgb(250, 249, 245)` — the same ivory as anthropic.com |
| Hero asset | **one `<video>`**: `assets.claude.ai/videos/cowork-login-hero.mp4`, 632 × 724, 25.57 s, `autoplay loop muted playsinline`, no poster |
| Hero CTA | **a working sign-up form**, not a button: "Continue with Google" / "Continue with email" / "Continue with SSO", plus a secondary "Download desktop app" |
| Requests / payload | 41 requests, ~1.18 MB, of which **~712 KB is six woff2 font files** |
| Canvas / WebGL | none |

Two things to take:

**(a) The hero CTA is the conversion surface itself.** They do not send you to a signup page; the
signup is in the hero. Our two links go elsewhere.

**(b) `AnimatedReveal` — the generalised, dependency-free version of anthropic's word reveal:**

```css
.AnimatedReveal…__container > * {
  opacity: 0;
  transform: translateY(var(--reveal-y, 10px));
  transition-delay: calc(var(--reveal-delay, 0s) + var(--reveal-index, 0) * var(--reveal-stagger, …));
}
.AnimatedReveal…__container.revealed > * { opacity: 1; transform: translateY(0); }

@media (prefers-reduced-motion: reduce) {
  .AnimatedReveal…__container > * { opacity: 1; transition: none; transform: none; }
}
```

Any container's direct children stagger in by index, driven entirely by three CSS custom
properties and one class flip. This is the pattern I would port — it covers the headline reveal,
the CTA reveal, and any future staggered list with one 12-line rule.

*Caveat, stated because I hit it:* a reload at 390×844 was intercepted by a Cloudflare bot
challenge (`claude-390-top.png` shows the Turnstile interstitial, Ray ID `a2ca3e144bc472c0`). I
have **no** claude.com mobile measurements. The desktop numbers above are all from a clean load.

---

## 5. The delta

| Measurement | Ours (`/en`) | anthropic.com | claude.com | Gap |
|---|---|---|---|---|
| Hero height @900 px viewport | **910 px** | **390 px** | 876 px | 2.3× anthropic |
| First non-hero content | y = **910** (below fold) | y = **458** (visible) | below fold | we show nothing real above the fold |
| Words in hero | **117** | **34** | 39 | **3.0–3.4×** |
| h1 words | 4 | 10 | 4 | fine |
| Subhead words / sentences | **30 / 3** | 24 / 2 | 6 / 1 | we over-explain |
| Focal points | **7** | **2** | 5 (2 are one action) | 3.5× |
| Eyebrow pill | yes (**clipped**) | none | none | delete |
| Buttons in hero | 2 | **0** | 1 form + 1 link | one is enough |
| Disclaimer text in hero | yes | none | none | delete |
| Decorative background layers | 2 pseudo-elements | 0 (in hero proper) | 0 | delete |
| Entrance animation | **none** | word reveal + card + constellation | staggered reveal + video | we have nothing |
| `prefers-reduced-motion` in `solution-pages.css` | **absent** | 4 separate guards | 1 guard | must add before animating |
| Hero images / video | 0 | 0 in hero, 787 KB in the card below | 1 mp4 | — |
| Contrast failures in hero | **4 classes** (2.24–3.82:1) | 0 observed | 0 observed | fix |
| Mobile hero height | **1201 px** (1.42 vh) | 510 px | not measurable | 2.4× |
| Mobile hero legibility | terminal **wraps into gibberish** | clean | not measurable | broken |

---

## 6. Proposed simplification, ordered by leverage

Every item below is scoped to the hero. `SPHero.astro` and `SPTerminalMockup.astro` are shared —
see §7 before changing their props.

### P0 — Delete. (highest leverage, zero risk, no new code)

**Change.** Remove from the homepage hero: the eyebrow pill, the secondary CTA, the terminal
disclaimer, and the third sentence of the subhead. Target: **117 words → ~30**, **7 focal points →
3** (h1, one-line subhead, one CTA).

**Files.** `src/components/solution-pages/SPHero.astro:33-36` (badge block),
`:47-49` (secondary CTA), `src/components/solution-pages/SPTerminalMockup.astro:110-120`
(disclaimer `<p>`), `src/styles/solution-pages.css:121-140` (`.sp-hero-badge`,
`.sp-hero-badge-dot`), `src/i18n/translations/en.json` (`hero.eyebrow` → delete;
`hero.subtitle` → shorten) then 12 locale files.

**Risk.** Low mechanically; `hero.badge` is a **required** prop on the `Props` interface
(`SPHero.astro:10`) used by every solution page, so it must become optional rather than be
deleted outright. The subtitle edit is an English source change → `npm run i18n:generate-hashes`
and a delta re-naturalisation of 12 locales (`npm run i18n:naturalize-status`), which is the real
cost of this item.

**Proof.** Re-measure `hero.innerText` word count and `.sp-hero-content > *` child count; assert
≤ 40 words and ≤ 4 children.

### P1 — Unlock the height and stop the header from clipping.

**Change.** Drop `min-height: 100dvh` and replace the flat `padding: 48px 48px` with
`padding: calc(var(--nav-top-offset, 3.5rem) + 48px) 48px 48px`, matching what
`.sp-page > nav.sp-breadcrumb` already does at `solution-pages.css:56`. Let the hero be its natural
height (~420 px after P0) so the next section is visible above the fold, as on anthropic.com.

**Files.** `src/styles/solution-pages.css:84-95`, and the mobile block at `:2020-2023`.

**Risk.** Medium — `.sp-hero` is shared with every solution page and `PersonaPage`, several of
which use the `--split` variant with a video (`SPHero.astro:62-69`). Those pages need a visual
pass at both breakpoints. Removing `min-height` also removes the vertical centring's reason to
exist; `justify-content: center` becomes a no-op and should go too.

**Proof.** `.sp-hero-badge`/`h1` `getBoundingClientRect().top` must be **> 56** (the fixed header's
`bottom`) at 1440×900 **and** at 390×844 — this is the exact assertion that fails today (49 and
32 respectively). And `.sp-hero.nextElementSibling.getBoundingClientRect().top < innerHeight`.

### P2 — Decide the terminal's fate.

The fake terminal is the largest single object in the hero (800 × 371 desktop, 598 px tall on
mobile), it fails contrast in three of its classes, it wraps into nonsense at 390 px, and it ships
an apology for being fake. Neither reference site puts a simulated artifact in its hero.

**Option A (recommended): delete it from the homepage hero.** After P0+P1 the hero becomes
headline + one line + one CTA, ~420 px, and the real content below the fold does the selling.
Files: `src/pages/[lang]/index.astro:14-26` (the `heroTerminalLines` array) and
`SPHomePage.astro:49`. `SPTerminalMockup` itself stays for the pages that still use it.

**Option B: keep it but fix it.** Raise `.sp-terminal-line` from `#777` and `.sp-terminal-dots`
from `#555` to ≥ 4.5:1 against `#1e1e1e` (computed: `#8a8a8a` → 4.83:1, `#9a9a9a` → 5.92:1; the
`✓` at `#4a7c3f` needs a lighter green entirely), and add a `max-width: 768px` rule that switches
`.sp-terminal-body` to
`white-space: pre; overflow-x: auto` or drops the leader-dot spans entirely so nothing wraps.
Files: `src/styles/solution-pages.css:212-250` plus a new mobile block.

**Proof.** For A: assert `.sp-terminal-wrapper` absent from `.sp-hero`. For B: recompute the four
ratios from §2.3(b) and assert ≥ 4.5; at 390 px assert every `.sp-terminal-line`
`getBoundingClientRect().height` equals the single-line height.

### P3 — Add ONE signature move: the word reveal.

This is the "special component" distilled to its cheapest form, and it is the item with the best
payoff-per-byte of anything in this document.

**Change.** Port claude.com's `AnimatedReveal` pattern (§4b) rather than anthropic's bespoke
splitter — same visual result, one CSS rule instead of 55 lines of DOM surgery. Then apply the
word-level variant to the h1 only:

- `<head>` (in `BaseLayout.astro`, next to the existing `:root` block at `:279-414`): the
  `js-anim` add + 1500 ms `setTimeout` remove, and the `@media (prefers-reduced-motion:
  no-preference) { html.js-anim .sp-hero h1 { opacity: 0 } }` guard.
- `solution-pages.css`: `.animate-word` / `.animate-space` exactly as measured in §3.2, plus a
  `@media (prefers-reduced-motion: reduce)` block — **`solution-pages.css` currently has no
  reduced-motion guard at all** (verified: it is absent from the 12 files that do).
- ~40 lines of JS: split the h1's text nodes, preserve inline elements, random delay in
  [100, 500) ms, one `IntersectionObserver` at `threshold: 0.2`, `disconnect()` after firing, and
  the `u-sr-only` duplicate for screen readers.

**Risk.** Low, and the failure modes are all covered by the 1500 ms timeout. The one thing not to
copy: anthropic wraps a `.no-animate` escape hatch into their selector — take that too, or a
future long h1 will animate somewhere it should not.

**Proof.** Three states, each verified in the browser, not read: (1) default — screenshot at
t=0 ms and t=1500 ms differ; (2) `agent-browser set media light reduced-motion` — `.animate-word`
computed `opacity: 1`, `transition-duration: 0s`, and the two screenshots are identical; (3) JS
blocked (`network route "**/*.js" --abort`) — h1 visible. State (3) is the control: if it passes
with JS disabled *and* the animation still runs with JS on, the guard is real rather than
decorative.

### P4 — Optional: the fork constellation, as our own version of the idea.

Only if the operator wants a signature graphic. Build per §3.4's "cheapest faithful version":
build-time inline SVG, one production node, thin `#4a7c3f`-tinted lines out to fork nodes,
CSS-transition draw-on gated by one `IntersectionObserver`, drift as two out-of-phase
`@keyframes`. **No images, no GSAP.** Place it *below* the hero as anthropic does, not inside it.

**Risk.** This is net-new surface in a task whose goal is simplification. It only pays off if it
replaces something — pair it with P2 Option A so the terminal leaves as the constellation arrives,
or skip it.

**Proof.** Total added bytes ≤ 6 KB; zero network requests added; reduced-motion screenshot
identical to the settled default-motion screenshot.

### What gets deleted, in total

`hero.eyebrow` (13 locales), `.sp-hero-badge` + `.sp-hero-badge-dot` (`solution-pages.css:121-140`),
the secondary CTA in the homepage hero (`SPHero.astro:47-49`), `.sp-terminal-disclaimer`
(`SPTerminalMockup.astro:110-120`) and `common.terminalSimulationDisclaimer` (13 locales), the
`heroTerminalLines` array (`index.astro:14-26`, 13 lines), `min-height: 100dvh` and
`justify-content: center` (`solution-pages.css:86,90`), the two decorative pseudo-elements
(`solution-pages.css:96-114`, 19 lines), two sentences of `hero.subtitle` (13 locales), and the
dead `hero.titleHighlight` concatenation (`SPHomePage.astro:36`).

---

## 7. Cross-domain consequences

- **`sx-chrome` (header).** The fixed 56 px header is what clips our eyebrow pill. I propose to fix
  it from the hero's padding (`solution-pages.css:84-95`), which is the local fix. If chrome
  instead introduces a global `--nav-top-offset` / scroll-padding convention, the hero should
  consume that rather than hard-code 3.5rem. **Named, not touched.**
- **`sx-tokens`.** `solution-pages.css:8-46` declares its own 22-token `--sp-*` palette on
  `.sp-page`, parallel to the `:root` block in `BaseLayout.astro:279-414`. Every hero colour cited
  in this document comes from that private set. Deduplicating it is tokens' call, not mine.
- **`sx-homepage`.** `SPHero` has three callers — `SPHomePage.astro:44`, `PersonaPage.astro:85`,
  `SolutionPage.astro:92` — which between them render **21 solution pages and 4 persona pages**
  (`grep -rl SolutionPage src/pages | wc -l` → 21; same for `PersonaPage` → 4). Making
  `hero.badge` optional (P0) and removing `min-height` (P1) changes every one of those pages. The
  `.sp-hero--split` variant with a YouTube embed (`SPHero.astro:62-85`) is the case most likely to
  break under P1.
- **Housekeeping, not mine to fix.** `git status --porcelain` shows three untracked screenshots
  sitting in the package root: `packages/www/docs-quickstart-mid.png`,
  `docs-quickstart-top.png`, `pricing-desktop-top.png`. None are mine (my captures are named
  `ours-*`, `anthropic-*`, `claude-*` and live under the scratchpad). They look like a peer
  session's `agent-browser screenshot <bare-name>` landing in the CWD. Flagging rather than
  deleting — removing another session's uncommitted files is exactly what the shared-tree rule
  forbids. Whoever owns them should either move them to the scratchpad or `.gitignore` the
  pattern before anyone commits.
- **`i18n`.** P0 and P2 touch `hero.eyebrow`, `hero.subtitle`, and
  `common.terminalSimulationDisclaimer` across 13 locales. Per `CLAUDE.md`, English changes require
  `npm run i18n:generate-hashes` and a delta re-naturalisation; `check-i18n-naturalization` is a
  blocking gate. Deleting a key is cheap; **shortening `hero.subtitle` is the expensive part of
  P0** and should be batched with any other English copy change the fleet makes.
- **Docs/CI.** `SPTerminalMockup.astro:4` imports `parseRdcCommand` from
  `scripts/lib/cli-reference-catalog.js` to auto-link `rdc` commands to docs. If the terminal is
  removed from the homepage hero (P2 Option A) that link disappears from the homepage; check
  whether any CI gate asserts a homepage → CLI-docs link before landing it.

---

## 8. Open questions for the operator

1. **Does the terminal stay?** P2 Option A (delete it from the homepage hero) is my
   recommendation and it is the difference between a 420 px hero and a 790 px one. It is a
   product-positioning call, not a CSS one — the terminal is currently the only place the homepage
   shows what `rdc` actually looks like.
2. **Do we want a signature graphic at all (P4), or is "simple" the whole brief?** anthropic.com
   earns its constellation with a 787 KB image budget and a bespoke engine. We can build the same
   *idea* for ~6 KB, but it is still net-new surface inside a simplification task. My default if
   unanswered: **build P3 (the word reveal) and skip P4**, because P3 deletes nothing and adds ~2 KB
   while P4 only pays off paired with deleting the terminal.
3. **Should the hero CTA become the conversion surface, claude.com-style** (an email field that
   posts straight into signup) rather than a link to `ACCOUNT_PATH`? That is a funnel decision that
   reaches past the hero into the account portal, so I am flagging it rather than assuming it.
