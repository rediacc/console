# www — systematic bug hunt

**Author:** `sx-bughunt`. **Date:** 2026-08-17. **Method:** `agent-browser` 0.34.0,
session `sx-bughunt`, against the running dev server at `http://localhost:4321`, with
**every high-severity finding re-confirmed against `https://www.rediacc.com`** so that
nothing here is a dev-server artifact.

**Coverage:** 56 routes × {1440×900, 390×844} × {light, dark}; 7 locales × 5 pages ×
2 viewports; the full purchase funnel from `/en/pricing` to the account portal on
production; every form submitted empty and filled; search, theme toggle, language menu,
mega menu, mobile drawer, region picker, billing toggle, 404.

Findings already recorded in `01-SYNTHESIS.md` are **not** repeated. Where I found a
sharper version of a known finding it is marked *(refines a known finding)*.

---

## Summary

| # | Severity | Finding | Blast radius | Live on prod? |
|---|---|---|---|---|
| H1 | **High** | Arabic contact + partner pages have ~10,000 px of blank horizontal scroll | 2 pages × ar | untested on prod, cause is in committed CSS |
| H2 | **High** | Homepage and pricing page scroll horizontally at every viewport | `/`, `/pricing` × 13 locales | **yes, verified** |
| H3 | **High** | React hydration failure on `/install`; whole component discarded and re-rendered | `/install` × 13 locales | **yes, verified** |
| H4 | **High** | Empty contact-form submit answers "Something went wrong" instead of naming the empty field | contact page + sitewide modal | yes (code path) |
| H5 | **High** | Empty newsletter / lead-magnet submit does nothing at all, silently | footer sitewide + 7 resource pages | yes (code path) |
| M1 | Medium | 25 pages render solid-white cards in dark theme | 21 solutions + 4 personas | yes |
| M2 | Medium | CLI cheat-sheet docs page has zero dark-mode support | `/docs/rdc-cheat-sheet` | yes |
| M3 | Medium | Duplicate `<h1>` on all 36 linked docs pages | 36 × 13 locales | yes |
| M4 | Medium | Footer "Overview" link is dead on every page | all 56 routes | **yes, verified** |
| M5 | Medium | Pricing tooltips: 16×16 px target, hover-only | `/pricing`, `/` | yes |
| M6 | Medium | Language switcher has no `href`s | all routes | yes |
| M7 | Medium | Post-payment page has the shortest title and meta description on the site | `/checkout/success` | yes |
| M8 | Medium | 404 page drops the visitor's locale | all 404s | yes |
| M9 | Medium | Public pricing page advertises the **edge** (pre-production) environment | `/pricing` | **yes, verified** |
| M10 | Medium | `#image-modal` puts 6 invisible buttons in the tab order *(refines a known finding)* | all 56 routes | yes |
| M11 | Medium | Turnstile widget ignores the site's theme toggle | 2 forms | yes |
| L1 | Low | 20 of 21 solution pages render a dead `href="#"` card for themselves | 20 pages | yes |
| L2 | Low | Two structurally-empty `<section>`s on every solution page | 21 pages | yes |
| L3 | Low | Footer "About Us" points at `/contact`, not `/company` | all routes | yes |
| L4 | Low | Two different destinations for "Start free trial" on one page | `/pricing` | yes |
| L5 | Low | Newsletter opens a new tab before its request resolves | footer sitewide | yes |
| L6 | Low | Honeypot present on 3 forms, absent on 3 others | 3 forms | yes |
| L7 | Low | A docs-only CLI-reference modal + empty `<iframe>` ships on all 56 routes | all routes | yes |
| L8 | Low | Region picker forces an irreversible choice before sign-up, unexplained | funnel | yes |

**Count: 5 high, 11 medium, 8 low.**

Two whole *classes* rather than single instances are called out at the end, plus two
instrument defects worth the same treatment `01-SYNTHESIS.md §7` gave the others.

---

## What is clean

Recording this so the next session does not re-derive it:

- **Zero broken routes.** All 56 top-level routes return 200 (`/docs` 301s to
  `/docs/quick-start`). Every one of the **103 unique internal `href`s** harvested across
  those routes resolves; the only non-200s are four intentional locale redirects and
  `/account/` (which has no local portal, and 307s correctly on production).
