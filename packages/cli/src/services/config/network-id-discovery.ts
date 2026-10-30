/**
 * Network-ID discovery and allocation floor (PLAN-config-networkid-discovery T3).
 *
 * State sync carries every repo's `networkId` to every device (ruling D1(b)), so
 * the local record normally answers. This module covers the record WITHOUT an
 * ID (data pushed before sync carried IDs, or a diverged device): the machine
 * is asked first, an allocation happens only on a definite absence, and an
 * unreachable machine fails closed (D6(a)). Allocations take the TARGET
 * machine's used set as a floor (D3(a)), so a lagging counter never hands out
 * an ID another device already placed there.
 */
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { getExecutor, requestNetworkIdAuto } from '../executor/executor-factory.js';
import type { ExecuteResult } from '../executor/types.js';
import { probeRepoNetwork } from '../repo/repo-mount-check.js';

/** Where a repo's network ID is asked for: the machine, and the datastore mount it lives on. */
export interface NetworkIdTarget {
  machine: string;
  /** Mount path of a named datastore; undefined = the machine's default datastore. */
  datastore?: string;
  /** Set for a kubernetes-placed repo, which `repository_list` cannot see (#92). */
  kubeCluster?: string;
}

/** A record with no ID whose machine could not be asked (D6(a): fail closed). */
export class NetworkIdUndiscoverableError extends ValidationError {
  constructor(repository: string, machine: string) {
    super(t('errors.repo.networkIdUndiscoverable', { repository, machine }));
  }
}

type NetworkIdDiscovery =
  | { kind: 'found'; networkId: number }
  | { kind: 'absent'; listedIds: number[] }
  | { kind: 'unknown' };

/**
 * Ask the machine for a repo's network ID through the presence probe's own
 * `repository_list` call. `found` carries renet's persisted ID; `absent` is a
 * definite "this datastore has no such repo"; `unknown` covers an unreachable
 * machine, a failed listing, and a present repo whose mirror records no ID.
 */
async function discoverNetworkId(input: {
  repoGuid: string;
  machine: string;
  datastore?: string;
}): Promise<NetworkIdDiscovery> {
  const probe = await probeRepoNetwork(input.repoGuid, input.machine, {
    ...(input.datastore !== undefined && { datastore: input.datastore }),
  });
  if (probe === undefined) return { kind: 'unknown' };
  if (!probe.present) return { kind: 'absent', listedIds: probe.listedIds };
  return probe.networkId === undefined
    ? { kind: 'unknown' }
    : { kind: 'found', networkId: probe.networkId };
}

/**
 * Every network ID with a footprint on `machine` (repos in every datastore,
 * k3s members, units, loopback aliases), from renet's `network_used`.
 * `undefined` when the machine cannot answer, including a renet that predates
 * the function (rollout skew), so callers fall back to the probe's listed IDs.
 */
async function machineUsedNetworkIds(machine: string): Promise<number[] | undefined> {
  let result: ExecuteResult;
  try {
    result = await getExecutor().execute({
      functionName: 'network_used',
      machineName: machine,
      params: {},
      captureOutput: true,
      quietSpinners: true,
    });
  } catch {
    return undefined;
  }
  if (!result.success || !result.stdout) return undefined;
  return parseNetworkUsed(result.stdout);
}

/** Parse `renet network used --json` (one JSON array of claims) into its IDs. */
export function parseNetworkUsed(stdout: string): number[] | undefined {
  const lines = stdout.split('\n').map((l) => l.trim());
  for (let i = lines.length - 1; i >= 0; i--) {
    const ids = claimIds(lines[i]);
    if (ids !== undefined) return ids;
  }
  return undefined;
}

/** The network IDs of one claims line, or `undefined` when the line is not one. */
function claimIds(line: string): number[] | undefined {
  if (!line.startsWith('[')) return undefined;
  let claims: unknown;
  try {
    claims = JSON.parse(line);
  } catch {
    return undefined;
  }
  if (!Array.isArray(claims)) return undefined;
  return claims
    .map((c) => (c as { network_id?: unknown } | null)?.network_id)
    .filter((id): id is number => typeof id === 'number' && Number.isInteger(id) && id > 0);
}

/** The target machine's used set, or `fallback` when it cannot answer. */
export async function targetFloor(
  target: NetworkIdTarget,
  fallback: number[] = []
): Promise<number[]> {
  return (await machineUsedNetworkIds(target.machine)) ?? fallback;
}

/** Allocate in the active config with `floor` as the target machine's used set. */
export async function allocateNetworkIdWithFloor(floor: number[]): Promise<number> {
  const { configService } = await import('./config-resources.js');
  return configService.allocateNetworkId({ floor });
}

/** A network ID renet allocates inside the repo's next `job start` (`network_id: "auto"`). */
export const NETWORK_ID_AUTO = 'auto';

