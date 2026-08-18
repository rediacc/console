# RESEARCH — metrics (the quantitative baseline)

**Author:** `sx-metrics` · **Measured:** 2026-08-17 · **Tool:** agent-browser 0.34.0
(Chrome 145 headless) + CDP `CSS.startRuleUsageTracking`.

Everything below is a number I read out of a live page. Where I inferred rather
than measured, it says so. Section 9 holds every snippet verbatim so a future
session re-runs *this* methodology instead of inventing a new one.

---

## 0. Verdict

The site is not complex in the ways people usually mean: our DOM is **smaller**
(762 nodes vs claude.com's 1,149 and anthropic.com's 1,263), **shallower** (max
depth 11 vs 16 and 23), our CSS is **fewer bytes parsed** (226 KB vs 342 KB and
315 KB), and our accessibility score is **as good or better**. Chasing those is
theatre. Three things are genuinely, measurably out of line: we ship **6.99 MB of
decoded JavaScript** where anthropic.com ships 0.31 MB — and **6.67 MB of it is a
single chunk containing all thirteen locale bundles**, served to every visitor on
every page; our **visual entropy** is 2–3× theirs on every axis that matters
(23 distinct painted font-sizes vs anthropic's 8; 43 distinct painted colors vs
18; 11 border-radii vs 7; 32 line-heights vs 13); and our homepage is **twice as
long** (7.55 screens desktop / 13.98 mobile vs anthropic's 3.57 / 7.59) built
from **60 boxed surfaces vs their 26**. The single highest-leverage change is
`src/i18n/utils.ts:1-13` — thirteen static JSON imports that Rollup hoists into
the shared React vendor chunk — which is 91% of the homepage's shipped bytes and
costs one afternoon.

---

## 1. SCORECARD — homepage, 1440×900, cold cache

Ours = `https://www.rediacc.com/en` (production build). Ratio = ours ÷ best of
the two references. **Bold** = we are worse.

| # | Metric | Ours | claude.com | anthropic.com | Ratio |
|---|---|---:|---:|---:|---:|
| **WEIGHT** |
| 1 | Total decoded bytes | **7,455,727** | 2,588,273 | 1,579,204 | **4.7×** |
| 2 | Total wire bytes | **1,787,868** | 1,248,736 | ~1,578,864 † | 1.4× |
| 3 | Requests | 44 | 42 | 50 | 1.05× |
| 4 | JS decoded | **6,998,912** | 1,267,131 | 305,858 | **22.9×** |
| 5 | JS wire | **1,571,347** | 410,679 | ~305,509 † | **5.1×** |
| 6 | HTML document decoded | 88,933 | 209,522 | 41,310 | 2.2× |
| 7 | Font files / bytes | 6 / 141,620 | 6 / 728,528 | 3 / 359,752 | 0.39× |
| 8 | Image bytes | 1,925 | 56,747 | 807,275 | 0.002× |
| **CSS** |
| 9 | Stylesheets `<link>`ed | **9** | 5 | **1** | **9×** |
| 10 | CSS bytes parsed (CDP) | 226,347 | 341,987 | 314,509 | 0.72× |
| 11 | CSS bytes *used* (CDP) | 51,736 | 41,498 | 64,746 | 0.80× |
| 12 | CSS unused % (CDP) | 77.1% | 87.9% | 79.4% | 0.97× |
| 13 | Style rules parsed | 1,625 | 2,152 | 1,954 | 0.83× |
| 14 | Selectors parsed | 1,822 | 2,406 | 2,209 | 0.82× |
| 15 | `--custom-property` declarations | 324 | 1,029 | 1,588 | 0.31× |
| **DOM** |
| 16 | DOM nodes | 762 | 1,149 | 1,263 | 0.66× |
| 17 | Max depth | 11 | 16 | 23 | 0.69× |
| 18 | Painted (non-zero-box) elements | 591 | 546 | 653 | 1.08× |
| 19 | Distinct class names in use | **226** | 165 | 186 | **1.37×** |
| 20 | Elements with `style=""` | 6 | 65 | 111 | 0.09× |
| 21 | Boxed surfaces (border/shadow/own bg) | **60** | 25 | 26 | **2.3×** |
| 22 | Boxed surfaces per screen | **7.9** | 5.5 | 7.3 | **1.08×** |
| **TYPE & COLOR ENTROPY** (distinct values actually painted) |
| 23 | `font-size` | **23** | 13 | 8 | **2.9×** |
| 24 | `line-height` | **32** | 24 | 13 | **2.5×** |
| 25 | `letter-spacing` | **11** | 2 | 4 | **5.5×** |
| 26 | `font-family` (first in stack) | **7** | 3 | 5 | **2.3×** |
| 27 | `font-weight` | 4 | 5 | 4 | 1.0× |
| 28 | `color` | **19** | 10 | 8 | **2.4×** |
| 29 | `background-color` (painted) | **18** | 7 | 5 | **3.6×** |
| 30 | `border-color` | **30** | 16 | 15 | **2.0×** |
| 31 | **All colors** (∪ of 28,29,30) | **43** | 19 | 18 | **2.4×** |
| 32 | `border-radius` | **11** | 6 | 7 | **1.8×** |
| 33 | `box-shadow` | **6** | 5 | 0 | **∞** |
| 34 | Distinct margin values | 24 | 11 | 23 | 1.04× |
| 35 | Distinct padding values | **20** | 13 | 11 | **1.8×** |
| 36 | Distinct spacing values (m ∪ p) | **32** | 18 | 29 | **1.1×** |
| 37 | `transition-duration` | 8 | 10 | 6 | 1.3× |
| 38 | `z-index` | 6 | 4 | 7 | 1.0× |
| **FONTS** |
| 39 | Families loaded | 2 | 3 | 3 | — |
| 40 | Weights/faces loaded | 6 | 6 files | 3 files | — |
| 41 | family+weight combos actually painted | **9** | 7 | 7 | **1.29×** |
| 42 | Text runs painted in a *fallback* family | **11** | 0 | 0 | **∞** |
| **LENGTH & TARGETS** |
| 43 | Page height @1440×900 | **6,794 px** | 4,104 | 3,211 | **2.1×** |
| 44 | …in screens | **7.55** | 4.56 | 3.57 | **2.1×** |
| 45 | Page height @390×844 | **11,795 px** | 6,608 | 6,407 | **1.8×** |
| 46 | …in screens | **13.98** | 7.83 | 7.59 | **1.8×** |
| 47 | Top-level sections in `<main>` | **14** | 6 | 11 | **1.3×** |
| 48 | Interactive elements, whole page (visible) | 110 | 117 | 116 | 0.95× |
| 49 | Interactive elements in DOM | 120 | 252 | 200 | 0.60× |
| 50 | Above-fold interactive, *naive* visible count | **51** | 18 | 17 | **3.0×** |
| 51 | Above-fold, **hit-tested clickable** | 15 | 17 ‡ | 17 ‡ | 0.88× |
| **LOAD** |
| 52 | TTFB | **686 ms** | 158 | 107 | **6.4×** |
| 53 | FCP | **1,768 ms** | 840 | 392 | **4.5×** |
| 54 | LCP | **1,768 ms** (`h1`) | 1,256 (`p`) | 580 (`h1`) | **3.0×** |
| 55 | CLS | 0.000 | 0.000 | 0.000 | 1.0× |
| **ACCESSIBILITY** (axe-core, default tag set) |
| 56 | Violated rules | 3 | 2 | 4 | 1.5× |
| 57 | Violating nodes | 4 | 2 | 10 | 2.0× |
| 58 | Critical / serious | 0 / 2 | 1 / 0 | 0 / 2 | — |
| 59 | Rules passed | 44 | 44 | 39 | 1.0× |

† anthropic.com's assets are cross-origin (`cdn.prod.website-files.com`) with no
`Timing-Allow-Origin`, so Resource Timing reports `0` for every byte. I refetched
all 50 URLs with `curl` (§9.6); the CDN answered without applying compression to
that request, so the anthropic wire figure is effectively its *decoded* figure and
is an **upper bound** on real wire bytes. Its decoded numbers are exact.

‡ claude.com and anthropic.com both had a cookie consent banner open, contributing
3 buttons each. Excluding those: 15 / 14 / 14 — a dead heat. See §4.2.

### The pricing pages

`https://www.anthropic.com/pricing` **301s to `https://claude.com/pricing`** —
verified, `location.href` after navigation reads `https://claude.com/pricing`
(`cold-anthropicpricing-1440x900.json`). There is no third pricing page.

| Metric | Ours `/en/pricing` | claude.com/pricing |
|---|---:|---:|
| CSS bytes parsed (CDP) | 178,123 | 2,750,570 |
| CSS unused % | 74.4% | **94.7%** |
| Stylesheets tracked | 25 | 96 |
| DOM nodes | 902 | **6,942** |
| Max depth | 11 | 24 |
| Boxed surfaces | **166** | 86 |
| Boxed surfaces / screen | **18.0** | 10.4 |
| Page height @1440×900 | 8,292 px / 9.21 screens | 7,417 px / 8.24 screens |
| Page height @390×844 | 11,931 px / 14.14 screens | 12,096 px / 14.33 screens |
| Distinct `font-size` | **19** | 14 |
| All colors | 27 | 25 |
| `box-shadow` | 2 | 5 |
| LCP | **1,808 ms** | 432 ms |
| axe rules / nodes | 4 / 6 | 5 / 16 |

**claude.com/pricing is not the exemplar the homepage is.** It parses 2.75 MB of
CSS (a 2.66 MB Webflow `claude-brand.shared.*.min.css`, 94.9% unused) into 6,942
DOM nodes. Our pricing page beats it on almost every structural axis except
**box density** (18.0 surfaces per screen vs 10.4) and **LCP**. Anyone arguing
"be like claude.com/pricing" should be shown this table first.

---

## 2. The single damning finding: `assets/react.*.js` is 13 locales

`https://www.rediacc.com/assets/react.DrK1BhOX.js` — **6,673,504 bytes decoded /
1,457,105 bytes over the wire**, `initiatorType: "script"` (it is executed, not
merely preloaded). That is **89.5% of the page's decoded bytes** and **81.5% of
its wire bytes**.

What is in it, measured by character-script census over the downloaded file:

| Script block | Characters in the chunk |
|---|---:|
| Cyrillic (ru) | 210,674 |
| Arabic (ar) | 165,430 |
| Hangul (ko) | 94,399 |
| CJK (zh) | 93,449 |
| Kana (ja) | 67,999 |

plus Latin-script locale markers: `Wiederherstellung` ×162, `herstel` ×220,
`ripristino` ×152, `recuperação` ×141, `recuperación` ×127, `récupération` ×90,
`Kurtarma` ×65. The first 400 characters of the file are Arabic marketing copy.

**Root cause, with file:line:**

- `packages/www/src/i18n/utils.ts:1-13` statically imports all thirteen locale
  JSONs. On disk they total **9,284,710 bytes**
  (`ls -l src/i18n/translations/*.json`).
- `packages/www/src/i18n/react.ts:3` — `useTranslation()` calls
  `createTranslator` from that module.
- Every hydrated React island imports `useTranslation`:
  `Navigation.tsx:4`, `Footer.tsx:7`, `SearchModal.tsx:4`, `MegaMenu.tsx:4`,
  `ContactModal.tsx:4`, `ContactForm.tsx:4`, `LeadMagnetModal.tsx:4`,
  `NewsletterSignup.tsx:4`, `NewsletterReturnPopup.tsx:4`, `LogoWall.tsx:2`,
  `DownloadsList.tsx:4`, `InstallMethods.tsx:17`.
- Rollup therefore hoists all thirteen JSONs into the shared vendor chunk
  `assets/react.*.js`, which **every page** loads. Confirmed on `/en/pricing`
  too: identical `6,998,912` decoded JS bytes.

`grep -l "react.zEl4485N.js" dist/assets/*.js` lists 10+ island chunks importing
it. The local `dist/assets/react.zEl4485N.js` is 6,708,716 bytes.

**Inference (not measured):** splitting so an island receives only its own
locale should take homepage decoded JS from 6,998,912 to roughly
`6,998,912 − 6,673,504 + (6,673,504 ÷ 13) ≈ 838,000` bytes, and wire bytes from
1,571,347 to ~226,000. That is a 8.3× decoded reduction from one module.

---

## 3. The second finding: solution-page CSS on the homepage

CDP rule-usage coverage of `https://www.rediacc.com/en` (§9.3), byte-accurate,
the same engine as the DevTools Coverage panel:

| Stylesheet | Bytes | Unused |
|---|---:|---:|
| `/styles/main.css` | 77,091 | 61.7% |
| `/assets/dev-environments-brief.DCAEVfNs.css` | 43,814 | **89.8%** |
| `/assets/disaster-recovery.CUnfI_BA.css` | 40,844 | **87.8%** |
| `/assets/dev-environments-brief.Dr8ZFj4H.css` | 29,312 | 76.7% |
| `/styles/contact-modal.css` | 10,367 | **100%** |
| `/styles/search-modal.css` | 8,626 | **100%** |
| `/assets/index.Dbh1AFuQ.css` | 6,202 | 15.2% |
| `/styles/responsive.css` | 4,562 | 86.0% |
| `/styles/region-picker.css` | 4,253 | **100%** |
| inline `<style>` in `/en` | 1,217 + 59 | 100% / 0% |
| **Total** | **226,347** | **77.1%** |

The homepage `<link>`s **three solution-page stylesheets** —
`dev-environments-brief` (twice, two different hashes) and `disaster-recovery` —
together **113,970 bytes, i.e. 50.4% of all CSS parsed on the homepage**, at
77–90% unused. Verified straight from the HTML:

```
$ curl -sSL --compressed https://www.rediacc.com/en \
  | grep -oE '<link[^>]*rel="stylesheet"[^>]*>' | sed -E 's/.*href="([^"]*)".*/\1/'
/styles/main.css
/styles/responsive.css
/styles/search-modal.css
/styles/contact-modal.css
/styles/region-picker.css
/assets/dev-environments-brief.DCAEVfNs.css
/assets/index.Dbh1AFuQ.css
/assets/dev-environments-brief.Dr8ZFj4H.css
/assets/disaster-recovery.CUnfI_BA.css
```

anthropic.com ships **one** stylesheet. claude.com ships five.

**Caveat I want on the record:** unused-CSS *percentage* is a bad target — see
§5.2. What matters here is that 114 KB of the 226 KB has nothing to do with this
page.

---

## 4. Where the "complex" feeling actually comes from

### 4.1 Entropy, controlled for element count

The obvious objection to "23 font-sizes vs 8" is *we just have more elements*.
The data kills it: anthropic.com paints **653** non-zero-box elements to our
**591**, and does it with **8** distinct font-sizes, **5** background colors,
**2** border-radii and **0** box-shadows. More painted elements, one third the
vocabulary.

Our homepage font-size ladder, with the count of elements at each size
(`detail.js`, §9.4) — 23 values:

```
16px×176  14px×158  18px×157  12.8px×42  11px×15  12px×6  20px×5  10px×5
32px×5  40px×5  9px×4  17px×3  48px×3  20.8px×3  …  (9 more, ≤3 elements each)
```

`12.8px`, `20.8px`, `17px`, `9px`, `10px`, `11px` are em-cascade accidents, not
design decisions. anthropic.com's whole ladder is
`12 / 14 / 15 / 16 / 18 / 20 / 24 / 60.87px` — eight values, and the top three
(`12px×321`, `20px×251`, `16px×199`) carry 771 of its elements.

Colors, ours vs anthropic.com (top of each list):

```
ours       rgb(26,26,26)×221  rgb(94,94,99)×136  rgb(74,74,79)×128
           rgb(107,107,112)×43  … 20 distinct text colors, 19 backgrounds,
           30 border colors  =  43 distinct colors painted
anthropic  rgb(20,20,19)×335  rgb(250,249,245)×273  rgb(176,174,165)×183
           rgb(135,134,127)×16  … 9 text colors, 5 backgrounds, 15 borders
           = 18 distinct colors painted
```

Three near-identical greys (`#5e5e63`, `#4a4a4f`, `#6b6b70`) doing the same job
is the shape of the problem: nobody chose them together.

Surface decoration on the homepage: **7 border-radii, 5 shadow styles, 11 border
styles** (`boxes.js`, §9.5). anthropic.com: **2 radii, 0 shadows, 1 border
style**. That is the number I would put on a wall.

### 4.2 Above-fold density: the naive metric lies, and I checked

`document.querySelectorAll(<interactive selector>)` filtered by visibility
counts **51** above-fold targets for us vs 18 / 17. That number is wrong for our
purposes: 42 of ours sit inside the nav's pre-rendered mega-menu panels, which
have real boxes but are not hit-testable. Re-measuring with
`document.elementFromPoint()` at each element's own centre plus an effective-opacity
walk (`hittest.js`, §9.5) gives:

| | clickable above fold | in header/nav | in body |
|---|---:|---:|---:|
| rediacc.com/en | 15 | 13 | 2 |
| claude.com | 17 (14 + 3 cookie) | 9 | 8 |
| anthropic.com | 17 (14 + 3 cookie) | 15 | 2 |

**We are not denser above the fold.** I am reporting this because the naive
number is the one a careless re-measurement will produce, and it would let a
future session claim a 3× win it did not earn. Use `hittest.js`, not the naive
count. (The 51-vs-18 gap is still a real fact about *DOM* weight in the header —
`sx-chrome`'s territory — just not about visual density.)

The fold itself is clean: see
`scratchpad/shots/sx-metrics/hprod-fold-1440x900.png`.

### 4.3 Length

Full-page captures, all at 1440 wide:

- ours — `scratchpad/shots/sx-metrics/fprod-full-1440.png` (6,794 px):
  hero, "Your world moves fast" 3-card grid, an infra logo strip, a 4-card
  "Most tools copy one piece" grid, a **five-block** "The Difference"
  before/after sequence, a 4-number metrics strip, a second logo strip, the full
  three-tier pricing table, footer. **14 top-level sections, 60 boxed surfaces.**
- claude.com — `fclaude-full-1440.png` (4,104 px): hero + signup card,
  "Explore plans" (3 cards), FAQ (3 rows), footer. **6 sections, 25 boxes.**
- anthropic.com — `fanth-full-1440.png` (3,211 px): headline, one large black
  rounded panel (this is the "special component" the operator likes), 3 release
  cards, a 5-row link list, footer. **11 sections, 26 boxes, 0 shadows.**

At 390×844 ours is **13.98 screens** of scrolling. Both references are ~7.6.

### 4.4 Eleven text runs render in a fallback font

`detail.js` finds 11 painted text nodes on our homepage whose computed
first-choice family is a bare generic:

```
{tag:"text", fam:"sans-serif", txt:"10× faster"}
{tag:"text", fam:"sans-serif", txt:"seconds, not months"}
{tag:"text", fam:"sans-serif", txt:"many clouds, no copy"}
{tag:"text", fam:"monospace",  txt:"DB"}   … 7 more
```

They are `<text>` elements inside inline SVG illustrations, which never inherit
the page's `--font-family`. claude.com and anthropic.com: **0**. This is why our
"family+weight combos painted" is 9 against their 7 — two of ours are accidents.
Cheap, visible fix; belongs to whoever owns the illustrations (`sx-tokens` /
`sx-homepage`).

### 4.5 Load

LCP 1,768 ms against anthropic's 580 ms, and TTFB 686 ms against their 107 ms.
The TTFB gap is Cloudflare edge-cache behaviour on a cold path, not markup; I did
not isolate it. FCP == LCP for us on both pages, meaning the `h1` is the largest
paint and nothing blocks it — so the LCP number will move mainly with TTFB and
with the render-blocking CSS in §3, not with the JS in §2 (that chunk is
`type=module`, deferred). **Do not promise an LCP win from the i18n split.**

---

## 5. What is NOT wrong — do not "fix" these

This is the most useful thing in this document. Four plausible-sounding targets
would be pure theatre, because we already match or beat both references:

1. **Unused-CSS percentage.** Ours 77.1%. claude.com 87.9%. anthropic.com 79.4%.
   claude.com/pricing is **94.7%** unused on a 2.66 MB sheet. Every site with a
   global stylesheet looks like this. Target *bytes parsed*, never the ratio.
2. **DOM node count and depth.** 762 nodes / depth 11 vs 1,149 / 16 and
   1,263 / 23. We are the leanest of the three. Node-count reduction buys nothing.
3. **Above-fold interactive density** — see §4.2, we are at parity once
   hit-tested.
4. **Accessibility.** 3 violated rules / 4 nodes, 44 rules passed. claude.com has
   1 critical; anthropic.com has 10 violating nodes. Ours are `aria-hidden-focus`
   (1), `color-contrast` (2), `heading-order` (1) — worth fixing on principle,
   worthless as a simplification KPI. **They are a guardrail, not a target: they
   must not get worse.**

Also not a problem: **font bytes** (141 KB, the leanest of the three — claude.com
ships 728 KB of fonts), **image bytes** (1.9 KB vs anthropic's 807 KB — though
that is arguably a *content* deficiency, not a win), **request count** (44 vs 42
and 50), and **inline `style=""` attributes** (6 vs 65 and 111).

---

## 6. Proposed OFFICIAL before/after targets

Measured on the **production build** of `/en` at **1440×900**, cold cache, unless
noted. Re-run §9 verbatim.

| # | Metric | Before | Target | Why this one |
|---|---|---:|---:|---|
| **T1** | Homepage decoded JS bytes | 6,998,912 | **≤ 500,000** | §2. One module. 14× win. |
| **T2** | Homepage wire bytes, total | 1,787,868 | **≤ 400,000** | Follows T1. |
| **T3** | Distinct painted `font-size` | 23 | **≤ 8** | anthropic = 8. Type scale is the visible core of "simple". |
| **T4** | Distinct painted colors (∪ text/bg/border) | 43 | **≤ 16** | anthropic = 18, claude = 19. |
| **T5** | Distinct painted `border-radius` | 11 | **≤ 3** | anthropic = 7, and only 2 among its boxed surfaces. |
| **T6** | Distinct painted `box-shadow` | 6 | **≤ 1** | anthropic = 0. Shadows are the cheapest thing to delete. |
| **T7** | Distinct painted `line-height` | 32 | **≤ 8** | anthropic = 13; 32 means the scale is unowned. |
| **T8** | Distinct painted `letter-spacing` | 11 | **≤ 3** | claude = 2. |
| **T9** | Boxed surfaces, homepage | 60 | **≤ 28** | claude 25, anthropic 26. |
| **T10** | Boxed surfaces, `/en/pricing` | 166 (18.0/screen) | **≤ 90 (≤ 11/screen)** | claude/pricing 86 / 10.4. |
| **T11** | Page height @1440×900 | 6,794 px (7.55 scr) | **≤ 4,200 px (≤ 4.7 scr)** | claude 4,104. |
| **T12** | Page height @390×844 | 11,795 px (13.98 scr) | **≤ 7,000 px (≤ 8.3 scr)** | both refs ≈ 6,500. |
| **T13** | Stylesheets `<link>`ed on `/en` | 9 | **≤ 3** | §3. Kill the solution-page leak. |
| **T14** | CSS bytes parsed on `/en` | 226,347 | **≤ 120,000** | Deleting the 114 KB leak gets most of this. |
| **T15** | Text runs painted in a fallback family | 11 | **0** | §4.4. Binary, trivially checkable. |
| **T16** | Top-level sections in `<main>` | 14 | **≤ 8** | claude 6, anthropic 11. |

**Guardrails — must not regress (report them every time):**

| G1 | axe violated rules / nodes | 3 / 4 | ≤ 3 / ≤ 4 |
| G2 | CLS | 0.000 | ≤ 0.02 |
| G3 | LCP | 1,768 ms | ≤ 1,768 ms (do not promise better — see §4.5) |
| G4 | `h1` count | 1 | exactly 1 |
| G5 | Interactive elements, whole page | 110 | ≥ 60 (deleting nav links is fine; deleting the funnel is not) |

If you want **one** number for the operator: *decoded bytes the homepage ships*,
**7.46 MB → under 1 MB**, alongside *distinct painted colors*, **43 → 16**.

---

## 7. Methodology notes and honest limits

- **The dev server is a valid instrument for structure, not for weight.** I
  measured both. `localhost:4321/en` and `www.rediacc.com/en` agree exactly on
  page height (6,794 px), on every entropy figure (23 font-sizes, 43 colors, 11
  radii, 6 shadows), on painted elements (591), and within 0.2% on style rules
  (1,628 vs 1,625) and selectors (1,822 vs 1,822). They diverge only where Astro's
  dev pipeline differs: **157 requests vs 44**, **10.8 MB of unbundled JS modules
  vs 23 bundled files**, and **150,334 bytes of injected inline `<style>` vs
  1,276**. So: **T3–T16 may be re-measured on the dev server; T1, T2 and the
  vitals must be measured against a production build.**
- **Cold cache matters and warm runs silently lie.** My first pass reused one
  browser and reported `transferSize: 0` for cached pricing-page assets (33 KB
  "total"). Every number above comes from a **fresh named session per URL** so
  the HTTP cache is empty. `cold.sh` (§9.2) enforces this.
- **CSS coverage is real, not approximated.** `coverage.mjs` (§9.3) drives
  `CSS.startRuleUsageTracking` over CDP. Chrome reports only the *used* ranges, so
  unused bytes are derived by subtracting merged used ranges from
  `CSS.getStyleSheetText` length — exactly what the DevTools Coverage panel does.
  As a control I also kept the naive static approximation inside `probe.js`
  ("does any element match this selector"): it says 72.5% unused where CDP says
  77.1%. Close enough to trust the approximation if CDP is ever unavailable, and
  the 4.6-point gap is the honest error bar.
- **Instrument control.** The entropy probe discriminates strongly across the
  three sites on the same page type (8 / 13 / 23 font-sizes) while element counts
  stay within 20% of each other — it is measuring vocabulary, not volume. The
  above-fold probe **failed** its control (§4.2) and I replaced it rather than
  report the flattering number.
- **Could not obtain:** (a) real *wire* bytes for anthropic.com — cross-origin
  Webflow CDN with no `Timing-Allow-Origin`, and my `curl` refetch came back
  effectively uncompressed, so its wire figure is an upper bound only; decoded
  bytes are exact. (b) **INP** — requires real interaction; `vitals` returned
  `null` on all six pages. (c) A separate anthropic.com pricing page — it 301s to
  claude.com/pricing. (d) JS *execution* coverage (`Profiler.startPreciseCoverage`)
  — I stopped at CSS; the 6.67 MB chunk is damning enough without it, and a future
  session can add it with the same CDP harness.
- **claude.com redirects on a second navigation.** Re-opening `https://claude.com/`
  inside a session that already loaded it lands on
  `https://claude.ai/?redirect=claude.com&via=cookie` (46 DOM nodes). My mobile
  pass hit this; I re-measured in a clean session. Check `result.url` in every
  output before trusting a row.

---

## 8. Cross-domain consequences (naming, not fixing)

- **`sx-tokens`** — T3–T8 land in your files. 229 distinct `--custom-property`
  names are defined across 348 declarations in **six** `:root`-ish origins:
  `src/layouts/BaseLayout.astro:281` and `:302`, `public/styles/main.css:61`,
  `public/styles/responsive.css:73`, `src/styles/sidebar-shared.css:6`,
  `src/components/AnnouncementBar.astro:32`. Only 324 custom-property
  *declarations* survive into the runtime cascade on the homepage — against
  claude.com's 1,029 and anthropic.com's 1,588. **Their token systems are far
  larger than ours and their painted output is far smaller.** Fewer tokens is not
  the goal; fewer *painted values* is. Also §4.4: inline SVG `<text>` needs
  `font-family` set.
- **`sx-chrome`** — the header renders 42 boxed interactive elements inside the
  fold that are not hit-testable (mega-menu panels). Not a visual-density problem
  (§4.2) but it is DOM and hydration weight, and it is why `Navigation.6ZJran_r.js`
  is 68,135 bytes decoded.
- **`sx-homepage`** — T9, T11, T16. 14 sections, 60 boxed surfaces, five
  near-identical before/after blocks in "The Difference".
- **`sx-pricing`** — T10. 166 boxed surfaces, 18.0 per screen, the worst density
  figure anywhere in this study including claude.com/pricing.
- **Whoever owns build config** — §2 and §3 are both bundler-shaped:
  `src/i18n/utils.ts:1-13` and the three solution-page stylesheets `<link>`ed on
  `/en`. Neither is anyone's *design* domain and both are bigger wins than any
  design change. **Do not let them fall between chairs.**

---

## 9. The instruments — re-run these verbatim

Working copies live in
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/metrics/`.
That directory is session-scoped and will be gone; the source below is canonical.
Nothing here is added to the repo.

### 9.0 Session setup

```bash
export AGENT_BROWSER_SESSION=sx-metrics
export AGENT_BROWSER_SCREENSHOT_DIR=/tmp/.../shots/sx-metrics
mkdir -p "$AGENT_BROWSER_SCREENSHOT_DIR"
# NEVER `agent-browser close --all` — it kills every peer's browser.
```

### 9.1 `probe.js` — weight, CSS, DOM, entropy, fonts, height, targets

Run as `agent-browser eval --stdin --json < probe.js`.

```js
(() => {
  // ---------- WEIGHT ----------
  const res = performance.getEntriesByType('resource');
  const nav = performance.getEntriesByType('navigation')[0];
  const bucket = (r) => {
    const u = r.name.split('?')[0].toLowerCase();
    if (/\.(woff2?|ttf|otf|eot)$/.test(u)) return 'font';
    if (/\.(png|jpe?g|gif|webp|avif|svg|ico)$/.test(u)) return 'image';
    if (u.endsWith('.css') || r.initiatorType === 'css') return 'css';
    if (/\.(js|mjs|cjs|jsx|ts|tsx)$/.test(u) || r.initiatorType === 'script') return 'js';
    if (/\.(mp4|webm|mov|m4v)$/.test(u)) return 'video';
    if (r.initiatorType === 'fetch' || r.initiatorType === 'xmlhttprequest') return 'xhr';
    return 'other';
  };
  const weight = {};
  for (const r of res) {
    const b = bucket(r);
    weight[b] = weight[b] || { count: 0, transfer: 0, decoded: 0, encoded: 0 };
    weight[b].count++;
    weight[b].transfer += r.transferSize || 0;
    weight[b].decoded += r.decodedBodySize || 0;
    weight[b].encoded += r.encodedBodySize || 0;
  }
  const docTransfer = nav ? (nav.transferSize || 0) : 0;
  const docDecoded = nav ? (nav.decodedBodySize || 0) : 0;
  const totals = { requests: res.length + (nav ? 1 : 0), transfer: docTransfer, decoded: docDecoded };
  for (const k in weight) { totals.transfer += weight[k].transfer; totals.decoded += weight[k].decoded; }

  // ---------- CSS ----------
  let sheets = 0, rulesTotal = 0, styleRules = 0, selectorsTotal = 0, mediaRules = 0,
      keyframes = 0, fontFaceRules = 0, customPropDecls = 0, declsTotal = 0,
      inaccessible = 0, matchedRules = 0, unmatchedRules = 0, unTestable = 0;
  const cssBytesByHref = {};
  const walk = (list) => {
    for (const rule of list) {
      rulesTotal++;
      if (rule.type === 1 || rule instanceof CSSStyleRule) {
        styleRules++;
        const sels = (rule.selectorText || '').split(',').map(s => s.trim()).filter(Boolean);
        selectorsTotal += sels.length;
        declsTotal += rule.style ? rule.style.length : 0;
        if (rule.style) {
          for (let i = 0; i < rule.style.length; i++) {
            if (rule.style[i].startsWith('--')) customPropDecls++;
          }
        }
        // static "does any element match" test; strip pseudo-elements & dynamic pseudo-classes
        let any = false, testable = false;
        for (const s of sels) {
          const cleaned = s
            .replace(/::[a-zA-Z-]+(\([^)]*\))?/g, '')
            .replace(/:(hover|focus|focus-within|focus-visible|active|visited|target|checked|disabled|enabled|placeholder-shown|autofill|user-invalid|invalid|valid|-webkit-[a-z-]+|-moz-[a-z-]+)(\([^)]*\))?/g, '')
            .trim();
          if (!cleaned) continue;
          testable = true;
          try { if (document.querySelector(cleaned)) { any = true; break; } } catch (e) { testable = false; }
        }
        if (!testable) unTestable++;
        else if (any) matchedRules++;
        else unmatchedRules++;
      } else if (rule.type === 4 || rule instanceof CSSMediaRule) {
        mediaRules++; walk(rule.cssRules || []);
      } else if (rule.type === 7 || (window.CSSKeyframesRule && rule instanceof CSSKeyframesRule)) {
        keyframes++;
      } else if (rule.type === 5 || (window.CSSFontFaceRule && rule instanceof CSSFontFaceRule)) {
        fontFaceRules++;
      } else if (rule.cssRules) {
        walk(rule.cssRules);
      }
    }
  };
  for (const sh of document.styleSheets) {
    sheets++;
    try { walk(sh.cssRules); } catch (e) { inaccessible++; }
    if (sh.href) {
      const r = res.find(x => x.name === sh.href);
      cssBytesByHref[sh.href] = r ? { transfer: r.transferSize, decoded: r.decodedBodySize } : null;
    }
  }
  const inlineStyleTagBytes = Array.from(document.querySelectorAll('style'))
    .reduce((a, s) => a + (s.textContent || '').length, 0);

  // ---------- DOM ----------
  const all = document.querySelectorAll('*');
  let maxDepth = 0, inlineStyled = 0;
  const classSet = new Set();
  let deepestPath = '';
  for (const el of all) {
    let d = 0, n = el, path = [];
    while (n && n !== document.documentElement) { d++; path.push(n.tagName.toLowerCase()); n = n.parentElement; }
    if (d > maxDepth) { maxDepth = d; deepestPath = path.reverse().join('>'); }
    if (el.hasAttribute('style') && el.getAttribute('style').trim()) inlineStyled++;
    for (const c of el.classList) classSet.add(c);
  }

  // ---------- ENTROPY (painted computed styles) ----------
  const props = ['color', 'background-color', 'font-size', 'font-family', 'font-weight',
                 'border-radius', 'box-shadow', 'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
                 'padding-top', 'padding-bottom', 'padding-left', 'padding-right',
                 'line-height', 'letter-spacing', 'border-color', 'border-width', 'text-transform', 'transition-duration', 'z-index'];
  const sets = {}; props.forEach(p => sets[p] = new Set());
  let visible = 0;
  for (const el of all) {
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const painted = rect.width > 0 && rect.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
    if (!painted) continue;
    visible++;
    for (const p of props) {
      let v = cs.getPropertyValue(p);
      if (!v) continue;
      if (p === 'background-color' && v === 'rgba(0, 0, 0, 0)') continue; // transparent = not painted
      if (p === 'box-shadow' && v === 'none') continue;
      if (p === 'border-radius' && v === '0px') continue;
      sets[p].add(v.trim());
    }
  }
  const entropy = {};
  for (const p of props) entropy[p] = sets[p].size;
  const marginVals = new Set(); ['margin-top','margin-bottom','margin-left','margin-right'].forEach(p => sets[p].forEach(v => marginVals.add(v)));
  const padVals = new Set(); ['padding-top','padding-bottom','padding-left','padding-right'].forEach(p => sets[p].forEach(v => padVals.add(v)));
  entropy['_margin_all'] = marginVals.size;
  entropy['_padding_all'] = padVals.size;
  entropy['_spacing_all'] = new Set([...marginVals, ...padVals]).size;
  entropy['_color_all'] = new Set([...sets['color'], ...sets['background-color'], ...sets['border-color']]).size;

  // ---------- FONTS ----------
  const loadedFaces = [];
  try { document.fonts.forEach(f => { if (f.status === 'loaded') loadedFaces.push(f.family + ' ' + f.weight + ' ' + f.style); }); } catch (e) {}
  const paintedFamilyWeight = new Set();
  for (const el of all) {
    if (!el.textContent || !el.textContent.trim()) continue;
    const hasDirectText = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    if (!hasDirectText) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    paintedFamilyWeight.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + cs.fontWeight);
  }
  const fontFiles = res.filter(r => /\.(woff2?|ttf|otf|eot)$/.test(r.name.split('?')[0].toLowerCase()))
    .map(r => ({ url: r.name.split('/').pop(), transfer: r.transferSize, decoded: r.decodedBodySize }));

  // ---------- HEIGHT / TARGETS ----------
  const vh = window.innerHeight, vw = window.innerWidth;
  const pageH = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  const interactiveSel = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [tabindex]:not([tabindex="-1"]), [onclick]';
  const inter = Array.from(document.querySelectorAll(interactiveSel));
  const visInter = inter.filter(el => {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  });
  const aboveFold = visInter.filter(el => { const r = el.getBoundingClientRect(); return r.top < vh && r.bottom > 0; });

  return {
    url: location.href, vw, vh,
    weight, totals, doc: { transfer: docTransfer, decoded: docDecoded },
    css: { sheets, inaccessible, rulesTotal, styleRules, selectorsTotal, mediaRules, keyframes,
           fontFaceRules, declsTotal, customPropDecls, matchedRules, unmatchedRules, unTestable,
           unmatchedPct: styleRules ? +(100 * unmatchedRules / styleRules).toFixed(1) : 0,
           inlineStyleTagBytes, cssBytesByHref },
    dom: { nodes: all.length, visibleNodes: visible, maxDepth, deepestPath: deepestPath.slice(0, 300),
           inlineStyled, distinctClasses: classSet.size },
    entropy,
    fonts: { loadedFaces: loadedFaces.length, loadedList: loadedFaces, paintedFamilyWeight: paintedFamilyWeight.size,
             paintedList: [...paintedFamilyWeight], files: fontFiles.length, fileList: fontFiles,
             fontBytes: fontFiles.reduce((a, f) => a + (f.transfer || 0), 0) },
    page: { heightPx: pageH, screens: +(pageH / vh).toFixed(2) },
    targets: { total: visInter.length, aboveFold: aboveFold.length, rawTotal: inter.length }
  };
})()
```

### 9.2 `cold.sh` — one fresh browser per URL (mandatory for weight)

```bash
#!/usr/bin/env bash
# usage: cold.sh <label> <url>
# Fresh browser session per URL => cold HTTP cache => honest transferSize.
set -u
D=<this metrics dir>; S=<screenshot dir>
LABEL=$1; URL=$2
export AGENT_BROWSER_SESSION="sx-metrics-$LABEL"
export AGENT_BROWSER_SCREENSHOT_DIR="$S"
ab() { agent-browser "$@"; }

