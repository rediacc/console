# RESEARCH — the solution constellation (navigator)

**Domain:** `sx-navigator`. Written 2026-08-17. Nothing was modified; this file is the
only artifact.

**The ask, verbatim:** *"Have you see the relation of solution pages with the our hero
aim? The hero on anthropic has clickable many objects. Maybe we can mock them for our
solution pages? Each click opens a small popup and redirects into the page. let's
investigate."*

---

## 0. Verdict

Yes, the 21 solution pages have a real structure, and it is **not the six-category
taxonomy in `solution-pages.ts:63-70`** — it is three verbs applied to one primitive
(`Copy → Test → Recover`), which is literally the hero sentence *"Clone Production. Break
Nothing."* Two of the shipped category assignments are demonstrably wrong, so a
constellation laid out on the existing taxonomy would be decoration with extra steps.
Two of the operator's premises about the reference are also wrong and worth knowing
before copying it: **the anthropic component is not in the hero** (it is 958 px down the
page, inside the dark "hard questions" card) and **it is not clickable** — measured
`pointer-events: none` on both the stage and the SVG, `aria-hidden="true"` on the stage.
The design below is therefore not a port; it is a different component that borrows one
composition (a sparse network framing an empty centre) and rejects the rest. It is worth
building **only if it deletes**: on its own it is a fourth navigation system for a set of
pages that already has three, and its real prize is not the graphic but the **6,474 locale
values it retires**.

---

## 1. The relation between the solution pages and the hero's aim

This section decides whether the rest is worth building, so it comes first.

### 1.1 The hero states exactly one mechanism

`src/i18n/translations/en.json` → `hero` (read via `SPHomePage.astro:35-39`):

| key | English |
|---|---|
| `hero.eyebrow` | `SELF-HOSTED · RUNS ON YOUR OWN SERVERS` |
| `hero.title` + `hero.titleHighlight` | **`Clone Production. Break Nothing.`** |
| `hero.subtitle` | `Rediacc is software you install on your own servers. It copies your whole live system in seconds: apps, databases, and settings. Then you can test, back up, and recover fast.` |

The subtitle names the primitive (*copies your whole live system in seconds*) and then
names three things you do with it: **test, back up, recover**. The headline compresses the
same thing into two clauses: `Clone Production` = the copy; `Break Nothing` = the safety
that the copy buys.

### 1.2 Classifying the 21 pages against that mechanism

Slug → category read from `src/config/solution-pages.ts:125-497`. Short labels and
one-line blurbs are the existing `pages.solutionPages.<key>.explore.solutions[]` strings.

| # | slug | shipped `category` | what it actually is | role |
|--:|---|---|---|---|
| 1 | `environment-cloning` | dev-env | fork prod into a dev env | **COPY** |
| 2 | `production-parity` | dev-env | the fork *is* prod, so parity is free | **COPY** |
| 3 | `infrastructure-costs` | dev-env | CoW forks cost ~0, so idle envs stop costing | **COPY** |
| 4 | `kubernetes-cluster-mobility` | multi-cloud | fork/move a *running* cluster | **COPY** |
| 5 | `safe-os-testing` | ransomware | apply the OS update to the fork first | **TEST** |
| 6 | `ai-pentesting` | defense | *"Clone production. Let AI attack it."* | **TEST** |
| 7 | `vulnerability-management` | defense | scan the fork, not prod | **TEST** |
| 8 | `continuous-security-testing` | defense | keep doing 6 and 7 on a schedule | **TEST** |
| 9 | `failover-testing` | multi-cloud | fail over to the fork on purpose | **TEST** |
| 10 | `backup-verification` | backups | restore into a fork and check it booted | **TEST** |
| 11 | `migration-safety` | **encryption** | fork before you migrate, roll back if not | **TEST** |
| 12 | `immutable-backups` | ransomware | snapshots ransomware can't reach | **RECOVER** |
| 13 | `instant-recovery` | backups | restore = fork from a snapshot | **RECOVER** |
| 14 | `rapid-recovery` | **ransomware** | same claim as 13, different framing | **RECOVER** |
| 15 | `retention-compliance` | backups | keep those snapshots for N years | **RECOVER** |
| 16 | `cloud-outage-protection` | multi-cloud | bring the copy up somewhere else | **RECOVER** |
| 17 | `encryption` | encryption | your keys | *property* |
| 18 | `audit-trail` | encryption | every action logged | *property* |
| 19 | `data-sovereignty` | encryption | it runs on your metal | *property* |
| 20 | `vendor-lock-in` | multi-cloud | it moves anywhere | *property* |
| 21 | `integrations` | dev-env | it plugs into your CI | *property* |

**COPY 4 · TEST 7 · RECOVER 5 · property 5 = 21.**

### 1.3 The shipped taxonomy is not load-bearing — two proofs

1. **`migration-safety` is categorised `encryption`** (`solution-pages.ts:215-217`). Its
   `hero.title` is *"Migrate without risking your data"* and its whole content is about
   forking before a migration. There is no encryption claim in it. It is filed under a
   category it does not belong to, and it therefore renders with the purple
   `encryption` left-border (`solution-pages.css:1866-1868`).
