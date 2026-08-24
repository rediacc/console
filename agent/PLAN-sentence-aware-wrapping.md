# PLAN: sentence-aware wrapping for packages/www

Status: draft
Author: plan agent (session a68f3ab4)
Date: 2026-08-23
Intended path: `/home/muhammed/console/agent/PLAN-sentence-aware-wrapping.md`
Actual path: this file. Plan mode restricted this session to a single writable file,
so the deliverable could not be written to `agent/`. Copy it across before implementing.

Every number below was measured live against `http://localhost:4321` with
`agent-browser` (headless Chromium 145) in session `plan-typo`. Nothing was guessed
and nothing in the repo was modified.

---

## 1. The rule, stated precisely

The operator's words: "a line must not both end one sentence and begin another".

Applied literally that rule is unsatisfiable, and the measurement proves it.
`.sp-slice-winner-description` is five sentences rendered on two lines at 1440x900.
Any line that carries two whole sentences "ends one and begins another", so the
literal rule forces one line per sentence and turns that paragraph from two lines
into five. That is not what the operator is complaining about.

What the operator is actually pointing at is a sentence that is **broken across a
line boundary while sharing a line with its neighbour**:

```
Most tools copy one          <- line 1 ends mid-sentence
piece. We copy all of it.    <- line 2 carries the tail of A and the whole of B
```

So the enforced rule is:

> **A sentence that occupies more than one line must not share either of those lines
> with an adjacent sentence.**

Two whole sentences sitting on one line is fine and stays fine. A long sentence
wrapping onto several lines of its own is fine and stays fine. The defect is
precisely the mixed case above.

This is the rule the detector implements and the rule the gate enforces.
Everything in this plan depends on that distinction, so do not "simplify" the rule
back to the literal wording later.

---

## 2. Mechanism decision

**Chosen: (a) wrap each sentence in `<span class="sentence">` with
`display: inline-block`, produced at build time.**

An inline-block is an atomic line-breaking unit: it starts on a new line when it
does not fit on the current one, which is exactly the guarantee the rule needs.

### 2.1 The browser evidence that decided it

Same page, same viewport (1440x900), same detector, three mechanisms:

| Mechanism | defects on `/en` |
|---|---|
| today (`h*{text-wrap:balance}`, `p{text-wrap:pretty}`, live at `public/styles/main.css:582-594`) | **11** |
| `text-wrap: pretty !important` on `p,li,h1..h6` | **11** (no change at all) |
| `text-wrap: balance !important` on `p,li,h1..h6` | **8** |
| sentence spans, `display:inline-block` | **0** (see 2.2 for the single residual) |

`pretty` moves nothing because it only rescues a single-word last line. `balance`
recovers 3 of 11 by accident, not by respecting sentences, and browsers cap it at
around six lines. Neither is a mechanism; both are heuristics that happen to help
sometimes. That kills candidates (b) and (c). Candidate (c), binding the last two
words with a non-breaking space, addresses orphans and has no bearing on sentence
boundaries.

### 2.2 The rendered lines, before and after

Extracted by reconstructing visual lines from per-character `Range` rects, so this
is what the browser actually painted, not a model of it.

```
#not-a-slice h2            BEFORE  | Most tools copy one
                                   | piece. We copy all of it.
                           AFTER   | Most tools copy one piece.
                                   | We copy all of it.

.sp-home-hero-sub          BEFORE  | Rediacc is software you install on your own servers. It copies your
                                   | whole live system in seconds: apps, databases, and settings.
                           AFTER   | Rediacc is software you install on your own servers.
                                   | It copies your whole live system in seconds: apps, databases,
                                   | and settings.

.difference-col--before li BEFORE  | Your team waits days for a test copy. And it still doesn't
                                   | match.
                           AFTER   | Your team waits days for a test copy.
                                   | And it still doesn't match.

.closing-cta-subtitle      BEFORE  | Most teams test in fake staging, then pray. Copy your live system in
                                   | seconds. Run the risky change on real data. Production never feels it.
                           AFTER   | Most teams test in fake staging, then pray.
                                   | Copy your live system in seconds.
                                   | Run the risky change on real data. Production never feels it.
```

The last AFTER line is the residual class from section 1: two whole sentences share
line 3, neither is broken, and that is correct output.

The one defect still reported after the probe ran is
`.newsletter-footer-desc`, which the probe deliberately excluded (it lives inside
the `<footer>` React island). It is a limitation of the probe, not of the mechanism.
See 3.3.

