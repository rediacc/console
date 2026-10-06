#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { createDevServer, pickFreePort, resourceSnapshot } from './lib/dev-server-process.js';
import {
  captureNavigationEvidence,
  makeReloadPlant,
  pollRoutesReady,
  reportInconclusiveCauses,
  runScenarioRetryingReload,
  waitForPlayerReady as waitForPlayerReadyIn,
} from './lib/tutorial-player-diagnostics.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../..');
const artifactsRoot = path.join(repoRoot, 'artifacts', 'tutorial-player-release-gate');
const stamp = new Date().toISOString().replaceAll(/[:.]/g, '-');
const runDir = path.join(artifactsRoot, stamp);
const session = `tutorial-player-gate-${Date.now()}`;
// A fixed default port was the defect: a taken 4511 made astro move to 4512 while the browser still drove 4511 (somebody else's server). The default is now a kernel-assigned free port; the override stays for a deliberate pin, and createDevServer fails loudly if the banner's port differs from the one asked for.
const port = process.env.TUTORIAL_PLAYER_GATE_PORT
  ? Number(process.env.TUTORIAL_PLAYER_GATE_PORT)
  : await pickFreePort();
const baseUrl = `http://127.0.0.1:${port}`;
const devServer = createDevServer({ repoRoot, port });

fs.mkdirSync(runDir, { recursive: true });

const failures = [];
let exitCode = 0;
let navigationRetries = 0;
let scenarioReloadRetries = 0;

// TEST SEAM, off by default: TUTORIAL_PLAYER_GATE_PLANT_RELOADS=N makes the seek scenario reload the page N times right after its seek write (see makeReloadPlant).
const plantReload = makeReloadPlant({ evalInPage, wait, log });

function log(message) {
  process.stdout.write(`${message}\n`);
}

/**
 * @param {string} message
 * @param {unknown} [details] structured context dumped alongside the failure
 */
function fail(message, details = null) {
  failures.push({ message, details });
  process.stderr.write(`✗ ${message}\n`);
  if (details) {
    process.stderr.write(`${JSON.stringify(details, null, 2)}\n`);
  }
}

function writeArtifact(name, data) {
  const artifactPath = path.join(runDir, name);
  fs.writeFileSync(
    artifactPath,
    typeof data === 'string' ? data : JSON.stringify(data, null, 2),
    'utf8'
  );
  return artifactPath;
}