2. **`rapid-recovery` (`ransomware`) and `instant-recovery` (`backups`) are near-twins in
   different categories.** `hero.title` = *"Recover in minutes. Not days."* vs *"Get your
   whole setup back in minutes"*. Two categories, one claim.

A third signal: `data-sovereignty` is the only one of the 21 that **no other page's
`explore.solutions[]` array ever references** (measured: 180 references cover 20 slugs).
It is orphaned by the existing cross-linking.

So the six categories are a *market-segment* taxonomy (who buys it), not a *mechanism*
taxonomy (what it does). Segments are the right thing for the CTA routing they already
drive (`CATEGORY_CTA_MAP`, `solution-pages.ts:97-104`) and the wrong thing for a spatial
layout, because a spatial layout asserts that adjacency means something.

### 1.4 Answer

**There is a structure worth encoding, and it is the hero sentence.** A constellation
whose three arms are `Copy` / `Test` / `Recover`, radiating from one centre node that is
the running system, with the five *property* pages sitting as an inner ring around that
centre, is a picture of the product argument rather than an arrangement of links. The
existing six categories survive as the **colour** of each node (they already have six hex
values at `solution-pages.css:1853-1870`) so nothing is lost.

**Caveat, stated plainly:** this re-taxonomises the page set. It adds a `role` field; it
does not remove `category`. That is a content decision, and it is the prerequisite for the
component meaning anything. If the operator will not take it, do not build the
constellation — build `sx-chrome`'s Item 2 (short nav labels) instead, which fixes the
measured problem for 273 locale values and zero new components.

---

## 2. What anthropic actually built — measured, not described

Session `sx-navigator`, `https://www.anthropic.com/`, viewport 1440×900.

### 2.1 It is not the hero, and it is not clickable

Screenshot `shots/sx-navigator/anthropic-hero-1440.png` is the hero at scroll 0: headline,
a 34-word paragraph, no component. The constellation begins at **document Y ≈ 958**, inside
the near-black card (`shots/sx-navigator/anthropic-constellation-1440.png`).

```
getComputedStyle(.ktve-stage).pointerEvents  ->  "none"
getComputedStyle(svg.ktve-net).pointerEvents ->  "none"
.ktve-stage[aria-hidden]                     ->  "true"
```

Both premises in the ask are wrong. **Everything below is therefore a design for something
they did not build.**

### 2.2 Geometry

| measurement | value |
|---|---|
| `.ktve-stage` rect | 1285 × 645 at (78, 519), `position: absolute` |
| `svg.ktve-net` viewBox | `0 0 1440 704` (rendered scale ≈ 0.892) |
| `<image>` tiles | **28** |
| tile sizes | **exactly two**: 49.24 × 36.93 (4:3) and 40.55 × 50.69 (4:5) |
| `<line>` edges | **27**, all `stroke-width: 1px`, `stroke: rgb(250,249,245)` (the page cream, on a near-black card) |
| `<text>` labels | **5**, `"Anthropic Serif", Georgia`, `20px`, `text-anchor: middle`, 2 lines each |
| `<path>`, `<foreignObject>`, `<use>` | **0** |
| ink coverage (tiles) | ≈ 53,000 px² of 1,013,760 px² = **5.2 %** |
| ink coverage (lines) | total line length **2,036 units × 1px = 0.2 %** |

### 2.3 The five things that make it feel good

1. **The centre is empty.** Label centres are at (246,300), (1184,205), (940,75),
   (1151,613), (330,613) in the 1440×704 box. Not one tile or label centre falls inside
   `x ∈ [340,1050] ∧ y ∈ [150,550]`. The message occupies a ~700×400 void and the network
   occupies the perimeter. **The component is a frame, not a field.** This is the single
   most portable move.
2. **It bleeds.** Tiles sit at `x = -25` and `y = -25` and `y = 704` — deliberately
   clipped by the container. Nothing is politely inside a box.
3. **It cannot be a mesh.** 33 nodes, 27 edges. Edges < nodes forces at least six
   disconnected components, and if exactly six then zero cycles. Degree histogram:
   **20 nodes of degree 1**, 8 of degree 2, 4 of degree 3, one of degree 6. It is chains
   of leaves, not a web. Line lengths: min 4, median 54, max 236 — mostly *short local
   hops*, a handful of long reaches. A hub-and-spoke star would have produced 28 long
   equal spokes and read as a logo.
4. **The tiles are too small to read.** 49×37 CSS px, rendered at 0.892 → ~44×33. They are
   texture. This is why 787 KB of webp is spent on content nobody can see, and why we can
   drop images entirely without losing the effect.
5. **One weight, one colour.** Every line is 1px in the background cream. There is no
   secondary emphasis anywhere in the graphic. All five labels are the same size, the same
   colour, the same font.

### 2.4 Motion (from `RESEARCH-motion.md`, spot-checked)

Lines draw in via `stroke-dashoffset`; tiles fade from `scale(1.3)` staggered by distance
from centre (the `transform` attributes still read `scale(1.3000)` before reveal — I
confirmed `opacity: 0` and `stroke-opacity: 0` on a fresh load, and `opacity: 1` after a
downward scroll of ≥1px). Then everything **breathes ±2 px forever** on a two-frequency
Lissajous, gated by an `IntersectionObserver` at threshold 0.25.

