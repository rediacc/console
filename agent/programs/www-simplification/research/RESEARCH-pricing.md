# RESEARCH — pricing surface

**Agent:** `sx-pricing` · **Date:** 2026-08-17 · **Status:** research only, zero edits made.

Screenshots referenced below live in
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-pricing/`.

---

## 1. Verdict

The pricing page is not complex because it shows too much pricing; it is complex
because it shows almost no pricing and a great deal of everything else. A visitor
crosses a full 900px empty dark hero before the first number appears at y=1226,
then meets 20 comparison rows of which only **4** distinguish the two plans they
can actually buy, a 2,355px licensing essay, 13 FAQ entries, and two banners
whose buttons are visually louder than the buy buttons. Underneath, the
2,321-line stylesheet holds **771 lines (33.2%) that match no element on any of
the four pages that load it** — three generations of pricing-card system stacked
in one file. The highest-leverage change is to **delete the hero and lift the
cards into the first viewport**, which is also what claude.com does; everything
else on the page is a candidate for deletion, not redesign. Separately, and more
seriously than any layout issue, `/en/disaster-recovery` ships the *same card
component with the same three plan names* at **$1,299 / $3,999 / mo** against
`/en/pricing`'s **$49 / $59** — a 26x contradiction two clicks apart (§6.1).

---

## 2. What we have

### 2.1 Page shape (measured live, 1440x900, `/en/pricing`)

| Metric | Value | How measured |
|---|---|---|
| Page height | **8,397px** = 9.3 viewports | `document.body.scrollHeight` |
| …with all accordions open | **10,301px** = 11.4 viewports | after `details.open = true` on all |
| Mobile height (390x844) | **12,056px** = 14.3 viewports | same, after `set viewport 390 844` |

> **Height stability checked.** `sx-homepage` found page heights growing after
> scroll as `loading="lazy"` images resolve (homepage: 6,794px fresh → 7,697px
> settled, +903). That effect does **not** apply to the pricing page: it carries
> **3 images, 1 of them lazy**, and re-measuring after walking to the bottom and
> settling 2s returns **8,397px unchanged** on desktop and **12,056px unchanged**
> at 390x844. Every height in this document is a settled figure. The one place it
> does bite my files is placement, not size: `PricingPreview`'s section on the
> homepage is 1,251px either way, but its top moves from y=4,183 fresh to
> **y=5,454 settled** — the homepage pricing block sits 1,271px lower than a
> fresh-load reading suggests (§6.6).
| Top-level `<section>`s | **9** | `article.pricing-page > section` |
| Y of first price on screen | **1,226px** (1.36 viewports) | `.cf-price` bounding rect |
| Hero height | **900px** — exactly one viewport | `.pricing-hero` |
| Focusable elements in the article | **25** (110 page-wide) | `a[href],button,[tabindex="0"]` visible |

Section-by-section, desktop (`file:line` = `src/pages/[lang]/pricing.astro`):

| # | Section | Line | Height | % of page |
|---|---|---|---|---|
| 1 | `pricing-hero` — h1 + subhead only | 110 | 900 | 10.7% |
| 2 | `plans` — toggle + 3 cards | 118 | 984 | 11.7% |
| 3 | `roi-cta-section` | 160 | 187 | 2.2% |
| 4 | `edge-channel-section` | 175 | 187 | 2.2% |
| 5 | `PricingTrustSection` | 194 | **2,355** | **28.0%** |
| 6 | `PricingComparison` | 197 | 729 (1,724 open) | 8.7% |
| 7 | `FAQSection` (13 items) | 200 | 1,635 (2,545 open) | 19.5% |
| 8 | `ps-teaser-section` | 203 | 430 | 5.1% |
| 9 | `pricing-cta` | 217 | 358 | 4.3% |

**The plans themselves occupy 11.7% of the pricing page.** The licensing
explainer (`PricingTrustSection`) is 2.4x larger than the cards, and on mobile it
is 3,426px — four full phone screens of prose about what happens when your
licence expires, on the page whose job is to sell the licence.

Screenshot `p-desktop-top.png`: the hero is 900px of near-black with two lines of
centred text and roughly 400px of empty space below them. Nothing else.

### 2.2 Tiers, axes and toggles

- Cards rendered: **3** — Professional $49, Business $59, Enterprise "Contact us"
  (`pricing.astro:41`, `PLAN_ORDER.filter(code => code !== 'COMMUNITY')`).
- Plans in the comparison table: **4** — Community is a full column with real
  values (`PricingComparison.astro:36-40`), no price, no CTA, no card. A visitor
  is shown a fourth plan they cannot select. See §6.2.
- Prices come from `packages/shared/src/subscription/constants.ts:390-408`
  (`PLAN_PRICING`), limits from `constants.ts:34-55` (`PLAN_LIMITS`).
- Card metric rows: **5**, from `technicalSummary.values`. Of those five,
  **three are identical on every card**: "Unlimited Repositories", "1 Floating
  Licenses", "Unlimited Users & Teams". Only *Repository size* and *Server setups
  per month* differ. So **60% of every card's feature list is filler**, and it is
  the filler a buyer reads first (screenshot `p-desktop-900.png`).
- "1 Floating Licenses" is also a plural-agreement bug shown on all three cards.

Toggles and controls demanded of the visitor:

| Control | Where | Options |
|---|---|---|
| Billing period | `pricing.astro:121-143` | Monthly / Annual |
| Comparison categories | `PricingComparison.astro:72` | 5 accordions, 4 closed by default |
| FAQ | `FAQSection` | 13 accordions |
| Comparison plan column (mobile) | `PricingComparison.astro:50-65` | 4-way tab |
| **Account region** | region-picker modal, fires on the buy button | Europe / US / Asia Pacific |
| Channel | `pricing.astro:175-191` | stable vs edge |

### 2.3 The comparison table earns two facts

`en.json → pages.pricing.comparison.categories`, counted by script:

```
rows total 20 | Professional == Business: 16 | identical across all 4 plans: 10
```

- **10 of 20 rows (50%)** are `✓ ✓ ✓ ✓` — they differentiate nothing and belong
  in the "All plans include" strip that already exists at `pricing.astro:153`.
- **16 of 20 rows (80%)** do not distinguish Professional from Business, the only
  two plans a visitor can buy on this page.
- The 4 that do: *Server setups per month*, *Repository size*, *Dedicated Account
  Manager*, *Phone Support*. The first two are already printed on the cards.
- Net: **the entire 20-row, 5-category, 1,724px-when-open table adds exactly two
  facts** the cards do not already show.
- The first row of the first (and only open-by-default) category is *Floating
  Licenses (Machines)* = `1 / 1 / 1 / Custom` — the single most prominent row in
  the table is one where three of four columns read "1"
  (screenshot `p-desktop-4613.png`).

### 2.4 What the 2,321 CSS lines are actually spent on

`src/styles/pricing-page.css` has four consumers, not one:

```
src/pages/[lang]/pricing.astro:14            import
src/pages/[lang]/disaster-recovery.astro:10  import
src/components/PricingPreview.astro:7        import  (homepage embed)
src/styles/professional-services-page.css:4  @import
src/styles/disaster-recovery-page.css:1      @import   (1-line file, nothing else)
```

Structure: **175 distinct classes, 294 rules on the pricing page, 22 media
queries, 36 comment-delimited sections.**

Coverage measured in the live browser by walking the CSSOM and running
`document.querySelector` on every rule's selector across all four consuming
pages, then intersecting (control: `.cf-pricing-card`, `.pricing-hero`,
`.comparison-category`, `.billing-toggle-btn` all matched, so the instrument
fires):

| Measurement | Value |
|---|---|
| Rules matching something on `/en/pricing` | **109 of 294 (37%)** |
| Rules matching nothing on *any* of the 4 consumers | **155** |
| Lines in those rules (state/`:hover`/`.active` selectors excluded) | **771 of 2,322 = 33.2%** |
| Rules used only by `/en/professional-services` | 41 |
| Rules used only by `/en/disaster-recovery` | 29 |

The 771 dead lines fall into 19 contiguous regions; the large ones are:

| Region | Lines | What it is |
|---|---|---|
| L843–L1115 | 273 | `.package-pricing`, `.pricing-factors`, `.service-types`, `.detail-badge` — a professional-services page that no longer renders this markup |
| L1133–L1248 | 116 | `.retainer-options`, `.implementation-overview` |
| L390–L495 | 106 | `.ps-access*` — a 9-class access-matrix layout |
| L1516–L1589 | 74 | `.comparison-table*` — the flat table the `<details>` accordion replaced |
| L597–L735 | 139 | `.card-price`, `.card-features`, `.billing-row`, `.savings-badge`, `.card-guarantees` — the pre-`cf-` card system |
| L134–L166 | 33 | `.pricing-grid` / `.three-up` / `.four-up` — the pre-`cf-` grid |

So the honest answer to "what do the 2,321 lines buy": roughly **770 lines buy
nothing**, another **~450** belong to two other pages (professional-services and
disaster-recovery) that import this file rather than owning their own, and the
pricing page itself is served by about **109 rules**. There are **three
generations of pricing card** in the file — `.pricing-card` + `.technical-card`
(dead), `.card-*` (dead), `.cf-*` (live) — and nothing ever deleted the first
two.

### 2.5 Dead content, not just dead CSS

- **`plans.*.features`** — 40 English strings (8/10/10/12 for
  community/professional/business/enterprise) in `en.json`. `CfPricingCard.astro`
  renders `metrics` (from `technicalSummary`), never `features`. Multiplied by 13
  locales this is **520 translated strings rendering nowhere**.
- **12 dead `pages.pricing.ui.*` keys** (token-search over all `src/**/*.{astro,ts,tsx}`):
  `limitedOffer`, `whatsIncluded`, `contactSales`, `keyBenefits`, `monthOrYear`,
  `foreverFree`, `edgeLimitsNote`, `cta.business.valueNote`
  (`"Includes $9,999 setup credit"`), `cta.business.launchBadge`,
  `guarantees.{freeTrial,cancelAnytime,noContracts}`. These are the residue of a
  previous pricing model.
- **`.cf-starting-at` is unreachable by construction.** `pricing.astro:35` sets
  `startingAtPlans = new Set(['enterprise'])`, but `CfPricingCard.astro:51` sends
  `enterprise` down the "Contact us" branch that never reads `plan.startingAt`.
  The flag can only ever be true for the one plan that ignores it.
- **`ui.anchor: "Strategic anchor"`** is *live*, on `/en/disaster-recovery`
  (`disaster-recovery.astro:41`), rendered as a visitor-facing badge on the
  Enterprise card (screenshot `dr-cards.png`). "Anchor" is the internal
  pricing-psychology term for the decoy tier. It is shipped as marketing copy.

### 2.6 PricingPreview duplicates the pricing page, and disagrees with it

`PricingPreview.astro` is a near-verbatim copy of `pricing.astro`'s card logic:
`badgeConfig` (19-29 vs 23-33), `startingAtPlans` (31 vs 35), the `PLAN_ORDER`
filter (36-50 vs 41-55), `buildMetrics` (52-57 vs 60-65), the billing-toggle
markup (66-88 vs 121-143), and the **entire 35-line toggle `<script>`**
(102-139 vs 241-282). About **90 duplicated lines**, including the same
explanatory comment about Community.

They diverge on the only thing that matters — the funnel. Measured on both live
pages:

| | `/en` (PricingPreview) | `/en/pricing` |
|---|---|---|
| Cards / prices | Professional $49, Business $59, Enterprise | identical |
| CTA label | **"Start free trial"** | **"Start 14-day free trial"** |
| CTA element | `<a href="/account/">` | `<button data-checkout="professional">` |
| Destination | generic portal root | `/account/?checkout=PROFESSIONAL&period=monthly` |

Cause: `pricing.astro:148` passes `useCheckout={true}`; `PricingPreview.astro:91`
does not, so `checkoutPlans` is empty (`CfPricingCard.astro:33`). A visitor who
buys from the homepage never reaches the plan-preselected checkout and never has
their billing period carried over. Two labels for one action is also a
translation liability across 13 locales.

### 2.7 The checkout entry

There is no checkout flow in `packages/www`: `src/pages/[lang]/checkout/` holds
one file, `success.astro` (a 2.7KB confirmation page with an inline `<style>`
block). Checkout itself lives on the portal. Measured by clicking the real
button:

1. Click **Start 14-day free trial** →
2. a **region-picker modal** opens (`.region-picker-backdrop`), reading *"Choose
   your account region … **This can't be changed after sign-up.**"* — Europe /
   United States / Asia Pacific →
3. `/account/?checkout=PROFESSIONAL&period=monthly&returnUrl=…` →
4. portal signup →
5. card entry.

The first thing between a visitor and paying is an **irreversible data-residency
decision, demanded before they have an account**. Screenshot
`p-regionpicker.png`.

### 2.8 Visual hierarchy points off-page

Computed styles on `/en/pricing`:

| Button | Background | Font size | Weight |
|---|---|---|---|
| `.cf-cta-btn` — all three buy buttons | `rgb(247,247,248)`, 1px `rgb(210,210,215)` border | **14px** | 600 |
| `.cf-featured .cf-cta-btn` (Most popular) | **byte-identical to the others** | 14px | 600 |
| `.roi-cta-banner .btn-primary` — "ROI Calculator →" | `linear-gradient(135deg, rgb(85,107,47), rgb(76,96,41))`, white text | **18px** | 400 |
| `.edge-channel-banner .btn` | transparent, bordered | 18px | 400 |

The only solid-filled, high-contrast button in the entire plans-to-comparison
stretch is a link **away** from the pricing page to a calculator; the three
buttons that take money are the smallest type on the page and the "Most popular"
card gets no visual promotion at all (screenshot `p-desktop-banners.png`).

### 2.9 Mobile (390x844)

- 12,056px = **14.3 viewports**.
- First price at y=620 (better than desktop — the hero collapses to 296px).
- `PricingTrustSection` = **3,426px**, 28% of the page.
- Horizontal overflow: `document.documentElement.scrollWidth = 618` against a
  390px viewport. **Within `.pricing-page` only one element overflows**
  (`.comparison-plan-toggle`, right edge 394px, 4px over). The 618px figure comes
  from `.nav-right` / `.nav-utilities` in the header — see §6.
- The comparison table itself behaves: the 4-way plan tab hides the other
  columns, so no table scroll trap. Cards stack cleanly (`m-900.png`).

### 2.10 Accessibility note

15 `.cf-feature-info` tooltip spans carry `tabindex="0"` with **no `role`**
(`CfPricingCard.astro:74-81`). They add 15 tab stops that announce as
unlabelled text nodes, and their content is CSS-only (`data-tooltip`), so it is
unreachable by keyboard on the pricing page's 25 in-article tab stops.

---

## 3. What claude.com does

All values read live from `https://claude.com/pricing` at 1440x900 via `eval` +
`getBoundingClientRect` / `getComputedStyle`. Screenshot `claude-top.png`.

