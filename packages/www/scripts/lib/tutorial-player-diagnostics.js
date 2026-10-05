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
