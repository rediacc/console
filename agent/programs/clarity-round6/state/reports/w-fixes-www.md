# w-fixes-www

Writer wave on `clarity-round6`. Four verified defects, all fixed. Every number below was
re-measured in this session against the live tree or the frozen `dist/`.

---

## Defect 1 - dead config fields `illustration` / `illustrationMobile`

**Confirmed live before touching anything.** `dist/en/solutions/instant-recovery/index.html`
contains exactly one `sp-problem-illustration` div holding an inlined `<svg>`, and **zero**
`<picture>` elements. The JSDoc on `illustrationMobile` promised a `<picture>` swap under
768px; no page has ever emitted one.

Removed from `packages/www/src/config/solution-pages.ts`:

- the `illustration?: ImageMetadata` and `illustrationMobile?: ImageMetadata` fields;
- all 21 `illustration:` write sites and the single `illustrationMobile:` write site;
- all 22 `import illustration* from '../assets/images/illustrations/*.svg'` lines and the
  now-orphaned `import type { ImageMetadata } from 'astro'`.

The file is 52 lines shorter and imports exactly one thing (`ACCOUNT_PATH`).

Nothing reads these fields: `SolutionPage.astro:114` passes `slug`, `SPProblem.astro:43`
calls `resolveSolutionIllustration(slug)`, and
`packages/www/src/utils/solution-illustration.ts:10-20` resolves by slug through an eager
`import.meta.glob`. That path is untouched, so every page keeps its drawing.

### The orphaned asset - DELETED, and why

`packages/www/src/assets/images/illustrations/instant-recovery.mobile.svg` was **deleted**.

Two reasons, and the first is the load-bearing one: `diff` against
`instant-recovery.svg` reports the files **byte-identical** (both 1,575 bytes). There is no
portrait variant to lose; the "mobile" file is a copy of the desktop one under a different
name. Second, the glob in `solution-illustration.ts` is `*.svg` and `eager: true`, so the
file was being read and inlined into the module graph on every build while being
unreachable at runtime (its glob key would be `instant-recovery.mobile`, a slug no page
has). It is tracked in git, so the bytes are recoverable if that call is ever reversed.

---

## Defect 2 - `socialProof` was a phantom section

**Confirmed live:** across the whole frozen `dist/`, `sp-social-proof` and `sp-quote-text`
appear in exactly one file, `dist/assets/dev-environments-brief.CIViZ2DP.css`. Zero
occurrences in any built HTML.

Removed `'socialProof'` from the `SectionType` union and from `ALL_SECTIONS` in
`solution-pages.ts`. `SPSocialProof.astro` is untouched, as instructed, and so is the
`.sp-social-proof` half of the grouped padding selector at
`packages/www/src/styles/solution-pages.css:1749`.

**One edit outside my stated file list, flagged deliberately.**
`packages/www/src/config/persona-pages.ts` imports `SectionType` from `solution-pages.ts`
and listed `'socialProof'` in three of its four `sections` arrays (`:56`, `:79`, `:105`).
Removing the union member without removing those three lines is a hard type error, so I
removed them. Three lines, no other change to that file. `npx tsc --noEmit -p
packages/www/tsconfig.json` reports nothing for either config (the only errors it prints
are the pre-existing `Property 'plausible' does not exist on type 'Window'` family, which
predate this wave).

### i18n leaves orphaned - 184, and NOT deleted

Counted from the gate's own `--list` output:

| branch family | branches | leaves each | total |
|---|---|---|---|
| `pages.solutionPages.<page>.socialProof` | 20 | 8 | 160 |
| `pages.personaPages.<page>.socialProof` | 3 | 8 | 24 |
| **total** | **23** | | **184** |

The eight leaf names are `quote`, `author`, `company`, `impact.improvement`, and two rival
spellings of the same two facts (`impact.before.label` / `impact.beforeLabel` and the
`after` pair), which is its own small finding: the branch carries a nested shape and a flat
shape simultaneously, and `SPSocialProof.astro:27` reads both via
`socialProof.impact as (ImpactNested & ImpactFlat)`.

Two of the 22 solution `contentKey`s and one of the four persona pages never had a
`socialProof` branch at all.

I deleted none of them. They are frozen in the new baseline (defect 3) so they cannot be
forgotten, and the thirteen catalogs are the lead's serialised surface.

---

## Defect 3 - the wildcard blind spot in `check-dead-translation-keys`

### The root cause, restated in terms of what to fix

The pattern `pages.solutionPages.*` was never the problem by itself. `to()` returns a
**subtree**, and a subtree pattern vouches for everything beneath it. So the gate could not
see a missing SECTION, only a missing PAGE.

### The fix

`scripts/check-dead-translation-keys.ts` now narrows a `to()` result that is bound to a
variable down to the properties actually read off that variable. Two new exported
functions, `stripComments()` and `subtreeNarrowing()`, and one change to the tail of
`referencePatterns()`, which now runs the narrowing LAST because it has to REMOVE patterns
the earlier rules emitted (the same key text is produced both by the `to()` rule and by the
"any dotted backtick string" rule, and leaving either copy in restores the whole subtree).