| Measurement | Value |
|---|---|
| Page height | 7,417px = 8.2 viewports |
| `h1` | the single word **"Pricing"**, 64px, at y=240 |
| Hero band | none — `body` background `rgb(250,249,245)` runs from nav to cards |
| Audience tabs | y=389 — *Individual / Team & Enterprise / API* |
| First card | y=594 |
| **First price ($0)** | **y=680 — inside the first viewport** |
| Tiers visible at once | **3** (Free/Pro/Max, or Team/Enterprise) |
| Billing-period control | **none** |
| Comparison rows, Individual tab | **50** across 4 categories (24+12+5+9) |
| Comparison rows, Team & Enterprise tab | 64 across 5 categories |
| Comparison categories open by default | **9 of 9** |
| Rows identical across all columns (Individual) | **35 of 50 = 70%** |
| CTA destination | `https://claude.ai/login?plan=pro` — plan preselected, one hop |
| Region / residency decision before signup | none |

Three of these deserve emphasis because they overturn the obvious hypothesis:

**They do not win by having a shorter page or a shorter matrix.** 7,417px vs our
8,397px is not a meaningful gap, and their Individual matrix is **2.5x our row
count** with a *worse* undifferentiated-row ratio (70% vs our 50%). "Cut the
comparison table" is not the transferable lesson, and I would have written that
down if I had not measured it.