function runAgent(args) {
  const commandArgs = ['--session', session, '--json', ...args];
  let out = null;
  // A phrase rather than a number: the caller has to render it either way, and
  // `${status ?? 'with no status'}` is both a hardcoded nullish default (banned by
  // custom/no-hardcoded-nullish-defaults) and, once `status` is inferred as a number, an unnecessary conditional. Deciding the wording once at the throw site avoids both.
  let exitInfo = 'exited 0';
  try {
    out = execFileSync('agent-browser', commandArgs, {
      cwd: repoRoot,
      encoding: 'utf8',
      maxBuffer: 8 * 1024 * 1024,
      // Both streams piped, so a non-zero exit hands its output to the catch instead of leaking to the console and vanishing from the error object.
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    // THE EXIT STATUS OF `agent-browser open` IS NOT EVIDENCE, and this repo already knows it: `.ci/scripts/quality/check-agent-browser-exit.sh` measured the same
    // binary returning rc=0 on a terminal and rc=1 with stdout redirected, for a page
    // that loaded correctly both ways, and states the invariant as "no script may let that exit status decide control flow". That gate scans SHELL scripts under `set -e`; this is the same defect in JavaScript, where `execFileSync` throws on the same worthless status.
    //
    // THE RED THIS EXPLAINS: CI run 33430885467, job 99616335703, died on the FIRST navigation of the first scenario with the single line `Error: Command failed: agent-browser --session ... open http://127.0.0.1:4511/en/docs/tutorial-production-mode` -- no status, no output, and the identical command passing locally on the same tree. `String(error)` produces exactly that and drops `.status`/`.stdout`/`.stderr`.
    //
    // So: the ENVELOPE decides, never the status. agent-browser prints its verdict as JSON on STDOUT even when it exits 1 (verified against the real binary: a failed open exits 1 with an empty stderr and
    // `{"success":false,...,"error":"Navigation failed: net::ERR_UNSAFE_PORT"}` on
    // stdout). A real failure therefore still fails below, with its reason quoted.
    out = String(error.stdout ?? '');
    exitInfo =
      typeof error.status === 'number' ? `exited ${error.status}` : 'exited with no status';
    if (!out.trim()) {
      const stderr = String(error.stderr ?? '').trim();
      throw new Error(
        `agent-browser ${args.join(' ')} ${exitInfo} and printed nothing on stdout` +
          (error.signal ? `\n  signal: ${error.signal}` : '') +
          `\n  stderr: ${stderr || '(empty)'}`
      );
    }
  }
  let parsed;
  try {
    parsed = JSON.parse(out);
  } catch {
    // `--json` printing something unparseable is its own distinct failure, and calling it a JSON SyntaxError hides the bytes that caused it.
    throw new Error(
      `agent-browser ${args.join(' ')} ${exitInfo} with unparseable --json output:` +
        `\n  ${String(out).trim().slice(0, 2000) || '(empty)'}`
    );
  }
  if (!parsed.success) {
    throw new Error(
      `agent-browser ${args.join(' ')} failed: ${JSON.stringify(parsed.error)} (${exitInfo})`
    );
  }
  return parsed.data;
}

function wait(ms) {
  runAgent(['wait', String(ms)]);
}

function open(url) {
  const out = runAgent(['open', url]);
  // Stamp the document, so a later state that has lost its player says whether the page reloaded (stamp gone) or the player unmounted in place (stamp kept): dev-server noise against a product bug.
  evalInPage('(() => { window.__tpgDoc = 1; })()');
  return out;
}

/**
 * A dev-server reload under an eval destroys its context (`Inspected target navigated or
 * closed`, CI run 37131294077), and every eval here reads state or sets an idempotent value, so
 * one that died that way runs again in the new document. Anything else still throws.
 */
const RELOADED_UNDER_EVAL = /navigated or closed|context was destroyed|Cannot find context/i;
const EVAL_RELOAD_RETRIES = 2;

function evalInPage(code) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return runAgent(['eval', code]).result;
    } catch (error) {
      if (attempt >= EVAL_RELOAD_RETRIES || !RELOADED_UNDER_EVAL.test(String(error))) throw error;
      log(
        `→ the page reloaded under an eval (${RELOADED_UNDER_EVAL.exec(String(error))[0]}), evaluating again`
      );
      wait(500);
    }
  }
}

function screenshot(name) {
  const rel = path.join('artifacts', 'tutorial-player-release-gate', stamp, name);
  return runAgent(['screenshot', rel]);
}

function clearConsole() {
  runAgent(['console', '--clear']);
}

function readConsole() {
  return runAgent(['console']).messages ?? [];
}

/**
 * @param {unknown} condition
 * @param {string} message
 * @param {unknown} [details]
 */
function assertCondition(condition, message, details = null) {
  if (!condition) fail(message, details);
}

function isPlaying(state) {
  return state.paused === false && state.ended === false;
}

/**
 * A click dispatched via `evalInPage(...).click()` is NOT a trusted user gesture --
 * PROVEN live 2026-08-28: it found the button and "succeeded" as a JS call, but
 * `video.play()` silently never started playback (readyState 4, paused stayed true),
 * which is exactly Chrome's autoplay policy refusing an untrusted programmatic click.
 * agent-browser's native `click <selector>` command dispatches a real trusted input
 * event through the same pipeline a human's click would use, and the same button
 * click that failed under eval succeeded under this (currentTime advanced to 1.15s
 * within 1.5s of the click). Every scenario click below uses this, never eval.
 */
function clickSelector(selector) {
  try {
    runAgent(['click', selector]);
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: String(error) };
  }
}

/**
 * A click that THREW never reached the page: agent-browser resolves the element and checks it is
 * actionable BEFORE dispatching any input, so these refusals leave the player exactly as it was.
 * Only that class is retried. A click that succeeded and did nothing is a real dropped click, and
 * the scenario's own state assertion still fails on it -- the retry cannot hide that.
 */
const REFUSED_BEFORE_DISPATCH =
  /not found|not visible|not attached|detached|intercept|obscured|not stable/i;
