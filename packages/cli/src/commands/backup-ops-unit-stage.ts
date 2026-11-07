import type { SFTPClient } from '../remote/sftp/index.js';
import {
  ALERT_UNIT_SUFFIX,
  VERIFY_UNIT_SUFFIX,
} from '../services/backup/backup-schedule-verify.js';
import { outputService } from '../services/core/output.js';
import { writeStderr } from '../services/core/request-context.js';
import { shellQuote } from '../utils/shell-quote.js';

/** Resolve which strategy names to trigger. */
export function resolveStrategyNames(
  strategyFilter: string | undefined,
  boundNames: string[],
  allStrategyNames: string[]
): string[] {
  if (strategyFilter) return [strategyFilter];
  if (boundNames.length > 0) return boundNames;
  return allStrategyNames;
}

/**
 * The unit names a strategy runs as on a machine: the base unit, one per datastore (`.ds.`) and one per
 * repository with its own cadence (`.repo.`), as `backup schedule` renders them. A strategy that is not
 * bound to the machine, or whose units cannot be resolved, falls back to its bare name.
 */
export async function strategyUnitNames(
  machineName: string,
  strategyName: string
): Promise<string[]> {
  const { expectedScheduleUnits } = await import('../services/backup/backup-schedule.js');
  let units: string[] = [];
  try {
    units = (await expectedScheduleUnits(machineName))
      .filter((u) => u.strategyName === strategyName)
      .map((u) => u.unitName);
  } catch {
    units = [];
  }
  return units.length > 0 ? units : [strategyName];
}

export const SYSTEMD_DIR = '/etc/systemd/system';
export const UNIT_PREFIX = 'rediacc-backup-';
export const UNIT_SUFFIX = '.service';

/**
 * Whether a unit name (after `rediacc-backup-`) is one of the strategy's scheduled units: the base unit, a `.ds.` or a
 * `.repo.` unit. A verify or alert companion and the ad-hoc unit are not.
 */
function isStrategyUnit(strategyName: string, unit: string): boolean {
  if (unit === strategyName) return true;
  if (!unit.startsWith(`${strategyName}.ds.`) && !unit.startsWith(`${strategyName}.repo.`)) {
    return false;
  }
  return !unit.endsWith(VERIFY_UNIT_SUFFIX) && !unit.endsWith(ALERT_UNIT_SUFFIX);
}

/**
 * The strategy's scheduled units installed on the machine, read from the unit files `backup schedule` writes. The
 * machine is the source of truth: a schedule applied through another config (or a binding this config lacks) is still
 * found, and the check needs neither D-Bus nor an unprivileged `systemctl cat` (which printed nothing on a machine
 * whose `backup status` read the same unit as scheduled). A unit file left on the machine after its binding was removed
 * is still listed and started: the machine, not the config, says what is scheduled. The config's expected units come
 * first, in their order.
 */
export async function deployedStrategyUnits(
  sftp: SFTPClient,
  strategyName: string,
  expected: string[]
): Promise<string[]> {
  let listing = '';
  let listingError = '';
  const exitCode = await sftp.execStreaming(`sudo -n ls -1 ${shellQuote(SYSTEMD_DIR)}`, {
    onStdout: (data) => {
      listing += data;
    },
    onStderr: (data) => {
      listingError += data;
    },
  });
  // A failed listing is not an empty one: an empty answer would stage an ad-hoc unit beside a deployed schedule.
  if (exitCode !== 0) {
    throw new Error(
      `Could not list the installed backup units on the machine (exit ${exitCode}): ${listingError.trim() || 'no output'}`
    );
  }
  const installed = listing
    .split('\n')
    .map((line) => line.trim())
    .filter((file) => file.startsWith(UNIT_PREFIX) && file.endsWith(UNIT_SUFFIX))
    .map((file) => file.slice(UNIT_PREFIX.length, -UNIT_SUFFIX.length))
    .filter((unit) => isStrategyUnit(strategyName, unit));
  const found = new Set(installed);
  const ordered = expected.filter((unit) => found.has(unit));
  return [...ordered, ...installed.filter((unit) => !ordered.includes(unit)).sort()];
}

