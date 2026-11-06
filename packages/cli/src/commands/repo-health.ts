import { type HealthFinding, withFix } from '@rediacc/shared/services/machine/findings';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { ensureRepositoryNetworkId } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import type { ExecuteResult } from '../services/executor/executor-factory.js';
import { isRenetFlagUnsupported } from '../services/executor/job-client.js';
import { parseCapturedJson } from '../services/executor/renet-output.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import type { OutputFormat } from '../types/index.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';

/** A Rediaccfile health() verdict: 0 ok, 1 warning, 2 error; `none` is "no check" (no health() defined). */
export type RepoHealthLevel = 'ok' | 'warning' | 'error' | 'none';

/** One Rediaccfile's health() result, as renet reports it. */
export interface RepoHealthFile {
  file: string;
  exit: number;
  level: RepoHealthLevel;
  detail?: string;
}

/** renet's HealthReport: `state` is the deploy gate's verdict, `level` and `files` the monitoring view (renet --strict). */
export interface RepoHealthReport {
  state: string;
  detail?: string;
  level?: RepoHealthLevel;
  files?: RepoHealthFile[];
}

/** The exit code of each level, the convention of `rdc machine health`. "No check" is not a failure, and not healthy either. */
export const REPO_HEALTH_LEVEL_EXIT: Readonly<Record<RepoHealthLevel, number>> = {
  ok: 0,
  none: 0,
  warning: 1,
  error: 2,
};

/** A renet failure, an unreadable answer or a renet that predates the monitoring view: always an error. */
export const REPO_HEALTH_FAILURE_EXIT = 2;

const LEVELS = new Set<string>(Object.keys(REPO_HEALTH_LEVEL_EXIT));

/** The report's level, or undefined when renet answered without one (a renet older than `--strict`). */
export function reportLevel(report: RepoHealthReport): RepoHealthLevel | undefined {
  return typeof report.level === 'string' && LEVELS.has(report.level) ? report.level : undefined;
}

const LEVEL_LINE: Record<RepoHealthLevel, { key: string; print: (msg: string) => void }> = {
  ok: { key: 'commands.repo.health.levelOk', print: (m) => outputService.success(m) },
  warning: { key: 'commands.repo.health.levelWarning', print: (m) => outputService.warn(m) },
  error: { key: 'commands.repo.health.levelError', print: (m) => outputService.error(m) },
  none: { key: 'commands.repo.health.levelNone', print: (m) => outputService.info(m) },
};

/** A file without health() prints no line, so `none` has no file label. */
const FILE_LEVEL_KEY: Record<Exclude<RepoHealthLevel, 'none'>, string> = {
  ok: 'commands.repo.health.fileLevelOk',
  warning: 'commands.repo.health.fileLevelWarning',
  error: 'commands.repo.health.fileLevelError',
};

/** The coded finding of a repo's health() verdict (D-remedy): one for a warning or an error, none otherwise. */
export function repoHealthReportFindings(
  report: RepoHealthReport & { level: RepoHealthLevel },
  repository: string
): HealthFinding[] {
  if (report.level !== 'warning' && report.level !== 'error') return [];
  const detail = (report.files ?? [])
    .filter((f) => f.level === 'warning' || f.level === 'error')
    .map((f) => `${f.file} exit ${f.exit}${f.detail ? `: ${f.detail}` : ''}`)
    .join('; ');
  return [
    withFix({
      code: report.level === 'warning' ? 'repo.health.warning' : 'repo.health.error',
      severity: report.level,
      subject: repository,
      detail: detail || (report.detail ?? ''),
    }),
  ];
}

/** Print a completed report and answer its exit code. */
export function renderRepoHealthReport(
  report: RepoHealthReport & { level: RepoHealthLevel },
  repository: string,
  format: OutputFormat
): number {
  const exitCode = REPO_HEALTH_LEVEL_EXIT[report.level];
  const files = report.files ?? [];
  if (format === 'json') {
    outputService.print(
      {
        repository,
        level: report.level,
        state: report.state,
        detail: report.detail ?? null,
        files,
        findings: repoHealthReportFindings(report, repository),
        exitCode,
      },
      format
    );
    return exitCode;
  }
  outputService.info(t('commands.repo.health.header', { repository }));
  const line = LEVEL_LINE[report.level];
  line.print(t(line.key));
  for (const f of files) {
    if (f.level === 'none') continue;
    outputService.info(
      t('commands.repo.health.fileLine', {
        file: f.file,
        level: t(FILE_LEVEL_KEY[f.level]),
        exit: f.exit,
      })
    );
    // The detail is renet's own text (the function's error), printed as data under its file.
    if (f.detail) outputService.info(`    ${f.detail}`);
  }
  return exitCode;
}

