import { beforeEach, describe, expect, it, vi } from 'vitest';

// The cooldown lives in the CONFIG (`state.licenseRefresh`), not in a sidecar
// file. The previous implementation wrote `license-refresh-state.json` under the
// user's state dir, which made behaviour depend on machine-local litter: this
// suite passed on a developer box that had run `rdc` recently and failed in CI,
// because the sidecar's mere presence decided which code path executed.
let mockState: Record<string, unknown> = {};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    updateState: vi.fn(
      async (
        _name: string,
        fn: (cfg: Record<string, unknown>) => Record<string, unknown>
      ): Promise<void> => {
        mockState = fn({ state: mockState.state }) as Record<string, unknown>;
      }
    ),
  },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn(() => Promise.resolve(mockState)),
    getEffectiveConfigName: vi.fn(() => 'test'),
  },
}));

const { isRefreshDue, markRefreshAttempted, LICENSE_REFRESH_COOLDOWN_MS } = await import(
  '../account/license-refresh-state.js'
);

const NOW = Date.UTC(2026, 6, 18, 12, 0, 0);

beforeEach(() => {
  mockState = {};
});

describe('license refresh cooldown', () => {
  it('allows a refresh when nothing has ever been recorded', async () => {
    expect(await isRefreshDue('hostinger', NOW)).toBe(true);
  });

  it('suppresses a second refresh inside the cooldown', async () => {
    await markRefreshAttempted('hostinger', NOW);
    expect(await isRefreshDue('hostinger', NOW + 60_000)).toBe(false);
  });

  it('allows a refresh once the cooldown has elapsed', async () => {
    await markRefreshAttempted('hostinger', NOW);
    expect(await isRefreshDue('hostinger', NOW + LICENSE_REFRESH_COOLDOWN_MS)).toBe(true);
  });

  // The cooldown is per machine: refreshing one must not starve another, or a
  // multi-machine estate would only ever keep one machine's licences current.
  it('tracks machines independently', async () => {
    await markRefreshAttempted('hostinger', NOW);
    expect(await isRefreshDue('hostinger', NOW + 60_000)).toBe(false);
    expect(await isRefreshDue('my-server', NOW + 60_000)).toBe(true);
  });

  // A clock moving backwards (NTP correction, VM resume) would otherwise leave a
  // future timestamp behind and suppress refreshes until real time caught up.
  it('treats a future timestamp as due rather than recent', async () => {
    await markRefreshAttempted('hostinger', NOW + 10 * LICENSE_REFRESH_COOLDOWN_MS);
    expect(await isRefreshDue('hostinger', NOW)).toBe(true);
  });

  it('survives a config with no state at all', async () => {
    mockState = {};
    expect(await isRefreshDue('hostinger', NOW)).toBe(true);
  });

  it('records into the config state bucket, not a sidecar file', async () => {
    await markRefreshAttempted('hostinger', NOW);
    const state = mockState.state as { licenseRefresh?: Record<string, number> };
    expect(state.licenseRefresh?.hostinger).toBe(NOW);
  });

  // Writing the cooldown must not disturb the rest of the state bucket.
  it('preserves sibling state when recording', async () => {
    mockState = { state: { reconciledAt: '2026-07-18T00:00:00Z' } };
    await markRefreshAttempted('hostinger', NOW);
    const state = mockState.state as { reconciledAt?: string };
    expect(state.reconciledAt).toBe('2026-07-18T00:00:00Z');
  });

  it('persists across reads', async () => {
    await markRefreshAttempted('a', NOW);
    await markRefreshAttempted('b', NOW);
    expect(await isRefreshDue('a', NOW + 60_000)).toBe(false);
    expect(await isRefreshDue('b', NOW + 60_000)).toBe(false);
  });

  // Cooldown must be long enough that routine commands do not each pay for an
  // SSH scan plus an account-server round trip.
  it('uses a cooldown measured in hours, not minutes', () => {
    expect(LICENSE_REFRESH_COOLDOWN_MS).toBeGreaterThanOrEqual(60 * 60 * 1000);
  });
});
