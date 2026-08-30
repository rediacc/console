# PLAN: fix tutorial-player release gate — rewrite it for TutorialVideoPlayer, not TerminalPlayer
Status: done

## Implementation notes (2026-08-28, post-plan)

The rewrite followed the plan's selector mapping closely, with two additions the
plan's investigation (necessarily static) could not have caught:

1. **Untrusted clicks silently fail autoplay/fullscreen.** `evalInPage(...).click()`
   dispatches a programmatic click, which Chrome's autoplay and Fullscreen-API
   gesture requirements correctly refuse to honor -- `video.play()` and
   `element.requestFullscreen()` both no-op under it. Verified live: the same
   button, clicked via `agent-browser`'s native `click <selector>` command (a real
   trusted input event) instead of eval, worked immediately (`currentTime`
   advanced within 1.5s). All scenario clicks now go through a `clickSelector()`
   helper backed by the native command.
2. **The dev server was orphaned on every run, including passing ones.**
   `npm run dev` spawns `astro` as a grandchild; killing just the `npm` PID
   doesn't propagate to it, and the original safety-net SIGKILL timer never got
   to fire because `proc`'s own 'exit' event (which npm reaches quickly) resolved
   `stopDevServer()` before `main()`'s `process.exit()` tore down the timer.
   Fixed with `detached: true` + an unconditional group-wide SIGKILL after a
   grace window, rather than one that fires only if the npm wrapper hasn't
   already exited.
3. Scenario 5's caption z-index comparison (docs vs. a solution-page mount) was
   also wrong as initially written: solution videos have no `words` manifest
   entry (captions are burned into the pixels), so `.tvp-caption` never renders
   there by design. Fixed to assert only the invariant that actually holds
   (both mounts render a real player; the docs caption's z-index matches the
   CSS-defined value) rather than a cross-mount equality that fails by design.

Control-first verified per the plan's instruction: reverted `clickSelector` to
the broken eval-click shape, confirmed the gate correctly fails with the exact
original symptom, then restored and confirmed green again.

Final state: `npm run test:tutorial-player -w @rediacc/www` passes cleanly
(exit 0, all 5 scenarios), reproduced across 3 consecutive runs, zero orphaned
processes left behind on any of them.
Owner: e580532b
Updated: 2026-08-28

## TL;DR

