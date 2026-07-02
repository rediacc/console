/**
 * Plan execution: mutation phase + post-deploy verification + summary emit.
 *
 * All writes go through atomic staging: content is first written to
 * `<finalPath>.new` via `sudo tee`/`sudo sh -c 'umask 077 && cat >'`, then
 * `mv`-committed. `mv` within the same filesystem is atomic, so a partial
 * write or SSH disconnect mid-batch never leaves the machine with a
 * half-deployed unit.
 */

import type { SFTPClient } from '../../shared-desktop/sftp/index.js';
import { envFilePath } from '../backup-env-file.js';
import { outputService } from '../output.js';
import type {
  ReconcileOptions,
  ReconcilePlan,
  RemoteUnitState,
  StrategyDiff,
} from './reconcile.js';
import { isEnabledState, parseSystemctlShow } from './reconcile.js';
import { sanitizeBackupOutput } from './unit-generator.js';

async function runRemoteCommand(
  sftp: SFTPClient,
  command: string,
  options: ReconcileOptions,
  errorMessage: string
): Promise<void> {
  const exitCode = await sftp.execStreaming(command, {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => process.stderr.write(data),
  });
  if (exitCode !== 0) {
    throw new Error(`${errorMessage} (exit ${exitCode})`);
  }
}

async function captureStdout(sftp: SFTPClient, command: string): Promise<string> {
  let stdout = '';
  await sftp.execStreaming(command, {
    onStdout: (data) => {
      stdout += data.toString();
    },
    onStderr: () => {},
  });
  return stdout;
}

