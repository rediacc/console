/**
 * Per-gate core grants out of ONE machine-wide lease, for a launcher that runs gates side by side outside run.ts's pool (PR-TASK 79b7e92e).
 *
 * WHY. run.ts schedules every gate against the broker lease (lease-client.ts), so `npm run ci` cannot take more than its share of the machine. A launcher that spawns gates itself bypassed that entirely: on 2026-11-24 at load 134 on 24 cores, `trace-honest.ts` in one lease ran six gates at once, none holding a token and none told its width, so each vitest gate sized itself to all 24 cores (`VITEST_MAX_WORKERS="$CI_RUNNER_CORES"` read empty), while `core_lease.py status` reported 24 of 24 tokens free. The machine-wide pool exists to stop exactly that, and it only works when every heavy launcher draws from it.
 *
 * WHAT IT DOES. `GateCores.take()` waits until at least one more token can be held, takes up to the per-gate grant (this run's share of the pool split over `jobs` concurrent gates, at least 1), and returns the grant with the environment the gate must run under: `CI_RUNNER_CORES=<grant>` and, when a broker backs it, `CI_CORE_LEASE_HELD=1` so the gate's own pytest wrapper or nested runner does not lease the same cores again. `give()` hands the tokens back. Waiting prints ONE line naming the live run count and who to ask (`core_lease.py status`).
 *
 * NO LEASE IS NOT A REFUSAL. When the broker is absent or degrades, `lease-client.ts` already says so and answers Infinity; the grant is then this machine's cores split over `jobs`, which still tells every gate its width, and that alone removed the 6 x 24 oversubscription.
 */
import os from 'node:os';
import { CORES_ENV, LEASE_HELD_ENV } from './exec';
import type { RunnerLease } from './lease-client';

/** How often a waiting take re-reads the lease, ms. */
export const GATE_CORES_POLL_MS = 1000;

export interface GateGrant {
  readonly cores: number;
  readonly env: NodeJS.ProcessEnv;
}

export class GateCores {
  private inUse = 0;
  private queue: Promise<unknown> = Promise.resolve();
  /** Wait lines printed so far; only the first wait of the run is announced. */
  private notices = 0;
  /** How many takes had to wait at least one poll, for the launcher's summary line. */
  waited = 0;

  constructor(
    private readonly lease: Pick<RunnerLease, 'held' | 'available' | 'reconcile'>,
    private readonly jobs: number,
    private readonly opts: {
      cpus?: number;
      pollMs?: number;
      warn?: (text: string) => void;
      env?: NodeJS.ProcessEnv;
    } = {}
  ) {}

  /** The grant one gate asks for: its share of the pool split over the concurrent jobs. */
  private target(share: number): number {
    const whole = Number.isFinite(share) ? share : (this.opts.cpus ?? os.availableParallelism());
    return Math.max(1, Math.floor(whole / Math.max(1, this.jobs)));
  }

  /** Serialise every take and give, so two async workers never reconcile against the same `inUse`. */
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const next = this.queue.then(fn, fn);
    this.queue = next.catch(() => undefined);
    return next;
  }

  private envFor(cores: number): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = {
      ...(this.opts.env ?? process.env),
      [CORES_ENV]: String(cores),
    };
    if (this.lease.held) env[LEASE_HELD_ENV] = '1';
    else delete env[LEASE_HELD_ENV];
    return env;
  }

  /** Wait for at least one token, take up to the per-gate grant, and return it with the gate's environment. */
  async take(label: string): Promise<GateGrant> {
    let blocked = false;
    for (;;) {
      const got = await this.serial(async () => {
        const view = await this.lease.available(this.inUse);
        const want = this.target(view.share);
        if (!Number.isFinite(view.free)) {
          this.inUse += want;
          return want;
        }
        const give = Math.min(want, Math.floor(view.free));
        if (give < 1) return { runs: view.runs, total: view.total };
        const held = await this.lease.reconcile(this.inUse + give);
        const granted = Number.isFinite(held) ? Math.min(give, held - this.inUse) : give;
        if (granted < 1) return { runs: view.runs, total: view.total };
        this.inUse += granted;
        return granted;
      });
      if (typeof got === 'number') {
        if (blocked) this.waited += 1;
        return { cores: got, env: this.envFor(got) };
      }
      if (this.notices === 0) {
        this.notices += 1;
        this.opts.warn?.(
          `gate-cores: ${label} waits for a core token: all ${got.total} are held by ${got.runs ?? '?'} live run(s) on this machine (who: python3 .ci/rediacc_ci/core_lease.py status)\n`
        );
      }
      blocked = true;
      await new Promise((r) => setTimeout(r, this.opts.pollMs ?? GATE_CORES_POLL_MS));
    }
  }

  /** Hand a finished gate's tokens back to the machine. */
  async give(grant: GateGrant): Promise<void> {
    await this.serial(async () => {
      this.inUse = Math.max(0, this.inUse - grant.cores);
      await this.lease.reconcile(this.inUse);
    });
  }
}

