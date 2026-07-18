import readline from 'node:readline';
import { getMachineContainers } from '@rediacc/shared/services/machine';
import { t } from '../i18n/index.js';
import { getDatastore, requireDatastoreHost } from '../services/config/config-datastores.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import type { MachineConnectionLease } from '../services/machine/machine-connection.js';
import { deployAllRepoKeys } from '../services/repo/repo-key-deployment.js';
import { telemetryService } from '../services/telemetry/telemetry.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createRepoNameResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoTarget } from '../utils/repo-target.js';
import { recordTimelineStep, type TimelineStep } from '../utils/timeline.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

/** Prompt the user for batch confirmation. Returns true if confirmed. */
async function confirmBatch(action: string, count: number, machine: string): Promise<boolean> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`${t('commands.repo.batchConfirm', { action, count, machine })} `, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'y');
    });
  });
}

/**
 * Ensure DNS records exist for a repo's auto-route domain. Pure HTTP — needs
 * only names, so callers may fire it before (or concurrent with) SSH work.
 * Resolves to the machine's baseDomain (undefined when not configured or on
 * failure; DNS issues never block repo up).
 */
export async function ensureDns(
  repoName: string,
  machineName: string
): Promise<string | undefined> {
  try {
    const machineConfig = await configService.getLocalMachine(machineName);
    const baseDomain = machineConfig.infra?.baseDomain;
    if (baseDomain && machineConfig.infra) {
      const localConfig = await configService.getLocalConfig();
      const { ensureRepoDnsRecords } = await import('../services/provision/infra-provision.js');
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
async function maybeSyncCertCache(
  baseDomain: string,
  machineName: string,
  lease?: MachineConnectionLease
): Promise<void> {
  try {
    const { isCertCacheStale, downloadCertCache } = await import(
      '../services/account/cert-cache.js'
    );
    const current = await configService.getCurrent().catch(() => undefined);
    const entry = current?.state?.certCache?.[baseDomain];
    if (!isCertCacheStale(entry?.updatedAt)) return;
    const before = entry?.certCount ?? 0;
    const result = await downloadCertCache(machineName, { silent: true }, lease?.sftp);
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

/** Read the machine's baseDomain from local config (cert sync does not need DNS to settle). */
async function getBaseDomain(machineName: string): Promise<string | undefined> {
  try {
    const machineConfig = await configService.getLocalMachine(machineName);
    return machineConfig.infra?.baseDomain;
  } catch {
    return undefined;
  }
}

export interface PostRepoUpTasksOptions {
  /**
   * Pre-started ensureDns promise (fired early by the caller, e.g. before
   * SSH work). When provided, the caller owns its 'dns' step timing.
   */
  dnsPromise?: Promise<string | undefined>;
  /**
   * Shared machine connection held by the caller for the duration of this
   * call. The pooled SSH paths underneath (cert sync, service-URL status
   * fetch) reuse it via machineConnections refcounting.
   */
  lease?: MachineConnectionLease;
  /** Collect orchestrated phase timings ('dns', 'cert_sync', 'service_urls') for timeline rendering. */
  steps?: TimelineStep[];
}

export async function postRepoUpTasks(
  repoName: string,
  machineName: string,
  options: PostRepoUpTasksOptions = {}
): Promise<void> {
  const { steps } = options;

  // DNS-await ∥ cert sync: cert sync only needs the baseDomain from local
  // config, so it does not wait for DNS record creation to settle.
  const dnsPromise =
    options.dnsPromise ??
    recordTimelineStep(steps, 'dns', () => ensureDns(repoName, machineName), { parallel: true });
  const certPromise = recordTimelineStep(
    steps,
    'cert_sync',
    async () => {
      const baseDomain = await getBaseDomain(machineName);
      if (baseDomain) {
        await maybeSyncCertCache(baseDomain, machineName, options.lease);
      }
    },
    { parallel: true }
  );

  const [dnsSettled] = await Promise.allSettled([dnsPromise, certPromise]);
  const baseDomain = dnsSettled.status === 'fulfilled' ? dnsSettled.value : undefined;

  if (baseDomain) {
    await recordTimelineStep(steps, 'service_urls', () =>
      printResolvedServiceUrls(repoName, machineName, `${machineName}.${baseDomain}`)
    );
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

    // Lease-aware status fetch: machineConnections pools by host, so when the
    // caller holds a lease on this machine the SSH session is reused. Only
    // the containers section is needed to resolve service URLs.
    const { fetchMachineStatus } = await import('../services/machine/machine-status.js');
    const listResult = await fetchMachineStatus(machineName, { sections: ['containers'] });
    const machine = { machineName, vaultStatus: JSON.stringify(listResult) };

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
  machine?: string;
  /** Commander sets this false when `--no-start` is passed (mount-only batch). */
  start?: boolean;
  includeForks?: boolean;
  parallel?: boolean;
  concurrency?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  const { machineName } = await resolveRepoTarget({ machine: options.machine });

  await deployAllRepoKeys(machineName);

  const params: Record<string, unknown> = {};
  if (options.includeForks) params.include_forks = true;
  if (options.start === false) params.mount_only = true;
  if (options.dryRun) params.dry_run = true;
  if (options.parallel) params.parallel = true;
  if (options.parallel && options.concurrency) {
    params.concurrency = Number.parseInt(options.concurrency, 10);
  }

  outputService.info(t('commands.repo.upAll.starting', { machine: machineName }));

  const result = await getExecutor().execute({
    functionName: 'repository_up_all',
    machineName,
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

export async function handleDownAll(options: {
  machine?: string;
  parallel?: boolean;
  concurrency?: string;
  yes?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  const { machineName } = await resolveRepoTarget({ machine: options.machine });

  if (options.dryRun) {
    outputService.print(
      { dryRun: true, action: 'down-all', machine: machineName },
      getOutputFormat()
    );
    return;
  }

  const repos = await configService.listRepositories();
  if (!options.yes && !(await confirmBatch('Down', repos.length, machineName))) {
    return;
  }

  outputService.info(t('commands.repo.down.allStarting', { machine: machineName }));

  const result = await getExecutor().execute({
    functionName: 'repository_down_all',
    machineName,
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
  machine?: string;
  datastore?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}): Promise<void> {
  try {
    if (options.machine && options.datastore) {
      throw new ValidationError(t('errors.repo.listTargetExclusive'));
    }
    // A datastore names WHERE the repos live; the machine holding it right now is a
    // fact about the datastore, not something the operator should have to know. So
    // --datastore resolves to its holder, and a detached datastore says so rather
    // than dispatching at nothing.
    const { machineName, kubeCluster } = options.datastore
      ? {
          machineName: await requireDatastoreHost(options.datastore),
          kubeCluster: (await getDatastore(options.datastore)).cluster,
        }
      : await resolveRepoTarget(options);
    outputService.info(t('commands.repo.list.starting', { machine: machineName }));
    const format = getOutputFormat();
    const result = await getExecutor().execute({
      functionName: 'repository_list',
      machineName,
      kubeCluster,
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
