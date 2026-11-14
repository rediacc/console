import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import {
  getMachineHealth,
  type MachineHealthResult,
  parseListResult,
} from '@rediacc/shared/services/machine';
import { withFix } from '@rediacc/shared/services/machine/findings';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import type {
  FailedVerifyRepo,
  MissedTargetRepo,
  StaleBackupRepo,
} from '../../services/backup/backup-schedule-coverage.js';
import { failedVerifyRepos, formatSpan } from '../../services/backup/backup-schedule-coverage.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { getExecutor } from '../../services/executor/executor-factory.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import { machineStatusJob, parseMachineStatus } from '../../services/machine/machine-status.js';
import type { RenetProcess } from '../../services/renet/renet-daemons.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import type { RepoHealthLevel } from '../repo-health.js';
import {
  applyCertificates,
  applyRepoHealth,
  certificatesOf,
  foldRepoHealthResult,
  type RepoHealthFold,
  repoLabel,
} from './health-folds.js';
import { fetchMissedTargets, fetchStaleBackups, staleBinariesOf } from './status.js';

const exitCodeStatusHandlers: Record<number, () => void> = {
  0: () => outputService.success(t('commands.machine.health.statusHealthy')),
  1: () => outputService.warn(t('commands.machine.health.statusWarning')),
  2: () => outputService.error(t('commands.machine.health.statusError')),
};

function displayStatusByExitCode(exitCode: number): void {
  const handler = exitCodeStatusHandlers[exitCode] as (() => void) | undefined;
  if (handler === undefined) {
    outputService.error(t('commands.machine.health.statusCritical'));
  } else {
    handler();
  }
}

function displaySystemSection(sys: MachineHealthResult['details']['system']): void {
  const hasData = sys.uptime ?? sys.memoryPercent ?? sys.diskPercent ?? sys.datastorePercent;
  if (!hasData) return;

  outputService.info(t('commands.machine.health.systemSection'));

  const systemFields: { value: unknown; key: string; param: string }[] = [
    { value: sys.uptime, key: 'systemUptime', param: 'uptime' },
    { value: sys.memoryPercent, key: 'systemMemory', param: 'percent' },
    { value: sys.diskPercent, key: 'systemDisk', param: 'percent' },
    { value: sys.datastorePercent, key: 'systemDatastore', param: 'percent' },
  ];

  for (const field of systemFields) {
    if (field.value) {
      outputService.info(t(`commands.machine.health.${field.key}`, { [field.param]: field.value }));
    }
  }
}

function displayContainersSection(cont: MachineHealthResult['details']['containers']): void {
  if (cont.total === 0) return;

  outputService.info(t('commands.machine.health.containersSection'));
  outputService.info(
    t('commands.machine.health.containersSummary', {
      running: cont.running,
      total: cont.total,
      healthy: cont.healthy,
      unhealthy: cont.unhealthy,
    })
  );
}

function displayServicesSection(svc: MachineHealthResult['details']['services']): void {
  if (svc.total === 0) return;

  outputService.info(t('commands.machine.health.servicesSection'));
  outputService.info(
    t('commands.machine.health.servicesSummary', {
      active: svc.active,
      total: svc.total,
      failed: svc.failed,
    })
  );
}

function displayStorageSection(stor: MachineHealthResult['details']['storage']): void {
  if (stor.smartHealthy === 0 && stor.smartFailing === 0) return;

  outputService.info(t('commands.machine.health.storageSection'));
  outputService.info(
    t('commands.machine.health.storageSmart', {
      healthy: stor.smartHealthy,
      failing: stor.smartFailing,
    })
  );
  if (stor.maxTemperature !== null) {
    outputService.info(t('commands.machine.health.storageTemp', { temp: stor.maxTemperature }));
  }
}

function displayRepositoriesSection(
  repositoryStats: MachineHealthResult['details']['repositories']
): void {
  if (repositoryStats.total === 0) return;

  outputService.info(t('commands.machine.health.repositoriesSection'));
  outputService.info(
    t('commands.machine.health.repositoriesSummary', {
      mounted: repositoryStats.mounted,
      total: repositoryStats.total,
      docker: repositoryStats.dockerRunning,
    })
  );
}

function displayLicensesSection(lic: MachineHealthResult['details']['licenses']): void {
  if (lic.total === 0) return;

  outputService.info(t('commands.machine.health.licensesSection'));
  outputService.info(
    t('commands.machine.health.licensesSummary', {
      valid: lic.valid,
      total: lic.total,
      expired: lic.expired,
      mismatch: lic.machineMismatch,
      missing: lic.missing,
    })
  );
}

function displayIssuesSection(issues: string[]): void {
  if (issues.length === 0) return;

  outputService.info(t('commands.machine.health.issuesSection'));
  for (const issue of issues) {
    outputService.warn(`  - ${issue}`);
  }
}

