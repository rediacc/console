# Explore report: homepage Difference, pricing No-Lock-In, FAQ surfaces, illustration assets

Read-only investigation. Nothing was modified. All paths relative to
`/home/muhammed/console/packages/www/` unless stated otherwise.

---

## (A) The homepage "Difference" section - there are TWO sections

`/en/` renders via `src/pages/[lang]/index.astro:23` -> `src/components/solution-pages/SPHomePage.astro:55-65`,
which composes exactly five body sections:

```
SPHomeHero -> SolutionConstellation -> SPHomeNotASlice -> HomeDifference -> PricingPreview -> SPHomeBottomCta
```

The operator quoted strings from BOTH. "Most tools copy one piece. We copy all of it."
and "They save everything. Recovery takes hours, not a minute." are `notASlice`, rendered by
`SPHomeNotASlice.astro`. The section literally TITLED "The Difference" is a different
component, `HomeDifference.astro`, rendering the `beforeAfter` branch.

### A1. `SPHomeNotASlice` - source of the operator's quotes

- Component: `src/components/solution-pages/SPHomeNotASlice.astro` (258 lines)
- CSS: entirely in its own scoped `<style>` block, `SPHomeNotASlice.astro:110-257`. No
  external stylesheet contributes to it.
- Section id: `not-a-slice` (`:19`)
- i18n root: `notASlice` - **top-level in `en.json`**, not under `pages.home`

Markup structure:

| element | file:line | notes |
|---|---|---|
| `.sp-not-a-slice` `<section>` | `:19` | `background: var(--sp-bg-light)`, `padding: 96px 48px` (`:111-115`) |
| `.sp-overline` `<p>` | `:21` | centered (`:120-122`) |
| `<h2>` | `:22` | 36px/700, centered, `max-width: 720px` (`:123-134`) |
| `.sp-slice-grid` | `:24` | `grid-template-columns: repeat(4, 1fr)`, `gap: 20px` (`:135-140`) |
| 4x `.sp-slice-card` | `:26-75` | white card, 1px border, `text-align: center` (`:146-153`) |
| `.sp-slice-icon` + inline `<svg>` | `:27-72` | **index-switched** inline SVGs: `i === 0` / `1` / `2` / `3` at `:28`, `:37`, `:46`, `:59`. Each `viewBox="0 0 140 100"`, 140x100 rendered (`:161-164`) |
| `<h3>` / `<p>` | `:73-74` | 16px/600 and 14px, both `--sp-text-muted-light` (`:165-177`) |
| `.sp-slice-divider` | `:79` | 1px rule, `max-width: 720px` (`:178-183`) |
| `.sp-slice-winner` `<article>` | `:81-106` | **already a 2-column `220px 1fr` grid, SVG left / text right** (`:190-199`), brand border |
| `.sp-slice-winner-icon` `<svg>` | `:83-100` | `viewBox="0 0 200 120"`, hard-coded `#7fa03f` strokes |
| `.sp-slice-winner-label` + dot | `:103` | uppercase, brand color (`:209-229`) |
| `.sp-slice-winner-description` | `:104` | 18px (`:230-235`) |

Responsive: 4-up -> 2-up at `max-width: 1100px` (`:141-145`); at `max-width: 900px`
the grid goes 1-up, padding drops to `64px 24px`, h2 to 28px, and `.sp-slice-winner`
collapses to one column with `text-align: center` (`:236-256`).

Design notes already in the file: the winner card's emphasis is "by border and surface,
not by a second shadow value" (`:184-189`) - the site paints exactly one box-shadow, and
the previous `0 4px 24px var(--sp-brand-glow)` was removed. The dot's 4px ring was a
zero-blur non-zero-spread shadow (an outline, not an elevation) and was deleted rather
than reproduced (`:220-223`). Preserve that discipline in any rework.

**Data flow:** `const slices = (to('notASlice.slices') as Slice[] | undefined) ?? []`
(`:16`). The array is data-driven but **the SVGs are not** - they are index-switched
literals, so a 5th slice would render with no icon.

Exact English strings (`src/i18n/translations/en.json:186-211`):

