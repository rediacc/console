import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const stateFile = join(tmpdir(), `license-refresh-${process.pid}-${Date.now()}.json`);

vi.mock('../../utils/platform.js', () => ({
  LICENSE_REFRESH_STATE_FILE: stateFile,
}));

const { isRefreshDue, markRefreshAttempted, LICENSE_REFRESH_COOLDOWN_MS } = await import(
  '../account/license-refresh-state.js'
);

const NOW = Date.UTC(2026, 6, 18, 12, 0, 0);

beforeEach(async () => {
  await fs.rm(stateFile, { force: true });
});
afterEach(async () => {
  await fs.rm(stateFile, { force: true });
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
  // future timestamp on disk and suppress refreshes until real time caught up.
  it('treats a future timestamp as due rather than recent', async () => {
    await markRefreshAttempted('hostinger', NOW + 10 * LICENSE_REFRESH_COOLDOWN_MS);
    expect(await isRefreshDue('hostinger', NOW)).toBe(true);
  });

  it('survives a corrupt state file', async () => {
    await fs.writeFile(stateFile, '{not json');
    expect(await isRefreshDue('hostinger', NOW)).toBe(true);
    await expect(markRefreshAttempted('hostinger', NOW)).resolves.toBeUndefined();
    expect(await isRefreshDue('hostinger', NOW + 60_000)).toBe(false);
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