ab set viewport 1440 900 >/dev/null
ab vitals "$URL" --json > "$D/vitals-$LABEL.json" 2>&1     # navigates cold + records LCP/CLS/FCP/TTFB
ab wait --load networkidle >/dev/null 2>&1
sleep 2
ab eval --stdin --json < "$D/probe.js" > "$D/cold-$LABEL-1440x900.json" 2>&1
ab screenshot "$S/$LABEL-1440x900.png" >/dev/null 2>&1
ab a11y --json > "$D/a11y-$LABEL.json" 2>&1

ab set viewport 390 844 >/dev/null
ab open "$URL" >/dev/null 2>&1
ab wait --load networkidle >/dev/null 2>&1
sleep 2
ab eval --stdin --json < "$D/probe.js" > "$D/cold-$LABEL-390x844.json" 2>&1
ab screenshot "$S/$LABEL-390x844.png" >/dev/null 2>&1
ab close >/dev/null 2>&1
```

Invocations used for this document:

```bash
./cold.sh prodhome        https://www.rediacc.com/en
./cold.sh prodpricing     https://www.rediacc.com/en/pricing
./cold.sh localhome       http://localhost:4321/en
./cold.sh localpricing    http://localhost:4321/en/pricing
./cold.sh claudehome      https://claude.com/
./cold.sh claudepricing   https://claude.com/pricing
./cold.sh anthropichome   https://www.anthropic.com/
./cold.sh anthropicpricing https://www.anthropic.com/pricing   # -> 301 to claude.com/pricing
```

### 9.3 `coverage.mjs` — real CSS coverage over CDP

```bash
export AGENT_BROWSER_SESSION=sx-metrics-cov
agent-browser open about:blank >/dev/null
CDP=$(agent-browser get cdp-url | sed -E 's#ws://([^/]+)/.*#http://\1#')
node coverage.mjs "$CDP" https://www.rediacc.com/en
```

```js
// Real CSS rule coverage via CDP (CSS.startRuleUsageTracking), the same engine
// DevTools' Coverage panel uses. Usage: node coverage.mjs <cdpHttpBase> <url>
// Requires Node >= 22 (global WebSocket). No dependencies.
const [, , base, url] = process.argv;

