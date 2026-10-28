import { Command } from 'commander';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../backup-storage-browse.js', () => ({
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
}));

import { registerBackupRetention } from '../backup-retention-commands.js';

describe('backup retention set', () => {
  it('passes the PUT body as an object, since accountServerFetch serializes it itself', async () => {
    mockFetch.mockResolvedValue({ policies: [] });
    const backup = new Command('backup');
    registerBackupRetention(backup);
    await backup.parseAsync(['retention', 'set', 'shop', '--keep-last', '3'], { from: 'user' });
    const init = mockFetch.mock.calls[0][1] as { method: string; body: unknown };
    expect(init.method).toBe('PUT');
    expect(typeof init.body).toBe('object');
    expect(init.body).toEqual({ lineageGuid: 'lineage-1', keepLast: 3 });
  });
});
