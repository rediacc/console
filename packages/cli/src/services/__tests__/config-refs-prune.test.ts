import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import { pruneDanglingRefs } from '../config/config-refs-prune.js';

function baseConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000000',
    version: 1,
    resources: {
      machines: {
        m1: { ip: '1.2.3.4', user: 'root' },
      },
      repositories: {
        gitlab: {
          grand: 'latest',
          tags: { latest: { repositoryGuid: '11111111-1111-1111-1111-111111111111' } },
        },
        mail: {
          grand: 'latest',
          tags: { latest: { repositoryGuid: '22222222-2222-2222-2222-222222222222' } },
        },
      },
      backupStrategies: {
        hourly: {
          destinations: [{ kind: 'hosted-service', name: 'd1' }],
          schedule: '0 * * * *',
        },
        daily: {
          destinations: [{ kind: 'hosted-service', name: 'd1' }],
          schedule: '0 0 * * *',
        },
      },
    },
  };
}

describe('pruneDanglingRefs', () => {
  it('drops machine→strategy refs that name an unknown strategy', () => {
    const cfg = baseConfig();
    cfg.resources!.machines!.m1.backupStrategies = ['hourly', 'NONE', 'daily'];
    const r = pruneDanglingRefs(cfg);
    expect(cfg.resources!.machines!.m1.backupStrategies).toEqual(['hourly', 'daily']);
    expect(r.dropped.map((d) => d.value)).toEqual(['NONE']);
    expect(r.dropped[0].path).toContain('resources.machines.m1.backupStrategies');
  });

  it('drops strategy→repo excludes that name an unknown repo', () => {
    const cfg = baseConfig();
    cfg.resources!.backupStrategies!.daily.exclude = ['mail', 'GHOST', 'gitlab'];
    const r = pruneDanglingRefs(cfg);
    expect(cfg.resources!.backupStrategies!.daily.exclude).toEqual(['mail', 'gitlab']);
    expect(r.dropped.map((d) => d.value)).toEqual(['GHOST']);
  });

  it('keeps live refs untouched', () => {
    const cfg = baseConfig();
    cfg.resources!.machines!.m1.backupStrategies = ['hourly', 'daily'];
    cfg.resources!.backupStrategies!.daily.exclude = ['mail'];
    const r = pruneDanglingRefs(cfg);
    expect(r.dropped).toHaveLength(0);
    expect(cfg.resources!.machines!.m1.backupStrategies).toEqual(['hourly', 'daily']);
    expect(cfg.resources!.backupStrategies!.daily.exclude).toEqual(['mail']);
  });

  it('removes the field entirely when the kept list goes empty', () => {
    const cfg = baseConfig();
    cfg.resources!.machines!.m1.backupStrategies = ['NONE'];
    pruneDanglingRefs(cfg);
    expect(cfg.resources!.machines!.m1.backupStrategies).toBeUndefined();
  });
});