- **Exactly one JavaScript page error on the entire site** (H3). Measured with a
  cumulative-delta sweep across all 56 routes — see *Instruments* below for why a naive
  per-page read is worthless here.
- **No broken images, no failed asset requests, no request to an unexpected host, no key
  or token in any client payload.** External hosts contacted: `plausible.rediacc.com`,
  `challenges.cloudflare.com`, `static.cloudflareinsights.com`. (227 apparent requests to
  `www.w3.org` are `data:` URIs — a false positive, checked.)
- **Every fetch-backed form has a real error branch.** No form shows success on failure.
  The problems are on the *empty-input* path (H4, H5), not the failure path.
- **The mobile drawer is correct**: `aria-expanded`, `aria-controls`, focus moves to the
  close button, body scroll locks, Escape closes and restores scroll, and the closed
  drawer's 16 links carry `tabindex="-1"` so they are **not** in the tab order. I flagged
  this as a suspected defect and it survived the check — it is not one.
- **The mega menu opens correctly from the keyboard** (`Enter` on the trigger flips
  `aria-expanded` false→true and shows the panel). The known "clicking Solutions closes
  it" defect is **mouse-only** — worth knowing before anyone rewrites the whole component.
- **No flash of wrong theme.** `BaseLayout.astro:152-163` is a blocking inline script
  ahead of the render-blocking stylesheet at `:237`.
- **The production funnel completes.** `/en/pricing` → "Start 14-day free trial" → region
  picker → `https://eu.rediacc.com/account/login` with a working sign-in form, and the
  chosen plan **is** carried (`?checkout=PROFESSIONAL&period=monthly`). See the caveat in
  H2's neighbourhood under *Funnel*.

---

# High severity

## H1 — Arabic contact and partner pages have ~10,000 px of blank horizontal scroll

**URLs:** `http://localhost:4321/ar/contact`, `http://localhost:4321/ar/partners`
**Viewports:** both 1440×900 and 390×844.
**Screenshot:** `/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-bughunt/rtl/ar-contact-scroll-neg.png`

**Steps:** open `/ar/contact`, scroll left (in RTL the scrollable direction is negative).
**Expected:** no horizontal scroll; the contact form fills the viewport.
**Actual:** the document is 11,263 px wide against a 1,440 px viewport. Scrolling to
`scrollX = -9823` leaves a completely blank white page with only the sticky header
visible — the form is 9,823 px away.

Measured, reproduced **3 runs out of 3**:

| Route | `scrollWidth − clientWidth` |
|---|---:|
| `/ar/contact` | **9,823** |
| `/ar/partners` | **9,984** |
| `/en/contact` (control) | −15 |

**Cause.** The spam honeypot is hidden with `left: -9999px`:

- `public/styles/contact-modal.css:286-292` — `.contact-honeypot { position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden }`
- `src/pages/[lang]/partners.astro:517-523` — `.partner-form-honeypot`, byte-identical rule.

`left` is a *physical* property. In LTR, overflow past the left edge is the **leading**
edge and browsers do not make it scrollable. Under `dir="rtl"` the leading edge is the
right, so the same −9999 px becomes **trailing** overflow and *is* scrollable. Measured
honeypot position on `/ar/partners`: `x = −9999`, `right = −9998`.

**Blast radius.** Arabic is the only RTL locale, and only these two pages mount an inline
form (the sitewide `ContactModal` only renders its honeypot once opened — I swept all 56
Arabic routes and no other page exceeds 13 px). But these are the **two lead-capture
pages**: an Arabic visitor who reaches "Contact" or "Become a Partner" gets a page that
scrolls into a void.

**Sibling check (the class, not the instance):** `left:-9999px` is the only off-screen
hiding idiom in the tree with this failure mode; `sidebar-shared.css:223,277` and the
`9999px` occurrences in `newsletter.css:352` / `main.css:254,1014,2409` are
`max-height`/`border-radius` and are unaffected.

---

## H2 — The homepage and the pricing page scroll horizontally, on production, at every viewport