| key path | English value |
|---|---|
| `notASlice.overline` | One tool. The whole stack. |
| `notASlice.title` | Most tools copy one piece. We copy all of it. |
| `notASlice.slices[0].title` | Database tools |
| `notASlice.slices[0].description` | They copy your data. Your app is more than data. |
| `notASlice.slices[1].title` | Dev-box tools |
| `notASlice.slices[1].description` | They copy your code. Code alone is not a test. |
| `notASlice.slices[2].title` | Backup tools |
| `notASlice.slices[2].description` | They save everything. Recovery takes hours, not a minute. |
| `notASlice.slices[3].title` | Kubernetes tools |
| `notASlice.slices[3].description` | They copy your manifests. A cluster is more than YAML. |
| `notASlice.winner.label` | Rediacc |
| `notASlice.winner.description` | Each team gets their own writable copy. Data, apps, settings, all of it. Ready in 60 seconds. That includes whole Kubernetes clusters. You only pay for storage when something changes. |

Item count: **4 slice cards + 1 winner card**.

### A2. `HomeDifference` - the section titled "The Difference"

- Component: `src/components/HomeDifference.astro` (108 lines)
- CSS: scoped `<style>` at `HomeDifference.astro:62-108`
- i18n root: `beforeAfter` - **top-level**, `en.json:212-232`
- Title: `beforeAfter.title` = **"The Difference"** (`en.json:213`, rendered `:46`)

Markup:

```
section.home-difference > .home-difference-container
  > header.section-header > h2.section-title            (:45-47)
  > .difference-compare                                  (:49)
      2x article.card.difference-col--{before|after}     (:51)
          h3.difference-col-label                        (:52)
          ul.difference-col-list > li x4                 (:53-55)
```

The `after` column also gets `card--raised` (`:51`).

CSS: `.difference-compare { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6);
max-width: var(--container-lg) }` (`:63-69`); collapses to `1fr` at `max-width: 768px`
(`:103-107`). **No illustrations, no images, no SVG anywhere in this component.**

**Critical history, from the file's own header comment (`HomeDifference.astro:2-23`):**
this section *used to be* exactly the layout the operator now wants to rebuild - "a two-up
lead block plus four alternating full-width illustrated rows, plus a `<dialog>` zoom
lightbox for the clipart, plus 22 lines of client script to drive it." It was deleted for
being **2,176px desktop / 4,059px mobile (4.8 phone screens, 29% of the whole page) for
73 words and 12 pieces of clipart, at 30px per word against 8-10px everywhere else**. The
stated reason: "By the third row a reader is pattern matching rather than reading, and none
of the drawings said anything its two lines of text did not."

All eight `beforeAfter.*.points`, both labels, and the title survived that deletion. Only
the drawing left.

**Dead CSS left behind** (`HomeDifference.astro:19-22`, verbatim): `.difference-twoup*` is
dead with that file, and `.difference-row*` / `.difference-zoom*` at
`packages/www/public/styles/main.css:1956-2090` "now have no consumer on any page. Left in
place rather than reached into, because that file belongs to another writer." If an
alternating layout returns here, that block is the natural thing to either revive or delete.

Exact strings (`en.json:212-232`):

| key path | English value |
|---|---|
| `beforeAfter.title` | The Difference |
| `beforeAfter.before.label` | Without Rediacc |
| `beforeAfter.before.points[0]` | Your team waits days for a test copy. And it still doesn't match. |
| `beforeAfter.before.points[1]` | Backups take weeks. Many fail without warning. |
| `beforeAfter.before.points[2]` | Your recovery plan says 4 hours. Real life is 4 days. |
| `beforeAfter.before.points[3]` | Devs write code on the live site. The test copy is weeks old. |
| `beforeAfter.after.label` | With Rediacc |
| `beforeAfter.after.points[0]` | A perfect copy in 60 seconds. |
| `beforeAfter.after.points[1]` | Hourly backups. No extra storage. |
| `beforeAfter.after.points[2]` | Recovery tested in 60 seconds. |
| `beforeAfter.after.points[3]` | Every dev gets a fresh copy. |

Item count: **2 columns x 4 points = 8 claims**.

### A3. Naming history worth knowing

`SPHomePage.astro:26-28` records that five 12-line `SPHome*` pass-through wrappers were
deleted, one of which renamed `HomeDifference` to `SPHomeBeforeAfter`, "so the section had
four names for one thing." Do not reintroduce a wrapper.