const list = await (await fetch(`${base}/json/list`)).json();
let page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
if (!page) throw new Error('no page target');

const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
const sheets = new Map(); // styleSheetId -> header
const send = (method, params = {}) =>
  new Promise((res, rej) => {
    const n = ++id;
    pending.set(n, { res, rej });
    ws.send(JSON.stringify({ id: n, method, params }));
  });

ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(m.error.message)) : res(m.result);
  } else if (m.method === 'CSS.styleSheetAdded') {
    sheets.set(m.params.header.styleSheetId, m.params.header);
  }
});
await new Promise((r) => ws.addEventListener('open', r));

await send('Page.enable');
await send('DOM.enable');
await send('CSS.enable');
await send('CSS.startRuleUsageTracking');
await send('Page.navigate', { url });
await new Promise((r) => setTimeout(r, 9000));
const delta = await send('CSS.takeCoverageDelta').catch(() => ({ coverage: [] }));
const { ruleUsage } = await send('CSS.stopRuleUsageTracking');
const usage = [...(delta.coverage || []), ...ruleUsage];

// Chrome only reports the rules that were USED. Unused bytes must be derived by
// subtracting used ranges from the full stylesheet text (this is exactly what
// the DevTools Coverage panel does).
const perSheet = new Map();
for (const [sid, h] of sheets) {
  let text = '';
  try { text = (await send('CSS.getStyleSheetText', { styleSheetId: sid })).text; } catch (e) { continue; }
  perSheet.set(sid, {
    url: h.sourceURL || `<inline #${h.startLine}:${h.startColumn}>`,
    bytes: text.length, usedBytes: 0, usedRules: 0, ranges: [],
  });
}
for (const r of usage) {
  const e = perSheet.get(r.styleSheetId);
  if (!e || !r.used) continue;
  e.ranges.push([r.startOffset, r.endOffset]);
}
for (const e of perSheet.values()) {
  e.ranges.sort((a, b) => a[0] - b[0]);
  let last = -1;
  for (const [s, en] of e.ranges) {
    e.usedRules++;
    const from = Math.max(s, last);
    if (en > from) { e.usedBytes += en - from; last = en; }
  }
  delete e.ranges;
}
const rows = [...perSheet.values()].filter((r) => r.bytes > 0).sort((a, b) => b.bytes - a.bytes);
const tot = rows.reduce((a, r) => ({ bytes: a.bytes + r.bytes, usedBytes: a.usedBytes + r.usedBytes, usedRules: a.usedRules + r.usedRules }),
  { bytes: 0, usedBytes: 0, usedRules: 0 });
