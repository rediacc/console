## SESSION f88f9be7 2026-08-31T16:39:05Z

Executing `/home/developer/.claude/plans/let-s-make-comprehensive-plan-luminous-sparrow.md`:
a comprehension big-bang on the 21 solution + 4 persona pages in `packages/www`.
Goal: 8.7 screens -> ~4, and a CTA in the first viewport.

## Next action

W2, the disclosure conversions, which is the only workstream that still moves the
screen-count number. Convert in this order, by what the component already is:
`SPCostCalculator` (React island, 1,150px, the single largest object on the page) behind
`components/Overlay.tsx`; `SPTechDiff` and `SPComparisonTable` (both Astro, static) behind
native `popover="auto"`, copying `SolutionConstellation.astro:289` which already does this
on the same page and degrades without JS. Each collapsed section leaves a trigger card:
heading, one line, headline number, and a ~120px textless thumbnail (that thumbnail is W5,
hand-authored - the private illustration_pipeline CANNOT be used, see the plan's W5).
Do NOT add React to a static section just to get a dialog.

After converting, re-run `npx tsx scripts/check-page-density.ts --selftest` (needs a built
dist) and confirm the page-height target; the gate already asserts CTA/dead-space/columns.

## Landed and gate-verified this session

W1 and W3 are COMPLETE.
- Hero CTA on all 25 pages via an optional `cta` prop on SPHero, rendered through the
  existing `AccountLink.astro`. Always -> ACCOUNT_PATH; the bottom CTA keeps its category
  routing. First-CTA depth moved 84-91% -> 5-9%. `for-ctos` has a self-serve path at last.
- 25 per-page action labels ("Start cloning", "Start cutting TCO"), all 13 catalogs.
- Five defects fixed: captcha dead end (6 forms onto a new `src/hooks/useCaptchaGuard.ts`),
  techDiff column labels, Plyr `ratio` (397px dead black -> 0), collapsed-nav breadcrumb,
  comparison-table scroll wrapper + sticky column.
- NEW GATE `check:ci-page-density` (scripts/check-page-density.ts, runner
  .ci/scripts/quality/page-density.sh, wired at package.json:182 /
  manifest.ts:2499 / ci-quality.yml:1570). Verified IN the ci-runner plan via
  `run.ts --list`. Against the pre-fix dist it reproduced all three defects; against the
  rebuilt dist EXIT=0 over 12 page/viewport pairs, 5 controls firing.
- Extracted `scripts/lib/serve-dist.ts`; check-browser-smoke.ts:103 now uses it and still
  passes 6 routes.

Gates green: dead-css (62/62, not grown), css-dom-refs (31/31, not grown), landmarks,
hydration-clean, layout-overflow, browser-smoke, page-density, ci-parity,
gate-reachability, i18n completeness + key-usage + em-dash, sentence-wrapping (9/9).

## In flight

`- [>]` #7cbd0f40, worker a8e18b51c73b33df7, until 17:08Z: collapsing
`captchaUnavailable` from two sentences to one in the 12 non-English catalogs. English was
already collapsed ("Verification could not load: check your connection or any ad blocker.")
because check:ci-sentence-wrapping caught it in 5 .tsx files. **The gate scans English
only, so it cannot see the locale half** - that is why this is tracked rather than assumed
done. Agent owns the 12 locale files ONLY; en.json is mine.

## Volatile state

- A fresh `packages/www/dist` EXISTS (1814 pages, built 18:28). The page-density gate needs
  it. My dev server on :4399 is STOPPED - restart it if you need one.
- `npx playwright install chromium` was run, so both browser gates run locally without
  Docker via `REDIACC_SMOKE_NO_DOCKER=1`.
- Peer session still owns SPHero.astro / PersonaPage.astro / SPHomePage.astro /
  SPHomeVideo.astro / persona-pages.ts. I have edited SPHero and PersonaPage additively;
  their video wiring is intact and must stay so.
