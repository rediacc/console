import readline from 'node:readline';
import { DEFAULTS } from '@rediacc/shared/config';
import { getMachineContainers } from '@rediacc/shared/services/machine';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployAllRepoKeys } from '../services/repo-key-deployment.js';
import { telemetryService } from '../services/telemetry.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { createRepoNameResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

/** Prompt the user for batch confirmation. Returns true if confirmed. */
export async function confirmBatch(
  action: string,
  count: number,
  machine: string
): Promise<boolean> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`${t('commands.repo.batchConfirm', { action, count, machine })} `, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'y');
    });
  });
}

async function ensureDns(repoName: string, machineName: string): Promise<string | undefined> {
  try {
    const machineConfig = await configService.getLocalMachine(machineName);
    const baseDomain = machineConfig.infra?.baseDomain;
    if (baseDomain && machineConfig.infra) {
      const localConfig = await configService.getLocalConfig();
      const { ensureRepoDnsRecords } = await import('../services/infra-provision.js');
      await ensureRepoDnsRecords(machineName, repoName, machineConfig.infra, localConfig);
    }
    return baseDomain;
  } catch {
    // Non-fatal: DNS record creation failure should not block repo up
    return undefined;
  }
}

// Auto-sync the acme cert cache from the machine.
//
// Skipped if the cached entry for this baseDomain was updated within the last
// AUTO_SYNC_MIN_INTERVAL_HOURS window — this prevents a series of back-to-back
// `repo up` calls from SSH-thrashing the host for a file that Traefik refreshes
// only on renewal. When sync runs and actually changes something, we emit an
// info-level log so the behavior is visible; silent failures are swallowed as
// before because cert cache is advisory.
async function maybeSyncCertCache(baseDomain: string, machineName: string): Promise<void> {
  try {
    const { isCertCacheStale, downloadCertCache } = await import('../services/cert-cache.js');
    const current = await configService.getCurrent().catch(() => undefined);
    const entry = current?.infra?.acmeCertCache?.[baseDomain];
    if (!isCertCacheStale(entry?.updatedAt)) return;
    const before = entry?.certCount ?? 0;
    const result = await downloadCertCache(machineName, { silent: true });
    if (result && result.certCount !== before) {
      outputService.info(
        t('commands.repo.certSync.updated', {
          count: result.certCount,
          machine: machineName,
        })
      );
    }
  } catch {
    // Non-fatal: cert cache failure should not block repo up
  }
}

export async function postRepoUpTasks(repoName: string, machineName: string): Promise<void> {
  const baseDomain = await ensureDns(repoName, machineName);

  if (baseDomain) {
    await maybeSyncCertCache(baseDomain, machineName);
  }

  if (baseDomain) {
    await printResolvedServiceUrls(repoName, machineName, `${machineName}.${baseDomain}`);
  }
}

// Containers carry a partial-rediacc-label shape on the JSON wire; this local
// alias avoids leaking through @rediacc/shared types we don't need to depend
// on here.
type LabeledContainer = { name: string; labels?: Record<string, string> };

function autoRouteHost(
  c: LabeledContainer,
  parentName: string,
  repoName: string,
  tag: string | undefined,
  machineDomain: string
): string {
  const labels = c.labels ?? {};
  const rediaccName = labels['rediacc.service_name'] as string | undefined;
  const composeName = labels['com.docker.compose.service'] as string | undefined;
  const serviceName = rediaccName ?? composeName ?? c.name;
  return tag
    ? `${serviceName}-fork-${tag}.${parentName}.${machineDomain}`
    : `${serviceName}.${repoName}.${machineDomain}`;
}

const TRAEFIK_RULE_KEY_RE = /^traefik\.http\.routers\..+\.rule$/;
const HOST_VALUE_RE = /Host\(`([^`]+)`\)/g;

function collectHostsFromContainer(labels: Record<string, string>, into: Set<string>): void {
  const rediaccDomain = labels['rediacc.domain'] as string | undefined;
  if (rediaccDomain) {
    for (const h of rediaccDomain
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)) {
      into.add(h);
    }
  }
  for (const [key, value] of Object.entries(labels)) {
    if (!TRAEFIK_RULE_KEY_RE.test(key)) continue;
    for (const m of value.matchAll(HOST_VALUE_RE)) {
      into.add(m[1]);
    }
  }
}

function extractCustomHosts(matched: LabeledContainer[]): Set<string> {
  const customHosts = new Set<string>();
  for (const c of matched) {
    collectHostsFromContainer(c.labels ?? {}, customHosts);
  }
  return customHosts;
}

// emitResolvedLines prints one Exposed: line per service_port container and
// one per custom Traefik / rediacc.domain host. Returns true if it printed
// anything (so the caller can decide whether to fall back to the template).
function emitResolvedLines(
  matched: LabeledContainer[],
  repoName: string,
  parentName: string,
  tag: string | undefined,
  machineDomain: string
): boolean {
  const serviceContainers = matched.filter((c) => c.labels?.['rediacc.service_port'] !== undefined);
  for (const c of serviceContainers) {
    const host = autoRouteHost(c, parentName, repoName, tag, machineDomain);
    outputService.info(`Exposed: https://${host}`);
  }
  const customHosts = extractCustomHosts(matched);
  for (const host of customHosts) {
    outputService.info(`Exposed: https://${host}  (custom)`);
  }
  return serviceContainers.length > 0 || customHosts.size > 0;
}

