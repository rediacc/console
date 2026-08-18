# PLAN: Delete the unwired `lint:css` checkers and repair the wired gate they exposed
Status: done
Owner: e6500e92
Updated: 2026-08-18

## Recommendation, in one line

**Outcome 1: delete `packages/www/scripts/check-unused-css.js` and
`packages/www/scripts/check-unused-css-files.js`.** Measured against the wired
`check:ci-dead-css`, the unwired checker finds **zero** real findings the wired gate
misses, **misses six** that the wired gate catches, and **invents three** the wired gate
correctly rejects. It is strictly worse on every axis. Wiring it would install a second,
less accurate implementation of a gate that already runs in CI.

The measurement also turned up two real defects in the **wired** gate, which this plan
fixes in the same change because the standing rule fixes findings in the session that
finds them.

---

## 1. What was actually run, and what it printed

All commands run from `/home/muhammed/monorepo/console` (or `packages/www` where noted) on
2026-08-18, stdout and stderr captured to separate files.

| Command | Exit | Result |
|---|---|---|
| `npm run lint:css` (in `packages/www`) | **1** | `85 unused CSS classes found` |
| `npm run lint:css-files` (in `packages/www`) | **1** | `2 unused CSS files found` |
| `npx tsx scripts/check-dead-css.ts --list` | 0 | **92** dead classes |
| `npm run check:ci-dead-css` | 0 | 92 dead, baseline 92, no new, no fixed |
| `npm run check:ci-css-dom-refs` | 0 | Rendered 811, styled 1335, unstyled 32 (baseline 32), 9/9 controls pass |

Two numbers in the task brief are stale and I am recording the measured ones instead:
`scripts/data/dead-css-baseline.json` holds **92** entries, not 95, and it matches the
live set exactly (zero new, zero fixed). The `css-dom-refs` baseline is 32 unstyled
classes as stated.

**Unwired confirmed, with a planted control.** `grep -rPn 'lint:css|lint:all|check-unused-css'`
across the repo (excluding `node_modules`, `dist`, `.git`) returns hits only in
`packages/www/package.json:13-15`, the two scripts' own headers, and prose in
`agent/` research documents. Nothing in `package.json` (root), `scripts/ci-runner/manifest.ts`,
`.github/workflows/`, or `.ci/`. The control for that grep was the same pattern run for
`check:ci-dead-css`, which returns 5 files including `scripts/ci-runner/manifest.ts:1604`
and `.github/workflows/ci-quality.yml:721`. The instrument fires; the zero is real.

---

## 2. The set relationship, computed

Names only (the unwired checker reports a bare class name plus a line number; the wired
gate reports `file:class`), deduplicated and sorted, then `comm`'d.

```
lint:css              85 unique names
check:ci-dead-css     92 unique names
intersection          82
lint:css only          3   compliant, restored, sealed
dead-css only         10   btn-full, newsletter-footer, pricing-card, pricing-grid,
                           problem-illustration, video-player,
                           toc-level-3, toc-level-4, toc-level-5, toc-level-6
```

`check:ci-css-dom-refs` is the inverse question (rendered but unstyled) and shares no
findings with either by construction. It is not a candidate for consolidation and is left
untouched.

### 2a. The 3 that only `lint:css` finds are all FALSE POSITIVES

`.compliant`, `.restored` and `.sealed` are state modifiers on
`src/styles/solution-pages.css:736,795,832` (`.sp-server-card.sealed`,
`.sp-server-card.restored`, `.sp-cost-card.compliant`). They are applied here:

```
packages/www/src/components/solution-pages/SPHowItWorks.astro:87
  <div class:list={['sp-server-card', howItWorks.cloneVisual.production.cardClass ?? 'production']}>
```

and the value of `cardClass` comes from the translation catalogue, not from any source
file:

```
packages/www/src/i18n/translations/en.json   "cardClass": "sealed" | "restored" | "compliant"
                                             | "verified" | "config" | "down"   (17 occurrences)
```

