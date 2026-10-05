/**
 * The TypeScript side of the core contract (agent/plans/PLAN-prepush-full-cpu.md parts 1 and 4): how many cores this process may use, and the ci-runner's client of the machine-wide core lease.
 *
 * `grantedCores()` is the twin of `.ci/rediacc_ci/core_lease.py granted_cores()`: `CI_RUNNER_CORES` when it is a positive integer (the grant exec.ts exports to every gate it launches), else every core this process may run on. No caller keeps a cap of its own (operator ruling 2026-10-05: no static worker counts); a floor below which parallelism is pointless is the manifest's `cores.min`.
 *
 * THE LEASE. Two runs on one machine (a pre-push in a push clone and a session's pytest, or two worktrees) each used to assume every core was theirs. core_lease.py owns one token per core, held by flock, released by the kernel when the holder dies. The runner speaks to it through one `broker` process per run, JSON lines on stdin and stdout, and ends it by closing stdin. The interface this client ASSUMES, written here because the module grows in parallel with this file:
 *
 *   spawn   python3 -m rediacc_ci.core_lease broker      (cwd = repo root, PYTHONPATH gains <root>/.ci)
 *   request {"op":"free"}                                -> {"free": <int tokens free machine-wide>}
 *   request {"op":"acquire","min":<a>,"max":<b>}         -> {"ids": [<int token id>, ...]}   (0..b ids, non-blocking; fewer than a is a short grant, never a wait)
 *   request {"op":"release","ids":[...]}                 -> any JSON object without an "error" key
 *   any reply {"error": "..."} is a refusal; EOF on stdin releases everything the broker holds.
 *
 * DEGRADES, LOUDLY, TO "THE RUN OWNS THE WHOLE MACHINE". No module, no `broker` verb (today's core_lease.py answers any argv with its selftest), a reply that is not that JSON, or a broker that dies mid-run: the run continues on its own core budget, the reason is printed in the header, and gates are not told the lease is held. That is exactly the behaviour before the lease existed, so a missing lease costs contention, never a verdict. A runner launched under a held lease (`CI_CORE_LEASE_HELD=1`, e.g. a nested run inside a gate) does not lease again: its grant is its budget.
 */
