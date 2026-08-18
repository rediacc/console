# RESEARCH — component primitives (sx-primitives)

Research date 2026-08-17. Measured against the running dev server on
`http://localhost:4321`, 15 of the 61 pages sampled, browser session
`sx-primitives`, viewport 1440x900 unless stated.

---

## 1. Verdict

There is no primitive layer. There are 40 independent button implementations,
33 independent card shells, 5 independent form implementations and 6
independent overlay implementations, spread across 9 stylesheets that do not
know about each other, and a `--radius-*` token scale in `main.css:248-254`
that most of them ignore in favour of hardcoded `10px`, `15px`, `100px`,
`9.6px`. The site already contains a complete, well-built form system
(`main.css:2717-2840`: `.form-group`, `.form-label`, `.form-input/select/
textarea`, `.form-error`, `:invalid`/`:valid`/`[aria-invalid]` states) that
**zero components use** — the shared primitive was written, then bypassed five
times. The highest-leverage move is therefore not "design a system", it is
**collapse to one Button, one Card, one Field, one Overlay and delete the
~4,500 lines of per-page CSS that reimplement them** — because the drift is not
deliberate design, it is 8/12/14/15/16px radii chosen by whichever stylesheet
the component happened to be born in.

---

## 2. What we have

### 2.1 Buttons — 45 distinct computed treatments, 40 class roots

Method: `document.querySelectorAll('a,button,input[type=submit],[role=button]')`,
keep anything with a background, a border, or a `btn|button|cta` class; tuple =
`(border-radius, padding, font-size, font-weight, border, background, color,
box-shadow, transition, text-transform, letter-spacing, height)` read from
`getComputedStyle`. Script:
`scratchpad/js/btn.js`; per-page dumps in `scratchpad/dump/btn*.json`.

| Page | button-like elements | distinct treatments |
|---|---|---|
| `/en` | 27 | **20** |
| `/en/pricing` | 28 | **20** |
| `/en/solutions/encryption` | 30 | 19 |
| `/en/install` | 33 | 17 |
| `/en/partners` | 22 | 17 |
| `/en/docs` | 43 | 16 |
| `/en/downloads` | 25 | 16 |
| `/en/for-ctos` | 28 | 17 |
| `/en/professional-services` | 24 | 15 |
| `/en/company` | 20 | 15 |
| `/en/roi-calculator` | 23 | 15 |
| `/en/contact` | 19 | 14 |
| `/en/solutions` | 18 | 13 |
| `/en/blog` | 18 | 13 |
| `/en/newsletter` | 19 | 13 |
| **union of the 15** | — | **45 distinct tuples / 40 class roots** |

Property spread across those 45 tuples:

| Property | distinct values | the values |
|---|---|---|
| `border-radius` | **6** | `4px`, `8px`, `9999px`, `10px`, `12px`, `0 0 4px 4px` |
| `padding` | **18** | `16/32`, `14/32`, `16/40`, `12/24`, `14/24`, `12/22`, `12/16`, `8/20`, `8/16`, `8/12`, `6.5/14.5`, `4/12`, `12/8`, `0/12`, `28/24`, `12/12`, `8/8`, `0` |
| `font-size` | **9** | `12.8`, `14`, `15`, `16`, `17`, `18`, `20.8`, `25.6`, `28.8` px |
| `font-weight` | **4** | 400, 500, 600, 700 |
| `box-shadow` | 3 | none, `0 1px 3px rgba(0,0,0,.08)`, `0 4px 20px rgba(74,124,63,.25)` |
| `transition` | **20** | 20 hand-written property lists for the same hover |