/**
 * The resolution order for a record with no ID (plan §2.2, steps 2-4):
 * the machine's persisted ID; else, on a definite absence, {@link NETWORK_ID_AUTO}:
 * renet allocates the ID inside the job, above the machine's used set and the
 * caller's IDs, under its spool lock (agent/plans/PLAN-detached-jobs.md section 14),
 * which replaces the client's `network_used` probe and allocation; else a
 * fail-closed error. A kubernetes-placed repo is invisible to the probe (#92),
 * so it goes to renet's allocation directly.
 */
export async function resolveMissingNetworkId(input: {
  repository: string;
  repoGuid: string;
  target: NetworkIdTarget;
}): Promise<number | typeof NETWORK_ID_AUTO> {
  const { target } = input;
  if (target.kubeCluster !== undefined) return NETWORK_ID_AUTO;

  const found = await discoverNetworkId({
    repoGuid: input.repoGuid,
    machine: target.machine,
    ...(target.datastore !== undefined && { datastore: target.datastore }),
  });
  if (found.kind === 'found') return found.networkId;
  if (found.kind === 'unknown') {
    throw new NetworkIdUndiscoverableError(input.repository, target.machine);
  }
  return NETWORK_ID_AUTO;
}

/**
 * Derive a repo's target from its recorded placement alone (no remote call),
 * for `ensureRepositoryNetworkId` callers that resolved no target themselves.
 */
async function resolveNetworkIdTarget(repoKey: string): Promise<NetworkIdTarget> {
  const { configService } = await import('./config-resources.js');
  const { placementViewFromConfig, resolveMachine } = await import(
    '../addressing/resolve-machine.js'
  );
  const { namedDatastoreMount } = await import('../cluster/cluster-target.js');
  const config = await configService.getCurrent();
  if (!config) throw new Error(t('errors.config.noActiveConfig'));
  const resolved = await resolveMachine(repoKey, placementViewFromConfig(config), {
    readOnly: true,
  });
  return {
    machine: resolved.machine,
    ...(resolved.datastore !== undefined && {
      datastore: namedDatastoreMount(resolved.datastore),
    }),
    ...(resolved.cluster !== undefined && { kubeCluster: resolved.cluster }),
  };
}

/** renet's refusal of a network ID (`private/renet/pkg/repository/netid_guard.go`). */
export interface NetworkIdConflict {
  code: 'network_id_in_use' | 'network_id_mismatch';
  networkId: number;
  persistedNetworkId?: number;
  holder?: { kind: string; name: string; datastore: string };
}

/**
 * Find renet's one-line JSON refusal in a failed result's output. renet prints
 * it to stderr; the relay may prefix the line, so the JSON is taken from the
 * first `{` on a line that names a network-ID code.
 */
export function parseNetworkIdConflict(
  result: Pick<ExecuteResult, 'stderr' | 'stdout' | 'error'>
): NetworkIdConflict | undefined {
  const text = [result.stderr, result.stdout, result.error].filter(Boolean).join('\n');
  for (const line of text.split('\n')) {
    const conflict = conflictFromLine(line);
    if (conflict) return conflict;
  }
  return undefined;
}

function conflictFromLine(line: string): NetworkIdConflict | undefined {
  if (!line.includes('"network_id_in_use"') && !line.includes('"network_id_mismatch"')) {
    return undefined;
  }
  const start = line.indexOf('{');
  const end = line.lastIndexOf('}');
  if (start === -1 || end <= start) return undefined;
  try {
    return toConflict(JSON.parse(line.slice(start, end + 1)) as Record<string, unknown>);
  } catch {
    return undefined;
  }
}

function toConflict(raw: Record<string, unknown>): NetworkIdConflict | undefined {
  const code = raw.code;
  if (code !== 'network_id_in_use' && code !== 'network_id_mismatch') return undefined;
  if (typeof raw.network_id !== 'number') return undefined;
  const holder = raw.holder as Record<string, unknown> | undefined;
  return {
    code,
    networkId: raw.network_id,
    ...(typeof raw.persisted_network_id === 'number' && {
      persistedNetworkId: raw.persisted_network_id,
    }),
    ...(holder &&
      typeof holder === 'object' && {
        holder: {
          kind: String(holder.kind ?? ''),
          name: String(holder.name ?? ''),
          datastore: String(holder.datastore ?? ''),
        },
      }),
  };
}

/**
 * The ID a refused verb moves to: a mismatch adopts the repo's persisted ID
 * (the machine wins, D4(a)); an ID in use allocates past the holder, above the
 * machine's used set. `undefined` when the mismatch names a persisted ID this
 * run already saw refused: the repo can only run on that ID, so no retry can succeed.
 */
export async function nextNetworkIdAfterConflict(
  conflict: NetworkIdConflict,
  target: NetworkIdTarget,
  allocate: (floor: number[]) => Promise<number> = allocateNetworkIdWithFloor,
  refused: number[] = []
): Promise<number | undefined> {
  if (conflict.code === 'network_id_mismatch' && conflict.persistedNetworkId !== undefined) {
    return refused.includes(conflict.persistedNetworkId) ? undefined : conflict.persistedNetworkId;
  }
  const used = await targetFloor(target);
  return allocate([...new Set([...used, ...refused, conflict.networkId])]);
}