/** Print a failure (renet failed, its answer was unreadable, or it predates `--strict`) and answer exit 2. */
export function renderRepoHealthFailure(
  message: string,
  repository: string,
  format: OutputFormat
): number {
  if (format === 'json') {
    outputService.print(
      {
        repository,
        level: 'error',
        state: null,
        detail: message,
        files: [],
        findings: [
          withFix({
            code: 'repo.health.failed',
            severity: 'error',
            subject: repository,
            detail: message,
          }),
        ],
        exitCode: REPO_HEALTH_FAILURE_EXIT,
      },
      format
    );
  } else {
    outputService.error(t('commands.repo.health.failed', { repository, message }));
  }
  return REPO_HEALTH_FAILURE_EXIT;
}

/** Read a finished job's output into a verdict and print it; answers the exit code. */
export function handleRepoHealthOutput(
  output: string | undefined,
  repository: string,
  machine: string,
  format: OutputFormat
): number {
  let report: RepoHealthReport;
  try {
    report = parseCapturedJson<RepoHealthReport>(output);
  } catch (error) {
    return renderRepoHealthFailure(
      error instanceof Error ? error.message : String(error),
      repository,
      format
    );
  }
  const level = reportLevel(report);
  if (level === undefined) {
    return renderRepoHealthFailure(
      t('commands.repo.health.unsupported', { machine }),
      repository,
      format
    );
  }
  return renderRepoHealthReport({ ...report, level }, repository, format);
}

/** A failed job: an older renet rejecting `--strict` is named as such; anything else is renet's own error. Exit 2 either way. */
export function handleRepoHealthJobFailure(
  result: Pick<ExecuteResult, 'error' | 'stderr' | 'stdout'>,
  repository: string,
  machine: string,
  format: OutputFormat
): number {
  const combined = `${result.stderr ?? ''}\n${result.stdout ?? ''}`;
  const message = isRenetFlagUnsupported(combined)
    ? t('commands.repo.health.unsupported', { machine })
    : (result.error ?? t('commands.repo.health.renetFailed'));
  return renderRepoHealthFailure(message, repository, format);
}

// The `printRepoHealth` step renders the verdict once the job's output is seen, so a ticket handed back early prints nothing.
bindStepHandler('printRepoHealth', ({ output, params, machine }) => {
  const name = typeof params.name === 'string' ? params.name : '';
  setExitCode(handleRepoHealthOutput(output, name, machine, getOutputFormat()));
  return Promise.resolve();
});

/**
 * `rdc repo health <ref>`: run the repo's Rediaccfile health() functions (renet `repository health --strict`) and
 * exit 0 ok, 1 warning, 2 error. A repo with no health() is "no check" (exit 0, never reported healthy).
 */
export function registerRepoHealthCommand(repo: Command): void {
  repo
    .command('health')
    .description(t('commands.repo.health.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (ref: string, options: { debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref, {
          readOnly: true,
        });
        await ensureRepositoryNetworkId(repoKey);
        const outcome = await runCommandJob(
          'repo health',
          {
            functionName: 'repository_health',
            machineName,
            kubeCluster,
            datastore: await recordedDatastoreMount(repoKey),
            params: { repository: repoKey, strict: true },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
            captureOutput: true,
          },
          [planStep('printRepoHealth', { name })]
        );
        if (outcome.kind === 'pending') {
          const code = pendingExitCode(outcome);
          if (code !== undefined) setExitCode(code);
          return;
        }
        if (!outcome.result.success) {
          setExitCode(
            handleRepoHealthJobFailure(outcome.result, name, machineName, getOutputFormat())
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}