### 2.3 Every failure mode, measured

| Question | Answer, measured |
|---|---|
| One sentence wider than the container: does it wrap internally and reintroduce the defect? | No. `inline-block` is shrink-to-fit capped at the container width, so it wraps internally and its neighbours still start on fresh lines. `.sp-home-hero-sub` sentence 2 measured 600px in a 600px container, wrapped internally over two lines, and the block reported **0** defects. The rule tolerates this by construction: an internally wrapped sentence sharing no line with a neighbour is not a defect. |
| Horizontal overflow at mobile widths? | None. `scrollWidth/clientWidth` was `375/390` at 390x844 and `753/768` at 768x1024, before and after, on `/en`, `/ar` and `/ja`. |
| Vertical cost | Worst case +1.2%. `/en` at 390x844: page height 9510 -> 9625. At 1440x900: 5272 -> 5320. At 768x1024 the height was **identical** for `/ar` and `/ja`. |
| Interaction with `text-wrap: balance` on headings | Harmless. `#not-a-slice h2` kept its 86px height and 2 lines and lost the defect. Balancing now happens inside each sentence rather than across the block, which is the desired behaviour, not a regression. |
| Interaction with `text-wrap: pretty` on `p` | Harmless. `pretty` still applies per inline-block. |
| Text selection and copy/paste | `element.textContent` is byte-identical to the original after wrapping (asserted on all six probe targets). A real space text node is emitted between spans, so no words are glued. Chromium may insert a newline when copying across inline-block boundaries; this is a known browser behaviour and is listed as a residual risk in section 7. |
| Screen readers | The accessibility tree text is unchanged; `<span>` carries no role and `display` does not alter the text alternative. Some readers pause at inline-block boundaries, which are sentence boundaries here, so the pause is correct. |
| `Intl.Segmenter` availability | Present in Node v22.21.1 (build side, verified) and `typeof Intl.Segmenter === 'function'` in the page (verified). Baseline is Chrome 87 / Safari 14.1 / Firefox 125, all below the site's floor. |
| "e.g." and "v1.2." false positives | `Intl.Segmenter` handles both correctly. `"Recovery takes hours, not a minute. e.g. this is v1.2. Done."` segments as `["Recovery takes hours, not a minute. e.g. this is v1.2. ", "Done."]`. It does not split at "e.g." and does not split at "v1.2.". **Do not hand-roll a regex**; a regex gets both of these wrong. |
| CJK (no spaces, `。` terminator) | Works. `/ja` 12 -> 1, `/zh` 4 -> 1 at 1440x900; `/ja` 20 -> 1 at 390x844. Segmentation examples verified: `本番環境をクローン。` and `集群远不止 YAML。` are segmented as whole sentences. |
| RTL (Arabic, `؟` terminator) | Works. `/ar` 8 -> 1 at 1440x900, 12 -> 1 at 390x844, 5 -> 1 at 768x1024. `inline-block` is direction-agnostic; no `direction` property is involved, unlike the `PricingTrustSection` alternation bug recorded in `EXPLORE-home.md` section B. `Intl.Segmenter('ar')` splits on `؟` correctly. |
| `check:ci-dead-css` | Satisfied, with a caveat. Its source glob is `packages/www/src/**/*.{astro,tsx,ts,jsx,js,md,mdx}` (`scripts/check-dead-css.ts:124`). **`.mjs` is not in that list**, so write the rehype plugin as `.ts` (matching `remark-resolve-translations.ts`), not `.mjs` (unlike `rehype-stable-heading-ids.mjs`). With `Sentences.astro` and `Sentences.tsx` both emitting the class it is covered either way, but do not rely on that. |
| `check:ci-css-dom-refs` | Satisfied: the class is rendered and has a rule. |
| `-webkit-line-clamp` | One consumer, `src/styles/docs-browse.css:289-290`. `line-clamp` requires `display: -webkit-box` and inline-block children inside a `-webkit-box` are historically fragile. **Verify this one selector during implementation**; my forced-clamp probe was inconclusive because the element on `/en/docs` is not the clamped one. |
| `text-align: justify` | Not used anywhere on the site (measured `center` / `start` on all probe targets). No interaction. |

---

## 3. Where the split happens: build time, three renderers, one helper

