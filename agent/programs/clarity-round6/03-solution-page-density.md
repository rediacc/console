# 03. Solution-page density

Status: **planning**, template layer verified 2026-08-27 by a `www-site` sweep.

## The disease

Four claims, twenty-five statements, 255 atoms, 9.7 screens. Measured on
`infrastructure-costs` and within 3% on two siblings, so it is systemic. Numbers in
`01-verified-context.md`.

`SPHomePage.astro` records that the homepage went from nine sections to five for exactly
this reason. The 21 solution pages never got that pass.

## The enabling fact that makes parallel work safe

**Every heavy sub-block is purely data-gated. There is no template logic to change.**

    SPProblem.astro:56    problem.statCallouts && length > 0
    SPProblem.astro:91    problem.timeline &&
    SPHowItWorks.astro:85/:142/:194   cloneVisual / costVisual / pipelineVisual
    SPBottomCta.astro:64,67           tierBadge, command

Omit `problem.timeline` from a locale subtree and `SPProblem` degrades silently and
correctly. It does not crash. So the three heaviest objects on the page, the stat
callouts, the timeline and the `costVisual` server table, can each be removed from ONE
page by editing only that page's i18n subtree.

**And a whole section is removable per page by config alone.** Proven by precedent, not
inference: `solution-pages.ts:291-304` gives `kubernetes-cluster-mobility` a bespoke
`sections` array omitting `costCalculator` and `socialProof`, with no template change.
17 pages use `ALL_SECTIONS`, 3 use `SECTIONS_NO_COMPARISON`, 1 is bespoke.

### The rule every page agent gets, verbatim

> Remove a WHOLE SECTION via the `sections` array in `src/config/solution-pages.ts`.
> Remove a SUB-BLOCK via the page's i18n subtree.
> Never the reverse.

The reverse crashes the build. These fields are unguarded `.map()` calls and required
props: `SPProblem.astro:48-50`, `SPStatsBar.astro:19`, `SPHowItWorks.astro:69-73`,
`SPTechDiff.astro:47-55`, `SPBenefits.astro:23-26`, `SPComparisonTable.astro:78`,
`SPBottomCta.astro:58-61`.

## What a page agent may touch, and what it may not

**Per-page surface, exactly four things:**

1. the i18n subtree `pages.solutionPages.<contentKey>` in all 13 catalogs
   (`infrastructureCosts` is 230 English leaves)
2. its own contiguous block in `src/config/solution-pages.ts` (about 10 lines per slug)
3. its illustration SVG, resolved BY SLUG GLOB, not by config
   (`src/utils/solution-illustration.ts:10-20`)
4. its calculator function in `cost-presets.ts`

**Blast radius if an agent edits a component instead of data:** every SP section component
is mounted by `PersonaPage.astro:88-140` as well, so a "small fix" in `SPProblem` hits
21 solution pages PLUS 4 persona pages. `SolutionConstellation` additionally hits the
homepage. `solution-pages.css` reaches 21 + 4 personas + 6 resource briefs + the homepage
+ why-now + roi-calculator.

**Two shared strings that look per-page and are not:** `SPDownloadShort.astro:119-131`
and `SPDownloadGated` read `pages.solutionPages.downloadShort.*`, one string serving all
21 pages.

**Two keys that must NOT be deleted even though they live in the page's own subtree:**
`label` and `blurb`. `SolutionConstellation.astro:92-100` reads them for the OTHER slugs,
so deleting them from one page breaks the constellation on the other 20.

## The gate that will not save you

`check:ci-dead-translation-keys` **cannot see an orphaned section.**
`SolutionPage.astro:61` calls `to(\`pages.solutionPages.${config.contentKey}\`)`, and
`contentKey` is unresolvable, so the extractor emits the pattern `pages.solutionPages.*`,
a prefix of every key under every page. Verified against the gate's own exported matcher:

    pages.solutionPages.infrastructureCosts.problem.timeline.oldLabel -> true
    pages.solutionPages.zzzNotAPage.foo.bar                           -> true

The live proof is `socialProof`: still a member of `ALL_SECTIONS` at `:107`, rendered by
nothing since rediacc/console#519, and the gate still reports all 6925 keys reachable.

**Consequence: removing a section from `sections` and leaving its i18n produces roughly
30 to 70 dead keys times 13 locales, and nothing goes red.** Key deletion is a deliberate
step in this plan, not something CI will remind anyone about.

## The 13-locale multiplier, and why writers must be serialised

Deleting `problem` (30 leaves) from one page requires, atomically:

1. the same subtree deleted from all 13 catalogs
2. `.translation-hashes.json` regenerated, ONCE, by ONE owner
3. `.naturalized-hashes.json` (1.7 MB), same single-owner rule
4. `scripts/data/em-dash-surfaces-baseline.json` drained if any deleted key was baselined
   (1527 baselined entries live under `pages.solutionPages.*`; 62 are `infrastructureCosts`)
