/**
 * `OrgExecutor` reachability: the gate on egress-unreachable reports, the outside vantage, `outsideProbe` and the bench drill seam (PLAN-org-executor-connect-timeout-relocate E13, E15). Split out of org-executor.test.ts, which keeps the start, env and readiness.
 *
 * `cloudflare:workers` exists only inside workerd, so `DurableObject` is replaced by a base class that keeps `ctx` and `env` as the real one does. The fakes are in src/__tests__/helpers/org-executor-harness.ts.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('cloudflare:workers', () => {
  class Base {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  }
  // WorkerEntrypoint: src/egress.ts, which org-executor.ts imports, extends it.
  return { DurableObject: Base, WorkerEntrypoint: Base };
});

import {
  OUTSIDE_PROBE_TIMEOUT_MS,
  outsideProbe,
  vantageHint,
  vantageName,
} from '../org-executor-relocate';
import type { OrgExecutorEnv } from '../org-executor-support';
import type { ProbeResult } from '../reachability';
import { harness, ORG, T0 } from './helpers/org-executor-harness';

/** Every console.warn line so far, its arguments joined. */
function warnLines(): string[] {
  return vi.mocked(console.warn).mock.calls.map((c) => c.join(' '));
}

/** A promise executor that never settles. */
function neverSettles(): void {
  // Neither resolve nor reject is ever called.
}

