// Runner profiler: start a sampler in `main`, stop it and write the panel in
// `post`.
//
// WHY THIS IS A JAVASCRIPT ACTION. `runs.post` is JavaScript-actions-only --
// composite actions have no equivalent -- and `post-if` defaults to always(),
// so the panel is still written when the job FAILS, which is exactly the run
// you want a profile of. There is no `background:` step keyword to lean on: it
// has been announced but is absent from the syntax reference and has no schema.
//
// NO DEPENDENCIES, ON PURPOSE. Not even @actions/core. A JS action's node_modules
// has to be vendored into the repo, and this tool exists to save runner time,
// not to add 40 files to every checkout. Everything here is node stdlib against
// the runner's own bundled node, which is why the SAMPLER is pure bash: node's
// presence inside the ubuntu-slim container is exactly the thing the probe
// workflow is there to establish, and the sampler must work before it is known.

// ESM, NOT CommonJS, and not by preference. The runner executes this file with
// plain `node`, which resolves the nearest package.json -- and the repo root's
// declares "type": "module". A `require()` here dies with "require is not
// defined in ES module scope" on the runner exactly as it does locally, before
// a single sample is taken. Caught by driving a real main->post cycle; reading
// the file could not have shown it.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..', '..');
const SAMPLER = path.join(REPO_ROOT, '.ci', 'scripts', 'ci', 'profiler', 'sampler-linux.sh');
const PANEL = path.join(REPO_ROOT, '.ci', 'scripts', 'ci', 'profiler', 'panel.sh');

function input(name, fallback) {
  const key = `INPUT_${name.toUpperCase().replaceAll(' ', '_')}`;
  const v = process.env[key];
  return v === undefined || v === '' ? fallback : v.trim();
}

function saveState(name, value) {
  const file = process.env.GITHUB_STATE;
  if (!file) return;
  fs.appendFileSync(file, `${name}=${value}${os.EOL}`);
}

function notice(level, message) {
  process.stdout.write(`::${level}::profiler: ${message}${os.EOL}`);
}

