import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoTarget } from '../utils/repo-target.js';
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
  machine?: string;
  cluster?: string;
  name?: string;
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

/** Run repository_trim on a machine, optionally scoped to one repo. */
async function handleTrimAction(options: TrimOptions): Promise<void> {
  const { machineName, kubeCluster } = await resolveRepoTarget(options);
  await assertMachineExists(machineName);

  const params: Record<string, unknown> = {};
  if (options.name) {
    const repo = await configService.getRepository(options.name);
    if (!repo) {
      throw new Error(t('commands.repo.trim.repoNotFound', { name: options.name }));
    }
    params.name = repo.repositoryGuid;
  }
  if (options.docker || options.dockerVolumes) params.docker = true;
  if (options.dockerVolumes) params.docker_volumes = true;
  if (options.reportOnly) params.report_only = true;

  outputService.info(t('commands.repo.trim.starting', { machine: machineName }));

  const result = await getExecutor().execute({
    functionName: 'repository_trim',
    machineName,
    kubeCluster,
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
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--name <name>', t('commands.repo.trim.nameOption'))
    .option('--docker', t('commands.repo.trim.dockerOption'))
    .option('--docker-volumes', t('commands.repo.trim.dockerVolumesOption'))
    .option('--report-only', t('commands.repo.trim.reportOnlyOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: TrimOptions) => {
      try {
        await handleTrimAction(options);
      } catch (error) {
        handleError(error);
      }
    });
}
