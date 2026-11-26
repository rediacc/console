/**
 * Controls for scripts/lib/runtmp.ts, the TypeScript twin of .ci/rediacc_ci/runtmp.py.
 *
 * Every case drives a REAL child process: a normal exit, SIGTERM with the signal hook, SIGKILL, and a planted defect
 * (SIGTERM with no hook) that must leave the dir, which proves the "removed" verdicts could have failed. The
 * cross-language cases prove the two modules share one stamp: Python's `sweep_dead` removes a dead TypeScript run dir
 * and the TypeScript `sweepDead` removes a dead Python one.
 *
 *   npx tsx scripts/__tests__/runtmp.control.ts
 */
import { type ChildProcess, spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

import { installSignalCleanup, runDir, shared, stamp, sweepDead } from '../lib/runtmp.js';

const PY_MODULE = path.resolve(import.meta.dirname, '../../.ci/rediacc_ci/runtmp.py');

let bad = 0;
function check(ok: boolean, what: string): void {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) bad += 1;
}

type Mode = 'plain' | 'hooked' | 'throwing' | 'unhooked';

function childMain(mode: Mode, base: string): void {
  const dir = runDir('rtctl-', base);
  fs.writeFileSync(path.join(dir, 'f'), 'x');
  if (mode === 'hooked') installSignalCleanup();
  if (mode === 'throwing')
    installSignalCleanup(() => {
      throw new Error('cleanup-boom');
    });
  process.stdout.write(`${dir}\n`);
  if (mode === 'plain') process.exit(0);
  setInterval(() => undefined, 1000);
}

async function startChild(
  mode: Mode,
  base: string
): Promise<{ child: ChildProcess; dir: string; stderr: () => string }> {
  const child = spawn(
    process.execPath,
    [...process.execArgv, import.meta.filename, 'child', mode, base],
    { stdio: ['ignore', 'pipe', 'pipe'] }
  );
  let err = '';
  child.stderr?.on('data', (d: Buffer) => {
    err += d.toString();
  });
  const dir = await new Promise<string>((resolve, reject) => {
    let buf = '';
    child.stdout?.on('data', (d: Buffer) => {
      buf += d.toString();
      if (buf.includes('\n')) resolve(buf.split('\n')[0]);
    });
    child.on('exit', () => reject(new Error(`child (${mode}) exited before reporting its dir`)));
  });
  return { child, dir, stderr: () => err };
}

function ended(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) resolve();
    else child.on('exit', () => resolve());
  });
}

function pyRun(code: string, ...args: string[]): string {
  const r = spawnSync(
    'python3',
    [
      '-c',
      `import importlib.util,sys;s=importlib.util.spec_from_file_location('runtmp',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);${code}`,
      PY_MODULE,
      ...args,
    ],
    { encoding: 'utf8' }
  );
  if (r.status !== 0) throw new Error(`python failed: ${r.stderr}`);
  return r.stdout.trim();
}