const CLICK_ATTEMPTS = 4;
const CLICK_RETRY_GAP_MS = 400;

function clickWithRetry(selector) {
  let result = clickSelector(selector);
  for (let attempt = 1; !result.ok && attempt < CLICK_ATTEMPTS; attempt += 1) {
    if (!REFUSED_BEFORE_DISPATCH.test(result.reason)) break;
    log(
      `→ click on ${selector} refused (attempt ${attempt}), retrying: ${result.reason.slice(0, 300)}`
    );
    wait(CLICK_RETRY_GAP_MS);
    result = clickSelector(selector);
  }
  // The refusal text is the only evidence of WHY a click failed, and it used to be dropped.
  if (!result.ok) log(`→ click on ${selector} FAILED: ${result.reason.slice(0, 600)}`);
  return result;
}

function clickPlaybackButton() {
  return clickWithRetry('.tvp-root [data-plyr="play"]');
}

/** The readiness wait (lib/tutorial-player-diagnostics.js `waitForPlayerReady`), bound to this page and the scenario budget. */
function waitForPlayerReady(budgetMs = SCENARIO_READY_MS) {
  return waitForPlayerReadyIn(evalInPage, budgetMs, SCENARIO_READY_MS);
}

function burstPlaybackClicks(count, gapMs) {
  for (let i = 0; i < count; i += 1) {
    clickPlaybackButton();
    if (i < count - 1) wait(gapMs);
  }
  return { ok: true };
}

function currentState() {
  return evalInPage(`(() => {
    const video = document.querySelector('.tvp-root video');
    const plyrRoot = video?.closest('.plyr');
    return {
      paused: video ? video.paused : null,
      ended: video ? video.ended : null,
      currentTime: video ? video.currentTime : null,
      plyrPlaying: plyrRoot ? plyrRoot.classList.contains('plyr--playing') : null,
      sameDocument: window.__tpgDoc === 1,
      players: document.querySelectorAll('.tvp-root video').length
    };
  })()`);
}

function sampledStates(durationMs, tickMs) {
  return evalInPage(`(() => new Promise((resolve) => {
    const rows = [];
    const start = Date.now();
    const collect = () => {
      const video = document.querySelector('.tvp-root video');
      rows.push({
        t: Date.now() - start,
        paused: video ? video.paused : null,
        currentTime: video ? video.currentTime : null,
        // Tell a stalled fetch or a starved decoder (readyState below HAVE_FUTURE_DATA) from a play() race (data present, clock frozen).
        readyState: video ? video.readyState : null,
        networkState: video ? video.networkState : null,
        bufferedEnd: video && video.buffered.length > 0 ? video.buffered.end(video.buffered.length - 1) : null,
        sameDocument: window.__tpgDoc === 1
      });
      if (Date.now() - start >= ${durationMs}) {
        resolve(rows);
      } else {
        setTimeout(collect, ${tickMs});
      }
    };
    collect();
  }))()`);
}

const SCENARIO_READY_MS = 20000;
const WARMUP_READY_MS = 120000;
// Every route a scenario opens. The HTML probe and the warm-up both walk this one list: on 2026-10-05 the warm-up covered only the first, and the seek scenario's route reloaded under it (its samples went from no video element to a fresh player at 0). `eager` marks a docs route whose player mounts on load; the solution page mounts its player only after the poster is clicked (scenarioMountConsistency's own contract), so its warm-up opens it and waits for no player.
const SCENARIO_ROUTES = [
  { path: '/en/docs/tutorial-production-mode', eager: true },
  { path: '/en/docs/tutorial-add-server', eager: true },
  { path: '/en/solutions/rapid-recovery', eager: false },
];

/**
 * THE FIRST VISIT'S COST IS PAID HERE, ONCE, ON ITS OWN BUDGET (2026-10-05). On a dev server the
 * player's modules compile on the first browser visit, not when the "ready" probe fetches the
 * HTML, and a first-visit dependency re-optimization reloads the page once (see
 * waitForPlayerReady). Both used to land inside the first scenario's 20 s. The one-pass pre-push
 * on 2026-10-05 ran this gate beside pytest and sixty other gates: the docs page showed only its
 * poster for the whole budget, and a reload later in the run left every remaining scenario
 * reading a player that was gone (all fields null). The warm-up opens the page, waits up to
 * WARMUP_READY_MS for the player, then reloads it and requires it ready again inside the
 * scenarios' own budget, which shows compilation and re-optimization are both behind it before
 * any scenario's clock starts. It does this for EVERY route in SCENARIO_ROUTES, because a route's
 * first visit can re-optimize again.
 */