`t()` returns a `string` and 55 `.astro` files interpolate it as text. It cannot be
made to return markup without turning every call site into `set:html`, which is both
an escaping hazard and a type break. So the split does not go in the translator.

There are 818 multi-sentence English catalog leaves out of 6,230 (13.1%), reached
from 80 call sites across 34 source files. Hand-wrapping 818 values is not on the
table; hand-wrapping 80 call sites is, and markdown prose needs no call-site work
at all.

### 3.1 Files to create

| File | Contents |
|---|---|
| `packages/www/src/utils/sentences.ts` | `splitSentences(text: string, lang: Language): string[]`. Wraps `Intl.Segmenter(lang, {granularity:'sentence'})`, drops whitespace-only segments, right-trims each segment. Throws if `Intl.Segmenter` is absent rather than silently returning one segment, so a broken runtime is loud. |
| `packages/www/src/components/Sentences.astro` | `Props: { text: string; lang: Language; class?: string }`. Emits `<span class="sentence">` per segment joined by a literal space. Emits the bare text unchanged when there is exactly one segment, so single-sentence values add no markup. |
| `packages/www/src/components/Sentences.tsx` | The same output for React islands. Takes `lang` as a **prop**, never from `document.documentElement.lang`, so SSR and hydration agree. This is what `check:ci-hydration-clean` is about. |
| `packages/www/src/plugins/rehype-sentence-wrap.ts` | hast pass over markdown prose. Wraps text nodes whose parent is `p`, `li`, `h1..h6`, `td`, `th`, `blockquote`, `figcaption`, `dd`. Skips `code`, `pre`, `a` inside `code`, and any subtree under `svg`. `.ts`, not `.mjs`, per the `check:ci-dead-css` caveat above. |

### 3.2 Files to modify

| File | Change |
|---|---|
| `packages/www/public/styles/main.css` | Add `.sentence { display: inline-block; }` immediately after the existing text-wrap block at `:582-594`, with a comment stating the rule from section 1. That block is the natural home; do not start a new one. |
| `packages/www/astro.config.mjs` | Register `rehypeSentenceWrap` in `markdown.rehypePlugins`, beside `rehypeStableHeadingIds` (imported at `:19`). |
| The 34 source files holding the 80 call sites | Replace `{t('key')}` in text position with `<Sentences text={t('key')} lang={lang} />`. Highest concentrations measured: `src/pages/[lang]/company.astro` (9), `src/components/LeadMagnetModal.tsx` (5), `src/components/NewsletterSignup.tsx` (5), `src/pages/[lang]/professional-services.astro` (5), `src/components/ContactModal.tsx` (4), `src/components/solution-pages/SPHomeNotASlice.astro` (4), `src/pages/[lang]/newsletter.astro` (4). The static gate in section 5 produces the authoritative list. |

### 3.3 Why not a `dist/**/*.html` rewrite

An `astro:build:done` integration over the 1,842 built HTML files is tempting: zero
call-site edits, covers everything. It was rejected for three measured reasons.

1. **Islands would fight it.** `/en` mounts six hydrated islands
   (`Navigation.tsx:idle`, `ContactModal.tsx:load`, `RegionPickerModal.tsx:load`,
   `NewsletterReturnPopup.tsx:load`, `LeadMagnetModal.tsx:idle`,
   `Footer.tsx:visible`). Spans injected into their server-rendered HTML are a
   hydration mismatch and React drops them on mount. Measured: 5 multi-sentence
   blocks per page live inside islands, on every page checked
   (`/en`, `/en/pricing`, `/en/docs`, `/en/disaster-recovery`). Those are exactly
   where the one unfixed residual sits.
2. **It needs an HTML parser the repo does not have.** No `parse5`, `linkedom`,
   `cheerio`, `jsdom` or `node-html-parser` is a dependency today, and `.npmrc`
   carries `minimum-release-age=1440` plus `ignore-scripts=true`. Adding one for
   this is a supply-chain cost for a problem the component route solves without it.
3. **It would not show up in `npm run dev`.** `astro:build:done` never runs on the
   dev server, so the operator would not see the fix while working.

An `astro:server:setup` + middleware variant fixes (3) but not (1) or (2).

The chosen split gives markdown prose the zero-call-site treatment it deserves
(the rehype plugin covers 1,015 docs files across 13 locales; `/en/docs/quick-start`
alone measures 29 defects today) and pays the call-site cost only where the text is
authored in a component.

---

## 4. The sweep