// Synchronous, fork-free pause. The post hook has to give a SIGTERM'd sampler a
// moment to leave, and there is no blocking sleep in node's stdlib.
function sleepMs(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

// "Alive" means alive AND still the sampler. A bare process.kill(pid, 0) says
// only that SOMETHING holds that pid, and pids are recycled: a job that spawns
// a few thousand short-lived processes between main and post can hand our
// number to something else, and the post hook would then SIGTERM an unrelated
// process in the middle of the job it is supposed to be observing.
function alive(pid) {
  try {
    process.kill(pid, 0);
  } catch {
    return false;
  }
  try {
    const cmdline = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8');
    return cmdline.includes('sampler-linux.sh');
  } catch {
    // No /proc entry: it died between the signal probe and the read.
    return false;
  }
}

function tail(file, bytes) {
  try {
    const data = fs.readFileSync(file, 'utf8');
    return data.slice(-bytes).trim().replaceAll(/\s+/g, ' ');
  } catch {
    return '';
  }
}

function runMain() {
  if (process.platform !== 'linux') {
    // The five non-Linux install jobs use neither this action nor slim, and can
    // never move there (ubuntu-slim is x64 Linux only), so a cross-platform
    // sampler would buy nothing but surface area.
    saveState('skip', `unsupported platform ${process.platform}`);
    return;
  }
  if (!fs.existsSync(SAMPLER)) {
    saveState('skip', `sampler not found at ${SAMPLER}`);
    notice('warning', `sampler not found at ${SAMPLER}; not profiling`);
    return;
  }

  const interval = input('interval', '10');
  const strict = input('strict', 'false') === 'true' ? 'true' : 'false';
  const label = input('runner-label', process.env.RUNNER_LABEL || 'unknown');
  const tmp = process.env.RUNNER_TEMP || os.tmpdir();
  const stamp = `${process.env.GITHUB_JOB || 'job'}-${process.pid}`;
  const out = path.join(tmp, `profiler-${stamp}.tsv`);
  const log = path.join(tmp, `profiler-${stamp}.log`);

  let fd;
  try {
    fd = fs.openSync(log, 'a');
  } catch (err) {
    notice('warning', `cannot open sampler log ${log}: ${err.message}; not profiling`);
    saveState('skip', 'sampler log not writable');
    return;
  }

  const child = spawn('bash', [SAMPLER, '--out', out, '--interval', interval], {
    detached: true,
    stdio: ['ignore', fd, fd],
    env: { ...process.env, PROFILER_RUNNER_LABEL: label },
  });
  child.unref();
  fs.closeSync(fd);

  saveState('pid', String(child.pid));
  saveState('out', out);
  saveState('log', log);
  saveState('start', String(Date.now()));
  saveState('strict', strict);
  saveState('label', label);
  process.stdout.write(
    `profiler: sampling every ${interval}s into ${out} (pid ${child.pid}, runner label ${label})${os.EOL}`
  );
}

// What the main phase recorded, with the defaults a run that never got there
// would leave behind.
function readSamplerState() {
  return {
    pid: Number(process.env.STATE_pid || 0),
    out: process.env.STATE_out || '',
    log: process.env.STATE_log || '',
    start: Number(process.env.STATE_start || 0),
    strict: process.env.STATE_strict === 'true' ? 'true' : 'false',
  };
}

// Stop a live sampler, returning the note that describes how it went.
function stopSampler(pid) {
  let note = '';
  try {
    process.kill(pid, 'SIGTERM');
  } catch (err) {
    note = `could not signal sampler pid ${pid}: ${err.message}`;
  }

  for (let i = 0; i < 20 && alive(pid); i++) sleepMs(100);
  if (!alive(pid)) return note;

  try {
    process.kill(pid, 'SIGKILL');
  } catch {
    /* already gone between the check and the signal */
  }
  return 'the sampler had to be SIGKILLed; the final sample may be truncated';
}

// A sampler that is already gone is the failure worth naming: the panel must
// say so rather than render whatever partial file it left behind as if it were
// the whole job.
function samplerGoneNote(log) {
  const why = tail(log, 400);
  return `the sampler was no longer running when the job ended${why ? ` (last log: ${why})` : ''}`;
}

function runPost() {
  const skip = process.env.STATE_skip;
  if (skip) {
    process.stdout.write(`profiler: skipped (${skip})${os.EOL}`);
    return;
  }
  const { pid, out, log, start, strict } = readSamplerState();

  if (!out) {
    notice('warning', 'no sampler state recorded; the main step never ran');
    return;
  }

  const wasAlive = pid > 0 && alive(pid);
  const note = wasAlive ? stopSampler(pid) : samplerGoneNote(log);

  const wallS = start > 0 ? Math.round((Date.now() - start) / 1000) : 0;
  const res = spawnSync('bash', [PANEL], {
    stdio: 'inherit',
    env: {
      ...process.env,
      PROFILER_SAMPLE_FILE: out,
      PROFILER_STRICT: strict,
      PROFILER_WALL_S: String(wallS),
      PROFILER_TITLE: process.env.GITHUB_JOB || '',
      PROFILER_NOTE: note,
    },
  });
  if (res.error) {
    notice('warning', `panel.sh could not be run: ${res.error.message}`);
    return;
  }
  if (res.status !== 0) {
    // panel.sh only exits non-zero under strict; anything else is its own bug
    // and must not be swallowed.
    process.exitCode = res.status;
  }
}

// main and post are the SAME file, so the phase is carried in state. This is
// the marker @actions/core writes for the same reason; it is reproduced here
// rather than depended on, because a state key is cheaper than a vendored
// dependency tree.
if (process.env.STATE_isPost === 'true') {
  runPost();
} else {
  // Saved BEFORE the work: an early return from runMain (unsupported platform,
  // missing sampler) must still leave a post phase that can explain itself.
  saveState('isPost', 'true');
  runMain();
}