/**
 * Stage the ad-hoc service of a strategy with no deployed unit, so the backup-unit job can start it by name
 * (PLAN-detached-jobs section 21). Returns the unit name, or undefined when the strategy covers no repository here.
 */
export async function stageAdhocUnit(
  sftp: SFTPClient,
  machineName: string,
  name: string,
  config: import('../types/index.js').BackupStrategyConfig,
  remoteRenetPath: string,
  debug?: boolean
): Promise<string | undefined> {
  outputService.info(`No deployed unit for "${name}", running ad-hoc...`);
  const [
    { buildStrategyCommandsForMachine, sanitizeBackupOutput },
    { accountServerForRenet },
    { expectedAccountServerOrigin, storeFlagForRenet },
  ] = await Promise.all([
    import('../services/backup/backup-schedule.js'),
    import('../services/backup/backup-schedule-reconcile.js'),
    import('../services/backup/backup-store-universe.js'),
  ]);
  const commands = await buildStrategyCommandsForMachine(
    machineName,
    name,
    config,
    remoteRenetPath,
    await accountServerForRenet(sftp, remoteRenetPath, expectedAccountServerOrigin()),
    await storeFlagForRenet(sftp, remoteRenetPath)
  );
  if (commands.length === 0) {
    outputService.warn(`Backup strategy "${name}" covers no repository on ${machineName}`);
    return undefined;
  }

  const adhocUnit = `rediacc-backup-${name}-adhoc`;
  await clearFinishedAdhocUnit(sftp, adhocUnit, name);
  const [{ generateAdhocServiceUnit }, { resolveMachineCpuCount }] = await Promise.all([
    import('../services/backup/backup-schedule-unit-generator.js'),
    import('../services/backup/backup-schedule-reconcile.js'),
  ]);
  const content = generateAdhocServiceUnit(
    name,
    commands,
    await resolveMachineCpuCount(sftp),
    config.cpuLimit
  );

  if (debug) {
    outputService.info(`Writing ${adhocUnit}.service:\n${sanitizeBackupOutput(content)}`);
  }

  const exitCode = await sftp.execStreaming(
    `sudo tee ${shellQuote(`${SYSTEMD_DIR}/${adhocUnit}.service`)} > /dev/null && sudo systemctl daemon-reload`,
    { stdin: content, onStdout: () => {}, onStderr: (data) => writeStderr(data) }
  );
  if (exitCode !== 0) {
    throw new Error(`Failed to stage the ad-hoc backup unit for "${name}" (exit ${exitCode})`);
  }
  return adhocUnit;
}

/** SubStates of a unit that has finished (or was never loaded): only these are safe to stop and clear. */
const FINISHED_SUBSTATES = new Set(['', 'dead', 'exited', 'failed']);

/**
 * Rewriting an ad-hoc unit under a running backup would orphan it, and a transient unit of an earlier release
 * (`--remain-after-exit`) shadows the file written here. Refuse unless it has finished (any transitional state such
 * as auto-restart or reload counts as running); otherwise stop it and clear its failed state so the name is free.
 */
async function clearFinishedAdhocUnit(sftp: SFTPClient, unit: string, name: string): Promise<void> {
  let subState = '';
  await sftp.execStreaming(
    `systemctl show -p SubState --value ${shellQuote(`${unit}.service`)} 2>/dev/null || true`,
    {
      onStdout: (data) => {
        subState += data;
      },
      onStderr: () => {},
    }
  );
  if (!FINISHED_SUBSTATES.has(subState.trim())) {
    throw new Error(
      `An ad-hoc backup for "${name}" is still running (${unit}.service). Wait for it, or cancel it with: rdc backup cancel ${name}`
    );
  }
  await sftp.execStreaming(
    `sudo systemctl stop ${shellQuote(`${unit}.service`)} 2>/dev/null; sudo systemctl reset-failed ${shellQuote(`${unit}.service`)} 2>/dev/null; true`,
    { onStdout: () => {}, onStderr: () => {} }
  );
}