`SPHomePage.astro:22-24` also records that a `metrics-bar` was deleted because all four of
its numbers were already prose in `home-difference`, and one ("241 GB in under 60 seconds")
contradicted the hero's "3.2 TB in 4.7s". Any new numbers added to the Difference section
should be checked against `SPHomeHero`.

---

## (B) The pricing "No Lock-In. Ever." alternating pattern

- Component: `src/components/PricingTrustSection.astro` (218 lines)
- Rendered at: `src/pages/[lang]/pricing.astro:130` (imported `pricing.astro:11`)
- CSS: **`src/styles/pricing-page.css:1205-1310`** (NOT `public/styles/main.css`).
  `pricing.astro:14` imports that stylesheet.
- i18n root: `pages.pricing.trustSection` (`en.json:755-790`)

### Structure

```
section.pricing-trust-section.section-light           (:16)
  .pricing-trust-container                            (:17)
    .pricing-trust-header > h2 + p                    (:18-21)
    .trust-row                  rows[0]  text | svg   (:24-48)
    .trust-row.trust-row-reverse rows[1] svg | text   (:51-77)
    .trust-row                  rows[2]  text | svg   (:80-116)
    .trust-row.trust-row-reverse rows[3] svg | text   (:119-146)
    .trust-row                  rows[4]  text | svg   (:149-177)
    .trust-row.trust-row-reverse rows[5] svg | text   (:180-213)
    <CorporateGuarantee lang={lang} />                (:216)
```

Each row is:

```html
<div class="trust-row [trust-row-reverse]">
  <div class="trust-row-text"><h3>{rows[N].title}</h3><p>{rows[N].description}</p></div>
  <div class="trust-row-visual"><svg viewBox="0 0 400 280" ...>...</svg></div>
</div>
```

### The alternation is hard-coded, not data-driven

`const rows = ta(ns + '.rows')` (`:13`) supplies the copy, but the component writes **six
literal `<div>` blocks** and indexes them positionally (`rows[0]` at `:26`, `rows[1]` at
`:53`, ... `rows[5]` at `:182`). `trust-row-reverse` is typed by hand on rows 2, 4, 6
(`:51`, `:119`, `:180`). Each SVG is inlined by hand inside the `.astro` file.

Consequence: adding a 7th row requires editing BOTH the JSON and the component, and a JSON
array of 5 would silently crash on `rows[5].title` (no guard). This is a template, not a
reusable component.

### SVG conventions in this section

All six are `viewBox="0 0 400 280" fill="none" aria-hidden="true"`, drawn with
`stroke="currentColor"` for neutral geometry and `var(--illustration-accent,#4a7c3f)` for
the "good" accent (checkmarks, active states, green rails). Row 3 defines a `<marker
id="arrowGreen">` inline (`:109-113`) - note that id is global to the document, so cloning
this pattern onto another page that also renders this section would duplicate the id.

Subjects, in order: server rack with a crossed-out lapsed license (`:30-46`); terminal
window with five commands still answering (`:57-75`); existing repos vs one new dashed repo
plus a key (`:86-114`); a timeline with an active segment, an expiry dot, a dashed grace
segment and a clock (`:125-144`); five license slots with one released back to the pool
(`:155-175`); a source machine -> destination machine migration with a grace rail
(`:186-211`).

### CSS (`src/styles/pricing-page.css`)

| selector | line | declaration |
|---|---|---|
| `.pricing-trust-section` | `:1211-1213` | `padding: var(--section-padding)` |
| `.pricing-trust-container` | `:1215-1219` | `max-width: var(--container-2xl)`, `padding: 0 var(--space-6)` |
| `.pricing-trust-header` | `:1221-1224` | centered, `margin-bottom: var(--space-16, 4rem)` |
| `.pricing-trust-header h2` | `:1226-1231` | `--font-size-3xl`, bold |
| `.pricing-trust-header p` | `:1233-1239` | `--font-size-lg`, `max-width: var(--container-md)` |
| `.trust-row` | `:1241-1250` | `display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); align-items: center; margin-bottom: var(--space-12); max-width: var(--container-xl); margin-inline: auto` |
| `.trust-row-reverse` | `:1252-1254` | `direction: rtl` |
| `.trust-row-reverse > *` | `:1256-1258` | `direction: ltr` |
| `.trust-row-text h3` | `:1260-1265` | `--font-size-xl`, semibold |
| `.trust-row-text p` | `:1267-1272` | `max-width: 480px` |
| `.trust-row-visual` | `:1274-1278` | flex, centered |
| `.trust-row-visual svg` | `:1280-1285` | `width: 100%; max-width: 400px; height: auto; color: var(--color-text-primary)` |

