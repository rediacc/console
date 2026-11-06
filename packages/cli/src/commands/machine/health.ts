import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import {
  getMachineHealth,
  type MachineHealthResult,
  parseListResult,
} from '@rediacc/shared/services/machine';
import {
  type CertificatesSectionInput,
  type ChallengeSectionInput,
  checkAcmeChallengeCnames,
  checkCertificateExpiry,
} from '@rediacc/shared/services/machine/parsing-health';
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
import { type ExecuteResult, getExecutor } from '../../services/executor/executor-factory.js';
import { isRenetFlagUnsupported } from '../../services/executor/job-client.js';
import { parseCapturedJson } from '../../services/executor/renet-output.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import { machineStatusJob, parseMachineStatus } from '../../services/machine/machine-status.js';
import type { RenetProcess } from '../../services/renet/renet-daemons.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import type { RepoHealthFile, RepoHealthLevel } from '../repo-health.js';
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
  let exitCode = health.exitCode;
  const binaries = extra.staleBinary ?? [];
  if (binaries.length > 0) {
    issues.push(
      `${binaries.length} renet process(es) run a replaced binary: ${binaries.map((p) => `${p.unit} (pid ${p.pid})`).join(', ')}`
    );
    exitCode = Math.max(exitCode, 1);
  }
  const behindSchedule = extra.staleBackups.filter((b) => b.targetSeconds === undefined);
  const behindTarget = extra.staleBackups.filter((b) => b.targetSeconds !== undefined);
  if (behindSchedule.length > 0) {
    issues.push(
      `${behindSchedule.length} repository(ies) last backed up more than twice their schedule interval ago`
    );
    exitCode = Math.max(exitCode, 1);
  }
  if (behindTarget.length > 0) {
    const named = behindTarget
      .map(
        (b) =>
          `${b.name ?? b.guid} (target ${formatSpan(b.targetSeconds ?? 0)}, last captured ${formatSpan(b.ageSeconds)} ago)`
      )
      .join(', ');
    issues.push(`${behindTarget.length} repository(ies) missed their backup target: ${named}`);
    exitCode = Math.max(exitCode, 1);
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
    issues.push(
      `${missed.length} repository(ies) missed their backup target on the latest run: ${named}`
    );
    exitCode = Math.max(exitCode, 1);
  }
  const failedVerifies = extra.failedVerifies ?? [];
  if (failedVerifies.length > 0) {
    const named = failedVerifies.map((f) => `${f.name ?? f.guid} (${f.status})`).join(', ');
    issues.push(
      `${failedVerifies.length} repository(ies) failed their last backup verify: ${named}`
    );
    exitCode = Math.max(exitCode, 1);
  }
  // Raised from 0 only by these checks, so the shared verdict's message moves with it.
  const message = exitCode === health.exitCode ? health.message : 'System has warnings';
  return { ...health, issues, exitCode, healthy: exitCode === 0, message };
}

/** The machine's repos behind their schedule or target, and those whose latest run missed one. */
function backupStanding(
  name: string,
  listResult: ReturnType<typeof parseListResult>
): Promise<[StaleBackupRepo[], MissedTargetRepo[]]> {
  if (!listResult) return Promise.resolve([[], []]);
  return Promise.all([fetchStaleBackups(name, listResult), fetchMissedTargets(name, listResult)]);
}

/** One repository's report in renet's `repository health --all --strict` answer. */
export interface RepoHealthEntry {
  guid: string;
  name?: string;
  network_id?: number;
  state?: string;
  level: RepoHealthLevel;
  detail?: string;
  files?: RepoHealthFile[];
  error?: string;
}

/**
 * The repo-health read folded into `machine health`: `ok` with every mounted repo's report, `unsupported` when the
 * remote renet predates `--all --strict`, `failed` when the read itself failed.
 */
export type RepoHealthFold =
  | { status: 'ok'; repositories: RepoHealthEntry[] }
  | { status: 'unsupported'; repositories: [] }
  | { status: 'failed'; repositories: []; error: string };

/** A coded finding (D-remedy); the fix table that adds `fix` to each code is the remediation layer's. */
export interface HealthFinding {
  code: string;
  severity: 'warning' | 'error';
  subject: string;
  detail: string;
}

export type MachineHealthWithRepos = MachineHealthResult & { findings: HealthFinding[] };

const LEVELS = new Set<string>(['ok', 'warning', 'error', 'none']);

/**
 * An older renet answers `--all` in one of two ways, both before running anything: cobra rejects the flag, or its
 * builder ignores the unknown `all` param and refuses the call for naming no repository.
 */
function isRepoHealthAllUnsupported(output: string): boolean {
  return isRenetFlagUnsupported(output) || /Repository name is required/.test(output);
}