So all three are live. `lint:css` cannot see them because it skips the `content/`
directory and only scans `.astro/.tsx/.ts/.js`, never `.json`. It reports a class as dead
whose deletion would strip the styling from every solution page's how-it-works card.

**The wired gate gets these right only by luck**, which is defect A in section 5.

### 2b. Six of the 10 that only `check:ci-dead-css` finds are REAL, and `lint:css` is blind to them by construction

`lint:css`'s last usage pattern is
`new RegExp('\\b' + escapeRegex(className) + '\\b')` (`check-unused-css.js:216`). A hyphen
is a non-word character, so `\b` matches at a hyphen and the pattern accepts a **prefix or
suffix** of a longer hyphenated name. Verified cases:

| Dead class | The unrelated name that "proves" it alive | Where |
|---|---|---|
| `.btn-full` | `btn-full-width` | `src/**` |
| `.pricing-card` | `cf-pricing-card` | `src/components/CfPricingCard.astro:65` |
| `.pricing-grid` | `cf-pricing-grid` | `src/pages/[lang]/pricing.astro:82` |
| `.video-player` | `sp-video-player` | `src/components/solution-pages/SolutionVideoPlayer.tsx:153` |
| `.newsletter-footer` | `newsletter-footer-desc` | `src/components/NewsletterSignup.tsx:127` |
| `.problem-illustration` | `sp-problem-illustration` | `src/components/solution-pages/SPProblem.astro:53` |

`check-dead-css.ts:46` tokenizes with `/[-_a-zA-Z][\w-]*/g`, which is greedy and yields the
whole token `cf-pricing-card`, so it never mistakes it for `pricing-card`. In a codebase
with `cf-`, `sp-`, and `tv-` prefixes on nearly every component this is not an edge case,
it is the dominant naming pattern, and it silently blinds `lint:css` across the site.

(One of these six, `.newsletter-footer`, turns out to be live for a different reason. See
defect B in section 5. The blindness argument stands regardless: `lint:css` was right
about it by accident, for a reason unrelated to why it is live.)

### 2c. The remaining 4 are `toc-level-3..6`, where `lint:css` is right

`src/layouts/DocsLayout.astro:238` and `src/layouts/ContentLayout.astro:138` render
``class={`sidebar-item toc-item toc-level-${heading.level}`}``. `lint:css` suppresses
these through `DYNAMIC_CLASS_PATTERNS` (`/^toc-level-[2-6]$/`, `check-unused-css.js:40`).
The wired gate has them baselined as dead. That is defect B in section 5.

So the whitelist encodes one piece of real knowledge, and it is knowledge worth keeping.
It is kept as a code fix to the wired gate, not as a second script.

---

## 3. Scoreboard

| | `lint:css` | `check:ci-dead-css` |
|---|---|---|
| Real dead classes found | 76 | 82 |
| Real dead classes missed | 6 | 0 (of the union) |
| False positives emitted | 3 | 10 (see section 5) |
| Wired into CI | no | yes |
| Baselined, so it can land green | no | yes |
| Stable finding id | no (line numbers) | yes (`file:class`) |
| Has an inline control | yes (comment stripper) | yes (7 selftest assertions) |
| Reads scoped `<style>` blocks | no | no (dead-css); yes (dom-refs) |

`lint:css` loses on precision, on recall, on wiring, and on finding-id stability. There is
no axis on which it wins.

---

## 4. What is lost by deleting, stated honestly

1. **The `DYNAMIC_CLASS_PATTERNS` whitelist** (`check-unused-css.js:26-44`): 17 patterns
   naming classes applied at runtime (`active`, `error`, `selected`, `open`, `closed`,
   `fade-in`, `fade-out`, `loaded`, `loading`, `visible`, `hidden`, `expanded`,
   `collapsed`, `toc-level-[2-6]`, `h[1-6]`, `no-js`, `js`). Only the `toc-level` entry
   currently matters, because the others all appear as tokens somewhere and are already
   alive to the wired gate. Step 3 of the implementation preserves the underlying
   capability generically rather than transcribing the list.
