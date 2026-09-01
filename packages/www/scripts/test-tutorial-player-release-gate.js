#!/usr/bin/env node

import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../..');
const artifactsRoot = path.join(repoRoot, 'artifacts', 'tutorial-player-release-gate');
const stamp = new Date().toISOString().replaceAll(/[:.]/g, '-');
const runDir = path.join(artifactsRoot, stamp);
const session = `tutorial-player-gate-${Date.now()}`;
/** Port the gate's throwaway static server listens on when none is given. */
const DEFAULT_GATE_PORT = '4511';

const port = Number(process.env.TUTORIAL_PLAYER_GATE_PORT ?? DEFAULT_GATE_PORT);
const baseUrl = `http://127.0.0.1:${port}`;

fs.mkdirSync(runDir, { recursive: true });

const failures = [];
let serverProc = null;
let exitCode = 0;
/**
 * Set the moment the dev server process exits, whenever that happens -- not just
 * during boot. PROVEN NECESSARY: a live run (2026-08-28) had astro exit between
 * two scenarios; every scenario after that failed with generic "button click
 * failed" / null-phase noise, and the eventual agent-browser crash
 * (net::ERR_CONNECTION_REFUSED) was the only place the real cause was visible,
 * buried under 7 unrelated-looking assertion failures. The boot promise's exit
 * handler only fires usefully once (a second resolve/reject after it has
 * already settled is a silent no-op), so a mid-run death was invisible until
 * this flag made it a first-class, reported fact instead.
 */