import { type ChildProcessWithoutNullStreams, spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { CORES_ENV, LEASE_HELD_ENV } from './exec';
import type { PoolLease } from './pool';

/** The CPUs this process may run on, at least 1. node's availableParallelism honours the affinity mask, as core_lease.py's sched_getaffinity does. */
function availableCores(): number {
  return Math.max(1, os.availableParallelism());
}

/** The positive integer grant in `CI_RUNNER_CORES`, or undefined when there is none (unset, zero, malformed). */
export function grantFromEnv(env: NodeJS.ProcessEnv = process.env): number | undefined {
  const raw = (env[CORES_ENV] ?? '').trim();
  return /^\d+$/.test(raw) && Number(raw) > 0 ? Number(raw) : undefined;
}

/** The cores granted to this process: the runner's grant when it made one, else every core it may run on. Never a constant. */
export function grantedCores(env: NodeJS.ProcessEnv = process.env): number {
  return grantFromEnv(env) ?? availableCores();
}

/** True when this process already runs inside a held lease, so it must not lease again. */
function leaseHeldByParent(env: NodeJS.ProcessEnv = process.env): boolean {
  return env[LEASE_HELD_ENV] === '1';
}

/** A PoolLease plus what the header prints about it and how to end it. */
export interface RunnerLease extends PoolLease {
  /** `broker`: tokens from the machine-wide lease; `inherited`: inside a parent's held lease; `whole-machine`: no lease (the reason is in `note`). */
  readonly kind: 'broker' | 'inherited' | 'whole-machine';
  /** One line for the run header, naming the lease and, when degraded, why. */
  readonly note: string;
  /** Release everything and end the broker. Idempotent. */
  close(): void;
}

function unleased(kind: 'inherited' | 'whole-machine', note: string): RunnerLease {
  return {
    kind,
    note,
    held: kind === 'inherited',
    available: async () => Number.POSITIVE_INFINITY,
    reconcile: async () => Number.POSITIVE_INFINITY,
    close: () => {},
  };
}

/** One JSON-lines conversation with the broker, strictly one request in flight at a time. */
class BrokerLink {
  private buffer = '';
  private waiting: ((line: string | undefined) => void) | undefined;
  private queue: Promise<unknown> = Promise.resolve();
  private dead: string | undefined;

  constructor(private readonly child: ChildProcessWithoutNullStreams) {
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      this.drain();
    });
    const die = (why: string): void => {
      if (this.dead === undefined) this.dead = why;
      const w = this.waiting;
      this.waiting = undefined;
      w?.(undefined);
    };
    // 'close', not 'exit': it fires after stdout has drained, so a reply written just before the broker exits is still read.
    child.on('close', (code, signal) => die(`the broker exited (${signal ?? `code ${code}`})`));
    child.on('error', (e) => die(`the broker could not start: ${e.message}`));
    child.stdin.on('error', (e) => die(`the broker's stdin closed: ${e.message}`));
    child.stderr.resume();
  }

  private drain(): void {
    const nl = this.buffer.indexOf('\n');
    if (nl < 0 || this.waiting === undefined) return;
    const line = this.buffer.slice(0, nl);
    this.buffer = this.buffer.slice(nl + 1);
    const w = this.waiting;
    this.waiting = undefined;
    w(line);
  }

  /** Send one request and read one reply line, or reject with the reason the conversation failed. */
  request(body: Record<string, unknown>, timeoutMs: number): Promise<Record<string, unknown>> {
    const run = async (): Promise<Record<string, unknown>> => {
      if (this.dead !== undefined) throw new Error(this.dead);
      const line = await new Promise<string | undefined>((resolve) => {
        const timer = setTimeout(() => {
          this.waiting = undefined;
          if (this.dead === undefined)
            this.dead = `no reply to ${JSON.stringify(body)} within ${timeoutMs} ms`;
          resolve(undefined);
        }, timeoutMs);
        this.waiting = (l) => {
          clearTimeout(timer);
          resolve(l);
        };
        this.child.stdin.write(`${JSON.stringify(body)}\n`);
        this.drain();
      });
      if (line === undefined) throw new Error(this.dead ?? 'the broker said nothing');
      let parsed: unknown;
      try {
        parsed = JSON.parse(line);
      } catch {
        throw new Error(
          `its reply to ${JSON.stringify(body)} was not JSON: ${JSON.stringify(line.slice(0, 120))}`
        );
      }
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed))
        throw new Error(
          `its reply to ${JSON.stringify(body)} was not a JSON object: ${line.slice(0, 120)}`
        );
      const reply = parsed as Record<string, unknown>;
      if (typeof reply.error === 'string')
        throw new Error(`it refused ${JSON.stringify(body)}: ${reply.error}`);
      return reply;
    };
    const next = this.queue.then(run, run);
    this.queue = next.catch(() => undefined);
    return next;
  }

  close(): void {
    try {
      this.child.stdin.end();
    } catch {
      /* already closed */
    }
    // EOF releases everything; the kill is the backstop for a broker that ignores it, and the kernel frees its flocks either way.
    const t = setTimeout(() => this.child.kill('SIGKILL'), 2000);
    t.unref();
    this.child.unref();
  }
}

interface OpenLeaseOptions {
  root: string;
  env?: NodeJS.ProcessEnv;
  /** Override the broker command (argv), for the selftest's fake brokers. */
  command?: readonly string[];
  /** Where a mid-run degradation is reported. */
  warn?: (text: string) => void;
  handshakeMs?: number;
  requestMs?: number;
}

/**
 * Open the runner's lease. Never throws: every way the broker can be missing or wrong ends in `whole-machine` with the reason in `note`.
 */
