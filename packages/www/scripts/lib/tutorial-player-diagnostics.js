/**
 * Readiness and failure-evidence helpers for the tutorial-player release gate.
 *
 * SPLIT OUT BECAUSE THE GATE HIT max-lines (532 against 512, and 533 again on 2026-10-05 when the
 * warm-up landed), not as architecture for its own sake. These are the natural seam: neither drives a scenario, both exist purely
 * so a timeout arrives with evidence attached, and every dependency is passed in rather
 * than closed over, so they can be exercised without booting a dev server.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

/**
 * Poll each route over HTTP until it serves 200, bounded.
 *
 * `astro dev` prints its banner when it is LISTENING, not when it can serve a page, so
 * this asserts servability instead of assuming it. It replaced a fire-and-forget warm
 * fetch, which asserted nothing and would have leaked its own failure into the next
 * navigation's timeout.
 *
 * SOLD AS READINESS, NOT AS A FIX FOR THE FLAKE, because the measurement says it is not
 * one. Across 16 passing runs the first `open` costs ~5s of a 25s budget, and scenarios
 * opening never-compiled routes against a warm module graph cost ~0.4-0.5s each -- that
 * difference is the SSR route-compile cost this removes, so it buys under half a second.
 * The failures are not a squeeze on that budget: three at 28.4s / 29.0s / 29.0s against
 * agent-browser's 25s default is a fixed CEILING, not a distribution tail.
 */
