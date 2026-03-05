#!/usr/bin/env node

import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '../../..');
const artifactsRoot = path.join(repoRoot, 'artifacts', 'tutorial-player-release-gate');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const runDir = path.join(artifactsRoot, stamp);
const session = `tutorial-player-gate-${Date.now()}`;
const port = Number(process.env.TUTORIAL_PLAYER_GATE_PORT || '4511');
const baseUrl = `http://127.0.0.1:${port}`;

fs.mkdirSync(runDir, { recursive: true });

const failures = [];
let serverProc = null;
let exitCode = 0;

function log(message) {
  process.stdout.write(`${message}\n`);
}

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

function assertCondition(condition, message, details = null) {
  if (!condition) fail(message, details);
}

function isPlayingPhase(phase) {
  return phase === 'narrating' || phase === 'dwell' || phase === 'replaying';
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
    serverProc = spawn('npm', args, {
      cwd: repoRoot,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    const timeout = setTimeout(() => {
      reject(new Error('Timed out waiting for astro dev server to start'));
    }, 60000);

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
      reject(new Error(`astro dev exited early with code ${code}`));
    });
  });
}

async function stopDevServer() {
  if (!serverProc) return;
  const proc = serverProc;
  serverProc = null;
  await new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    proc.once('exit', done);
    proc.kill('SIGTERM');
    const timer = setTimeout(() => {
      try {
        proc.kill('SIGKILL');
      } catch {
        // Ignore kill errors on already-exited processes.
      }
      done();
    }, 4000);
    timer.unref();
  });
}

function clickPlaybackButton() {
  return evalInPage(`(() => {
    const btn = document.querySelector('.ap-control-bar .terminal-player-guided-toggle');
    if (!btn) return { ok: false, reason: 'missing-playback-button' };
    btn.click();
    return { ok: true };
  })()`);
}

function burstPlaybackClicks(count, gapMs) {
  return evalInPage(`(() => {
    const btn = document.querySelector('.ap-control-bar .terminal-player-guided-toggle');
    if (!btn) return { ok: false, reason: 'missing-playback-button' };
    for (let i = 0; i < ${count}; i += 1) {
      window.setTimeout(() => btn.click(), i * ${gapMs});
    }
    return { ok: true };
  })()`);
}

function currentState() {
  return evalInPage(`(() => {
    const root = document.querySelector('.terminal-tutorial');
    const btn = document.querySelector('.ap-control-bar .terminal-player-guided-toggle');
    return {
      phase: root?.dataset.guidedPhase ?? null,
      step: root?.dataset.guidedStep ?? null,
      buttonLabel: btn?.getAttribute('aria-label') ?? null
    };
  })()`);
}

