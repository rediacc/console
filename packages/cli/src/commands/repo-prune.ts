import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createRepoNameResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { askConfirm } from '../utils/prompt.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoTarget } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

/** One class of the renet `repository_docker_prune` record (Go json tags). */
interface PruneClass {
  count: number;
  bytes: number;
  paths?: string[] | null;
}

/** Mirror of renet's `dockerPruneRecord`; only the fields the table reads. */
interface PruneRecord {
  guid?: string;
  mode?: string;
  classes?: Record<string, PruneClass> | null;
  estimate?: number;
  estimate_online?: number;
  unsafe?: boolean;
  downtime_seconds?: number;
  trimmed_bytes?: number;
  datastore_trimmed_bytes?: number;
  trim_skipped?: string;
  refused?: string;
  errors?: string[] | null;
}

interface PruneOptions {
  /** Machine-wide survey form: the machine whose mounted repositories to survey. */
  machine?: string;
  apply?: boolean;
  offline?: boolean;
  allImages?: boolean;
  trim?: boolean;
  yes?: boolean;
  debug?: boolean;
}

/** Report order of the record's classes (renet `dockerPruneClassOrder`). */
const CLASS_ORDER = ['A', 'B', 'C', 'D', 'G', 'E', 'F1', 'F2', 'L', 'Q'] as const;

function formatBytes(bytes: number | undefined): string {
  const b = bytes ?? 0;
  const tb = 1024 ** 4;
  const gb = 1024 ** 3;
  const mb = 1024 ** 2;
  if (b >= tb) return `${(b / tb).toFixed(1)} TB`;
  if (b >= gb) return `${(b / gb).toFixed(1)} GB`;
  if (b >= mb) return `${(b / mb).toFixed(1)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${b} B`;
}

/** Every refusal that needs no config or machine, raised before anything runs. */
function validateFlags(ref: string | undefined, options: PruneOptions): void {
  if (options.offline && !options.apply) {
    throw new ValidationError(t('commands.repo.prune.offlineNeedsApply'));
  }
  if (!ref && options.apply) {
    throw new ValidationError(t('commands.repo.prune.applyNeedsRef'));
  }
  if (ref && options.machine) {
    throw new ValidationError(t('commands.repo.refMachineConflict', { verb: 'prune' }));
  }
  if (options.offline && !assumeYes(options) && isAgentEnvironment()) {
    throw new ValidationError(t('commands.repo.prune.offlineNeedsYes'));
  }
}

/**
 * The root program owns `-y, --yes` and consumes it wherever it appears on the
 * line, so this command's own option never fires; the root flag arrives as
 * REDIACC_YES=1 (cli.ts preAction).
 */
function assumeYes(options: PruneOptions): boolean {
  return options.yes === true || process.env.REDIACC_YES === '1';
}

function buildParams(guid: string, options: PruneOptions): Record<string, unknown> {
  const params: Record<string, unknown> = { name: guid };
  if (options.apply) params.apply = true;
  if (options.offline) params.offline = true;
  if (options.allImages) params.all_images = true;
  if (options.trim === false) params.no_trim = true;
  return params;
}

/** The lines under the table that report a refusal, an unsafe scan and the record's own errors. */
function renderProblems(record: PruneRecord): void {
  if (record.refused) {
    outputService.error(t('commands.repo.prune.refused', { reason: record.refused }));
  }
  if (record.unsafe) {
    outputService.warn(t('commands.repo.prune.unsafe'));
  }
  for (const error of record.errors ?? []) outputService.warn(error);
}

/** The footer of an applied run: what went back to the pool and how long the daemon was down. */
function renderApplied(record: PruneRecord): void {
  outputService.success(
    t('commands.repo.prune.completed', {
      trimmed: formatBytes((record.trimmed_bytes ?? 0) + (record.datastore_trimmed_bytes ?? 0)),
      downtime: Math.round(record.downtime_seconds ?? 0),
    })
  );
  if (record.trim_skipped) {
    outputService.info(t('commands.repo.prune.trimSkipped', { reason: record.trim_skipped }));
  }
}

function renderRecord(label: string, record: PruneRecord): void {
  const classes = record.classes ?? {};
  const rows = CLASS_ORDER.map((key) => ({
    class: key,
    description: t(`commands.repo.prune.class.${key}`),
    count: classes[key]?.count ?? 0,
    bytes: formatBytes(classes[key]?.bytes),
  }));
  outputService.info(label);
  outputService.print(rows, 'table');
  renderProblems(record);

  if (record.mode === 'online' || record.mode === 'offline') {
    renderApplied(record);
    return;
  }
  outputService.info(
    t('commands.repo.prune.estimate', {
      offline: formatBytes(record.estimate),
      online: formatBytes(record.estimate_online),
    })
  );
}