Measurement-driven, not a grep. A block is defective only if it actually wraps that
way at a real viewport.

### 4.1 The instrument

`packages/www/scripts/measure-sentence-lines.ts`, Playwright + `node:http` static
server over `packages/www/dist`, copying the skeleton of
`scripts/check-browser-smoke.ts` (`chromium.launch()` at `:142`, in-process server
at `:24`). Per candidate block it:

1. flattens the block's text nodes into one string plus an index map;
2. computes a line top per non-space character with a one-character `Range`
   (`getClientRects()`), which is inline-block agnostic, unlike a `Range` over the
   whole element whose rects include the inline-block boxes;
3. segments with `Intl.Segmenter(pageLang)`;
4. reports a finding when a sentence spans more than one line top AND its first line
   top equals the previous sentence's last, or its last equals the next sentence's
   first.

Candidate blocks are elements whose children are all `inline` / `inline-block` /
`contents`, with at least 12 characters of text and at least one client rect, not
under `script`/`style`/`svg`/`noscript`, and not `display:none` or
`visibility:hidden`.

**Do not filter on opacity.** `.reveal` sections are `opacity: 0` until scrolled and
still have full layout. Filtering them out would silently drop `.closing-cta-subtitle`
and every other revealed block. This bit me during measurement: element screenshots
of `#not-a-slice` came back blank white for exactly this reason while the numeric
measurement was correct.

### 4.2 The matrix, and why

Cost measured at roughly **0.5 s per (route, viewport)** against the dev server;
a static file server over `dist` is faster.

- **Viewports: 1440x900 and 390x844.** Two, not three. 1440 is the operator's own
  reference and where the quoted defects live. 390 is where the count is worst
  (`/en` 18 vs 11, `/ja` 20 vs 12), because narrow containers produce more wraps.
  768x1024 was measured and is dominated: it found 5 on every locale, all of which
  also appear at one of the other two. Dropping it removes a third of the runtime
  and no coverage.
- **Locales: all 13.** Not negotiable. The defect count is locale-specific
  (`/en` 11, `/de` 12, `/ja` 12, `/tr` 11, `/ar` 8, `/zh` 4 at 1440x900) because
  word lengths and sentence lengths differ. Checking English only would ship the
  defect in twelve languages, which is the failure class
  `check-em-dash-surfaces.ts:105-111` already documents for this pipeline.
- **Routes: 6 page families, not 1,842 pages.** Every page is generated from a
  template, so a family is fully represented by one member. The six:
  `/{lang}` (home), `/{lang}/pricing`, `/{lang}/docs` (index),
  `/{lang}/docs/quick-start` (markdown article, the rehype path),
  `/{lang}/for-devops` (persona template), `/{lang}/disaster-recovery`
  (solution/FAQ template). Measured defect counts at 1440x900 today: 11, 26, 16, 29,
  20, 19.

13 x 6 x 2 = **156 measurements**.

### 4.3 How results feed the fix

The measurement run emits a JSON report keyed by
`route|locale|viewport|selector|sentence`. Each finding maps to source three ways:

1. selector under a docs article route -> the rehype plugin covers it, no edit;
2. selector inside an `astro-island` subtree -> `Sentences.tsx` in that component;
3. everything else -> the static gate's call-site list (section 5.1) names the file
   and line.

Drive the loop to zero on the six families, then run the instrument once over a
wider route list as a one-off audit before declaring the sweep done. The wider run
is not part of CI.

---

## 5. The CI gate: hybrid, two gates

A static gate alone cannot know whether a block wraps. A browser gate alone cannot
tell a future author that they forgot `<Sentences>` on a string that happens not to
wrap today at the two measured viewports. Both, wired separately so a failure names
the right thing.

### 5.1 Static gate: `check:ci-sentence-wrapping`

`scripts/check-sentence-wrapping.ts`, source-level, sub-second, runs on every PR.

**Asserts:** every text-position render of a catalog value whose English is
multi-sentence and longer than 25 characters goes through `<Sentences>`.

Resolution: parse `.astro` and `.tsx` under `packages/www/src` for
`t(...)` / `ta(...)` / `to(...)` calls in text position, resolve the key against
`en.json`, count sentences with `Intl.Segmenter`, and require the enclosing
expression to be a `Sentences` element.