**URLs:** `https://www.rediacc.com/en` and `https://www.rediacc.com/en/pricing`
(reproduced identically on localhost).
**Screenshot:** `.../shots/sx-bughunt/desktop-pricing-overflow.png`

**Steps:** load either page at 1440×900 and scroll right.
**Expected:** no horizontal scroll at a standard desktop width.
**Actual:** `window.scrollX` reaches 133. Measured on production:

```
https://www.rediacc.com/en          scrollWidth 1573  clientWidth 1440  → 133 px
https://www.rediacc.com/en/pricing  scrollWidth 1573  clientWidth 1440  → 133 px
```

At 390×844 the same pages overflow by **244 px** and **228 px**. Other locales are worse
— measured at 1440 desktop: `ja` 287, `de` 252, `ru` 244/254, `ko` 90, `tr` 82; at 390
mobile: `ja` 398, `de` 362, `ru` 354, `ko` 200, `tr` 193.

**Cause, traced from the document down to the leaf.** The chain is
`documentElement (1573/1440) → main → .sp-page → .cf-pricing-section →
.cf-pricing-container (1561/1400) → .cf-pricing-grid (1561/1400) →
.cf-pricing-card (616/452) → ul.cf-features (576/372) → span.cf-feature-info (575/14)`.

The leaf is the pricing-card info tooltip:

```
src/styles/pricing-page.css:1804-1820
.cf-feature-info::after {
  content: attr(data-tooltip);
  position: absolute;
  white-space: nowrap;      /* ← up to 575 px of unwrappable text */
  opacity: 0;               /* ← hidden by opacity only, so it stays in layout */
  pointer-events: none;
}
```

`opacity: 0` hides it visually but leaves it in the layout and therefore in every
ancestor's scroll extent. Longer tooltip translations are exactly why `ja`/`de`/`ru`
overflow more than `en`.

**Why this is high and not cosmetic:** it is the homepage and the page you buy from, it
is on production, it affects all 13 locales, and it is worse on phones than on desktop.

---

## H3 — React hydration failure on `/install`, on production

**URL:** `https://www.rediacc.com/en/install`
**Steps:** load the page with the console open.
**Expected:** no console error; the platform tab that the server rendered stays selected.
**Actual:** React throws *"Hydration failed because the server rendered HTML didn't match
the client. As a result this tree will be regenerated on the client"* and discards the
entire `<InstallMethods>` subtree.

Production SSR, read with `curl`:

```
tab=All Methods    aria-selected=true   activeClass=True
tab=Linux          aria-selected=false  activeClass=False
tab=macOS          aria-selected=false  activeClass=False
tab=Windows        aria-selected=false  activeClass=False
```

After hydration the browser reports `Linux` selected. React's own diff also drops a
`<div className="code-block">` that the server had rendered.

**Cause.** `src/components/InstallMethods.tsx:134-145`:

```ts
const [filter, setFilter] = useState<FilterTab>(() => {
  if (typeof window === 'undefined') return 'all';
  ...
  return detectPlatform();
});
```

This is the first pattern React's own error message lists ("A server/client branch
`if (typeof window !== 'undefined')`"). The server always commits to `'all'`; the client
always commits to the detected platform.

**Note for the record:** `InstallMethods` is imported only by
`src/pages/[lang]/install.astro:59`. Errors reported on other routes during my first sweep
were an artifact of the broken `errors --clear` (see *Instruments*); the corrected
delta sweep attributes this error to `/install` alone, and it is the **only** JavaScript
page error on all 56 routes.

---

## H4 — Submitting the contact form empty answers "Something went wrong. Please try again."

**URL:** `http://localhost:4321/en/contact`
**Screenshot:** `.../shots/sx-bughunt/interact/contact-empty-submit.png`

**Steps:** load the page, click **Send Message** without typing anything.
**Expected:** the browser or the app names the empty field ("Please fill in your name").
**Actual:** the form fires a network request and renders
`Something went wrong. Please try again.` — an error that reads as a *system fault* when
the fault is the user's blank form.

The form carries `noValidate` (`src/components/ContactForm.tsx:120`, and
`ContactModal.tsx:232` for the sitewide modal), which switches off native required-field
validation, and neither component adds a client-side replacement — so a completely empty
form is POSTed and the generic catch-all message is shown.