export async function openLease(opts: OpenLeaseOptions): Promise<RunnerLease> {
  const env = opts.env ?? process.env;
  if (leaseHeldByParent(env)) {
    const grant = grantFromEnv(env);
    return unleased(
      'inherited',
      `core lease: inside a held lease (${LEASE_HELD_ENV}=1${grant === undefined ? '' : `, ${CORES_ENV}=${grant}`}); this run does not lease again`
    );
  }
  const module = path.join(opts.root, '.ci', 'rediacc_ci', 'core_lease.py');
  if (opts.command === undefined && !fs.existsSync(module)) {
    return unleased(
      'whole-machine',
      `core lease: NONE, ${path.relative(opts.root, module)} is absent; this run assumes the whole machine`
    );
  }
  const argv = opts.command ?? ['python3', '-m', 'rediacc_ci.core_lease', 'broker'];
  let child: ChildProcessWithoutNullStreams;
  try {
    child = spawn(argv[0], argv.slice(1), {
      cwd: opts.root,
      env: {
        ...env,
        PYTHONPATH: [path.join(opts.root, '.ci'), env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    return unleased(
      'whole-machine',
      `core lease: NONE, the broker did not spawn (${(e as Error).message}); this run assumes the whole machine`
    );
  }
  const link = new BrokerLink(child);
  let free: number;
  try {
    const reply = await link.request({ op: 'free' }, opts.handshakeMs ?? 3000);
    if (typeof reply.free !== 'number' || !Number.isInteger(reply.free) || reply.free < 0)
      throw new Error(
        `its reply to {"op":"free"} carried no integer "free": ${JSON.stringify(reply)}`
      );
    free = reply.free;
  } catch (e) {
    link.close();
    return unleased(
      'whole-machine',
      `core lease: NONE, \`${argv.join(' ')}\` is not a usable broker (${(e as Error).message}); this run assumes the whole machine`
    );
  }

  const tokens: number[] = [];
  let degraded: string | undefined;
  const requestMs = opts.requestMs ?? 10_000;
  const degrade = (why: string): void => {
    if (degraded !== undefined) return;
    degraded = why;
    tokens.length = 0;
    link.close();
    opts.warn?.(
      `ci-runner: WARNING: the core lease failed mid-run (${why}); the rest of this run assumes the whole machine, and its tokens are released\n`
    );
  };
  return {
    kind: 'broker',
    note: `core lease: machine-wide broker, ${free} token(s) free at start`,
    get held(): boolean {
      return degraded === undefined;
    },
    available: async (inUse: number): Promise<number> => {
      if (degraded !== undefined) return Number.POSITIVE_INFINITY;
      try {
        const reply = await link.request({ op: 'free' }, requestMs);
        const n = typeof reply.free === 'number' ? reply.free : Number.NaN;
        if (!Number.isFinite(n) || n < 0)
          throw new Error(`bad free reply ${JSON.stringify(reply)}`);
        return n + Math.max(0, tokens.length - inUse);
      } catch (e) {
        degrade((e as Error).message);
        return Number.POSITIVE_INFINITY;
      }
    },
    reconcile: async (cores: number): Promise<number> => {
      if (degraded !== undefined) return Number.POSITIVE_INFINITY;
      const want = Math.max(0, Math.ceil(cores - 1e-9));
      try {
        if (tokens.length < want) {
          const reply = await link.request(
            { op: 'acquire', min: 0, max: want - tokens.length },
            requestMs
          );
          const ids = Array.isArray(reply.ids) ? reply.ids : undefined;
          if (ids === undefined || !ids.every((i) => typeof i === 'number'))
            throw new Error(`bad acquire reply ${JSON.stringify(reply)}`);
          tokens.push(...(ids as number[]));
        } else if (tokens.length > want) {
          const extra = tokens.splice(want);
          await link.request({ op: 'release', ids: extra }, requestMs);
        }
        return tokens.length;
      } catch (e) {
        degrade((e as Error).message);
        return Number.POSITIVE_INFINITY;
      }
    },
    close: () => {
      if (degraded === undefined) {
        degraded = 'closed';
        link.close();
      }
    },
  };
}

/**
 * The client's own controls, run from run.ts --selftest against fake brokers written to a temp dir, so the protocol, the short grant, the release and every degradation are proven without core_lease.py.
 */
export async function leaseClientSelftest(
  tmpRoot: string
): Promise<{ failures: string[]; assertions: number }> {
  const failures: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };
  check(grantedCores({ [CORES_ENV]: '5' }) === 5, 'a positive CI_RUNNER_CORES must be honoured');
  check(grantedCores({}) === availableCores(), 'no grant must read the real core count');
  check(grantedCores({ [CORES_ENV]: '0' }) === availableCores(), 'a zero grant is not a grant');
  check(
    grantedCores({ [CORES_ENV]: 'eight' }) === availableCores(),
    'a malformed grant is not a grant'
  );

  // tree-write: safe the only caller passes os.tmpdir(), so the fake brokers live outside the repository
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'ci-runner-lease-'));
  try {
    // A 4-token broker that speaks the assumed protocol and logs every request, so release is observable.
    const fake = path.join(dir, 'broker.py');
    const log = path.join(dir, 'requests.log');
    fs.writeFileSync(
      fake,
      [
        'import json, sys',
        `log = open(${JSON.stringify(log)}, "a")`,
        'free = set(range(4))',
        'for line in sys.stdin:',
        '    req = json.loads(line); log.write(line); log.flush()',
        '    if req["op"] == "free": out = {"free": len(free)}',
        '    elif req["op"] == "acquire":',
        '        ids = sorted(free)[: req["max"]]; free.difference_update(ids); out = {"ids": ids}',
        '    elif req["op"] == "release": free.update(req["ids"]); out = {"ok": True}',
        '    else: out = {"error": "unknown op"}',
        '    sys.stdout.write(json.dumps(out) + "\\n"); sys.stdout.flush()',
        '',
      ].join('\n')
    );
    const env = { PATH: process.env.PATH ?? '' };
    const real = await openLease({ root: dir, env, command: ['python3', fake] });
    check(
      real.kind === 'broker' && real.held,
      `a broker that speaks the protocol must be used, got ${real.kind}: ${real.note}`
    );
    check((await real.available(0)) === 4, "available() must report the broker's free tokens");
    check((await real.reconcile(2.5)) === 3, 'reconcile(2.5 cores) must hold ceil(2.5) = 3 tokens');
    check(
      (await real.available(2.5)) === 1.5,
      'available() holding 3 tokens for 2.5 cores must be the broker free 1 plus the 0.5 slack'
    );
    check(
      (await real.reconcile(9)) === 4,
      'a short acquire must return what it got (4 of 9), not fail'
    );
    check((await real.reconcile(1)) === 1, 'reconcile down must release the extra tokens');
    real.close();
    const requests = fs.readFileSync(log, 'utf8');
    check(/"op": ?"release"/.test(requests), `the release must reach the broker, log: ${requests}`);

    // DEGRADATIONS, each must say why and assume the whole machine.
    const selftesting = path.join(dir, 'selftest.py');
    fs.writeFileSync(selftesting, 'print("  PASS  a positive grant is honoured")\n');
    const notBroker = await openLease({
      root: dir,
      env,
      command: ['python3', selftesting],
      handshakeMs: 2000,
    });
    check(
      notBroker.kind === 'whole-machine' &&
        !notBroker.held &&
        /not a usable broker/.test(notBroker.note),
      `a module that answers with its selftest must degrade by name, got ${notBroker.kind}: ${notBroker.note}`
    );
    check(
      (await notBroker.available(0)) === Number.POSITIVE_INFINITY,
      'CONTROL: a degraded lease bounds nothing'
    );
    const absent = await openLease({ root: dir, env });
    check(
      absent.kind === 'whole-machine' && /is absent/.test(absent.note),
      `a missing core_lease.py must degrade by name, got ${absent.note}`
    );
    const inherited = await openLease({
      root: dir,
      env: { ...env, [LEASE_HELD_ENV]: '1', [CORES_ENV]: '6' },
    });
    check(
      inherited.kind === 'inherited' && inherited.held && /CI_RUNNER_CORES=6/.test(inherited.note),
      `a runner inside a held lease must not lease again and must say so, got ${inherited.kind}: ${inherited.note}`
    );
    const dying = path.join(dir, 'dying.py');
    fs.writeFileSync(
      dying,
      'import json, sys\nline = sys.stdin.readline()\nsys.stdout.write(json.dumps({"free": 4}) + "\\n"); sys.stdout.flush()\n'
    );
    const warned: string[] = [];
    const mid = await openLease({
      root: dir,
      env,
      command: ['python3', dying],
      warn: (t) => warned.push(t),
      requestMs: 2000,
    });
    check(mid.kind === 'broker', 'CONTROL: the dying broker passes its handshake');
    check(
      (await mid.reconcile(2)) === Number.POSITIVE_INFINITY &&
        !mid.held &&
        warned.some((w) => /failed mid-run/.test(w)),
      `a broker that dies mid-run must degrade loudly and stop claiming the lease, warned: ${warned.join('')}`
    );
    mid.close();
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return { failures, assertions };
}
