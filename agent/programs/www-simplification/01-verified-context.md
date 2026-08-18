# 01. Verified context

Status: **verified on `main` at 2026-08-18T05:13Z**, commit `8a03fe5ae`.

**RE-VERIFY BEFORE YOU RELY ON ANY LINE HERE.** Every `file:line` is a hypothesis
that was true at the timestamp above. The measurements were first taken on branch
`0815-1` and the load-bearing ones were re-checked on `main` before this file was
written; the rest carry their original date and are labelled.

## What is true right now

- **`packages/www` is untouched.** `git status --porcelain packages/www/` returns
  zero lines. It is also clean at `HEAD`, which means every future diff there is
  yours and `git show HEAD:<file> > <file>` is a precise rollback that cannot
  destroy another session's work.
- The tree is parked on `main`. Modified tracked files include
  `.claude/agents/i18n-guardian.md`, `.claude/commands/handoff.md`,
  `.claude/commands/pr-merge.md`. Cut a fresh `MMDD-N` branch before touching a
  tracked file.

## Re-verified on `main` (these are not from memory)

| Claim | How it was re-checked | Result |
|---|---|---|
| 13 static locale imports drive the bundle | `sed -n '1,13p' src/i18n/utils.ts \| grep -c '^import'` | **13** |
| Locale JSON on disk | `du -sh src/i18n/translations` | **11M** (byte-exact figure from research: 9,284,710 B) |
| The two offending call sites are identical | `sed -n '33p' src/components/MegaMenu.tsx`, `sed -n '145p' src/components/Sidebar.tsx` | both `to(\`pages.solutionPages.${config.contentKey}\`)` |
| `stringToSlug` strips non-ASCII | `sed -n '6,13p' src/utils/slug.ts` | `.replaceAll(/[^\w\s-]/g, '')`, **no `u` flag** |
| The TOC regex discards the id | `sed -n '62p' src/utils/sidebar-behavior.ts` | `/<h([2-6])[^>]*>(.*?)<\/h\1>/gi` |
| No rehype plugins configured | `grep -c rehypePlugins astro.config.mjs` | **0** |
| The form system has no consumers | `grep -rl form-input src/ \| wc -l` | **0 files** |
| Stylesheet sizes | `wc -l` | `pricing-page.css` **2321**, `main.css` **3421** |
| The shadowing token block | `sed -n '279,282p' src/layouts/BaseLayout.astro` | inline `<style>` "Critical CSS Variables" |

## The numbers this program is judged against

Measured 2026-08-17 with a fresh browser session per URL, because a warm cache
silently reports `transferSize: 0`. Re-measure before quoting one as current.

| Metric | Ours | claude.com | anthropic.com |
|---|---|---|---|
| Homepage JS decoded | **6,998,912 B** | 1,267,131 | 305,858 |
| Distinct painted colours | **43** (prod, 2026-08-17) / **39** (fresh build, 2026-08-18) | 19 | 18 |
| Distinct painted font sizes | **23** | 13 | 8 |
| Page height at 390x844 | **11,795 px** | 6,608 | 6,407 |
| Homepage body sections | **9** | 3 | 4 |
| Nav bar targets | **13** | 9 | 7 |
| Mean nav label length | **36.8 ch** | 9.7 ch | short nouns |

**Two dated colour counts, both kept on purpose.** `sx-metrics` measured 43 against
production on 2026-08-17; `w3-tokens` reproduces **39** twice against a fresh build on
2026-08-18, attributing every painted value to its declaring rule with CDP
`getMatchedStylesForNode`. The tree changed between them, so neither supersedes the
other; date any figure you quote. The target of 16 or fewer is unaffected either way.

**Correction to an earlier claim in this programme:** `#7fa03f` IS defined, at
`main.css:183` as `--color-accent-green`. An earlier brief said it was defined in no
`:root`, which was wrong. The real defect is that two homepage components paste the raw
hex instead of using the token.

**Where the residue actually lives, measured not inferred** (`w3-tokens`, CDP attribution):
of 23 font sizes `main.css` + `responsive.css` declare only 7; of 11 radii `main.css`
declares 5; of 6 box-shadows `main.css` declares **zero**, all six sitting in
`solution-pages.css`, `pricing-page.css` and `index.astro` scoped styles. A token wave
confined to `main.css` therefore cannot reach the shadow target at all.

Two page-height conventions exist and must not be averaged: the **scrolled**
figure is the user-facing truth (lazy images resolve late; the homepage reads
6,794 px fresh and 7,697 px after scrolling to the bottom), the **fresh-load**
figure is the byte-accounting truth. State which one you used.


