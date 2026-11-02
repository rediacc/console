/**
 * The estimate `backup strategy set --rpo` prints comes from the measurement `backup churn` stored.
 * Before the wire, `defaultRpoDeps.estimate` answered undefined for every target, so every `--rpo`
 * was refused without `--no-estimate`.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const dir = vi.hoisted(() => ({ value: '' }));
vi.mock('@rediacc/shared/paths', async (orig) => ({
  ...(await orig<object>()),
  getConfigDir: () => dir.value,
}));
vi.mock('../../services/config/config-name.js', () => ({
  getEffectiveConfigName: () => 'rediacc',
}));

const MIB = 1024 * 1024;
const summary = (cells4: number) => ({
  samples: 1,
  baselines: 1,
  skipped: 0,
  failed: 0,
  changedCellsPerRun: { '4MiB': cells4 },
  maxChangedCellsPerRun: { '4MiB': cells4 },
  uploadBytesPerRun: { '4MiB': cells4 * 4 * MIB },
});

beforeEach(() => {
  dir.value = mkdtempSync(join(tmpdir(), 'churn-store-'));
});
afterAll(() => rmSync(dir.value, { recursive: true, force: true }));

describe('defaultRpoDeps.estimate', () => {
  it('refuses a target with no stored measurement', async () => {
    const { defaultRpoDeps } = await import('../../services/backup/backup-rpo-plan.js');
    await expect(
      defaultRpoDeps.estimate([{ ref: 'mail', rpoSeconds: 300 }])
    ).resolves.toBeUndefined();
  });

  it('prices a measured repository: cells per run, cost and the cap', async () => {
    const { recordChurn } = await import('../../services/backup/backup-churn-store.js');
    const { defaultRpoDeps } = await import('../../services/backup/backup-rpo-plan.js');
    await recordChurn('mail', summary(10));

    const report = await defaultRpoDeps.estimate([{ ref: 'mail', rpoSeconds: 300 }]);
    expect(report).toBeDefined();
    const text = (report?.lines ?? []).join('\n');
    expect(text).toContain('commands.backup.churn.estimate.target');
    expect(text).toContain('"cells":10');
    expect(text).toContain('"runs":288');
    expect(text).toContain('commands.backup.churn.estimate.cost');
  });

  it('never stores a summary with no measured sample', async () => {
    const { recordChurn } = await import('../../services/backup/backup-churn-store.js');
    const { defaultRpoDeps } = await import('../../services/backup/backup-rpo-plan.js');
    await recordChurn('wiki', { samples: 0, baselines: 1, skipped: 0, failed: 0 });
    await expect(
      defaultRpoDeps.estimate([{ ref: 'wiki', rpoSeconds: 300 }])
    ).resolves.toBeUndefined();
  });

  it('a family ref reads every tag measured, a bare name only itself', async () => {
    const { recordChurn } = await import('../../services/backup/backup-churn-store.js');
    const { defaultRpoDeps } = await import('../../services/backup/backup-rpo-plan.js');
    await recordChurn('shop', summary(4));
    await recordChurn('shop:test', summary(6));

    const family = await defaultRpoDeps.estimate([{ ref: 'shop:*', rpoSeconds: 900 }]);
    expect((family?.lines ?? []).join('\n')).toContain('"cells":10');
    const bare = await defaultRpoDeps.estimate([{ ref: 'shop', rpoSeconds: 900 }]);
    expect((bare?.lines ?? []).join('\n')).toContain('"cells":4');
  });
});