/**
 * Controls against a fake lease: a 4-token pool with two 2-core holders makes the third take wait until one gives back; an unleased run still tells every gate its width; a broker-backed grant marks the lease held. Returns the failures, empty when green.
 */
export async function gateCoresSelftest(): Promise<string[]> {
  const failures: string[] = [];
  const fake = (total: number, held = true) => {
    let tokens = 0;
    return {
      held,
      get tokens() {
        return tokens;
      },
      available: async (inUse: number) => ({
        free: total - tokens + Math.max(0, tokens - inUse),
        share: total,
        total,
        runs: 1,
      }),
      reconcile: async (cores: number) => {
        tokens = Math.min(total, Math.max(0, Math.ceil(cores)));
        return tokens;
      },
    };
  };
  const lease = fake(4);
  const warned: string[] = [];
  const gc = new GateCores(lease, 2, { pollMs: 5, warn: (t) => warned.push(t), env: {} });
  const a = await gc.take('a');
  const b = await gc.take('b');
  if (a.cores !== 2 || b.cores !== 2 || lease.tokens !== 4)
    failures.push(
      `two takes of a 4-token pool over 2 jobs must hold 2 each, got ${a.cores}, ${b.cores}, ${lease.tokens} held`
    );
  if (a.env[CORES_ENV] !== '2' || a.env[LEASE_HELD_ENV] !== '1')
    failures.push(
      `a broker-backed grant must export ${CORES_ENV}=2 and ${LEASE_HELD_ENV}=1, got ${JSON.stringify(a.env)}`
    );
  let thirdAt = 0;
  const third = gc.take('c').then((g) => {
    thirdAt = Date.now();
    return g;
  });
  await new Promise((r) => setTimeout(r, 40));
  if (thirdAt !== 0) failures.push('a third take of a full pool must wait, it returned at once');
  if (
    warned.length !== 1 ||
    !/waits for a core token: all 4 are held by 1 live run/.test(warned[0] ?? '')
  )
    failures.push(
      `a waiting take must print one line naming the holders, got ${JSON.stringify(warned)}`
    );
  const gaveAt = Date.now();
  await gc.give(a);
  const c = await third;
  if (c.cores < 1 || thirdAt < gaveAt)
    failures.push('the waiting take must start only after a holder gives back');
  if (gc.waited !== 1) failures.push(`one take waited, the counter says ${gc.waited}`);
  await gc.give(b);
  await gc.give(c);
  if (lease.tokens !== 0)
    failures.push(`every give must return its tokens, ${lease.tokens} still held`);

  // CONTROL: no lease (Infinity) never waits and still names every gate's width.
  const none = new GateCores(
    {
      held: false,
      available: async () => ({ free: Infinity, share: Infinity, total: Infinity }),
      reconcile: async () => Infinity,
    },
    6,
    { cpus: 24, env: { [LEASE_HELD_ENV]: '1' } }
  );
  const grants = await Promise.all(Array.from({ length: 8 }, (_, i) => none.take(`n${i}`)));
  if (grants.some((g) => g.cores !== 4 || g.env[CORES_ENV] !== '4'))
    failures.push(
      `an unleased run over 24 cpus and 6 jobs must grant 4 each, got ${grants.map((g) => g.cores).join(',')}`
    );
  if (grants.some((g) => g.env[LEASE_HELD_ENV] !== undefined))
    failures.push(
      `an unleased grant must not claim ${LEASE_HELD_ENV}, or the gate's own pytest wrapper would skip the lease`
    );
  return failures;
}