export async function printResolvedServiceUrls(
  repoName: string,
  machineName: string,
  machineDomain: string
): Promise<void> {
  try {
    const [parentName, tag] = repoName.includes(':') ? repoName.split(':') : [repoName, undefined];

    const provider = await getStateProvider();
    const machine = await provider.machines.getWithVaultStatus({
      teamName: '',
      machineName,
    });

    if (!machine) {
      printServiceUrlPattern(repoName, machineDomain);
      return;
    }

    // The rediacc.repo_name label holds the FULL repo name including any
    // :tag suffix for forks (e.g. "mautic:bugfix"), so a direct equality
    // check covers both grands and forks. Traefik Host rules and the
    // rediacc.domain label are already runtime-interpolated on running
    // containers, so we read literal hostnames.
    const matched = getMachineContainers(machine).filter(
      (c) => c.labels?.['rediacc.repo_name'] === repoName
    );

    const emitted = emitResolvedLines(matched, repoName, parentName, tag, machineDomain);
    if (!emitted) {
      printServiceUrlPattern(repoName, machineDomain);
    }
  } catch {
    printServiceUrlPattern(repoName, machineDomain);
  }
}

export function printServiceUrlPattern(repoName: string, machineDomain: string): void {
  try {
    if (repoName.includes(':')) {
      const [parentName, tag] = repoName.split(':');
      outputService.info(
        `Exposed services (rediacc.service_port): https://{service}-fork-${tag}.${parentName}.${machineDomain}`
      );
    } else {
      outputService.info(
        `Exposed services (rediacc.service_port): https://{service}.${repoName}.${machineDomain}`
      );
    }
  } catch {
    // Non-fatal
  }
}

