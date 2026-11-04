/** What `repo replicate`, its refresh and its remove share: the phase runner, the small readers and one replica's way up. */

import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { getCluster } from '../config/config-cluster-ops.js';
import { configService } from '../config/config-resources.js';
import { parseCapturedJson } from '../executor/local-executor.js';
import type { PlannedStep } from '../jobs/steps.js';
import { type ClusterPhaseResult, runClusterPhase } from './cluster-job.js';
import { ensureForkLicense, type ReplicaNode } from './repo-replicate.js';

const STEP_LABEL = 'Replica step';
const FORK_WRITES = 'local';

// Test seam (mirrors cluster-kube's __setHealthGateClock).
let clockFn: () => number = () => Date.now();
export function __setReplicateClock(fn: () => number): void {
  clockFn = fn;
}
export function replicateNow(): number {
  return clockFn();
}

export type Replica = ReplicaSet['replicas'][number];

export interface PhaseOptions {
  debug?: boolean;
  capture?: boolean;
  steps?: PlannedStep[];
}

export function phase(
  verb: string,
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: PhaseOptions = {}
): Promise<ClusterPhaseResult> {
  return runClusterPhase(functionName, machineName, params, {
    label: STEP_LABEL,
    verb,
    ...options,
  });
}

/** One tag of `replica_fork`'s answer (renet pkg/datastore/replica.go). */
export interface ForkEntry {
  tag: string;
  name: string;
  state: 'forked' | 'reused' | 'placed';
  record?: unknown;
}

export function parseForkEntries(output: string | undefined): ForkEntry[] | undefined {
  if (!output) return undefined;
  try {
    const parsed = parseCapturedJson<ForkEntry[]>(output);
    return Array.isArray(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

export function forkTag(fork: string): string {
  return fork.slice(fork.indexOf(':') + 1);
}

export function forkLabel(fork: string): string {
  return fork.replace(':', '-');
}

export function sortedReplicas(set: ReplicaSet): Replica[] {
  return [...set.replicas].sort((a, b) => a.index - b.index);
}

/** A replica's private IP (kube_node_label resolves nodes by InternalIP). */
export async function nodeIp(machineName: string): Promise<string> {
  return (await configService.getLocalMachine(machineName)).ip;
}

/** The cluster's k8s-capable members (replica hosts), in pool/index order. */
export async function resolveReplicaNodes(clusterName: string): Promise<ReplicaNode[]> {
  const cluster = await getCluster(clusterName);
  const nodes: ReplicaNode[] = [];
  for (const pool of cluster.pools) {
    if (pool.role !== 'k8s-server' && pool.role !== 'k8s-agent' && pool.role !== 'hyperconverged') {
      continue;
    }
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      nodes.push({ machine: name, ip: machine.ip });
    }
  }
  return nodes;
}

export interface BringUp {
  verb: string;
  repo: string;
  repoGuid: string;
  control: string;
  debug?: boolean;
}

/**
 * Attach a fork on its node, license it, and open its volumes. The fork record
 * lives on control until the publish, so an off-control node gets it ferried.
 *
 * The order is load-bearing. renet licence-checks datastore_volumes_open against
 * the fork's own datastore id, so the licence comes first; and the open has to
 * precede the node label the publish stamps, because the label is the scheduling
 * gate and a pod must never reach a volume that is not mounted (bug #49: such a
 * replica comes up healthy, Ready and EMPTY).
 *
 * By GUID, never by name (#93): the repo folder on the fork is `repos/<guid>`.
 */
export async function bringUpReplica(
  input: BringUp,
  replica: Replica,
  entry?: ForkEntry
): Promise<void> {
  const params: Record<string, unknown> = { name: replica.fork, writes: FORK_WRITES };
  if (replica.node !== input.control && entry?.record) {
    params.record_b64 = Buffer.from(JSON.stringify(entry.record)).toString('base64');
  }
  const attached = await phase(input.verb, 'replica_attach', replica.node, params, {
    debug: input.debug,
    capture: true,
  });
  const record = parseCapturedJson<{ datastoreId?: unknown }>(attached.result.stdout);
  if (typeof record.datastoreId !== 'string' || record.datastoreId === '') {
    throw new Error(
      `Cannot license replica fork "${replica.fork}" on ${replica.node}: its datastore registry reports no datastore id for it.`
    );
  }
  await ensureForkLicense(
    { repo: input.repo, repoGuid: input.repoGuid },
    replica.fork,
    replica.node,
    record.datastoreId
  );
  await phase(
    input.verb,
    'datastore_volumes_open',
    replica.node,
    { name: replica.fork, repo: input.repoGuid },
    { debug: input.debug }
  );
}

export function notFinished(setName: string, repo: string, what: string): Error {
  return new Error(
    `Replica set "${setName}" is not finished: ${what}. ` +
      `Re-run the command to resume it, or remove it with "rdc repo replicate remove ${repo}".`
  );
}

/**
 * The control copies of the fork records. A record on a node is the live one, and
 * a later re-fork of the same tag would collide with the leftover (finding #40).
 */
export function forgetParam(replicas: Replica[], control: string): { forget?: string } {
  const forget = replicas.filter((r) => r.node !== control).map((r) => r.fork);
  return forget.length > 0 ? { forget: forget.join(',') } : {};
}