---

## 3. What changes when the objects must be clickable

This is the core of the design, so it is stated as a list of departures.

| # | anthropic | ours, and why |
|---|---|---|
| 1 | breathes forever (±2 px, ~2.5 s) | **no idle motion at all.** A target that drifts under the cursor is a Fitts's-law tax and a WCAG 2.2 §2.5.8 hazard. All motion stops by ~1,400 ms and the component is dead still. |
| 2 | `pointer-events: none` on everything | the *graphic* keeps `pointer-events: none`; the **navigation is a separate HTML layer** (see §4.1). |
| 3 | `aria-hidden="true"` | only the `<svg>` is `aria-hidden`. It contains nothing focusable. `RESEARCH-bugs.md` found a sitewide `aria-hidden` focus trap — the rule here is that `aria-hidden` never appears on an ancestor of a link. |
| 4 | 44×33 px tiles | hit targets ≥ **44×44** (WCAG 2.2 AA asks 24×24; 44 is comfortable and matches touch). |
| 5 | unlabelled tiles | every node carries its real label. An unlabelled dot is a guessing game when it is a destination. |
| 6 | 5 objects | 21 + 4. Density is the risk; §7 says how it is measured. |
| 7 | no hover state at all | hover **and focus** get the same 0.2 s treatment. Anything hover reveals, focus reveals. |
| 8 | 787 KB of webp | **zero images.** |

---

## 4. The design

### 4.1 The one structural decision: two layers, not one

**The SVG carries only the edges. The nodes are HTML.**

```html
<div class="cx" data-role="constellation">
  <!-- decorative: 29 <line>, 1px, one colour, no text, nothing focusable -->
  <svg class="cx-net" viewBox="0 0 1440 760" aria-hidden="true" focusable="false"
       preserveAspectRatio="xMidYMid slice">
    <g class="cx-edges">
      <line x1="720" y1="380" x2="270" y2="235"/>
      … 28 more …
    </g>
  </svg>

  <!-- the navigation: real links, absolutely positioned from the same coordinates -->
  <nav class="cx-nav" aria-label="Solutions">
    <ul class="cx-arm">
      <li>
        <a class="cx-n cx-anchor" style="--x:18.75%;--y:30.92%"
           href="/en/solutions#copy" data-role="copy">Copy</a>
        <ul>
          <li><a class="cx-n" style="--x:9.51%;--y:18.42%" data-cat="dev-env"
                 data-blurb="Spin up a full copy of production in seconds."
                 href="/en/solutions/environment-cloning"
                ><span class="cx-dot"></span><span class="cx-lbl">Environment Cloning</span></a></li>
          … 3 more …
        </ul>
      </li>
      … test (7), recover (5) …
    </ul>
    <ul class="cx-ring"> … 5 property nodes … </ul>
  </nav>

  <!-- one popover, reused; contents swapped from the invoking node's data-* -->
  <div id="cx-pop" popover class="cx-pop" role="dialog" aria-labelledby="cx-pop-t">
    <p class="cx-pop-cat"></p>
    <h3 id="cx-pop-t"></h3>
    <p class="cx-pop-blurb"></p>
    <a class="cx-pop-go" href="#">Open<span class="cx-pop-arrow" aria-hidden="true">→</span></a>
  </div>
</div>
```

Why this beats putting the nodes inside the SVG:

- Real `<a href>`: middle-click, ctrl-click, right-click-open-in-new-tab, crawlable, in the
  sitemap's link graph.
- Focus rings, `:focus-visible`, and hit-target padding are ordinary CSS. SVG focus rings
  are a per-browser lottery.
- Text wraps and reflows per locale natively. No `text-anchor` arithmetic, no manual
  line-breaking for German, no RTL glyph-mirroring hazard (§8).
- With CSS off it is a nested `<ul>` of 25 links. With JS off, every link navigates. With
  a narrow viewport the SVG is `display:none` and the same DOM is a grouped list (§4.6).
- The graphic can stay `aria-hidden` honestly, because it genuinely contains nothing.

Nodes are positioned by CSS custom properties written by Astro at build time:
`.cx-n { position:absolute; left:var(--x); top:var(--y); transform:translate(-50%,-50%) }`.
Edge endpoints and node positions come from **the same coordinate array**, so they cannot
drift.

### 4.2 Layout — deterministic from config, zero hand-placed points

New field on `SolutionPageConfig`: `role: 'copy' | 'test' | 'recover' | 'property'`, plus
the ordering already implied by object key order.

```
VIEWBOX  1440 × 760      C = (720, 380)      rx = 520, ry = 290

anchors (3):  θ_copy = 150°, θ_test = 30°, θ_recover = 270°     [clockwise sequence]
              P = C + (rx·cosθ, −ry·sinθ)
              -> copy (270, 235)   test (1170, 235)   recover (720, 670)

arm nodes:    for the n nodes of arm k, i = 0…n-1
              φ_i = θ_k + (i − (n−1)/2) · 15°
              s_i = 1.34 + (i mod 2) · 0.07          [alternating reach = the "scatter"]
              P_i = C + (rx·s_i·cos φ_i, −ry·s_i·sin φ_i)

property ring (5): ψ_j = 90° − j·72°,  P_j = C + (0.40·rx·cos ψ_j, −0.40·ry·sin ψ_j)

RTL:          x ← 1440 − x, applied ONCE to every P, before anything else.
```

