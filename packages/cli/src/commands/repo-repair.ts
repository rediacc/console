/**
 * `rdc repo repair <ref>` (D-remedy, X4): run the repository's Rediaccfile repair() functions through renet
 * `repository repair`, with the classes of `rdc machine repair`, then health() again.
 *
 * Each Rediaccfile declares its class with `# rediacc:repair class=auto-safe|auto-with-backup [window=only]`.
 * auto-safe runs; auto-with-backup runs only with `--with-backup`, after a successful snapshot of the repository; an
 * undeclared repair() is operator-only and runs only after its prompt is answered (or with `--yes`); window=only runs
 * only inside the machine's maintenance window, or with `--window-override`. Exit 0 when health() ends ok (or has no
 * check), 1 on a warning, 2 on an error, a failed repair() or a renet failure.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { ensureRepositoryNetworkId } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { type ExecuteResult, getExecutor } from '../services/executor/executor-factory.js';
import { isRenetFlagUnsupported } from '../services/executor/job-client.js';
import { parseCapturedJson } from '../services/executor/renet-output.js';
import type { OutputFormat } from '../types/index.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { inMaintenanceWindow } from './machine/repair.js';
import {
  REPO_HEALTH_LEVEL_EXIT,
  type RepoHealthLevel,
  type RepoHealthReport,
} from './repo-health.js';

/** One Rediaccfile's part of renet's RepairReport. */
interface RepoRepairFile {
  file: string;
  class: string;
  declared: boolean;
  window_only: boolean;
  health_level: RepoHealthLevel;
  result: string;
  reason?: string;
  exit: number;
  detail?: string;
}

/** renet's RepairReport (`renet repository repair --json`). */
export interface RepoRepairReport {
  before: RepoHealthReport & { level: RepoHealthLevel };
  files: RepoRepairFile[];
  after?: RepoHealthReport & { level: RepoHealthLevel };
  ran: number;
  failed: number;
}

export interface RepoRepairOptions {
  dryRun?: boolean;
  withBackup?: boolean;
  windowOverride?: boolean;
  yes?: boolean;
}

/** The machine side of one `repo repair`, injected so the class decisions are testable. */
export interface RepoRepairDeps {
  /** One `repository_repair` call; `dryRun` plans without running any repair(). */
  repair: (allowClasses: string[], inWindow: boolean, dryRun: boolean) => Promise<RepoRepairReport>;
  snapshot: () => Promise<{ ok: boolean; detail?: string }>;
  /** Ask before running operator-only repair() functions; false when nobody can answer. */
  confirm: (files: string[]) => Promise<boolean>;
}

export interface RepoRepairOutcome {
  report: RepoRepairReport;
  allowClasses: string[];
  /** Why a planned class did not run: `snapshot-failed`, `not-confirmed`, `needs-backup`. */
  withheld: string[];
  exitCode: number;
}

/** The exit code of a finished run: a failed repair() is 2, otherwise the level health() ends at. */
export function repoRepairExitCode(report: RepoRepairReport): number {
  if (report.failed > 0) return 2;
  const level = (report.after ?? report.before).level;
  return REPO_HEALTH_LEVEL_EXIT[level] ?? REPO_HEALTH_LEVEL_EXIT.error;
}

/** Whether auto-with-backup may run: only with --with-backup and, outside a dry run, a snapshot that succeeded. */
async function backupDecision(
  planned: RepoRepairFile[],
  opts: RepoRepairOptions,
  deps: RepoRepairDeps
): Promise<{ allow: boolean; withheld?: string }> {
  if (!planned.some((f) => f.class === 'auto-with-backup')) return { allow: false };
  if (!opts.withBackup) return { allow: false, withheld: 'needs-backup' };
  if (opts.dryRun) return { allow: true };
  return (await deps.snapshot()).ok
    ? { allow: true }
    : { allow: false, withheld: 'snapshot-failed' };
}

/** Whether operator-only (undeclared) repair() may run: only with --yes or an answered prompt. */
async function operatorDecision(
  planned: RepoRepairFile[],
  opts: RepoRepairOptions,
  deps: RepoRepairDeps
): Promise<{ allow: boolean; withheld?: string }> {
  const files = planned.filter((f) => f.class === 'operator-only').map((f) => f.file);
  if (files.length === 0) return { allow: false };
  // A dry run shows no prompt, so nothing is withheld for want of an answer.
  if (opts.yes || opts.dryRun) return { allow: true };
  const confirmed = await deps.confirm(files);
  return confirmed ? { allow: true } : { allow: false, withheld: 'not-confirmed' };
}

/**
 * Plan with every class allowed, decide which classes may run (auto-safe always; auto-with-backup after a snapshot;
 * operator-only after the prompt), then run with exactly those.
 */
export async function runRepoRepair(
  opts: RepoRepairOptions,
  inWindow: boolean,
  deps: RepoRepairDeps
): Promise<RepoRepairOutcome> {
  const windowOk = inWindow || opts.windowOverride === true;
  const plan = await deps.repair(
    ['auto-safe', 'auto-with-backup', 'operator-only'],
    windowOk,
    true
  );
  const planned = plan.files.filter((f) => f.result === 'planned');
  const backup = await backupDecision(planned, opts, deps);
  const operator = await operatorDecision(planned, opts, deps);
  const allowClasses = [
    'auto-safe',
    ...(backup.allow ? ['auto-with-backup'] : []),
    ...(operator.allow ? ['operator-only'] : []),
  ];
  const withheld = [backup.withheld, operator.withheld].filter((w): w is string => w !== undefined);
  const report = opts.dryRun ? plan : await deps.repair(allowClasses, windowOk, false);
  return { report, allowClasses, withheld, exitCode: repoRepairExitCode(report) };
}