for (const r of rows) r.unusedPct = +(100 * (1 - r.usedBytes / r.bytes)).toFixed(1);
console.log(JSON.stringify({ url, sheets: rows.length, total: tot,
  unusedBytePct: +(100 * (1 - tot.usedBytes / tot.bytes)).toFixed(1),
  perSheet: rows }, null, 1));
ws.close();
```

### 9.4 `detail.js` — fallback fonts, size/color histograms, headings

```js
(() => {
  const all = document.querySelectorAll('*');
  // 1. text painted in a bare fallback family (no webfont applied)
  const fallback = [];
  for (const el of all) {
    const direct = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim());
    if (!direct) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const fam = getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim();
    if (/^(sans-serif|serif|monospace|system-ui|-apple-system)$/.test(fam)) {
      fallback.push({ tag: el.tagName.toLowerCase(), cls: el.className.toString().slice(0, 60), fam, txt: el.textContent.trim().slice(0, 40) });
    }
  }
  // 2. above-fold interactive inventory (NAIVE — see hittest.js for the honest one)
  const sel = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [tabindex]:not([tabindex="-1"]), [onclick]';
  const vh = innerHeight;
  const af = Array.from(document.querySelectorAll(sel)).filter(el => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && r.top < vh && r.bottom > 0;
  }).map(el => ({ tag: el.tagName.toLowerCase(), txt: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 30),
                  inNav: !!el.closest('header,nav'), y: Math.round(el.getBoundingClientRect().top) }));
  // 3. sections + headings
  const sections = Array.from(document.querySelectorAll('main > *, main section, main > div > section'));
  const h = { h1: document.querySelectorAll('h1').length, h2: document.querySelectorAll('h2').length,
              h3: document.querySelectorAll('h3').length, h4: document.querySelectorAll('h4').length };
  // 4/5. histograms
  const fs = {}, col = {}, bg = {}, rad = {};
  for (const el of all) {
    const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    fs[cs.fontSize] = (fs[cs.fontSize] || 0) + 1;
    col[cs.color] = (col[cs.color] || 0) + 1;
    if (cs.backgroundColor !== 'rgba(0, 0, 0, 0)') bg[cs.backgroundColor] = (bg[cs.backgroundColor] || 0) + 1;
    if (cs.borderRadius !== '0px') rad[cs.borderRadius] = (rad[cs.borderRadius] || 0) + 1;
  }
  const sortObj = o => Object.entries(o).sort((a, b) => b[1] - a[1]);
  return {
    url: location.href,
    fallbackTextNodes: fallback.length, fallbackSample: fallback.slice(0, 12),
    aboveFold: { n: af.length, inNav: af.filter(x => x.inNav).length, list: af },
    sections: sections.length, headings: h,
    fontSizes: sortObj(fs), colors: sortObj(col), bgs: sortObj(bg), radii: sortObj(rad)
  };
})()
```

### 9.5 `hittest.js` and `boxes.js`

`hittest.js` — the **honest** above-fold count (use this, not `probe.js`'s
`targets.aboveFold`):

```js
(() => {
  // Interactive targets that are genuinely CLICKABLE above the fold:
  // visible box + non-zero effective opacity + wins the hit test at its own centre.
  const sel = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [tabindex]:not([tabindex="-1"]), [onclick]';
  const vh = innerHeight, vw = innerWidth;
  const effOpacity = (el) => { let o = 1, n = el; while (n && n.nodeType === 1) { o *= parseFloat(getComputedStyle(n).opacity || '1'); n = n.parentElement; } return o; };
  const out = [];
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (r.top >= vh || r.bottom <= 0 || r.left >= vw || r.right <= 0) continue;
    if (effOpacity(el) < 0.05) continue;
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), vw - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, 1), vh - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!hit || !(el.contains(hit) || hit.contains(el))) continue;
    out.push({ tag: el.tagName.toLowerCase(), txt: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().replace(/\s+/g, ' ').slice(0, 32),
               region: el.closest('header') ? 'header' : el.closest('nav') ? 'nav' : el.closest('footer') ? 'footer' : 'body',
               y: Math.round(r.top) });
  }
  const byRegion = {};
  out.forEach(o => byRegion[o.region] = (byRegion[o.region] || 0) + 1);
  return { url: location.href, vw, vh, clickableAboveFold: out.length, byRegion, list: out };
})()
```

`boxes.js` — boxed-surface census (T9/T10) and decoration vocabulary:

```js
(() => {
  // "Boxed containers": rendered block elements >=80x40 that visually separate
  // themselves from their parent with a border, a shadow, or a different
  // background. This is the surface count a reader has to parse per screen.
  const isBox = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (r.width < 80 || r.height < 40) return false;
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const hasShadow = cs.boxShadow && cs.boxShadow !== 'none';
    const bw = ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth']
      .map(k => parseFloat(cs[k]) || 0);
    const hasBorder = bw.some(v => v > 0);
    const p = el.parentElement;
    const pbg = p ? getComputedStyle(p).backgroundColor : 'rgba(0, 0, 0, 0)';
    const ownBg = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== pbg;
    return hasShadow || hasBorder || ownBg;
  };
  const boxes = [], radii = new Set(), shadows = new Set(), borders = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (!isBox(el)) continue;
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    boxes.push({ tag: el.tagName.toLowerCase(), w: Math.round(r.width), h: Math.round(r.height),
                 radius: cs.borderRadius, shadow: cs.boxShadow.slice(0, 40), bg: cs.backgroundColor });
    if (cs.borderRadius !== '0px') radii.add(cs.borderRadius);
    if (cs.boxShadow !== 'none') shadows.add(cs.boxShadow);
    if (parseFloat(cs.borderTopWidth) > 0) borders.add(cs.borderTopWidth + ' ' + cs.borderTopStyle + ' ' + cs.borderTopColor);
  }
  const pageH = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  return { url: location.href, boxes: boxes.length, boxesPerScreen: +(boxes.length / (pageH / innerHeight)).toFixed(1),
           distinctRadii: radii.size, distinctShadows: shadows.size, distinctBorderStyles: borders.size,
           radiiList: [...radii], shadowList: [...shadows].map(s => s.slice(0, 60)),
           pageH, screens: +(pageH / innerHeight).toFixed(2) };
})()
```

### 9.6 Cross-origin byte fallback (anthropic.com)

When Resource Timing reports `transferSize: 0` (no `Timing-Allow-Origin`), pull
the URL list from CDP and refetch:

```bash
agent-browser network requests --json > net.json
python3 -c "
import json
for r in json.load(open('net.json'))['data']['requests']:
    print(r.get('resourceType','?'), r.get('url'))