**Edges (29 for 30 nodes — deliberately below the node count, matching §2.3.3):**

- arm node `i` ↔ arm node `i−1` (a **chain** along the arc, not a spoke fan) — 18 edges
- arm node `0` ↔ its anchor — 3 edges
- anchor ↔ centre — 3 edges
- each property node ↔ centre — 5 edges

The chain is what produces anthropic's line-length distribution for free: many short local
hops (adjacent arc positions, ~40-70 units) and a few long reaches (anchor → centre,
~300 units). A spoke fan would produce 21 equal long lines and read as a sunburst.

### 4.3 ASCII sketch (LTR, desktop)

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  ·Prod Parity        ·Infra Costs                    ·Safe OS      ·AI Pentest│
 │      \      ·Env Cloning  \                            /      \      /       │
 │       \    /               ·K8s Mobility        ·Failover   ·Vuln Mgmt       │
 │        \  /                    \                    \       /                │
 │        COPY ───────────┐        \             ┌──── TEST ──── ·Backup Verify │
 │                         \        \           /                  \            │
 │                          \        \         /                    ·Migration  │
 │                           \    ·Encryption  ·Audit                           │
 │        ╭───────────────────────────────────────────────────────────╮         │
 │        │                                                           │         │
 │        │        Every solution is one thing done to a copy         │         │
 │        │        of your running system.                            │  ← the  │
 │        │                                                ·Sovereign │  empty  │
 │        │        [ the popover opens HERE, always ]                 │  centre │
 │        │                                                           │         │
 │        ╰───────────────────────────────────────────────────────────╯         │
 │              ·Integrations              ·Vendor Lock-in                      │
 │                        \                    /                                │
 │                         └──── RECOVER ─────┘                                 │
 │                        /      /    \       \                                 │
 │            ·Immutable ·Instant  ·Rapid  ·Retention  ·Cloud Outage            │
 └──────────────────────────────────────────────────────────────────────────────┘

   ·  = 6px dot in the page's category colour + label (12px)
   ── = 1px line, one colour, no weight variation
   RTL: the whole figure mirrors on x — COPY moves to the upper RIGHT and the
        clockwise sequence becomes counter-clockwise, which is correct.
```

The five property nodes sit close to the centre because they are properties *of the
system*, not things you do with it. The three verbs sit far out because they are the
three directions the argument travels. That is the whole semantic content of the layout,
and it is defensible in one sentence — which is the test a decorative layout fails.

### 4.4 The popup

**Mechanism.** One `<div popover>` (the platform Popover API), reused for all 21 nodes.

- **Open:** the node is an `<a href>`. A click listener calls `preventDefault()` +
  `pop.showPopover()` **only for a plain primary click**. `event.metaKey || ctrlKey ||
  shiftKey || button !== 0` falls through to the real navigation, so middle-click and
  ctrl-click still open a tab.
- **Content:** copied from the invoker's `data-*` — category chip, label, the existing
  28-46 char blurb, and the destination on the "Open →" link. No client-side data payload;
  the strings ship once, on the node that owns them.
- **Position:** **always the centre of the constellation.** This is the payoff of copying
  anthropic's empty middle — there is a permanent, pre-cleared 600×260 landing zone, so
  the popup needs no anchor positioning at all. CSS anchor positioning is not baseline in
  Firefox/Safari; this design never needs it, in any direction, at any breakpoint.
- **Close:** free from `popover="auto"` — Escape, light-dismiss on outside click, top
  layer (no z-index war with the sticky header).
- **Focus:** on open, focus moves to the popup's "Open →" link (`autofocus`). On the
  `toggle` event with `newState === 'closed'`, focus is restored to the stored invoker.
  ~6 lines. (Automatic focus restoration only comes free via a `popovertarget` invoker,
  which we cannot use because invokers must be `<button>` and we need `<a href>`.)
- **Redirect:** the "Open →" link is a plain `<a href>`. Enter on it navigates. There is no
  scripted `location.assign`, no timer, no auto-redirect.

**Why the popup is worth having at all** (it is a real question — a click that opens a
box before the page is friction): the blurb is the disambiguator. `Rapid Recovery` and
`Instant Recovery` are indistinguishable as labels and distinguishable as blurbs. On a
spatial navigator where labels must be short, the popup is where the short label gets its
sentence back.

**Two paths to every destination, always.** The arm anchor (`Copy`/`Test`/`Recover`) is
itself a link to the `/solutions#copy` section, so a keyboard user who does not want to
tab through 7 dots has a way out; and any node's `href` is the destination if the popup
never opens.

### 4.5 Motion

Strictly inside `RESEARCH-motion.md` §3.5's five numbers.