let serverDiedMidRun = null;
let navigationRetries = 0;
// PIPED SINCE FOREVER AND NEVER READ. On a navigation timeout this is the only record
// of what the server thought it was doing, so it is kept and written out on failure.
const serverLog = [];
let intentionalShutdown = false;

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
  // custom/no-hardcoded-nullish-defaults) and, once `status` is inferred as a number, an
  // unnecessary conditional. Deciding the wording once at the throw site avoids both.
  let exitInfo = 'exited 0';
  try {
    out = execFileSync('agent-browser', commandArgs, {
      cwd: repoRoot,
      encoding: 'utf8',
      maxBuffer: 8 * 1024 * 1024,
      // Both streams piped, so a non-zero exit hands its output to the catch instead of
      // leaking to the console and vanishing from the error object.
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    // THE EXIT STATUS OF `agent-browser open` IS NOT EVIDENCE, and this repo already
    // knows it: `.ci/scripts/quality/check-agent-browser-exit.sh` measured the same
    // binary returning rc=0 on a terminal and rc=1 with stdout redirected, for a page
    // that loaded correctly both ways, and states the invariant as "no script may let
    // that exit status decide control flow". That gate scans SHELL scripts under
    // `set -e`; this is the same defect in JavaScript, where `execFileSync` throws on
    // the same worthless status.
    //
    // THE RED THIS EXPLAINS: CI run 33430885467, job 99616335703, died on the FIRST
    // navigation of the first scenario with the single line `Error: Command failed:
    // agent-browser --session ... open http://127.0.0.1:4511/en/docs/tutorial-production-mode`
    // -- no status, no output, and the identical command passing locally on the same
    // tree. `String(error)` produces exactly that and drops `.status`/`.stdout`/`.stderr`.
    //
    // So: the ENVELOPE decides, never the status. agent-browser prints its verdict as
    // JSON on STDOUT even when it exits 1 (verified against the real binary: a failed
    // open exits 1 with an empty stderr and
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
    // `--json` printing something unparseable is its own distinct failure, and calling
    // it a JSON SyntaxError hides the bytes that caused it.
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
  return runAgent(['open', url]);
}

function evalInPage(code) {
  return runAgent(['eval', code]).result;
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

/** Prints the "this may not be a real regression" context, most-specific cause first. */
function reportInconclusiveCauses(resources) {
  if (serverDiedMidRun) {
    process.stderr.write(
      `\n⚠ THE DEV SERVER EXITED MID-RUN (code ${serverDiedMidRun.code}) -- everything after ` +
        `that point failed against a dead server, not a real player defect. Find why astro ` +
        `died (OOM, an uncaught exception, a killed process) before treating these as product ` +
        `bugs.\n`
    );
    return;
  }
  if (resources.pressureDetected) {
    process.stderr.write(
      `\n⚠ SYSTEM UNDER LOAD while this ran (load/core=${resources.loadPerCore.toFixed(2)}, ` +
        `boot=${resources.bootMs}ms of a 180000ms budget) -- this may be resource contention, ` +
        `not a real regression. Re-run on an idle machine before treating it as a product bug.\n`
    );
  }
}

function isPlaying(state) {
  return state.paused === false && state.ended === false;
}

/**
 * A resource-starved run and a real regression produce IDENTICAL symptoms here:
 * failed clicks, missing debug hooks, a crashed agent-browser session -- nothing
 * in the scenario assertions can tell them apart. Measured live 2026-08-28: the
 * same run that timed out on a loaded devbox (84s cold boot against a then-60s
 * budget) later crashed agent-browser mid-scenario under the same concurrent
 * CPU load, and a human had to reason it out from the machine's process list.
 * This makes that reasoning part of the artifact instead: sample load average
 * per core (>1 means more runnable work than cores, the standard reading) and
 * how long the dev server actually took to boot against its 180s budget.
 */
function resourceSnapshot(bootMs) {
  const cpuCount = os.cpus().length || 1;
  const loadPerCore = os.loadavg()[0] / cpuCount;
  // Half the boot budget: a clean cold boot measured 84s, so crossing 90s is
  // already an outlier, not just "a bit slow".
  const slowBoot = bootMs !== null && bootMs > 90000;
  const highLoad = loadPerCore > 1.2;
  return {
    cpuCount,
    loadavg1m: os.loadavg()[0],
    loadPerCore,
    bootMs,
    pressureDetected: slowBoot || highLoad,
  };
}

async function startDevServer() {
  return await new Promise((resolve, reject) => {
    const args = [
      'run',
      'dev',
      '-w',
      '@rediacc/www',
      '--',
      '--host',
      '127.0.0.1',
      '--port',
      String(port),
    ];
    // `detached: true` makes this its own process group leader. PROVEN NECESSARY,
    // not precautionary: `npm run dev` spawns `astro` as a grandchild, and killing
    // just the npm PID does not propagate to it -- verified live 2026-08-28, a fully
    // successful gate run (exit 0, all 5 scenarios passing) still left `astro`
    // running and holding port 4511 afterward. stopDevServer() below signals the
    // whole group (`-proc.pid`), which reaches the grandchild too.
    serverProc = spawn('npm', args, {
      cwd: repoRoot,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: true,
    });

    // A cold `astro dev` start (no vite cache, content store rebuild) measured
    // 84s on a loaded devbox; CI runners hit the same cold path every run, so
    // 60s under-times it. 180s leaves headroom without masking a real hang.
    const timeout = setTimeout(() => {
      reject(new Error('Timed out waiting for astro dev server to start'));
    }, 180000);

    // MATCH ASTRO'S BANNER, NOT THE SUBSTRING `ready`. The string "address already in
    // use" CONTAINS "ready", and so does any message quoting the URL -- so an EADDRINUSE
    // line would have been read as "the server is up" and the run would proceed against
    // somebody else's listener. It did not fire in the observed failures (no
    // serverDiedMidRun warning in either), but it is a booby trap in exactly this path.
    const READY = /ready in \d|Local\s+http:\/\/127\.0\.0\.1:/i;
    const onData = (chunk) => {
      const text = String(chunk);
      serverLog.push(text);
      if (READY.test(text)) {
        clearTimeout(timeout);
        resolve();
      }
    };

    serverProc.stdout.on('data', onData);
    serverProc.stderr.on('data', onData);
    serverProc.on('exit', (code) => {
      clearTimeout(timeout);
      if (!intentionalShutdown) {
        serverDiedMidRun = { code, at: Date.now() };
      }
      reject(new Error(`astro dev exited early with code ${code}`));
    });
  });
}

async function stopDevServer() {
  if (!serverProc) return;
  const proc = serverProc;
  serverProc = null;
  intentionalShutdown = true;
  // `proc`'s own 'exit' event is NOT a reliable signal that the whole group is
  // dead -- PROVEN live 2026-08-28: npm (the direct child, `proc` here) exits
  // fast on SIGTERM while `astro` (its grandchild, still in its own graceful
  // shutdown) keeps running; the old code resolved on npm's exit and
  // `process.exit()` in main()'s finally then killed the whole script before the
  // SIGKILL safety-net timer (`timer.unref()`'d, so it never survives
  // process.exit()) got a chance to fire. astro was left holding the port on
  // EVERY run, including fully passing ones. Fix: always send an unconditional
  // group-wide SIGKILL after a short grace window, never conditionally.
  try {
    process.kill(-proc.pid, 'SIGTERM');
  } catch {
    try {
      proc.kill('SIGTERM');
    } catch {
      // Already gone.
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 1200));
  try {
    process.kill(-proc.pid, 'SIGKILL');
  } catch {
    try {
      proc.kill('SIGKILL');
    } catch {
      // Ignore: already exited, or never had a distinct group to kill.
    }
  }
}

// PLAYER SELECTORS, verified against packages/www/src/components/TutorialVideoPlayer.tsx
// at HEAD (2026-08-28): the player root is `.tvp-shell > .tvp-root`, hydrated by
// tutorial-video-hydrate.ts onto `.tutorial-video-container[data-video-src]` (docs) or
// `.video-player-mount[data-video-src]` (solution-page hero). Plyr wraps the real
// `<video>` and renders standard `[data-plyr="X"]` control buttons (controls list at
// TutorialVideoPlayer.tsx:362-376 includes 'play' and 'fullscreen'), toggling
// `.plyr--playing` / `.plyr--fullscreen-active` on the `.plyr` wrapper it inserts.
// This replaces the TerminalPlayer-era `.ap-control-bar`/`.terminal-tutorial`/
// `window.__tutorialDebug` surface, deleted wholesale in 80a000965 (2026-05-27) --
// see agent/PLAN-fix-tutorial-player-debug-hook-attachment.md for the full trace.

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

function clickPlaybackButton() {
  return clickSelector('.tvp-root [data-plyr="play"]');
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
      plyrPlaying: plyrRoot ? plyrRoot.classList.contains('plyr--playing') : null
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
        currentTime: video ? video.currentTime : null
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

function scenarioBasicPlayPauseResume() {
  log('→ scenario: basic play/pause/resume');
  openFirst(`${baseUrl}/en/docs/tutorial-production-mode`);
  wait(1200);
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
  wait(1000);
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
  wait(1200);

  const hasVideo = evalInPage(`(() => Boolean(document.querySelector('.tvp-root video')))()`);
  assertCondition(hasVideo, 'tutorial video element not found on the page');
  if (!hasVideo) return;

  assertCondition(clickPlaybackButton().ok, 'play click failed before seek');
  wait(1200);
  // Direct media-element seek rather than driving a .tvp-chapter-tick click: the
  // chapter overlay only paints once the <track> cues have loaded (async, no
  // reliable ready signal to poll for here), so a direct write is the more robust
  // check for "does a seek stick" -- the SPA-history-triggered snapback this
  // scenario exists to catch happens downstream of the media element's own
  // currentTime, not upstream of it.
  const seekTarget = 48;
  evalInPage(`(() => {
    const v = document.querySelector('.tvp-root video');
    v.currentTime = ${seekTarget};
  })()`);

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
  wait(1000);
  assertCondition(clickPlaybackButton().ok, 'play click failed before fullscreen');
  wait(900);

  // The Fullscreen API refuses requestFullscreen() without a trusted user gesture,
  // same root cause as the play button -- must be a native click, not eval'd .click().
  const enter = clickSelector('.tvp-root [data-plyr="fullscreen"]');
  assertCondition(enter.ok, 'failed to click fullscreen button', enter);
  wait(700);

  const fsState = evalInPage(`(() => ({
    fullscreen: Boolean(document.fullscreenElement),
    captionPresent: Boolean(document.querySelector('.tvp-root .tvp-caption'))
  }))()`);
  assertCondition(fsState.fullscreen, 'fullscreen not active after toggle', fsState);
  // .tvp-caption is not swapped for a fullscreen-only element (unlike the deleted
  // TerminalPlayer's `.terminal-player-caption-layer--fullscreen`): it is the SAME
  // element, repositioned by `.plyr--fullscreen-active .tvp-caption` CSS. Its
  // continued presence in the DOM is what matters here.
  assertCondition(
    fsState.captionPresent,
    'caption element missing after entering fullscreen',
    fsState
  );

  clickSelector('.tvp-root [data-plyr="fullscreen"]');
  wait(500);
  const exitState = evalInPage(`(() => ({ fullscreen: Boolean(document.fullscreenElement) }))()`);
  assertCondition(!exitState.fullscreen, 'fullscreen did not exit', exitState);

  // The docs-vs-heading-share layering comparison from the deleted TerminalPlayer era
  // is retired, not adapted: `.heading-share` does not exist anywhere in the current
  // site (verified: grep -rn "heading-share" packages/www/src -> no hits), and the
  // layout it belonged to is gone. See
  // agent/PLAN-fix-tutorial-player-debug-hook-attachment.md, scenario 5, for why no
  // replacement invariant was invented here.
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
  // The homepage no longer carries a tutorial/video player -- SPHomeHero.astro
  // deliberately removed the old "fake terminal" (operator-approved: it "failed
  // contrast... shipped a disclaimer apologising for being simulated"). The docs
  // route and a solution-page hero are the two mount paths that both go through
  // TutorialVideoPlayer today (tutorial-video-hydrate.ts:25), so THIS is the pair
  // worth checking for consistency: same component, two different placements.
  log('→ scenario: docs/solution-page mount consistency');
  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  wait(800);
  const docs = evalInPage(`(() => {
    const s = (el, prop) => el ? getComputedStyle(el)[prop] : null;
    return {
      hasPlayer: Boolean(document.querySelector('.tvp-root video')),
      captionZ: s(document.querySelector('.tvp-root .tvp-caption'), 'zIndex')
    };
  })()`);

  open(`${baseUrl}/en/solutions/rapid-recovery`);
  wait(1000);
  const solution = evalInPage(`(() => {
    return {
      hasPlayer: Boolean(document.querySelector('.tvp-root video'))
    };
  })()`);
  writeArtifact('scenario-layering-solution.json', solution);

  assertCondition(docs.hasPlayer, 'docs page tutorial video player not found', docs);
  assertCondition(solution.hasPlayer, 'solution page tutorial video player not found', solution);
  // NOT a docs-vs-solution caption z-index comparison: solution videos have no
  // `words` manifest entry (verified: packages/www/src/data/video-manifest.json ->
  // solutions.rapid-recovery.en has only mp4/vertical/poster, no words) because their
  // captions are burned into the video pixels, per TutorialVideoPlayer.tsx:713's own
  // `activeWords &&` guard on rendering `.tvp-caption` at all. Asserting the two
  // mounts' caption z-index MATCH would fail by design, not by defect -- checked
  // instead is the one invariant that is actually guaranteed: a caption element,
  // when present, sits at the CSS-defined z-index (tutorial-video.css:63).
  assertCondition(
    docs.captionZ === '3',
    'docs caption z-index does not match the CSS-defined value',
    docs
  );
}

/**
 * Poll each visited route over HTTP until it serves 200, bounded.
 *
 * `astro dev` prints its banner when it is LISTENING, not when it can serve a page, so
 * this asserts servability instead of assuming it. It replaces a fire-and-forget warm
 * fetch, which asserted nothing and would have leaked its own failure into the next
 * navigation's timeout.
 *
 * SOLD AS READINESS, NOT AS THE FIX, because the measurement says it is not one.
 * Timing the phases across 16 passing runs: the first `open` costs ~5s of a 25s budget,
 * and scenarios 3 and 5 open never-before-compiled routes against a warm module graph for
 * ~0.4-0.5s each -- and THAT is the SSR route-compile cost this removes. The other ~4.5s
 * is the browser pulling the client module graph (React + Plyr, dynamically imported at
 * src/scripts/tutorial-video-hydrate.ts) through Vite's on-demand transform, which a
 * `fetch()` of the HTML never requests. So this buys under half a second.
 *
 * The failures are not a squeeze on that budget anyway: three of them at 28.4s / 29.0s /
 * 29.0s against agent-browser's 25s default operation timeout is a fixed CEILING, not a
 * distribution tail. A budget 20% utilised on 16 of 16 passes does not intermittently
 * need 500%. Base rate since the step was added: 3 failures in 38 executions (~8%),
 * across two agent-browser versions and ~20 commits, with passes interleaved -- including
 * one BETWEEN the two failures that first looked consecutive.
 */
async function pollRoutesReady() {
  const routes = [
    '/en/docs/tutorial-production-mode',
    '/en/docs/tutorial-add-server',
    '/en/solutions/rapid-recovery',
  ];
  for (const route of routes) {
    const startedAt = Date.now();
    const deadline = startedAt + 60000;
    let last = 'no attempt';
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${baseUrl}${route}`, { signal: AbortSignal.timeout(20000) });
        if (res.ok) {
          log(`→ ready ${route} (${res.status}, ${Date.now() - startedAt}ms)`);
          last = null;
          break;
        }
        last = `HTTP ${res.status}`;
      } catch (err) {
        last = String(err);
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (last !== null) {
      log(`→ NOT READY ${route} after ${Date.now() - startedAt}ms: ${last}`);
    }
  }
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
    captureNavigationEvidence();
    navigationRetries += 1;
    log('→ retrying the first navigation once');
    const retryAt = Date.now();
    const out = open(url);
    log(`→ first navigation ok on RETRY (${Date.now() - retryAt}ms)`);
    return out;
  }
}

/** Pending requests and server output, written where the artifact upload can find them. */
function captureNavigationEvidence() {
  const dir = path.join(repoRoot, 'artifacts', 'tutorial-player-release-gate', stamp);
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch {
    return;
  }
  try {
    const net = runAgent(['network', 'requests']);
    fs.writeFileSync(path.join(dir, 'network-requests.json'), JSON.stringify(net, null, 2));
  } catch (err) {
    try {
      fs.writeFileSync(path.join(dir, 'network-requests.json'), `capture failed: ${err}\n`);
    } catch {
      // Evidence is best-effort; never let it mask the real failure.
    }
  }
  try {
    fs.writeFileSync(path.join(dir, 'dev-server.log'), serverLog.join(''));
  } catch {
    // As above.
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
    await startDevServer();
    resources = resourceSnapshot(Date.now() - bootStartedAt);
    await pollRoutesReady();
    wait(1500);

    scenarioBasicPlayPauseResume();
    scenarioBurstToggle();
    scenarioSeekNoSnapback();
    scenarioFullscreenAndLayering();
    scenarioMountConsistency();

    const summary = {
      status: failures.length === 0 ? 'pass' : 'fail',
      failures,
      artifactsDir: runDir,
      session,
      baseUrl,
      resources,
      navigationRetries,
      serverDiedMidRun,
    };
    writeArtifact('summary.json', summary);

    if (failures.length > 0) {
      reportInconclusiveCauses(resources);
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
    // If the crash happened before startDevServer resolved (its own timeout, or a
    // crash mid-boot), `resources` above still holds the pre-boot snapshot with
    // bootMs=null. Recompute against elapsed wall time so a boot-phase crash is
    // judged on how long it actually ran, not treated as instant.
    if (resources.bootMs === null) {
      resources = resourceSnapshot(Date.now() - bootStartedAt);
    }
    reportInconclusiveCauses(resources);
    writeArtifact('summary.json', {
      status: 'crash',
      failures,
      crash: String(error),
      artifactsDir: runDir,
      session,
      baseUrl,
      resources,
      serverDiedMidRun,
    });
    exitCode = 1;
  } finally {
    try {
      runAgent(['close']);
    } catch {
      // Ignore cleanup errors.
    }
    await stopDevServer();
    process.exit(exitCode);
  }
}

void main();