/**
 * The operator-facing text for a refusal on a verb that must not re-allocate
 * (`up`/`mount` of an existing repo): names the holder and points to
 * `rdc config reconcile`.
 */
export function networkIdConflictMessage(
  conflict: NetworkIdConflict,
  repository: string,
  machine: string
): string {
  const holder = conflict.holder
    ? `${conflict.holder.kind} ${conflict.holder.name}`.trim()
    : String(conflict.networkId);
  return t('errors.repo.networkIdInUse', {
    networkId: conflict.networkId,
    repository,
    holder,
    machine,
  });
}

/**
 * A repo's network ID: a synced local ID wins; a record without one asks its machine first, and an
 * unreachable machine fails closed. Lives here rather than on ConfigService so a config-only verb
 * importing the config service never reaches the executor.
 *
 * Returns 0 when no ID exists yet (a definite absence, or a kubernetes-placed repo): the repo's next
 * job on its machine then carries `network_id: "auto"`, renet allocates the ID in `job start`, and
 * the executor seam records it in the config (executor-factory `requestNetworkIdAuto`). 0 is the
 * vault's "no ID" value, so nothing downstream reads it as an ID.
 */
export async function ensureRepositoryNetworkId(
  repoRef: string,
  target?: NetworkIdTarget
): Promise<number> {
  const { configService } = await import('./config-resources.js');
  const key = await configService.getRepositoryKey(repoRef);
  if (!key) throw new Error(`Repository "${repoRef}" not found`);
  const repo = (await configService.getResourceState()).getRepositories()[key];
  if (repo.networkId !== undefined && repo.networkId > 0) return repo.networkId;
  const resolvedTarget = target ?? (await resolveNetworkIdTarget(key));
  const networkId = await resolveMissingNetworkId({
    repository: key,
    repoGuid: repo.repositoryGuid,
    target: resolvedTarget,
  });
  if (networkId === NETWORK_ID_AUTO) {
    requestNetworkIdAuto({
      machine: resolvedTarget.machine,
      aliases: [key, repoRef, repo.repositoryGuid],
      repoGuid: repo.repositoryGuid,
      repoName: key.split(':')[0],
      recordAs: key,
    });
    return 0;
  }
  await recordNetworkId(key, networkId);
  return networkId;
}

/** Write a repo's network ID into the active config's state (also the executor seam's record of an ID renet allocated). */
export async function recordNetworkId(repoKey: string, networkId: number): Promise<void> {
  const { configService } = await import('./config-resources.js');
  const state = await configService.getResourceState();
  const key = (await configService.getRepositoryKey(repoKey)) ?? repoKey;
  const repos = state.getRepositories();
  if (!(key in repos)) return;
  repos[key] = { ...repos[key], networkId };
  await state.setRepositories(repos);
}

/**
 * After renet refused a verb's network ID: move to the next one (past the holder, or the persisted ID on a mismatch), record it, and run `rerun` once with it. `undefined` when the failure is not a network-ID refusal, or is a mismatch whose persisted ID was already refused.
 */
export async function rerunAfterNetworkIdConflict(input: {
  failed: ExecuteResult;
  repoKey: string;
  target: NetworkIdTarget;
  rerun: (networkId: number) => Promise<ExecuteResult>;
  allocate?: (floor: number[]) => Promise<number>;
  /** IDs already refused earlier in this run, kept out of the next allocation. */
  refused?: number[];
}): Promise<ExecuteResult | undefined> {
  const conflict = parseNetworkIdConflict(input.failed);
  if (!conflict) return undefined;
  const next = await nextNetworkIdAfterConflict(
    conflict,
    input.target,
    input.allocate,
    input.refused
  );
  if (next === undefined) return undefined;
  await recordNetworkId(input.repoKey, next);
  return input.rerun(next);
}

/** Attempts a create-like verb gets, the first included, on a shared machine whose IDs keep colliding. */
export const MAX_NETWORK_ID_ATTEMPTS = 6;

/**
 * Run a create-like verb (create, fork, restore) and, when renet refuses its network ID, retry it on the next ID, up to {@link MAX_NETWORK_ID_ATTEMPTS} attempts. Every refused ID and the machine's used set stay out of each allocation. Any other failure, or the refusal of the last attempt, is returned as is.
 */
export async function runWithNetworkIdRetry(input: {
  repoKey: string;
  target: NetworkIdTarget;
  networkId: number;
  run: (networkId: number) => Promise<ExecuteResult>;
  allocate?: (floor: number[]) => Promise<number>;
}): Promise<ExecuteResult> {
  const refused: number[] = [];
  let result = await input.run(input.networkId);
  for (let attempt = 1; attempt < MAX_NETWORK_ID_ATTEMPTS && !result.success; attempt++) {
    const conflict = parseNetworkIdConflict(result);
    if (conflict) refused.push(conflict.networkId);
    const retried = await rerunAfterNetworkIdConflict({
      ...input,
      failed: result,
      rerun: input.run,
      refused,
    });
    if (!retried) break;
    result = retried;
  }
  return result;
}
