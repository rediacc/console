/**
 * Reconciliation core: read remote state + compute desired + diff + in-flight gate.
 *
 * This module is stateless w.r.t. the target machine — it issues read-only
 * `find`/`sha256sum`/`systemctl show` commands and produces a typed diff
 * that the executor module consumes.
 */

import { buildRcloneArgs } from '@rediacc/shared/queue-vault';
import type { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { BackupStrategyConfig } from '../../types/index.js';
import { generateEnvFile } from '../backup-env-file.js';
import { configService } from '../config-resources.js';
import { outputService } from '../output.js';
import {
  cronToOnCalendar,
  generateServiceUnit,
  generateTimerUnit,
  sha256Hex,
} from './unit-generator.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DesiredUnit {
  strategyName: string;
  serviceContent: string;
  timerContent: string;
  /** Empty string when the strategy has no credentials. */
  envFileContent: string;
}

export interface RemoteUnitFile {
  path: string;
  exists: boolean;
  sha256: string | null;
}

export interface RemoteUnitState {
  serviceFile: RemoteUnitFile;
  timerFile: RemoteUnitFile;
  envFile: RemoteUnitFile;
  isActiveService: boolean;
  isActiveAdhoc: boolean;
  isEnabledTimer: boolean;
  isActiveTimer: boolean;
  /** .service SubState === 'failed'. */
  isFailed: boolean;
}

export type StrategyAction = 'created' | 'updated' | 'unchanged' | 'removed' | 'skipped-in-flight';
export type ChangedFile = 'service' | 'timer' | 'env';

export interface StrategyDiff {
  name: string;
  action: StrategyAction;
  desired: DesiredUnit | null;
  remote: RemoteUnitState | null;
  changedFiles: ChangedFile[];
  reason?: string;
}

export interface ReconcilePlan {
  toCreate: StrategyDiff[];
  toUpdate: StrategyDiff[];
  toRemove: StrategyDiff[];
  unchanged: StrategyDiff[];
  skippedInFlight: StrategyDiff[];
  daemonReloadNeeded: boolean;
}

export interface ReconcileOptions {
  debug?: boolean;
  dryRun?: boolean;
  force?: boolean;
  resetFailed?: boolean;
}

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

const ACTIVE_STATES = new Set(['active', 'activating']);
const ENABLED_STATES = new Set(['enabled', 'enabled-runtime', 'static']);

export function isActiveState(value: string | undefined): boolean {
  return value !== undefined && ACTIVE_STATES.has(value);
}

export function isEnabledState(value: string | undefined): boolean {
  return value !== undefined && ENABLED_STATES.has(value);
}

/**
 * Extract strategy name from a rediacc-backup unit or env file basename.
 * Returns null for anything that doesn't match (including `-adhoc` service
 * files, which belong to the ad-hoc backup path, not scheduled strategies).
 */
export function parseStrategyFromPath(
  filePath: string
): { strategy: string; type: 'service' | 'timer' | 'env' } | null {
  const basename = filePath.slice(filePath.lastIndexOf('/') + 1);
  const svc = /^rediacc-backup-(.+)\.service$/.exec(basename);
  if (svc) {
    if (svc[1].endsWith('-adhoc')) return null;
    return { strategy: svc[1], type: 'service' };
  }
  const timer = /^rediacc-backup-(.+)\.timer$/.exec(basename);
  if (timer) return { strategy: timer[1], type: 'timer' };
  const env = /^backup-(.+)\.env$/.exec(basename);
  if (env) return { strategy: env[1], type: 'env' };
  return null;
}

/** Parse `systemctl show --property=...` output into records keyed by Id. */
export function parseSystemctlShow(output: string): Map<string, Record<string, string>> {
  const result = new Map<string, Record<string, string>>();
  const records = output.split(/\n\s*\n/).filter((r) => r.trim().length > 0);
  for (const record of records) {
    const props: Record<string, string> = {};
    for (const line of record.split('\n')) {
      const eq = line.indexOf('=');
      if (eq > 0) props[line.slice(0, eq)] = line.slice(eq + 1);
    }
    if (props.Id) result.set(props.Id, props);
  }
  return result;
}