Responsive, `@media (max-width: 48rem)` (`:1287-1310`): single column, `gap: var(--space-6)`,
`text-align: center`, `.trust-row-reverse` reset to `direction: ltr`, paragraph `max-width:
none`, svg `max-width: 320px`, and **`.trust-row-visual { order: -1 }`** so the SVG sits
ABOVE the text on mobile.

Also note `pricing-page.css:1205-1206`: "Reduced motion is handled once, in
`public/styles/main.css`. A local copy of that block only ever covers the selectors that
existed the day it was written." Do not add a local `prefers-reduced-motion` block.

### The 6 rows, exact English (`en.json:755-790`)

| key path | value |
|---|---|
| `pages.pricing.trustSection.heading` | No Lock-In. Ever. |
| `pages.pricing.trustSection.subtitle` | Rediacc licenses are designed to prevent lock-in. Here's what that means in practice. |
| `...rows[0].title` | Apps keep running forever. |
| `...rows[0].description` | Start, stop, and delete. These always work, even years after a subscription ends. Data stays reachable on the machines that hold it. |
| `...rows[1].title` | Full access to every tool. |
| `...rows[1].description` | Operating tools keep working. SSH access. Remote editing. Every management command. No license ever needed. |
| `...rows[2].title` | Only new servers need a subscription. |
| `...rows[2].description` | An active plan is needed to create new servers or copy existing ones. Resizing and expanding work for 60 days after a plan expires. Running servers is permanent. |
| `...rows[3].title` | 60-day grace for scaling. |
| `...rows[3].description` | When a subscription ends, resize and expand continue working for 60 more days. Start, stop, and delete are not affected. They work forever. |
| `...rows[4].title` | Unlimited machines. Pay only when adding new ones. |
| `...rows[4].description` | A Floating license is only used to create or copy a server. Normal work never takes up a license. Licenses free up after 5 hours with no action, so a single Floating license still covers many machines over time. No per-machine fees, ever. |
| `...rows[5].title` | 40-day buffer when server hardware changes. |
| `...rows[5].description` | Every server license is tied to the machine it was set up for. When a hosting provider moves a server to different hardware, the machine identity changes. Licenses keep working for 40 days. The next check-in automatically updates to the new machine. No downtime, no manual steps. |
| `...corporateGuarantee` | If Rediacc doesn't work out, we'll help with the migration back. |

### FINDING (defect, not asked for): the alternation is broken on `/ar/`

`src/layouts/BaseLayout.astro:69` sets `const dir = currentLang === 'ar' ? 'rtl' : 'ltr'`,
applied to `<html lang dir>` at `:73`.

`.trust-row` declares no `direction`, so on `/ar/` it inherits `rtl` from `<html>`.
`.trust-row-reverse` explicitly sets `direction: rtl` - **the same value**. So on
`/ar/pricing` all six rows lay out identically and the alternation disappears entirely.

Worse: `.trust-row-reverse > * { direction: ltr }` (`pricing-page.css:1256-1258`) forces the
Arabic **text content** of rows 2/4/6 to render left-to-right, which is a correctness bug in
the copy itself, not just the layout.

Fix direction: express the swap with `order` or explicit `grid-column` on the two children
rather than with `direction`. This makes the alternation direction-independent and removes
the need for the `> *` reset and the mobile `direction: ltr` override. Any reuse of this
pattern for the Difference section should adopt the fixed form, not clone the bug.

---

## (C) FAQ surfaces

### The homepage has NO FAQ section

`SPHomePage.astro:40-45` imports six components, none of them `FAQSection`. Solution pages
do not render one either - a repo-wide grep for `faq` across `src/` returns no hit in
`src/components/solution-pages/`.

### Shared component

`src/components/FAQSection.astro` (35 lines, no `<style>` block).

```
Props: { faqs?: Array<{question, answer}>, heading?: string, lang?: Language }   (:5-12)
const faqData    = faqs    || to('pages.pricing.faq.items')                      (:18)
const faqHeading = heading || t('pages.pricing.faq.heading')                     (:19)
```

Markup (`:22-35`):

