# PLAN: fix tutorial-player release gate — rewrite it for TutorialVideoPlayer, not TerminalPlayer
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: 42c5e4bdcf9adcefc94d87417cf982f920f7f7c5
Record-Sig: e777b920

## Why
The tutorial-player release gate was written for TerminalPlayer, a component deleted in May 2026 and replaced with TutorialVideoPlayer. The gate had never been wired into CI, so the 3-month drift between what it tested and what actually existed went undetected. When finally wired in this session, all 16 assertions failed because selectors (`.ap-control-bar`, `.terminal-tutorial`),
APIs (`window.__tutorialDebug`), and state logic (phase/step machine) belonged to the deleted player.

## Outcome
Gate rewritten against real TutorialVideoPlayer: all 5 scenarios now assert on `<video>` element properties (`paused`, `currentTime`, `ended`) and Plyr's CSS state classes instead of deleted debug hooks and phase machines. Verified: exit code 0, all scenarios pass on 3 consecutive runs, no orphaned processes. Owner [unresolved], completed 2026-08-28.

## Lessons
- Programmatic eval clicks (`evalInPage().click()`) silently fail browser gesture APIs (autoplay, fullscreen) — gate needed to use native click events, discovered only by driving the real scenario and comparing to a manual successful click.
- npm grandchild process cleanup requires `detached: true` + unconditional group-wide SIGKILL with grace window, not parent-PID-only termination — process.exit() resolves too early to reach the timer.
- Solution-page and docs-page video mounts render the same component but with different CSS constraints (captions burned-in vs. dynamic overlay); assertions about visual layering must account for both, or retire the cross-mount comparison entirely.
- CI gates never wired into workflow files are invisible drift vectors — they accumulate stale assertions until explicitly added to the pipeline.
- Untrusted clicks from eval fail while trusted DOM events succeed under the same browser state, discovered through live control-first verification (reverting the fix, confirming the gate fails with the expected symptom, then restoring).

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:40:06Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: scripts/ci-runner/manifest.ts, packages/www/src/styles/tutorial-video.css, packages/www/src/content/docs/en/tutorial-production-mode.mdx, packages/www/src/plugins/remark-tutorial-embed.ts, packages/www/src/scripts/tutorial-video-hydrate.ts, packages/www/src/layouts/DocsLayout.astro, packages/www/src/components/solution-pages/SolutionPage.astro, packages/www/package.json, package.json
Gates: check:ci-plan-citations, check:test-www, check:test:tutorial-player
Why-Source: model
Read-History: `git show 42c5e4bdcf9adcefc94d87417cf982f920f7f7c5` recovers the text; `git log --find-object=42c5e4bdcf9adcefc94d87417cf982f920f7f7c5 --all` names the commit

## History
- 2026-09-20T16:40:06Z compacted by d778be9d from `done` (record-sig e777b920)
