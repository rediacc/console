/**
 * `machine status` prints the pool line and, when any exist, the transfer-snapshot line read from
 * renet's renamed pool fields (PLAN-backup-local-image R2). The i18n key and its parameter names
 * `{pinned, active, stale}` stay as they were.
 */

import type { StorageHealthResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const info = vi.fn();
vi.mock('../../services/core/output.js', () => ({ outputService: { info } }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({
  t: (k: string, p?: Record<string, unknown>) => (p ? `${k} ${JSON.stringify(p)}` : k),
}));

const { renderPoolSummary } = await import('../machine/status.js');

type Pool = NonNullable<StorageHealthResult['pool']>;

function pool(overrides: Partial<Pool>): Pool {
  return {
    total_bytes: 100,
    used_bytes: 40,
    free_bytes: 60,
    used_human: '40G',
    free_human: '60G',
    used_percent: 40,
    active_transfer_snapshots: 0,
    stale_transfer_snapshots: 0,
    transfer_pinned_bytes: 0,
    transfer_pinned_human: '0B',
    ...overrides,
  };
}

function lines(): string[] {
  return info.mock.calls.map((c) => String(c[0]));
}

describe('renderPoolSummary', () => {
  beforeEach(() => info.mockClear());

  it('renders the snapshot line from the transfer fields', () => {
    renderPoolSummary(
      pool({
        active_transfer_snapshots: 1,
        stale_transfer_snapshots: 2,
        transfer_pinned_human: '3.0G',
      })
    );
    const out = lines();
    expect(out).toHaveLength(2);
    expect(out[0]).toContain('commands.machine.status.storageHealthPoolSummary');
    expect(out[1]).toBe(
      `commands.machine.status.storageHealthPoolSnapshots ${JSON.stringify({ pinned: '3.0G', active: 1, stale: 2 })}`
    );
  });

  it('a stale artifact alone still prints the line', () => {
    renderPoolSummary(pool({ stale_transfer_snapshots: 1, transfer_pinned_human: '4.0G' }));
    expect(lines()[1]).toContain('"stale":1');
  });

  it('control: omits the snapshot line at zero, and prints nothing without a pool', () => {
    renderPoolSummary(pool({}));
    expect(lines()).toHaveLength(1);
    info.mockClear();
    renderPoolSummary(undefined);
    expect(lines()).toHaveLength(0);
  });
});
