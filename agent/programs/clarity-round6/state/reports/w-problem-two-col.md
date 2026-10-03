# w-problem-two-col

Two-column PROBLEM section on solution and persona pages.

Files changed (the two I own, nothing else):

- `/home/developer/console/packages/www/src/components/solution-pages/SPProblem.astro`
- `/home/developer/console/packages/www/src/styles/solution-pages.css` (the `.sp-problem*` rules only)

## The layout

`.sp-problem-inner` becomes a two-track CSS grid, but ONLY when a slug actually
resolved to an illustration. `SPProblem.astro` emits
`class:list={['sp-problem-inner', illustrationSvg && 'sp-problem-split']}`, so with no
drawing there is no second column to make and the container stays the plain 720px prose
block it has always been. Verified against Astro's own runtime, not reasoned about:
`addAttribute(['sp-problem-inner', null], 'class:list')` returns
`class="sp-problem-inner"` and the truthy form returns
`class="sp-problem-inner sp-problem-split"`.

The tracks are the house pattern from `.sp-hero-split` in the same stylesheet, copied
rather than invented: `minmax(0, 32rem) minmax(0, 36rem)`, `column-gap: 48px`,
`justify-content: center`, `align-items: center`, capped at `max-width: 1136px`
(32rem + 48 + 36rem). That cap is not arbitrary. On `/en/solutions/encryption` the hero
band's own content box measures 1136px wide with its left edge at x=145, and the problem
band now lands on exactly the same edge, so the two bands line up down the page.

`align-items: center` gives the requested vertical centring between the copy and the
drawing.

## RTL

No physical `left`/`right` anywhere in the new rules. DOM order is text-then-illustration
and grid places the first child on the inline-START edge, which is the same reason
`.sp-hero-split` orders itself text-then-video. Grid line numbers follow the writing mode,
so `grid-column: 1 / -1` on the timeline mirrors too.

Measured on `/ar/solutions/migration-safety` at 1440 (`dir="rtl"`):

| box | left edge |
|---|---|
| `.sp-problem-illustration` | 145 |
| `.sp-problem-text` | 769 |
| `.sp-timeline-contrast` | right edge 1281, left 581 (700px cap on the inline-start side) |

Copy right, drawing left, timeline anchored to the inline-start edge. `scrollWidth -
innerWidth` is -15 on `/ar`, the same as `/en`, so no horizontal scroll was introduced.

The removed break-out actually deletes an old RTL hazard: `.sp-problem-illustration` used
to be `width: min(1100px, 100vw - 96px)` with a negative
`margin-inline-start: calc((var(--sp-content-max) - ...) / 2)` to escape the 720px prose
column. That whole mechanism is gone; the width now comes from the grid track.

## The 900px collapse

`@media (max-width: 900px)` flips `grid-template-columns` to `minmax(0, 1fr)` and drops
`row-gap` to 32px, matching `.sp-hero-split`'s existing breakpoint rather than adding a
new one. The DOM order survives the collapse, so mobile leads with the TITLE and the
drawing sits under the copy it illustrates. The illustration is capped at
`max-width: 36rem` there so it cannot tower over the copy, and stays on the inline-start
edge because the copy above it is start-aligned in both directions.

The old `@media (max-width: 768px) { .sp-problem-illustration { width: 100%;
margin-inline: 0 } }` was deleted: it existed only to undo the break-out, which no longer
exists.

Swept across the boundary on `/en/solutions/migration-safety`, all with zero horizontal
overflow:

| viewport | text col | illus col | two columns? |
|---|---|---|---|
| 1024 | 433 | 433 | yes |
| 950 | 396 | 396 | yes |
| 901 | 371 | 371 | yes |
| 899 | 788 | 576 | no, collapsed |
| 768 | 705 | 576 | no |
| 430 | 367 | 367 | no |

