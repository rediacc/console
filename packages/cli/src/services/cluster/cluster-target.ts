/**
 * Execution-target resolution for the repo-command funnel.
 *
 * Repo verbs stay the single surface for repo operations (design D14): the same
 * command targets a machine (`-m`) or a cluster (`--cluster`). This resolver is
 * the one place that maps a cluster target to its control-node machine plus the
 * KUBECONFIG context, so ~35 SSH-exec repo commands become cluster-capable
 * without per-command rewrites. Wave 1 builds the funnel; the repo commands wire
 * their `--cluster` flag into it in wave 5.
 */

import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { resolveControlNode } from '../config/config-cluster-ops.js';
import { controlDatastoreMount, NAMED_DS_BASE } from './cluster-kube.js';

/**
 * Remote mount path of a NAMED datastore on the machine that attaches it —
 * `/mnt/rediacc-ds/<datastore>` (spec 02 §1). This is where a repo placed on a
 * named datastore lives (`repo create --datastore <d>`, the R2-F1 placement
 * union), whether it is a docker-tiering datastore or the k8s data datastore a
 * cluster repo is forked from (the #38 fix: a cluster repo lands on its DATA
 * datastore, not the control datastore replicate excludes).
 */
export function namedDatastoreMount(datastore: string): string {
  return `${NAMED_DS_BASE}/${datastore}`;
}

export interface ExecutionTarget {
  /** Effective machine to SSH to — the control node when the target is a cluster. */
  machineName: string;
  /** Set when the target is a cluster. */
  cluster?: string;
  /** Remote KUBECONFIG path on the control node when the target is a cluster. */
  kubeconfig?: string;
}

/**
 * Remote mount path of a cluster's k3s image on its control node — the
 * `--mount-path` the `renet kube namespace/pv` verbs consume (they cannot rely
 * on the injected KUBECONFIG env because the bridge runs them under `sudo`,
 * which strips it, so the mount path travels as an explicit param). The
 * single-node cluster's state lives under mounts/<cluster>, matching the
 * router's kubeconfig glob (mounts/&#42;/.rediacc/k3s/kubeconfig.yaml).
 */
/**
 * Remote path of a cluster's kubeconfig on its control node. Under the
 * datastore-centric model the control-plane data-dir lives INSIDE the anchor
 * control datastore (`ds-control-<cluster>`), so the k3s distro backend writes
 * the kubeconfig at
 * `/mnt/rediacc-ds/ds-control-<cluster>/.rediacc/k3s/kubeconfig.yaml` — NOT the
 * legacy per-node repo mount `/mnt/rediacc/mounts/<cluster>/…` (that mount is
 * the disposable agent image, which never holds the CP kubeconfig). Deriving it
 * from the control-datastore mount is the P3-w7 fix for finding #11: reading the
 * stale path made `rdc cluster kubeconfig` (and `term`/`vscode connect
 * --cluster`) report "Is the cluster installed?" on a healthy cluster.
 *
 * This is the exact file `term`/`vscode connect --cluster` export as KUBECONFIG
 * (the user's kubectl reads it directly) and that `rdc cluster kubeconfig`
 * `sudo cat`s to seed the local cache, so it MUST match the on-disk layout.
 */
export function clusterKubeconfigRemotePath(cluster: string): string {
  return `${controlDatastoreMount(cluster)}/.rediacc/k3s/kubeconfig.yaml`;
}

/**
 * Attach a cluster's interactive-session context to a resolved SSH connection
 * (design D14, decision 10). This is the k8s analog of the docker-repo
 * DOCKER_HOST + working-directory injection: it exports the control node's
 * remote KUBECONFIG path (same path the repo-verb funnel threads via
 * local-executor's buildRenetEnvPrefix) so `kubectl` is ready in the session,
 * and — when a repo is given — records the namespace to pin the kubectl
 * current-context to. A k8s repo IS namespace `<repo>` (kube_namespace_create),
 * so the `-r` value maps 1:1 to the namespace. v1 is the control-node view; a
 * `--node` selector is a documented later follow-up.
 *
 * Mutates `details` in place so both `term connect` and `vscode connect` share
 * one implementation. The structural parameter type avoids importing the
 * ConnectionDetails shape from the machine layer.
 */
export function applyClusterConnectionContext(
  details: { environment?: Record<string, string>; kubeNamespace?: string },
  cluster: string,
  repository?: string
): void {
  details.environment = {
    ...(details.environment ?? {}),
    KUBECONFIG: clusterKubeconfigRemotePath(cluster),
  };
  if (repository) {
    details.kubeNamespace = repository;
  }
}

/**
 * Resolve `{ machine?, cluster? }` to a concrete execution target. Exactly one
 * of machine/cluster must be provided. A cluster resolves to its control node
 * plus a KUBECONFIG path; a machine resolves to itself.
 */
export async function resolveExecutionTarget(opts: {
  machine?: string;
  cluster?: string;
}): Promise<ExecutionTarget> {
  const hasMachine = Boolean(opts.machine);
  const hasCluster = Boolean(opts.cluster);

  if (hasMachine && hasCluster) {
    throw new ValidationError(t('errors.cluster.targetExclusive'));
  }
  if (!hasMachine && !hasCluster) {
    throw new ValidationError(t('errors.cluster.targetRequired'));
  }

  if (hasCluster) {
    const cluster = opts.cluster as string;
    const machineName = await resolveControlNode(cluster);
    return { machineName, cluster, kubeconfig: clusterKubeconfigRemotePath(cluster) };
  }

  return { machineName: opts.machine as string };
}