export async function handleUpAll(options: {
  machine: string;
  includeForks?: boolean;
  mountOnly?: boolean;
  parallel?: boolean;
  concurrency?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  await deployAllRepoKeys(options.machine);

  const params: Record<string, unknown> = {};
  if (options.includeForks) params.include_forks = true;
  if (options.mountOnly) params.mount_only = true;
  if (options.dryRun) params.dry_run = true;
  if (options.parallel) params.parallel = true;
  if (options.parallel && options.concurrency) {
    params.concurrency = Number.parseInt(options.concurrency, 10);
  }

  outputService.info(t('commands.repo.upAll.starting', { machine: options.machine }));

  const result = await localExecutorService.execute({
    functionName: 'repository_up_all',
    machineName: options.machine,
    params,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(t('commands.repo.upAll.completed'));
  } else {
    renderLocalExecutionFailure(result, t('commands.repo.upAll.failed'));
  }
}

class Semaphore {
  private readonly queue: (() => void)[] = [];
  private running = 0;

  constructor(private readonly max: number) {}

  async acquire(): Promise<void> {
    if (this.running < this.max) {
      this.running++;
      return;
    }
    return new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    this.running--;
    const next = this.queue.shift();
    if (next) {
      this.running++;
      next();
    }
  }
}

export async function runBatchParallel(
  repos: { name: string }[],
  concurrency: number,
  action: string,
  taskFn: (repoName: string) => Promise<void>
): Promise<void> {
  const sem = new Semaphore(concurrency);
  let succeeded = 0;

  await Promise.allSettled(
    repos.map(async ({ name }) => {
      await sem.acquire();
      try {
        outputService.info(t('commands.repo.batchStarting', { action, repo: name }));
        await taskFn(name);
        succeeded++;
      } catch (error) {
        outputService.warn(
          t('commands.repo.batchFailed', {
            action,
            repo: name,
            error: error instanceof Error ? error.message : String(error),
          })
        );
      } finally {
        sem.release();
      }
    })
  );

  outputService.info(t('commands.repo.batchResult', { action, succeeded, total: repos.length }));
}

export async function runBatchOperation(
  action: string,
  machine: string,
  skipConfirm: boolean,
  fn: (repoName: string) => Promise<void>,
  options?: { parallel?: boolean; concurrency?: string }
): Promise<void> {
  const repos = await configService.listRepositories();
  if (!skipConfirm && !(await confirmBatch(action, repos.length, machine))) {
    return;
  }

  if (options?.parallel) {
    const concurrency = Number.parseInt(
      options.concurrency ?? String(DEFAULTS.BATCH.CONCURRENCY),
      10
    );
    await runBatchParallel(repos, concurrency, action, fn);
    return;
  }

  let succeeded = 0;
  for (let i = 0; i < repos.length; i++) {
    const { name } = repos[i];
    outputService.info(
      t('commands.repo.batchIterating', { action, current: i + 1, total: repos.length, repo: name })
    );
    try {
      await fn(name);
      succeeded++;
    } catch (error) {
      outputService.warn(
        t('commands.repo.batchFailed', {
          action,
          repo: name,
          error: error instanceof Error ? error.message : String(error),
        })
      );
    }
  }
  outputService.info(t('commands.repo.batchResult', { action, succeeded, total: repos.length }));
}

export async function handleDownAll(options: {
  machine: string;
  yes?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  if (options.dryRun) {
    outputService.print(
      { dryRun: true, action: 'down-all', machine: options.machine },
      getOutputFormat()
    );
    return;
  }

  const repos = await configService.listRepositories();
  if (!options.yes && !(await confirmBatch('Down', repos.length, options.machine))) {
    return;
  }

  outputService.info(t('commands.repo.down.allStarting', { machine: options.machine }));

  const result = await localExecutorService.execute({
    functionName: 'repository_down_all',
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(t('commands.repo.down.allCompleted'));
  } else {
    renderLocalExecutionFailure(result, t('commands.repo.down.allFailed'));
  }
}

// Renders the `repo list` table: resolves tag/type from local config, marks
// server-sourced names (not in local config) with ' *', and prints a legend
// when any such name is shown.
async function printRepoListTable(resolved: Record<string, unknown>[]): Promise<void> {
  const { parseRepoRef } = await import('../utils/config-schema.js');
  const { classifyRepoType } = await import('../utils/repo-classify.js');
  const repoConfigs = await configService.listRepositories().catch((err: unknown) => {
    telemetryService.trackError(err, { operation: 'repo.list_repositories' });
    return [];
  });
  const configLookup = new Map<string, { grandGuid?: string; tag?: string }>();
  for (const rc of repoConfigs) {
    configLookup.set(rc.config.repositoryGuid, {
      grandGuid: rc.config.grandGuid,
      tag: rc.config.tag,
    });
  }
  const compact = resolved.map((r) => {
    const cfg = configLookup.get((r.guid ?? r.name) as string);
    const { name: baseName, tag: parsedTag } = parseRepoRef(r.name as string);
    const serverSourced = r.name_source === 'server';
    return {
      name: serverSourced ? `${baseName} *` : baseName,
      tag: cfg?.tag ?? parsedTag,
      type: classifyRepoType({ is_fork: Boolean(r.is_fork) }, cfg),
      size: r.size_human,
      mounted: r.mounted ? 'Yes' : 'No',
      docker: r.docker_running ? 'Yes' : 'No',
      containers: r.container_count,
      services: r.service_count,
      modified: r.modified_human,
    };
  });
  outputService.print(compact, 'table');
  if (resolved.some((r) => r.name_source === 'server')) {
    outputService.info(t('commands.repo.list.serverNameLegend'));
  }
}

export async function handleRepoList(options: {
  machine: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}): Promise<void> {
  try {
    outputService.info(t('commands.repo.list.starting', { machine: options.machine }));
    const format = getOutputFormat();
    const result = await localExecutorService.execute({
      functionName: 'repository_list',
      machineName: options.machine,
      params: {},
      debug: options.debug,
      captureOutput: true,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (result.success) {
      const repositories = parseRepositoryListOutput(result.stdout ?? '[]');
      const nameResolver = createRepoNameResolver(await loadGuidMap());
      // Resolve each repo's display name: local config > server repo_name > GUID.
      // Keep the GUID under `guid` and record where the name came from in `name_source`.
      const resolved: Record<string, unknown>[] = repositories.map((r) => {
        const guid = String(r.name);
        const { name, source } = nameResolver(guid, r.repo_name as string | undefined);
        return { ...r, name, guid, name_source: source };
      });
      if (format === 'table') {
        await printRepoListTable(resolved);
      } else {
        outputService.print(resolved, format);
      }
      outputService.success(t('commands.repo.list.completed'));
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.list.failed', { error: result.error }));
    }
  } catch (error) {
    handleError(error);
  }
}
