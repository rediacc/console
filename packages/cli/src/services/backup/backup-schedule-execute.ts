/**
 * Plan execution: the plan's payload for the `backup-schedule` job, and the summary emit.
 *
 * The mutation phase runs on the machine as one `backup-schedule` job (PLAN-detached-jobs J17). The CLI still computes
 * the plan (a hash diff against a read of the machine); this module turns it into the job's payload. renet writes each
 * file atomically (`<path>.new`, then a rename), reloads systemd, enables the timers and verifies them, so a partial
 * write or a dropped connection never leaves a half-deployed unit.
 */

import { outputService } from '../core/output.js';
import { envFilePath } from './backup-env-file.js';
import type { ReconcileOptions, ReconcilePlan, StrategyDiff } from './backup-schedule-reconcile.js';
import { sanitizeBackupOutput } from './backup-schedule-unit-generator.js';

interface ScheduleRemoval {
  name: string;
  timer: boolean;
  service: boolean;
  env: boolean;
  dangling: boolean;
}

/** The `backup-schedule` job's payload (private/renet/cmd/renet/job_backup_schedule.go, backupSchedulePayload). */
export interface SchedulePayload {
  remove: ScheduleRemoval[];
  remove_env: string[];
  files: { name: string; kind: 'service' | 'timer' | 'env'; content: string }[];
  reload: boolean;
  enable: string[];
  reset_failed: string[];
}

function hasTimer(diff: StrategyDiff): boolean {
  return diff.desired !== null && diff.desired.timerContent !== '';
}

function removalOf(diff: StrategyDiff): ScheduleRemoval | null {
  const remote = diff.remote;
  if (!remote) return null;
  return {
    name: diff.name,
    timer: remote.timerFile.exists,
    service: remote.serviceFile.exists,
    env: remote.envFile.exists,
    // A timer systemd still runs or links without its unit file cannot be disabled: renet stops it and drops its link.
    dangling: !remote.timerFile.exists && (remote.isActiveTimer || remote.isEnabledTimer),
  };
}

/** The files one created or updated strategy writes, and whether its env file is removed instead. */
function writesOf(diff: StrategyDiff): { files: SchedulePayload['files']; removeEnv: boolean } {
  const unit = diff.desired;
  const files: SchedulePayload['files'] = [];
  if (!unit) return { files, removeEnv: false };
  const name = unit.strategyName;
  // An env file that is no longer needed is removed outright: a directed removal has no staging or rollback.
  const wantsEnv = diff.changedFiles.includes('env');
  if (wantsEnv && unit.envFileContent) {
    files.push({ name, kind: 'env', content: unit.envFileContent });
  }
  if (diff.changedFiles.includes('service')) {
    files.push({ name, kind: 'service', content: unit.serviceContent });
  }
  if (diff.changedFiles.includes('timer')) {
    files.push({ name, kind: 'timer', content: unit.timerContent });
  }
  return { files, removeEnv: wantsEnv && !unit.envFileContent };
}

/**
 * The payload that applies `plan`: obsolete strategies removed first, then the changed files of every created or
 * updated strategy, the daemon-reload, the timers enabled (a timerless unit, a failure report, starts from OnFailure=
 * alone) and, with `--reset-failed`, the failed services cleared.
 */
export function buildSchedulePayload(
  plan: ReconcilePlan,
  options: Pick<ReconcileOptions, 'resetFailed'>
): SchedulePayload {
  const touched = [...plan.toCreate, ...plan.toUpdate];
  const payload: SchedulePayload = {
    remove: plan.toRemove.map(removalOf).filter((r): r is ScheduleRemoval => r !== null),
    remove_env: [],
    files: [],
    reload: plan.daemonReloadNeeded,
    enable: touched.filter(hasTimer).map((d) => d.name),
    reset_failed: options.resetFailed
      ? touched.filter((d) => d.remote?.isFailed).map((d) => d.name)
      : [],
  };
  for (const diff of touched) {
    const { files, removeEnv } = writesOf(diff);
    payload.files.push(...files);
    if (removeEnv && diff.desired) payload.remove_env.push(diff.desired.strategyName);
  }
  return payload;
}

// --------------------------------------------------------------------------- Emit plan summary ---------------------------------------------------------------------------

function formatDiffLine(diff: StrategyDiff): string {
  let line = `${diff.action} ${diff.name}`;
  if (diff.action === 'updated' && diff.changedFiles.length > 0) {
    line += ` (${diff.changedFiles.join(', ')})`;
  }
  if (diff.reason) line += `: ${diff.reason}`;
  return line;
}

export function emitPlanSummary(plan: ReconcilePlan): void {
  const all = [
    ...plan.toCreate,
    ...plan.toUpdate,
    ...plan.unchanged,
    ...plan.toRemove,
    ...plan.skippedInFlight,
  ].sort((a, b) => a.name.localeCompare(b.name));

  for (const diff of all) {
    const line = formatDiffLine(diff);
    if (diff.action === 'skipped-in-flight') {
      outputService.warn(line);
    } else {
      outputService.info(line);
    }
  }
}

export function printDryRunUnitBodies(plan: ReconcilePlan): void {
  for (const diff of [...plan.toCreate, ...plan.toUpdate]) {
    const unit = diff.desired;
    if (!unit) continue;
    outputService.info(`\n--- rediacc-backup-${unit.strategyName}.service ---`);
    outputService.info(sanitizeBackupOutput(unit.serviceContent));
    if (unit.envFileContent) {
      outputService.info(`--- ${envFilePath(unit.strategyName)} (mode 0600, values redacted) ---`);
      const keys = unit.envFileContent
        .split('\n')
        .map((line) => line.split('=')[0])
        .filter((k) => k.length > 0)
        .sort();
      outputService.info(keys.map((k) => `${k}=[REDACTED]`).join('\n'));
    }
    if (unit.timerContent) {
      outputService.info(`--- rediacc-backup-${unit.strategyName}.timer ---`);
      outputService.info(unit.timerContent);
    }
  }
}