Shrink-only baseline at `scripts/data/sentence-wrapping-baseline.json` via
`scripts/lib/shrink-only-baseline.ts` (the 8th consumer). Finding id is
`<file>:<translation-key>`, deliberately **not** carrying a line number, so the
baseline survives a line move (`check-em-dash-surfaces.ts:434-435`). Surface floor
`minFiles: 50` on `packages/www/src` so a collapsed glob fails instead of passing
(`check-em-dash-surfaces.ts:89-104`).

**Control (`--selftest`), four legs against a fixture tree under `--root`:**

| Leg | Fixture | Required verdict |
|---|---|---|
| 1 | `.astro` rendering `{t('multi')}` raw, where `multi` is two sentences | REPORTED |
| 2 | the same key inside `<Sentences text={t('multi')} lang={lang} />` | NOT reported |
| 3 | `.astro` rendering `{t('single')}` raw, one sentence | NOT reported |
| 4 | **mutant:** leg 1 re-run with the sentence counter stubbed to always return 1 | leg 1 must flip to NOT reported, and the gate must declare itself broken |

Leg 4 is the one that matters. It mutates the sentence counter, not the fixture,
which proves the finding in leg 1 is produced by sentence detection and not by the
file merely existing. Without it this gate is in the
`check-jq-boolean-default.ts` class recorded at `check-ci-parity.ts:35-41`:
named by a test, never actually exercised.

**Wiring**, per `EXPLORE-chrome.md` 4.1-4.3:

- `package.json`:
  `"check:ci-sentence-wrapping": "tsx scripts/check-sentence-wrapping.ts --selftest && tsx scripts/check-sentence-wrapping.ts"`
  (control-first form, matching `check:ci-dead-css` and `check:ci-layout-overflow`).
- `scripts/ci-runner/manifest.ts`: `GateSpec` with
  `leaves: ['scripts/check-sentence-wrapping.ts']`, no `needs` (source-level, does
  not read `dist`), `ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
  job: 'quality-content', step: 'Sentence wrapping' }`.
- `.github/workflows/ci-quality.yml`, job `quality-content` (`:734`), beside the
  existing "Dead CSS" / "CSS DOM references" steps:

  ```yaml
        - name: Sentence wrapping
          if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
          run: npm run check:ci-sentence-wrapping
  ```

  The step `name:` must match the manifest `step` byte for byte or
  `check:ci-parity` fails.

### 5.2 Browser gate: `check:ci-sentence-lines`

`scripts/check-sentence-lines.ts`, the section 4.1 instrument run as a gate over
`packages/www/dist`. **Asserts zero findings** across the 156-measurement matrix.

Anti-vacuity floor, mandatory: each (route, locale, viewport) must have inspected at
least 8 multi-sentence candidate blocks. A route that 404s, renders empty, or loses
its content to a layout change reports zero defects and would otherwise pass. This
is the same shape as `MIN_MANIFEST_GATES` in
`.ci/scripts/quality/check_gate_reachability_coverage.py`.

Also force `prefers-reduced-motion: reduce` on the context so reveal animations
settle deterministically, and assert `document.fonts.ready` before measuring:
line breaks depend on the actual font, and measuring before webfonts land measures
the fallback face.

**Control (`--selftest`), three legs against an in-memory fixture page served by the
same `node:http` server, no `dist` required:**

| Leg | Fixture | Required verdict |
|---|---|---|
| 1 | a fixed-width block whose copy reproduces the "Most tools copy one / piece. We copy all of it." break | at least 1 finding |
| 2 | identical copy and width, sentences wrapped in `.sentence` inline-blocks | 0 findings |
| 3 | **mutant:** leg 2 re-served with `.sentence { display: inline-block }` stripped from the fixture stylesheet | must go back to at least 1 finding |

Leg 3 mutates the mechanism, not the content. It proves the measurement responds to
inline-block atomicity and not to page identity, which is the failure the two blind
browser overflow hunts in `check-layout-overflow.ts:19-25` are the local precedent for.

**Wiring:** same three points, but job `quality-www-build` (`:1208`) and
`needs: ['build:www']` in the manifest, which is required and not an optimisation
(`manifest.ts:1626`): these gates refuse rather than self-skip when `dist` is absent.
Note also `EXPLORE-chrome.md` finding 5.1, that `check:ci-landmarks` and
`check:ci-browser-smoke` are both missing that `needs` today. Do not copy that bug.

### 5.3 Runtime budget

