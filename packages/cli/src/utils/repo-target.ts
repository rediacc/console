/**
 * Repo-command target resolution (design D14): repo verbs are the single surface
 * for repo operations, targeting a machine (`-m`) or a cluster (`--cluster`).
 *
 * This is the thin per-command adapter over the wave-1 funnel
 * (resolveExecutionTarget): it enforces the mutually-exclusive one-of rule and
 * maps a cluster target to its control-node machine plus the `kubeCluster`
 * marker that local-executor threads into KUBECONFIG. Every cluster-capable
 * repo verb resolves through here and passes { machineName, kubeCluster } down
 * to executeRepoFunction / localExecutorService.execute.
 */
import { t } from '../i18n/index.js';
import { resolveExecutionTarget } from '../services/cluster/cluster-target.js';
import { ValidationError } from './errors.js';

export interface RepoTarget {
  /** Effective machine to SSH to — the cluster's control node for a cluster target. */
  machineName: string;
  /** Set when the target is a cluster; threaded into execute() to inject KUBECONFIG. */
  kubeCluster?: string;
}

/**
 * Resolve a repo command's `-m`/`--cluster` options to a concrete target.
 * Exactly one must be provided (resolveExecutionTarget throws otherwise).
 */
export async function resolveRepoTarget(options: {
  machine?: string;
  cluster?: string;
}): Promise<RepoTarget> {
  const target = await resolveExecutionTarget({
    machine: options.machine,
    cluster: options.cluster,
  });
  return { machineName: target.machineName, kubeCluster: target.cluster };
}

/**
 * Refuse a Docker-only verb when a `--cluster` target is given. takeover,
 * tunnel, and autostart have no Kubernetes equivalent in v1 (D14); refusing
 * early with a clear message beats a confusing downstream failure.
 */
export function assertDockerOnly(verb: string, options: { cluster?: string }): void {
  if (options.cluster) {
    throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb }));
  }
}