**They win in the first viewport.** No hero. The h1 is a label, not a headline —
they spend zero pixels telling you what page you are on beyond the word. Cards,
prices and CTAs are all above 900px. Ours needs 1.36 viewports to show a number.

**They removed the billing toggle by writing a sentence.** The Pro card reads:
*"$17 — Per month with annual subscription discount ($200 billed up front). $20
if billed monthly."* Both prices, both periods, one static sentence, no control,
no JS, no state, no re-render. We spend a toggle, 23 lines of markup, 35 lines of
script — duplicated in two components (§2.6) — and six `data-monthly`/`data-annual`
attribute pairs to communicate strictly less.

Two secondary moves worth taking: their audience tab means nobody ever sees all
5 tiers or all 114 rows at once (segmentation beats truncation), and their card
lists are cumulative — *"Everything in Free, plus:"* — so each card shows only its
delta, where ours repeats three identical rows on every card.

---

## 4. The delta

### 4.1 Decisions demanded of the visitor

| Decision | Ours | claude.com | Gap |
|---|---|---|---|
| Which audience am I | — | 1 tab (3 options), pre-selected | they segment; we show everyone everything |
| Which tier | 3 cards + a 4th phantom column | 3 cards per tab | phantom Community (§6.2) |
| Monthly or annual | **toggle, must operate it** | stated in prose | **-1 control** |
| Expand comparison categories | **4 clicks** (4 of 5 collapsed) | 0 (9/9 open) | **-4 clicks** |
| Which plan column (mobile) | 4-way tab | responsive table | -1 control |
| Read 13 FAQ accordions | 13 | 3 tabbed groups | — |
| Stable or edge channel | **banner promises 2x limits elsewhere** | — | **-1 decision** (§6.3) |
| ROI-calculator detour | promoted with the loudest button on the page | — | **-1 detour** |
| Professional-services detour | full section | — | -1 detour |
| **Account region, irreversible, pre-signup** | **modal on the buy button** | none | **-1 blocking decision** |
| Scroll to first price | **1.36 viewports** | 0.76 viewports | **-450px** |
| **Total controls before "I'll take Professional"** | **6** | **1** | |

