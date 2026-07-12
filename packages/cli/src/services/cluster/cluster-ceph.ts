/**
 * Shared Ceph primitives for cluster provisioning AND whole-cluster fork.
 *
 * createCluster (cluster-provision) distributes a cluster's OWN ceph client
 * config to its OWN k8s nodes; forkCluster (cluster-kube) must give the fork's
 * DEST — nodes of a DIFFERENT cluster — access to the SOURCE cluster's ceph so
 * they can attach the fork's rbd clone (finding #7). Both need the same three
 * primitives (member resolution, a throwing dispatch, config export), so they
 * live here instead of being duplicated or forcing a circular import between the
 * two orchestrators.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { ClusterPool } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { getExecutor } from '../executor/executor-factory.js';
import { parseCapturedJson } from '../executor/local-executor.js';

/**
 * The Ceph cluster name is a fixed identity ("ceph") that is distinct from the
 * rediacc cluster name: renet's ceph_* functions default it to "rediacc", but
 * the datastore/rbd paths assume "ceph", so we pass it explicitly.
 */
export const CEPH_CLUSTER_NAME = 'ceph';

/** A materialized ceph-pool member: its config machine name and private IP. */
export interface CephMember {
  name: string;
  ip: string;
}

/**
 * Dispatch one internal ceph_* / kube_ bridge function to a member machine.
 * Throws a clear error (including renet's own failure message) on any
 * non-success so a failed step surfaces instead of silently warning.
 */
export async function dispatchCeph(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  const result = await getExecutor().execute({ functionName, machineName, params, debug });
  if (!result.success) {
    throw new Error(
      `Ceph install step "${functionName}" failed on ${machineName}: ${
        result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR
      }`
    );
  }
}

/** Resolve every ceph-pool member (name + IP) in pool/index order. */
export async function resolveCephMembers(
  clusterName: string,
  cephPools: ClusterPool[]
): Promise<CephMember[]> {
  const members: CephMember[] = [];
  for (const pool of cephPools) {
    for (let i = 1; i <= pool.count; i++) {
      const name = `${clusterName}-${pool.name}-${i}`;
      const machine = await configService.getLocalMachine(name);
      members.push({ name, ip: machine.ip });
    }
  }
  return members;
}

/**
 * Export a ceph mon's client config (/etc/ceph/ceph.conf + admin keyring) as the
 * base64 {conf,keyring} pair another node installs to reach that Ceph. Reads via
 * `ceph_client_config_export`, which shells out to `renet ceph client config
 * export --json`; the captured stdout is the `[ceph_client_config_export] {...}`
 * bridge relay format, so it is parsed with parseCapturedJson (finding #10).
 */
export async function exportCephClientConfig(
  monMachine: string,
  debug?: boolean
): Promise<{ conf: string; keyring: string }> {
  const exported = await getExecutor().execute({
    functionName: 'ceph_client_config_export',
    machineName: monMachine,
    params: {},
    debug,
    captureOutput: true,
  });
  if (!exported.success) {
    throw new Error(
      `Failed to export ceph client config from ${monMachine}: ${exported.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR}`
    );
  }
  const payload = parseCapturedJson<{ conf?: string; keyring?: string }>(exported.stdout);
  if (!payload.conf || !payload.keyring) {
    throw new Error(`ceph_client_config_export on ${monMachine} returned no conf/keyring`);
  }
  return { conf: payload.conf, keyring: payload.keyring };
}