export async function pollRoutesReady(baseUrl, routes, log) {
  for (const route of routes) {
    const startedAt = Date.now();
    const deadline = startedAt + 60000;
    let ready = false;
    let last = 'no attempt';
    while (!ready && Date.now() < deadline) {
      try {
        const res = await fetch(`${baseUrl}${route}`, { signal: AbortSignal.timeout(20000) });
        if (res.ok) {
          ready = true;
          log(`→ ready ${route} (${res.status}, ${Date.now() - startedAt}ms)`);
          break;
        }
        last = `HTTP ${res.status}`;
      } catch (err) {
        last = String(err);
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!ready) {
      log(`→ NOT READY ${route} after ${Date.now() - startedAt}ms: ${last}`);
    }
  }
}

/**
 * Pending requests and dev-server output, written where the artifact upload can find them.
 *
 * This is the whole point of the instrumentation: three failures reported only "Operation
 * timed out. The page may still be loading or the element may not exist." -- naming
 * neither what was pending nor how long a healthy run takes. The network dump either
 * convicts the stalled subresource or kills that hypothesis.
 *
 * Best-effort throughout: evidence collection must never mask the failure it documents.
 */
export function captureNavigationEvidence({ dir, runAgent, serverLog, log }) {
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch (err) {
    log(`→ could not create ${dir}: ${err}`);
    return;
  }
  try {
    const net = runAgent(['network', 'requests']);
    fs.writeFileSync(path.join(dir, 'network-requests.json'), JSON.stringify(net, null, 2));
  } catch (err) {
    try {
      fs.writeFileSync(path.join(dir, 'network-requests.json'), `capture failed: ${err}\n`);
    } catch {
      log('→ could not write network-requests.json');
    }
  }
  try {
    fs.writeFileSync(path.join(dir, 'dev-server.log'), serverLog.join(''));
  } catch {
    log('→ could not write dev-server.log');
  }
}

/** Prints the "this may not be a real regression" context, most-specific cause first. */
export function reportInconclusiveCauses(devServer, resources) {
  if (devServer.diedMidRun) {
    process.stderr.write(
      `\n⚠ THE DEV SERVER EXITED MID-RUN (code ${devServer.diedMidRun.code}) -- everything after ` +
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
    return;
  }
  if (resources.slowBoot) {
    // THE OPPOSITE READING, SAID OUT LOUD. A slow boot on an IDLE machine is the signature of something that never became ready, not of a busy runner, and the reader needs pushing toward the evidence rather than away from it.
    process.stderr.write(
      `\n⚠ THE SERVER TOOK ${resources.bootMs}ms TO BOOT, but the machine was IDLE ` +
        `(load/core=${resources.loadPerCore.toFixed(2)}). That is NOT resource contention. ` +
        `Read serverLog in summary.json: if it contains a ready banner, the server started ` +
        `fine and the READINESS MATCHER failed to see it.\n`
    );
  }
}

/**
 * Wait until the player is READY TO TAKE A CLICK, not merely until its play control exists.
 *
 * WHY A FIXED SLEEP WAS REPLACED. The docs mounts build through an IntersectionObserver and a
 * dynamic `import()` of 122 KB of player, and on a dev server that import is unbundled:
 * measured on 2026-09-09, the first route of a run compiled in 18.4s and the first navigation
 * took 8.4s, after which `wait(1200)` was nowhere near enough. The click then ran against an
 * element that did not exist yet and the whole scenario reported failures one step out of phase.
 * Only the FIRST navigation of a run is slow enough to hit it, which is why a sleep survived.
 *
 * WHY THE CONTROL ALONE IS NOT ENOUGH EITHER. The control appears the moment Plyr builds its
 * DOM, while the media element is still at readyState 0 (measured: 0 on the first sample, 4
 * about 100 ms later on an idle machine) and the control sits below the fold (y=949 in a
 * 577 px viewport), so the click first has to scroll it into view. CI run 110606567114 died
 * this way: on a loaded runner the very first click was refused ("play button click failed at
 * start"), the player stayed paused at 0, and every later step ran one phase off -- the pause
 * click started it and the resume click paused it.
 *
 * READY = the control exists, the media has its metadata, and the control has held the same
 * position for three consecutive samples, so no layout shift can move it under the click. The
 * poll runs inside the page (one round trip), bounded at SCENARIO_READY_MS (20 s) for a scenario and
 * WARMUP_READY_MS for the warm-up that pays the first visit's cost (`warmUpPlayer`).
 *
 * A RELOAD UNDER THE POLL IS RETRIED, NOT REPORTED. CI run 37131294077 (job 111227243538) died
 * 0.2 s after the first navigation with `CDP error (Runtime.evaluate): Inspected target navigated
 * or closed`: the dev server reloaded the page once while the poll was in flight (the shape of
 * its first-visit dependency re-optimization for the lazily imported player), which destroys the
 * evaluation context. The page is still loading, not broken, so the poll starts again in the new
 * document. The deadline is fixed once, in this process, and baked into the polled code, so an
 * attempt that evalInPage repeats after a reload still ends at the same moment: one 20 s budget.
 */
export function waitForPlayerReady(evalInPage, budgetMs, pollMs) {
  // ONE EVAL CANNOT OUTLIVE agent-browser's CDP timeout (a 120 s poll died with "CDP command timed out: Runtime.evaluate", 2026-10-05), so a budget longer than one poll is spent as a series of polls of at most `pollMs`.
  const deadline = Date.now() + budgetMs;
  let last = { ok: false, reason: 'no poll ran' };
  while (Date.now() < deadline) {
    last = pollPlayerReady(evalInPage, Math.min(pollMs, deadline - Date.now()));
    if (last.ok) return last;
  }
  return last;
}

function pollPlayerReady(evalInPage, budgetMs) {
  try {
    const state = evalInPage(`(() => new Promise((resolve) => {
      const SELECTOR = '.tvp-root [data-plyr="play"]';
      const deadline = ${Date.now() + budgetMs};
      let last = null;
      let stable = 0;
      const poll = () => {
        const control = document.querySelector(SELECTOR);
        const video = document.querySelector('.tvp-root video');
        const rect = control ? control.getBoundingClientRect() : null;
        const key = rect ? [rect.x, rect.y, rect.width, rect.height].join(',') : null;
        const metadata = Boolean(video) && video.readyState >= 1;
        stable = key !== null && key === last ? stable + 1 : 0;
        last = key;
        if (control && metadata && stable >= 2) return resolve({ ready: true });
        if (Date.now() > deadline) {
          return resolve({ ready: false, control: Boolean(control), metadata, stable });
        }
        setTimeout(poll, 100);
      };
      poll();
    }))()`);
    return state?.ready === true ? { ok: true } : { ok: false, reason: JSON.stringify(state) };
  } catch (error) {
    return { ok: false, reason: String(error) };
  }
}

/**
 * Walks a failure's structured details for the document stamp (`sameDocument`, set per document
 * by the gate's open()). `false` means the page reloaded after the scenario opened it, which is
 * dev-server noise; `true` means the document survived, so a missing or wrong player is a
 * product defect. Returns whether any `false` and any `true` were seen.
 */
function documentStampEvidence(details) {
  const seen = { reloaded: false, sameDocument: false };
  const walk = (node) => {
    if (node === null || typeof node !== 'object') return;
    if (node.sameDocument === false) seen.reloaded = true;
    if (node.sameDocument === true) seen.sameDocument = true;
    for (const value of Object.values(node)) walk(value);
  };
  walk(details);
  return seen;
}

/**
 * Runs a scenario; when it fails ONLY with evidence that the page reloaded under it, runs it once
 * more on a fresh load and says so loudly. A second failure, a failure with no reload evidence,
 * or any failure whose evidence shows the document survived (`sameDocument: true`) is kept as is:
 * a real player failure is never retried. Returns the scenario's reload retries (0 or 1).
 */
export function runScenarioRetryingReload({ name, run, failures, log }) {
  const before = failures.length;
  run();
  const fresh = failures.slice(before);
  if (fresh.length === 0) return 0;
  const evidence = fresh.map((f) => documentStampEvidence(f.details));
  if (!evidence.some((e) => e.reloaded) || evidence.some((e) => e.sameDocument)) return 0;
  log(
    `⚠ RETRY: scenario "${name}" failed with sameDocument=false (the page reloaded mid-scenario, ` +
      `a test-environment event, not a player verdict); discarding ${fresh.length} failure(s) and ` +
      `re-running it ONCE on a fresh load: ${fresh.map((f) => f.message).join(' | ')}`
  );
  failures.length = before;
  run();
  if (failures.length > before) {
    log(`⚠ RETRY of scenario "${name}" failed too; the failure stands`);
  } else {
    log(`⚠ RETRY of scenario "${name}" passed after one reload retry`);
  }
  return 1;
}

/**
 * The test seam behind TUTORIAL_PLAYER_GATE_PLANT_RELOADS=N (off by default): each call reloads the
 * page while N plants remain, so a run proves the reload retry absorbs one reload and fails on two.
 */
export function makeReloadPlant(
  { evalInPage, wait, log },
  count = Number(process.env.TUTORIAL_PLAYER_GATE_PLANT_RELOADS ?? 0)
) {
  let left = count;
  return () => {
    if (left <= 0) return;
    left -= 1;
    log('→ PLANTED reload (TUTORIAL_PLAYER_GATE_PLANT_RELOADS) in the seek scenario');
    evalInPage('(() => { setTimeout(() => location.reload(), 0); })()');
    wait(1500);
  };
}