## Wave 2 outcome, corrected 2026-08-18

`w3-tokens` reported 23->20 font sizes, 39->33 colours, 11->10 radii, 6->5 shadows.
**Those figures are one build stale and understate its own result.** Its final census
(`census-AFTER.json`, 09:45) records **17 / 28 / 8 / 3** on `/en` desktop light;
`w4-primitives` reproduced the same four numbers in an independent rig with a
byte-identical value set, and I confirmed them by reading the raw census files rather
than either report:

| metric | reported | ACTUAL (final census) | target |
|---|---:|---:|---:|
| distinct painted font-size | 20 | **17** | 8 |
| distinct painted colours (text u background u border) | 33 | **28** | 16 |
| distinct painted border-radius | 10 | **8** | 3 |
| distinct painted box-shadow | 5 | **3** | 1 |

The stale row came from `census-after.json` at 08:51; a later `build-w4scope` run at
09:39 improved on it and the report was written against the earlier file. **w11 must
compare against 17/28/8/3**, and the lesson generalises: an agent that measures more
than once can file a report against the wrong artifact, so cite the census file and its
timestamp, not just the number.

**Corollary worth remembering:** `w3` kept writing for several minutes AFTER it filed
"done" and told the next wave to start. Treat a completion message as the start of a
tail, not the end of one: re-read a shared file immediately before editing it rather
than trusting a copy read earlier.

**CITATION RESOLVED 2026-08-18.** `w3-tokens` rebuilt a reconstructed w3-only tree at
`<scratchpad>/w3-tokens-rig`, verified to contain zero w4 markers, built clean at 1,814
pages with a 2,424-file payload checked before and after. It reproduces **17 / 28 / 8 / 3**.
These figures are now attributable to w3 alone and are the row w11 compares against.

The earlier provisional note stands as a lesson even though the numbers survived:
matching figures are not evidence that the provenance is sound. A right answer was
recorded against a census from the contaminated window, one paragraph after a warning
about that exact error.

## Structural facts

- 80 components, not the 43 a top-level glob reports; five subdirectories exist.
- 61 page files, 1,015 markdown docs in one flat directory, 13 locales.
- 21 solution pages are byte-identical 16-line wrappers; all variance is in
  `src/config/solution-pages.ts` (515 lines). Each carries 216 to 363 leaf
  translation keys, about 6,600 in `en.json` alone.
- The main stylesheet is **not** in `src/`. `BaseLayout.astro:237-242` links
  `/styles/main.css` and four more from `public/styles/`, three of them via the
  `media="print"` onload trick, so they load on every route.
- `dist/` is 7.1 GB only because `public/assets/{videos,tutorials}` (6.9 GB,
  gitignored) is copied verbatim. A build does not need them: a portable rig
  payload is **112 MB**.

## Hazards that will bite an implementing session

- **`npm run build:www` deletes 14 tracked files.** `astro.config.mjs:26` runs
  `generate-search-index.js`, which resolves output to `packages/www/public/`
  rather than the outDir, `unlink`s every `search-index*.json` at `:82`, then
  rewrites them. All 14 are in `git ls-files`. A `catch {}` means a lost index
  still exits 0. The `mutex: ['www-dist']` that looks like protection is a
  process-local `Set` and holds nothing between two agents.
- **`.astro/` is hardcoded and shared** (`astro/dist/core/config/settings.js:21`),
  so a concurrent build rewrites content modules under a running dev server.
- **Wave 1 removes a safety net.** Deleting a whole locale file is invisible to
  three gates; the TypeScript build is the other backstop, and Wave 1 removes the
  static imports that provide it. Whatever replaces them must keep an equivalent
  hard failure.
- Cold start is about 56 s of content sync, not a hang.

## Instruments that reported success without having run

Each was caught by planting a control. Trust none of them bare.

- `AGENT_BROWSER_SCREENSHOT_DIR` is ignored; a bare filename lands in the working
  directory. It put three untracked PNGs into the repo.
- `agent-browser diff screenshot --output <path>` writes no file. The verdict is
  sound, the image is fiction. Use ImageMagick `compare`.
- `agent-browser errors --clear` does not clear. A sweep reported errors on 47 of
  56 routes; all 47 were one retained error.
- `npm run ci --changed` is a no-op: zero manifest entries declare `paths:`, so it
  runs all 232 gates, about 95 minutes serial.
- An accessibility audit reported `violations: 0` while silently downgrading all
  30 nodes to *incomplete*. Four real contrast failures were then found by hand.
- `querySelectorAll('*')` returns no pseudo-elements, which is why two independent
  overflow hunts reported "no offending elements" while the culprit was an
  `::after`.