function displayHealthReport(
  health: MachineHealthResult,
  name: string,
  repoHealth?: RepoHealthFold
): void {
  outputService.info(t('commands.machine.health.header', { name }));
  displayStatusByExitCode(health.exitCode);
  displaySystemSection(health.details.system);
  displayContainersSection(health.details.containers);
  displayServicesSection(health.details.services);
  displayStorageSection(health.details.storage);
  displayRepositoriesSection(health.details.repositories);
  if (repoHealth) displayRepoHealthSection(repoHealth);
  displayLicensesSection(health.details.licenses);
  displayIssuesSection(health.issues);
  outputService.info(t('commands.machine.health.exitCode', { code: health.exitCode }));
}

/** What the CLI adds to the vault-status health verdict: stale binaries (C4) and stale backups (G7). */
export interface HealthStaleness {
  staleBinary: RenetProcess[] | null;
  staleBackups: StaleBackupRepo[];
  /** Repos whose latest run missed their declared target (D-rpo). */
  missedTargets?: MissedTargetRepo[];
  /** Repos whose last `backup verify` mismatched or failed (backup_coverage). */
  failedVerifies?: FailedVerifyRepo[];
}

/**
 * Fold the staleness findings into a health result. Either kind is a warning (exit code at least 1):
 * a daemon on a deleted binary runs code the machine no longer has, and a repo two schedule intervals
 * behind is a backup that silently stopped.
 */
export function applyStaleness(
  health: MachineHealthResult,
  extra: HealthStaleness
): MachineHealthResult {
  const issues = [...health.issues];
  const findings = [...health.findings];
  let exitCode = health.exitCode;
  const warn = (text: string, code: string, subject: string): void => {
    issues.push(text);
    findings.push(withFix({ code, severity: 'warning', subject, detail: text }));
    exitCode = Math.max(exitCode, 1);
  };
  const binaries = extra.staleBinary ?? [];
  if (binaries.length > 0) {
    warn(
      `${binaries.length} renet process(es) run a replaced binary: ${binaries.map((p) => `${p.unit} (pid ${p.pid})`).join(', ')}`,
      'renet.binary.replaced',
      // One unit runs several renet processes (dockerd's supervisor and its children), so the subject names each unit once.
      [...new Set(binaries.map((p) => p.unit))].join(', ')
    );
  }
  const behindSchedule = extra.staleBackups.filter((b) => b.targetSeconds === undefined);
  const behindTarget = extra.staleBackups.filter((b) => b.targetSeconds !== undefined);
  if (behindSchedule.length > 0) {
    warn(
      `${behindSchedule.length} repository(ies) last backed up more than twice their schedule interval ago`,
      'backup.schedule.behind',
      behindSchedule.map((b) => b.name ?? b.guid).join(', ')
    );
  }
  if (behindTarget.length > 0) {
    const named = behindTarget
      .map(
        (b) =>
          `${b.name ?? b.guid} (target ${formatSpan(b.targetSeconds ?? 0)}, last captured ${formatSpan(b.ageSeconds)} ago)`
      )
      .join(', ');
    warn(
      `${behindTarget.length} repository(ies) missed their backup target: ${named}`,
      'backup.target.missed',
      behindTarget.map((b) => b.name ?? b.guid).join(', ')
    );
  }
  // A repo already reported as behind its target is not named a second time.
  const reported = new Set(extra.staleBackups.map((b) => b.guid));
  const missed = (extra.missedTargets ?? []).filter((m) => !reported.has(m.guid));
  if (missed.length > 0) {
    const named = missed
      .map((m) => {
        const achieved =
          m.achievedRpoMs === undefined ? '' : `, achieved ${formatSpan(m.achievedRpoMs / 1000)}`;
        return `${m.name ?? m.guid} (target ${formatSpan(m.targetSeconds)}${achieved})`;
      })
      .join(', ');
    warn(
      `${missed.length} repository(ies) missed their backup target on the latest run: ${named}`,
      'backup.target.missed-latest',
      missed.map((m) => m.name ?? m.guid).join(', ')
    );
  }
  const failedVerifies = extra.failedVerifies ?? [];
  if (failedVerifies.length > 0) {
    const named = failedVerifies.map((f) => `${f.name ?? f.guid} (${f.status})`).join(', ');
    warn(
      `${failedVerifies.length} repository(ies) failed their last backup verify: ${named}`,
      'backup.verify.failed',
      failedVerifies.map((f) => f.name ?? f.guid).join(', ')
    );
  }
  // Raised from 0 only by these checks, so the shared verdict's message moves with it.
  const message = exitCode === health.exitCode ? health.message : 'System has warnings';
  return { ...health, issues, findings, exitCode, healthy: exitCode === 0, message };
}

/** The machine's repos behind their schedule or target, and those whose latest run missed one. */
function backupStanding(
  name: string,
  listResult: ReturnType<typeof parseListResult>
): Promise<[StaleBackupRepo[], MissedTargetRepo[]]> {
  if (!listResult) return Promise.resolve([[], []]);
  return Promise.all([fetchStaleBackups(name, listResult), fetchMissedTargets(name, listResult)]);
}

