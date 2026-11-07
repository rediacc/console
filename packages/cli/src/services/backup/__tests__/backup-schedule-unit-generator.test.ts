/**
 * A scheduled unit runs renet with no CLI in the loop, so the CLI's licence pre-flight (backup-store-universe.ts) never
 * sees it. The account-server origin therefore travels in the unit text as `--expect-account-server`, on the snapshot
 * command and on the failure report, both of which mint a session from the repository licence.
 */
import { spawnSync } from 'node:child_process';
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
  isolateCommands,
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

describe('the renet --store probe result reaches the scheduled unit', () => {
  const twoDests: BackupStrategyDestination[] = [
    { name: 'primary', kind: 'hosted-service' },
    { name: 'west', kind: 'hosted-service', target: 'eu-west' },
  ];
  const spec: ScheduleUnitSpec = {
    unitName: 'hourly',
    strategyName: 'hourly',
    strategy: { ...strategy, destinations: twoDests },
    schedule: strategy.schedule,
    datastore: { path: WK_DATASTORE_PATH } as ScheduleUnitSpec['datastore'],
    scope,
  };

  it('writes --store for the non-home destination when the probe found the flag', () => {
    const unit = computeDesiredUnits([spec], RENET, 4, undefined, true).get('hourly');
    const exec = execLines(unit?.serviceContent ?? '').join('\n');
    expect(exec).toContain('--store eu-west');
    expect(exec).not.toContain('--store home');
  });

  it('refuses the unit when the probe did not find the flag, rather than writing west into home', () => {
    expect(() => computeDesiredUnits([spec], RENET, 4, undefined, false)).toThrow(/--store/);
  });
});

describe('one snapshot command per enabled destination', () => {
  const home: BackupStrategyDestination = { name: 'primary', kind: 'hosted-service' };
  const west: BackupStrategyDestination = {
    name: 'west',
    kind: 'hosted-service',
    target: 'eu-west',
    bandwidthLimit: '6M',
  };
  const office: BackupStrategyDestination = {
    name: 'office',
    kind: 'hosted-service',
    target: 'office-rustfs',
    bandwidthLimit: '2M',
  };
  const build = (destinations: BackupStrategyDestination[], storeFlag = true) =>
    buildBackupCommands(
      { ...strategy, destinations },
      destinations,
      WK_DATASTORE_PATH,
      RENET,
      scope,
      undefined,
      strategy.schedule,
      undefined,
      ORIGIN,
      storeFlag
    ).commands;

  it('gives two destinations two commands in declaration order, each with its store, cap and origin', () => {
    const commands = build([west, office]);
    expect(commands).toHaveLength(2);
    expect(commands[0]).toContain(' --store eu-west ');
    expect(commands[0]).toContain(' --bwlimit 6000000 ');
    expect(commands[1]).toContain(' --store office-rustfs ');
    expect(commands[1]).toContain(' --bwlimit 2000000 ');
    for (const c of commands) expect(c.endsWith(` --expect-account-server ${ORIGIN}`)).toBe(true);
  });

  it('omits --store for a home destination, so a single-destination timer is unchanged', () => {
    const [only] = build([home]);
    expect(only).not.toContain('--store');
    expect(build([home], false)).toEqual([only]);
  });

  it('refuses a non-home destination on a renet without --store, never writing it into home', () => {
    expect(() => build([home, west], false)).toThrow(/eu-west.*does not list --store/);
  });

  it('refuses two destinations on one target', () => {
    expect(() => build([west, { ...office, target: 'eu-west' }])).toThrow(
      /duplicate|name the target "eu-west"/
    );
  });

  it('runs a failing first command and then the second, and exits non-zero in the unit', () => {
    const { serviceContent } = generateServiceUnit(
      'two',
      { ...strategy, destinations: [west, office] },
      [west, office],
      WK_DATASTORE_PATH,
      RENET,
      scope,
      4,
      strategy.schedule,
      undefined,
      ORIGIN,
      true
    );
    const lines = execLines(serviceContent);
    const [isolated, ...rest] = lines;
    expect(isolated.startsWith("/bin/sh -c 'rc=0; ")).toBe(true);
    const first = isolated.indexOf('--store eu-west');
    const second = isolated.indexOf('--store office-rustfs');
    expect(first).toBeGreaterThan(0);
    expect(second).toBeGreaterThan(first);
    expect(isolated.match(/ \|\| rc=1;/g)).toHaveLength(2);
    expect(isolated.endsWith(" exit $$rc'")).toBe(true);
    // The spot verify stays its own line after the group, so a failed snapshot is still never verified.
    for (const line of rest) expect(line).not.toContain('--store');
  });

  it('executes the isolation as written: first fails, second still runs, exit is non-zero', () => {
    // systemd turns `$$` into `$` before the shell sees the line.
    const run = (cmds: string[]) =>
      spawnSync('sh', ['-c', isolateCommands(cmds)[0].replaceAll('$$', '$')], { encoding: 'utf8' });
    const failed = run(['false', 'echo second-ran']);
    expect(failed.stdout).toContain('second-ran');
    expect(failed.status).not.toBe(0);
    expect(run(['true', 'echo b']).status).toBe(0);
  });

  it('keeps a single command bare', () => {
    expect(isolateCommands(['one'])).toEqual(['one']);
  });
});