### 4.2 Structure

| | Ours | Theirs | Note |
|---|---|---|---|
| Page height (desktop) | 8,397px / 9.3vp | 7,417px / 8.2vp | comparable |
| Page height (mobile 390) | 12,056px / 14.3vp | — | ours is the outlier |
| Plans as % of page | **11.7%** | ~25% | we bury the product |
| Largest section | licensing essay, 28% | comparison matrix | wrong thing is biggest |
| Comparison rows | 20 | 50 | **row count is not the problem** |
| Rows that differentiate the two buyable plans | **4 of 20** | — | the problem |
| Card rows that vary between tiers | **2 of 5** | delta-only lists | |
| CSS for the surface | 2,321 lines, 33.2% dead | — | |
| Steps buy-click → payment page | **5** (incl. an irreversible modal) | **1** | |

---

## 5. Proposed simplification

Ordered by leverage. "Prove it" columns are the check I would run after, not a
description of the change.

### P1 — Delete the hero; open on the cards *(highest leverage)*

**Change.** Remove the `pricing-hero` section (`pricing.astro:110-115`) and its
styles (`pricing-page.css:34-67`). Replace with a claude.com-style label block:
`<h1>Pricing</h1>` plus at most one line, ~240px total, on the page background —
no dark band. Target: first price above 800px on desktop.