5. `scripts/data/dead-css-baseline.json` if the section's CSS goes too
6. the `sections` array in `solution-pages.ts`

`check:i18n:completeness` enforces symmetry in both directions: `Missing N keys` if a
locale lags English, and an ORPHAN error at `:760-766` if a key survives in a locale and
not in English. You cannot do 1 file and you cannot do 12.

The prior program already ruled on this shape:
**`packages/www/src/i18n/translations/` is SERIALISED and owned by NOBODY.** A wave
collects its deletions and REPORTS them; the LEAD applies every deletion in one
consolidated pass and runs `i18n:generate-hashes` ONCE, because that script rewrites every
tree and has been observed touching `packages/cli`'s manifest and writing through into
`private/account`.

**Never parse-and-reserialize a catalog. Splice bytes.** The per-page object is contiguous.

## Wave shape, and why Wave 0 exists

The operator asked what must happen before parallel agents start. Three things, and all
three are lead-only:

1. **A frozen static build on a random port, with the pid and the hashed-asset check.**
   `browser-probe.md` records that the dev server does not isolate, one server, one tree,
   HMR; that `packages/www/.astro/` is derived from `config.root` with no override so ANY
   build rewrites the cache every running dev server reads; and that a session once
   measured a docs grid that came entirely from another agent's stale snapshot on a port
   its own server never bound. Parallel measuring agents against a dev server produce
   numbers that silently change under them.
2. **A page probe with a FLOOR.** Exit non-zero under about 50 painted elements or DOM
   nodes, or when expected resource types are absent. A driver pointed at a wiped `dist`
   returned `success: true, domNodes: 5` and nothing failed.
3. **The template contract**, i.e. this document's rule box plus the per-page file
   ownership table, written into every page agent's prompt verbatim.

Only after those three do the page agents run. They are READ-and-PROPOSE agents: each
measures its page against the frozen build, decides its cuts, and emits a per-page splice
plus a `sections` diff into `reports/`. They do not write to the catalogs.

## Per-page treatment, not a blanket rule

The operator asked for special treatment per page, and the data supports it: the section
mix differs (17 ALL_SECTIONS, 3 no-comparison, 1 bespoke), the calculator presets differ,
and the comparison tables differ.

What is likely common across most pages, to be confirmed per page rather than assumed:

- the `sp-stats` bar, which on `infrastructure-costs` restates the chips about 100px above it
- the repeated timeline chevrons, three of five carrying one identical sentence
- the `costVisual` invented-server table, 62 atoms for one idea, and it prints raw
  `BTRFS COW` on a page whose prose deliberately avoids that jargon
- `techDiff` rows that duplicate each other
- the cost calculator, an interactive island 1092px tall, a candidate for demotion
- **`howItWorks` as a WHOLE SECTION (decision A5).** The operator ruled this a density
  question rather than a phrasing one: the site's 17 "One command." headlines are NOT
  rewritten, because an English value change on 17 pages trips `check:i18n:hashes` and
  forces a 12-locale re-naturalization for no reader gain. Instead each page agent
  evaluates dropping `howItWorks` entirely via its `sections` array. On
  `infrastructure-costs` it is 966px and 62 atoms, the densest section on the page, and
  most of that mass is the invented-server `costVisual` table printing raw `BTRFS COW`.

**`references` is 160 words of the 944 on `infrastructure-costs`** and is already a
`<details>`. Check whether it renders open before touching it.

## Replacing tables with pictures, under the locked constraint

I1 is absolute: **illustrations carry no text at all.** So a picture replacing the
`costVisual` table or the `techDiff` table must carry its meaning in shape, with any
load-bearing label living in the surrounding HTML through the normal key path, kept rare.

This is also why the resvg font trap does not apply: a textless SVG needs no font, and the
rehype sentence-wrap pass already skips any subtree under `svg` (I18).

`illustration_pipeline` is the existing generator: `source -> brief -> brief_quality ->
draw -> render -> visual_qa -> verify -> apply`, and it produced the 22 line-art SVGs on
the pages today. Two gaps to close before using it here: every agent step is `opus`, not
sonnet, and it produces ONE illustration per slug, while this work wants several per page.

## Two findings from the sweep, neither asked for

**F1. Dead config.** `SolutionPageConfig.illustration` (`solution-pages.ts:80`) and
`illustrationMobile` (`:82`) are written 21 times and read nowhere. `SolutionPage.astro:114`
passes `slug`, and `SPProblem.astro:43` globs by slug. Consequence:
`instant-recovery.mobile.svg` (`solution-pages.ts:19,176`) has never rendered.

**F2. `/en/solutions/instant-recovery` is hardcoded into `check:ci-browser-smoke`**
(`scripts/check-browser-smoke.ts:39-45`), asserting zero console errors on a real Chromium
every run. If that page is simplified, this gate drives it on every CI run, which is free
coverage and also a tripwire.