2. **The comment stripper and its inline control** (`check-unused-css.js:69-119`), which
   is a genuinely good piece of work: it blanks block comments while preserving line count,
   and it runs a two-directional control on every invocation. Nothing is lost, because
   `check-dead-css.ts:39` already strips comments with `/\/\*[\s\S]*?\*\//g` (multi-line
   safe, the same bug class the stripper was written for) and its `--selftest` asserts
   both directions: `a class inside a CSS COMMENT is not treated as defined` and the two
   `CONTROL:` lines asserting live names stay alive. Verified: 7/7 pass.
3. **File-level detection** from `check-unused-css-files.js`. See section 6.

Nothing else. The deletion removes 542 lines across two files plus three npm script keys.

---

## 5. Two real defects in the WIRED gate, found by this comparison

These are not optional. `scripts/data/dead-css-baseline.json` currently records **10 of
its 92 entries as dead when they are live**. The baseline is the drain list for a
simplification campaign, so every one of those ten is an instruction to delete a rule that
a live page depends on.

### Defect A: a class supplied only by the translation catalogue is invisible

`check-dead-css.ts:59-62` globs sources as
`src/**/*.{astro,tsx,ts,jsx,js,md,mdx}` plus `public/**/*.js`. It never reads
`src/i18n/translations/*.json`, where all 17 `cardClass` values live. Today's six values
(`compliant`, `config`, `down`, `restored`, `sealed`, `verified`) all happen to be ordinary
English words that occur in prose inside `src/content/**/*.md`, so the over-broad token
scan rescues them **by coincidence**. Evidence:

```
src/content/docs/en/data-regions.md          contains the word "compliant"
src/content/docs/en/backup-restore.md        contains the word "restored"
src/content/docs/en/proxy-and-executor.md    contains the word "sealed"
```

The next `cardClass` value that is not an English word (`archived-cold`, `sp-warm`,
anything hyphenated) will be reported as new dead CSS and the gate will fail, or worse, be
drained. `lint:css` found this, which is the single most useful thing it did, and it found
it for the wrong reason.

**Fix:** add `${WWW}/src/i18n/translations/en.json` to `sources()`.

**A trap inside the fix, verified before writing it here.** Adding the whole file as a
token soup rescues exactly one baselined entry that is genuinely dead:
`pricing-page.css:emergency` (the rule is `.detail-badge.emergency` at
`src/styles/pricing-page.css:475`; the token comes from prose such as
`"24/7 emergency hotline for critical incidents"` at `en.json:661`). So the fix must
harvest **only the values of keys literally named `cardClass`**, not every token in the
file. Measured: that yields exactly `{compliant, config, down, restored, sealed, verified}`
and rescues nothing else.

### Defect B: a class built by a template literal in a class attribute is reported dead

Eight baselined entries are live through interpolation:

| Baselined as dead | Actually rendered by | Values |
|---|---|---|
| `sidebar-shared.css:toc-level-3..6` | ``class={`sidebar-item toc-item toc-level-${heading.level}`}`` at `src/layouts/DocsLayout.astro:238`, `src/layouts/ContentLayout.astro:138` | levels 2 to 6 |
| `newsletter.css:newsletter-footer`, `newsletter-inline`, `newsletter-modal`, `newsletter-sticky-bar` | ``className={`newsletter-signup newsletter-${variant}`}`` at `src/components/NewsletterSignup.tsx:116` (and `:90`) | `type Variant = 'inline' \| 'footer' \| 'sticky-bar' \| 'page' \| 'modal'` at `NewsletterSignup.tsx:7` |

Every one of the five variants is reachable from a real call site:
`variant="footer"` (`src/components/Footer.tsx:225`), `variant="page"`
(`src/pages/[lang]/newsletter.astro:57`), `variant="sticky-bar"`
(`src/components/BlogStickyBar.tsx:70`), `variant="inline"`
(`src/pages/[lang]/changelog.astro:100`, `src/layouts/ContentLayout.astro:156`),
`variant="modal"` (`src/components/NewsletterReturnPopup.tsx:122`).
`newsletter-error` is genuinely dead: no source ever renders it.