**Files.** `src/pages/[lang]/pricing.astro`, `src/styles/pricing-page.css`,
`en.json → pages.pricing.hero` (and the 12 locale mirrors).

**Risk.** Low mechanically. The dark hero also anchors the `section-dark` button
overrides at `pricing-page.css:16-33`; removing it leaves the final-CTA section
as the only `section-dark` consumer, so those rules must be re-scoped, not
deleted. `/en/disaster-recovery` uses the same `.pricing-hero` class
(`disaster-recovery.astro:66`) — either it moves with us or the class stays for
its sake. **Cross-domain: `sx-hero`.**

**Prove it.** `.cf-price` bounding-rect top < 800 at 1440x900 and < 500 at
390x844; page height drops by ≥650px.

**Deletes:** ~34 CSS lines, one section, one translated headline pair x13.

### P2 — Retire the billing toggle; state both prices

**Change.** Delete the toggle markup (`pricing.astro:120-143`), the 42-line
`<script>` (241-282), the identical block in `PricingPreview.astro:66-88,102-139`,
the `data-monthly`/`data-annual` attribute pairs (`CfPricingCard.astro:62-67`),
and `.billing-toggle*` / `.cf-savings-badge` CSS (`pricing-page.css:1876-1936`,
2100-2120). Replace with one static line per card: *"$49/month, or $499/year —
save 15%."*

**Files.** `pricing.astro`, `PricingPreview.astro`, `CfPricingCard.astro`,
`pricing-page.css`, `en.json → ui.billingToggle` + `ui.monthOrYear` (already
present and unused, §2.5 — it is exactly the string this needs).

**Risk.** Medium, and it is a product risk, not a code one: the checkout handler
reads the toggle to set `period` (`CfPricingCard.astro:140-141`). Removing the
toggle means the period is chosen in the portal instead. That must be confirmed
to exist portal-side before this ships, or the deep-link keeps `period=monthly`
and the portal offers the switch. **Open question O1.**

**Prove it.** Both prices present in the static HTML with JS disabled; zero
`.billing-toggle*` selectors matched; checkout URL still carries a valid `period`.

**Deletes:** ~77 lines of JS across two components, ~23 lines of markup x2,
~70 CSS lines.

### P3 — Cut the comparison table to the rows that decide something

**Change.** Drop the 10 all-`✓` rows into the existing "All plans include" strip
(`pricing.astro:153`) — it already exists and already carries this job. Keep the
rows that differentiate. Open every remaining category by default, as
claude.com does. Drop the Community column (§6.2 decides whether it goes or gains
a card). Expected shape: 4 categories → 2, 20 rows → ~8, zero clicks to read.

**Files.** `PricingComparison.astro` (the `categoryOrder` array at 27-33 and the
`planColumns` at 35-40), `en.json → pages.pricing.comparison` x13 locales,
`pricing-page.css:1937-2045`.

**Risk.** Medium — this is a 13-locale content change, and `check:i18n` will
demand re-naturalization of every touched key. Deleting keys is cheaper than
editing them; prefer deletion. **Cross-domain: `i18n-guardian` conventions apply.**