function sampledStates(durationMs, tickMs) {
  return evalInPage(`(() => new Promise((resolve) => {
    const rows = [];
    const start = Date.now();
    const collect = () => {
      const root = document.querySelector('.terminal-tutorial');
      rows.push({
        t: Date.now() - start,
        phase: root?.dataset.guidedPhase ?? null,
        step: root?.dataset.guidedStep ?? null
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
  open(`${baseUrl}/en/docs/tutorial-ops`);
  wait(1200);
  clearConsole();

  assertCondition(clickPlaybackButton()?.ok, 'play button click failed at start');
  wait(1400);
  const started = currentState();
  assertCondition(isPlayingPhase(started.phase), 'start did not enter playing phase', started);

  assertCondition(clickPlaybackButton()?.ok, 'pause button click failed');
  wait(900);
  const paused = currentState();
  assertCondition(paused.phase === 'pausedByUser', 'pause did not enter pausedByUser', paused);
  wait(1200);
  const pausedStable = currentState();
  assertCondition(
    pausedStable.phase === 'pausedByUser',
    'pause state did not remain stable',
    pausedStable
  );

  assertCondition(clickPlaybackButton()?.ok, 'resume button click failed');
  wait(1400);
  const resumed = currentState();
  assertCondition(isPlayingPhase(resumed.phase), 'resume did not re-enter playing phase', resumed);

  writeArtifact('scenario-basic-console.json', readConsole());
  screenshot('scenario-basic.png');
}

function scenarioBurstToggle() {
  log('→ scenario: burst toggle resilience');
  open(`${baseUrl}/en/docs/tutorial-ops`);
  wait(1000);
  clearConsole();

  assertCondition(clickPlaybackButton()?.ok, 'initial click failed before burst');
  wait(350);
  assertCondition(burstPlaybackClicks(6, 80)?.ok, 'burst click scheduling failed');

  const rows = sampledStates(12000, 700);
  writeArtifact('scenario-burst-states.json', rows);
  writeArtifact('scenario-burst-console.json', readConsole());
  screenshot('scenario-burst.png');

  const allNarratingStep0 =
    rows.length > 0 && rows.every((row) => row.phase === 'narrating' && row.step === '0');
  assertCondition(
    !allNarratingStep0,
    'burst caused permanent narrating-step0 loop',
    rows.slice(-5)
  );
}

function scenarioSeekNoSnapback() {
  log('→ scenario: seek no snapback');
  open(`${baseUrl}/en/docs/tutorial-setup`);
  wait(1200);

  const hasDebug = evalInPage(
    `(() => Boolean(window.__tutorialDebug && window.__tutorialDebug.seekToSec))()`
  );
  assertCondition(hasDebug, '__tutorialDebug.seekToSec missing in dev session');
  if (!hasDebug) return;

  assertCondition(clickPlaybackButton()?.ok, 'play click failed before seek');
  wait(1200);
  evalInPage(`(() => window.__tutorialDebug.seekToSec(48))()`);

  const rows = sampledStates(9000, 700);
  writeArtifact('scenario-seek-states.json', rows);
  screenshot('scenario-seek.png');

  const firstHigh = rows.findIndex((row) => Number(row.step) >= 5);
  assertCondition(firstHigh !== -1, 'seek did not move to expected later step', rows);
  if (firstHigh !== -1) {
    const snapback = rows.slice(firstHigh + 1).find((row) => Number(row.step) < 5);
    assertCondition(!snapback, 'seek snapped back to earlier step later', {
      firstHigh,
      snapback,
      rows,
    });
  }
}

function scenarioFullscreenAndLayering() {
  log('→ scenario: fullscreen and layering');
  open(`${baseUrl}/en/docs/tutorial-ops`);
  wait(1000);
  assertCondition(clickPlaybackButton()?.ok, 'play click failed before fullscreen');
  wait(900);

  const enter = evalInPage(`(() => {
    const btn = document.querySelector('.ap-control-bar .ap-fullscreen-button');
    if (!btn) return { ok: false, reason: 'missing-fullscreen-button' };
    btn.click();
    return { ok: true };
  })()`);
  assertCondition(enter?.ok, 'failed to click fullscreen button', enter);
  wait(700);

  const fsState = evalInPage(`(() => ({
    fullscreen: Boolean(document.fullscreenElement),
    captionFs: Boolean(document.querySelector('.terminal-player-caption-layer--fullscreen'))
  }))()`);
  assertCondition(fsState.fullscreen, 'fullscreen not active after toggle', fsState);
  assertCondition(fsState.captionFs, 'fullscreen caption layer missing', fsState);

  evalInPage(
    `(() => { document.querySelector('.ap-control-bar .ap-fullscreen-button')?.click(); return true; })()`
  );
  wait(500);
  const exitState = evalInPage(`(() => ({ fullscreen: Boolean(document.fullscreenElement) }))()`);
  assertCondition(!exitState.fullscreen, 'fullscreen did not exit', exitState);

  const docsZ = evalInPage(`(() => {
    const s = (el, prop) => el ? getComputedStyle(el)[prop] : null;
    return {
      playerZ: s(document.querySelector('.terminal-tutorial'), 'zIndex'),
      controlZ: s(document.querySelector('.terminal-tutorial-player-inner .ap-control-bar'), 'zIndex'),
      captionZ: s(document.querySelector('.terminal-player-caption-layer'), 'zIndex'),
      shareZ: s(document.querySelector('.heading-share'), 'zIndex')
    };
  })()`);
  writeArtifact('scenario-layering-docs.json', docsZ);
  assertCondition(
    Number(docsZ.playerZ) > Number(docsZ.shareZ),
    'player layer should sit above heading-share on docs',
    docsZ
  );
}

function scenarioHomeConsistency() {
  log('→ scenario: home/docs consistency');
  open(`${baseUrl}/en/docs/tutorial-ops`);
  wait(800);
  const docs = evalInPage(`(() => {
    const s = (el, prop) => el ? getComputedStyle(el)[prop] : null;
    return {
      playerZ: s(document.querySelector('.terminal-tutorial'), 'zIndex'),
      captionZ: s(document.querySelector('.terminal-player-caption-layer'), 'zIndex')
    };
  })()`);

  open(`${baseUrl}/en`);
  wait(1000);
  const home = evalInPage(`(() => {
    const s = (el, prop) => el ? getComputedStyle(el)[prop] : null;
    return {
      hasPlayer: Boolean(document.querySelector('.terminal-tutorial')),
      playerZ: s(document.querySelector('.terminal-tutorial'), 'zIndex'),
      captionZ: s(document.querySelector('.terminal-player-caption-layer'), 'zIndex')
    };
  })()`);
  writeArtifact('scenario-layering-home.json', home);

  assertCondition(home.hasPlayer, 'home page terminal tutorial not found');
  assertCondition(docs.playerZ === home.playerZ, 'player z-index differs between docs and home', {
    docs,
    home,
  });
  assertCondition(
    docs.captionZ === home.captionZ,
    'caption z-index differs between docs and home',
    { docs, home }
  );
}

async function main() {
  try {
    execFileSync('agent-browser', ['--version'], { encoding: 'utf8' });
  } catch {
    fail('agent-browser is not installed or not accessible in PATH');
    process.exit(1);
  }

  try {
    log(`→ starting astro dev server on ${baseUrl}`);
    await startDevServer();
    wait(1500);

    scenarioBasicPlayPauseResume();
    scenarioBurstToggle();
    scenarioSeekNoSnapback();
    scenarioFullscreenAndLayering();
    scenarioHomeConsistency();

    const summary = {
      status: failures.length === 0 ? 'pass' : 'fail',
      failures,
      artifactsDir: runDir,
      session,
      baseUrl,
    };
    writeArtifact('summary.json', summary);

    if (failures.length > 0) {
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
    writeArtifact('summary.json', {
      status: 'crash',
      failures,
      crash: String(error),
      artifactsDir: runDir,
      session,
      baseUrl,
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