async function captureStdout(
  sftp: SFTPClient,
  command: string
): Promise<{ exitCode: number; stdout: string }> {
  let stdout = '';
  const exitCode = await sftp.execStreaming(command, {
    onStdout: (data) => {
      stdout += data.toString();
    },
    onStderr: () => {},
  });
  return { exitCode, stdout };
}

// ---------------------------------------------------------------------------
// Phase A — Read remote state
// ---------------------------------------------------------------------------

async function listRemoteUnitPaths(sftp: SFTPClient): Promise<string[]> {
  const cmd =
    `sudo sh -c "find /etc/systemd/system -maxdepth 1 ` +
    `\\( -name 'rediacc-backup-*.service' -o -name 'rediacc-backup-*.timer' \\) -printf '%p\\n' 2>/dev/null; ` +
    `find /etc/rediacc -maxdepth 1 -name 'backup-*.env' -printf '%p\\n' 2>/dev/null; true"`;
  const { stdout } = await captureStdout(sftp, cmd);
  return stdout
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
}

async function hashRemoteFiles(sftp: SFTPClient, paths: string[]): Promise<Map<string, string>> {
  const hashes = new Map<string, string>();
  if (paths.length === 0) return hashes;
  const quoted = paths.map((p) => `'${p.replaceAll("'", "'\\''")}'`).join(' ');
  const { stdout } = await captureStdout(sftp, `sudo sha256sum ${quoted}`);
  for (const line of stdout.split('\n')) {
    const match = /^([0-9a-f]{64})\s+(.+)$/.exec(line);
    if (match) hashes.set(match[2], match[1]);
  }
  return hashes;
}

async function querySystemdStates(
  sftp: SFTPClient,
  strategyNames: Iterable<string>
): Promise<Map<string, Record<string, string>>> {
  const units: string[] = [];
  for (const name of strategyNames) {
    units.push(`rediacc-backup-${name}.service`);
    units.push(`rediacc-backup-${name}-adhoc.service`);
    units.push(`rediacc-backup-${name}.timer`);
  }
  if (units.length === 0) return new Map();
  const cmd = `systemctl show --property=Id,LoadState,ActiveState,SubState,UnitFileState ${units.join(' ')}`;
  const { stdout } = await captureStdout(sftp, cmd);
  return parseSystemctlShow(stdout);
}

function makeRemoteUnitFile(
  filePath: string | undefined,
  hashes: Map<string, string>
): RemoteUnitFile {
  return {
    path: filePath ?? '',
    exists: filePath !== undefined,
    sha256: filePath ? (hashes.get(filePath) ?? null) : null,
  };
}