| Gate | Job | Measured / estimated | Cap |
|---|---|---|---|
| `check:ci-sentence-wrapping` | `quality-content` (ubuntu-latest, 15 min) | under 2 s. It parses the same file set as `check:ci-dead-css` and does no I/O beyond it. | fits with margin |
| `check:ci-sentence-lines` | `quality-www-build` (ubuntu-latest) | 156 x 0.5 s = 78 s, plus roughly 15 s for Chromium launch and the static server. Budget **120 s**. | `quality-www-build` already carries `build:www`; 2 min is comparable to `check:ci-browser-smoke` beside it |

Neither lands on the ubuntu-slim `quality-static` job, so the 15-minute slim cap is
not the binding constraint. If the browser gate ever exceeds 180 s, drop to one
viewport (1440x900) before dropping locales: the locale axis is where the defects
differ, the viewport axis is where they merely multiply.

---

## 6. Order of work

1. `sentences.ts` + `Sentences.astro` + `Sentences.tsx` + the `main.css` rule.
2. `rehype-sentence-wrap.ts` + `astro.config.mjs`. Re-measure `/en/docs/quick-start`
   (29 -> expect 0) to confirm the markdown path alone before touching call sites.
3. `check:ci-sentence-wrapping` with its control, seeded at the current call-site
   count. It generates the authoritative work list for step 4.
4. Drain the call-site list to zero, in two disjoint halves at most
   (`.astro` pages vs `.tsx` islands), per the two-writer cap.
5. `check:ci-sentence-lines` with its control, wired only once step 4 is at zero,
   so the gate is born green.
6. Run the wider one-off audit of section 4.3 and report what it finds.

---

## 7. Risks

1. **Copy/paste across inline-block boundaries.** Chromium can insert a newline
   when copying across inline-block elements. `textContent` is provably unchanged,
   but the clipboard is a separate path. Verify by hand on one paragraph in Chrome
   and Firefox before merging. If it bites, the fallback is
   `.sentence { display: inline-block; }` scoped away from body copy and applied
   only to headings and short blocks, which loses most of the value; say so out loud
   rather than shipping a silent downgrade.
2. **`-webkit-line-clamp` at `src/styles/docs-browse.css:289-290`.** The only
   `display: -webkit-box` on the site. Inline-block children inside a `-webkit-box`
   are fragile. One selector, verify directly.
3. **Vertical growth on dense pages.** Worst measured case is +1.2% page height, but
   that is an average over a whole page. A specific card with a fixed height and four
   sentences can overflow. The 390x844 pass in the browser gate is what catches it;
   do not drop the mobile viewport from the matrix.
4. **818 catalog leaves, 80 call sites, and the gap between them.** The static gate
   resolves keys through literal `t('a.b')` calls. Config-driven pages
   (`src/config/solution-pages.ts`) and `to()` calls returning arrays iterated in a
   template resolve to the template, not to each item. That is correct for the fix
   (one `<Sentences>` in the template covers every item) but it means the static
   gate's count is not a count of rendered blocks. The browser gate is what closes
   that gap, which is the reason the design is a hybrid and not just the cheap half.
5. **Locale drift.** A future English edit that adds a sentence to a value already
   wrapped is caught. A future *translation* that adds a sentence English does not
   have is caught only by the browser gate, and only if that locale is in the matrix.
   All 13 are, deliberately.
6. **`Intl.Segmenter` and product strings.** Verified safe on "e.g." and "v1.2.".
   Not verified on every string in the catalog. The static gate should print the
   segmentation for any value it reports, so a bad split is visible at review time
   rather than at render time.

---

## 8. Out of scope, stated so it is not mistaken for an oversight

**The `/en/docs` card title "Creating Your / First Repository" is not a
sentence-boundary defect and this mechanism does nothing for it.** Measured: it is
an `<a class="docs-card-link">` in a 124px-wide container, carrying `text-wrap:
balance`, holding exactly **one** sentence. It wraps because the container is narrow,
not because a sentence straddles a break. Fixing it is a width, font-size or
card-layout change on `.docs-card-link`, and it belongs to a separate finding.
The team lead's brief listed it among the failing examples; on measurement it is a
different bug.

**Incidental finding, unrelated to this plan.** On `/zh`, the footer newsletter
description renders the English string "Product news and self-hosting tips."
(selector `p.newsletter-footer-desc`). That is an untranslated value, not a wrapping
defect. It is inside the `Footer.tsx` island. Worth a worklist item on its own.