**Prove it.** Every remaining row has ≥2 distinct values across the rendered
columns, asserted by a script over `en.json` — the same one that produced §2.3.
Section height at 390px drops below 500px.

**Deletes:** 10 rows x 4 columns x 13 locales = **520 translated strings**, plus
the mobile 4-way plan toggle (`PricingComparison.astro:50-65,111-135`) which
exists only to survive a wide table.

### P4 — Give the buy button visual primacy; demote the detours

**Change.** Make `.cf-cta-btn` a solid primary at 16px, and give
`.cf-featured .cf-cta-btn` a stronger treatment than its siblings. Demote the ROI
banner button from `btn-primary` to a text link, or move the whole
`roi-cta-section` (`pricing.astro:160-172`) below the FAQ. Same for the
professional-services teaser.

**Files.** `pricing-page.css` (`.cf-cta-btn` block, `.roi-cta-banner`),
`pricing.astro:160-191`.

**Risk.** Low. Touches shared button tokens — coordinate with `sx-primitives`.

**Prove it.** Computed `background-color` of `.cf-cta-btn` is the brand solid;
no `.btn-primary` gradient exists between the cards and the comparison table.

### P5 — Delete the dead third of the stylesheet, then split what remains

**Change.** Two steps. (a) Delete the 19 dead regions in §2.4 — **771 lines**.
(b) Move the 41 professional-services-only rules into
`professional-services-page.css` and the 29 disaster-recovery-only rules into
`disaster-recovery-page.css` (currently a **1-line file** that does nothing but
`@import './pricing-page.css'`). What remains is a pricing stylesheet of roughly
**600–700 lines** that only the pricing surface loads.

**Files.** `src/styles/pricing-page.css`, `src/styles/professional-services-page.css`,
`src/styles/disaster-recovery-page.css`.

**Risk.** Low-to-medium, and it is measurable rather than judgemental. The
coverage instrument in §2.4 can be re-run before and after; the caveat is that it
sees only the rendered English DOM, so any selector applied by *runtime* JS
class-toggling could be a false positive. I excluded `:hover`/`:focus`/`.active`/
`.visible` selectors for exactly that reason; the remaining 771 lines are
structural selectors for markup that no component emits.

**Prove it.** Re-run the coverage script over all four pages; matched-rule count
unchanged, total rule count down by 130 blocks. Visual diff of all four pages at
1440x900 and 390x844 via `agent-browser diff screenshot --baseline`.

**Deletes:** 771 CSS lines (33.2%), plus two of the three card systems.

### P6 — Delete the dead content

`plans.*.features` (40 strings x 13 locales = **520 strings**), the 12 dead
`ui.*` keys, the unreachable `startingAt` path (`pricing.astro:35`,
`CfPricingCard.astro:33,58-60`), and — separately and urgently — the visitor-facing
string `"Strategic anchor"` (§2.5).

**Risk.** Low, but `check-i18n-naturalization` gates locale-file edits; delete
keys in all 13 files in one pass, never one locale at a time.

### P7 — Unify PricingPreview with the pricing page

Pass `useCheckout={true}` from `PricingPreview.astro:91` so the homepage funnel
matches, and extract the shared plan-building block (badgeConfig, PLAN_ORDER
filter, buildMetrics) into one module both import — ~90 duplicated lines
(§2.6). If P2 lands, the duplicated toggle script disappears with it and the
remaining duplication is ~40 lines.

**Risk.** Low. **Cross-domain: `sx-homepage` owns the homepage composition.**

### What I would delete outright

| Thing | Size |
|---|---|
| `pricing-hero` section + CSS | 1 section, ~40 lines |
| Billing toggle (markup, script, CSS, data attrs) x2 components | ~170 lines |
| 10 undifferentiated comparison rows x 4 cols x 13 locales | 520 strings |
| Mobile 4-way comparison plan toggle | ~50 lines |
| `plans.*.features` x 13 locales | 520 strings |
| 12 dead `ui.*` keys x 13 locales | 156 strings |
| Dead CSS regions | **771 lines** |
| `disaster-recovery-page.css` (1-line passthrough) | 1 file |
| `roi-cta-section` and/or `edge-channel-section` (operator call, O2/O3) | 2 sections |

---

## 6. Cross-domain consequences

### 6.1 CORRECTNESS — `/en/disaster-recovery` contradicts `/en/pricing` by 26x

Not a design finding. `src/pages/[lang]/disaster-recovery.astro:23-43` hardcodes
a plan array and feeds it to the **same `CfPricingCard` component** used by the
pricing page. Rendered live and confirmed by screenshot `dr-cards.png`:

