import { describe, expect, it } from 'vitest';
import type { RdcConfig } from '../../schema/schemas.js';
import { pruneDanglingRefs } from '../config-refs-prune.js';

function baseConfig(): RdcConfig {
  return {
    schemaVersion: 2,
    id: '00000000-0000-0000-0000-000000000000',
    version: 1,
    resources: {
      machines: {
        m1: { ip: '1.2.3.4', user: 'root' },
      },
      repositories: {
        'gitlab:latest': { repositoryGuid: '11111111-1111-1111-1111-111111111111' },
        'mail:latest': { repositoryGuid: '22222222-2222-2222-2222-222222222222' },
      },
      storages: {
        s1: { provider: 'onedrive', vaultContent: {} },
      },
      backupStrategies: {
        hourly: {
          destinations: [{ name: 'd1', storage: 's1' }],
          schedule: '0 * * * *',
        },
        daily: {
          destinations: [{ name: 'd1', storage: 's1' }],
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

  it('warns on storage destinations whose target is missing', () => {
    const cfg = baseConfig();
    cfg.resources!.backupStrategies!.daily.destinations = [
      { name: 'd1', storage: 's1' },
      { name: 'd2', storage: 'GHOST-STORAGE' },
    ];
    const r = pruneDanglingRefs(cfg);
    // Destinations are NOT auto-removed (could change strategy semantics).
    expect(cfg.resources!.backupStrategies!.daily.destinations).toHaveLength(2);
    expect(r.warnings).toHaveLength(1);
    expect(r.warnings[0]).toContain('GHOST-STORAGE');
  });

  it('removes the field entirely when the kept list goes empty', () => {
    const cfg = baseConfig();
    cfg.resources!.machines!.m1.backupStrategies = ['NONE'];
    pruneDanglingRefs(cfg);
    expect(cfg.resources!.machines!.m1.backupStrategies).toBeUndefined();
  });
});