Three guards keep it from inventing false positives. Each was found by running against the
real tree, and each is now a permanent self-test case:

1. **`to()` only, never `t()`.** `t()` returns a string, so `askTemplate.replaceAll(...)`
   is a String method. A first cut that narrowed `t()` too reported the real, live key
   `documentation.pageActions.ask` as dead.
2. **Any non-property use falls back to the whole subtree.** `roi-calculator.astro:34`
   hands `content` to a component intact; `pricing.astro:30` reads `faqItems` through
   `Array.prototype`. Both keep full coverage.
3. **The scan runs on comment-stripped source.** This one is not cosmetic. The frontmatter
   note in `SolutionPage.astro:2` contains the English word "content" in prose, which read
   as a bare use of the `content` variable and switched narrowing off for the entire file.
   Before this guard the narrowing fired on 2 files; after it, on 4, including the two that
   matter.

Pattern extraction still reads comments. Only the narrowing scan strips them. Stated
plainly because it is a real limitation: a key path written inside a comment still counts
as a reference.

### The control - planted, fired, removed

Run against a fixture root (`--root`), a full copy of `packages/www/src`, so the real
`en.json` was never touched.

| step | command | result |
|---|---|---|
| A: fixture unmodified | new gate, `--root <fixture>` | `exit 0`, green |
| B: plant `pages.solutionPages.encryption.zzzOrphanSection.{title,body}` | new gate | **`exit 1`**, "2 NEW ... in 1 branch(es)", both planted keys named |
| B': **same plant, PRE-CHANGE gate** (`git show HEAD:...`) | old gate | `exit 0`, "All 6927 ... are reachable" |
| C: plant removed | new gate | `exit 0`, green |
| D: delete a BASELINED branch (`pages.solutionPages.downloadGated`) | new gate | **`exit 1`**, "8 baselined key(s) are no longer dead ... drain it" |

B' is the important row: it is the blind spot, reproduced. The old gate declares a planted
orphan section reachable.

### The shrink-only baseline, and why there is one

Sharpening the gate exposed **192** pre-existing dead leaves in one step. None of them are
deletable by this wave (the catalogs are forbidden to me), and a red gate blocks every
other session in this tree. So the finding is frozen the way this repo already freezes six
other backlogs: `scripts/data/dead-translation-keys-baseline.json`, seeded with exactly
those 192 and wired through `scripts/lib/shrink-only-baseline.ts`.

That is strictly stronger than the status quo, which had **zero** visibility into any of
them, and it couples correctly: the moment the lead deletes a baselined branch the gate
hard-errors until the baseline is drained (control D above).

The 192 split:

- **184** the `socialProof` leaves of defect 2;
- **8** `pages.solutionPages.downloadGated.{title, description, emailPlaceholder,
  submitLabel, successMessage, errorMessage, disclaimer, dismissLabel}` - a **new find**,
  not on my list. `SPDownloadGated.astro` used to hold an inline email form; the form moved
  into `LeadMagnetModal.tsx` and the component now renders only a `<LeadMagnetButton>`. The
  eight strings the form used have been translated into thirteen catalogs ever since, and
  the old wildcard hid them. Those need deleting by the catalog owner too. That is **8
  leaves x 13 locales = 104 values**, on top of 184 x 13 = 2,392 for socialProof.

`bash .ci/scripts/test/gates/test-shrink-only-composition.sh` passes and now counts 16
baseline writers instead of 15, with the new one among the guarded set. I did not edit that
file.

---

## Defect 4 - four CSS defects

### 4a. Two white bands meeting at 1.00:1

**The reported classes were not the ones that render adjacent.** `.sp-roi-section` is
`SPRoiCalculator`'s root and appears only on `/[lang]/roi-calculator`, where its neighbour
above is `.sp-page-header`. The pair that actually meets on the solution pages is
`.sp-cost-section` (`SPCostCalculator.tsx:49`) then `.sp-how-it-works`, both
`var(--sp-bg-white)`. The defect is real, the class name was off by one.

`.sp-cost-section` now carries `border-bottom: 1px solid var(--color-border-subtle)`
(`packages/www/src/styles/solution-pages.css`), matching the idiom `.sp-stats` already uses
eleven rules earlier.

**A sibling selector cannot do this job, and it is worth recording why.**
`SPCostCalculator` is a `client:visible` island. In the built HTML the section is wrapped:
`...</section><!--astro:end--></astro-island> <section class="sp-how-it-works">`. So
`.sp-cost-section + .sp-how-it-works` matches nothing; `.sp-how-it-works` is a sibling of
the WRAPPER. Verified against `dist/en/solutions/environment-cloning/index.html`.

### 4b. `.nav` had no lower edge - ADDED, site-wide, deliberately

My call: **yes, add it.** `.nav` is `background-color: var(--color-bg-alt)` and after A7
`--color-bg-band` resolves to that same `--color-bg-alt`, so on the 25 solution and persona
pages a fixed bar sits on an identically coloured band and content scrolls up into it with
no boundary at all. A fixed bar over scrolling content wants an edge on every route; on
pages whose opening band already differs, an 8%-black hairline reads as a seam, not a rule.