/** How `promise` settled, readable at any point; undefined while it is pending. */
function tracked(promise: Promise<unknown>): { outcome: () => string | undefined } {
  let outcome: string | undefined;
  promise.then(
    () => {
      outcome = 'resolved';
    },
    (error: Error) => {
      outcome = `rejected: ${error.message}`;
    }
  );
  return { outcome: () => outcome };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('reachability gate on egress-unreachable reports (PLAN-org-executor-connect-timeout-relocate E13)', () => {
  const MINUTE = 60_000;
  const TARGET = { host: '203.0.113.7', port: 22 };

  function report(
    h: ReturnType<typeof harness>,
    at: number,
    target: { host: string; port: number } | 'none' = TARGET
  ) {
    vi.setSystemTime(at);
    return h.executor.recordEgressUnreachable(ORG, 0, target === 'none' ? undefined : target);
  }

  it('three reports whose target answers the Worker with a banner relocate once', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(await report(h, T0 + MINUTE)).toMatchObject({
      count: 1,
      counted: true,
      probe: 'reachable',
    });
    expect(await report(h, T0 + 3 * MINUTE)).toMatchObject({ count: 2, counted: true });
    expect(await report(h, T0 + 5 * MINUTE)).toEqual({
      ok: true,
      count: 3,
      threshold: 3,
      relocated: true,
      counted: true,
      probe: 'reachable',
    });
    expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
    expect(h.probes).toEqual([
      { hostname: '203.0.113.7', port: 22 },
      { hostname: '203.0.113.7', port: 22 },
      { hostname: '203.0.113.7', port: 22 },
    ]);
  });

  it('three reports whose target never greets the Worker never relocate and leave no stored count', async () => {
    const h = harness({ banner: ['end'] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    for (const minute of [1, 3, 5]) {
      expect(await report(h, T0 + minute * MINUTE)).toEqual({
        ok: true,
        count: 0,
        threshold: 3,
        relocated: false,
        counted: false,
        probe: 'target-unreachable',
      });
    }
    expect(h.issuer.relocate).not.toHaveBeenCalled();
    expect(h.storage.has('egressUnreachable')).toBe(false);
    expect(h.storage.has('egressUnreachableAt')).toBe(false);
    expect(h.probes).toHaveLength(3);
    expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({ egressUnreachableRecent: false });
  });

  it('a reset after opened, or a non-SSH reply, does not count either', async () => {
    const h = harness({ banner: [{ reject: new Error('reset') }] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    expect(await report(h, T0)).toMatchObject({ counted: false, probe: 'target-unreachable' });
    h.setBanner(['HTTP/1.1 200 OK\r\n']);
    expect(await report(h, T0 + 2 * MINUTE)).toMatchObject({
      counted: false,
      probe: 'target-unreachable',
    });
    expect(h.storage.has('egressUnreachable')).toBe(false);
  });

  it('a verdict is cached for 60 s per host and port', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    await report(h, T0);
    expect(await report(h, T0 + 59_999)).toMatchObject({ counted: true, probe: 'reachable' });
    expect(h.probes).toHaveLength(1);
    h.setBanner(['end']);
    // Another port on the same host is its own entry, so it is probed.
    expect(await report(h, T0 + 59_999, { host: '203.0.113.7', port: 2222 })).toMatchObject({
      counted: false,
      probe: 'target-unreachable',
    });
    expect(h.probes).toHaveLength(2);
    expect(await report(h, T0 + 60_000)).toMatchObject({
      counted: false,
      probe: 'target-unreachable',
    });
    expect(h.probes).toHaveLength(3);
    // A cached closed-port verdict does not count either.
    expect(await report(h, T0 + 61_000)).toMatchObject({
      counted: false,
      probe: 'target-unreachable',
    });
    expect(h.probes).toHaveLength(3);
  });

  it('at most 6 probes per window; past the cap a report is skipped and does not count', async () => {
    const h = harness({ banner: ['end'] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    for (let i = 0; i < 6; i++) {
      await report(h, T0 + i * 1000, { host: `203.0.113.${10 + i}`, port: 22 });
    }
    expect(h.probes).toHaveLength(6);
    h.setBanner(['SSH-2.0-x']);
    expect(await report(h, T0 + 7000, { host: '203.0.113.99', port: 22 })).toMatchObject({
      counted: false,
      probe: 'skipped',
    });
    expect(h.probes).toHaveLength(6);
    expect(h.storage.has('egressUnreachable')).toBe(false);
    // Once the first probes leave the 10-minute window, probing resumes.
    expect(
      await report(h, T0 + 10 * MINUTE + 1000, { host: '203.0.113.99', port: 22 })
    ).toMatchObject({
      counted: true,
      probe: 'reachable',
    });
    expect(h.probes).toHaveLength(7);
  });

  it('a report with no target is skipped: no probe, no count', async () => {
    const h = harness();
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    for (const minute of [1, 2, 3]) {
      expect(await report(h, T0 + minute * MINUTE, 'none')).toMatchObject({
        count: 0,
        relocated: false,
        counted: false,
        probe: 'skipped',
      });
    }
    expect(h.probes).toHaveLength(0);
    expect(h.issuer.relocate).not.toHaveBeenCalled();
    expect(h.storage.has('egressUnreachable')).toBe(false);
  });

  it('logs the verdict, reason and placement, never the address', async () => {
    const warn = vi.mocked(console.warn);
    const h = harness({ banner: ['end'] });
    await h.ready;
    await h.executor.pin(ORG, 0, 'light');
    await report(h, T0);
    await report(h, T0 + 1000);
    await report(h, T0 + 2000, 'none');
    const lines = warn.mock.calls.map((c) => c.join(' '));
    expect(lines).toContain(
      'proxy: org executor reachability probe target-unreachable (no-banner, outside weur timeout) at p0'
    );
    expect(lines).toContain(
      'proxy: org executor reachability probe target-unreachable (cached) at p0'
    );
    expect(lines).toContain('proxy: org executor reachability probe skipped (no-target) at p0');
    expect(lines.join('\n')).not.toContain('203.0.113.7');
  });

  describe('the outside vantage (finding 60c7b83e)', () => {
    /** The instance cannot reach the target (its colo shares the container's failing path); the vantage answers `far`. */
    async function blindHarness(far: ProbeResult | Error) {
      const h = harness({ banner: ['end'] });
      h.vantage.answer = far;
      await h.ready;
      await h.executor.pin(ORG, 0, 'light');
      return h;
    }

    it('a target the instance cannot reach but the vantage can counts, and three such reports relocate once', async () => {
      const h = await blindHarness({ verdict: 'reachable', reason: 'banner' });
      expect(await report(h, T0 + MINUTE)).toMatchObject({
        count: 1,
        counted: true,
        probe: 'reachable',
      });
      expect(await report(h, T0 + 3 * MINUTE)).toMatchObject({ count: 2, counted: true });
      expect(await report(h, T0 + 5 * MINUTE)).toMatchObject({
        count: 3,
        relocated: true,
        counted: true,
        probe: 'reachable',
      });
      expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
      expect(h.issuer.relocate).toHaveBeenCalledWith(ORG, 0);
      // The REGION 'us' harness asks the vantage on another continent, by its own name and hint.
      expect(h.vantage.calls).toHaveLength(3);
      expect(h.vantage.calls[0]).toEqual({
        name: 'reachability-vantage:v1:weur',
        locationHint: 'weur',
        hint: 'weur',
        target: TARGET,
      });
      expect(h.probes).toHaveLength(3);
    });

    it('a target neither the instance nor the vantage reaches is down: the vantage was asked, nothing counts, nothing moves', async () => {
      const h = await blindHarness({ verdict: 'target-unreachable', reason: 'timeout' });
      for (const minute of [1, 3, 5]) {
        expect(await report(h, T0 + minute * MINUTE)).toMatchObject({
          count: 0,
          relocated: false,
          counted: false,
          probe: 'target-unreachable',
        });
      }
      expect(h.vantage.calls).toHaveLength(3);
      expect(h.issuer.relocate).not.toHaveBeenCalled();
      expect(h.storage.has('egressUnreachable')).toBe(false);
    });

    it('a vantage that fails or times out reads as target-unreachable and never counts', async () => {
      const h = await blindHarness(new Error('vantage down'));
      expect(await report(h, T0 + MINUTE)).toMatchObject({
        counted: false,
        probe: 'target-unreachable',
      });
      expect(h.vantage.calls).toHaveLength(1);
      const lines = warnLines();
      expect(lines).toContain(
        'proxy: org executor reachability probe target-unreachable (no-banner, outside weur error) at p0'
      );
    });

    it('control: a target the instance reaches counts without asking the vantage', async () => {
      const h = harness();
      h.vantage.answer = { verdict: 'target-unreachable', reason: 'timeout' };
      await h.ready;
      await h.executor.pin(ORG, 0, 'light');
      expect(await report(h, T0 + MINUTE)).toMatchObject({
        count: 1,
        counted: true,
        probe: 'reachable',
      });
      expect(h.vantage.calls).toHaveLength(0);
    });

    it('control: a container that reaches its machines reports nothing, so nothing is probed and nothing moves', async () => {
      const h = harness();
      h.vantage.answer = { verdict: 'reachable', reason: 'banner' };
      await h.ready;
      for (const minute of [1, 3, 5]) {
        vi.setSystemTime(T0 + minute * MINUTE);
        expect(await h.executor.pin(ORG, 0, 'light')).toMatchObject({
          ok: true,
          egressUnreachableRecent: false,
        });
      }
      expect(h.probes).toHaveLength(0);
      expect(h.vantage.calls).toHaveLength(0);
      expect(h.issuer.relocate).not.toHaveBeenCalled();
    });
  });

  it('the vantage of each region sits on another continent; an unknown or unset region uses enam', () => {
    expect(vantageHint('asia')).toBe('weur');
    expect(vantageHint('eu')).toBe('enam');
    expect(vantageHint('us')).toBe('weur');
    expect(vantageHint('elsewhere')).toBe('enam');
    expect(vantageHint(undefined)).toBe('enam');
    expect(vantageName('weur')).toBe('reachability-vantage:v1:weur');
  });

  describe('outsideProbe, the call to the vantage', () => {
    /** An ORG_EXECUTOR slice whose stub answers with `answer`, recording the name and options of each `get`. */
    function namespace(answer: Promise<ProbeResult>) {
      const gets: { name: string; options?: DurableObjectNamespaceGetDurableObjectOptions }[] = [];
      const slice = {
        idFromName: (name: string) => ({ name }) as unknown as DurableObjectId,
        get: (id: DurableObjectId, options?: DurableObjectNamespaceGetDurableObjectOptions) => {
          gets.push({ name: (id as unknown as { name: string }).name, options });
          return { probeFromVantage: () => answer };
        },
      };
      return { slice, gets };
    }

    afterEach(() => {
      vi.useRealTimers();
    });

    it('a proxy in asia asks the weur vantage by name and location hint, and passes its answer through', async () => {
      const ns = namespace(Promise.resolve({ verdict: 'reachable', reason: 'banner' }));
      const outside = outsideProbe({ ORG_EXECUTOR: ns.slice, REGION: 'asia' });
      expect(outside.hint).toBe('weur');
      expect(await outside.probe(TARGET)).toEqual({ verdict: 'reachable', reason: 'banner' });
      expect(ns.gets).toEqual([
        { name: 'reachability-vantage:v1:weur', options: { locationHint: 'weur' } },
      ]);
    });

    it('a vantage that never answers rejects once OUTSIDE_PROBE_TIMEOUT_MS pass', async () => {
      vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] });
      const ns = namespace(new Promise<ProbeResult>(neverSettles));
      const pending = tracked(
        outsideProbe({ ORG_EXECUTOR: ns.slice, REGION: 'asia' }).probe(TARGET)
      );
      await vi.advanceTimersByTimeAsync(OUTSIDE_PROBE_TIMEOUT_MS - 1);
      expect(pending.outcome()).toBeUndefined();
      await vi.advanceTimersByTimeAsync(1);
      expect(pending.outcome()).toBe('rejected: outside-probe-timeout');
    });
  });

  describe('probeFromVantage on the vantage instance', () => {
    function vantageHarness(storage?: Map<string, unknown>) {
      return harness({ name: 'reachability-vantage:v1:weur', storage });
    }

    /** The harness names instances `executorName(name, placement)`; the vantage is named without the placement suffix. */
    function asVantage(h: ReturnType<typeof harness>) {
      (h.executor as unknown as { ctx: { id: unknown } }).ctx.id = {
        name: 'reachability-vantage:v1:weur',
        equals: (other: { name?: string }) => other.name === 'reachability-vantage:v1:weur',
      };
      return h;
    }

    it('probes the target from the unpinned vantage named for the hint', async () => {
      const h = asVantage(vantageHarness());
      await h.ready;
      expect(await h.executor.probeFromVantage('weur', TARGET)).toEqual({
        verdict: 'reachable',
        reason: 'banner',
      });
      expect(h.probes).toEqual([{ hostname: '203.0.113.7', port: 22 }]);
      expect(h.container.starts).toHaveLength(0);
    });

    it('refuses without a connect: another hint, an org executor instance, an unknown hint or a refused target', async () => {
      const h = asVantage(vantageHarness());
      await h.ready;
      const refused = { verdict: 'target-unreachable', reason: 'error' };
      expect(await h.executor.probeFromVantage('enam', TARGET)).toEqual(refused);
      expect(await h.executor.probeFromVantage('nowhere', TARGET)).toEqual(refused);
      expect(await h.executor.probeFromVantage('weur', { host: '10.0.0.1', port: 22 })).toEqual(
        refused
      );
      const org = harness();
      await org.ready;
      await org.executor.pin(ORG, 0, 'light');
      expect(await org.executor.probeFromVantage('weur', TARGET)).toEqual(refused);
      expect(h.probes).toHaveLength(0);
      expect(org.probes).toHaveLength(0);
      const lines = warnLines();
      expect(lines).toContain('proxy: org executor outside probe refused: vantage-id-mismatch');
      expect(lines).toContain('proxy: org executor outside probe refused: vantage-hint-invalid');
      expect(lines).toContain('proxy: org executor outside probe refused: report-target-refused');
    });

    it('a vantage instance that holds a pin refuses to probe', async () => {
      const storage = new Map<string, unknown>([['org', { orgId: ORG, placement: 0 }]]);
      const h = asVantage(vantageHarness(storage));
      await h.ready;
      expect(await h.executor.probeFromVantage('weur', TARGET)).toEqual({
        verdict: 'target-unreachable',
        reason: 'error',
      });
      expect(h.probes).toHaveLength(0);
      const lines = warnLines();
      expect(lines).toContain('proxy: org executor outside probe refused: vantage-pinned');
    });

    it('the vantage name is never an executor name, so pin refuses it', async () => {
      const h = asVantage(vantageHarness());
      await h.ready;
      expect(await h.executor.pin('reachability-vantage', 0, 'light')).toMatchObject({ ok: false });
      expect(h.container.starts).toHaveLength(0);
    });
  });

  describe('the bench drill seam (src/drill.ts, E15)', () => {
    const DRILL = { host: '192.0.2.10', port: 22 };

    /** The harness with `ENVIRONMENT` and the drill var set on the instance's env. */
    function drillHarness(environment: string) {
      const h = harness();
      Object.assign((h.executor as unknown as { env: OrgExecutorEnv }).env, {
        ENVIRONMENT: environment,
        EGRESS_DRILL_PROBE: '192.0.2.10:22=203.0.113.7:22',
      });
      return h;
    }

    it('on bench, three reports of the drill address probe the redirect and relocate once', async () => {
      const h = drillHarness('bench');
      await h.ready;
      await h.executor.pin(ORG, 0, 'light');
      await report(h, T0 + MINUTE, DRILL);
      await report(h, T0 + 3 * MINUTE, DRILL);
      expect(await report(h, T0 + 5 * MINUTE, DRILL)).toMatchObject({
        count: 3,
        relocated: true,
        counted: true,
        probe: 'reachable',
      });
      expect(h.issuer.relocate).toHaveBeenCalledTimes(1);
      expect(h.probes).toEqual([
        { hostname: '203.0.113.7', port: 22 },
        { hostname: '203.0.113.7', port: 22 },
        { hostname: '203.0.113.7', port: 22 },
      ]);
    });

    it('on edge, the same var leaves the probe at the reported address', async () => {
      const h = drillHarness('edge');
      await h.ready;
      await h.executor.pin(ORG, 0, 'light');
      await report(h, T0 + MINUTE, DRILL);
      expect(h.probes).toEqual([{ hostname: '192.0.2.10', port: 22 }]);
    });
  });
});