**Fix, and why the obvious version of it is wrong.** The obvious fix is to harvest every
``prefix-${`` fragment in every template literal and mark any class with that prefix as
alive. I tested that and it is too loose: `src/components/solution-pages/SPDownloadGated.astro:24`
holds ``const source = `solution-${slug}-30scroll`;``, which is an analytics **source
string**, not a class, and the loose rule would rescue four genuinely dead classes
(`responsive.css:solution-benefits`, `solution-card`, `solution-description`,
`solution-title`).

The correct fix harvests interpolated fragments **only from a class position**: inside
`class=`, `className=`, or a `class:list` entry. That covers both real cases and excludes
the analytics string, which lives in a bare `const`. `check-css-dom-refs.ts:45-68` already
has the parser for exactly these three positions and can be the reference implementation.

### Defect C, third-party runtime classes (smaller, same family)

`tutorial-video.css:plyr__poster` and `plyr__captions` are baselined as dead. `plyr` is a
declared dependency (`packages/www/package.json:60`, `"plyr": "^3.8.4"`) imported by
`src/components/TutorialVideoPlayer.tsx`, which also imports `../styles/tutorial-video.css:23`.
The library builds those elements at runtime; both tokens are present in
`node_modules/plyr/dist/plyr.js`. Styling a vendor library's generated DOM is the entire
point of those two rules, and deleting them would unstyle the tutorial player's poster and
captions.

**Fix:** a documented `VENDOR_CLASS_PREFIXES` list in `check-dead-css.ts` containing
`plyr__`, carrying a `BLOCKER:` reason per `docs/agent-reference/suppressions.md`, since it
is an allowlist. Alternative considered and rejected: scanning `node_modules/plyr/dist` as
a source. That is more principled but makes the gate depend on an installed tree and on a
minified bundle's token soup, and it would slow every run for one library.

**Net effect on the baseline:** 10 of 92 entries stop being dead. The baseline is
shrink-only and fails when a baselined finding is no longer found, so the same commit must
run `npx tsx scripts/check-dead-css.ts --write-baseline`, taking it from 92 to 82.

---

## 6. `check-unused-css-files.js`: delete too, after draining it

It reports 2 findings and **both are real**:

```
src/styles/language-switcher-inline.css     (34 lines)
src/styles/team-video.css                   (235 lines)
```

Verified independently: `grep -rPn` for each basename across the repo finds no `import`,
no `href=`, no `@import`. The only hits outside the file itself are prose in
`agent/programs/www-simplification/research/RESEARCH-docs.md:313,321,326`, which reached
the same conclusion by hand, and entries in `scripts/data/dead-css-baseline.json` and
`scripts/data/static-nowrap-baseline.json`.

**This capability is not covered by any wired gate today.** Knip's `packages/www` workspace
config globs `project: ["src/**/*.{ts,tsx,astro,mdx}", "scripts/**/*.{js,cjs,mjs,ts}"]`
(`knip.jsonc`), with no `.css`. Only the `private/account/web` workspace includes `css`.
Adding css to www's knip globs would immediately false-positive on
`public/styles/main.css` and `responsive.css`, which are loaded by `<link rel="stylesheet">`
at `src/layouts/BaseLayout.astro:289-290` and are not imported by any module. That is
presumably why the glob is what it is.

**But the capability is subsumed once the findings are drained.** Every class in a newly
orphaned stylesheet becomes a NEW dead class and fails `check:ci-dead-css`. The only gap
is today's exact case: a stylesheet whose classes are *already* in the baseline. Delete
the two files, drain their entries, and the future-regression case is covered.

To close the residual gap properly (a stylesheet whose classes are all dead, or one with
no class selectors at all), add a small assertion to `check-dead-css.ts`: if every class
defined by a sheet is in the dead set, report the **sheet**, not the classes. That is
roughly ten lines, it reuses `definedClasses()` and `findDead()`, and it needs no new
wiring because `check:ci-dead-css` is already a manifest-registered gate.

So: delete `check-unused-css-files.js`, delete the two dead stylesheets, and let the wired
gate carry the capability.

---

## 7. The drain question: 82 real dead classes, and which are safe

The brief asks whether to baseline or drain the 85. Since the recommendation is deletion,
the live question is what to do with `check:ci-dead-css`'s 92, and the answer has three
tiers.

**Tier 1, must be removed from the baseline because they are not dead (10).** Sections 5
above. `toc-level-3..6`, `newsletter-{footer,inline,modal,sticky-bar}`, `plyr__poster`,
`plyr__captions`. These are drained by fixing the gate, never by deleting CSS.

**Tier 2, whole dead files, safe mechanical deletion (19).** `team-video.css` (18 `tv-*`
classes, zero importers) and `language-switcher-inline.css` (`translation-notice`, zero
importers). Deleting the two files removes all 19 baseline entries at once and 269 lines
of CSS. Highest value per unit of risk in the set.

**Tier 3, individual rules, safe but need one grep each (53).** These break down cleanly
by stylesheet, and the grep to run before each deletion is the exact-token grep
`grep -rPn "(?<![\w-])<name>(?![\w-])"` over `src` and `public`, which is the check that
distinguishes `.pricing-card` from `cf-pricing-card`:

- `public/styles/main.css` (29): a `btn--*` modifier family (`btn--block`, `btn--bolt`,
  `btn--brand-outline`, `btn--ghost`, `btn-full`), a `form-notice-*` block of 6, a
  `footer-founder*` block of 3, `cf-guarantee-{link,photo}`, the video block
  (`video-element`, `video-player`, `video-wrapper`), and `cta-bolt`, which is the
  specimen named in `check-dead-css.ts`'s own header and still has a dedicated CI gate
  (`check:cta-bolt`) policing the uniqueness of a class nobody renders.
- `src/styles/pricing-page.css` (16) and `professional-services-page.css` (7): mostly a
  `ps-access-*` block of 7 and pricing layout leftovers.
- `public/styles/responsive.css` (6): `solution-{benefits,card,description,title}`,
  `scenario-grid`, `hero-cta-primary`. Confirmed dead, and confirmed not rescued by the
  `solution-${slug}-30scroll` string (section 5, defect B).
- `src/styles/solution-pages.css` (4): `sp-quote-{attribution,author,photo,title}`, the
  styling for the disabled `SPSocialProof.astro` component that knip already ignores with
  a BLOCKER reason. **Do not delete these** without also deciding the component's fate;
  the knip ignore says the component is kept deliberately so it can be restored.

**Recommendation on draining:** do Tier 1 and Tier 2 in this change (they are forced by
the shrink-only rule and are a 269-line simplification with zero risk). Leave Tier 3 to
the stylesheet sweeps this campaign is already running, where a rule deletion can be
verified against a rendered page. Draining 53 individual rules is a different task from
deleting a redundant checker, and mixing them makes both harder to review.

---

## 8. Implementation steps

Files touched, in order:

1. `packages/www/package.json`: delete the three script keys `lint:all`, `lint:css`,
   `lint:css-files` (lines 13-15).
2. Delete `packages/www/scripts/check-unused-css.js` and
   `packages/www/scripts/check-unused-css-files.js`.
3. Delete `packages/www/src/styles/team-video.css` and
   `packages/www/src/styles/language-switcher-inline.css`.
4. `scripts/check-dead-css.ts`:
   - add `src/i18n/translations/en.json`, harvesting only `"cardClass"` values (defect A);
   - harvest interpolated template-literal prefixes from `class=` / `className=` /
     `class:list` positions only, and mark a defined class alive when it carries such a
     prefix (defect B);
   - add `VENDOR_CLASS_PREFIXES = ['plyr__']` with a `BLOCKER:` reason (defect C);
   - add the fully-dead-stylesheet assertion from section 6;
   - add the four new selftest controls from section 9.
5. `scripts/data/dead-css-baseline.json`: regenerate via
   `npx tsx scripts/check-dead-css.ts --write-baseline`. Expected 92 to **63**
   (92 minus 10 rescued minus 19 from the two deleted files). Verify the resulting count
   by hand; do not accept whatever the tool writes without diffing it.
6. `scripts/data/static-nowrap-baseline.json`: contains
   `packages/www/src/styles/team-video.css:.tv-time`. Deleting the file will make that
   entry stale. Check whether that gate is shrink-only and drain it in the same commit.
7. Stale prose to correct, since a plan that asserts a wrong fact will mislead the next
   session: `agent/PLAN-localize-cheat-sheet-rendering.md:345` states that
   `packages/www/package.json` "runs `lint:css` / `lint:css-files` (unused-CSS gates)",
   which is false and is precisely the belief this plan disproves; its line 478 asks an
   open question about `lint:css-files` that deletion answers.

**No CI wiring changes.** Nothing is added to `scripts/ci-runner/manifest.ts` or
`.github/workflows/ci-quality.yml`. `check:ci-parity` and
`check:ci-gate-reachability-coverage` key off the `check:ci-*` naming convention, and
`lint:css` never carried that prefix, which is exactly why it slipped through unnoticed.
Removing a non-`check:ci-*` script is invisible to both.

**Do not run `astro build`.** No step here needs a fresh `dist/`. If step 5's count needs
confirmation against built output, that is the lead's build to run, not this change's.

---

## 9. Tests, each with its planted defect

Every one goes into `scripts/check-dead-css.ts`'s `--selftest`, which already runs
unconditionally before the real check (`check-dead-css.ts:107`), so a broken control fails
the gate rather than being skipped. The existing 7 controls stay.

| # | Control | The plant that must make it FIRE | Silent on the clean tree because |
|---|---|---|---|
| 1 | A class supplied only as a `cardClass` value is alive | Fixture: sheet defines `.zeta`, sources mention it nowhere, `en.json` fixture has `"cardClass": "zeta"`. Remove the `cardClass` harvest and the assertion must fail. | The harvest reads the key. |
| 2 | A `cardClass` harvest does NOT swallow the whole file | Fixture `en.json` with `"body": "an emergency hotline"` and no `cardClass`. Assert `emergency` is NOT alive. Plant: change the harvest to tokenize the whole file and this must fail. | Only `"cardClass"` values are read. |
| 3 | A class built by interpolation inside a class attribute is alive | Fixture source ``class={`toc-level-${n}`}``, sheet defines `.toc-level-3`. Plant: revert the class-position harvest and this must fail. | The prefix `toc-level-` is harvested from a class position. |
| 4 | An interpolated string OUTSIDE a class position does NOT rescue | Fixture ``const source = `solution-${slug}-30scroll`;`` with sheet defining `.solution-card`. Assert `solution-card` is still DEAD. Plant: widen the harvest to all template literals and this must fail. | The bare `const` is not a class position. |
| 5 | A vendor-prefixed class is alive | Sheet defines `.plyr__poster`, no source mentions it. Plant: empty `VENDOR_CLASS_PREFIXES` and this must fail. | `plyr__` is listed with its BLOCKER reason. |
| 6 | A non-vendor class with a similar name is still dead | Sheet defines `.plyrical`, unmentioned. Assert dead. Plant: match the prefix as a substring anywhere rather than at position 0 and this must fail. | Prefix match is anchored. |
| 7 | A stylesheet whose every class is dead is reported as a FILE | Two-sheet fixture, one all-dead, one with a live class. Assert exactly the first is reported. Plant: delete the assertion and this must fail. | The live sheet has a live class. |

Beyond the selftest, three end-to-end checks on the real tree, each with a named plant:

- **E1, the gate still fires on new dead CSS.** Append `.zzz-planted-dead { color: red }`
  to `packages/www/public/styles/main.css`, run `npm run check:ci-dead-css`, require exit
  1 naming `zzz-planted-dead`, then remove the line by hand (never `git checkout`) and
  require exit 0. Without this the whole change could land with the gate quietly vacuous.
- **E2, the shrink-only direction still fires.** With the regenerated baseline in place,
  add one entry by hand for a class that is not dead, run the gate, require exit 1 with
  the `baselined class(es) are no longer dead` message, then remove it.
- **E3, the deletions did not unstyle anything.** After deleting `team-video.css` and
  `language-switcher-inline.css`, run `npm run check:ci-css-dom-refs`. It must stay at
  exit 0 with unstyled still at 32. If a rendered class loses its only rule, this is the
  gate that says so, and it is the reason the file deletions are safe to do blind. Plant
  to prove it can fire: temporarily delete `src/styles/newsletter.css` instead and confirm
  the unstyled count rises above baseline, then restore it.

---

## 10. The rejected alternative, and why

**Outcome 2, wire `lint:css` with a shrink-only baseline.** Rejected. The cost is not the
wiring, it is the second implementation.

Had it been chosen, it would need all three points, because `check:ci-parity` and
`check:ci-gate-reachability-coverage` enforce them together:

1. A root `package.json` script named `check:ci-unused-css` (the `check:ci-` prefix is what
   both meta-gates key off; a `lint:*` name is invisible to them, which is the whole
   reason this script sat red and unread).
2. An entry in `scripts/ci-runner/manifest.ts` with `gate: true`, `leaves`, and a `ci`
   block naming workflow, job, and step, following the shape at
   `scripts/ci-runner/manifest.ts:1604-1614`.
3. A step in `.github/workflows/ci-quality.yml`'s **`quality-content`** job, beside
   `Dead CSS` at line 720, invoked as `npm run check:ci-unused-css`. The lane note at
   `manifest.ts:2031-2035` is the reason the invocation form matters: a gate was rejected
   from its best subject-matching lane because that lane's step ran a script **by path**
   rather than through npm, so the chain would never have reached CI. The pairing follows
   what the step RUNS. `quality-content` runs npm scripts and is a source-only lane, which
   is right for a checker that reads CSS and sources and needs no build.

And it would need a baseline, which is where the real cost shows. Its finding id would
have to change: it currently reports `Line 80: .tv-controls`, and a line number is the
wrong id for exactly the reason `check-em-dash-surfaces.ts:54-57` gives, that inserting a
paragraph above shifts every id below it and churns the baseline on unrelated edits. It
would have to move to a `file:class` id, which is what `check-dead-css.ts` already uses.
At that point the two gates have the same id space, the same baseline shape, the same
subject, and two different and disagreeing implementations of "is this class used". That
is the second implementation nobody runs, installed on purpose.

The `ZERO_SURFACES` invariant from `check-em-dash-surfaces.ts:135-153` is worth carrying
forward as a concept even under the deletion outcome: it is the rule that a surface which
joined at zero may never have an id enter its baseline. The analogue here is the two
stylesheets being deleted. Once they are gone, no future entry from those paths can appear,
because the paths will not exist. That is the strongest form of the invariant available.

---

## 11. Open questions for the operator

- **Tier 3 draining (53 rules).** This plan deliberately leaves them. If the answer is
  "drain them in this change too", say so and it becomes a much larger diff needing a
  rendered-page check per stylesheet. DEFAULT if unanswered: leave them baselined, and let
  the stylesheet sweeps take them.
- **`sp-quote-*` and `SPSocialProof.astro`.** Four dead classes style a component that
  `knip.jsonc` deliberately keeps for later restoration (rediacc/console#519). Deleting the
  CSS would make that restoration a rewrite rather than a re-enable. DEFAULT: keep the CSS,
  keep it baselined.
- **`cta-bolt` and `check:cta-bolt`.** A dedicated CI gate polices the uniqueness of a
  class that nothing renders. Out of scope here, but it is a gate that cannot fail in the
  way that matters, and it belongs on the simplification list.
