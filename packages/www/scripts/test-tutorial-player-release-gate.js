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
  const out = execFileSync('agent-browser', commandArgs, {
    cwd: repoRoot,
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
  });
  const parsed = JSON.parse(out);
  if (!parsed.success) {
    throw new Error(`agent-browser failed: ${JSON.stringify(parsed.error)}`);
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

    const onData = (chunk) => {
      const text = String(chunk);
      if (text.includes('ready') || text.includes(`http://127.0.0.1:${port}`)) {
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
  open(`${baseUrl}/en/docs/tutorial-production-mode`);
  wait(1200);
  clearConsole();

  assertCondition(clickPlaybackButton()?.ok, 'play button click failed at start');
  wait(1400);
  const started = currentState();
  assertCondition(isPlaying(started), 'start did not enter playing state', started);

  assertCondition(clickPlaybackButton()?.ok, 'pause button click failed');
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

  assertCondition(clickPlaybackButton()?.ok, 'resume button click failed');
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

  assertCondition(clickPlaybackButton()?.ok, 'initial click failed before burst');
  wait(350);
  assertCondition(burstPlaybackClicks(6, 80)?.ok, 'burst click scheduling failed');

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

  assertCondition(clickPlaybackButton()?.ok, 'play click failed before seek');
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
  assertCondition(clickPlaybackButton()?.ok, 'play click failed before fullscreen');
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