export async function readRemoteState(
  sftp: SFTPClient,
  desiredStrategyNames: string[]
): Promise<Map<string, RemoteUnitState>> {
  const paths = await listRemoteUnitPaths(sftp);

  const allStrategies = new Set<string>(desiredStrategyNames);
  const pathsByStrategy = new Map<string, { service?: string; timer?: string; env?: string }>();
  for (const filePath of paths) {
    const parsed = parseStrategyFromPath(filePath);
    if (!parsed) continue;
    allStrategies.add(parsed.strategy);
    let entry = pathsByStrategy.get(parsed.strategy);
    if (!entry) {
      entry = {};
      pathsByStrategy.set(parsed.strategy, entry);
    }
    entry[parsed.type] = filePath;
  }

  const hashes = await hashRemoteFiles(sftp, paths);
  const systemdStates = await querySystemdStates(sftp, allStrategies);

  const result = new Map<string, RemoteUnitState>();
  for (const name of allStrategies) {
    const entry = pathsByStrategy.get(name) ?? {};
    const serviceRec = systemdStates.get(`rediacc-backup-${name}.service`) ?? {};
    const adhocRec = systemdStates.get(`rediacc-backup-${name}-adhoc.service`) ?? {};
    const timerRec = systemdStates.get(`rediacc-backup-${name}.timer`) ?? {};
    result.set(name, {
      serviceFile: makeRemoteUnitFile(entry.service, hashes),
      timerFile: makeRemoteUnitFile(entry.timer, hashes),
      envFile: makeRemoteUnitFile(entry.env, hashes),
      isActiveService: isActiveState(serviceRec.ActiveState),
      isActiveAdhoc: isActiveState(adhocRec.ActiveState),
      isEnabledTimer: isEnabledState(timerRec.UnitFileState),
      isActiveTimer: isActiveState(timerRec.ActiveState),
      isFailed: serviceRec.SubState === 'failed',
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Phase B — Compute desired units
// ---------------------------------------------------------------------------

export async function computeDesiredUnits(
  strategies: { name: string; config: BackupStrategyConfig }[],
  datastore: string,
  remoteRenetPath: string
): Promise<Map<string, DesiredUnit>> {
  const result = new Map<string, DesiredUnit>();
  for (const { name, config } of strategies) {
    const enabledDests = config.destinations.filter((d) => d.enabled !== false);
    if (enabledDests.length === 0) {
      outputService.warn(`Skipping strategy "${name}": no enabled destinations`);
      continue;
    }

    const rcloneArgsByDest = new Map<string, { remote: string; params: string[] }>();
    for (const dest of enabledDests) {
      const storageCfg = await configService.getStorage(dest.storage);
      rcloneArgsByDest.set(dest.name, buildRcloneArgs(storageCfg.vaultContent, dest.folder));
    }

    const { serviceContent, envVars } = generateServiceUnit(
      name,
      config,
      enabledDests,
      rcloneArgsByDest,
      datastore,
      remoteRenetPath
    );
    const timerContent = generateTimerUnit(name, cronToOnCalendar(config.schedule));
    result.set(name, {
      strategyName: name,
      serviceContent,
      timerContent,
      envFileContent: generateEnvFile(envVars),
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Phase C — Compute reconcile plan (pure)
// ---------------------------------------------------------------------------

function envDrifted(
  desiredEnvHash: string | null,
  remoteEnvExists: boolean,
  remoteEnvHash: string | null
): boolean {
  if (desiredEnvHash !== null) {
    return !remoteEnvExists || remoteEnvHash !== desiredEnvHash;
  }
  return remoteEnvExists;
}

function classifyDesired(unit: DesiredUnit, remote: RemoteUnitState | undefined): StrategyDiff {
  const desiredServiceHash = sha256Hex(unit.serviceContent);
  const desiredTimerHash = sha256Hex(unit.timerContent);
  const desiredEnvHash = unit.envFileContent ? sha256Hex(unit.envFileContent) : null;

  // Treat "no service or timer on remote" as fresh, even if a stale env
  // file happens to exist (reconciler will overwrite it).
  const isFresh = !remote || (!remote.serviceFile.exists && !remote.timerFile.exists);
  if (isFresh) {
    const changedFiles: ChangedFile[] = ['service', 'timer'];
    if (desiredEnvHash !== null) changedFiles.push('env');
    return {
      name: unit.strategyName,
      action: 'created',
      desired: unit,
      remote: remote ?? null,
      changedFiles,
    };
  }

  const changed: ChangedFile[] = [];
  if (remote.serviceFile.sha256 !== desiredServiceHash) changed.push('service');
  if (remote.timerFile.sha256 !== desiredTimerHash) changed.push('timer');
  if (envDrifted(desiredEnvHash, remote.envFile.exists, remote.envFile.sha256)) {
    changed.push('env');
  }

  return {
    name: unit.strategyName,
    action: changed.length === 0 ? 'unchanged' : 'updated',
    desired: unit,
    remote,
    changedFiles: changed,
  };
}

function classifyRemoved(name: string, state: RemoteUnitState): StrategyDiff | null {
  const existing: ChangedFile[] = [];
  if (state.serviceFile.exists) existing.push('service');
  if (state.timerFile.exists) existing.push('timer');
  if (state.envFile.exists) existing.push('env');
  if (existing.length === 0) return null;
  return {
    name,
    action: 'removed',
    desired: null,
    remote: state,
    changedFiles: existing,
  };
}

export function computeReconcilePlan(
  desired: Map<string, DesiredUnit>,
  remote: Map<string, RemoteUnitState>
): ReconcilePlan {
  const plan: ReconcilePlan = {
    toCreate: [],
    toUpdate: [],
    toRemove: [],
    unchanged: [],
    skippedInFlight: [],
    daemonReloadNeeded: false,
  };

  for (const [name, unit] of desired) {
    const diff = classifyDesired(unit, remote.get(name));
    if (diff.action === 'created') plan.toCreate.push(diff);
    else if (diff.action === 'updated') plan.toUpdate.push(diff);
    else plan.unchanged.push(diff);
  }

  for (const [name, state] of remote) {
    if (desired.has(name)) continue;
    const diff = classifyRemoved(name, state);
    if (diff) plan.toRemove.push(diff);
  }

  plan.daemonReloadNeeded = plan.toCreate.length + plan.toUpdate.length + plan.toRemove.length > 0;
  return plan;
}

// ---------------------------------------------------------------------------
// Phase D — In-flight safety gate
// ---------------------------------------------------------------------------

function activeUnitName(diff: StrategyDiff): string | null {
  const state = diff.remote;
  if (!state) return null;
  if (state.isActiveService) return `rediacc-backup-${diff.name}.service`;
  if (state.isActiveAdhoc) return `rediacc-backup-${diff.name}-adhoc.service`;
  return null;
}

function buildInFlightError(blocking: StrategyDiff[]): Error {
  const listStr = blocking.map((d) => `  - ${d.name}: ${d.reason}`).join('\n');
  return new Error(
    `Cannot deploy: backup(s) currently running:\n${listStr}\n\n` +
      `Options:\n` +
      `  - Wait for the backup to finish and retry\n` +
      `  - Cancel it: rdc machine backup cancel -m <machine> --strategy ${blocking[0].name}\n` +
      `  - Use --force to deploy anyway (running invocation keeps old unit; new unit applies on next tick)`
  );
}

function collectInFlight(
  plan: ReconcilePlan,
  force: boolean
): { blocking: StrategyDiff[]; warned: string[] } {
  const blocking: StrategyDiff[] = [];
  const warned: string[] = [];
  for (const list of [plan.toUpdate, plan.toRemove]) {
    for (const diff of list) {
      const unit = activeUnitName(diff);
      if (!unit) continue;
      if (force) {
        warned.push(unit);
      } else {
        blocking.push({
          ...diff,
          action: 'skipped-in-flight',
          reason: `${unit} is currently running`,
        });
      }
    }
  }
  return { blocking, warned };
}

/**
 * Fail fast (or warn, with `--force`) when a backup is running for a
 * strategy we're about to modify or remove. Running invocation keeps its
 * in-memory unit; the new unit takes effect on the next timer tick.
 */
export function applyInFlightGate(plan: ReconcilePlan, force: boolean): void {
  const { blocking, warned } = collectInFlight(plan, force);

  if (blocking.length > 0) {
    const blockedNames = new Set(blocking.map((d) => d.name));
    plan.toUpdate = plan.toUpdate.filter((d) => !blockedNames.has(d.name));
    plan.toRemove = plan.toRemove.filter((d) => !blockedNames.has(d.name));
    plan.skippedInFlight = blocking;
    plan.daemonReloadNeeded =
      plan.toCreate.length + plan.toUpdate.length + plan.toRemove.length > 0;
    throw buildInFlightError(blocking);
  }

  for (const unit of warned) {
    outputService.warn(
      `${unit} is currently running; deploy proceeds. The running invocation keeps its in-memory unit; ` +
        `the new configuration applies on the next timer tick.`
    );
  }
}