function warmUpPlayer() {
  for (const [i, { path: route, eager }] of SCENARIO_ROUTES.entries()) {
    const url = `${baseUrl}${route}`;
    const startedAt = Date.now();
    if (i === 0) openFirst(url);
    else open(url);
    if (!eager) {
      log(`→ warm-up ${route} opened (${Date.now() - startedAt}ms; its player mounts on click)`);
      continue;
    }
    const first = waitForPlayerReady(WARMUP_READY_MS);
    assertCondition(first.ok, `player never hydrated during the warm-up of ${route}`, first);
    const firstMs = Date.now() - startedAt;
    open(url);
    const again = waitForPlayerReady();
    assertCondition(
      again.ok,
      `${route} was not ready within the scenario budget after its warm-up reload`,
      again
    );
    log(
      `→ warm-up ${route} ok (first hydration ${firstMs}ms, warm reload ${Date.now() - startedAt - firstMs}ms)`
    );
  }
}

function scenarioBasicPlayPauseResume() {
  log('→ scenario: basic play/pause/resume');
  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  const ready = waitForPlayerReady();
  assertCondition(ready.ok, 'player never became ready on the docs page', ready);
  clearConsole();

  assertCondition(clickPlaybackButton().ok, 'play button click failed at start');
  wait(1400);
  const started = currentState();
  assertCondition(isPlaying(started), 'start did not enter playing state', started);

  assertCondition(clickPlaybackButton().ok, 'pause button click failed');
  wait(900);
  const paused = currentState();
  assertCondition(paused.paused === true, 'pause did not stop the video', paused);
  wait(1200);
  const pausedStable = currentState();
  assertCondition(
    pausedStable.paused === true && pausedStable.currentTime === paused.currentTime,
    'pause state did not remain stable',
    { paused, pausedStable }
  );

  assertCondition(clickPlaybackButton().ok, 'resume button click failed');
  wait(1400);
  const resumed = currentState();
  assertCondition(isPlaying(resumed), 'resume did not re-enter playing state', resumed);

  writeArtifact('scenario-basic-console.json', readConsole());
  screenshot('scenario-basic.png');
}

function scenarioBurstToggle() {
  log('→ scenario: burst toggle resilience');
  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  assertCondition(waitForPlayerReady().ok, 'player never became ready before burst');
  clearConsole();

  assertCondition(clickPlaybackButton().ok, 'initial click failed before burst');
  wait(350);
  assertCondition(burstPlaybackClicks(6, 80).ok, 'burst click scheduling failed');

  const rows = sampledStates(12000, 700);
  writeArtifact('scenario-burst-states.json', rows);
  writeArtifact('scenario-burst-console.json', readConsole());
  screenshot('scenario-burst.png');

  // The real analog of the old "stuck at narrating step0" bug: a play() promise race
  // from rapid clicking can wedge the player at currentTime 0 while reporting
  // paused=false. If currentTime never advances across the whole sample window while
  // the player claims to be playing at least once, it is wedged, not merely paused.
  const claimsPlayingAndStuck =
    rows.length > 0 &&
    rows.some((row) => row.paused === false) &&
    rows.every((row) => row.currentTime === rows[0].currentTime);
  assertCondition(
    !claimsPlayingAndStuck,
    'burst caused the player to wedge at currentTime 0 while claiming to play',
    rows.slice(-5)
  );
}