/** Run `repository_health --all --strict` on the machine and fold its answer. */
export async function fetchRepoHealth(machineName: string): Promise<RepoHealthFold> {
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName] as { datastore?: string } | undefined;
    const result = await getExecutor().execute({
      functionName: 'repository_health',
      machineName,
      datastore: machine?.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
      params: { all: true, strict: true },
      captureOutput: true,
      // The verdict reads this answer now: `--background` must not hand back a ticket in its place.
      probe: true,
    });
    return foldRepoHealthResult(result);
  } catch (error) {
    return {
      status: 'failed',
      repositories: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function displayRepoHealthSection(fold: RepoHealthFold): void {
  if (fold.status !== 'ok' || fold.repositories.length === 0) return;
  outputService.info(t('commands.machine.health.repoHealthSection'));
  const unchecked: string[] = [];
  for (const r of fold.repositories) {
    if (r.level === 'none') {
      unchecked.push(repoLabel(r));
      continue;
    }
    // The repo name is data; only the level is copy.
    outputService.info(`  ${repoLabel(r)}: ${t(REPO_LEVEL_KEY[r.level])}`);
  }
  if (unchecked.length > 0) {
    outputService.info(
      t('commands.machine.health.repoHealthNoCheck', { repositories: unchecked.join(', ') })
    );
  }
}

const REPO_LEVEL_KEY: Record<Exclude<RepoHealthLevel, 'none'>, string> = {
  ok: 'commands.repo.health.fileLevelOk',
  warning: 'commands.repo.health.fileLevelWarning',
  error: 'commands.repo.health.fileLevelError',
};

/** The `renderMachineHealth` step: the verdict for the listing the `list-all` job produced, plus every repo's health(). */
/** The full machine verdict for one listing: the shared parser, then staleness, every repo's health() and the certificates. */
export async function composeMachineHealth(name: string, listing: unknown) {
  const vaultStatus = JSON.stringify(listing);
  const machine = { machineName: name, vaultStatus };
  const listResult = parseListResult(vaultStatus);
  // The listing the job returned already holds the stale-process section.
  const staleBinary = listResult ? staleBinariesOf(listResult) : null;
  const [staleBackups, missedTargets] = await backupStanding(name, listResult);
  const failedVerifies = failedVerifyRepos(listResult?.backup_coverage);
  const repoHealth = await fetchRepoHealth(name);
  const health = applyCertificates(
    applyRepoHealth(
      applyStaleness(getMachineHealth(machine), {
        staleBinary,
        staleBackups,
        missedTargets,
        failedVerifies,
      }),
      repoHealth,
      name
    ),
    certificatesOf(listResult)
  );
  return { health, staleBinary, staleBackups, missedTargets, failedVerifies, repoHealth };
}

async function renderHealthFromJob(
  name: string,
  output: string | undefined,
  format: OutputFormat
): Promise<void> {
  const { health, staleBinary, staleBackups, missedTargets, failedVerifies, repoHealth } =
    await composeMachineHealth(name, parseMachineStatus(output));

  if (format === 'json') {
    outputService.print(
      {
        ...health,
        stale_binary: staleBinary,
        backup_staleness: staleBackups,
        target_misses: missedTargets,
        verify_failures: failedVerifies,
        repo_health: repoHealth.repositories,
        repo_health_status: repoHealth.status,
      },
      format
    );
  } else {
    displayHealthReport(health, name, repoHealth);
  }

  if (health.exitCode !== 0) {
    setExitCode(health.exitCode);
  }
}

bindStepHandler('renderMachineHealth', async ({ machine, output }) => {
  // The spinner of the attached call ends before the verdict prints; in a ticket's later run there is none.
  stopSpinner(true);
  await renderHealthFromJob(machine, output, getOutputFormat());
});

/** `machine health`: one read job; the verdict is its step, so a ticket handed back early prints nothing half-done. */
async function runHealthJob(name: string): Promise<void> {
  if (!(await configService.getLocalConfig()).machines[name]) {
    throw new ValidationError(t('errors.machineNotFound', { name }));
  }
  // The job captures its output, so nothing else shows while the machine lists itself.
  startSpinner(t('commands.machine.health.fetching'));
  let outcome: Awaited<ReturnType<typeof runCommandJob>>;
  try {
    outcome = await runCommandJob('machine health', await machineStatusJob(name), [
      planStep('renderMachineHealth'),
    ]);
  } catch (error) {
    stopSpinner(false);
    throw error;
  }
  stopSpinner(outcome.kind !== 'pending' && outcome.result.success);
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, t('commands.machine.health.fetching'));
  }
}

export function registerHealthCommand(machine: Command): void {
  machine
    .command('health')
    .description(t('commands.machine.health.description'))
    .argument('<name>', t('options.name'))
    .action(async (name: string) => {
      try {
        await runHealthJob(name);
      } catch (error) {
        handleError(error);
      }
    });
}