Contrast with `PartnerApplicationForm.tsx:147-151`, which *does* implement the check and
returns a specific message. The pattern exists in the codebase; the two contact surfaces
do not use it. (This is the same "the shared thing exists and the code goes around it"
shape as `01-SYNTHESIS.md §1`.)

*Caveat, stated plainly:* on localhost `/account/api/v1/contact/submit` 404s, so every
submit fails. What the empty submit proves is that **a request is issued at all** — i.e.
there is no client-side gate. What the production server replies to an empty body is not
something I tested, because doing so means sending junk to a live contact endpoint.

---

## H5 — Submitting the newsletter or lead-magnet form empty does nothing, silently

**URL:** `http://localhost:4321/en/newsletter` (and the footer widget on all 56 routes)

**Steps:** click **Subscribe** with the email field empty.
**Expected:** an error, or the browser's native "Please fill out this field".
**Actual:** nothing. No message, no focus move, no request. Measured form text before and
after the click is byte-identical.

Cause: `src/components/NewsletterSignup.tsx:131` sets `noValidate`, and `:45` is
`if (!email) return;` — a bare early return with no user-facing branch. Identical
construction at `src/components/LeadMagnetModal.tsx:133` (the gated-PDF modal used on
the seven `/resources/*` briefs and the solution pages).

A dead button is worse than an error message: the visitor concludes the site is broken
and leaves. This is the *first* interaction on the site's main email-capture surface.

---

# Medium severity

## M1 — 25 pages render solid-white cards in dark theme

**URL example:** `http://localhost:4321/en/solutions/instant-recovery` with
`data-theme="dark"`.
**Screenshot:** `.../shots/sx-bughunt/dark/solution-timeline-old-step.png` — five bright
white cards floating on a `rgb(26,26,27)` page.

Measured computed styles on the dark page:

| Selector | `background` | `color` | file:line |
|---|---|---|---|
| `.sp-timeline-old-step` | `rgb(255,255,255)` | `rgb(138,106,106)` | `src/styles/solution-pages.css:583-588` |
| `.sp-timeline-old-step:last-child` | `#fdf0f0` | `#a04040` | `:593-598` |
| `.sp-calc-result-col.without` | `#fdf8f6` | — | `:780-783` |
| `.sp-calc-result-col.with` | `#f4faf2` | — | `:784-786` |
| `.sp-tech-detail-col-header.traditional` | `rgb(250,250,250)` | `rgb(107,107,112)` | `solution-pages.css` |

The sibling `.sp-timeline-new-step` (`:632-641`) correctly uses `var(--sp-brand-*)` and
does adapt — which is what makes this an oversight rather than a design choice.

I ran an automated "outermost opaque box with luminance > 0.6 on a dark page" sweep across
the routes; these are the only true positives. Two things it flagged that I checked and
**cleared**: `.pt-btn-primary` on `/partners` (white button, but it sits on an olive
`.pt-final-cta` section — correct in both themes) and `.skip-nav-link` (light-on-dark by
design, off-screen until focused). The `.cf-badge` pill and the `rgba(...)` overlays are
also false positives.

Also verified as a genuine token hole, distinct from the known 12-accent finding:
`--sp-text-muted-light: #6b6b70` is declared once (`solution-pages.css:24`), consumed at
24 call sites, and is **not** among the seven `--sp-*` tokens redefined in the dark block
at `:2105-2113`. On `#0f0f10` it computes to ≈3.6:1 — below AA for body text.

## M2 — The CLI cheat-sheet docs page has no dark mode at all

`src/styles/cheatsheet.css` declares its own component tokens at `:10-34`
(`--cs-color-bg: #ffffff`, `--cs-color-text: #1a1a2e`, plus pastel category colours) and
contains **zero** `data-theme` selectors — `grep -c "data-theme" src/styles/cheatsheet.css`
returns `0`. Toggling to dark does nothing to this section. Rendered by
`CheatSheetGrid.astro` on `/docs/rdc-cheat-sheet`.

## M3 — Duplicate `<h1>` on all 36 linked docs pages

**URL:** `http://localhost:4321/en/docs/quick-start`