What I did NOT do is add a bare `border-bottom` and leave it there. `--nav-top-offset` is
what mega-menu panels drop from (`persona-mega-menu.css:54`, `learn-menu.css:36`), what
sticky sidebars measure (`sidebar-shared.css:29-30`), and what `scroll-padding-top` uses
(`main.css:795`, `:812`). A border the offset did not know about leaves a 1px stripe of
page showing between the nav and every panel anchored under it. So the width is a token:

- `--nav-border-width: 1px` at `main.css:320`, single declaration site in the whole tree
  (verified by grep, including `BaseLayout.astro`'s inline `:root`);
- `--nav-top-offset` is now `calc(--nav-height + --nav-border-width + --announcement-bar-height)`;
- `.nav` uses `border-bottom: var(--nav-border-width) solid var(--color-border-subtle)`.

`--color-border-subtle` already inverts (`rgba(0,0,0,0.08)` light, `rgba(255,255,255,0.1)`
dark). `.nav`'s `clip-path: inset(0 -100vw -100vh -100vw)` has a negative bottom inset, so
the border is not clipped.

### 4c. The near-black video placeholder

`.video-player-mount:not([data-hydrated])` in `packages/www/src/styles/solution-video.css`
went from the literal `#0b0e14` to `var(--color-bg-light)`. That literal dated from when
the hero band was black and the reserved box disappeared into it; on a light hero it is a
near-black slab, the most visible thing on the page for as long as the dynamic `plyr`
import takes. The token follows the band in both themes, so the reservation is felt as a
shape and not seen as a colour. The 16:9 / 9:16 geometry is untouched.

### 4d. The stale narration

Two sentences in the nav-chrome comment at `main.css:1839` and `:1841`. Both were factually
about a black hero. They are inside a past-tense bug story, so the history is worth keeping;
they now say "over the hero beneath it (black at the time, light since A7 ...)" and "3.51:1
on the then-black hero". No behavioural change.

---

## Gate exit codes

Every one run in this session, after all edits.

| gate | exit |
|---|---|
| `npm run check:ci-dead-css` | **0** - 62 dead classes, baseline 62, no new, none drained |
| `npm run check:ci-css-dom-refs` | **0** - rendered 874, styled 1431, unstyled 31, baseline 31 |
| `npm run check:i18n:components` | **0** - 111 astro + 28 tsx, no hardcoded strings |
| `npm run check:ci-dead-translation-keys` | **0** - 6,925 keys, 1,358 patterns, baseline 192 |
| `npm run check:ci-em-dash-surfaces` | **0** - 990 files, 20 surfaces, 2,714 baselined |
| `npx tsx scripts/check-translation-key-usage.ts` | **0** - 693 keys verified (the opposite direction) |
| `npx tsc --noEmit -p scripts/tsconfig.json` | **0** |
| `npx eslint scripts/check-dead-translation-keys.ts` | **0** |
| `npx biome format` on my five files | **0** |
| `bash .ci/scripts/test/gates/test-shrink-only-composition.sh` | **0** - 16 writers, all guarded |
| `npx tsc --noEmit -p packages/www/tsconfig.json` | pre-existing `window.plausible` errors only, nothing in the files I touched |
| `npm run check:format` (whole tree) | **1**, and NOT mine - see findings below |

Not run, and why: `npm run build` (forbidden this wave, a frozen `dist` is being served on
29304), and therefore also `check:ci-browser-smoke`, `check:ci-landmarks` and
`check:ci-layout-overflow`, which all need a fresh build. My CSS changes are the kind those
three would exercise: **someone with the build must run them before this lands.** The nav
border shifts `--nav-top-offset` by 1px, which is the change most worth a browser look.

---

## Found, not owned

1. **`private/account/scripts/rotation/platforms/cloudflare-token.ts:81-84` fails
   `npm run check:format`.** Biome wants `Promise.all([listAccountTokens(client),
   listUserTokens(client)])` on one line. Pre-existing and committed (`git status` clean on
   that path, last touched by `5f55c91`), inside the forbidden `private/` submodule. It is
   the only remaining `check:format` error in the whole tree; with it fixed that gate is
   green.

2. **`pages.solutionPages.downloadGated.*` - 8 dead leaves x 13 locales.** Detailed under
   defect 3. Needs the catalog owner, then a baseline drain.

3. **`socialProof.impact` carries two rival shapes at once**, nested
   (`impact.before.label`) and flat (`impact.beforeLabel`), and `SPSocialProof.astro:27`
   reads both through `as (ImpactNested & ImpactFlat)`. If #519 is ever honestly revived,
   one of the two shapes should go. Not touched: the component is deliberately retained.

4. **`SPProblem.astro:60-75` documents that `statCallout.ref` is unvalidated** and that
   `scripts/validate-comparison-refs.js` only ever walks `comparison.features`. The comment
   is accurate and the component guards correctly; noting it because a validator that reads
   one of two `ref` surfaces looks like it reads both.

5. **The brief's class name for 4a was wrong** (`.sp-roi-section` for `.sp-cost-section`).
   The defect was real; only the name pointed at a different page. Worth knowing if other
   findings came from the same scan.
