import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Kubernetes distribution lifecycle methods for BridgeTestRunner.
 *
 * These dispatch the `kube_*` bridge functions by literal name. The kube suites
 * (15/16/17, env-gated on K8S_MODE) exercise them against live k3s-on-a-worker
 * VMs on the datastore-cluster model:
 *   - kube_install / kube_uninstall / kube_upgrade: node lifecycle
 *   - kube_join_token / kube_join: multi-node join (real-NIC bind for a cluster)
 *   - kube_node_remove / kube_node_label: node membership + local-PV topology label
 *   - kube_kubeconfig / kube_health: read-only access (public functions)
 *   - kube_prep_fork / kube_identity_rewrite: the whole-cluster fork/migrate
 *     primitives (drain + F1-F8 PKI re-mint; operation=fork re-mints the CA and
 *     scrubs secrets, operation=migrate preserves the CA).
 *
 * The per-namespace kube model (kube_namespace_x / kube_pv_x / kube_deploy) is
 * DELETED — the datastore-cluster redesign routes kube repo lifecycle through
 * the runtime-generic `repository_up`/`down`/`status` verbs (RepositoryMethods)
 * dispatched by the repo's datastore placement.
 */
export interface KubeInstallOptions {
  mountPath: string;
  networkId?: string;
  distro?: string;
  role?: 'server' | 'agent';
  version?: string;
  apiPort?: number;
  airgapBundle?: string;
  /** registries.yaml so k3s gets --private-registry (a wired zot is bypassed without it). */
  registriesYaml?: string;
  disableComponents?: string;
  /** Real private NIC to bind/advertise on (multi-node cluster); default: dummy IP. */
  bindIp?: string;
}

export interface KubeJoinOptions {
  mountPath: string;
  networkId?: string;
  role?: 'server' | 'agent';
  token: string;
  endpoint: string;
  /** Real private NIC to bind/advertise on (multi-node cluster). */
  bindIp?: string;
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

export interface KubePrepForkOptions {
  mountPath: string;
  networkId?: string;
  /** Node name to drain (empty = skip drain, just stop + sweep). */
  node?: string;
}

export interface KubeIdentityRewriteOptions {
  mountPath: string;
  networkId?: string;
  /** REQUIRED: fork re-mints the CA + scrubs secrets + ROLE=fork; migrate preserves the CA. */
  operation: 'fork' | 'migrate';
  mode?: 'server' | 'agent';
  newNodeIp?: string;
  /** Retag the image to a new networkID (fork case; omit = keep). */
  newNetworkId?: string;
  /** Fork arm: repo effect-isolation role for the ROLE ConfigMap. */
  role?: 'fork' | 'rehearsal';
  /** Fork arm: fork-attach write disposition (local|ceph) for the ROLE ConfigMap. */
  writes?: 'local' | 'ceph';
  /** Fork arm: skip the scrub-all of third-party Secrets (re-opens F2). */
  keepThirdParty?: boolean;
  /** Agent mode: new control-plane URL (https://ip:port). */
  server?: string;
  /** Agent mode: CA-derived join token to reuse. */
  token?: string;
}

export interface KubeNodeLabelOptions {
  mountPath: string;
  networkId?: string;
  /** Node name to (un)label. */
  node?: string;
  /** Resolve the node by its InternalIP (alternative to node). */
  newNodeIp?: string;
  /** Datastore name; stamps rediacc.io/ds-<name>=true (local-PV topology). */
  datastore?: string;
  /** Remove the label instead of adding it. */
  remove?: boolean;
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
      registriesYaml: opts.registriesYaml,
      disableComponents: opts.disableComponents,
      bindIp: opts.bindIp,
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
      bindIp: opts.bindIp,
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

  /**
   * Install the package prerequisites (ceph-common/rbd + sqlite3) a bare machine
   * needs to host a whole-cluster fork of a DIFFERENT cluster (kube_fork_dest_prep).
   * Takes no params — it installs the fixed fork-dest package set.
   */
  async kubeForkDestPrep(): Promise<ExecResult> {
    return this.testFunction({ function: 'kube_fork_dest_prep' });
  }

  /** Drain + stop a node so its image is fork/migrate-consistent (kube_prep_fork). */
  async kubePrepFork(opts: KubePrepForkOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_prep_fork',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      node: opts.node,
    });
  }

  /**
   * Rewrite a forked/migrated node's identity (kube_identity_rewrite):
   * operation=fork runs the F1-F8 PKI re-mint (fresh CA) + secret scrub + ROLE
   * rewrite; operation=migrate preserves the CA and regenerates only the leaf.
   */
  async kubeIdentityRewrite(opts: KubeIdentityRewriteOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_identity_rewrite',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      operation: opts.operation,
      mode: opts.mode,
      newNodeIp: opts.newNodeIp,
      newNetworkId: opts.newNetworkId,
      role: opts.role,
      writes: opts.writes,
      keepThirdParty: opts.keepThirdParty,
      server: opts.server,
      token: opts.token,
    });
  }

  /**
   * Add/remove the rediacc.io/ds-<datastore>=true node label (kube_node_label)
   * so local-PV pods on a cluster-attached datastore schedule (carry-in 1: not
   * yet auto-wired at attach time, so the suites invoke the primitive).
   */
  async kubeNodeLabel(opts: KubeNodeLabelOptions): Promise<ExecResult> {
    return this.testFunction({
      function: 'kube_node_label',
      mountPath: opts.mountPath,
      networkId: opts.networkId,
      node: opts.node,
      newNodeIp: opts.newNodeIp,
      datastore: opts.datastore,
      removeLabel: opts.remove,
    });
  }
}
