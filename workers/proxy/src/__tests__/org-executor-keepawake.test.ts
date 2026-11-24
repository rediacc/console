/**
 * `OrgExecutor` keep-awake (agent/plans/PLAN-console-run-index.md box RI5, D5): a dispatch whose client left holds the container awake until it ends, up to `MAX_DISPATCH_HOLD_MS`, and the dispatch count route is never reachable through the forward.
 *
 * The fakes are in src/__tests__/helpers/org-executor-harness.ts.
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
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

import { BUSY_PATH, MAX_DISPATCH_HOLD_MS } from '../org-executor';
import { flush, harness, IDLE_MS, ORG, openStream, T0 } from './helpers/org-executor-harness';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(T0);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** A pinned executor whose only request was cancelled by the client, with `dispatches` still running in the container. */
async function clientGone(dispatches: { running: number }) {
  const h = harness();
  await h.ready;
  const stream = openStream();
  h.container.app = (request) =>
    new URL(request.url).pathname === BUSY_PATH
      ? Response.json({ busy: dispatches.running })
      : stream.response;
  await h.executor.pin(ORG, 0, 'light');
  const response = await h.executor.fetch(new Request('https://proxy/v1/command'));
  await response.body?.cancel();
  await flush();
  return h;
}

describe('keep-awake until the dispatch ends', () => {
  it('the route constant is the executor wire route', () => {
    expect(BUSY_PATH).toBe(PROXY_ROUTES.busy);
    expect(MAX_DISPATCH_HOLD_MS).toBe(60 * 60_000);
  });

  it('with the body cancelled and one dispatch running the alarm re-arms instead of stopping', async () => {
    const h = await clientGone({ running: 1 });

    vi.setSystemTime(T0 + IDLE_MS);
    await h.executor.alarm();

    expect(h.container.destroys).toEqual([]);
    expect(h.alarmAt()).toBe(T0 + 2 * IDLE_MS);
    expect(h.container.portUrls).toContain(`http://container${BUSY_PATH}`);
  });

  it('control: with no dispatch running the alarm stops the container at sleepAfter', async () => {
    const h = await clientGone({ running: 0 });

    vi.setSystemTime(T0 + IDLE_MS);
    await h.executor.alarm();

    expect(h.container.destroys).toEqual(['idle']);
  });

  it('a dispatch that ends is released at the next alarm', async () => {
    const dispatches = { running: 1 };
    const h = await clientGone(dispatches);
    vi.setSystemTime(T0 + IDLE_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toEqual([]);

    dispatches.running = 0;
    vi.setSystemTime(T0 + 2 * IDLE_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toEqual(['idle']);
  });

  it('a hold past 60 minutes stops the container', async () => {
    const h = await clientGone({ running: 1 });
    const firstHold = T0 + IDLE_MS;
    vi.setSystemTime(firstHold);
    await h.executor.alarm();

    vi.setSystemTime(firstHold + MAX_DISPATCH_HOLD_MS - 1);
    await h.executor.alarm();
    expect(h.container.destroys).toEqual([]);

    vi.setSystemTime(firstHold + MAX_DISPATCH_HOLD_MS);
    await h.executor.alarm();
    expect(h.container.destroys).toEqual(['idle']);
  });

  it('an outside /v1/busy is refused and never reaches the container', async () => {
    const h = await clientGone({ running: 3 });
    const before = h.container.portUrls.length;

    const response = await h.executor.fetch(new Request(`https://proxy${PROXY_ROUTES.busy}`));

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ code: 'ROUTE_NOT_FOUND' });
    expect(h.container.portUrls).toHaveLength(before);
  });
});

describe('isBusyPath (review 1cf0bd86.1)', () => {
  it('refuses every spelling the container router reads as the busy route', async () => {
    const { isBusyPath } = await import('../org-executor-support');
    for (const spelling of [
      BUSY_PATH,
      '/v1/%62usy',
      '/v1/b%75sy',
      '//v1/busy',
      '/v1//busy',
      '/v1/busy/',
      '/v1/%E0%A4%A',
    ]) {
      expect(isBusyPath(spelling), spelling).toBe(true);
    }
  });

  it('leaves every other path to the forward', async () => {
    const { isBusyPath } = await import('../org-executor-support');
    for (const path of ['/v1/ready', '/v1/busyness', '/v1', '/', '/v2/busy']) {
      expect(isBusyPath(path), path).toBe(false);
    }
  });
});
