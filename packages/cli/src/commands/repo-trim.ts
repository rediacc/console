import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoTarget } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';

/** Mirror of renet `trim.RepoResult` (Go json tags). */
interface TrimRepoResult {
  guid: string;
  name?: string;
  discards_active?: boolean;
  refreshed?: boolean;
  needs_remount?: boolean;
  estimated_reclaimable_bytes?: number;
  docker_reclaimed_bytes?: number;
  trimmed_bytes?: number;
  skipped?: string;
  error?: string;
}

interface TrimResult {
  repos?: TrimRepoResult[] | null;
  datastore_trimmed_bytes?: number;
  total_trimmed_bytes?: number;
  report_only?: boolean;
}

interface TrimOptions {
  /** Machine-wide form: the machine whose mounted repositories to trim. */
  machine?: string;
  docker?: boolean;
  dockerVolumes?: boolean;
  reportOnly?: boolean;
  debug?: boolean;
}

function formatTrimBytes(bytes: number | undefined): string {
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

function trimRepoStatus(repo: TrimRepoResult, reportOnly: boolean): string {
  if (repo.error) return `error: ${repo.error}`;
  if (repo.skipped) return `skipped: ${repo.skipped}`;
  if (repo.needs_remount) return 'needs remount';
  if (reportOnly) return repo.discards_active ? 'discards on' : 'discards off';
  return repo.refreshed ? 'trimmed (mapping refreshed)' : 'trimmed';
}

/**
 * Run repository_trim. A positional `<ref>` scopes to one repo (its machine is
 * derived from the ref); no ref runs the machine-wide form against `-m`.
 */
async function handleTrimAction(ref: string | undefined, options: TrimOptions): Promise<void> {
  let machineName: string;
  let kubeCluster: string | undefined;
  const params: Record<string, unknown> = {};
  // #74: set only by the REF arm. The machine-wide form addresses the machine's
  // own default datastore by definition, so leaving it undefined there is the
  // correct answer, not an omission.
  let datastore: string | undefined;

  if (ref) {
    // A ref carries its own machine, so -m would be contradictory.
    if (options.machine) {
      throw new ValidationError(t('commands.repo.refMachineConflict', { verb: 'trim' }));
    }
    // Gate A read-only resolution: the trim run is itself the verification.
    const resolved = await resolveRepoRef(ref, { readOnly: true });
    machineName = resolved.machineName;
    kubeCluster = resolved.kubeCluster;
    const repo = await configService.getRepository(resolved.repoKey);
    if (!repo) {
      throw new Error(t('commands.repo.trim.repoNotFound', { name: resolved.name }));
    }
    params.name = repo.repositoryGuid;
    datastore = await recordedDatastoreMount(resolved.repoKey);
  } else {
    // Machine-wide form: trim every mounted repo on the machine (errors when
    // -m is also absent, as before).
    const target = await resolveRepoTarget({ machine: options.machine });
    machineName = target.machineName;
    kubeCluster = target.kubeCluster;
  }

  await assertMachineExists(machineName);

  if (options.docker || options.dockerVolumes) params.docker = true;
  if (options.dockerVolumes) params.docker_volumes = true;
  if (options.reportOnly) params.report_only = true;

  outputService.info(t('commands.repo.trim.starting', { machine: machineName }));

  const result = await getExecutor().execute({
    functionName: 'repository_trim',
    machineName,
    ...(kubeCluster !== undefined && { kubeCluster }),
    datastore,
    params,
    debug: options.debug,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(result, t('commands.repo.trim.failed'));
    return;
  }

  const parsed = parseDatastorePruneOutput(result.stdout ?? '') as TrimResult;
  renderTrimResult(parsed);
}

function renderTrimResult(parsed: TrimResult | null | undefined): void {
  if (!parsed) {
    outputService.error(t('commands.repo.trim.failed'));
    return;
  }
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(parsed, format);
    return;
  }

  const repos = parsed.repos ?? [];
  if (repos.length === 0) {
    outputService.info(t('commands.repo.trim.noMountedRepos'));
    return;
  }

  const reportOnly = Boolean(parsed.report_only);
  const rows = repos.map((repo) => ({
    repository: repo.name ?? repo.guid,
    status: trimRepoStatus(repo, reportOnly),
    // Docker reclaim runs independently of the fstrim snapshot guard, so a repo
    // can show reclaimed build-cache bytes here even when its status is "skipped".
    docker: reportOnly ? '-' : formatTrimBytes(repo.docker_reclaimed_bytes),
    trimmed: reportOnly ? '-' : formatTrimBytes(repo.trimmed_bytes),
    reclaimable: formatTrimBytes(repo.estimated_reclaimable_bytes),
  }));
  outputService.print(rows, 'table');

  if (!reportOnly) {
    outputService.success(
      t('commands.repo.trim.completed', {
        total: formatTrimBytes(parsed.total_trimmed_bytes),
      })
    );
  }
}

/** Register `repo trim` — online pool-space reclamation (rediacc/renet#76). */
export function registerRepoTrimCommand(repo: Command): void {
  repo
    .command('trim')
    .summary(t('commands.repo.trim.descriptionShort'))
    .description(t('commands.repo.trim.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('--docker', t('commands.repo.trim.dockerOption'))
    .option('--docker-volumes', t('commands.repo.trim.dockerVolumesOption'))
    .option('--report-only', t('commands.repo.trim.reportOnlyOption'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string | undefined, options: TrimOptions) => {
      try {
        await handleTrimAction(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}