/** Read the `repository_health --all --strict` result. Pure: the caller runs the call. */
export function foldRepoHealthResult(
  result: Pick<ExecuteResult, 'success' | 'error' | 'stdout' | 'stderr'>
): RepoHealthFold {
  const combined = `${result.stderr ?? ''}\n${result.stdout ?? ''}`;
  if (!result.success) {
    if (isRepoHealthAllUnsupported(combined)) return { status: 'unsupported', repositories: [] };
    return {
      status: 'failed',
      repositories: [],
      error: result.error ?? 'repository health read failed',
    };
  }
  let parsed: { repositories?: unknown };
  try {
    parsed = parseCapturedJson<{ repositories?: unknown }>(result.stdout);
  } catch (error) {
    return {
      status: 'failed',
      repositories: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
  // An answer without the list is an older renet's single report: it ran without --all.
  if (!Array.isArray(parsed.repositories)) return { status: 'unsupported', repositories: [] };
  const repositories = (parsed.repositories as RepoHealthEntry[]).map((r) =>
    // A level renet did not send (or one this CLI does not know) is never read as healthy.
    LEVELS.has(r.level) ? r : { ...r, level: 'error' as const }
  );
  return { status: 'ok', repositories };
}

const repoLabel = (r: RepoHealthEntry): string => r.name ?? r.guid;

function repoHealthDetail(r: RepoHealthEntry): string {
  if (r.error) return r.error;
  const files = (r.files ?? []).filter((f) => f.level === 'warning' || f.level === 'error');
  return files.map((f) => `${f.file} exit ${f.exit}${f.detail ? `: ${f.detail}` : ''}`).join('; ');
}

/** The finding of one repo whose health() is not ok; none for ok or "no check". */
function repoFinding(r: RepoHealthEntry): HealthFinding | null {
  if (r.level !== 'warning' && r.level !== 'error') return null;
  return {
    code: r.level === 'warning' ? 'repo.health.warning' : 'repo.health.error',
    severity: r.level,
    subject: repoLabel(r),
    detail: repoHealthDetail(r),
  };
}

/** The findings a repo-health read raises: one per repo not ok, or one for an older renet or a failed read. */
export function repoHealthFindings(fold: RepoHealthFold, machineName: string): HealthFinding[] {
  if (fold.status === 'unsupported') {
    return [
      {
        code: 'renet.repo-health.unsupported',
        severity: 'warning',
        subject: machineName,
        detail: `renet on ${machineName} predates repository health checks; update it with rdc machine setup ${machineName}`,
      },
    ];
  }
  if (fold.status === 'failed') {
    return [
      {
        code: 'repo.health.failed',
        severity: 'error',
        subject: machineName,
        detail: `repository health checks could not run: ${fold.error}`,
      },
    ];
  }
  return fold.repositories.map(repoFinding).filter((f): f is HealthFinding => f !== null);
}

function findingIssue(f: HealthFinding): string {
  if (f.code === 'repo.health.warning' || f.code === 'repo.health.error') {
    return `Repository ${f.subject} health ${f.severity}${f.detail ? `: ${f.detail}` : ''}`;
  }
  return f.detail;
}

/**
 * Fold every repo's health() into the machine verdict (D-repohealth): a warning raises the exit code to 1, an error
 * to 2, each with one finding. A repo with no check adds nothing. An older renet is one warning
 * (`renet.repo-health.unsupported`), so the verdict is never green by error, and a failed read is exit 2.
 */
export function applyRepoHealth(
  health: MachineHealthResult,
  fold: RepoHealthFold,
  machineName: string
): MachineHealthWithRepos {
  const findings = repoHealthFindings(fold, machineName);
  const issues = [...health.issues, ...findings.map(findingIssue)];
  const exitCode = Math.max(
    health.exitCode,
    ...findings.map((f) => (f.severity === 'error' ? 2 : 1))
  );
  if (exitCode === health.exitCode) return { ...health, issues, findings };
  const message = exitCode >= 2 ? 'System has errors' : 'System has warnings';
  return { ...health, issues, findings, exitCode, healthy: false, message };
}

/** The listing's certificates section, read by both the expiry check (G5) and the shared-CNAME detector (G6). */
export type CertificatesListing = CertificatesSectionInput & ChallengeSectionInput;

/**
 * Fold the certificate dimension (D-certs) into the verdict: each `cert.expiry.near` finding names its certificate and
 * raises the exit code to 1 (under 21 days) or 2 (under 7), and each `acme.challenge.cname-shared` finding (G6) is a
 * warning naming the chain end and the names landing there. The section comes from the listing; a machine without the
 * proxy has none and raises nothing.
 */
export function applyCertificates(
  health: MachineHealthWithRepos,
  section: CertificatesListing | null | undefined,
  now: Date = new Date()
): MachineHealthWithRepos {
  const certFindings: HealthFinding[] = [
    ...checkCertificateExpiry(section, now),
    ...checkAcmeChallengeCnames(section),
  ].map((f) => ({
    code: f.code,
    severity: f.severity,
    subject: f.subject,
    detail: f.detail,
  }));
  if (certFindings.length === 0) return health;
  const exitCode = Math.max(
    health.exitCode,
    ...certFindings.map((f) => (f.severity === 'error' ? 2 : 1))
  );
  const findings = [...health.findings, ...certFindings];
  const issues = [...health.issues, ...certFindings.map((f) => f.detail)];
  if (exitCode === health.exitCode) return { ...health, issues, findings };
  const message = exitCode >= 2 ? 'System has errors' : 'System has warnings';
  return { ...health, issues, findings, exitCode, healthy: false, message };
}

/** The listing's certificates section; the generated ListResult type gains it with the next contract regeneration. */
function certificatesOf(listResult: unknown): CertificatesListing | undefined {
  if (!listResult || typeof listResult !== 'object') return undefined;
  const section = (listResult as { certificates?: unknown }).certificates;
  return section && typeof section === 'object' ? (section as CertificatesListing) : undefined;
}

/** Run `repository_health --all --strict` on the machine and fold its answer. */
export async function fetchRepoHealth(machineName: string): Promise<RepoHealthFold> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName] as { datastore?: string } | undefined;
  try {
    const result = await getExecutor().execute({
      functionName: 'repository_health',
      machineName,
      datastore: machine?.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
      params: { all: true, strict: true },
      captureOutput: true,
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
async function renderHealthFromJob(
  name: string,
  output: string | undefined,
  format: OutputFormat
): Promise<void> {
  const vaultStatus = JSON.stringify(parseMachineStatus(output));
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