The gate (`packages/www/scripts/test-tutorial-player-release-gate.js`) tests a
`TerminalPlayer.tsx`-based UI (`window.__tutorialDebug`, `data-guided-phase`,
`.ap-control-bar`, a custom fullscreen caption layer, a "fake terminal" on the
homepage) that was deleted wholesale by commit `80a000965` ("feat: solution-page
asset pipelines, repo cat/backup CLI work, tutorial recording, i18n sync (#492)",
2026-05-27) and replaced by `TutorialVideoPlayer.tsx`, a Plyr-based `<video>`
player. This is not a runtime regression -- it's a gate that never got updated
because it was never wired into CI (per the comment already in
`scripts/ci-runner/manifest.ts:404-408`) until this session. The fix is a
targeted rewrite of the gate's 5 scenarios against the real current player,
selectors, and routes -- not a debugging session against the product.

## Root cause

1. `b1d40b6d4` ("feat(www): ship guided tutorial player...", 2026-03-05) added
   `TerminalPlayer.tsx` + `terminal-player-shell.tsx` + `terminal-player-audio.tsx`
   + `terminal-player-utils.ts` and, in the same commit, the release gate script
   this plan is fixing (`443` lines at HEAD then). `window.__tutorialDebug`
   (with `.phase`/`.step`/`.seekToSec` and friends, matching exactly what the
   gate expects) was real, working code in `TerminalPlayer.tsx` at this point
   (confirmed via `git show b1d40b6d4:packages/www/src/components/TerminalPlayer.tsx`
   and `git show 80a000965^:packages/www/src/components/TerminalPlayer.tsx`,
   lines 374-392) -- the gate was not asserting on an interface that was never
   implemented; it was asserting on one that was implemented and later deleted.
2. `80a000965` (2026-05-27) deleted all four `TerminalPlayer*` files (see
   `git log --oneline --all --diff-filter=D -- packages/www/src/components/TerminalPlayer.tsx`)
   and `FeatureShowcase.tsx` (the homepage component that hosted the terminal
   player), and added `TutorialVideoPlayer.tsx` as a new file in the same
   commit. It did **not** touch `test-tutorial-player-release-gate.js`.
3. Per `scripts/ci-runner/manifest.ts:404-408`, the `check:test:tutorial-player`
   gate "was defined in package.json but referenced nowhere: never ran in CI"
   until it was wired in this session alongside the astro-boot-timeout and
   dead-server-detection fixes. So the 3-month drift between `80a000965` and now
   was never caught -- there was no CI job to catch it.
4. Every one of the 16 current failures traces 1:1 to a selector/state/route
   invariant that belonged to the deleted `TerminalPlayer` and no longer exists
   in `TutorialVideoPlayer`:
   - `window.__tutorialDebug`, `data-guided-phase`, `data-guided-step`: existed
     in `TerminalPlayer.tsx` (confirmed via
     `git show 80a000965^:packages/www/src/components/TerminalPlayer.tsx`,
     lines 378-396 for `__tutorialDebug`, line 443 for
     `terminal-player-caption-layer`); grep for all of these across
     `packages/www/src` today returns zero hits.
   - `.ap-control-bar .terminal-player-guided-toggle`,
     `.ap-control-bar .ap-fullscreen-button`: same -- gone with `TerminalPlayer`.
     `TutorialVideoPlayer.tsx:361-376` uses Plyr's own control list
     (`play-large`, `play`, ..., `fullscreen`), which renders standard
     `[data-plyr="play"]` / `[data-plyr="fullscreen"]` buttons under
     `.plyr__controls`, not `.ap-control-bar`.
   - `.terminal-tutorial`: gone. Current player root is
     `.tvp-shell` > `.tvp-root` (`TutorialVideoPlayer.tsx:676,691`).
   - `.terminal-player-caption-layer--fullscreen`: gone. Current caption element
     is `.tvp-caption` (`TutorialVideoPlayer.tsx:722`), a single element that is
     *repositioned* via CSS in fullscreen
     (`packages/www/src/styles/tutorial-video.css:81-85`,
     `.plyr--fullscreen-active .tvp-caption` / `.plyr:fullscreen .tvp-caption`),
     not swapped for a second element.
   - `.heading-share`: does not exist anywhere in `packages/www/src` any more
     (`grep -rn "heading-share" packages/www/src` → no hits). The z-index
     "player above heading-share" invariant belongs to a layout that's gone.
   - "home page terminal tutorial not found": the homepage
     (`packages/www/src/pages/[lang]/index.astro` -> `SPHomePage.astro` ->
     `SPHomeHero.astro`) never mounts `tutorial-video-hydrate.ts` and has no
     player. `SPHomeHero.astro:8-18` documents this as a deliberate,
     operator-approved removal: *"the fake terminal, the largest object above
     the fold... failed contrast... shipped a disclaimer apologising for being
     simulated. Neither reference site puts a simulated artifact in its hero."*
     `FeatureShowcase.tsx` (the old host of the homepage terminal player) was
     deleted in `80a000965` and is unused everywhere today. This scenario's
     premise is simply false now, by design.

## What the current player actually looks like (verified against HEAD)

- Docs pages embed the player via `![alt](/assets/tutorials/<slug>.cast)` markdown
  image syntax (e.g. `packages/www/src/content/docs/en/tutorial-production-mode.mdx:15`,
  `.../tutorial-add-server.mdx:15`), transformed at build time by
  `packages/www/src/plugins/remark-tutorial-embed.ts:127-141` into
  `<div class="tutorial-video-container" data-video-src=... data-poster-src=...
  data-sources='...' data-lang="en"></div>`.
- Client-side, `packages/www/src/scripts/tutorial-video-hydrate.ts:23-74` finds
  every `.tutorial-video-container[data-video-src]` (docs pages, wired at
  `packages/www/src/layouts/DocsLayout.astro:895`) and `.video-player-mount[data-video-src]`
  (solution-page heroes, `SPSolutionVideo.astro:51`, wired at
  `packages/www/src/components/solution-pages/SolutionPage.astro:206`), sets
  `el.dataset.hydrated = 'true'`, and mounts a React root rendering
  `TutorialVideoPlayer`.
- `TutorialVideoPlayer.tsx:676-731` renders:
  `.tvp-shell > .tvp-root > (<video> + .tvp-chapter-overlay + .tvp-caption
  [+ .tvp-toolbar-overlay if a language picker is needed])`.
  Plyr wraps the `<video>` in its own `.plyr` / `.plyr__video-wrapper` container
  and toggles `.plyr--playing` / `.plyr--paused` / `.plyr--fullscreen-active` on
  itself; standard buttons carry `data-plyr="play"` / `data-plyr="fullscreen"`
  (`TutorialVideoPlayer.tsx:361-376`).
- There is **no debug hook and no phase/step state machine** in the current
  player. "Steps" now live purely as static prose/commands rendered by
  `packages/www/src/components/tutorial/TutorialStep.astro`, sourced from
  `tutorial-storyboard`/`tutorial-transcripts` JSON, entirely decoupled from
  video playback position. There is no `window.*` API to assert against; the
  new gate has to assert on real `<video>` element state
  (`video.paused`, `video.currentTime`, `video.duration`) and Plyr's own CSS
  state classes, read via `document.querySelector('.tvp-root video')` /
  `.closest('.plyr')`.

## Fix plan (rewrite `test-tutorial-player-release-gate.js`)

The two infra fixes from this session (astro cold-boot timeout, dead-server
detection) are correct and should stay untouched. All 5 scenario functions
(lines 292-460 of the current file) need a targeted rewrite against the real
player. No change is needed to `startDevServer`/`stopDevServer`/`main`/the
resource-pressure diagnostics.

1. **`clickPlaybackButton` / `currentState` helpers (lines 239-269)**
   - Replace the `.ap-control-bar .terminal-player-guided-toggle` /
     `.terminal-tutorial` selectors with:
     - locate the player root: `document.querySelector('.tvp-root')` (wait for
       `.tutorial-video-container[data-hydrated="true"] .tvp-root` first, since
       hydration is async -- `tutorial-video-hydrate.ts:33-34` sets
       `data-hydrated` synchronously but the React render + Plyr construction
       inside `TutorialVideoPlayer.tsx:361` runs after).
     - the playback toggle is Plyr's own big/small play button:
       `.tvp-root .plyr__control[data-plyr="play"]` (there are two matches --
       `play-large` and the controls-bar `play`; either is clickable and both
       toggle the same `<video>`).
     - state should be read off the real `<video>` element
       (`.tvp-root video`): `{ paused: video.paused, currentTime: video.currentTime,
       ended: video.ended }`, plus the Plyr root's state class
       (`video.closest('.plyr')?.classList.contains('plyr--playing')`) as a
       cross-check that Plyr's UI agrees with the media element.
   - `isPlayingPhase(phase)` (line 136) goes away; replace with a boolean
     `isPlaying(state)` that checks `!state.paused && !state.ended`.

2. **`scenarioBasicPlayPauseResume` (lines 292-322)**
   - Same play -> assert playing -> pause -> assert paused -> assert stable ->
     resume -> assert playing shape, but against `video.paused` /
     `plyr--playing` instead of `phase`/`step`. Drop the `buttonLabel`
     assertion (Plyr's aria-label toggles internally; if kept, read it off
     `.tvp-root .plyr__control[data-plyr="play"]` -- Plyr sets
     `aria-label="Pause, {title}"` style strings that are internal/i18n-driven
     and not worth pinning exactly).

3. **`scenarioBurstToggle` (lines 324-346)**
   - Keep the "rapid toggles must not wedge the player" intent (still a real,
     useful invariant against a native `<video>` + Plyr). Adapt
     `burstPlaybackClicks` to click `.tvp-root .plyr__control[data-plyr="play"]`
     and `sampledStates` to sample `{ t, paused: video.paused, currentTime:
     video.currentTime }`. Replace `allNarratingStep0` (a phase-machine concept)
     with a check that `currentTime` is advancing at least once across the
     sample window once the burst settles (i.e., the player isn't stuck at
     `currentTime === 0` with `paused === false`, which would indicate a
     wedged play() promise race -- the real analog of the old "stuck at
     step 0" bug this scenario was designed to catch).

4. **`scenarioSeekNoSnapback` (lines 348-377)**
   - `window.__tutorialDebug.seekToSec` has no replacement API. Rewrite to seek
     the real media element directly:
     `evalInPage('(() => { const v = document.querySelector(".tvp-root video");
     v.currentTime = 48; return v.currentTime; })()')`, or drive it through the
     product's own seek UI by clicking a `.tvp-chapter-tick` inside
     `.tvp-chapter-overlay` (`TutorialVideoPlayer.tsx:719`,
     `paintChapterOverlay` in the same file builds these ticks from the
     `<track kind="chapters">`) if the chapters track for
     `tutorial-add-server` has cues past the 48s mark -- check
     `public/assets/tutorials/video/en/tutorial-add-server.en.chapters.vtt`
     before committing to this path, since a *direct* `currentTime` write
     doesn't exercise the UI at all and a chapter-tick click is the more
     faithful regression check.
   - Replace `firstHigh`/`snapback` (step-index concepts) with sampling
     `video.currentTime` after the seek and asserting it (a) lands near 48s
     immediately and (b) never drops back below ~47s in the following sample
     window (the real analog of "seek did not snap back").

5. **`scenarioFullscreenAndLayering` (lines 379-424)**
   - Fullscreen button: `.tvp-root .plyr__control[data-plyr="fullscreen"]`
     (not `.ap-control-bar .ap-fullscreen-button`).
   - `document.fullscreenElement` assertion stays valid as-is (native
     Fullscreen API, Plyr just toggles it on `.plyr`).
   - `.terminal-player-caption-layer--fullscreen` has no replacement element.
     Replace with an assertion that `.tvp-caption` is still present after
     entering fullscreen (`document.querySelector('.tvp-root .tvp-caption')`)
     and, if a caption cue is active during the fullscreen window, that it
     carries `.is-visible` (`tutorial-video.css:67-74`).
   - Drop the `docsZ`/`.heading-share` comparison entirely -- that element does
     not exist in the current site (`grep -rn "heading-share"
     packages/www/src` -> no hits) and the "player above the share button"
     invariant belongs to a layout `80a000965`-or-earlier removed. If a
     replacement in-player stacking invariant is wanted, the closest current
     analog is `.tvp-caption` (`z-index: 3`,
     `tutorial-video.css:63`) sitting above `.tvp-chapter-overlay`
     (`z-index: 4`... note this is *lower* numerically but *earlier* in DOM
     order under `.plyr__progress`, i.e. they don't actually overlap in
     practice) -- recommend simply dropping this half of the scenario rather
     than inventing a new invariant nobody asked for; note the gap in the
     scenario's docstring/log line instead.

6. **`scenarioHomeConsistency` (lines 426-460)**
   - The homepage genuinely has no tutorial/video player any more, by
     deliberate design (`SPHomeHero.astro:8-18`). `assertCondition(home.hasPlayer, ...)`
     can never pass again and should not be resurrected against `/en`.
   - Replace the *intent* (two independent mount paths for the same player
     component should render it consistently) with a route pair that still
     exists: docs (`/en/docs/tutorial-production-mode`, mounted via
     `.tutorial-video-container` in `DocsLayout.astro:895`) vs. a solution page
     (`/en/solutions/rapid-recovery`, mounted via `.video-player-mount` in
     `SolutionPage.astro:206` / `SPSolutionVideo.astro:51`). Assert both routes
     produce a `.tvp-root` with a real `<video src>`, and that the two mounts'
     `.tvp-caption` (`getComputedStyle(...).zIndex`) values match, since both
     go through the exact same `TutorialVideoPlayer` component and any
     divergence would indicate real per-route CSS drift.
   - Alternative if a same-component-different-route comparison is judged not
     valuable enough to keep: retire this scenario outright and say so
     explicitly in the gate's summary output, rather than leaving a
     permanently-red assertion in the file. This needs a one-line sign-off
     from whoever owns the www/marketing surface, since it's a product-scope
     call, not a technical one.

## Verification

- Primary: re-run the release gate itself after each scenario is rewritten --
  `npm run check:test:tutorial-player` (root) /
  `npm run test:tutorial-player -w @rediacc/www`, which is exactly
  `node packages/www/scripts/test-tutorial-player-release-gate.js` per
  `packages/www/package.json:15` and `package.json:228`. This is the existing
  regression instrument (`scripts/ci-runner/manifest.ts:404-419`, gate
  `check:test:tutorial-player`, CI step "Tutorial player release gate" in
  `.github/workflows/ci-quality.yml` job `quality-packages`) and needs no new
  wiring -- it only needs to go green against the real player.
- Per the `testing` skill's "control first / plant the defect" rule: before
  calling any rewritten scenario done, deliberately break the corresponding
  real behavior (e.g., temporarily comment out the `play` click handler wiring,
  or force `video.currentTime` to snap back after a seek) and confirm the
  scenario goes red for the right reason, then revert and confirm it's green
  again. This is cheap here because the whole point of the gate is driving a
  real browser against real product code -- there's no mock to keep honest.
- Secondary/regression-of-the-regression: after the rewrite, grep the finished
  script for the retired vocabulary (`__tutorialDebug`, `guidedPhase`,
  `ap-control-bar`, `terminal-tutorial`, `heading-share`) to confirm no stale
  selector survived a partial edit:
  `grep -nE "__tutorialDebug|guidedPhase|ap-control-bar|terminal-tutorial|heading-share" packages/www/scripts/test-tutorial-player-release-gate.js`
  should return nothing.
- No new test *file* is warranted: this gate is already the correct
  ci-quality.yml-wired regression instrument for "does the tutorial video
  player actually work in a real browser," per the `testing` skill's routing
  table (real-browser/runtime behavior -> this standalone script, not a new
  `check-*.ts` static gate and not a vitest unit test -- `check:test-www`
  already covers the parts of `TutorialVideoPlayer.tsx` that are unit-testable
  without a browser, e.g. `WordsDoc`/caption-cue math, and should stay
  separate from this browser-driven gate).
- Before landing, also fix (or file as a fast-follow) the misleading comment
  at `packages/www/src/scripts/tutorial-video-hydrate.ts:15-16` referencing
  "the original `.tutorial-player-container` hydration in `tutorial-hydrate.ts`"
  -- that file does not exist in the current tree
  (`find packages/www -iname tutorial-hydrate.ts` -> no hits), so the comment
  is itself a small piece of the same drift this plan is otherwise fixing.
  Out of scope for the gate fix itself, but flagged here so it doesn't get
  mistaken for a still-live code path while investigating.

### Critical Files for Implementation
- packages/www/scripts/test-tutorial-player-release-gate.js
- packages/www/src/components/TutorialVideoPlayer.tsx
- packages/www/src/scripts/tutorial-video-hydrate.ts
- packages/www/src/plugins/remark-tutorial-embed.ts
- packages/www/src/styles/tutorial-video.css
