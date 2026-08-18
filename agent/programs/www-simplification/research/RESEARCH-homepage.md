# RESEARCH — homepage body (below the fold)

**Domain:** everything on `http://localhost:4321/en` below `.sp-hero`.
**Agent:** `sx-homepage`. **Date:** 2026-08-17.
**Browser session:** `sx-homepage`. Screenshots:
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-homepage/`

---

## 1. Verdict

The homepage is **7,697px / 8.6 screens tall on desktop and 14,496px / 17.2 screens on
mobile**, versus 4,104px (claude.com) and 3,217px (anthropic.com) — we are **1.9× claude.com
and 2.4× anthropic.com**, and on mobile **2.2× both**. It is not long because it says more:
the entire body carries **623 words across 9 sections**, and one section (`home-difference`,
2,202px = 29% of the page) spends 2,202 pixels on **73 words and 6 clipart SVGs**. The page
makes **one argument four times** — "your test copy is stale and partial, ours is a whole
instant copy" is restated by `sp-why-now`, `sp-not-a-slice`, `home-difference`, and
`metrics-bar` — and it ships **two chip strips of the same idea** (`logo-wall` and
`integrations-strip`) 3,451px apart. The single highest-leverage move is to **delete
`home-difference`'s illustration rows, `logo-wall`, and `metrics-bar` outright and collapse
the four repetitions into one section**, which alone removes ~2,900px (38% of the page) and
~230 lines of CSS without deleting a single distinct claim.

---

## 2. What we have

### 2.1 The real component tree (the task brief's guess was wrong)

`src/pages/[lang]/index.astro` is 39 lines and renders exactly one component
(`index.astro:38`): `SPHomePage`. The section list lives at
`src/components/solution-pages/SPHomePage.astro:44-58`:

| # | Rendered by | Wrapper (12 lines each, pure pass-through) | Real component |
|---|---|---|---|
| 0 | `SPHero` | — | `solution-pages/SPHero.astro` (86 lines) — **sx-hero's** |
| 1 | `SPHomeWhyNow` | — | `solution-pages/SPHomeWhyNow.astro` (161 lines) |
| 2 | `SPHomeLogoWall` | `SPHomeLogoWall.astro` | `components/LogoWall.tsx` (31 lines) |
| 3 | `SPHomeNotASlice` | — | `solution-pages/SPHomeNotASlice.astro` (249 lines) |
| 4 | `SPHomeBeforeAfter` | `SPHomeBeforeAfter.astro` | `components/HomeDifference.astro` (182 lines) |
| 5 | `SPHomeMetricsBar` | `SPHomeMetricsBar.astro` | `components/MetricsBar.astro` (23 lines) |
| 6 | `SPHomeIntegrationsStrip` | `SPHomeIntegrationsStrip.astro` | `components/IntegrationsStrip.astro` |
| 7 | `SPHomePricingPreview` | `SPHomePricingPreview.astro` | `components/PricingPreview.astro` |
| 8 | `SPHomeBottomCta` | — | `SPHomeBottomCta.astro` (31 lines, inline) |

**Six of the nine sections go through a 12-line `SPHome*.astro` wrapper that does nothing
but forward `lang`** (`SPHomeLogoWall.astro`, `SPHomeBeforeAfter.astro`,
`SPHomeMetricsBar.astro`, `SPHomeIntegrationsStrip.astro`, `SPHomePricingPreview.astro`,
plus `SPHomeBeforeAfter` renaming `HomeDifference`). That is 60 lines of indirection and
a naming mismatch (`BeforeAfter` → `HomeDifference` → `.home-difference` → heading "The
Difference") that costs a grep every time someone looks for this section.

**Components the task brief listed that are NOT on the homepage** (verified by
`grep -rl <component> src --include=*.astro --include=*.tsx`):

- `FAQSection.astro` — only `pricing.astro`, `disaster-recovery.astro`.
- `PlatformTabs.tsx` — only `InstallMethods.tsx`, `DownloadsList.tsx`.
- `NewsletterSignup.tsx`, `NewsletterReturnPopup.tsx`, `LeadMagnetModal.tsx` — mounted by
  `BaseLayout.astro` / `Footer.tsx`, but **absent from the homepage DOM at rest** (measured:
  `querySelector` returns `null` for all three). They are not a homepage weight problem.
- `CorporateGuarantee.astro` — *is* on the page, nested inside `PricingPreview.astro`. It is
  the one-line "If Rediacc doesn't work for you, we'll help you migrate back." strip visible
  in `shots/sx-homepage/desk-5950.png`.

### 2.2 Measured section inventory (1440×900, after a full scroll to the bottom)

Measured via `getBoundingClientRect()` + `textContent` on `.sp-page`'s children. Word counts
use `textContent`, not `innerText`, because `.reveal` sections return empty `innerText`
before their scroll animation fires — a first pass with `innerText` reported `closing-cta`
as "1 word".

| # | class | Heading | Top px | Height px | Words | img+svg | px/word | Earns its place? |
|---|---|---|---|---|---|---|---|---|
| 0 | `sp-hero` | Clone Production. Break Nothing. | 0 | **910** | 117 | 1 | 8 | sx-hero's call |
| 1 | `sp-why-now` | Your world moves fast. Your test copy doesn't. | 910 | **786** | 88 | 3 | 9 | **Move to subpage** |
| 2 | `logo-wall` | Works with your infrastructure | 1696 | **144** | 4 | 0 | 36 | **DELETE** |
| 3 | `sp-not-a-slice` | Most tools copy one piece. We copy all of it. | 1840 | **892** | 101 | 5 | 9 | **Keep** (the differentiator) |
| 4 | `home-difference` | The Difference | 2732 | **2202** | 73 | 6 | **30** | **Cut to ~1/4** |
| 5 | `metrics-bar` | *(no heading)* | 4934 | **213** | 21 | 0 | 10 | **DELETE / fold in** |
| 6 | `integrations-strip` | Works with what you already run | 5147 | **307** | 40 | 0 | 8 | **Keep** |
| 7 | `cf-pricing-section` | Clear pricing. No surprises. | 5454 | **1251** | 142 | 0 | 9 | **Keep** |
| 8 | `closing-cta` | Ready to Clone Your First Stack? | 6705 | **360** | 37 | 0 | 10 | **Keep** |
| | | **TOTAL body** | | **7,065** | **623** | 15 | | |

Plus `header` 56px (fixed) and `footer` 632px → `document.documentElement.scrollHeight` =
**7,697px = 8.55 screens** at 900px.

> **Important measurement trap, recorded for the implementation session.** The page **grows
> as you scroll it**: a first measurement from a fresh load reported 6,794px, because
> `home-difference` was 931px until its four `loading="lazy"` illustrations resolved, after
> which it became **2,202px**. Always scroll to the bottom before measuring. Also: the black
> rounded chip visible at the bottom-centre of every desktop screenshot is
> `<astro-dev-toolbar>` (confirmed via `document.elementFromPoint(712,890)`), **not** site
> content — do not chase it.

### 2.3 Repetition — the page makes one argument four times

Regex counts over `.sp-page` `textContent` (623 words total):

| Claim | Occurrences | Where |
|---|---|---|
| copy / clone / fork | **27** | every section |
| "60 seconds" / "under a minute" / "in seconds" / "4.7s" / "46s" | **11** | hero, why-now, not-a-slice, difference ×3, metrics ×2 |
| kubernetes / cluster | **14** | hero, why-now, not-a-slice, integrations |
| recovery / restore | 5 | why-now, difference, metrics |
| "0 bytes" / "no extra storage" | 4 | hero, not-a-slice, difference, metrics |

The structural repetition is worse than the word counts suggest. Four sections carry the
**same four claim-pairs**:

| Claim | `sp-why-now` | `sp-not-a-slice` | `home-difference` | `metrics-bar` |
|---|---|---|---|---|
| Test copy is slow/stale | "Devs are 10× faster" | "Dev-box tools" | "A perfect copy in 60 seconds." | "241 GB / copied in under 60 seconds" |
| Backups don't verify | — | "Backup tools" | "Hourly backups. No extra storage." | "0 bytes / extra storage" |
| Recovery is untested | "Hackers are 10× faster" | "Database tools" | "Recovery tested in 60 seconds." | "< 1 min / recovery time" |
| K8s is a special case | "Your setup is split" | "Kubernetes tools" | "Every dev gets a fresh copy." | "46s / whole Kubernetes cluster fork" |

`metrics-bar` is a pure restatement: all four of its numbers are already stated as prose in
`home-difference` 2,200px above it, and two of them are already in the hero terminal
(`index.astro:16-25`).

**`logo-wall` is strictly subsumed by `integrations-strip`.** Its six categories
(`en.json` `logoWall.categories`: Git, CI/CD, Containers, Databases, Monitoring, Storage)
each have at least one concrete instance in `integrations.items` (Git→Git/GitLab,
CI/CD→Jenkins, Containers→Docker/Kubernetes/k3s, Databases→PostgreSQL/MySQL/MariaDB,
Monitoring→Prometheus, Storage→S3/btrfs/Ceph). Two chip strips saying "works with your
stuff", 3,451px apart, the abstract one first. See `shots/sx-homepage/desk-1700.png`
(logo-wall chips) and `desk-5100.png` (integrations chips).

### 2.4 CTAs

11 links/buttons in the body (excluding the 6 image-zoom buttons, which have `aria-label`
only), of which **4 are the same signup action** under 3 different labels:

`Start free trial` (hero) · `Read the Docs →` (hero) · `Monthly`/`Annual` (pricing toggle) ·
`Start free trial` ×2 (pricing) · `Contact sales` · `Compare all plans and features →` ·
`Install Rediacc Free` (closing) · `Talk to Sales` (closing).

"Start free trial" ×3 and "Install Rediacc Free" are one destination with three names.

### 2.5 Density and the illustration problem

`home-difference` is the page's centre of gravity and its worst offender:

- **2,202px for 73 words** (30 px/word, versus 8-10 px/word everywhere else).
- Structure (`HomeDifference.astro:54-91`): a two-up `problem.svg` → `solution.svg` lead
  block, then **four alternating full-width rows**, each one line of problem text, one line
  of solution text, and one 800×450 clipart SVG.
- The SVGs are flat clipart — a calendar reading "30", a person lying on a bench, a cracked
  red square, green document icons with checkmarks (see `desk-2550.png`, `desk-3400.png`,
  `desk-4250.png`). They illustrate sentences that already stand alone.
- It ships an interactive **zoom lightbox** for those clipart images: a `<dialog>`
  (`HomeDifference.astro:95-98`), 22 lines of client script (`:160-182`), and 6 CSS rules
  (`main.css:2367-2437`). Nothing on claude.com or anthropic.com has an equivalent.

CSS footprint of the cut candidates:

| Section | `public/styles/main.css` | Inline `<style>` | Client JS |
|---|---|---|---|
| `home-difference` + `difference-*` + zoom dialog | **2291-2437** (~147 lines, 24 rules) | `HomeDifference.astro:100-158` (59 lines) | `:160-182` (22 lines) |
| `logo-wall` | **1641-1676** (~36 lines, 5 rules) | — | — |
| `metrics-bar` | **2438-2485** (~48 lines) | — | — |
| `sp-why-now` | (component-scoped) | `SPHomeWhyNow.astro` (92 lines) | — |

### 2.6 Mobile (390×844)

**14,496px = 17.2 screens.** Every card grid collapses to one column, so the 3-card, 4-card,
and 4-row grids become 3, 4, and 4 full stacks:

| Section | Mobile height | vs desktop |
|---|---|---|
| `sp-hero` | 1,201 | 1.3× |
| `sp-why-now` | 1,363 | 1.7× |
| `logo-wall` | 196 | 1.4× |
| `sp-not-a-slice` | 1,832 | 2.1× |
| `home-difference` | **4,059** | 1.8× |
| `metrics-bar` | 368 | 1.7× |
| `integrations-strip` | 632 | 2.1× |
| `cf-pricing-section` | 2,422 | 1.9× |
| `closing-cta` | 559 | 1.6× |

`home-difference` alone is **4.8 mobile screens**. See `shots/sx-homepage/mobile-full.png`.

### 2.7 Scroll experience — where attention breaks

Walked at 850px steps (`desk-0` … `desk-6100.png`):

1. **0-910** hero: one focal point, works.
2. **910-1696** why-now: three icon cards + a pull-quote. Second focal point of the same idea.
3. **1696-1840** logo-wall: a 144px chip strip wedged between two big sections. It reads as a
   page-break artifact, not a section — in `desk-1700.png` it sits directly under the fixed
   nav with no heading of its own, looking like part of the chrome.
4. **1840-2732** not-a-slice: four cards + a green "REDIACC" callout. Strongest section.
5. **2732-4934** the difference: **attention breaks here.** Four near-identical
   left-image/right-image rows scrolling for 2.4 screens. By row 3 the reader is pattern-
   matching, not reading. This is also where a reader on mobile spends 4.8 screens.
6. **4934-5147** metrics: four numbers restating what was just read.
7. **5147-5454** integrations: the *second* chip strip. A reader who noticed the first one
   experiences this as déjà vu.
8. **5454-6705** pricing: works, this is the payload.
9. **6705-7065** closing CTA, then a 632px footer.

The page has **no altitude change**: sections 2, 4, 5, 6 are all "here are N boxes that
each restate the thesis". claude.com changes job every section (convert → compare → object-
handle); we change only the box count.

### 2.8 Content at the wrong altitude

`integrations-strip`'s body paragraph (`en.json` `integrations.migrationMessage`) is docs
prose on a marketing page:

> "Rediacc bundles your apps, databases, and settings into one file. Move it anywhere.
> Already on Docker? You're most of the way there. Running Kubernetes? Fork or move the
> whole cluster the same way."

Three sentences of migration guidance above a chip row. The chips alone make the point; the
paragraph belongs in `/docs/quick-start`.

---

## 3. Correctness: fabricated social proof

**Good news, stated plainly: there is no fabricated social proof on this page.**

- **No testimonials.** `grep -n "testimonial\|customerLogo\|trustedBy\|customers\":"
  src/i18n/translations/en.json` → **zero matches**. `SPSocialProof.astro` exists in the
  repo but is **not rendered by `SPHomePage.astro`**.
- **No customer logos.** `LogoWall.tsx` is misleadingly named — the term normally means a
  customer logo wall, but `LogoWall.tsx:20-24` renders `logoWall.categories`, which are the
  six **technology categories** Git / CI/CD / Containers / Databases / Monitoring / Storage.
  No company names, no logos, no counts. `integrations-strip` likewise lists only
  third-party technology names (Docker, PostgreSQL, Prometheus…), which is a compatibility
  claim, not a customer claim.

**But there are two real correctness problems with the metrics, which I am flagging
separately from the simplification argument:**

1. **The page states two mutually inconsistent figures for the same capability.** The hero
   terminal (`src/pages/[lang]/index.astro:16-18`) shows
   `Cloning production (3.2 TB) … done in 4.7s`, while `metrics-bar` 4,934px below shows
   **"241 GB / copied in under 60 seconds"**. 3.2 TB in 4.7s is ~170× faster per byte than
   241 GB in 60s. Both are on the same screen-scroll; a technical reader will notice.
2. **"241 GB" has no provenance anywhere in the repo.** It appears 5 times, all of them in
   `packages/www/src/i18n/translations/en.json` (lines 299, 582, 2726, 2762, 2916), and
   `grep -rn "241 ?GB" --include=*.md --include=*.ts --include=*.json .` finds **nothing
   outside the translation file** — no benchmark, no test output, no doc. It is a
   specific-looking number with no measurement behind it.

For contrast, **"46s / whole Kubernetes cluster fork" is real** — it is corroborated by the
Ceph/K8s campaign record ("cluster fork 46s / migrate 16s cutover"). And "0 bytes extra
storage" is true by construction (BTRFS reflink CoW). So the fix is not to strip the
numbers, it is to **cite them or drop the two that cannot be cited**. Deleting `metrics-bar`
(recommended below on simplification grounds) resolves the contradiction as a side effect,
but the hero's `3.2 TB / 4.7s` and the three other `241 GB` uses in `en.json` still need an
owner. **This is not fixed by the simplification and must not be lost.**

---

## 4. What claude.com and anthropic.com do

Measured live at 1440×900 and 390×844 by a delegated read-only browser session
(`sx-homepage-ref`), scrolled to the bottom before measuring. Screenshots:
`scratchpad/shots/sx-homepage-ref/`.

### claude.com — container `<main id="main-content">`, 3 body sections

| # | Heading | Height px | Top px | Words |
|---|---|---|---|---|
| 0 | "Think fast, build faster" (hero, contains a sign-in card) | 876 | 0 | 31 |
| 1 | "Explore plans" (Free / Pro / Max) | 1,477 | 876 | 174 |
| 2 | "FAQ" (accordion, collapsed) | 681 | 2,353 | 143 |

Total **4,104px / 4.56 screens**; mobile 6,608px / 7.8 screens. Header 84px, footer 1,070px.
~10 genuine CTAs. **Three sections, three different jobs**: convert (sign in), compare
(pricing), handle objections (FAQ). No "why now", no differentiator essay, no illustration
rows. Visually: one cream background the whole way down, one focal point per screen, and a
large serif display face doing the work that our clipart does.

### anthropic.com — container `<main class="page_wrap">`, 4 body sections

| # | Heading | Height px | Top px | Words (visible) |
|---|---|---|---|---|
| 0 | "AI research and products that put safety at the frontier" (hero) | **390** | 68 | 42 |
| 1 | "Anthropic is built on hard questions." | 767 | 458 | ~41 |
| 2 | "Latest releases" (3 cards) | 604 | 1,226 | 86 |
| 3 | "we build AI to serve humanity's long-term well-being." | 458 | 1,830 | 28 |

Total **3,217px / 3.57 screens**; mobile 6,391px / 7.6 screens. Nav 68px, footer 923px. 8
unique CTAs across 5 labels.

**The anthropic hero's "special component"** (the operator's phrase): the hero is only
**390px tall** and contains exactly one `<h1>`, one `<p>`, and **zero images, SVGs, videos,
or canvases**. Its only two interactive elements are **inline underlined text links embedded
inside the headline itself** — "research" → `/research`, "products" →
`claude.com/product/overview`. There is no CTA button. The headline animates word by word
(one `<span>` per word, plus a `u-sr-only` duplicate for screen readers). The one dramatic
visual on the whole page is the section *below* it: a full-bleed rounded black panel with a
scroll-driven particle-network animation. That is `sx-hero`'s finding to act on, but it is
the key to the height numbers: **anthropic's entire hero is 43% the height of ours**, and
their most striking component is one animation on an otherwise typographic page.

---

## 5. The delta

| Metric | **Rediacc /en** | claude.com | anthropic.com | Gap |
|---|---|---|---|---|
| Desktop page height | **7,697px** | 4,104px | 3,217px | **+88% / +139%** |
| Screens @ 900px | **8.55** | 4.56 | 3.57 | +4.0 / +5.0 screens |
| Mobile height (390×844) | **14,496px** | 6,608px | 6,391px | **+119% / +127%** |
| Mobile screens | **17.2** | 7.8 | 7.6 | +9.4 / +9.6 |
| Body sections | **9** | 3 | 4 | +6 / +5 |
| Body words | **623** | 348 | 197 | +79% / +216% |
| Tallest single section | **2,202px** (`home-difference`) | 1,477px (pricing) | 767px | — |
| px per word, worst section | **36** (`logo-wall`), **30** (`home-difference`) | ~8 | ~19 | — |
| Body CTAs | 11 (4 = same signup) | ~10 | 8 | comparable |
| Distinct card/chip grid patterns | **6** | 2 | 1 | +4 |
| Sections restating one thesis | **4** | 0 | 0 | +4 |
| Chip strips of integrations | **2** | 0 | 0 | +2 |
| Footer height | 632px | 1,070px | 923px | **we are smallest** |
| Illustrations in body | 15 img+svg | ~0 in hero/pricing | 0 in hero | — |

Two things fall out of this table that are worth saying out loud:

1. **Our footer is not the problem** — it is smaller than both references. The length is all
   in the body.
2. **We are long without being wordy.** 623 words in 7,697px means the page is mostly
   pictures and padding. claude.com fits 348 words in 4,104px. The cure is not "write less
   copy", it is "stop drawing".

---

## 6. Proposed simplification, ordered by leverage

### P1 — Delete `home-difference`'s illustration rows; keep the four claim-pairs as text
**Saves ~1,600px desktop / ~3,000px mobile. The single biggest win on the page.**

- **Change:** replace the two-up lead + four alternating illustrated rows with a single
  4-item problem→solution grid (text only, or one shared illustration for the whole
  section). Drop the zoom lightbox entirely.
- **Files:** `src/components/HomeDifference.astro` (all 182 lines rewritten; delete
  `:54-69` two-up, `:71-91` rows, `:95-98` `<dialog>`, `:100-158` inline style,
  `:160-182` script). `public/styles/main.css:2291-2437` (~147 lines, 24 rules) deleted.
  `src/components/solution-pages/SPHomeBeforeAfter.astro` collapses into the call site.
- **Risk:** low. The illustrations are decorative; every row's meaning is in its two lines
  of text, verified by reading `beforeAfter.before.points` / `after.points` in `en.json`.
  The section is not linked from anywhere (no anchor).
- **Watch out:** `resolveSolutionIllustration` (`src/utils/solution-illustration.ts`) and
  the `public/assets/images/problem*.svg` / `solution*.svg` assets are **also used by the
  solution pages** — do not delete the assets or the util, only this consumer.
- **Prove it:** re-measure `.home-difference` height at 1440×900 and 390×844 after a
  full scroll; expect ≤600px / ≤1,100px. Re-run the section-inventory eval and confirm
  total ≤6,100px.

### P2 — Delete `logo-wall` outright
**Saves 144px desktop / 196px mobile, and removes a duplicate idea.**

- **Change:** remove `<SPHomeLogoWall lang={lang} />` from `SPHomePage.astro:52`, delete
  `src/components/solution-pages/SPHomeLogoWall.astro` and `src/components/LogoWall.tsx`,
  delete `public/styles/main.css:1641-1676`.
- **Risk:** low, but it **orphans the `logoWall.*` keys in all 13 locale files** — see §7.
- **Prove it:** `grep -rn "LogoWall" src` returns nothing; `.logo-wall` absent from the
  rendered DOM; `npm run check:i18n` still passes after the key removal.

### P3 — Delete `metrics-bar`; attach its two citable numbers to the P1 grid
**Saves 213px desktop / 368px mobile, and resolves the 241 GB contradiction.**

- **Change:** remove `<SPHomeMetricsBar lang={lang} />` from `SPHomePage.astro:55`, delete
  `SPHomeMetricsBar.astro` + `src/components/MetricsBar.astro`, delete
  `public/styles/main.css:2438-2485`. Carry **"0 bytes extra storage"** and **"46s whole
  Kubernetes cluster fork"** (both defensible) into the P1 grid as inline emphasis. Do
  **not** carry "241 GB" forward.
- **Risk:** low mechanically; the judgement is whether four big numbers are load-bearing for
  conversion. Neither reference site has a metrics bar.
- **Prove it:** the string "241 GB" no longer appears in the rendered homepage
  (`document.body.textContent.includes('241 GB') === false`).

### P4 — Move `sp-why-now` off the homepage
**Saves 786px desktop / 1,363px mobile.**

- **Change:** remove `<SPHomeWhyNow lang={lang} />` from `SPHomePage.astro:51`. The
  component (161 lines, 92 of them inline CSS) moves to a solutions/why-now page or a blog
  post rather than being deleted — its "AI made devs and attackers 10× faster" framing is
  real content, just not homepage content.
- **Risk:** **medium, and this is the one genuine judgement call** — see §8. It is the page's
  emotional hook. Both reference homepages have zero equivalent, which is the argument for
  moving it; the counter-argument is that Anthropic does not need to explain why now.
- **Prove it:** homepage total ≤5,300px; the moved page renders with its styles intact
  (the inline `<style>` travels with the component, so no CSS surgery needed).

### P5 — Trim `integrations-strip` to chips only
**Saves ~100px, and removes docs prose from a marketing page.**

- **Change:** drop the `integrations.migrationMessage` paragraph from
  `src/components/IntegrationsStrip.astro`; keep the title and the 15 chips. The migration
  guidance belongs in `/docs/quick-start`.
- **Risk:** low. **Prove it:** section ≤200px; chips still 15.

### P6 — Collapse the six 12-line pass-through wrappers
**Saves 0px of page height; saves a grep every time.**

- **Change:** delete `SPHomeLogoWall.astro`, `SPHomeBeforeAfter.astro`,
  `SPHomeMetricsBar.astro`, `SPHomeIntegrationsStrip.astro`, `SPHomePricingPreview.astro`
  and import the real components directly in `SPHomePage.astro`. Rename
  `HomeDifference.astro` → the section it actually is, so the chain
  `BeforeAfter → HomeDifference → .home-difference → "The Difference"` stops having four
  names for one thing.
- **Risk:** none functionally; it is a rename. Do it in the same pass as P1-P3 so the
  imports are only touched once.
- **Prove it:** `npm run build` clean; `grep -rn "SPHome" src` returns only the surviving
  three.

### P7 — One label for one action
- **Change:** "Start free trial" (×3) and "Install Rediacc Free" (closing CTA) are one
  destination. Pick one string; `getStarted.cta.primary` in `en.json` is the outlier.
- **Risk:** low, but it is a **13-locale copy change** — see §7.

### The proposed shorter page (ordered list of what survives)

| # | Section | Now | After | Why it survives |
|---|---|---|---|---|
| 1 | `sp-hero` | 910 | 910 (sx-hero's call) | The promise |
| 2 | `sp-not-a-slice` — "Most tools copy one piece. We copy all of it." | 892 | ~700 | The **only** section that states the differentiator rather than the benefit |
| 3 | `home-difference` — 4 problem→solution pairs, text, with the 2 citable numbers inline | 2,202 + 213 | ~600 | The proof, at one-quarter the cost |
| 4 | `integrations-strip` — chips only | 307 | ~200 | "It works with what I already run" is the top objection |
| 5 | `cf-pricing-section` | 1,251 | 1,251 | claude.com's biggest section is pricing too |
| 6 | `closing-cta` | 360 | 360 | The ask |
| | **Body total** | **7,065** | **~4,021** | |
| | **Page total (+56 header, +632 footer)** | **7,697 / 8.55 screens** | **~4,709 / 5.2 screens** | |

**Deleted outright:** `logo-wall` (144px), `metrics-bar` (213px), `home-difference`'s
two-up block + 4 illustration rows + zoom lightbox (~1,600px), six pass-through wrappers,
~231 lines of `main.css`, 22 lines of client JS, one `<dialog>`.
**Moved to a subpage:** `sp-why-now` (786px, 161 lines).

That lands us at **~5.2 screens desktop** — within a screen of claude.com's 4.56 — and
roughly **9 screens on mobile**, down from 17.2. If the operator also takes P4's why-now
move as a delete rather than a move, and `sx-hero` shortens the hero toward anthropic's
390px, the page reaches claude.com's number exactly.

---

## 7. Cross-domain consequences

Named, not fixed.

- **i18n (13 locales, all of them).** P2/P3/P4/P7 orphan or change these key groups in
  `packages/www/src/i18n/translations/*.json`: `logoWall.*` (title + 6 categories),
  `metrics.items[]` (4 objects), the `whyNow.*` group, `integrations.migrationMessage`, and
  `getStarted.cta.primary`. English is the source of truth; per the repo convention any
  English value change requires `npm run i18n:generate-hashes`, and
  `check-i18n-naturalization` is a **blocking gate** that fires when an already-naturalized
  key goes stale. Deletions must be applied to all 13 locale files, and the locale set must
  be derived from `@rediacc/locales`, not hand-listed. **This is the largest hidden cost of
  the simplification and it belongs to whoever owns i18n, not to me.**
- **`sx-tokens` / CSS.** P1-P3 delete ~231 lines and 33 rules from
  `public/styles/main.css` (1641-1676, 2291-2485). Those line numbers will shift under any
  other edit to that file — coordinate ordering, or do the deletions by selector, not by
  line range.
- **`sx-hero`.** (a) The hero terminal at `src/pages/[lang]/index.astro:16-25` claims
  `3.2 TB … 4.7s`, which contradicts `metrics-bar`'s `241 GB / under 60 seconds`. If I
  delete `metrics-bar` the visible contradiction goes, but the hero's number is still
  uncited. (b) anthropic's hero is **390px** against our 910px; that measurement is theirs
  to act on and is in §4 for them.
- **`sx-chrome`.** `CorporateGuarantee.astro` renders inside `PricingPreview.astro`, so a
  chrome-side change to it lands on the homepage. Also: `BaseLayout.astro` mounts
  `NewsletterReturnPopup` and `LeadMagnetModal`, and `ImageModal` leaves an always-mounted
  full-viewport `.image-modal` div in the DOM (`opacity:0; pointer-events:none` — inert, but
  present on every page).
- **Solution pages.** `resolveSolutionIllustration` and
  `public/assets/images/{problem,solution}*.svg` are shared with the solution pages. P1
  removes a *consumer*, not the assets. Whoever owns solution pages should know the
  homepage stops being a user of four `rowSlugs` illustrations
  (`environment-cloning`, `backup-verification`, `instant-recovery`, `production-parity`).

---

## 8. Open questions for the operator

1. **`sp-why-now` (786px): move to a subpage, or delete?** It is the page's only emotional
   argument ("AI made devs and attackers 10× faster; your test copy did not keep up").
   Neither claude.com nor anthropic.com has anything like it. My recommendation is **move it
   to a subpage** rather than delete, so the writing is not lost. Genuine call, because it
   is a positioning decision, not a layout one.
2. **The "241 GB" figure.** It appears 5× in `en.json` with no source anywhere in the repo,
   and it contradicts the hero's "3.2 TB in 4.7s". Do you have a measurement behind either
   number? If yes, cite it and keep the stronger one. If not, both should go. I am not
   guessing a replacement.
3. **Does the homepage want an FAQ?** claude.com's third and final section is one (681px),
   and we already have `FAQSection.astro` built and running on `/pricing`. Adding it cuts
   against "simplify", but it is the section claude.com chose to keep when it kept only
   three. Not proposing it; flagging that they made the opposite trade to ours.