```html
<section class="faq-section section-light">
  <div class="container">
    <h2>{faqHeading}</h2>
    <div class="faq-grid">
      <details class="faq-item"><summary>{q}</summary><p>{a}</p></details>
    </div>
  </div>
</section>
```

The defaulting at `:18-19` matters: **`pricing.astro:136` passes no props at all**, so the
pricing page relies on the fallback. Any change to that default silently changes the pricing
page.

CSS lives in `src/styles/pricing-page.css:511-585` (`.faq-section` `:511`, `h2` `:515`,
`.faq-grid` `:522`, `.faq-item` `:529`, `summary` `:537`, `::after` chevron `:549`,
`[open] summary::after` `:557`, `:focus-visible` `:561`, `::-webkit-details-marker` reset
`:567`, `p` `:571`, mobile `:579-585`, plus a rule at `:734`), with additional
`.faq-item` rules in `public/styles/main.css:640` and `:668`.

`src/pages/[lang]/disaster-recovery.astro:10-11` imports **both**
`disaster-recovery-page.css` and `pricing-page.css` - the latter purely to pick up the FAQ
styles. `disaster-recovery-page.css` contains no `faq` selectors. That coupling is fragile
but currently correct.

### Three rendering paths, 9 data sets, 55 items total

| surface | renderer | i18n node | count | item shape |
|---|---|---|---|---|
| `/[lang]/pricing` | `FAQSection`, no props (`pricing.astro:136`) | `pages.pricing.faq` | **12** | `{question, answer}` |
| `/[lang]/disaster-recovery` | `FAQSection` w/ props (`disaster-recovery.astro:122`) | `pages.disasterRecovery.faq` | **7** | `{question, answer}` |
| `/[lang]/resources/nis2-directive-summary` | inline `<details>` (`nis2-directive-summary.astro:86-95`) | `pages.resourcesNis2Directive.faq` | **6** | `{q, a}` |
| 6x resource brief pages | `src/components/resources/ResourceBriefPage.astro:118-130` | `pages.resourcesBrief.<deck>.faq` | **5 each = 30** | `{q, a}` |

Note the **two incompatible item shapes**: `{question, answer}` for the `FAQSection`
consumers, `{q, a}` for the two inline renderers (`nis2-directive-summary.astro:31`,
`ResourceBriefPage.astro:60`). Any consolidation must reconcile these.

`ResourceBriefPage.astro` uses a TEMPLATE namespace - `const ns = \`pages.resourcesBrief.${deckKey}\``
- which the dead-key gate resolves to `pages.resourcesBrief.*` (see (C) gates below).

### Structured data

`pricing.astro:29-41` builds a `schema.org/FAQPage` JSON-LD from `pages.pricing.faq.items`
and injects it into `<head>` (`:53-55`). **Deleting or reordering pricing FAQ items changes
the emitted structured data**, which Google may have already indexed. No other FAQ surface
emits FAQPage JSON-LD (`StructuredData.astro:177` has a `'faq'` case but no FAQ page passes
`structuredDataType="faq"`).

### FULL question list with key paths

#### `pages.pricing.faq` - heading "Frequently Asked Questions", 12 items

Key path pattern: `pages.pricing.faq.items[N].question`

| N | question |
|---|---|
| 0 | Is there a free trial? |
| 1 | Do I need a credit card to start? |
| 2 | Can I upgrade or downgrade my plan? |
| 3 | Do you offer annual billing? |
| 4 | What payment methods do you accept? |
| 5 | How are machines counted? |
| 6 | Does Rediacc run on my own servers? |
| 7 | How many machines does each plan cover? |
| 8 | What does Enterprise include? |
| 9 | Do you offer discounts for education or nonprofits? |
| 10 | What happens if I cancel? |
| 11 | How are cluster nodes counted? |

Observation for scoring: 5 and 7 and 11 are three separate answers to "how does counting
work"; 0 and 1 are two halves of one trial question.

#### `pages.disasterRecovery.faq` - heading "Frequently Asked Questions", 7 items

Key path pattern: `pages.disasterRecovery.faq.items[N].question`

| N | question |
|---|---|
| 0 | Can I upgrade or downgrade my plan? |
| 1 | What payment methods do you accept? |
| 2 | Is there a free trial available? |
| 3 | What's included in support? |
| 4 | How fast can I recover from a disaster? |
| 5 | Are my backups actually tested and verified? |
| 6 | What happens to my data if the service goes down? |

