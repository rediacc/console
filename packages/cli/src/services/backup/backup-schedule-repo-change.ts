/**
 * The two questions a repository change asks before it touches a machine's backup schedule.
 *
 * 1. Does the change move the schedule at all? A fork joins a unit only when a strategy names its family (an include
 *    list, or a `name:*` per-repo target); a fork of a repository whose units name exact tags changes no unit text, so
 *    re-rendering would provision renet, refresh every repository licence on the machine and read every unit for a
 *    plan of "unchanged". {@link repoChangeMovesSchedule} answers from the config alone.
 *
 * 2. Is this config the schedule's owner? A deployed unit records the account server it was rendered for in its
 *    `--expect-account-server` flag. A re-render from another config (eu-bench against a machine the stable config
 *    scheduled) would repoint those timers at that config's account server, so a repository change re-renders only
 *    when every recorded origin is this config's. A machine whose units record none is not re-rendered either: no
 *    owner can be proven, and `rdc backup schedule` from the owning config is the deploy verb.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { configService } from '../config/config-resources.js';
import { machineUnitSpecs, type ScheduledStrategy } from './backup-schedule-targets.js';
import { EXPECT_ACCOUNT_SERVER_FLAG } from './backup-schedule-unit-generator.js';

/** The config with one repository GUID removed from every family, as it stood before that repository existed. */
function withoutRepository(config: RdcConfig, repositoryGuid: string): RdcConfig {
  const families = config.resources?.repositories ?? {};
  const pruned = Object.fromEntries(
    Object.entries(families).map(([name, family]) => [
      name,
      {
        ...family,
        tags: Object.fromEntries(
          Object.entries(family.tags).filter(([, tag]) => tag.repositoryGuid !== repositoryGuid)
        ),
      },
    ])
  );
  return { ...config, resources: { ...config.resources, repositories: pruned } } as RdcConfig;
}

/** The unit specs as comparable text: the parts that reach a unit's name, timer and argv. */
function specFingerprint(
  strategies: { name: string; config: ScheduledStrategy }[],
  config: RdcConfig,
  machineName: string
): string {
  return JSON.stringify(
    machineUnitSpecs(strategies, config, machineName).map((spec) => ({
      unit: spec.unitName,
      schedule: spec.schedule,
      datastore: spec.datastore.path,
      scope: spec.scope,
      run: spec.run ?? null,
    }))
  );
}

/**
 * Whether adding `repositoryGuid` (already registered in the active config) changes any backup unit of the machine.
 * False when the machine binds no enabled strategy, and false when the specs cannot be resolved: a fork never
 * re-renders a schedule it cannot prove it moves, and `rdc backup schedule` reports the resolution error itself.
 */
export async function repoChangeMovesSchedule(
  machineName: string,
  repositoryGuid: string
): Promise<boolean> {
  try {
    const localConfig = await configService.getLocalConfig();
    const names = localConfig.machines[machineName]?.backupStrategies ?? [];
    if (names.length === 0) return false;
    const strategies: { name: string; config: ScheduledStrategy }[] = [];
    for (const name of names) {
      const strategy = await configService.getBackupStrategy(name);
      if (strategy && strategy.enabled !== false) strategies.push({ name, config: strategy });
    }
    if (strategies.length === 0) return false;
    const config = await configService.getCurrent();
    if (!config) return false;
    return (
      specFingerprint(strategies, config, machineName) !==
      specFingerprint(strategies, withoutRepository(config, repositoryGuid), machineName)
    );
  } catch {
    return false;
  }
}

/** The account-server origins the machine's deployed backup service units record, one per line of `grep -o`. */
export async function readRecordedScheduleOrigins(sftp: SFTPClient): Promise<string[]> {
  let out = '';
  await sftp.execStreaming(
    `sudo sh -c "grep -ho -- '${EXPECT_ACCOUNT_SERVER_FLAG} [^ ]*' /etc/systemd/system/rediacc-backup-*.service 2>/dev/null; true"`,
    {
      onStdout: (data) => {
        out += data.toString();
      },
      onStderr: () => {},
    }
  );
  return parseRecordedOrigins(out);
}

/** The distinct origins in `grep -o` output of `--expect-account-server <origin>` matches, sorted. */
export function parseRecordedOrigins(output: string): string[] {
  const origins = new Set<string>();
  for (const line of output.split('\n')) {
    const value = line.trim().slice(EXPECT_ACCOUNT_SERVER_FLAG.length).trim();
    if (line.trim().startsWith(EXPECT_ACCOUNT_SERVER_FLAG) && value) origins.add(value);
  }
  return [...origins].sort((a, b) => a.localeCompare(b));
}

/**
 * Why this config may not re-render the machine's schedule after a repository change, or undefined when it may:
 * every origin the deployed units record is this config's `expected` origin.
 */
export function scheduleOwnerRefusal(
  recorded: string[],
  expected: string | undefined
): string | undefined {
  if (recorded.length === 0) {
    return 'its deployed units record no account server, so no owning config can be proven';
  }
  if (!expected) {
    return `its units are held to ${recorded.join(', ')} and this config names no account server`;
  }
  const foreign = recorded.filter((origin) => origin !== expected);
  if (foreign.length > 0) {
    return `its units are held to ${foreign.join(', ')}, not this config's ${expected}`;
  }
  return undefined;
}