**The primary CTA is implemented nine times.** Same job ("the green button you
click"), nine independent definitions:

| Class | file:line | radius | padding | size/weight | fill |
|---|---|---|---|---|---|
| `.btn.btn-primary` | `public/styles/main.css:1683,1721` | `9999px` | `16/32` | 18px / 400 | gradient `--color-brand-primary → --color-brand-secondary` |
| `.nav-cta-btn` | `public/styles/main.css:1004` | `9999px` | `8/16` | 16px / **700** | `rgb(85,107,47)` |
| `.sidebar-account-cta` | `public/styles/main.css:1214` | `8px` | `12/16` | 16px / **700** | `rgb(85,107,47)` |
| `.sp-btn-primary` | `src/styles/solution-pages.css:171` | `8px` | `14/32` | **17px** / 600 | gradient + `0 4px 20px` green glow |
| `.pt-btn-primary` | `src/pages/[lang]/partners.astro` | `8px` | `12/24` | 16px / 600 | `rgb(85,107,47)` |
| `.newsletter-button` | `src/styles/newsletter.css:75` | `8px` | `8/16` | 14px / 500 | `rgb(85,107,47)` |
| `.sp-download-short__button` | `src/styles/solution-pages.css:2580` | `8px` | `12/22` | **15px** / 600 | **`rgb(74,124,63)`** |
| `.sp-lead-magnet-button__cta` | `src/styles/lead-magnet-modal.css:281` | `8px` | `12/22` | **15px** / 600 | hardcoded |
| `.contact-inline-submit` | `public/styles/contact-modal.css:376` | `4px` | `8/16` | 16px / 500 | `--color-brand-primary` |

Two different greens ship as "the brand button": `rgb(85,107,47)` (#556B2F) and
`rgb(74,124,63)` (#4A7C3F). Both appear on `/en/solutions/encryption`.

Screenshot strip (real cloned DOM nodes, side by side):
`scratchpad/shots/sx-primitives/strip-buttons-global.png` — five green filled
buttons at three radii, three type sizes and three weights; and
`.cf-cta-btn` ("Start free trial") rendered as a *grey* tertiary button while
`.btn-primary` ("ROI Calculator →") is a green pill. Solution-page family:
`scratchpad/shots/sx-primitives/strip-solution-primitives.png`.

**The codebase already knows about the sprawl and papered over it.**
`main.css:1745-1770` defines `.cta-bolt`, a cross-cutting `!important`
override whose own comment says it exists to *"override background regardless
of the underlying button class (`.cf-cta-btn`, `.sp-btn-primary`,
`.dp-btn-primary`, `.btn-primary`)"*. That comment is the census, written by
the site itself. See §2.9 — the class ships on zero pages.

### 2.2 Cards — 33 shells, 5 radii within 8px of each other

Method: block elements with `border-radius >= 4px`, real padding, and a
surface (border, shadow, or a background differing from the parent).
`scratchpad/js/card.js`, dumps `scratchpad/dump/card*.json`. 37 raw tuples of
which 4 are buttons that satisfy the same test — **33 genuine card shells**.

| Property | distinct values |
|---|---|
| `border-radius` | **7** — `8px`, `12px`, `14px`, `15px`, `16px`, `9999px`, `8px 0 0 8px` |
| `padding` | **14** — 16, 20, 24, 32, 40, `28/24`, `32/28`, `36/28`, `36/40`, `24/32`, `16/32`, `12/8`, `14/6`, 8 |
| `border` | **16** — including two neutral greys used interchangeably |
| `box-shadow` | 5 |

The two greys are the tell:

- `rgb(210,210,215)` = `--color-border` from `public/styles/main.css` — used by
  `.pt-card`, `.value-card`, `.featured-card`, `.method-card`, `.cf-pricing-card`,
  `.contact-form-section`, `.contact-method`, `.install-next-steps-card`.
- `rgb(229,229,229)` = `--sp-border-light` from `src/styles/solution-pages.css` —
  used by `.sp-explore-card`, `.sp-slice-card`, `.sp-why-now-card`,
  `.sp-roi-card`, `.sp-download-short__card`, `.sp-roi-calculator`.

Nothing chose between them. A card is `#d2d2d7` or `#e5e5e5` according to which
stylesheet its component was written in.

**One page mixes three card systems.** `/en` renders `.sp-why-now-card`
(12px / `32px 28px` / `#e5e5e5`), `.sp-slice-card` (12px / `28px 24px` /
`#e5e5e5`) and `.cf-pricing-card` (15px / `40px` / `#d2d2d7` + `0 4px 20px`
shadow) in three consecutive sections. Measured live; screenshots
`scratchpad/shots/sx-primitives/home-cards-slice.png` and
`home-cards-pricing.png`.

The drift strip — 16 shells rendered with their exact measured
radius/padding/border/shadow, so they can be compared without page context —
is `scratchpad/shots/sx-primitives/strip-card-shells.png`. They are visually
indistinguishable. Their definitions live in 8 files.

### 2.3 Badges / pills / chips — 31 treatments, three ways to say "pill"

`scratchpad/js/badge.js`, dumps `scratchpad/dump/badge*.json`.
Radius spread: **7 distinct** — and three of them mean *fully rounded*:
`9999px` (`.logo-wall-badge`, `.cf-badge`, `.pt-eyebrow`), `100px`
(`.sp-hero-badge`, `.sp-calc-result-tag`, `.sp-server-card-status`), `24px`
(`.hero-badge`).

The sharpest instance is on the homepage, measured live:

| | `.integrations-strip-badge` | `.logo-wall-badge` |
|---|---|---|
| defined | `public/styles/main.css:2509` | `public/styles/main.css:1669` |
| instances on `/en` | 15 | 6 |
| radius | **8px** | **9999px** |
| padding | `8px 16px` | `8px 16px` |
| font | 14px / 500 | 14px / 500 |
| background | `rgb(248,249,250)` | `rgb(247,247,248)` |
| border | `1px rgba(0,0,0,0.08)` | `1px rgb(210,210,215)` |

Same role (a technology name), same padding, same type, backgrounds one hex
step apart — and one set is a rounded rectangle while the other is a pill.
Both are defined in the *same file*, 840 lines apart.

The "SELF-HOSTED · RUNS ON YOUR OWN SERVERS" eyebrow
(`src/i18n/translations/en.json:158`) renders as `.sp-hero-badge`
(`src/styles/solution-pages.css:121`: `100px` radius, 12px, `0.1em`
letter-spacing, `rgba(74,124,63,0.15)` fill) via
`src/components/solution-pages/SPHomePage.astro:35`. There are **four other
eyebrow implementations** for the same typographic device:
`.pt-eyebrow` (`src/pages/[lang]/partners.astro:170`, `9999px`, 12.8px,
`0.512px` tracking, solid `#556B2F` fill),
`.resource-brief-eyebrow` (`src/components/resources/ResourceBriefPage.astro:156`),
`.resource-eyebrow` (`src/pages/[lang]/resources/nis2-directive-summary.astro:117`),
`.sp-calc-result-tag` / `.sp-server-card-status` (uppercase micro-labels at
`0.66px` and `1.2px` tracking).

### 2.4 Forms — five systems, and a sixth that nobody uses

Five independent form implementations, each with its own success/error class
namespace and its own `useState` submit lifecycle:

| Component | lines | success class | error class | `useState` calls |
|---|---|---|---|---|
| `src/components/ContactForm.tsx` | 213 | `.contact-inline-success` | `.contact-inline-error` | 5 |
| `src/components/ContactModal.tsx` | 335 | `.contact-modal-success` | `.contact-modal-error` | 6 |
| `src/components/NewsletterSignup.tsx` | 169 | `.newsletter-success-content` | `.newsletter-error` | 4 |
| `src/components/PartnerApplicationForm.tsx` | 441 | `.partner-form-success` | `.partner-form-error` | 9 |
| `src/components/LeadMagnetModal.tsx` | 320 | `.lead-magnet-modal__success` | `.lead-magnet-modal__error` | 6 |

Measured input geometry (`scratchpad/js/form.js`, `dump/form*.json`) — three
mutually incompatible field styles:

| System | radius | padding | font-size | border colour | height |
|---|---|---|---|---|---|
| newsletter (`src/styles/newsletter.css:46`) | `8px` | `8/12` | 14px | `rgb(210,210,215)` | 40.75 / 44px |
| contact (`public/styles/contact-modal.css:122,321`) | `4px` | `8/12` | 16px | **`rgb(138,138,139)`** | 44px |
| partner (`src/pages/[lang]/partners.astro`) | `8px` | `12/12` | 16px | `rgb(210,210,215)` | 48 / 52px |

Labels: **4 distinct treatments** — `14px/500/#1a1a1a/mb:0` (contact,
partners), `13.6px/500/#4a4a4f/mb:6px` (roi-calculator),
`14px/400/#1a1a1a` (partner checkboxes), `14px/500/#4a4a4f/mb:8px`
(solution pages).

Error text: `--color-error` in three of them, hardcoded `#b91c1c` / `#fca5a5`
at 13px in `src/styles/lead-magnet-modal.css:173-183`.

**The system that should have prevented this already exists and is dead.**
`public/styles/main.css:2717-2840` is a complete field system —
`.form-group`, `.form-label`, `.form-input`, `.form-select`, `.form-textarea`,
`.form-error` (with `::before` icon), `:invalid:not(:placeholder-shown)`,
`:valid`, `[aria-invalid='true']`, `:disabled` (`main.css:635`), and a mobile
breakpoint (`main.css:415`). Verified unused two ways:

```
$ grep -rn 'form-input' packages/www --include=*.astro --include=*.tsx \
      --include=*.ts --include=*.md --include=*.mdx --include=*.json
(no output)
```

and live, on four pages:
`document.querySelectorAll('.form-input,.form-group,.form-textarea,.form-select').length`
→ `0` on `/en`, `/en/pricing`, `/en/solutions/encryption`, `/en/partners`.

`contact-modal.css` is itself two copies of the same form. Normalising
`.contact-modal-*` and `.contact-inline-*` to a common prefix: 30 modal rules,
18 inline rules, **15 selectors present in both, 11 with byte-identical
bodies** (`.X-field`, `.X-field label`, `.X-field select`, `.X-field
input::placeholder`, `.X-field *:focus-visible`, `.X-submit`, `.X-submit:hover`,
`.X-submit:disabled`, `.X-submit:focus-visible`, `.X-error`, `[dir='rtl']
.X-field select`).

### 2.5 Overlays — six implementations, zero shared code

| Component | lines | backdrop class | backdrop opacity | blur | z-index token | fade keyframe |
|---|---|---|---|---|---|---|
| `ContactModal.tsx` | 335 | `.contact-modal-backdrop` (`public/styles/contact-modal.css:3`) | `--opacity-40` | 1px | `--z-toast` | `contactFadeIn` |
| `SearchModal.tsx` | 470 | `.search-modal-backdrop` (`public/styles/search-modal.css:4`) | `--opacity-40` | 1px | `--z-toast` | `fadeIn` |
| `RegionPickerModal.tsx` | 274 | `.region-picker-backdrop` (`public/styles/region-picker.css:3`) | `--opacity-40` | 1px | `--z-toast` | `regionFadeIn` |
| `LeadMagnetModal.tsx` | 320 | `.lead-magnet-modal-backdrop` (`src/styles/lead-magnet-modal.css:11`) | **`0.5` hardcoded** | none | `--z-toast` | `lead-magnet-fade-in` |
| `NewsletterReturnPopup.tsx` | 157 | `.newsletter-return-popup-overlay` (`src/styles/newsletter.css:319`) | **`color-mix(… 35%)`** | none | **`--z-modal`** | none |
| `ImageModal.astro` | 167 | `.image-modal` (`public/styles/main.css:3075`) | **`--opacity-60`** | **2px** | `--z-toast` | none |

Panels: 4 distinct treatments — `--radius-md` + shared shadow at max-width
480px / `--container-xs` / 620px (contact / search / region), hardcoded
`12px` + `32px 28px` + 480px (`lead-magnet-modal.css:39-49`), `--radius-xl` +
`--space-8` + 36rem (`newsletter.css:330-336`), `--radius-md` + `--space-8` +
500px (`main.css:3092`). Five distinct close-button treatments.

Behaviour is copy-pasted, not shared. `handleFocusTrap(e, modal, close)` is
**byte-identical** in `ContactModal.tsx:29-49`, `LeadMagnetModal.tsx:32-52` and
`RegionPickerModal.tsx:9-27` except for the focusable-elements selector string;
`SearchModal.tsx` reimplements the same logic inline at lines 199-278;
`NewsletterReturnPopup.tsx:75-90` does Escape + scroll-lock but **no focus
trap at all**. `document.body.style.overflow = 'hidden'` is written five times.

CSS duplication, normalising the class prefixes and the keyframe names:
contact vs search share **173 identical lines** (of 375 / 331);
contact vs region share 92 (of 375 / 180).

The site ships **19 `@keyframes`** across its stylesheets, of which 13 do two
jobs: 8 fade-ins (`fadeIn`, `fade-in`, `contactFadeIn`, `regionFadeIn`,
`lead-magnet-fade-in`, `personaMenuFadeIn`, `megaMenuFadeIn`,
`methodCardFadeIn`) and 5 slide-ups (`slideUp`, `contactSlideUp`,
`regionSlideUp`, `lead-magnet-slide-in`, `newsletter-slide-up`).

Three of these stylesheets ship on **every page** —
`BaseLayout.astro:240-242` loads `search-modal.css`, `contact-modal.css` and
`region-picker.css` with the `media="print"` onload trick. 23,312 bytes of
near-duplicate CSS on every route, for three dialogs most visitors never open.

### 2.6 Tabs / segmented controls — five implementations, three ARIA contracts

| Control | file | radius | padding | type | ARIA |
|---|---|---|---|---|---|
| `.platform-tab` | `src/styles/platform-tabs.css:13`, `PlatformTabs.tsx:22-28` | `8px` | `8/16` | 14px / 500 | `role="tablist"` + `role="tab"` + `aria-selected` |
| `.comparison-plan-toggle-btn` | `src/styles/pricing-page.css:2140`, `PricingComparison.astro:50-57` | `9999px` | `4/12` | 12.8px / 600 | `role="tablist"` + `role="tab"` + `aria-selected` |
| `.billing-toggle-btn` | `src/styles/pricing-page.css:1888`, `PricingPreview.astro:67-84` | `9999px` | `8/20` | 14px / 600 | `role="radiogroup"` + `role="radio"` + `aria-checked` |
| `.sp-roi-size-btn` | `src/styles/solution-pages.css:2181`, `SPRoiCalculator.tsx:201-206` | `10px` | `12/8` | 18px | **none** — no `aria-pressed`, no `aria-selected` |
| `.docs-top-tab-link` | `src/components/DocsTopTabs.astro:143` | n/a | n/a | 14px / 500 | underline nav, no tab roles |

Two of the five are pills, one is 8px, one is 10px, one is an underline. The
`.billing-toggle-btn` and `.comparison-plan-toggle-btn` sit on the *same page*
(`/en/pricing`) at `8/20` and `4/12` padding.

### 2.7 Icons — no library, 121 hand-inlined SVGs, 9 stroke weights

No icon dependency in `packages/www/package.json`. **121 inline `<svg>`
elements across 37 code files** (`grep -rho '<svg' src --include=*.astro
--include=*.tsx --include=*.ts | wc -l`; the other 521 hits are illustration
assets under `src/assets/images/illustrations`, not icons).

Four nominal "icon modules" —
`src/components/CategoryIcons.tsx` (6),
`src/components/icons/PlatformIcons.tsx` (3),
`src/components/icons/ClipboardIcons.tsx` (2),
`src/components/solution-pages/icons.ts` (**43**) — plus ~30 one-off files
that inline their own.

Consistency, measured across all inline SVG:

- `stroke-width`: **9 distinct values** — `2` (58), `1.5` (42), `1` (12),
  `1.75` (9), `1.25` (9), `2.5` (7), `3` (5), `4` (2), `0` (2). Icons at 1px
  and icons at 2.5px in the same visual system read as two different sets.
- `viewBox`: `0 0 24 24` (79), `0 0 16 16` (11), `0 0 20 20` (9), plus
  6 bespoke illustration boxes.
- explicit `width` on the tag: `16` (10), `48` (5), `20` (4), `14` (4),
  `18` (3), `24` (1), `64` (1), `120` (1).

### 2.8 Interaction states

Live CSSOM census on `/en/pricing` (walks every loaded stylesheet, collects
every rule whose `selectorText` contains `:focus`):

- **70 focus rules, 15 distinct outline declarations.**
- The intended one — `outline: 2px solid var(--color-brand-primary);
  outline-offset: 2px` — covers 39 of them. Good.
- Four ring *colours* beyond it: `--color-brand-bolt` (3px),
  `--color-accent-green`, `--sp-brand-primary, #4a7c3f`,
  `rgba(255,255,255,0.8)`, plus a `3px solid Highlight` forced-colors rule.
- Four offsets: `2px` (58), `-2px` (5), `4px` (2), `-1px` (1).
- **6 rules set `outline: none` inside `:focus-visible`.** Four replace it with
  a `box-shadow` ring and are fine (`main.css:2760`, `contact-modal.css:138`
  and `:337`, `newsletter.css:67`); two do not obviously —
  `region-picker.css:154-158` (`.region-picker-card:focus-visible`) and
  `search-modal.css:124-125` (`.search-modal-input:focus-visible`).

`transition` is where consistency collapses entirely: **20 distinct hand-written
property lists** across 45 button treatments, with durations 0.15s / 0.2s /
0.3s and one bare `transition: 0.2s` (`.sp-roi-size-btn`,
`src/styles/solution-pages.css:2181`) that animates *every* animatable property.

**axe-core audit** (`agent-browser a11y`, 6 pages). Violations that belong to
this domain:

| Violation | impact | where | note |
|---|---|---|---|
| `aria-hidden-focus` | serious | `#image-modal` | **on every page of the site** — `ImageModal.astro` is mounted in `BaseLayout.astro:430` with `aria-hidden` while containing focusable `.image-modal-close`, `.zoom-btn`, `.nav-btn` |
| `link-name` | serious | `.sp-bottom-cta-inner > .sp-btn-primary` on `/en/solutions/encryption` | a primary CTA link with no accessible name (it is the empty `a.sp-btn-primary` in the button dump) |
| `label` | **critical** | 3 × `input[type=range]` on `/en/solutions/encryption` | ROI-calculator sliders have no label |
| `color-contrast` | serious | 23 nodes on `/en/solutions/encryption`, 47 on `/en/docs`, `.cf-guarantee-text` on `/en`, `.footer-version` | |

Two unstyled native `input[type=text]` fields leak browser defaults
(`2px inset rgb(118,118,118)`, radius 0) into `/en/contact` and `/en/partners`
— honeypot fields, but they render.

### 2.9 Two dead primitives, one of them guarded by a gate that cannot fail

`.cta-bolt` — the `!important` "joker CTA" at `main.css:1745-1770` — appears in
**no markup anywhere**:

```
$ grep -rn 'cta-bolt' packages/www/src/ | grep -v '\.css'
(no output)
```

and live: `document.querySelectorAll('.cta-bolt').length` → `0` on `/en`,
`/en/pricing`, `/en/solutions/encryption`, `/en/partners`.

`scripts/check-cta-bolt-uniqueness.js` enforces "at most one `.cta-bolt` per
rendered page" and **is wired into `npm run ci`** via the root
`check:ci-cta-bolt` script (`package.json:131`). With zero instances, the
`<= 1` rule passes vacuously on every page and can never fail; the script's
own `=== 1` rule is skipped whenever `announcement.enabled` is false. A CI gate
is being paid for on a class that does not ship.

`packages/www/scripts/check-unused-css.js` exists, exits 1 correctly, and
currently reports **179 unused CSS classes**. Nothing runs it: `lint:css` and
`lint:all` are declared in `packages/www/package.json:11-13` and referenced by
no root script, no `.ci/` script and no workflow
(`grep -rn 'lint:css\|lint:all' package.json .ci` → no output). It also
under-reports — it flags `.form-label` (line 2723) but not its siblings
`.form-input` / `.form-select` / `.form-textarea` in the same dead block.

---

## 3. What claude.com / anthropic.com do

Same script, same criteria, same viewport.

| URL | button-like elements | distinct treatments | treatments **per** element |
|---|---|---|---|
| `https://claude.com/pricing` | 42 | **12** | **0.29** |
| `https://claude.com/` | 18 | 13 | 0.72 |
| `https://claude.com/product/claude-code` | 69 | 37 | 0.54 |
| `https://www.anthropic.com/` | **6** | **4** | — |
| `https://www.anthropic.com/news` | 11 | 8 | 0.73 |
| — | | | |
| `http://localhost:4321/en` | 27 | 20 | **0.74** |
| `http://localhost:4321/en/pricing` | 28 | 20 | **0.71** |

Read carefully: **raw tuple counts are not the story.** `claude.com` is two
stacks stitched together (a Next.js app shell on `/` and `/product/*`, Webflow
on `/pricing`), plus a HubSpot form and a cookie banner, so its raw variety is
not much lower than ours. The difference is *where the variety comes from*.

**Their variants are props on one component; ours are separate stylesheets.**
Enumerating class roots on `claude.com/` (`scratchpad/js/impl.js`):

```
Button#button        Button#variant-brand    Button#variant-primary
Button#size-medium   Button#variant-secondary Button#variant-tertiary
Button#hasLeadingIcon Button#hasTrailingIcon  Button#iconOnly
ButtonTextLink#textLink
```

That is **one `Button` component with four variants and three icon modifiers,
plus one text-link button** — every CTA on the page carries
`Button-module-scss-module__1SItCG__button`. Our equivalent list is 40
unrelated roots:

```
btn, btn-primary, btn-secondary, cf-cta-btn, contact-inline-submit, copy-btn,
doc-link, docs-copy-page-md, download-button, heading-share-trigger,
image-modal-close, language-trigger, nav-account-btn, nav-btn, nav-cta-btn,
nav-install-btn, nav-next, nav-prev, newsletter-button, partner-form-submit,
platform-tab, pt-btn-primary, pt-btn-secondary, search-btn,
sidebar-account-cta, sidebar-close-btn, sidebar-link, skip-nav-link,
sp-btn-primary, sp-btn-secondary-dark, sp-download-short__button,
sp-explore-card, sp-roi-size-btn, sp-share-cta, theme-toggle-btn, billing-toggle-btn,
zoom-btn, zoom-in, zoom-out, zoom-reset
```

Measured properties of their button system:

- **Radius: effectively one value.** `8px` on 26 of 66 measured tuples; the
  rest are `0px` (text buttons, 14) and `12px` (segmented tabs, 10). Their
  `Button` component is `8px`, full stop. Ours uses 6.
- **Ink: two colours.** `rgb(20,20,19)` and `rgb(250,249,245)` account for
  every filled button on `claude.com`. Solid fills observed: `rgb(20,20,19)`,
  `rgb(250,249,245)`, `rgb(232,230,220)`, `rgb(198,97,63)` (one accent).
  We ship two different greens for the same role.
- **Weight: 400 on 52 of 66 tuples**, 500 on 10. Their buttons are not bold.
  Ours run 400/500/600/700, with the nav CTA at **700**.
- **Padding: `8px/16px` on 19 of 66**, `8px/12px` on 4, `0/24px` on 2 — a
  visible 4px step. Ours has 18 padding tuples with no discernible step.
- **Borders are box-shadows.** Their outline variant is
  `box-shadow: … 0 0 0 1px rgb(209,207,197)` rather than a `border`, so hover
  and focus never shift layout by a pixel. Ours mixes `border: 1px` with
  `padding: calc(var(--space-2) - 1.5px)` compensation
  (`main.css:1031-1035`) to hide the shift.
- **Utility/token classes carry the type.** `u-text-style-body-2`,
  `u-text-style-caption`, `u-weight-semibold`, `u-border-tertiary`,
  `u-gap-m`, `u-theme-white` on `claude.com/pricing`. Type and spacing come
  from a named scale, not from the component.

Cards, both reference sites, 6 pages: **17 distinct tuples**, radius `24px`
(7) / `12px` (5) / `16px` (2), **padding `32px` on 8 of 17** and `8px` on 5.
Two radii and one padding do essentially all the work. Ours: 33 shells,
7 radii, 14 paddings.

`https://www.anthropic.com/` is the extreme case and the operator's stated
reference: the entire homepage renders **6 button-like elements in 4
treatments**, and exactly **1 card**. Simplicity there is not a styling
achievement, it is a *count* achievement — there is very little on the page.

---

## 4. The delta

| Primitive | Ours | claude.com / anthropic.com | Gap |
|---|---|---|---|
| Button implementations | **40 class roots** in 9 stylesheets | **1 component**, 4 variants + 3 icon modifiers, + 1 text-link | 40 → 2 |
| Button computed treatments (union) | **45** | ~12 per page, one system | 45 → ~6 |
| Button radii | 6 (`4/8/9999/10/12/0 0 4 4`) | 1 (`8px`) for buttons, `12px` for tabs | 6 → 1 |
| Button paddings | **18** | 3 on a 4px step | 18 → 3 |
| Button font-sizes | 9 | 3 in-system | 9 → 3 |
| Button font-weights | 4 (incl. 700) | 400 dominant, 500 secondary | 4 → 2 |
| Button transitions | **20 hand-written lists** | 1 shared list | 20 → 1 |
| Brand fill colours for "primary" | **2** (`#556B2F`, `#4A7C3F`) | 1 | 2 → 1 |
| Card shells | **33** | ~6, radius 24/12, padding 32 | 33 → 1 + variants |
| Card radii | 7 (8/12/14/15/16/9999/asym) | 2 | 7 → 1 |
| Card neutral border greys | **2**, chosen by stylesheet | 1 | 2 → 1 |
| Badge/pill treatments | 31, three "fully rounded" values | 1 pill + 1 tag | 31 → 2 |
| Eyebrow implementations | 5 | 1 caption utility | 5 → 1 |
| Form systems | **5 live + 1 dead unused** | 1 (+ vendor HubSpot form) | 6 → 1 |
| Input styles | 3 (radius 4/8, height 40.75/44/52) | 1 `TextInput` module | 3 → 1 |
| Label treatments | 4 | 1 | 4 → 1 |
| Overlay implementations | **6**, no shared code | 1 `Dropdown`/`NavDropdown` panel primitive | 6 → 1 |
| Focus-trap implementations | 5 (3 byte-identical copies) | shared | 5 → 1 |
| Segmented controls | 5, three ARIA contracts | 1 `Tabs#button` | 5 → 1 |
| `@keyframes` | 19, of which 13 are fade/slide dupes | — | 19 → 6 |
| Icon sources | 4 modules + ~30 inline one-offs, 9 stroke weights | 1 icon set | 9 weights → 1 |
| Focus-ring declarations | 15 distinct, 4 offsets, 6 `outline:none` | 1 | 15 → 1 |

---

## 5. Proposed simplification

Ordered by leverage. Every item names the files it touches, the risk, and the
proof.

### P1 — One `.btn`, three variants, two sizes. Delete the other 37.

**Change.** Keep `.btn` (`main.css:1683`) as the only button. Variants:
`.btn--primary` (solid brand), `.btn--secondary` (1px border), `.btn--ghost`
(text + arrow, replaces `.sp-btn-secondary-dark` and the "Read the Docs →"
family). Sizes: `.btn--sm` (icon buttons, chrome, toggles) and default. All
geometry from tokens: `--radius-md` (8px), padding on the `--space-*` scale,
`--font-size-base`, weight 500 or 600 — **pick one and hold it**. Border
rendered as `box-shadow: inset 0 0 0 1px` so hover never shifts layout, as
claude.com does.

Rewrite these to `.btn` + a modifier and **delete their rules**:
`.nav-cta-btn` / `--secondary` (`main.css:1004-1062`),
`.sidebar-account-cta` / `--secondary` (`main.css:1214+`),
`.login-btn` (`main.css:1064`, already flagged unused),
`.cf-cta-btn` (`pricing-page.css:1825`),
`.sp-btn-primary` / `.sp-btn-secondary-dark` (`solution-pages.css:171,191`),
`.sp-download-short__button` (`solution-pages.css:2580`),
`.sp-lead-magnet-button__cta` (`lead-magnet-modal.css:281`),
`.newsletter-button` (`newsletter.css:75`),
`.pt-btn-primary` / `.pt-btn-secondary` / `.partner-form-submit`
(`src/pages/[lang]/partners.astro`),
`.contact-inline-submit` / `.contact-modal-submit` / `.contact-modal-done-btn`
(`contact-modal.css:230,376`, and the `.contact-modal-submit` twin),
`.copy-btn` (`install-page.css:172`),
`.docs-copy-page-md`, `.heading-share-trigger`.
Icon-button chrome (`.search-btn`, `.theme-toggle-btn`, `.hamburger-btn`,
`.sidebar-close-btn`, `.image-modal-close`, `.zoom-btn`, `.nav-btn`,
`.tv-ctrl-btn`) collapses into one `.btn--icon`.

Also **delete `.cta-bolt`** (`main.css:1745-1770`) and
`scripts/check-cta-bolt-uniqueness.js` with its root `check:ci-cta-bolt`
wiring. It overrides four button classes that will no longer exist, it ships
on zero pages, and its gate cannot fail (§2.9). Under "clean break, no
compatibility theater" this is a straight deletion, not a deprecation.

**Files.** `public/styles/main.css` (mine), `src/styles/solution-pages.css`,
`src/styles/newsletter.css`, `src/styles/lead-magnet-modal.css`,
`src/styles/install-page.css`, `public/styles/contact-modal.css` (mine),
`src/styles/pricing-page.css` (**sx-pricing**), `src/pages/[lang]/partners.astro`,
plus the `class=` sites in ~25 components.

**Risk.** High blast radius, low conceptual risk — it is a rename plus a
delete. The real hazard is `.btn` currently carrying `padding: 16/32` and
`font-size: 18px`, which is *large*; retargeting it to `12/24` and 16px shrinks
every existing `.btn` on the site. That is a visual change the operator should
see before it lands, not a bug.

**Proof.** Re-run `scratchpad/js/btn.js` over the same 15 pages. Success is
**distinct treatments ≤ 8 site-wide** (from 45) and **class roots ≤ 6** (from
40). Re-run the strip screenshot and compare against
`strip-buttons-global.png`.

### P2 — One `.card`. Delete 32 shells.

**Change.** One shell: `--radius-lg` (12px), `--space-6` padding,
`1px solid var(--color-border)`, no shadow by default, `--shadow-sm` on an
`.card--raised` modifier for pricing. Kill `--sp-border-light` entirely so
`#e5e5e5` and `#d2d2d7` become one value (**coordinate with sx-tokens**).
Delete `.sp-explore-card`, `.sp-slice-card`, `.sp-why-now-card`,
`.sp-roi-card`, `.sp-download-short__card`, `.sp-roi-calculator`,
`.sp-benefit-card`, `.pt-card`, `.pt-tier-card`, `.value-card`, `.value-stat`,
`.featured-card`, `.post-item`, `.method-card`, `.install-next-steps-card`,
`.download-item`, `.contact-method`, `.contact-form-section`, `.pt-apply-card`,
`.requirement-card`, `.services-benefits`, `.roi-cta-banner`,
`.edge-channel-banner`, `.sp-slice-winner`.
`.cf-pricing-card` / `.service-package-card` are **sx-pricing's** call.

**Files.** `main.css` (mine), `solution-pages.css`, `install-page.css`,
`downloads-page.css`, `professional-services-page.css`, `partners.astro`,
`company.astro`, blog index, `pricing-page.css` (**sx-pricing**).

**Risk.** Medium. `.sp-*` cards carry hover lift and glow that some solution
pages lean on; folding them to one shell removes visual emphasis the copy may
be relying on.

**Proof.** Re-run `scratchpad/js/card.js`. Success: **≤ 3 distinct card
tuples**, **1 radius**, **1 border colour**. Compare to
`strip-card-shells.png`.

### P3 — One `.field`. Adopt the form system that is already written.

**Change.** Use `main.css:2717-2840` — it is already good, already has
`:invalid` / `:valid` / `[aria-invalid]` / `:disabled` / mobile states, and is
already loaded on every page. Rewrite all five forms onto
`.form-group` / `.form-label` / `.form-input` / `.form-error`. Extract the
submit lifecycle (`idle → submitting → success → error` + Turnstile) into one
`useFormSubmit` hook; today it is five `useState` clusters totalling 30 state
variables.

Delete: `.newsletter-input` and its states (`newsletter.css:46-75`),
`.contact-modal-field *` **and** `.contact-inline-field *`
(`contact-modal.css:122-181, 321-390` — the 11 byte-identical pairs from §2.4),
`.partner-form-*` field CSS in `partners.astro`, the lead-magnet field CSS.
Also add labels to the three ROI-calculator range inputs (the `label` critical
axe violation) and remove the two native-styled honeypots' visual leak.

**Files.** `ContactForm.tsx`, `ContactModal.tsx`, `NewsletterSignup.tsx`,
`LeadMagnetModal.tsx`, `contact-modal.css`, `newsletter.css`,
`lead-magnet-modal.css`, `main.css` — **all mine**. Except
`PartnerApplicationForm.tsx` + `partners.astro`, which are **not** in my list;
flagged in §6.

**Risk.** Low. It is adoption of existing, tested CSS. The one real change is
that contact fields move from `4px` radius / `rgb(138,138,139)` border to the
shared `8px` / `--color-border`.

**Proof.** Re-run `scratchpad/js/form.js`: success is **1 field tuple, 1 label
tuple** across `/contact`, `/partners`, `/newsletter`, `/roi-calculator`, `/en`.
`grep -rn 'form-input' src` must go from 0 hits to many. Re-run
`agent-browser a11y` on `/en/solutions/encryption` — the `label` critical
violation must be gone.

### P4 — One `<Overlay>`. Delete five backdrops and three focus traps.

**Change.** One React `Overlay` component owning backdrop + panel + focus trap
+ Escape + scroll lock + `role="dialog"`/`aria-modal`, and one
`.overlay-backdrop` / `.overlay-panel` CSS pair in `main.css`. `ContactModal`,
`SearchModal`, `LeadMagnetModal`, `RegionPickerModal`,
`NewsletterReturnPopup` become content-only children.

Delete: `public/styles/contact-modal.css` (375 lines), `search-modal.css`
(331), `region-picker.css` (180) and the modal half of
`lead-magnet-modal.css`; the three `<link media="print">` tags at
`BaseLayout.astro:240-242` (**≈23 KB off every route**); the duplicated
`handleFocusTrap` in three files; 8 fade keyframes → 1, 5 slide keyframes → 1.

`NewsletterReturnPopup` gains a focus trap it does not currently have.

Separately, fix `ImageModal.astro` — the `aria-hidden-focus` serious violation
on **every page** (§2.8). Either `inert` the container while closed or stop
rendering its buttons until open.

**Files.** `ContactModal.tsx`, `SearchModal.tsx`, `LeadMagnetModal.tsx`,
`RegionPickerModal.tsx`, `NewsletterReturnPopup.tsx`, `ImageModal.astro`,
`main.css`, `contact-modal.css`, `region-picker.css`, `newsletter.css`,
`lead-magnet-modal.css` — all mine. `search-modal.css` + `SearchModal.tsx` are
not named in my list; flagged in §6. `BaseLayout.astro:240-242` is
**sx-chrome / sx-tokens** territory.

**Risk.** Medium-high: `SearchModal` has its own keyboard model (arrow-key
result navigation, `aria-selected` on results) that must survive the merge.

**Proof.** Keyboard-drive each overlay: open, Tab to the last control, Tab
again lands on the first; Escape closes; focus returns to the trigger; body
scroll restored. `agent-browser network requests` on a cold `/en` load must
show 3 fewer stylesheets. Total CSS bytes drop ≥ 20 KB.

### P5 — One segmented control, one eyebrow, one chip.

**Change.** `.segmented` + `.segmented__item` (pill, `--radius-full`,
`8px 16px`, 14px/500, `role="tablist"`) replaces `.platform-tab`,
`.billing-toggle-btn`, `.comparison-plan-toggle-btn`, `.sp-roi-size-btn`
— and `.sp-roi-size-btn` finally gets `aria-selected`. `.eyebrow` (one radius,
one tracking, one size) replaces `.sp-hero-badge`, `.pt-eyebrow`,
`.resource-eyebrow`, `.resource-brief-eyebrow`, `.hero-badge`. `.chip`
replaces `.integrations-strip-badge`, `.logo-wall-badge`, `.sp-tech-logo`,
`.sp-calc-result-tag`, `.sp-server-card-status`.

**Files.** `main.css` (mine), `platform-tabs.css` (delete, 52 lines),
`PlatformTabs.tsx` (mine), `solution-pages.css`, `partners.astro`,
`resources/*`, `pricing-page.css` (**sx-pricing**),
`PricingComparison.astro` / `PricingPreview.astro` (**sx-pricing**).

**Proof.** `scratchpad/js/badge.js`: **≤ 4 distinct badge tuples** (from 31),
**1 pill radius** (from 3). One `role` contract across all segmented controls.

### P6 — One icon set, one stroke weight.

**Change.** Consolidate `CategoryIcons.tsx`, `icons/PlatformIcons.tsx`,
`icons/ClipboardIcons.tsx`, `solution-pages/icons.ts` and the ~30 inline
one-offs into a single `icons/` module: `viewBox="0 0 24 24"`,
`stroke-width: 1.5`, `currentColor`, sized by a `size` prop. Nine stroke
weights become one.

**Files.** `CategoryIcons.tsx` (mine), `src/components/icons/*`,
`src/components/solution-pages/icons.ts`, ~30 call sites.

**Proof.** `grep -rhoE 'stroke-width=[^ ]+' src | sort -u` returns one value.
Inline `<svg>` count in code files drops from 121 to roughly the icon count.

### P7 — Make the dead-CSS gate real.

`packages/www/scripts/check-unused-css.js` already exists, already exits 1, and
already finds 179 unused classes — nothing runs it. Wire `lint:css` into
`npm run ci` **after** P1-P6 land (running it before would fail on 179
pre-existing entries). Fix its blind spot first: it flags `.form-label` but
misses `.form-input` / `.form-select` / `.form-textarea` in the same block, so
prove it can fire on those before trusting it.

**Risk.** Wiring an unrun gate into CI will surface work in other specialists'
files. Coordinate the timing with the lead.

---

## 6. Cross-domain consequences

Recorded, not touched.

1. **sx-tokens — the radius and colour scales are the shared seam.** Every
   proposal above resolves to `--radius-*` and `--color-border`. Two things
   must be decided *there*, not here: (a) `--sp-border-light: #e5e5e5` in
   `src/styles/solution-pages.css` must be deleted so it collapses onto
   `--color-border: #d2d2d7`; (b) the two brand greens `#556B2F`
   (`--color-brand-primary`) and `#4A7C3F` (`--sp-brand-primary`) must become
   one. My button and card work is blocked on both. Also: the token scale
   already defines `--radius-sm/md/lg/xl/full` = 4/8/12/16/9999
   (`main.css:248-254`), yet the site hardcodes `100px` (6×), `6px` (5×),
   `3px` (3×), `10px` (2×), `15px` (1×) — off-scale values that a token audit
   should sweep.

2. **sx-pricing — `pricing-page.css` (50 KB) owns 4 of my primitives.**
   `.cf-cta-btn` (:1825), `.billing-toggle-btn` (:1888),
   `.comparison-plan-toggle-btn` (:2140), `.cf-pricing-card` (15px radius,
   40px padding), `.enterprise-cta` (:737), `.roi-cta-banner` (:1334). The
   button/segmented/card collapse cannot complete without those. `.cf-badge`
   ("Most popular" / "Best Value") is also a pill I would fold into `.chip`.

3. **sx-chrome — nav and sidebar carry 8 of the 40 button roots.**
   `.nav-cta-btn`, `.nav-cta-btn--secondary`, `.sidebar-account-cta`,
   `.sidebar-account-cta--secondary`, `.login-btn`, `.search-btn`,
   `.theme-toggle-btn`, `.hamburger-btn`, `.sidebar-close-btn`,
   `.language-trigger`. Note `main.css:1031-1035` uses
   `padding: calc(var(--space-2) - 1.5px)` to compensate for a 1.5px border —
   a symptom the `inset box-shadow` border in P1 removes. Also
   `BaseLayout.astro:240-242` (the three `media="print"` modal stylesheets)
   is yours to change when P4 deletes them.

4. **sx-hero — the homepage eyebrow is `.sp-hero-badge`**
   (`src/styles/solution-pages.css:121`), one of 5 eyebrow implementations. If
   the hero is rebuilt, it should consume the shared `.eyebrow` from P5 rather
   than a sixth.

5. **Not in anyone's stated file list.** `PartnerApplicationForm.tsx` (441
   lines, the largest form) and `src/pages/[lang]/partners.astro` (which
   contains `.pt-btn-primary`, `.pt-btn-secondary`, `.pt-card`,
   `.pt-tier-card`, `.pt-eyebrow`, `.partner-form-*` inline). Likewise
   `SearchModal.tsx` + `public/styles/search-modal.css`, which P4 needs.
   Someone must own these; today nobody does.

6. **Defects found while measuring, for the lead to route.** All are recorded
   here rather than fixed, per the "DO NOT MODIFY ANYTHING" rule in
   `00-BRIEF.md`, and all should be fixed during implementation:
   - `aria-hidden-focus` (serious) on `#image-modal`, **on every page** —
     `ImageModal.astro` + `BaseLayout.astro:430`. *Mine.*
   - `link-name` (serious): `a.sp-btn-primary` with no accessible name in
     `.sp-bottom-cta-inner` on `/en/solutions/encryption`.
   - `label` (**critical**): 3 unlabelled `input[type=range]` in
     `SPRoiCalculator.tsx`.
   - `color-contrast` (serious): 23 nodes on `/en/solutions/encryption`,
     47 on `/en/docs`, `.cf-guarantee-text` on `/en`, `.footer-version`.
   - `heading-order` (moderate) on 4 of 6 audited pages; two duplicate `main`
     landmarks on `/en/docs`.
   - `.cta-bolt` is dead and its CI gate cannot fail (§2.9).
   - `lint:css` / `lint:all` are declared and never invoked (§2.9).

---

## 7. Open questions for the operator

1. **How bold should a button be?** Today the nav CTA is **700**, solution
   CTAs are 600, `.btn` is **400**, forms are 500. claude.com is 400 on 52 of
   66 measured buttons — their buttons are noticeably lighter than ours. My
   default would be **500**, which is a visible change to every CTA on the
   site. Confirm before P1.

2. **Pill or 8px?** Our nav, `.btn` and the toggles are fully round
   (`9999px`); the solution pages, partners and forms are `8px`. claude.com is
   `8px` everywhere. One must go. My default is **8px**, which changes the
   most recognisable element on the site (the green "Get Started" pill).

3. **`.btn` is currently large** (`16px 32px`, 18px type, 62px tall). Making it
   the single button means either every other button grows, or `.btn` shrinks
   to ~`12px 24px` / 16px. My default is to shrink it. Confirm.

4. **Does the `RegionPickerModal` still need to exist?** It is a sixth overlay
   carrying its own stylesheet for a one-time region choice. Folding it into
   P4 is straightforward; deleting the feature would be simpler still, but
   that is a product call, not a styling one.

---

## Appendix — reproducing these numbers

```bash
export AGENT_BROWSER_SESSION=sx-primitives
S=/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad
agent-browser set viewport 1440 900
agent-browser open http://localhost:4321/en
agent-browser eval "$(cat $S/js/btn.js)"     # buttons
agent-browser eval "$(cat $S/js/card.js)"    # card shells
agent-browser eval "$(cat $S/js/badge.js)"   # badges / pills / chips
agent-browser eval "$(cat $S/js/form.js)"    # fields + labels
agent-browser eval "$(cat $S/js/impl.js)"    # distinct class roots
agent-browser a11y http://localhost:4321/en --json
```

Per-page dumps: `$S/dump/{btn,card,badge,form,impl}_*.json`
(`REF_*` = claude.com / anthropic.com).
Screenshots: `$S/shots/sx-primitives/` — `strip-buttons-global.png`,
`strip-card-shells.png`, `strip-solution-primitives.png`,
`home-cards-slice.png`, `home-cards-pricing.png`, `home-mobile-hero.png`.
The specimen-strip injectors are `$S/js/strip.js` (clones real DOM nodes) and
`$S/js/synth.js` (renders measured tuples as plain boxes); both mutate only the
live page and are undone by a reload.