function shellEscape(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

async function stageFile(
  sftp: SFTPClient,
  finalPath: string,
  content: string,
  mode: 'secret' | 'normal',
  options: ReconcileOptions
): Promise<string> {
  const stagingPath = `${finalPath}.new`;
  const writeCmd =
    mode === 'secret'
      ? `sudo sh -c 'umask 077 && cat > ${stagingPath}'`
      : `sudo tee ${stagingPath} > /dev/null`;
  const exitCode = await sftp.execStreaming(writeCmd, {
    stdin: content,
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => process.stderr.write(data),
  });
  if (exitCode !== 0) {
    throw new Error(`Failed to stage ${stagingPath} (exit ${exitCode})`);
  }
  return stagingPath;
}

async function cleanupOrphanedStaging(sftp: SFTPClient): Promise<void> {
  // rm -v prints one line per removed file; any output means a prior run
  // left staging files behind — flag that to the operator.
  const cmd =
    `sudo sh -c 'rm -fv /etc/systemd/system/rediacc-backup-*.new ` +
    `/etc/rediacc/backup-*.env.new 2>/dev/null; true'`;
  const stdout = await captureStdout(sftp, cmd);
  if (stdout.trim().length > 0) {
    const count = stdout.trim().split('\n').length;
    outputService.warn(
      `Cleaned up orphaned staging files from a prior interrupted deploy: ${count} file(s)`
    );
  }
}

interface StagedFile {
  stagingPath: string;
  finalPath: string;
}

function collectExistingPaths(remote: RemoteUnitState): string[] {
  const paths: string[] = [];
  if (remote.serviceFile.exists) paths.push(remote.serviceFile.path);
  if (remote.timerFile.exists) paths.push(remote.timerFile.path);
  if (remote.envFile.exists) paths.push(remote.envFile.path);
  return paths;
}

async function removeOneStrategy(
  sftp: SFTPClient,
  diff: StrategyDiff,
  options: ReconcileOptions
): Promise<void> {
  const remote = diff.remote;
  if (!remote) return;
  await runRemoteCommand(
    sftp,
    `sudo systemctl disable --now rediacc-backup-${diff.name}.timer`,
    options,
    `Failed to disable timer for removed strategy "${diff.name}"`
  );
  const paths = collectExistingPaths(remote);
  if (paths.length === 0) return;
  await runRemoteCommand(
    sftp,
    `sudo rm -f ${paths.map(shellEscape).join(' ')}`,
    options,
    `Failed to remove files for strategy "${diff.name}"`
  );
}

async function applyRemovals(
  sftp: SFTPClient,
  toRemove: StrategyDiff[],
  options: ReconcileOptions
): Promise<void> {
  for (const diff of toRemove) {
    await removeOneStrategy(sftp, diff, options);
  }
}

async function stageEnvFile(
  sftp: SFTPClient,
  diff: StrategyDiff,
  staged: StagedFile[],
  options: ReconcileOptions
): Promise<void> {
  const unit = diff.desired;
  if (!unit) return;
  const finalPath = envFilePath(unit.strategyName);
  if (unit.envFileContent) {
    const stagingPath = await stageFile(sftp, finalPath, unit.envFileContent, 'secret', options);
    staged.push({ stagingPath, finalPath });
  } else {
    // Env file previously existed but is no longer needed. No staging/rollback
    // for removals — the deploy semantics accept this as a directed change.
    await runRemoteCommand(
      sftp,
      `sudo rm -f ${shellEscape(finalPath)}`,
      options,
      `Failed to remove obsolete env file for "${unit.strategyName}"`
    );
  }
}

async function stageTouched(
  sftp: SFTPClient,
  touched: StrategyDiff[],
  options: ReconcileOptions
): Promise<StagedFile[]> {
  const staged: StagedFile[] = [];
  try {
    for (const diff of touched) {
      const unit = diff.desired;
      if (!unit) continue;
      if (diff.changedFiles.includes('env')) {
        await stageEnvFile(sftp, diff, staged, options);
      }
      if (diff.changedFiles.includes('service')) {
        const finalPath = `/etc/systemd/system/rediacc-backup-${unit.strategyName}.service`;
        const stagingPath = await stageFile(
          sftp,
          finalPath,
          unit.serviceContent,
          'normal',
          options
        );
        staged.push({ stagingPath, finalPath });
      }
      if (diff.changedFiles.includes('timer')) {
        const finalPath = `/etc/systemd/system/rediacc-backup-${unit.strategyName}.timer`;
        const stagingPath = await stageFile(sftp, finalPath, unit.timerContent, 'normal', options);
        staged.push({ stagingPath, finalPath });
      }
    }
    return staged;
  } catch (err) {
    await rollbackStaged(sftp, staged);
    throw err;
  }
}

async function rollbackStaged(sftp: SFTPClient, staged: StagedFile[]): Promise<void> {
  if (staged.length === 0) return;
  const quoted = staged.map((s) => shellEscape(s.stagingPath)).join(' ');
  await sftp
    .execStreaming(`sudo rm -f ${quoted}`, {
      onStdout: () => {},
      onStderr: () => {},
    })
    .catch(() => {
      /* best-effort cleanup */
    });
}

async function commitStaged(
  sftp: SFTPClient,
  staged: StagedFile[],
  options: ReconcileOptions
): Promise<void> {
  for (const { stagingPath, finalPath } of staged) {
    await runRemoteCommand(
      sftp,
      `sudo mv ${shellEscape(stagingPath)} ${shellEscape(finalPath)}`,
      options,
      `Failed to commit ${finalPath}`
    );
  }
}

async function finalizeSystemd(
  sftp: SFTPClient,
  plan: ReconcilePlan,
  options: ReconcileOptions
): Promise<void> {
  if (plan.daemonReloadNeeded) {
    await runRemoteCommand(
      sftp,
      'sudo systemctl daemon-reload',
      options,
      'Failed to reload systemd daemon'
    );
  }

  const touched = [...plan.toCreate, ...plan.toUpdate];
  for (const diff of touched) {
    await runRemoteCommand(
      sftp,
      `sudo systemctl enable --now rediacc-backup-${diff.name}.timer`,
      options,
      `Failed to enable timer for "${diff.name}"`
    );
  }

  if (options.resetFailed) {
    for (const diff of touched) {
      if (diff.remote?.isFailed) {
        await runRemoteCommand(
          sftp,
          `sudo systemctl reset-failed rediacc-backup-${diff.name}.service`,
          options,
          `Failed to reset-failed for "${diff.name}"`
        );
      }
    }
  }
}

async function ensureEtcRediacc(
  sftp: SFTPClient,
  touched: StrategyDiff[],
  options: ReconcileOptions
): Promise<void> {
  const needed = touched.some((d) => d.changedFiles.includes('env') && d.desired?.envFileContent);
  if (!needed) return;
  await runRemoteCommand(
    sftp,
    'sudo install -d -m 0755 -o root -g root /etc/rediacc',
    options,
    'Failed to ensure /etc/rediacc exists'
  );
}

/**
 * Execute a reconciliation plan: remove obsolete units, stage+commit
 * created/updated units, daemon-reload, enable timers. Writes are atomic
 * via `<path>.new` staging + `mv`.
 */
export async function executePlan(
  sftp: SFTPClient,
  plan: ReconcilePlan,
  options: ReconcileOptions
): Promise<void> {
  await cleanupOrphanedStaging(sftp);
  await applyRemovals(sftp, plan.toRemove, options);

  const touched = [...plan.toCreate, ...plan.toUpdate];
  await ensureEtcRediacc(sftp, touched, options);

  const staged = await stageTouched(sftp, touched, options);
  await commitStaged(sftp, staged, options);

  await finalizeSystemd(sftp, plan, options);
}

// ---------------------------------------------------------------------------
// Phase F — Post-deploy verification
// ---------------------------------------------------------------------------

function diagnoseTimer(timer: string, rec: Record<string, string> | undefined): string | null {
  if (!rec) return `${timer}: no state returned by systemctl show`;
  const issues: string[] = [];
  if (rec.LoadState !== 'loaded') issues.push(`LoadState=${rec.LoadState}`);
  if (!isEnabledState(rec.UnitFileState)) issues.push(`UnitFileState=${rec.UnitFileState}`);
  if (rec.ActiveState !== 'active') issues.push(`ActiveState=${rec.ActiveState}`);
  return issues.length > 0 ? `${timer}: ${issues.join(', ')}` : null;
}

export async function verifyPostDeploy(sftp: SFTPClient, plan: ReconcilePlan): Promise<void> {
  const timers = [...plan.toCreate, ...plan.toUpdate].map((d) => `rediacc-backup-${d.name}.timer`);
  if (timers.length === 0) return;

  const cmd = `systemctl show --property=Id,LoadState,ActiveState,UnitFileState ${timers.join(' ')}`;
  const stdout = await captureStdout(sftp, cmd);
  const records = parseSystemctlShow(stdout);

  const failures: string[] = [];
  for (const timer of timers) {
    const issue = diagnoseTimer(timer, records.get(timer));
    if (issue) failures.push(issue);
  }

  if (failures.length > 0) {
    throw new Error(
      `Post-deploy verification failed:\n${failures.map((f) => `  - ${f}`).join('\n')}\n` +
        `Diagnose with: journalctl -u <timer-name>`
    );
  }
}

// ---------------------------------------------------------------------------
// Phase G — Emit plan summary
// ---------------------------------------------------------------------------

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
    outputService.info(`--- rediacc-backup-${unit.strategyName}.timer ---`);
    outputService.info(unit.timerContent);
  }
}