Observation for scoring: **items 0, 1, 2 are near-verbatim duplicates of pricing items
2, 4, 0**. Three of seven slots on a disaster-recovery page are recycled billing questions.
Only 4, 5, 6 are on-topic.

#### `pages.resourcesNis2Directive.faq` - heading "Frequently asked", 6 items

Key path pattern: `pages.resourcesNis2Directive.faq.items[N].q`

| N | question |
|---|---|
| 0 | Is this an authoritative translation of the directive? |
| 1 | Who is in scope under NIS2? |
| 2 | When did NIS2 enter into force, and what is the transposition deadline? |
| 3 | What are the maximum fines? |
| 4 | Does NIS2 apply to non-EU companies? |
| 5 | How does Article 23 incident reporting work? |

This is the only FAQ set on the site with no duplication and no billing content.

#### `pages.resourcesBrief.<deck>.faq` - heading "Questions readers asked", 5 items x 6 decks = 30

Decks: `ransomwareSurvival`, `multiCloudAlways`, `verifiedBackups`, `encryptionControl`,
`devEnvironments`, `preemptiveDefense`.

Key path pattern: `pages.resourcesBrief.<deck>.faq.items[N].q`

**All six decks carry the byte-identical five questions:**

| N | question |
|---|---|
| 0 | Who is this brief written for? |
| 1 | Is there a non-technical version? |
| 2 | What happens to my email? |
| 3 | Why btrfs? |
| 4 | Does this apply to managed services like AWS RDS? |

Observation for scoring: 30 items expressing 5 distinct questions. Across 13 locales that is
**390 catalog leaves for 5 questions**, each re-naturalized whenever English changes.
"Why btrfs?" appears on the encryption-control and multi-cloud decks with the same answer as
on the ransomware deck. This is the single largest FAQ cleanup opportunity on the site, and
the cheapest: the six branches are identical, so they could collapse to one shared branch
referenced by all six decks.

### What deleting an FAQ item costs

An item is an **array element** under `<ns>.faq.items` in **13 catalog files**:
`src/i18n/translations/{en,ar,de,es,et,fr,it,ja,ko,pt,ru,tr,zh}.json`. Deletion is a JSON
array splice in each - **not** a component edit - except the resource-brief decks, where the
array is per-deck, so one logical question is 6 splices per locale = 78 splices.

Because these are ARRAYS and not named keys, deleting item 3 of 12 **renumbers items 4-11**
in every locale and in both hash ledgers. Removing a whole `faq` branch is therefore far
cheaper than removing individual items: a branch removal touches one node per locale and
renumbers nothing.

Gates that fire:

1. **`scripts/check-translation-completeness.ts:739-766`** (repo root) - hard-fails on
   ORPHAN KEYS, "present in this locale, absent from English". `orphanKeys` is computed at
   `:739` and pushed to `errors` at `:760-766` with the message "remove them; English is the
   source of truth and these are unreachable". So an English-only deletion is a CI failure;
   all 13 files must be spliced together. The comment at `:724-738` records why this check
   exists: the renet catalogs accumulated 191 orphans through this exact blind spot, and they
   were corrupted key NAMES (`bridge.create_failed` -> `bridge.create_<ar>`).
   Wired as `check:i18n:completeness` (`package.json:172`) and inside `check:i18n` (`:170`).

2. **`scripts/check-translation-hashes.ts:158`** - reads
   `src/i18n/translations/.translation-hashes.json`, which holds **6,230 per-key entries**
   with flat dotted paths including `pages.disasterRecovery.faq.items.0.question`,
   `...items.0.answer`, `...faq.heading`, and so on. Renumbering invalidates the hashes of
   every shifted item. Regenerate with `npm run i18n:generate-hashes`
   (`package.json:206` -> `scripts/generate-translation-hashes.ts`; also aliased
   `fix:i18n` `:195` and `i18n:update-hashes` `:208`).

3. **`scripts/check-i18n-naturalization.ts:36`** - reads
   `src/i18n/translations/.naturalized-hashes.json`, shaped
   `{ $meta, languages: { tr: { "<flat.key.path>": hash, ... }, de: {...}, ... } }` for the
   12 non-English locales. Same flat paths (`beforeAfter.after.points.0` etc.). Renumbering
   makes every shifted surviving item look STALE, and `check-i18n-naturalization` is a
   BLOCKING gate in `check:i18n` (`package.json:170`) that fails when an already-naturalized
   key goes stale. A `.naturalized-hashes.json.lock` sits beside it.