Worth knowing rather than fixing: between 900 and 1136 the two `minmax(0, Xrem)` tracks
shrink to EQUAL widths, not to the 32:36 ratio. `.sp-hero-split` has had exactly this
behaviour since it shipped. At the tightest two-column point (901px) the prose column is
371px, which is wider than the 327px it gets on a 390px phone, so nothing is cramped that
is not already accepted elsewhere.

## Where the sub-blocks landed

**`statCallouts` moved INSIDE the text column.** They are short chips that restate the
prose claim, so they read as part of the copy, and keeping them in the column is what
makes the two column heights comparable, which is what makes the vertical centring look
deliberate instead of accidental. On encryption at 1440 the text column measures 498px
against the drawing's 324px with the callouts present; strip them and it is 308px against
324px, which is very nearly a dead heat.

**`timeline` spans BOTH tracks, underneath.** It is a horizontal band by design, a row of
connected steps with arrowhead joints capped at 700px, and half a column crushes it. It
gets `grid-column: 1 / -1` and `margin-top: 0`, because `row-gap: 48px` now supplies the
separation its standalone 48px margin used to and the two would otherwise compound.

Both absent-cases were driven, not reasoned about. Callouts absent (simulated on
encryption, since no page in `en.json` ships without them yet) gives a 516px section with
the two columns near-balanced and nothing looking orphaned. Timeline absent is the live
encryption case below.

## Heights, before and after

`/en/solutions/encryption` (callouts, no timeline):

| viewport | before | after | change |
|---|---|---|---|
| 1440 | 1318 px | 690 px | -48% |
| 390 | 934 px | 926 px | -1% |

`/en/solutions/migration-safety` (callouts AND timeline):

| viewport | before | after | change |
|---|---|---|---|
| 1440 | 1622 px | 1037 px | -36% |
| 390 | 1355 px | 1331 px | -2% |

`/ar/solutions/migration-safety` at 1440: 1551 px before, 966 px after, -38%.

Callouts-absent variant of encryption at 1440: 516 px.

Mobile barely moves, which is correct: it was already a single column, and the only real
change there is the drawing losing its 40px top margin and its `max-width` cap. The
section was never the mobile problem; it was the desktop one.

## How this was verified

A full `npm run build` was deliberately NOT run, and this is stated rather than buried: a
peer agent is live in `SPHomePage.astro` and `PricingPreview.astro` in this same
`packages/www`, and a build would both compile their half-finished edits and unlink the 14
tracked `search-index*.json` files out of `packages/www/public/`. `ps -eo args | grep -c
'[a]stro build'` returned 0 before I started, and I left it that way.