| phase | what | duration | easing |
|---|---|---|---|
| reveal, edges | `stroke-dashoffset: L → 0` on 29 lines, staggered 0-260 ms by distance from centre | 700 ms | `cubic-bezier(0.16,1,0.3,1)` |
| reveal, nodes | `opacity 0→1`, `transform: scale(.94)→1`, staggered 120-560 ms | 800 ms | same |
| hover / focus | `opacity` on the label, `transform: scale(1.35)` on the dot | **0.2 s** | `ease` |
| idle | **nothing** | — | — |

- Total motion ends at **~1,400 ms**, matching anthropic's 1,350 ms finish line.
- Trigger: one `IntersectionObserver` at threshold 0.2, `unobserve()` after firing. No rAF
  ticker exists, so there is nothing to add and remove on scroll.
- `stroke-dashoffset` is a paint-level property, not composited — this is the one place the
  design leaves the two-property rule. It runs once, on 29 elements, for 700 ms, and never
  again. Stated so the trade is visible rather than discovered.
- **`prefers-reduced-motion`:** the initial `opacity: 0` / `stroke-dashoffset: L` lives
  **inside `@media (prefers-reduced-motion: no-preference)`** — anthropic's inversion. The
  global `*` nuke at `public/styles/main.css:365-380` zeroes *durations*; it does not undo
  an `opacity: 0`, so without the inversion a reduced-motion or JS-disabled visitor gets a
  blank frame. This is the exact trap `RESEARCH-motion.md` §3.4 documented.

### 4.6 Responsive, no-JS, no-CSS — one DOM, three presentations

| condition | what happens | cost |
|---|---|---|
| ≥ 900 px, JS on | constellation | full |
| ≥ 900 px, JS off | constellation renders (SVG + positions are static HTML/CSS); clicking a node navigates directly, no popup | 0 |
| < 900 px | `.cx-net { display:none }`, `.cx-n { position: static }` → the same `<ul>` reflows into a three-group list; popup disabled via `@media (pointer: coarse)` so a tap navigates | 0 extra markup |
| no CSS | a nested `<ul>` of 25 links under `<nav aria-label="Solutions">` | 0 |

The constellation is a **desktop presentation of a list that always exists**. Mobile is not
a degraded constellation; it is the list, which is what mobile wanted anyway. Note
`MegaMenu.tsx` is already desktop-only (`.nav-links` is `display:none` below 64rem,
`public/styles/main.css:750-755` / `:1103-1119`), so this matches the existing split.

### 4.7 Accessibility checklist

- `<nav aria-label="Solutions">` wrapping a nested `<ul>`/`<li>`/`<a>`. Real list
  semantics; screen readers can jump by list and by nav landmark.
