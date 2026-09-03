# PLAN: load the video player's CSS on demand, not on every page that carries the hydrator
Status: draft
Owner: 74de73ca
Updated: 2026-09-03

Every claim below was confirmed at source level in the toolchain, not inferred.

## The finding

`TutorialVideoPlayer.tsx:23-24` imports `plyr/dist/plyr.css` and
`../styles/tutorial-video.css` at module scope. Those become one emitted chunk,
**37,018 B raw / 6,087 B gzip** (plyr 32,428 B; tutorial-video.css 4,590 B).

Counted over the current `dist` (1,842 HTML files), and reproduced independently twice:

| | pages |
|---|---|
| link the player stylesheet | 1,366 |
| contain a player mount | 572 |
| link AND mount | 572 |
| **link with NO mount** | **794** |
| mount with no link | 0 |

**All 794 are docs pages.**

## Root cause, confirmed in the toolchain source

The hydrator reaches the player through a dynamic `import()`, but Astro's page-CSS
hoisting (`astro/dist/core/build/plugins/plugin-css.js:84-160`) iterates every chunk's
`viteMetadata.importedCss` and attaches client-chunk CSS to every page in
`pagesByScriptId`. **Dynamic-import boundaries are irrelevant to it.** So the sheet is
linked wherever the HYDRATOR is, not wherever a PLAYER is. DocsLayout carries the
hydrator on 1,028 docs pages; 234 of them have a video.

## Mechanisms evaluated

1. **Move the import to the components that emit a mount.** CANNOT WORK, and this is
   the finding that kills the obvious fix: all 794 offenders are docs, docs are one
   layout over one `[slug].astro`, and the `.tutorial-video-container` mount is emitted
   by a REMARK PLUGIN as raw HTML -- there is no module to hang an import on. Fixes 0
   of 794.
2. **Drop the hydrator from layouts without mounts.** Cannot work, same reason: Astro
   bundles a `<script>` per page regardless of conditional rendering, and the docs
   layout serves both populations.
3. **Anything native in Astro.** There is none; `build.inlineStylesheets` decides
   inline-vs-link, not which pages get it.
4. **Runtime injection via Vite `?url`.** CHOSEN, and confirmed rather than assumed:
   `vite/dist/node/chunks/config.js:29635-29639` compiles `?url` to a `transform-only`
   import plus a URL string; `:29797` excludes `transform-only` from `chunkCSS`, so it
   never enters `importedCss`; `:29854` still runs `finalizeCss`, so it stays minified;
   `:29866` emits it as an asset Astro never reads. `plyr.css` has zero `url()`
   references, so asset rebasing is a non-issue.

## FOUC risk: zero, by construction rather than by timing

`tutorial-video.css` contains **no selector for either mount class** -- every rule is
`.tvp-*` or a `.tvp-root`-scoped `.plyr*` override, i.e. DOM React creates. The
placeholder's reserved box comes from `solution-video.css:94,108` and
`DocsLayout.astro:1369`, neither of which moves. So the stylesheet governs only DOM
that does not exist until after it has loaded, and
`Promise.all([ensurePlayerStyles(), import(player)])` makes the first frame of player
DOM already styled.

Cascade: `.plyr`/`.tvp-` selectors exist in exactly two files, and their overlaps are
decided by SPECIFICITY, not order -- `solution-video.css:39-40,71-72` say in as many
words that they were written that way "so the outcome does not depend on which
stylesheet the bundler emits first". Reordering is safe, and that safety is documented
in-tree. There is no `<ClientRouter />` anywhere, so no head swap can orphan a link.

**The second import must move too, not merely may.** If `tutorial-video.css` stays
static, `TutorialVideoPlayer.*.css` still exists and is still linked on all 1,366
pages (4,590 B instead of 37,018), and the gate's assertion is unsatisfiable.

## The gate: `check:ci-player-css-scope`

**Assertion:** for every `dist/**/*.html`, a page that links a player stylesheet must
contain a mount. Today 794. After the fix 0.