function scenarioSeekNoSnapback() {
  log('→ scenario: seek no snapback');
  open(`${baseUrl}/en/docs/tutorial-add-server`);
  assertCondition(waitForPlayerReady().ok, 'player never became ready before seek');

  const hasVideo = evalInPage(`(() => Boolean(document.querySelector('.tvp-root video')))()`);
  assertCondition(hasVideo, 'tutorial video element not found on the page');
  if (!hasVideo) return;

  assertCondition(clickPlaybackButton().ok, 'play click failed before seek');
  wait(1200);
  // Direct media-element seek rather than driving a .tvp-chapter-tick click: the chapter overlay only paints once the <track> cues have loaded (async, no reliable ready signal to poll for here), so a direct write is the more robust check for "does a seek stick" -- the SPA-history-triggered snapback this scenario exists to catch happens downstream of the media element's own currentTime, not upstream of it.
  const seekTarget = 48;
  evalInPage(`(() => {
    const v = document.querySelector('.tvp-root video');
    v.currentTime = ${seekTarget};
  })()`);
  plantReload();

  const rows = sampledStates(9000, 700);
  writeArtifact('scenario-seek-states.json', rows);
  screenshot('scenario-seek.png');

  const landed = rows.find((row) => row.currentTime !== null && row.currentTime >= seekTarget - 1);
  assertCondition(Boolean(landed), 'seek did not land near the target time', {
    seekTarget,
    rows,
  });
  if (landed) {
    const landedIdx = rows.indexOf(landed);
    const snapback = rows
      .slice(landedIdx + 1)
      .find((row) => row.currentTime !== null && row.currentTime < seekTarget - 2);
    assertCondition(!snapback, 'seek snapped back to an earlier time later', {
      landedIdx,
      snapback,
      rows,
    });
  }
}

function scenarioFullscreenAndLayering() {
  log('→ scenario: fullscreen and layering');
  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  assertCondition(waitForPlayerReady().ok, 'player never became ready before fullscreen');
  assertCondition(clickPlaybackButton().ok, 'play click failed before fullscreen');
  wait(900);

  // The Fullscreen API refuses requestFullscreen() without a trusted user gesture, same root cause as the play button -- must be a native click, not eval'd .click().
  const enter = clickSelector('.tvp-root [data-plyr="fullscreen"]');
  assertCondition(enter.ok, 'failed to click fullscreen button', enter);
  wait(700);

  const fsState = evalInPage(`(() => ({
    fullscreen: Boolean(document.fullscreenElement),
    captionPresent: Boolean(document.querySelector('.tvp-root .tvp-caption'))
  }))()`);
  assertCondition(fsState.fullscreen, 'fullscreen not active after toggle', fsState);
  // .tvp-caption is not swapped for a fullscreen-only element (unlike the deleted TerminalPlayer's `.terminal-player-caption-layer--fullscreen`): it is the SAME element, repositioned by `.plyr--fullscreen-active .tvp-caption` CSS. Its continued presence in the DOM is what matters here.
  assertCondition(
    fsState.captionPresent,
    'caption element missing after entering fullscreen',
    fsState
  );

  clickSelector('.tvp-root [data-plyr="fullscreen"]');
  wait(500);
  const exitState = evalInPage(`(() => ({ fullscreen: Boolean(document.fullscreenElement) }))()`);
  assertCondition(!exitState.fullscreen, 'fullscreen did not exit', exitState);

  // The docs-vs-heading-share layering comparison from the deleted TerminalPlayer era is retired, not adapted: `.heading-share` does not exist anywhere in the current site (verified: grep -rn "heading-share" packages/www/src -> no hits), and the layout it belonged to is gone. See agent/PLAN-fix-tutorial-player-debug-hook-attachment.md, scenario 5, for why no replacement invariant was invented here.
  const docsZ = evalInPage(`(() => {
    const s = (el, prop) => el ? getComputedStyle(el)[prop] : null;
    return {
      captionZ: s(document.querySelector('.tvp-root .tvp-caption'), 'zIndex'),
      chapterOverlayZ: s(document.querySelector('.tvp-root .tvp-chapter-overlay'), 'zIndex')
    };
  })()`);
  writeArtifact('scenario-layering-docs.json', docsZ);
}

