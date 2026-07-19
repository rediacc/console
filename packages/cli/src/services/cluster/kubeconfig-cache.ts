/**
 * On-demand kubeconfig cache for clusters.
 *
 * The kubeconfig is never stored in rediacc.json (large, rotates). It is fetched
 * over SSH from the cluster's control node and cached at
 * <config dir>/kube/<cluster>.yaml (0600), following the tofu-workdir and
 * cert-cache side-state precedents. `rdc cluster kubeconfig` exposes it.
 */

import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { resolveControlNode } from '../config/config-cluster-ops.js';
import { machineConnections } from '../machine/machine-connection.js';
import { clusterKubeconfigRemotePath } from './cluster-target.js';

const KUBE_CACHE_DIR = join(getConfigDir(), 'kube');

/** Local cache path for a cluster's kubeconfig. */
export function kubeconfigCachePath(cluster: string): string {
  return join(KUBE_CACHE_DIR, `${cluster}.yaml`);
}

/**
 * Fetch the kubeconfig from the cluster's control node over SSH and cache it
 * locally (0600). Returns the local cache path. The remote kubeconfig is
 * rewritten server-side to point at the control node's reachable address.
 */
export async function fetchAndCacheKubeconfig(cluster: string): Promise<string> {
  const controlNode = await resolveControlNode(cluster);
  const lease = await machineConnections.acquire(controlNode);

  let contents = '';
  try {
    const remotePath = clusterKubeconfigRemotePath(cluster);
    const exitCode = await lease.sftp.execStreaming(`sudo cat ${remotePath}`, {
      onStdout: (data) => {
        contents += data;
      },
      onStderr: () => {},
    });
    if (exitCode !== 0 || !contents.trim()) {
      throw new Error(
        `Could not read kubeconfig from control node ${controlNode}:${remotePath}. Is the cluster installed?`
      );
    }
  } finally {
    lease.release();
  }

  await fs.mkdir(KUBE_CACHE_DIR, { recursive: true, mode: 0o700 });
  const localPath = kubeconfigCachePath(cluster);
  await fs.writeFile(localPath, contents, { mode: 0o600 });
  return localPath;
}