A *player stylesheet* is detected **by CONTENT, not filename** -- any dist CSS
containing `.plyr__control` or `.tvp-caption-word` -- so a rename or re-bundle cannot
make the gate blind. The marker choice was measured: `.tvp-root` and `.tvp-toolbar`
also appear in a NON-player bundle, so using them would over-match.

**Six floors, because the assertion is a negative and absence must be paid for:**
F1 dist exists; F2 >= 1,000 HTML files scanned (today 1,842); F3 >= 1,000 stylesheet
links seen (a broken href regex would otherwise report "no player links" vacuously);
F4 at least one dist CSS carries each marker (zero means the player has no stylesheet
at all -- a worse defect wearing this gate's green); F5 >= 500 pages carry a mount
(today 572); and **F6, the positive half that stops the fix degenerating into a
deletion**: every player stylesheet's filename must appear inside at least one dist JS
chunk, proving the styles still REACH the player. Without F6, deleting `plyr.css`
outright would pass.

**Controls:** eight plants, each with a clean counterpart, including P4 -- a CSS
carrying `.tvp-root` but neither marker must NOT be reported, which the real tree
proves is needed. Plus a mutant control that widens the marker list and asserts the
selftest goes red naming P4, and one that deletes F6 and asserts red naming P6, each
with a vacuity guard so a sed that stopped matching cannot test the unmutated gate.

## Order of work: control first, literally

1. Write the gate and its selftest BEFORE touching any source.
2. Run it against the EXISTING dist. It must report **794**. That is a free real-tree
   proof that it fires on the live defect, needing no build. Anything else means the
   gate is wrong, not the finding.
3. Then the five source changes; then ONE serialised `build:www` (it unlinks and
   rewrites 14 tracked `search-index*.json`, and concurrent builds corrupt `dist`).
4. Re-run: 0 offenders, all six floors satisfied.
5. Browser-check one page of each family: styled on first paint, no console errors.

## Non-goals

Not deleting or inlining plyr; not changing which pages have videos; not touching the
IntersectionObserver deferral. `check:ci-client-bundle-budget` measures JS only and its
figure does not move.

## A finding walked past and reported rather than fixed

`.tutorial-video-container` reserves **no box** before hydration -- nothing gives it an
`aspect-ratio` or `min-height`, only `max-inline-size`. So 234 docs tutorial pages
shift by the full player height when it lands, unlike solution pages which
`solution-video.css:94` protects. The browser probe's "the mount already reserves
768x432" holds for `.video-player-mount` ONLY. This plan neither causes nor worsens it;
it wants its own item.

## Tasks

- [ ] Write `scripts/check-player-css-scope.ts` with the six floors and eight selftest plants, BEFORE any source change
- [ ] Run it against the existing dist and confirm it reports exactly 794 offenders
- [ ] Write `packages/www/src/scripts/tutorial-video-styles.ts` exporting `ensurePlayerStyles()`, memoised, resolving on load OR error so a missing sheet leaves an ugly player rather than none
- [ ] Delete `TutorialVideoPlayer.tsx:23-24`, leaving a comment pointing at the new module and saying why
- [ ] Await `Promise.all([ensurePlayerStyles(), import(player)])` in the hydrator before `createRoot`
- [ ] Re-point the stale `BLOCKER:` citation in `scripts/check-dead-css.ts:53-62`
- [ ] Add the source-level invariant to `check-video-player-invariants.ts` (hydrator must await the styles before `createRoot`) with mutants that delete and that reorder the call
- [ ] Write `.ci/scripts/test/gates/test-player-css-scope.sh` with both mutants, written OUTSIDE the repo to avoid check:ci-pool-writer-safety
- [ ] Three-point wiring: package.json key, two manifest entries, and a `Player CSS scope` step in quality-www-build whose name matches the manifest byte for byte
- [ ] One serialised `build:www`, then re-run the gate for 0 offenders
- [ ] Browser-check a solution page, a docs tutorial page and the homepage