4. **`scripts/check-dead-translation-keys.ts`** - wired as `check:ci-dead-translation-keys`
   (`package.json:226`) and included in `check:i18n` (`:170`). This is the gate that REWARDS
   deletion: it walks catalog -> source and reports keys nothing can reach. Its header
   (`:13-18`) records the current state: **300 dead English leaves across 110 branches**,
   including all of `pages.pricing.plans.*.features` and 55 `ui.*` leaves under pricing and
   disaster recovery, one of which reads "Includes $9,999 setup credit". Reachability is
   decided by PATTERN prefix match from three shapes (`:20-36`): literal `t('a.b')` calls,
   template calls with a resolved `ns` (including template namespaces such as
   `pages.resourcesBrief.${deckKey}` -> `pages.resourcesBrief.*`), and any dotted 3+-segment
   string anywhere in sources. Floors `MIN_SOURCE_FILES = 50` and `MIN_PATTERNS = 200`
   (`:60-62`) guard against the scan losing its input.

   **Important constraint (`:38-41`, verbatim):** "A KEY REPORTED HERE THAT IS ACTUALLY
   REACHED IS A BUG IN THIS FILE, NOT A CANDIDATE FOR AN ALLOWLIST." There is no allowlist to
   add to; the fix is always to teach the extractor the new shape. Confirmed by the error
   text at `:384`: "see: extend referencePatterns() rather than allowlisting the key."

5. **Structured data**, non-gate: `pricing.astro:29-41` rebuilds the FAQPage JSON-LD from
   whatever survives, automatically. No action needed, but the emitted schema changes.

Practical deletion recipe: splice all 13 locales in one pass, run
`npm run i18n:generate-hashes`, then `npm run check:i18n`. The naturalization ledger will
need the shifted keys re-recorded; consult `docs/i18n/CONVENTIONS.md` before touching any
translation.

---

## (D) Illustration assets available

### `src/assets/images/illustrations/` - 22 SVGs, the primary inventory

Naming: kebab-case, one file per solution slug, with one `.mobile.svg` viewport variant.

```
ai-pentesting.svg                  immutable-backups.svg
audit-trail.svg                    infrastructure-costs.svg
backup-verification.svg            instant-recovery.mobile.svg
cloud-outage-protection.svg        instant-recovery.svg
continuous-security-testing.svg    integrations.svg
data-sovereignty.svg               kubernetes-cluster-mobility.svg
encryption.svg                     migration-safety.svg
environment-cloning.svg            production-parity.svg
failover-testing.svg               rapid-recovery.svg
                                   retention-compliance.svg
                                   safe-os-testing.svg
                                   vendor-lock-in.svg
                                   vulnerability-management.svg
```

### How they are embedded - two mechanisms, both INLINING the source

The rationale is recorded at `src/components/solution-pages/SPProblem.astro:40-43`: "The
drawings are textless and decorative (the meaning lives in the copy around them), so one
file serves every locale and viewport, inlined so it can paint from the theme-aware
`--illustration-*` tokens." That is why they are inlined rather than `<img src>`.

1. **Static named imports** - `src/config/solution-pages.ts:8-29`, 22 lines of
   `import illustrationAiPentesting from '../assets/images/illustrations/ai-pentesting.svg'`
   style imports (camelCase `illustration<PascalSlug>` naming).

2. **Dynamic by slug** - `src/utils/solution-illustration.ts:10` uses
   `import.meta.glob<string>('../assets/images/illustrations/*.svg', {...})`, and
   `:19` returns `illustrationModules[\`../assets/images/illustrations/${slug}.svg\`] ?? null`.
   Consumed at `SPProblem.astro:2,43,52-54`:
   `const illustrationSvg = slug ? resolveSolutionIllustration(slug) : null` then
   `{illustrationSvg && <div class="sp-problem-illustration" set:html={illustrationSvg} />}`.
   The slug is passed down from `PersonaPage.astro:104`
   (`<SPProblem problem={...} slug={config.illustrationSlug} />`).
   `src/config/persona-pages.ts:27` documents the convention: "per slug under
   `src/assets/images/illustrations/`".

   **Note:** `SPProblem` stacks the illustration BELOW the copy (`:48-54`: overline, h2, p,
   then illustration). It is not a side-by-side layout.

