// The tutorial player gate's throwaway astro dev server: start, the mid-run death flag, the captured log, and stop. Moved out of test-tutorial-player-release-gate.js to keep that script inside its line budget.
import { spawn } from 'node:child_process';
import net from 'node:net';
import os from 'node:os';
import process from 'node:process';
import { boundPort, boundPortMismatch, isDevServerReady, stripAnsi } from './dev-server-ready.js';

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
export function resourceSnapshot(bootMs) {
  const cpuCount = os.cpus().length || 1;
  const loadPerCore = os.loadavg()[0] / cpuCount;
  // Half the boot budget: a clean cold boot measured 84s, so crossing 90s is already an outlier, not just "a bit slow".
  const slowBoot = bootMs !== null && bootMs > 90000;
  const highLoad = loadPerCore > 1.2;
  return {
    cpuCount,
    loadavg1m: os.loadavg()[0],
    loadPerCore,
    bootMs,
    slowBoot,
    // PRESSURE IS WHAT THE LOAD AVERAGE SAYS, NOTHING ELSE. This used to be `slowBoot || highLoad`, which made every boot timeout announce "SYSTEM UNDER LOAD" -- because slowBoot is the timeout restated, not evidence about the
    // machine. Printed verbatim in CI on 2026-09-01: "SYSTEM UNDER LOAD (load/core=0.06)".
    // An instrument that says to dismiss the failure it just detected is worse than one that says nothing, and this one bought five re-runs of a real bug.
    pressureDetected: highLoad,
  };
}

/**
 * A port the kernel just handed out, so a second gate run, a leftover astro or another session's server cannot already hold it. Ephemeral ports sit above every port Chromium refuses (ERR_UNSAFE_PORT). Still verified against the banner after start: the pick narrows the race, the banner check closes it.
 */
export async function pickFreePort() {
  return await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

/** One gate run's dev server. `diedMidRun` is read live, since the exit handler sets it after start() has settled. */
export function createDevServer({ repoRoot, port }) {
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
  // PIPED SINCE FOREVER AND NEVER READ. On a navigation timeout this is the only record of what the server thought it was doing, so it is kept and written out on failure.
  const serverLog = [];
  let intentionalShutdown = false;
  let serverProc = null;

  async function start() {
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
      // `detached: true` makes this its own process group leader. PROVEN NECESSARY, not precautionary: `npm run dev` spawns `astro` as a grandchild, and killing just the npm PID does not propagate to it -- verified live 2026-08-28, a fully successful gate run (exit 0, all 5 scenarios passing) still left `astro` running and holding port 4511 afterward. stopDevServer() below signals the whole group (`-proc.pid`), which reaches the grandchild too.
      serverProc = spawn('npm', args, {
        cwd: repoRoot,
        env: process.env,
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: true,
      });

      // A cold `astro dev` start (no vite cache, content store rebuild) measured 84s on a loaded devbox; CI runners hit the same cold path every run, so 60s under-times it. 180s leaves headroom without masking a real hang.
      const timeout = setTimeout(() => {
        reject(new Error('Timed out waiting for astro dev server to start'));
      }, 180000);

      // WAITING FOR THE BANNER. Three defects lived here, in order, and the middle one was a WRONG DIAGNOSIS of the third -- worth recording, because it cost four re-runs that each looked like infrastructure flake.
      //
      // 1. The original test was `text.includes('ready')`. "address already in use"
      //    CONTAINS "ready", so an EADDRINUSE line read as "the server is up" and the run
      //    would have proceeded against somebody else's listener. Tightening it was right.
      // 2. The tightened regex was then blamed on CHUNK BOUNDARIES -- the theory being that
      //    `onData` sees whatever bytes arrive together, so a split inside the banner leaves
      //    neither half matching. The buffer was made cumulative to fix that. THE THEORY WAS
      //    WRONG and the change did not help: the very next run timed out identically.
      // 3. The real cause, measured 2026-09-01 by running the command both ways: GitHub
      //    Actions always sets `CI=true`, astro's colour library treats that as
      //    colour-capable with no TTY, and the coloured banner puts an escape sequence
      //    exactly between `in` and the space -- `\x1b[2mready in\x1b[22m 4739`. The
      //    matcher returns TRUE on the plain capture and FALSE on the CI capture, byte for
      //    byte. So it could never go green in CI and always went green locally, which is
      //    precisely the shape that reads as a flaky runner.
      //
      // The fix is to strip ANSI on INGEST (see ./lib/dev-server-ready.js), not to teach one regex about escape codes. That keeps the artifact readable and makes every future matcher over this buffer colour-proof by construction rather than by remembering.
      //
      // Both host spellings are matched because astro prints the host it was GIVEN: `localhost` by default, and `127.0.0.1` under `--host 127.0.0.1`, which is how this
      // gate starts it. An earlier comment here asserted astro "never prints 127.0.0.1";
      // that was wrong, and a real capture is what settled it.
      const onData = (chunk) => {
        serverLog.push(stripAnsi(String(chunk)));
        const text = serverLog.join('');
        // A moved port is a failure the instant it is printed: the browser must never be pointed at a port this server does not hold.
        const mismatch = boundPortMismatch(text, port);
        if (mismatch) {
          clearTimeout(timeout);
          reject(new Error(mismatch));
          return;
        }
        // Ready AND the Local URL seen: the banner's port is then proven equal to `port` by the check above.
        if (isDevServerReady(text) && boundPort(text) !== null) {
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

  async function stop() {
    if (!serverProc) return;
    const proc = serverProc;
    serverProc = null;
    intentionalShutdown = true;
    // `proc`'s own 'exit' event is NOT a reliable signal that the whole group is dead -- PROVEN live 2026-08-28: npm (the direct child, `proc` here) exits fast on SIGTERM while `astro` (its grandchild, still in its own graceful shutdown) keeps running; the old code resolved on npm's exit and `process.exit()` in main()'s finally then killed the whole script before the SIGKILL safety-net timer (`timer.unref()`'d, so it never survives process.exit()) got a chance to fire. astro was left holding the port on EVERY run, including fully passing ones. Fix: always send an unconditional group-wide SIGKILL after a short grace window, never conditionally.
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

  // PLAYER SELECTORS, verified against packages/www/src/components/TutorialVideoPlayer.tsx at HEAD (2026-08-28): the player root is `.tvp-shell > .tvp-root`, hydrated by tutorial-video-hydrate.ts onto `.tutorial-video-container[data-video-src]` (docs) or `.video-player-mount[data-video-src]` (solution-page hero). Plyr wraps the real
  // `<video>` and renders standard `[data-plyr="X"]` control buttons (controls list at
  // TutorialVideoPlayer.tsx:362-376 includes 'play' and 'fullscreen'), toggling `.plyr--playing` / `.plyr--fullscreen-active` on the `.plyr` wrapper it inserts. This replaces the TerminalPlayer-era `.ap-control-bar`/`.terminal-tutorial`/ `window.__tutorialDebug` surface, deleted wholesale in 80a000965 (2026-05-27) -- see agent/PLAN-fix-tutorial-player-debug-hook-attachment.md for the full trace.

  return {
    start,
    stop,
    log: serverLog,
    get diedMidRun() {
      return serverDiedMidRun;
    },
  };
}