function scenarioMountConsistency() {
  // The homepage no longer carries a tutorial/video player -- SPHomeHero.astro deliberately removed the old "fake terminal" (operator-approved: it "failed contrast... shipped a disclaimer apologising for being simulated"). The docs route and a solution-page hero are the two mount paths that both go through TutorialVideoPlayer today (tutorial-video-hydrate.ts:25), so THIS is the pair worth checking for consistency: same component, two different placements.
  log('→ scenario: docs/solution-page mount consistency');

  // ONE PROBE SHAPE for both pages, because the point of this scenario is that the two surfaces answer it DIFFERENTLY. Docs mounts build immediately; solution mounts carry `data-click-to-load` and render a server-side poster instead of building the 122 KB player. Measured across all 44 English mount-carrying pages at 1440x900 and 390x844, every mount is ABOVE THE FOLD, so an IntersectionObserver fires on load and defers nothing -- which is why the deferral had to become a click.
  //
  // The solution assertions are the REAL contract and strictly stronger than the single `hasPlayer` this used to carry: no player before the click, a poster to click, a player inside the THEATER after it, the poster still there, and Escape putting it all back. The old form could not tell a working deferral from a broken mount.
  const probe = () =>
    evalInPage(
      `(() => { const q = (s) => document.querySelector(s); const c = q('.tvp-root .tvp-caption'); return { hasPlayer: Boolean(q('.tvp-root video')), hasPoster: Boolean(q('.video-poster-play')), theaterOpen: Boolean(q('.video-theater:not([hidden])')), playerInTheater: Boolean(q('.video-theater .tvp-root video')), captionZ: c ? getComputedStyle(c).zIndex : null }; })()`
    );

  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  wait(800);
  const docs = probe();
  open(`${baseUrl}/en/solutions/rapid-recovery`);
  wait(1000);
  const before = probe();
  // Native click, not eval'd .click(), for the reason clickSelector documents.
  clickSelector('.video-poster-play');
  wait(2500);
  const after = probe();
  runAgent(['press', 'Escape']);
  wait(600);
  const closed = probe();
  writeArtifact('scenario-layering-solution.json', { before, after, closed });

  assertCondition(docs.hasPlayer, 'docs page tutorial video player not found', docs);
  assertCondition(
    !docs.theaterOpen,
    'docs mounts must keep building in place; no theater belongs on a docs page',
    docs
  );
  assertCondition(
    !before.hasPlayer && before.hasPoster,
    'solution page must show a poster and NO player before the click',
    before
  );
  // THE POSTER SURVIVES THE CLICK, and that reversal is the point of the theater. Until 2026-09-09 this asserted `!after.hasPoster`, because the player was built in place and the poster was removed to make room for it. It is now built inside a full-viewport overlay instead -- the inline box is 576px wide for 1920x1080 footage
  // with burned-in captions -- and the poster is what the visitor returns to on close.
  // An assertion that the poster is gone would now be asserting the old defect.
  assertCondition(
    after.playerInTheater && after.theaterOpen,
    'clicking the poster must open the theater with a player inside it',
    after
  );
  assertCondition(
    after.hasPoster,
    'the inline poster must survive the click; closing the theater returns to it',
    after
  );
  assertCondition(
    !closed.theaterOpen && closed.hasPoster,
    'Escape must close the theater and leave the poster clickable',
    closed
  );

  // NOT a docs-vs-solution caption z-index comparison: solution videos have no `words` manifest entry (verified: packages/www/src/data/video-manifest.json -> solutions.rapid-recovery.en has only mp4/vertical/poster, no words) because their captions are burned into the video pixels, per TutorialVideoPlayer.tsx:713's own `activeWords &&` guard on rendering `.tvp-caption` at all. Asserting the two mounts' caption z-index MATCH would fail by design, not by defect -- checked instead is the one invariant that is actually guaranteed: a caption element, when present, sits at the CSS-defined z-index (tutorial-video.css:63).
  assertCondition(
    docs.captionZ === '3',
    'docs caption z-index does not match the CSS-defined value',
    docs
  );
}

/**
 * The first navigation, timed, and self-describing when it fails.
 *
 * WHY THIS EXISTS RATHER THAN A BARE open(): the gate has failed three times at exactly
 * this call and each time reported only "Operation timed out. The page may still be
 * loading or the element may not exist." -- which names neither what was pending nor how
 * long the healthy case takes. Logging the elapsed time on EVERY run makes the ~5s
 * baseline visible, so the next 29s reads instantly as a ceiling rather than a slowdown.
 *
 * On timeout it dumps the browser's pending requests and the dev server's own output
 * before retrying, because that is the evidence that names the stalled resource. The
 * leading suspect is the analytics script BaseLayout.astro loads unconditionally from a
 * third-party host on every page, dev included: an `async` script still delays `load`,
 * and a tutorial-player release gate has no business being decided by it. That is a
 * CANDIDATE, not a finding -- agent-browser's docs do not state what `open` waits for,
 * so the dump is what will settle it.
 *
 * The retry is recorded, never silent: a run that needed it is not clean, and a second
 * timeout still fails the gate.
 */