- `aria-hidden="true"` on the `<svg>` only, which contains no text and no focusable child.
  Never on an ancestor of the nav. (Do not repeat `RESEARCH-bugs.md`'s sitewide trap.)
- **Tab order is DOM order**, which is `copy → its 4 → test → its 7 → recover → its 5 →
  properties`. It is the semantic sequence and is therefore identical in LTR and RTL with
  no work. 25 tab stops, against the current mega menu's 23 — not a regression.
- Hit targets: `min-block-size: 44px; min-inline-size: 44px` on `.cx-n` via padding. The
  layout gate (§7) asserts no two hit rects intersect, in all 13 locales.
- `:focus-visible` ring must pass 3:1 against `#111` (the hero band, `.sp-hero` computed
  `background-color: rgb(17,17,17)`).
- Hover and focus produce the identical visual state. No hover-only affordance.
- Popup: Escape + light-dismiss from the platform; focus in on open, restored to the
  invoker on close.
- The popup is never the only path — the node's `href` is the destination.
- No `title` attributes, no tooltip-as-label.

### 4.8 Byte budget

| part | raw | gz (est.) |
|---|---:|---:|
| 21 + 3 + 1 + 5 node anchors (incl. `data-blurb`) | ~4.5 KB | ~1.3 KB |
| 29 `<line>` elements | ~1.6 KB | ~0.4 KB |
| popover shell | ~0.3 KB | ~0.2 KB |
| CSS (~110 lines) | ~2.4 KB | ~0.7 KB |
| client JS (~55 lines: click intercept, popup fill, focus restore, IO reveal) | ~1.6 KB | ~0.6 KB |
| **total** | **~10.4 KB** | **~3.2 KB** |
| **code only (CSS + JS)** | **~4.0 KB** | **~1.4 KB** |
| images | **0** | **0** |

Against `sx-motion`'s ~6 KB zero-dependency budget: the *code* is 4.0 KB; the remaining
6.4 KB is content markup that replaces card markup of comparable size. Against anthropic's
31,754-byte IIFE + 787 KB of webp: **1.6 KB of JS and no images.**

Layout math runs at **build time** in Astro, so the coordinate solver ships zero bytes.

---

## 5. What it replaces

This program is subtraction, so here is the ledger. Counts are `wc -lc` on the working
tree, 2026-08-17.

### 5.1 Code

| file / block | lines | bytes | replaced because |
|---|---:|---:|---|
| `src/pages/[lang]/solutions/index.astro` (card grid + scoped `<style>` `:79-124`) | 125 | 3,586 | the constellation **is** the `/solutions` page |
| `src/components/solution-pages/SPExploreSolutions.astro` | 48 | 1,205 | the constellation is the explore section (compact variant) |
| `src/components/solution-pages/SPRelatedSolutions.astro` | 49 | 1,323 | duplicate of the same card contract |
| `src/styles/solution-pages.css:1810-1894` + `:1996-1998,2054-2059,2082-2084` | 97 | ~2,400 | `.sp-explore*` card styling |
| `src/components/MegaMenu.tsx` | 276 | 8,610 | Solutions trigger becomes a link to `/solutions` |
| `src/styles/mega-menu.css` | 184 | 4,303 | ditto |
| `src/components/Sidebar.tsx:135-156` + `:274-332` (solutions accordion) | ~80 | ~2,800 | mobile gets the list presentation on `/solutions` |
| `public/styles/main.css:1278-1393` (`.sidebar-solutions-*`) | 116 | ~2,900 | ditto |
| **subtotal (navigator's own claim)** | **975** | **~27,127** | |
| `src/components/solution-pages/SPTerminalMockup.astro` | 121 | 3,935 | *already decided by the operator*; the compact variant takes the slot |
| `src/styles/solution-pages.css:212-386` (`.sp-terminal-*`, `@keyframes sp-blink`) | 175 | ~4,300 | ditto |
| `src/pages/[lang]/index.astro:14-26` (`heroTerminalLines`) | 13 | ~600 | ditto |
| **total including the already-decided terminal deletion** | **1,284** | **~35,962** | |

**Added:** one `.astro` component, one build-time layout module, one `.css`, one client
script ≈ **300 lines / ~9,000 bytes of source**.

**Net source: −975 lines / −18.1 KB** on this component's own claim, or **−984 lines /
−27.0 KB** if the terminal deletion is counted here.

### 5.2 The i18n ledger — this is the real prize

Measured across all 13 locale files:

```
21 solutions × explore.solutions[] = 180 entries per locale
180 entries × 3 translatable-shaped strings (title, description, category)
  = 540 values per locale × 13 locales = 7,020 values
of which genuinely translated (title + description) = 360 × 13 = 4,680
(the 180 `category` values are raw slugs — printed untranslated at
 SPExploreSolutions.astro:37 and solutions/index.astro:66; a defect, see §9)
```

Those 180 entries reference **20 distinct slugs**, so every short label is stored **an
average of 9 times** — `cloud-outage-protection`, `encryption` and `environment-cloning`
appear **21 times each**. It is a denormalised table with no primary key.

| | values |
|---|---:|
| delete `pages.solutionPages.*.explore.solutions[]` | **−7,020** |
| add `pages.solutionPages.<key>.label` + `.blurb`, 42 keys × 13 | **+546** |
| **net JSON values** | **−6,474** |
| net *translated* values (title/description → label/blurb) | **−4,134** |

**And the 546 new values already exist.** Verified in `en`, `de`, `ja`, `ar`, `tr`: the
localized short titles are present and properly naturalized (`Umgebungs-Klonen`,
`環境クローン`, `استنساخ البيئات`, `Ortam Klonlama`). This is a **harvest and dedupe**, not
authoring. English is internally consistent for 19 of 20 slugs (one title each).

Exactly two things need a human:

1. **`data-sovereignty` has no short label anywhere** — it is the one slug no explore array
   references. One new English string + 12 translations.
2. **`vendor-lock-in` has two divergent English titles** — `Vendor Lock-in Freedom` and
   `Vendor Lock-In Escape`. Pick one.

Even counting both as net-new, the bill is **13 + 13 = 26 values authored** against
**6,474 deleted**. For context, the operator has already committed ~1,200 locale values
elsewhere in this program; this component *returns* five times that.

Gates that must run afterwards (from `scripts/`): `i18n:generate-hashes` first, then
`check-translation-hashes`, `check-i18n-naturalization` (the harvested strings are
newly-registered keys and must be re-registered in the ledger even though the text is
unchanged), `check-translation-completeness`, `check-i18n-untranslated`,
`check-translation-key-usage`, `check_i18n_value_types.py`.

---

## 6. Where it lives — two variants, one engine

| variant | where | nodes | replaces |
|---|---|---:|---|
| **`compact`** | homepage hero, the slot the terminal vacates | centre + 3 anchors = **4** | `SPTerminalMockup` (121 L / 3,935 B) |
| **`full`** | `/[lang]/solutions` | 30 | the 21-card grid |

Measured hero geometry (`/en`, 1440×900): `.sp-hero` is **1425 × 910**, `position:
relative`, `overflow: hidden`, `background-color: rgb(17,17,17)`. Copy occupies
x 313-1113, y 49-427. The terminal occupies **800 × 346 at (313, 491)**. So the vacancy
is a centred 800×346 slot *plus* two 313 px side margins running the full 910 px — which
is the same proportion as anthropic's frame (their labels sit at x 246 and x 1184 in a
1440 box). The dark band, the centred copy, and the empty perimeter are already there.

**Four clickable objects is the right density for a first viewport.** Twenty-one is not —
anthropic's own hero offers five *questions* and zero links. The `full` variant earns 21
because it is on the page whose entire job is choosing among 21.

---

## 7. How I would prove it works

1. **Layout collision gate (the one that matters).** A script that loads
   `/{lang}/solutions` for all 13 locales at 1440×900 and 1280×800, reads every `.cx-n`
   bounding rect, and asserts: (a) no two rects intersect, (b) every rect is ≥44×44,
   (c) every rect is inside the viewport, (d) no rect intersects the reserved centre
   rectangle. German is the worst case (`Kubernetes-Cluster-Mobilität`, 27 chars → ~167 px
   at 12 px Inter); `ja`/`zh` are the narrowest. **Prove the instrument:** shrink the
   viewport to 1000 px and confirm the gate FAILS, before trusting a pass.
2. **Keyboard traversal.** `agent-browser` Tab-walk from the page top; assert 25 stops in
   DOM order, that each stop has a visible focus ring, that Enter on a dot opens the
   popup, that Escape closes it, and that focus lands back on the same dot. Run in `ar`
   as well as `en`.
3. **No-JS.** Load with scripting disabled; assert 25 anchors present, each with a
   non-empty `href`, and that the SVG rendered (i.e. the reveal's `opacity: 0` did not
   strand it — the `no-preference` inversion).
4. **Reduced motion.** `set media reduced-motion`; assert `getAnimations().length === 0`
   at t=0 and that every node computes `opacity: 1`.
5. **Motion finish line.** Sample `document.getAnimations()` every 150 ms from load;
   assert it reaches 0 by 1,600 ms and stays 0. This is the gate that catches anyone
   re-adding a breathe loop.
6. **RTL.** Screenshot `ar` and `en` at 1440×900, mirror one with ImageMagick
   (`convert -flop`), and `compare` the two. Node *positions* should match; glyphs will
   not. Any node whose position does not mirror is a bug.
7. **Byte gate.** Assert the component's CSS+JS stays under 6 KB raw.

---

## 8. RTL — what mirrors and what must not

Arabic is the only RTL locale (`BaseLayout.astro:65`, a hardcoded ternary; there is no
`dir` map). The site has 6 `[dir='rtl']` rules against 144 physical inline-axis properties,
so this component must contribute **zero** new physical inline-axis declarations.

**Mirrors:**

- The whole coordinate field: `x ← 1440 − x`, applied **once**, at build time, to the node
  array and the edge endpoints together. One line.
- The `Copy → Test → Recover` sequence, which is reading order. Mirroring x turns the
  clockwise LTR sequence into a counter-clockwise RTL sequence, which is correct.
- The popup's "Open →" arrow glyph. Use a `<span aria-hidden>` with
  `[dir='rtl'] & { transform: scaleX(-1) }`, or a logical `→`/`←` swap. Do not leave a
  bare `→` in RTL.

**Must NOT mirror:**

- **Glyphs.** Never apply `transform: scaleX(-1)` to the container or to any `<g>`
  containing text. Because the nodes are HTML (§4.1), this hazard does not exist here at
  all — that is a large part of why the two-layer design was chosen.
- **Dot-before-label order.** Handled natively: the node is a flex row and `dir="rtl"` on
  `<html>` reverses it. Use `margin-inline`, never `margin-left`.
- **Category colours**, which carry no directional meaning.
- **Numerals** inside blurbs (Arabic locale uses Western digits in the existing copy).

**The trap, stated so nobody hits it:** node positions use physical `left`/`top` with
**pre-mirrored** coordinates. If someone "improves" this to `inset-inline-start`, the
mirror is applied **twice** and the layout silently flips back to LTR in Arabic only.
Put that in a comment on the line.

**Free:** tab order, because it follows DOM order, which is semantic, not geometric.

---

## 9. Cross-domain consequences

Named, not fixed.

1. **`sx-chrome` owns `MegaMenu.tsx` and `Sidebar.tsx`.** §5.1 claims 656 lines across
   those two files and their CSS. Their Item 2 (short nav labels) and Item 3 (strip the
   bar) overlap directly. If the constellation ships, their Item 2's 273-value bill is
   *subsumed* by the 546-value `label`+`blurb` set — it should not be paid twice. Their
   Item 0 (the mega menu closes when you click its own trigger) becomes moot if the
   trigger becomes a plain link.
2. **`sx-hero` / `sx-homepage` own `.sp-hero` and `SPHomePage.astro`.** The `compact`
   variant lands in the slot `SPTerminalMockup` vacates.
3. **Category colours are literal hex, not tokens.** `solution-pages.css:1853-1870` hard-codes
   `#4a7c3f #c05050 #5a9abf #d4a04a #8a6fba #4ab0a0`. The constellation would consume the
   same six. **For `sx-tokens`:** these are six brand-adjacent colours with no custom
   property and no dark-mode variant.
4. **Defect, for `sx-bughunt` / `sx-i18n-ci`:** `SPExploreSolutions.astro:37` and
   `solutions/index.astro:66` render the raw category **slug** (`sol.category.replace('-','
   ')` → `dev env`, `multi cloud`) as user-visible text, in all 13 locales, while a
   translated label for every one of the six already exists at `solutions.categories.*` and
   is used correctly three lines away in the same codebase (`MegaMenu.tsx:22`,
   `Sidebar.tsx:135`, `solutions/index.astro:20`). 180 untranslated visible strings per
   locale. This is not caught by any i18n gate because the string is derived at runtime,
   not a literal.
5. **Defect, for `sx-docs` / `sx-chrome`:** `data-sovereignty` is unreachable from any
   other solution page's explore section (0 of 180 references). It is reachable only from
   the mega menu, the sidebar and `/solutions` — all three of which §5.1 proposes to
   change. Whatever ships must keep a path to it.
6. **`solution-pages.ts` is imported by 11 files.** Adding `role` is additive and safe;
   `category` stays for `CATEGORY_CTA_MAP` and the colours.

---

## 10. The honest argument against building it

Presented at full strength, because the operator should decide with it in hand.

1. **It does not solve the measured problem.** The measured problem is that nav labels are
   36.8-character marketing sentences (`MegaMenu.tsx:38`, `Sidebar.tsx:150`,
   `solutions/index.astro:35` all read `hero.title`). That is fixed by adding one short
   `label` key — 273 values, zero new components, one afternoon. The constellation is
   solving *"the hero has a hole in it where the terminal was."* Those are different
   problems, and the first one is the one the site actually has.
2. **Spatial navigation is worse than a list for finding a known item.** Nobody scans a
   star map for "retention compliance". They scan an alphabetical list, or they search —
   except that `RESEARCH-chrome.md` §2.4 measured **zero marketing pages in the search
   index**, so if the constellation becomes the primary path to 21 pages and has a bug,
   those pages have no other path. That is risk concentration on a surface with no
   fallback.
3. **This is a subtraction program, and the constellation only subtracts if the operator
   takes three separate deletion decisions** (kill the mega menu, kill the sidebar
   accordion, kill the explore cards). Take none of them and the site gains a fourth
   navigation system on top of three, which is a strict regression against the program's
   stated aim. **The component is not independently good; it is good conditional on the
   deletions.**
4. **The layout only means something after a re-taxonomy** (§1.3). Doing the re-taxonomy
   alone — fixing `migration-safety`, reconciling `rapid-recovery`/`instant-recovery`,
   giving each page a `role` — delivers most of the clarity gain with no new code at all.
   The graphic is the expensive 20% of the benefit.
5. **21 clickable dots is a density nobody in the reference set attempts.** anthropic's
   figure has 5 labels and 0 links; claude.com's nav has 9 targets. We would be shipping
   more interactive objects in one figure than either reference has on an entire page. The
   collision gate in §7 will tell us whether it *fits*; it cannot tell us whether it
   *reads*.
6. **The blurb-in-a-popup is a second click before the page.** It is justified only because
   short labels are ambiguous (`Rapid Recovery` vs `Instant Recovery`) — which is itself a
   symptom of #4, the taxonomy problem. Fix the taxonomy and the popup may be unnecessary.

**Where I come out:** build the **`compact` 4-node variant** for the hero — it is cheap
(~1.5 KB), it fills a slot that is being emptied anyway, it states the product argument in
one picture, and 4 targets is a defensible first-viewport density. **Defer the `full`
21-node variant** until the `role` re-taxonomy and the `label`/`blurb` harvest have shipped
and been looked at, because those two deliver the −6,474 locale values and most of the
clarity **without** the graphic, and they are the prerequisite for the graphic meaning
anything.

---

## Appendix: evidence

| artifact | what it shows |
|---|---|
| `/tmp/.../scratchpad/shots/sx-navigator/anthropic-hero-1440.png` | the actual hero at scroll 0 — **no constellation** |
| `/tmp/.../scratchpad/shots/sx-navigator/anthropic-constellation-1440.png` | the constellation at document Y 958, framing an empty centre |
| `/tmp/.../scratchpad/shots/sx-navigator/ours-hero-1440.png` | our hero: 1425×910, centred copy, 800×346 terminal slot |

Commands behind the counts:

```
# 180 explore entries × 3 strings, identical in all 13 locales
for f in *.json; do node -e "…count pages.solutionPages.*.explore.solutions…"; done
  -> every locale: 21 pages, 180 entries, 540 strings

# 20 distinct slugs, 1 title each except vendor-lock-in (2)
node -e "…group explore.solutions by slug…"
  -> cloud-outage-protection 21 refs, encryption 21, environment-cloning 21, …
  -> data-sovereignty: absent

# anthropic geometry
agent-browser eval "(()=>{ …querySelectorAll on svg.ktve-net… })()"
  -> 27 line, 28 image, 5 text, 0 path; viewBox "0 0 1440 704"
  -> pointerEvents "none" on stage and svg; stage aria-hidden "true"
  -> degree histogram {1:20, 2:8, 3:4, 6:1}; 33 nodes / 27 edges

# our hero geometry
agent-browser eval "(()=>{ …getBoundingClientRect on .sp-hero… })()"
  -> .sp-hero 1425×910 @ (0,0), rgb(17,17,17), overflow hidden
  -> .sp-hero-visual 800×346 @ (313,491)
```