| Plan name | `/en/pricing` | `/en/disaster-recovery` | Ratio |
|---|---|---|---|
| Professional | **$49/mo** ($499/yr) | **$1,299/mo** ($13,250/yr) | **26.5x** |
| Business | **$59/mo** ($599/yr) | **$3,999/mo** ($40,790/yr) | **67.8x** |
| Enterprise | Contact us | Contact us (`monthly: 9999` set, never rendered) | — |

Same three plan names, same card design, same "Start free trial" CTA, no label
anywhere on the DR page indicating these are a different product or line. Both
pages are reachable from the primary nav. The DR prices are hardcoded literals,
not derived from `PLAN_PRICING`, so nothing keeps them in sync and no gate would
catch a divergence.

This is either (a) a genuinely separate DR product that needs distinct plan names
and an explicit "this is not the platform subscription" frame, or (b) stale
copy from an abandoned pricing model. It cannot stay as-is: a prospect who opens
both tabs concludes the pricing is invented. **Owner: whoever holds
`disaster-recovery.astro` — I own the file per my brief but the decision is the
operator's (O4).** Also note the DR page ships the badge `"Strategic anchor"`
(`disaster-recovery.astro:41-42`), the internal term for a decoy tier.

### 6.2 The phantom Community plan

The comparison table gives Community a full column with real values
(`PricingComparison.astro:36`), FAQ items 1, 9 and 12 describe it in detail as
the post-cancellation floor, and `ui.cta.community.*` exists — but no card
renders it and there is no way to obtain it. Worse, FAQ #9 contradicts the table
it sits next to:

- FAQ #9 lists **"automated scheduling"** as a Professional-over-Community
  differentiator; the table gives Community *Automated Scheduling* `✓`.
- FAQ #9 lists **"API access"** likewise; the table gives Community
  *Integrations API* `✓`.
- FAQ #9 lists **"24-hour restore history"**; the table gives Community
  *Continuous Data Protection* `✓`.

Three contradictions between two sections 700px apart. Either Community is a
plan (give it a card and a price of $0) or it is a cancellation state (remove the
column, keep the FAQ). Content decision, but the fix lands in my files.

### 6.3 The edge-channel banner undercuts the price beside it