Instead the frozen `packages/www/dist` (built 17:44 today, and current: it already has the
density pass's timeline removals) was served on a local port and driven with
agent-browser, with the change applied to the live document: the exact CSS text I wrote
injected as a stylesheet, and the DOM restructured to the exact shape the component now
emits. The three things that could have made that a fiction were each checked against the
real tooling rather than assumed:

1. `@astrojs/compiler` `transform()` on the edited `SPProblem.astro`: zero diagnostics,
   and the emitted code is
   `<div${$$addAttribute(['sp-problem-inner', illustrationSvg && 'sp-problem-split'], "class:list")}>`
   with the JSX comment emitting nothing.
2. Astro's real `addAttribute` for both branches of `class:list` (above).
3. `esbuild` parse of the edited `solution-pages.css`: 0 errors, 0 warnings, 47,386 bytes
   out, so the new rules cannot have broken the sheet.

Screenshots (looked at, not just captured) are in
`/home/developer/.claude/projects/-home-developer-console/programs/clarity-round6/checkpoints/w-problem-two-col/`:
`before-encryption-1440.png`, `after-encryption-1440.png`, `after-encryption-390.png`,
`after-migration-1440.png`, `after-migration-390.png`, `after-ar-migration-1440.png`,
`after-nocallouts-1440.png`.

The before shot is the case for the change on its own: roughly 200px of empty band between
the description and the drawing, the drawing 1100px wide with most of that width being its
own internal margins, then another gap before the callouts.

## Gates

| gate | exit |
|---|---|
| `npm run check:ci-dead-css` | **0** (62 dead classes, baseline 62, unchanged) |
| `npm run check:ci-css-dom-refs` | **0** (rendered 873, unstyled 31, baseline 31, unchanged) |
| `npm run check:i18n:components` | **0** (no hardcoded strings; no markup TEXT changed, only structure) |
| `npm run check:ci-layout-overflow` | **0** (no overflow cause shapes in 2085 blocks) |
| `npx biome format` on both files | **0** |

Neither shrink-only baseline moved, so nothing needs draining. `.sp-problem-split` and
`.sp-problem-text` are new class names that both gates see as alive: dead-css finds them
named in `SPProblem.astro`, and css-dom-refs finds them styled.

## Found, not owned

Six things, none touched.

1. **`agent-browser open --viewport WxH` is silently ignored.** In a fresh session,
   `agent-browser open <url> --viewport 1440x900` followed by
   `eval "JSON.stringify({w:window.innerWidth,h:window.innerHeight})"` returns
   `{"w":1280,"h":577}`. Only `agent-browser set viewport 1440 900` actually resizes. This
   matters beyond my session: `/home/developer/console/packages/www/scripts/measure-page-density.sh`
   passes `--viewport 1280x900` on every `open`, so every number that harness has ever
   produced was measured at **1280x577**, and its `screens` column divides `scrollHeight`
   by a 900 that was never the viewport height. My first baseline pass hit this and
   returned byte-identical heights at 1440 and 390, which is what exposed it. One-line fix:
   add `agent-browser set viewport 1280 900` after the `open` in `measure()`.
2. **The pre-bash guard blocks correct commands.**
   `.claude/hooks/pre-bash/block-agent-browser-repo-output.sh` refuses a compound bash
   command that contains `agent-browser screenshot /absolute/path.png` when the same
   command also contains other `agent-browser` subcommands (`open`, `set viewport`,
   `eval`), reporting "No absolute output path" even though the screenshot path is
   absolute. Splitting the screenshot into its own Bash call succeeds immediately. It
   appears to judge the first or every `agent-browser` occurrence rather than the
   `screenshot` one. Cost roughly four extra round trips per shot.
3. **Three genuinely dead rules sit in the block I edited** and I left them alone rather
   than orphan a baselined finding: `.sp-problem-illustration img`,
   `.sp-problem-illustration picture` and `button.sp-illustration-trigger` in
   `solution-pages.css`. `SPProblem` inlines the SVG with `set:html`, so there is no `<img>`
   and no `<picture>`, and `sp-illustration-trigger` appears nowhere under
   `packages/www/src`. Draining them needs a `--write-baseline` pass on `check:ci-dead-css`,
   which is an owner's job, not a side effect of mine.
4. **Arabic stat-callout numbers are mangled in the catalog.** On the UNMODIFIED
   `/ar/solutions/migration-safety`, `.sp-stat-callout-number` renders `.88M` and `0K–00K`
   where English has `$4.88M` and `$90K–$300K`; the currency symbol and leading digits are
   missing from the value itself, not clipped by CSS (`scrollWidth === clientWidth` on both).
   Pre-existing, verified before my change. i18n catalogs are outside my ownership.
5. **RTL timeline arrowheads point the wrong way.**
   `.sp-timeline-old-step:not(:last-child)::after` uses physical `right: -1px` and
   `border-left`, so on `/ar` the joints sit on the wrong edge and point against the reading
   direction. Visible in `after-ar-migration-1440.png`. Not a `.sp-problem*` rule, so not mine.
6. **`solution-pages.css` already carried a large uncommitted diff when I arrived** (the A7
   light-band work: `--sp-bg-hero` to `--color-bg-band`, `--sp-text-white` to
   `--color-heading`/`--color-on-brand`, the benefits accent band). My three edits were
   exact-match replacements asserted to hit exactly one site each, and the file's mtime
   confirms nothing overwrote them afterwards, but whoever reviews the diff should know that
   most of it is not mine.