### Other raster assets

`src/assets/images/`: `archtitecture.png` (typo is in the real filename), `problem.png`,
`solution.png`, `rediacc_resources_repos.png`.

### `public/img/` - 24 SVG diagrams, referenced by URL (not inlined)

`account-api-token-lifecycle.svg`, `account-auth-flow.svg`, `account-device-code-flow.svg`,
`account-permission-flow.svg`, `account-registration-flow.svg`, `account-role-hierarchy.svg`,
`account-subscription-flow.svg`, `account-team-structure.svg`, `arch-docker-isolation.svg`,
`arch-full-stack.svg`, `arch-operating-modes.svg`, `arch-two-tool.svg`,
`backup-optimization.svg`, `backup-strategy-flow.svg`, `blackout-continuity.svg`,
`cross-backup.svg`, `dev-environments.svg`, `hub-architecture.svg`,
`hybrid-cloud-scaling.svg`, `legacy-scaling.svg`, `repo-migrate-flow.svg`,
`risk-free-upgrades.svg`, `time-travel-recovery.svg`, plus `docs-thumbs/` and `tutorials/`
subdirectories. These are docs/architecture diagrams consumed from markdown by URL. Because
they are not inlined they cannot paint from `--illustration-*` theme tokens.

### `public/assets/`

Social banners (`banner-{discord,facebook,github,reddit,x,youtube}.{png,svg}`,
`linkedin-banner{,-2x}.{png,svg}`), `plyr.svg`, an `images/` subdir, and 20 PDFs
(6 briefs x `-cto`/`-exec`, plus `nis2-directive-summary` in 13 locales + a default).

### Gitignored, absent from a fresh checkout

`packages/www/.gitignore` excludes `public/assets/tutorials/video/`,
`public/assets/videos/solutions/`, `public/assets/tutorials/audio/`, and `public/media/`
(synced to Cloudflare R2 / `media.rediacc.com`), plus `*.debug-frames/`.

### Relevant conflict for the planned work

`vendor-lock-in.svg` already exists as a file-based illustration in
`src/assets/images/illustrations/`, yet `PricingTrustSection`'s six lock-in drawings are
hand-inlined inside the `.astro` file. The two conventions are unreconciled.

For a rebuilt Difference section, the **file-based route is the established, reusable one**:
drop SVGs into `src/assets/images/illustrations/` and pull them with
`resolveSolutionIllustration(slug)` (or a sibling glob helper), which gives locale-independence,
theme-token painting, and no component edit per asset. `PricingTrustSection`'s inline-JSX
SVGs are a one-off and should not be treated as the pattern to copy.

---

## Answer to the direct question: is there a reusable alternating text/visual component?

**No. None exists.**

Sweep performed across all of `src/components/` (including the 34 files in
`solution-pages/`), `src/styles/*.css`, and `public/styles/main.css`, searching for
`reverse`, `row-reverse`, `:nth-child(even)`, and `direction: rtl`. Complete result set:

- `src/styles/pricing-page.css:1252-1258` + `PricingTrustSection.astro:51,119,180` - the
  only alternating text/visual construct on the site
- `src/styles/cheatsheet.css:262,382` - table row striping, unrelated
- `src/styles/solution-pages.css:1164` - `.sp-tech-detail-cell:nth-child(even)`, a cell
  background rule, unrelated

Closest existing two-up-with-visual constructs, neither alternating nor reusable:

- `SPHomeNotASlice.astro:190-199` - `.sp-slice-winner`, a single `220px 1fr` grid with the
  SVG left and text right. One instance, no alternation, SVG inlined literally.
- `SPProblem.astro:52-54` - stacks its illustration below the copy, not beside it.

Reusing the pricing pattern for the Difference section therefore means **extracting it into
a component first** (ideally parameterized over `{title, description, visual}` with the
alternation derived from the index, and the `direction: rtl` hack replaced by `order` /
`grid-column` so `/ar/` works). The extraction does not exist today.

`.difference-row*` / `.difference-zoom*` at `public/styles/main.css:1956-2090` are the
remains of the previous alternating implementation on this very section and currently have
no consumer.
