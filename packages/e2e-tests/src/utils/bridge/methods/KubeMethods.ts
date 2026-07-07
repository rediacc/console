import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Kubernetes distribution lifecycle methods for BridgeTestRunner.
 *
 * These dispatch the `kube_*` bridge functions by literal name, so the
 * e2e-coverage gate (which greps bridge-tests for each generated function name)
 * sees them once the lead regenerates the renet contract. Suite 15 (`E2E K8s`,
 * env-gated on K8S_MODE, wave 5+) exercises them against a live k3s-on-a-worker
 * VM:
 *   - kube_install / kube_uninstall / kube_upgrade: node lifecycle
 *   - kube_join_token / kube_join: multi-node join
 *   - kube_node_remove: drain + delete a node
 *   - kube_kubeconfig / kube_health: read-only access (public functions)
 */
export interface KubeInstallOptions {
  mountPath: string;
  networkId?: string;
  distro?: string;
  role?: 'server' | 'agent';
  version?: string;
  apiPort?: number;
  airgapBundle?: string;
  disableComponents?: string;
}

export interface KubeJoinOptions {
  mountPath: string;
  networkId?: string;
  role?: 'server' | 'agent';
  token: string;
  endpoint: string;
}

export interface KubeNodeRemoveOptions {
  mountPath: string;
  networkId?: string;
  node: string;
}

export interface KubeTargetOptions {
  mountPath: string;
  networkId?: string;
}

export interface KubeUpgradeOptions extends KubeTargetOptions {
  version?: string;
}

export interface KubeNamespaceOptions {
  mountPath: string;
  namespace: string;
  networkId?: string;
  cluster?: string;
  datastore?: string;
  /** Ceph RBD pool: routes PVCs to ceph-csi (empty = local datastore backend). */
  cephPool?: string;
  /** Ceph cluster name for the ceph/rbd CLI (default: ceph). */
  cephCluster?: string;
}

export interface KubeNamespaceForkOptions extends KubeNamespaceOptions {
  tag: string;
  pvBackend?: string;
}

export interface KubePVProvisionOptions {
  datastore: string;
  cluster: string;
  namespace: string;
  pvc: string;
  size: string;
  backend?: string;
}

export interface KubePVCloneOptions {
  datastore: string;
  cluster: string;
  srcPv: string;
  dstNamespace: string;
}

export class KubeMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  /** Install a k3s server or agent node (kube_install). */
  async kubeInstall(opts: KubeInstallOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_install',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      distro: opts.distro,
      role: opts.role,
      version: opts.version,
      apiPort: opts.apiPort,
      airgapBundle: opts.airgapBundle,
      disableComponents: opts.disableComponents,
    });
  }

  /** Print the token new nodes present to join (kube_join_token). */
  async kubeJoinToken(opts: KubeTargetOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_join_token',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
    });
  }

  /** Join this machine to an existing control plane (kube_join). */
  async kubeJoin(opts: KubeJoinOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_join',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      role: opts.role,
      token: opts.token,
      endpoint: opts.endpoint,
    });
  }

  /** Drain and remove a node (kube_node_remove). */
  async kubeNodeRemove(opts: KubeNodeRemoveOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_node_remove',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      node: opts.node,
    });
  }

  /** Re-extract the embedded k3s binary and restart (kube_upgrade). */
  async kubeUpgrade(opts: KubeUpgradeOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_upgrade',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      version: opts.version,
    });
  }

  /** Stop and remove the k3s node on this machine (kube_uninstall). */
  async kubeUninstall(opts: KubeTargetOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_uninstall',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
    });
  }

  /** Print a reachable kubeconfig (kube_kubeconfig). */
  async kubeKubeconfig(opts: KubeTargetOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_kubeconfig',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
    });
  }

  /** Check whether the API server is ready (kube_health). */
  async kubeHealth(opts: KubeTargetOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_health',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
    });
  }

  /** Create a repo namespace (kube_namespace_create). */
  async kubeNamespaceCreate(opts: KubeNamespaceOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_namespace_create',
      mountPath: opts.mountPath,
      namespace: opts.namespace,
      networkId: opts.networkId,
      cluster: opts.cluster,
      datastore: opts.datastore,
      cephPool: opts.cephPool,
      cephCluster: opts.cephCluster,
    });
  }

  /** Re-apply the persisted manifest for a namespace (kube_deploy). */
  async kubeDeploy(opts: KubeNamespaceOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_deploy',
      mountPath: opts.mountPath,
      namespace: opts.namespace,
      networkId: opts.networkId,
      cluster: opts.cluster,
      datastore: opts.datastore,
      cephPool: opts.cephPool,
      cephCluster: opts.cephCluster,
    });
  }

  /** Fork a namespace, CoW-cloning its PVs (kube_namespace_fork). */
  async kubeNamespaceFork(opts: KubeNamespaceForkOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_namespace_fork',
      mountPath: opts.mountPath,
      namespace: opts.namespace,
      tag: opts.tag,
      pvBackend: opts.pvBackend,
      networkId: opts.networkId,
      cluster: opts.cluster,
      datastore: opts.datastore,
      cephPool: opts.cephPool,
      cephCluster: opts.cephCluster,
    });
  }

  /** Delete a namespace and its local PV images (kube_namespace_delete). */
  async kubeNamespaceDelete(opts: KubeNamespaceOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_namespace_delete',
      mountPath: opts.mountPath,
      namespace: opts.namespace,
      networkId: opts.networkId,
      cluster: opts.cluster,
      datastore: opts.datastore,
    });
  }

  /** Provision a datastore-backed PV image (kube_pv_provision). */
  async kubePvProvision(opts: KubePVProvisionOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_pv_provision',
      datastore: opts.datastore,
      cluster: opts.cluster,
      namespace: opts.namespace,
      pvc: opts.pvc,
      size: opts.size,
      backend: opts.backend,
    });
  }

  /** Reflink-clone a PV image into a namespace (kube_pv_clone). */
  async kubePvClone(opts: KubePVCloneOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_pv_clone',
      datastore: opts.datastore,
      cluster: opts.cluster,
      srcPv: opts.srcPv,
      dstNamespace: opts.dstNamespace,
    });
  }

  /** Delete a PV image (kube_pv_delete). */
  async kubePvDelete(pv: string): Promise<ExecResult> {
    return this.testFunction({ function: 'kube_pv_delete', pv });
  }
}
