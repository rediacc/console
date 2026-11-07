/**
 * A scheduled unit runs renet with no CLI in the loop, so the CLI's licence pre-flight (backup-store-universe.ts) never
 * sees it. The account-server origin therefore travels in the unit text as `--expect-account-server`, on the snapshot
 * command and on the failure report, both of which mint a session from the repository licence.
 */
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../../types/index.js';
import { computeDesiredUnits } from '../backup-schedule-reconcile.js';
import type { ScheduleUnitSpec } from '../backup-schedule-targets.js';
import {
  accountServerFlags,
  buildBackupCommands,
  generateAlertServiceUnit,
  generateServiceUnit,
} from '../backup-schedule-unit-generator.js';

const RENET = '/usr/bin/renet';
const ORIGIN = 'https://bench.rediacc.com';
const hosted: BackupStrategyDestination = { name: 'chunks', kind: 'hosted-service' };
const strategy: BackupStrategyConfig = { destinations: [hosted], schedule: '0 * * * *' };
const scope = { exclude: [] };

const execLines = (unit: string): string[] =>
  unit
    .split('\n')
    .filter((l) => l.startsWith('ExecStart='))
    .map((l) => l.slice('ExecStart='.length));

describe('--expect-account-server in scheduled units', () => {
  it('ends the snapshot command with the config origin', () => {
    const { commands } = buildBackupCommands(
      strategy,
      [hosted],
      WK_DATASTORE_PATH,
      RENET,
      scope,
      undefined,
      strategy.schedule,
      undefined,
      ORIGIN
    );
    expect(commands).toHaveLength(1);
    expect(
      commands[0].startsWith(`${RENET} backup snapshot --datastore ${WK_DATASTORE_PATH}`)
    ).toBe(true);
    expect(commands[0].endsWith(` --expect-account-server ${ORIGIN}`)).toBe(true);
  });

  it('writes the flag into the snapshot ExecStart of the service unit, and only there', () => {
    const { serviceContent } = generateServiceUnit(
      'hourly',
      strategy,
      [hosted],
      WK_DATASTORE_PATH,
      RENET,
      scope,
      4,
      strategy.schedule,
      undefined,
      ORIGIN
    );
    const [snapshot, ...rest] = execLines(serviceContent);
    expect(snapshot).toContain(' backup snapshot ');
    expect(snapshot).toContain(` --expect-account-server ${ORIGIN}`);
    // The spot verify reads local files and mints no session; renet's verify has no such flag.
    for (const line of rest) expect(line).not.toContain('--expect-account-server');
  });

  it('writes the flag into the failure report, which mints a session too', () => {
    const unit = generateAlertServiceUnit(
      'hourly',
      WK_DATASTORE_PATH,
      RENET,
      scope,
      'snapshot',
      ORIGIN
    );
    const [report] = execLines(unit);
    expect(report).toContain(' backup report ');
    expect(report.endsWith(` --expect-account-server ${ORIGIN}`)).toBe(true);
  });

  it('threads the origin from computeDesiredUnits into the snapshot and both alert units', () => {
    const spec: ScheduleUnitSpec = {
      unitName: 'hourly',
      strategyName: 'hourly',
      strategy,
      schedule: strategy.schedule,
      datastore: { path: WK_DATASTORE_PATH } as ScheduleUnitSpec['datastore'],
      scope,
    };
    const units = computeDesiredUnits([spec], RENET, 4, ORIGIN);
    const withFlag = [...units.values()]
      .filter((u) => execLines(u.serviceContent).some((l) => l.includes('--expect-account-server')))
      .map((u) => u.strategyName)
      .sort((a, b) => a.localeCompare(b));
    expect(withFlag).toEqual(['hourly', 'hourly.alert', 'hourly.verify.alert']);
  });

  it('emits nothing without an origin, so a caller with no config renders the unit it always did', () => {
    expect(accountServerFlags(undefined)).toEqual([]);
    const { commands } = buildBackupCommands(strategy, [hosted], WK_DATASTORE_PATH, RENET, scope);
    expect(commands[0]).not.toContain('--expect-account-server');
  });
});