`pricing.astro:175-191` tells the visitor, on the pricing page, that
`edge.rediacc.com` "runs with **double the limits** of the stable channel". A
buyer reading that has just been shown 100 GB for $49. The dead string
`ui.edgeLimitsNote` says the opposite ("Limits shown for the edge channel. The
stable channel has half these limits"). I verified which is true: the card values
match `PLAN_LIMITS` in `packages/shared/src/subscription/constants.ts:40-49`
(100 GB, 2000 setups), and the comment at `constants.ts:28` confirms these are
the base values the account server's `getLimitsForEnvironment` doubles for edge.
So the banner is factually right and the dead string is stale — but a banner
offering 2x the product for the same price, sited between the cards and the
comparison table, is a conversion leak regardless. **Operator call (O3).**

### 6.4 Header overflows the 390px viewport

`document.documentElement.scrollWidth = 618` at a 390px viewport on
`/en/pricing`. The pricing article contributes 4px of that
(`.comparison-plan-toggle`, right edge 394). The rest is `.nav-right` /
`.nav-utilities` / `.language-selector` reaching x=425, and an off-canvas
`.sidebar` at x=-375 that is not `overflow`-clipped. **Owner: `sx-chrome`.** Not
mine, not touched — but it means every page on the site scrolls sideways on a
phone.

### 6.5 The contradictory performance figures do NOT appear on the pricing surface

`sx-homepage` found the homepage stating `Cloning production (3.2 TB) … done in
4.7s` (`src/pages/[lang]/index.astro:16`) against `241 GB / copied in under 60
seconds` in the metrics bar — ~170x apart per byte. Asked whether the pricing
surface repeats either, I grepped all seven of my files
(`pricing.astro`, `PricingPreview.astro`, `CfPricingCard.astro`,
`PricingComparison.astro`, `PricingTrustSection.astro`, `ServicePackageCard.astro`,
`checkout/success.astro`) for `241`, `3.2 TB` and `4.7`:

```
grep -rn "241|3\.2 TB|4\.7" <the seven files>   → no matches
```

**Negative result: neither figure is on the pricing surface**, so nothing in my
proposals is blocked on resolving it. Provenance, since I had the search open:
`3.2 TB / 4.7s` exists only as a hardcoded literal at `index.astro:16`, and
`241 GB` exists only in `en.json` at `metrics.items[0].number`,
`pages.company.values.items.simplicity.description`, and eight keys under
`pages.solutionPages.environmentCloning.*`. Neither is derived from anything.

While confirming that, one thing in the same namespace is worth naming because it
violates a standing rule rather than a design preference:
`en.json → pages.solutionPages.environmentCloning.socialProof.quote` is a
first-person customer testimonial with invented specifics ("We spun up 12
production-identical test environments in under 10 minutes … 3 engineers and 2
days per environment"), translated into all 13 locales. The operator's standing
rule is that there are no customers yet and social proof is never to be invented.
**Owner: whoever holds the solution pages.** Not mine, not touched.

### 6.6 PricingPreview's position on the homepage

Recorded here because it is my component on someone else's page: after lazy
images settle, the `#pricing` section starts at **y=5,454** on a 7,697px
homepage — the last content block before the footer, 6.1 viewports down. Its own
height (1,251px) is unaffected by settling. If P7 unifies the two card surfaces,
this placement is the thing that decides whether the homepage preview is worth
keeping at all. **Owner: `sx-homepage`.**

### 6.7 Other files my proposals reach into

- `FAQSection.astro` — 13 items, 1,635px (2,545px open), 19.5% of the pricing
  page. Shared component; whoever owns it should know the pricing FAQ is its
  heaviest consumer and that items 1/9/12 carry the Community contradictions.
- `CorporateGuarantee.astro` — rendered inside both `PricingTrustSection` and
  `PricingPreview`.
- `AccountLink.astro` + the region-picker in `BaseLayout.astro:459-466` — the
  modal in §2.7 is BaseLayout's, not mine. Reducing the buy flow from 5 steps to
  2 requires a decision there (defaulting the region by geo-IP with an option to
  change, rather than blocking on it). **Owner: `sx-chrome` / operator.**
- `src/styles/solution-pages.css` (2,616 lines) is the only stylesheet larger
  than mine and is what `roi-calculator.astro:8` actually loads — the ROI
  calculator does **not** use `pricing-page.css` and is out of my file set
  despite being linked from my page.

---

## 7. Open questions for the operator

**O1 — Can the portal choose the billing period?** P2 deletes the monthly/annual
toggle and states both prices in prose (claude.com's move). The checkout deep
link currently carries `period` from the toggle
(`CfPricingCard.astro:140-141`). If the portal cannot offer that choice, the
toggle stays and P2 shrinks to "show both prices in the card as well".

**O2 — Do the ROI calculator and professional-services sections belong on the
pricing page?** Together they are 617px, two of the nine sections, and the ROI
button is the loudest control on the page. Both are legitimate pages; the
question is whether the page whose job is "pick a plan" should promote two exits
above the fold of the comparison. My recommendation: keep one text link to the
ROI calculator inside the plans section, move professional-services to the footer
of the page.

**O3 — Should the edge-channel banner stay on the pricing page?** (§6.3) It
offers double the limits at the same price on a different host. Correct, but it
is an argument against the purchase the page is asking for.

**O4 — What are the disaster-recovery prices?** (§6.1) Real DR product line, or
stale copy? I will not touch those numbers on a guess. This is the one item I
would fix this session if given a direction, since it is a live factual
contradiction rather than a design preference.

**O5 — Is Community a plan or a state?** (§6.2) A $0 card, or delete the column
and fix FAQ #9. Either is defensible; the current shape is neither.

---

## Appendix — commands behind the counts

```bash
# CSS size ranking (2,321 lines, largest in src/styles after solution-pages.css)
wc -l src/styles/*.css | sort -rn

# comparison-row differentiation (§2.3)
node -e "…en.json → pages.pricing.comparison.categories…"
# → rows total 20 | Professional == Business: 16 | identical across all 4: 10

# CSS coverage, run in-browser against all 4 consuming pages, intersected
# control selectors .cf-pricing-card/.pricing-hero/.comparison-category/
# .billing-toggle-btn all matched → instrument fires
# → union 335 rules, matched somewhere 179, dead everywhere 155 → 771 lines (33.2%)

# live geometry
agent-browser eval "(()=>{ … getBoundingClientRect … })()"
```

Scripts used are in the session scratchpad
(`deadcss.js`, `deadblocks.js`, `sel.js`, `cov-*.json`, `dead-selectors.txt`).
Screenshots: `p-desktop-top.png`, `p-desktop-900.png`, `p-desktop-2258.png`,
`p-desktop-4613.png`, `p-desktop-banners.png`, `p-regionpicker.png`,
`m-0.png`, `m-900.png`, `m-4200.png`, `dr-cards.png`, `claude-top.png`.