const WITHHELD_KEY: Readonly<Record<string, string>> = {
  'needs-backup': 'commands.repo.repair.withheldNeedsBackup',
  'snapshot-failed': 'commands.repo.repair.withheldSnapshotFailed',
  'not-confirmed': 'commands.repo.repair.withheldNotConfirmed',
};

/** One Rediaccfile's line of the text report; a file whose health() was fine prints nothing. */
function printFile(f: RepoRepairFile): void {
  if (f.result === 'not-needed') return;
  // The file, class and renet's result word are data.
  const line = `  ${f.file} [${f.class}]: ${f.result}${f.reason ? ` (${f.reason})` : ''}`;
  if (f.result === 'failed') outputService.error(line);
  else outputService.info(line);
  if (f.detail) outputService.info(`    ${f.detail}`);
}

function printOutcome(outcome: RepoRepairOutcome, repository: string, format: OutputFormat): void {
  const { report } = outcome;
  if (format === 'json') {
    outputService.print(
      {
        repository,
        allow_classes: outcome.allowClasses,
        withheld: outcome.withheld,
        before: report.before,
        files: report.files,
        after: report.after ?? null,
        ran: report.ran,
        failed: report.failed,
        exitCode: outcome.exitCode,
      },
      format
    );
    return;
  }
  outputService.info(t('commands.repo.repair.header', { repository }));
  for (const f of report.files) printFile(f);
  for (const w of outcome.withheld)
    outputService.warn(t(WITHHELD_KEY[w] ?? WITHHELD_KEY['not-confirmed']));
  const level = (report.after ?? report.before).level;
  outputService.info(
    t('commands.repo.repair.summary', { ran: report.ran, failed: report.failed, level })
  );
}

/** renet's answer, or the reason it could not be read. */
function readReport(stdout: string | undefined): RepoRepairReport {
  const report = parseCapturedJson<Partial<RepoRepairReport>>(stdout);
  const before: unknown = report.before;
  const hasLevel = typeof before === 'object' && before !== null && 'level' in before;
  if (!Array.isArray(report.files) || !hasLevel)
    throw new Error(t('commands.repo.repair.unreadable'));
  return report as RepoRepairReport;
}

/** The message of a failed renet call: an older renet is named as such. */
function renetFailure(result: ExecuteResult, machine: string): string {
  const text = `${result.stderr ?? ''}\n${result.stdout ?? ''}`;
  if (isRenetFlagUnsupported(text) || /unknown command "repair"/.test(text)) {
    return t('commands.repo.repair.unsupported', { machine });
  }
  return result.error ?? t('commands.repo.repair.renetFailed');
}

/** The machine side of `repo repair` for one repository: every call an attached probe. */
function repoRepairDeps(
  target: { repoKey: string; machineName: string; datastore: string | undefined },
  debug: boolean | undefined
): RepoRepairDeps {
  const call = async (fn: string, params: Record<string, unknown>) => {
    const result = await getExecutor().execute({
      functionName: fn,
      machineName: target.machineName,
      datastore: target.datastore,
      params: { repository: target.repoKey, ...params },
      debug,
      captureOutput: true,
      probe: true,
    });
    if (!result.success) throw new Error(renetFailure(result, target.machineName));
    return result;
  };
  return {
    repair: async (allow, inWindow, dryRun) => {
      const params = { allow_classes: allow.join(','), in_window: inWindow, dry_run: dryRun };
      return readReport((await call('repository_repair', params)).stdout);
    },
    snapshot: async () => {
      try {
        await call('backup_snapshot', {});
        return { ok: true };
      } catch (error) {
        return { ok: false, detail: error instanceof Error ? error.message : String(error) };
      }
    },
    confirm: async (files) =>
      process.stdin.isTTY === true &&
      askConfirm(t('commands.repo.repair.confirmOperatorOnly', { files: files.join(', ') })),
  };
}

/** One `repo repair` run: resolve the repo and its machine's window, run, print, settle the exit code. */
async function repairRepo(
  ref: string,
  options: RepoRepairOptions & { debug?: boolean }
): Promise<void> {
  const { name, repoKey, machineName } = await resolveRepoRef(ref);
  await ensureRepositoryNetworkId(repoKey);
  const datastore = await recordedDatastoreMount(repoKey);
  const config = await configService.getLocalConfig();
  const machine = config.machines[machineName] as { maintenanceWindow?: string } | undefined;
  const inWindow = inMaintenanceWindow(machine?.maintenanceWindow, new Date());
  const deps = repoRepairDeps({ repoKey, machineName, datastore }, options.debug);
  const outcome = await runRepoRepair(options, inWindow, deps);
  printOutcome(outcome, name, getOutputFormat());
  if (outcome.exitCode !== 0) setExitCode(outcome.exitCode);
}

export function registerRepoRepairCommand(repo: Command): void {
  repo
    .command('repair')
    .summary(t('commands.repo.repair.descriptionShort'))
    .description(t('commands.repo.repair.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--dry-run', t('commands.repo.repair.optionDryRun'))
    .option('--with-backup', t('commands.repo.repair.optionWithBackup'))
    .option('--window-override', t('commands.repo.repair.optionWindowOverride'))
    .option('-y, --yes', t('commands.repo.repair.optionYes'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: RepoRepairOptions & { debug?: boolean }) => {
      try {
        await repairRepo(ref, options);
      } catch (error) {
        if (getOutputFormat() === 'json') {
          const message = error instanceof Error ? error.message : String(error);
          outputService.print({ repository: ref, error: message, exitCode: 2 }, 'json');
          setExitCode(2);
          return;
        }
        handleError(error);
      }
    });
}
