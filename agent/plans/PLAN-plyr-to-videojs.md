# PLAN: the www video player moves from Plyr to Video.js 10

Status: approved -- operator /ask 2026-10-08T02:13Z: "Hold 3.8.4, migrate next branch" (worklist #da951a5c)
Depends-On: no-dep -- the plyr 3.8.4 hold (a64eaf6b0) keeps the tree green until this lands; nothing else gates it
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P1 -- upstream Plyr is in security-only maintenance; the hold is the only thing keeping check:lint:web green
Concurrency: parallel -- three writers with disjoint files (section 4); the browser-probe measurement runs after all three land
Owns: packages/www/src/components/TutorialVideoPlayer.tsx, packages/www/src/components/tutorial-video/**, packages/www/src/scripts/tutorial-video-*.ts, packages/www/src/scripts/video-theater.ts, packages/www/src/utils/overlay-lock.ts, packages/www/src/styles/tutorial-video.css, packages/www/src/styles/solution-video.css, packages/www/src/i18n/translations/*.json, packages/www/src/components/solution-pages/SPSolutionVideo.astro, packages/www/package.json, package-lock.json, .ci/policy/.deps-upgrade-blocklist, scripts/gates/check-video-player-invariants.ts, scripts/gates/check-player-css-scope.ts, scripts/gates/check-dead-css.ts, packages/www/scripts/test-tutorial-player-release-gate.js
Worklist: #da951a5c

## Why

plyr 3.8.5 (2026-10-06) marks the Plyr class `@deprecated` ("security updates only, use Video.js 10"), which fails `@typescript-eslint/no-deprecated` at `TutorialVideoPlayer.tsx:226,341`. The tree holds plyr at 3.8.4. The upstream migration guide is https://videojs.org/docs/framework/html/guides/migrate-from-plyr; its React twin is under `/docs/framework/react/`.

## 1. Package

- **`@videojs/react@^10.0.1`, not `video.js`.** On npm, `video.js` latest is still 8.24.1; v10 is published only under `@videojs/*`. 10.0.1 was published 2026-10-02T23:02Z, so it clears `release-age.json`. Its peer range is react ^18 || ^19, and the www player is already a React 19 island.
- **Provider peers:** all 14 are optional and stay uninstalled. `@videojs/html` (lit plus custom elements) is not used.
- **Dependency changes:** remove `plyr` (www package.json:59) and its blocklist lines. Lockfile from npm 11.20.0.
- **Gates:** `check:deps`, `check:ci-lockfile` and `check:lint:web`.

## 2. Mapping (design: opus Plan agent, 2026-10-08, file:line in TutorialVideoPlayer.tsx)

- **Player:** `new Plyr` (:341) and the ref (:226) become `<VideoPlayer><VideoSkin><Video/></VideoSkin></VideoPlayer>` with `usePlayer`. Teardown happens on unmount; the snapshot `key` (:650) stays.
- **Controls:** the preset skin replaces the controls list (:344-356). The skin is ejected into `tutorial-video/skin/` only if it cannot drop or reorder items.
- **Language picker:** spike first. It goes into the skin's settings menu if a child item is possible without ejecting; otherwise the skin is ejected. If ejecting costs more than about 600 lines, fall back to the in-frame toolbar picker only, and record the choice. This replaces `language-pane.ts` and `#plyr-settings-*` (:363, :446).
- **Captions:**
  - Keep the native `<track kind="subtitles" default>` and hide the skin's own caption renderer.
  - The state comes from the `textTracks` `change` event (replacing :578-579).
  - `.tvp-caption` is rendered inside the skin (replacing :407-415 and :462-467).
- **Chapters:** the `default` chapters track gives the skin's chapter segments. `paintChapterOverlay` and the `.tvp-chapter-*` CSS go, and the "Chapters" label gets localized (:84-114, :673).
- **Portrait:** `ratio 9:16` (:343) becomes CSS `aspect-ratio: 9/16` on the skin root under `.tvp-root--portrait`.
- **Fullscreen:**
  - The skin's `requestFullscreen` is used.
  - On iOS, `webkitbeginfullscreen` turns the subtitles track to `showing`.
  - The theater's Escape-yields-to-fullscreen order (video-theater.ts:65) is unchanged.
- **Hotkeys:** the preset hotkeys, scoped to the player.
- **Persistence:** a new `tutorial-video/preferences.ts` (key `tvp-prefs`) holds volume, rate and captions. It migrates once from `plyr-tutorial`, and `alignPlyrCaptionLanguage` is deleted (:173-201, :582-589).
- **Kept as is:** snapshot and restore (:204-262, :418-435).
- **Removed:** `public/assets/plyr.svg`.
- **Control labels:** `I18nProvider` with `video.player.*` keys in all 13 locales. Today every label is English in all of them.
- **Loading:** the placeholder plus `import()` stays, as does `?url` runtime CSS (tutorial-video-styles.ts:32,56). The deferred chunk must stay ≤ 150,000 B (check-client-bundle-budget.ts:78; it is 122,110 B today).

## 3. Gates that change

- **`check-video-player-invariants.ts`:**
  - `qualityPaneFaults` (:52-62) is retired.
  - `placementFaults` (:72-90) follows the spike's outcome.
  - Also: `chromeFaults` (:136), the styles list (:226), the mutant (:345-346) and the sanity check (:432).
- **`check-player-css-scope.ts:49`** MARKERS, together with `test_gate_player_css_scope.py:40-41` in the same commit.
- **`check-dead-css.ts:66-79,244-245`:** the vendor prefix.
- **Release gate `test-tutorial-player-release-gate.js`** (:228, 247, 252, 445, 461, 471), plus `scripts/lib/tutorial-player-diagnostics.js:129,164` and `dev-server-process.js:175-177`.

## 4. Writers

Disjoint file sets; W1 publishes the selector and i18n-key contract first.
- **V1 player core:**
  - Owns: `TutorialVideoPlayer.tsx`, `tutorial-video/language-pane.ts`, new `tutorial-video/preferences.ts`, `tutorial-video-styles.ts`, `tutorial-video-mount.ts`, www `package.json`, `package-lock.json`, `.ci/policy/.deps-upgrade-blocklist` and `public/assets/plyr.svg`.
  - Runs the spike, then publishes the contract.
- **V2 CSS, i18n and comments:**
  - Owns: `tutorial-video.css`, `solution-video.css`, `src/i18n/translations/*.json`, the comment-only `.astro` and `.ts` files (SPSolutionVideo, SolutionPage, PersonaPage, SPHomePage, DocsLayout, overlay-lock, video-theater, tutorial-video-hydrate).
- **V3 gates and tests:**
  - Owns: the four gate scripts, the py test, the release gate and its two lib helpers, and `manifest.ts` (comment only).

## Boxes

- [ ] V1: spike (language picker placement, skin eject or not) recorded here; selector and i18n-key contract published
- [ ] V1: player core on @videojs/react, plyr removed with its hold; chunk ≤ 150,000 B measured from a build
- [ ] V2: CSS on the skin's custom properties; `video.player.*` in 13 locales (naturalized); comments updated
- [ ] V3: invariant, css-scope, dead-css and release gates moved to the new skin, each with a control
- [ ] Browser-probe measurement before and after: four pages × 1440x900 and 390x844. Measures deferred bytes, click-to-playing, portrait rect (about 327x581 at 390), chapter segments, captions in fullscreen, `currentTime` kept across a language switch and a resize, keyboard and the Escape order, and console errors

## Risks

Video.js 10 is a week old, so expect churn and 24-hour holds on each patch. Other gaps:
- no custom settings pane;
- no preference persistence;
- no full-window fallback on iOS;
- the speed list is fixed;
- the chunk size is unmeasured;
- captions show twice if the skin's renderer is not hidden.