function renderRecords(entries: { label: string; record: PruneRecord }[], survey: boolean): void {
  // A refused scan is a failed run: a script reads it from the exit code, whatever the output format.
  if (entries.some((e) => e.record.refused)) setExitCode(1);
  const format = getOutputFormat();
  if (format !== 'table') {
    // The record passes through unchanged: one object for a ref, an array for the machine-wide survey.
    const records = entries.map((e) => e.record);
    outputService.print(survey ? records : records[0], format);
    return;
  }
  for (const entry of entries) renderRecord(entry.label, entry.record);
}

function confirmOffline(label: string, options: PruneOptions): Promise<boolean> {
  if (!options.offline || assumeYes(options)) return Promise.resolve(true);
  outputService.warn(t('commands.repo.prune.downtimeNotice', { repository: label }));
  return askConfirm(t('commands.repo.prune.confirm', { repository: label }));
}

async function pruneOne(
  machineName: string,
  kubeCluster: string | undefined,
  datastore: string | undefined,
  guid: string,
  options: PruneOptions
): Promise<PruneRecord | undefined> {
  const result = await getExecutor().execute({
    functionName: 'repository_docker_prune',
    machineName,
    ...(kubeCluster !== undefined && { kubeCluster }),
    datastore,
    params: buildParams(guid, options),
    debug: options.debug,
    captureOutput: true,
  });
  if (!result.success) {
    renderLocalExecutionFailure(result, t('commands.repo.prune.failed'));
    return undefined;
  }
  return parseDatastorePruneOutput(result.stdout ?? '') as PruneRecord;
}

async function handleRefPrune(ref: string, options: PruneOptions): Promise<void> {
  // Gate A read-only resolution: the prune run is itself the verification.
  const resolved = await resolveRepoRef(ref, { readOnly: true });
  await assertCommandPolicy(CMD.REPO_PRUNE, resolved.repoKey);
  const repo = await configService.getRepository(resolved.repoKey);
  if (!repo) {
    throw new Error(t('commands.repo.prune.repoNotFound', { name: resolved.name }));
  }
  await assertMachineExists(resolved.machineName);

  if (!(await confirmOffline(resolved.repoKey, options))) {
    outputService.info(t('commands.repo.prune.cancelled'));
    return;
  }

  outputService.info(
    t('commands.repo.prune.starting', {
      repository: resolved.repoKey,
      machine: resolved.machineName,
    })
  );
  const record = await pruneOne(
    resolved.machineName,
    resolved.kubeCluster,
    await recordedDatastoreMount(resolved.repoKey),
    repo.repositoryGuid,
    options
  );
  if (record) renderRecords([{ label: resolved.repoKey, record }], false);
}

/** Machine-wide dry-run survey: list the machine's repositories, then report each mounted one. */
async function handleMachineSurvey(options: PruneOptions): Promise<void> {
  const target = await resolveRepoTarget({ machine: options.machine });
  await assertMachineExists(target.machineName);
  outputService.info(t('commands.repo.prune.surveying', { machine: target.machineName }));

  const listed = await getExecutor().execute({
    functionName: 'repository_list',
    machineName: target.machineName,
    ...(target.kubeCluster !== undefined && { kubeCluster: target.kubeCluster }),
    params: {},
    debug: options.debug,
    captureOutput: true,
  });
  if (!listed.success) {
    renderLocalExecutionFailure(listed, t('commands.repo.prune.failed'));
    return;
  }
  const mounted = parseRepositoryListOutput(listed.stdout ?? '[]').filter((r) => r.mounted);
  if (mounted.length === 0) {
    outputService.info(t('commands.repo.prune.noMountedRepos'));
    return;
  }

  const resolveName = createRepoNameResolver(await loadGuidMap());
  const entries: { label: string; record: PruneRecord }[] = [];
  for (const entry of mounted) {
    const guid = String(entry.name);
    const label = `${resolveName(guid, entry.repo_name as string | undefined).name} (${guid})`;
    const record = await pruneOne(target.machineName, target.kubeCluster, undefined, guid, options);
    if (record) entries.push({ label, record });
  }
  renderRecords(entries, true);
}

async function handlePruneAction(ref: string | undefined, options: PruneOptions): Promise<void> {
  validateFlags(ref, options);
  if (ref) {
    await handleRefPrune(ref, options);
  } else {
    await handleMachineSurvey(options);
  }
}

/** Register `repo prune`, Docker storage classification and reclaim (PLAN-repo-docker-storage-prune). */
export function registerRepoPruneCommand(repo: Command): void {
  repo
    .command('prune')
    .summary(t('commands.repo.prune.descriptionShort'))
    .description(t('commands.repo.prune.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('--apply', t('commands.repo.prune.applyOption'))
    .option('--offline', t('commands.repo.prune.offlineOption'))
    .option('--all-images', t('commands.repo.prune.allImagesOption'))
    .option('--no-trim', t('commands.repo.prune.noTrimOption'))
    .option('-y, --yes', t('options.yes'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string | undefined, options: PruneOptions) => {
      try {
        await handlePruneAction(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}