async function main(): Promise<void> {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'rtctl-base-'));
  try {
    const st = stamp('rtctl-');
    check(
      st.startsWith(`rtctl-${process.pid}-n`) && st.endsWith('-'),
      `stamp carries this pid and namespace (${st})`
    );
    check(
      ['', 'x', '1a-', 'a b-'].every((p) => {
        try {
          stamp(p);
          return false;
        } catch {
          return true;
        }
      }),
      'a prefix that could collide is refused'
    );

    const own = shared('rtctl-own-', base);
    check(shared('rtctl-own-', base) === own, 'shared hands back one run dir per prefix');
    fs.rmSync(own, { recursive: true });
    check(fs.existsSync(shared('rtctl-own-', base)), 'shared remakes a removed run dir');

    // 1. a normal exit leaves nothing
    const plain = await startChild('plain', base);
    await ended(plain.child);
    check(!fs.existsSync(plain.dir), 'a normal exit removes the run dir');

    // 2. SIGTERM with the signal hook removes it
    const hooked = await startChild('hooked', base);
    check(fs.existsSync(hooked.dir), 'the hooked child made its run dir');
    hooked.child.kill('SIGTERM');
    await ended(hooked.child);
    check(!fs.existsSync(hooked.dir), 'SIGTERM with installSignalCleanup removes the run dir');

    // 2b. a throwing extra still exits 130 with the dir removed, and the error is named on stderr
    const throwing = await startChild('throwing', base);
    throwing.child.kill('SIGTERM');
    await ended(throwing.child);
    check(!fs.existsSync(throwing.dir), 'a throwing cleanup callback still removes the run dir');
    check(throwing.child.exitCode === 130, 'a throwing cleanup callback still exits 130');
    check(
      throwing.stderr().includes('cleanup-boom'),
      'a throwing cleanup callback is named on stderr'
    );
    check(
      hooked.stderr() === '',
      'CONTROL (error named): a callback-free signal exit writes nothing to stderr'
    );

    // 3. PLANTED DEFECT: SIGTERM with no hook leaves it (the control that makes 2 able to fail)
    const unhooked = await startChild('unhooked', base);
    unhooked.child.kill('SIGTERM');
    await ended(unhooked.child);
    check(
      fs.existsSync(unhooked.dir),
      'CONTROL (cleanup removed): SIGTERM with no hook leaves the run dir'
    );

    // 4. SIGKILL: left until the next sweep, which removes it and spares a live run
    const killed = await startChild('unhooked', base);
    killed.child.kill('SIGKILL');
    await ended(killed.child);
    check(fs.existsSync(killed.dir), 'SIGKILL leaves the run dir (the premise of the sweep)');
    // runDir sweeps before it creates, so the live dir is made now and the explicit sweep must still spare it.
    const live = runDir('rtctl-', base);
    sweepDead('rtctl-', base);
    check(
      !fs.existsSync(killed.dir) && !fs.existsSync(unhooked.dir),
      'the sweep removes every dead run dir'
    );
    check(fs.existsSync(live), 'the sweep spares a live run dir');
    const aliveChild = await startChild('unhooked', base);
    check(
      !sweepDead('rtctl-', base).includes(aliveChild.dir) && fs.existsSync(aliveChild.dir),
      'sweepDead spares another live process'
    );
    aliveChild.child.kill('SIGKILL');
    await ended(aliveChild.child);

    // 5. cross-language
    const tsDead = await startChild('unhooked', base);
    tsDead.child.kill('SIGKILL');
    await ended(tsDead.child);
    const pyRemoved = pyRun('print("\\n".join(m.sweep_dead("rtctl-", sys.argv[2])))', base);
    check(
      pyRemoved.split('\n').includes(tsDead.dir) && !fs.existsSync(tsDead.dir),
      'Python sweep_dead removes a dead TypeScript run dir'
    );
    const pyDead = pyRun(
      'import os,subprocess;p=subprocess.Popen(["sleep","60"]);' +
        'm.tempfile.mkdtemp(prefix=m.stamp("rtctl-",p.pid),dir=sys.argv[2]);p.kill();p.wait();' +
        'print(sorted(f for f in os.listdir(sys.argv[2]) if f.startswith("rtctl-%d-"%p.pid))[0])',
      base
    );
    check(fs.existsSync(path.join(base, pyDead)), 'a dead Python run dir exists before the sweep');
    const tsRemoved = sweepDead('rtctl-', base);
    check(
      tsRemoved.includes(path.join(base, pyDead)) && !fs.existsSync(path.join(base, pyDead)),
      'TypeScript sweepDead removes a dead Python run dir'
    );
    const other = fs.mkdtempSync(path.join(base, 'rtctl-notstamped-'));
    check(!sweepDead('rtctl-', base).includes(other), 'a dir that is not stamped is left alone');
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
  console.log(bad === 0 ? 'runtmp controls: all passed' : `runtmp controls: ${bad} failed`);
  process.exitCode = bad === 0 ? 0 : 1;
}

if (process.argv[2] === 'child') {
  childMain(process.argv[3] as Mode, process.argv[4]);
} else {
  void main();
}