function openFirst(url) {
  const startedAt = Date.now();
  try {
    const out = open(url);
    log(`→ first navigation ok (${Date.now() - startedAt}ms)`);
    return out;
  } catch (err) {
    log(`→ first navigation FAILED after ${Date.now() - startedAt}ms: ${err}`);
    captureNavigationEvidence({
      dir: path.join(repoRoot, 'artifacts', 'tutorial-player-release-gate', stamp),
      runAgent,
      serverLog: devServer.log,
      log,
    });
    navigationRetries += 1;
    log('→ retrying the first navigation once');
    const retryAt = Date.now();
    const out = open(url);
    log(`→ first navigation ok on RETRY (${Date.now() - retryAt}ms)`);
    return out;
  }
}

async function main() {
  try {
    execFileSync('agent-browser', ['--version'], { encoding: 'utf8' });
  } catch {
    fail('agent-browser is not installed or not accessible in PATH');
    process.exit(1);
  }

  let resources = resourceSnapshot(null);
  const bootStartedAt = Date.now();
  try {
    log(`→ starting astro dev server on ${baseUrl}`);
    await devServer.start();
    resources = resourceSnapshot(Date.now() - bootStartedAt);
    await pollRoutesReady(
      baseUrl,
      SCENARIO_ROUTES.map((r) => r.path),
      log
    );
    wait(1500);

    warmUpPlayer();
    for (const [name, run] of [
      ['basic play/pause/resume', scenarioBasicPlayPauseResume],
      ['burst toggle resilience', scenarioBurstToggle],
      ['seek no snapback', scenarioSeekNoSnapback],
      ['fullscreen and layering', scenarioFullscreenAndLayering],
      ['docs/solution-page mount consistency', scenarioMountConsistency],
    ]) {
      scenarioReloadRetries += runScenarioRetryingReload({ name, run, failures, log });
    }

    const summary = {
      status: failures.length === 0 ? 'pass' : 'fail',
      failures,
      artifactsDir: runDir,
      session,
      baseUrl,
      resources,
      navigationRetries,
      scenarioReloadRetries,
      serverDiedMidRun: devServer.diedMidRun,
    };
    writeArtifact('summary.json', summary);

    if (failures.length > 0) {
      reportInconclusiveCauses(devServer, resources);
      process.stderr.write(
        `\n✗ tutorial player release gate failed (${failures.length} failures)\n`
      );
      process.stderr.write(`Artifacts: ${runDir}\n`);
      exitCode = 1;
      return;
    }

    process.stdout.write(`\n✓ tutorial player release gate passed\nArtifacts: ${runDir}\n`);
    exitCode = 0;
  } catch (error) {
    fail('release gate execution crashed', { error: String(error) });
    // If the crash happened before startDevServer resolved (its own timeout, or a crash mid-boot), `resources` above still holds the pre-boot snapshot with
    // bootMs=null. Recompute against elapsed wall time so a boot-phase crash is
    // judged on how long it actually ran, not treated as instant.
    if (resources.bootMs === null) {
      resources = resourceSnapshot(Date.now() - bootStartedAt);
    }
    reportInconclusiveCauses(devServer, resources);
    writeArtifact('summary.json', {
      status: 'crash',
      failures,
      crash: String(error),
      artifactsDir: runDir,
      session,
      baseUrl,
      resources,
      serverDiedMidRun: devServer.diedMidRun,
      // THE BOOT TIMEOUT IS THE ONE FAILURE THAT CANNOT BE READ WITHOUT THIS, and it was the one path that omitted it. `serverLog` was written on the navigation path only, so five boot-timeout artifacts in a row reported that the server "timed out" while discarding the banner proving it had started in 4.7s. The header comment above already claimed this was "written out on failure"; now it is.
      serverLog: devServer.log,
    });
    exitCode = 1;
  } finally {
    try {
      runAgent(['close']);
    } catch {
      // Ignore cleanup errors.
    }
    await devServer.stop();
    process.exit(exitCode);
  }
}

void main();