" | sort -u > urls.txt
while read -r t u; do
  echo \"$t $(curl -sSL --compressed -o /dev/null -w '%{size_download}' \"$u\") $u\"
done < urls.txt
```

`--compressed` yields **decoded** bytes. The Webflow CDN did not honour a
hand-set `Accept-Encoding` in this environment, so a wire-byte figure obtained
this way must be labelled an upper bound.

### 9.7 Source-side counts used above

```bash
cd packages/www
ls -l src/i18n/translations/*.json | awk '{s+=$5} END {print s}'          # 9284710
grep -rhoE "^\s*--[a-zA-Z0-9-]+\s*:" src/styles public/styles src/layouts src/components \
  | sed -E 's/\s|://g' | sort -u | wc -l                                   # 229 distinct
grep -rhcE "^\s*--[a-zA-Z0-9-]+\s*:" src/styles/*.css public/styles/*.css | paste -sd+ | bc   # 348
curl -sSL --compressed https://www.rediacc.com/en \
  | grep -oE '<link[^>]*rel="stylesheet"[^>]*>' | sed -E 's/.*href="([^"]*)".*/\1/'  # 9 sheets
```

### 9.8 Screenshot inventory (evidence)

All under
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-metrics/`:

| File | What it shows |
|---|---|
| `hprod-fold-1440x900.png` | our fold — clean, 15 clickable targets |
| `hclaude-fold-1440x900.png`, `hanth-fold-1440x900.png` | their folds |
| `fprod-full-1440.png` | our whole homepage, 6,794 px, 14 sections, 60 boxes |
| `fclaude-full-1440.png` | claude.com whole homepage, 4,104 px, 6 sections |
| `fanth-full-1440.png` | anthropic.com whole homepage, 3,211 px, 0 shadows |
| `prodhome-390x844.png`, `claudehome-390x844.png`, `anthropichome-390x844.png` | mobile |
| `prodpricing-*`, `claudepricing-*` | pricing, both viewports |

---

## 10. Open questions for the operator

1. **Do you want the 6.67 MB locale chunk fixed inside this simplification
   program, or as a separate build-side change?** It is by far the largest single
   number in this study, it is not a design decision, and nobody on this fleet
   owns `src/i18n/`. My recommendation: it rides this program, because "the site
   feels heavy" and "we ship 13 languages to every visitor" are the same
   complaint. *(Default if unanswered: include it, and assign it to whoever takes
   `sx-chrome`, since the islands that pull it are the nav and footer.)*
2. **Is a 2× shorter homepage acceptable content-wise?** T11/T16 mean deleting
   roughly half the page — most obviously the five near-identical before/after
   blocks in "The Difference". That is a marketing call, not a CSS one.
3. **Are 43 painted colors the result of a light/dark dual palette?** Our
   homepage renders a dark hero band inside a light page. If T4 (≤16 colors) is
   to be measured fairly it may need to be measured per theme
   (`agent-browser set media dark|light`). I did not split it; say the word and
   I will re-baseline both themes before implementation starts.