Measured: two visible `<h1>` elements with identical text —
`h1.article-title` inside `.article-header-main` (the layout's own title) and a bare
`<h1>` inside `.article-content` (the markdown file's own `# Quick Start`).

Confirmed by counting `<h1` in the served HTML of all 36 docs routes reachable from the
sidebar: **every one returns 2.** (There are 61 English docs markdown files in total, so
the real count is likely higher.) An SEO and screen-reader-outline defect, and it is
mechanical — one of the two is always redundant.

## M4 — The footer "Overview" link is dead on every page

`src/components/Footer.tsx:109` renders `href={`/${currentLang}#problem`}`.

There is **no `id="problem"` on the homepage**. Verified three ways: rendered HTML on
localhost has no match; `curl https://www.rediacc.com/en | grep -c 'id="problem"'`
returns `0`; and in the browser `document.getElementById('problem')` is `null` with
`window.scrollY` staying at 0 after navigating to `/en#problem`.

The footer is on all 56 routes, so this is 56 dead links.

*A near-miss worth recording so nobody re-files it:* `SPHero.astro:48` uses the same
`'#problem'` as its secondary-CTA fallback, and **all 21 solution pages** ship
`href="#problem"` above the fold. I was about to file that as a second instance — but
solution pages *do* have `id="problem"` (the `SPProblem` section). Those links work. Only
the homepage lacks the target.

## M5 — Pricing feature tooltips are 16×16 px and hover-only

`src/components/CfPricingCard.astro:74-80` renders a `<span class="cf-feature-info">`
carrying the tooltip text. Measured on `/en/pricing` at 390×844: the target's bounding box
is **16×16 px** — below the WCAG 2.2 24×24 minimum and far below the 44×44 recommendation.
There are 5 of them per card, 3 cards.

The tooltip is revealed by `:hover` and `:focus-visible` only
(`src/styles/pricing-page.css:1822-1823`). The span does carry `tabindex="0"`, so keyboard
users can reach it — but on a click I measured `element.matches(':focus-visible')` →
**`false`**, which means a pointer/touch focus does not satisfy the selector. **Inference,
labelled as such:** on a real touch device, where `:hover` does not exist and focus comes
from a tap, these tooltips are unreachable. I could not prove this on a real device;
Playwright's synthetic click also sets hover, which is why the tooltip *did* appear in my
measurement (`::after` opacity `1`) even though `:focus-visible` was false.

The same rule is the cause of H2.

## M6 — The language switcher has no links

`.language-menu` (`role="menu"`) contains **13 `<button role="menuitem">` elements and
zero `<a href>`** — measured directly. Consequences: the 12 alternate locales cannot be
middle-clicked, opened in a new tab, copied as a link, or reached at all without
JavaScript. (The `<link rel="alternate" hreflang>` tags are present — 14 per page — so
crawlers are fine; this is a user-affordance defect, not an SEO one.)

## M7 — The post-payment page has the site's shortest title and description

`/en/checkout/success`: `<title>` is **22 characters** ("Subscription Confirmed") and the
meta description is **36 characters**. Every other route on the site falls inside 30-60 /
50-160 — the only other outliers are the two `/docs` routes at 21 characters.

This is the page a paying customer lands on. Worth stating that
`01-SYNTHESIS.md §5c` records `meta.title` 30-60 and `meta.description` 50-160 as
**ERROR-level** SEO rules for locale-sourced strings in all 13 locales; these two pages
sit outside those bounds, which suggests their meta does not come from the locale JSON and
is therefore ungated. I did not run the gate to confirm which.

## M8 — The 404 page drops the visitor's locale

`/en/anything-missing` renders links to `/`, `/solutions`, and `/contact` — **no locale
segment**. Those three are 301 redirects (to `/en/...`), so a German or Japanese visitor
who mistypes a URL is silently moved to the English site. `document.documentElement.lang`
is hardcoded `en` on the 404 page regardless of the requested locale.

## M9 — The public pricing page advertises the pre-production environment

`/en/pricing` carries `<a class="btn btn-secondary" href="https://edge.rediacc.com/en/pricing">Explore the edge channel →</a>`.
Confirmed present on **production**:
`curl -s https://www.rediacc.com/en/pricing | grep -o 'https://edge\.rediacc\.com[^"]*'`
returns `https://edge.rediacc.com/en/pricing`.

Per `CLAUDE.md`, `edge.rediacc.com` is "auto-deployed on merge to main, D1 cloned from
production daily" — an internal continuous-deployment target with a nightly-cloned
database. Sending prospective customers there from the page they buy on is a positioning
and data-hygiene question, not a rendering bug, which is why it is medium and not high.
Flagging, not judging: the *channel* concept is public (stable vs edge CLI releases), so
this may be deliberate.

## M10 — `#image-modal` puts six invisible buttons into the tab order of every page
*(refines the known `aria-hidden` finding)*

The known finding is that `#image-modal` is `aria-hidden` while holding focusable buttons.
The measured consequence is sharper than that: on `/en` at 1440×900,

```
modalAriaHidden: "true"   modalFocusables: 6   modalReachable: 6   inert: false
```

All six (`close`, `prev`, `next`, `zoom-in`, `zoom-out`, `zoom-reset`) are reachable by
`Tab`, on all 56 routes. A keyboard user hits six controls they cannot see, on every page.

Two things I checked and cleared while here, so they do not get re-investigated:
the modal is `opacity:0; pointer-events:none` across the full 1425×900 viewport and does
**not** intercept clicks (`elementFromPoint` returns the page content beneath); and the
`<img class="modal-image" src="">` it carries is an empty-src placeholder that is never
painted.

## M11 — The Turnstile widget ignores the site's theme toggle

`ContactModal.tsx` and `LeadMagnetModal.tsx:284-289` mount `<Turnstile>` without a `theme`
option. The library default is `'auto'`, which follows `prefers-color-scheme` — i.e. the
operating system, not `data-theme`. A visitor whose OS is light and who clicks the site's
dark toggle gets a light CAPTCHA box inside a dark modal, and vice versa.

---

# Low severity

**L1 — 20 of 21 solution pages render a dead card for themselves.**
`SPExploreSolutions.astro:29-30` sets `href = isCurrent ? '#' : ...`. Each page's
`explore.solutions` array in `en.json` contains an entry for its own slug, so the card for
the page you are already on renders as `<a href="#" class="sp-explore-card current">` — a
focusable link that jumps to the top. `data-sovereignty` is the single exception (its
array omits itself). The fix is in the content, not the component.

**L2 — Two structurally-empty `<section>`s on every solution page.**
`SPSolutionVideo.astro:22` is a `<section>` whose only children are `<video><source>` —
no text node can ever exist in it. `SPDownloadGated.astro:27` wraps a `LeadMagnetButton`
that returns `null` until the visitor scrolls past a 30vh sentinel, while the wrapper
keeps `padding: 56px 20px` (`solution-pages.css:2546-2549`) — 112 px of empty space around
nothing on first paint, ×21 pages.

**L3 — Footer "About Us" points at `/contact`,** while a separate "Company" entry points
at `/company`.

**L4 — Two destinations for the same words on one page.** On `/en/pricing`, the card CTA
"Start 14-day free trial" is a `<button>` that opens the region picker and proceeds to
checkout; the section CTA "Start free trial" is an `<a href="/en/install">` to the
download page. Same promise, two funnels.

**L5 — The newsletter opens a new tab before its request resolves.**
`NewsletterSignup.tsx:54-56` calls `window.open(openOnSuccessUrl)` ahead of the `fetch`,
so a failed subscribe still leaves the visitor with an unexpected new tab. Used by
`NewsletterReturnPopup`.

**L6 — Honeypot coverage is inconsistent.** Present on `ContactModal`, `ContactForm`,
`PartnerApplicationForm`; **absent** on `NewsletterSignup`, `LeadMagnetModal`, and the ROI
email gate — the three that are easiest to script against.

**L7 — A docs-only modal ships on all 56 routes.** `BaseLayout.astro:429` mounts
`CliReferenceModal`, which renders a full dialog plus an empty `<iframe>` on every
marketing, legal, and solution page. It is `hidden`, so the `href="#"` "Open in new tab"
link inside it is *not* in the tab order — I checked, and it is not a defect, just weight.

**L8 — The region picker forces an irreversible choice before sign-up.** The modal says
"This can't be changed after sign-up" but does not say what the consequence is, and the
choice is demanded before the visitor has an account. Copy decision, recorded because it
sits directly on the money path.

---

# Two classes, not instances

**Class A — hidden-by-opacity and hidden-by-offset elements that stay in layout.**
H1 (`left:-9999px` under RTL) and H2 (`opacity:0` + `white-space:nowrap`) are the same
mistake in two costumes: an element is *made invisible* without being *removed from
layout*, and the layout then leaks into the document's scroll extent. Both produce a
horizontal scrollbar on a page nobody would suspect. Before this is called fixed, grep for
every `opacity: 0` on a `::before`/`::after` and every negative-offset hide in
`public/styles/` and `src/styles/`, and check each against `dir=rtl`. `visibility:hidden`
or `clip-path` would close both.

**Class B — validation switched off with no replacement.** Five of six forms set
`noValidate` (`ContactModal`, `ContactForm`, `PartnerApplicationForm`, `NewsletterSignup`,
`LeadMagnetModal`). Exactly one of them — `PartnerApplicationForm.tsx:147-156` — then
implements the check it turned off. Two do nothing (H4) and two return silently (H5). The
sixth, the ROI gate at `SPRoiCalculator.tsx:269`, is the only form that *keeps* native
validation, and it is the only one where an empty submit behaves correctly. The pattern to
adopt already exists in the repo.

---

# Instruments that lied

In the spirit of `01-SYNTHESIS.md §7`, two more for the list.

**`agent-browser errors --clear` does not clear.** Proven: `errors --json` returns 3
entries; `errors --clear` runs and exits 0; `errors --json` returns the same 3. `console
--clear` *does* work (verified: `messages: []` afterwards). My first sweep reported page
errors on 47 of 56 routes; every one of them was the same `/install` error, retained and
re-reported. The correct method is a **cumulative delta** — read the length before and
after each navigation and attribute only the new tail. Re-run with that method: 1 error,
1 route.

**A naive `aria-hidden` + focusable scan over-reports by a factor of two.** It flagged
`#navigation-sidebar` on all 56 routes alongside `#image-modal`. The sidebar's 16 links
carry `tabindex="-1"` when closed and are genuinely out of the tab order; the modal's six
buttons are genuinely in it. The scan must filter on `element.tabIndex >= 0`, not merely
on the selector matching.

A third worth noting because it wasted a measurement pass: a floating dark widget appears
at the bottom of nearly every screenshot in this run. It is `<astro-dev-toolbar>`, a
dev-server artifact with `z-index: 999999`. It is not on production and it is not a bug —
but it *does* sit on top of the page and will absorb clicks and hit-tests in any
dev-server measurement.

---

# Funnel, end to end

Walked on **production**, 1440×900:

1. `https://www.rediacc.com/en/pricing` — 200, renders. *(horizontally scrollable, H2.)*
2. Click **Start 14-day free trial** on the Professional card → region picker modal opens,
   three regions, no dead ends.
3. Click **Europe** → `https://eu.rediacc.com/account/?checkout=PROFESSIONAL&period=monthly&returnUrl=...`
   The chosen plan and billing period **are** carried. From localhost the same click goes
   to `edge-eu.rediacc.com`, which is correct host-derived behaviour.
4. That URL then client-side redirects to `https://eu.rediacc.com/account/login`, which
   renders a working sign-in form ("Sign in or create an account").

**One caveat, stated as an observation rather than a finding:** the
`?checkout=PROFESSIONAL&period=monthly` query string is **gone from the URL** after step 4.
The server returns 200 for the parameterised URL and does not redirect, so the drop is the
portal's own client-side router. Whether the portal retains the selection in memory (and
therefore lands the user on Professional checkout after sign-in) could not be verified
without creating a real account, and the code lives in `private/account/web`, outside
`packages/www`. If it does not retain it, the visitor picks a plan and then has to pick it
again — worth one check by whoever owns that package.

Dead ends found on the way in: none. The paths that do fail are the ones that never reach
the portal — H4 and H5 kill the two forms a visitor uses when they are not ready to buy.
