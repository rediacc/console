/**
 * Shared types for BridgeTestRunner and method classes.
 */

export interface ExecResult {
  stdout: string;
  stderr: string;
  code: number;
}

export interface TestFunctionOptions {
  function: string;
  datastorePath?: string;
  repository?: string;
  networkId?: string;
  password?: string;
  size?: string;
  newSize?: string;
  pool?: string;
  pgNum?: string;
  image?: string;
  snapshot?: string;
  clone?: string;
  mountPoint?: string;
  cowSize?: string;
  keepCow?: boolean;
  container?: string;
  command?: string;
  // repository_logs / repository_promote (runtime-generic verbs) parameters
  lines?: string;
  parent?: string;
  fork?: string;
  checkpointName?: string;
  sourceMachine?: string;
  destMachine?: string;
  format?: string;
  force?: boolean;
  timeout?: number;
  uid?: string;
  // Filesystem formatting parameters
  filesystem?: string;
  label?: string;
  // Ceph datastore fork/unfork parameters
  source?: string;
  cluster?: string;
  // backup_push parameters
  destinationType?: 'machine' | 'storage';
  to?: string;
  machines?: string[];
  storages?: string[];
  dest?: string;
  tag?: string;
  state?: 'online' | 'offline';
  checkpoint?: boolean;
  override?: boolean;
  grand?: string;
  // backup_pull parameters
  sourceType?: 'machine' | 'storage';
  from?: string;
  // Setup installation parameters (new vault param fixes)
  installSource?: 'apt-repo' | 'tar-static' | 'deb-local';
  dockerSource?: 'docker-repo' | 'package-manager' | 'snap' | 'manual';
  installAmdDriver?: 'auto' | 'true' | 'false';
  installNvidiaDriver?: 'auto' | 'true' | 'false';
  installCriu?: 'auto' | 'true' | 'false' | 'manual';
  // kube_registry_* (zot pull-through cache) parameters
  upstreams?: string;
  scope?: 'machine' | 'cluster';
  endpoint?: string;
  // kube_* (Kubernetes distribution lifecycle) parameters
  mountPath?: string;
  distro?: string;
  // kube_install/join node role (server|agent) OR the identity-rewrite fork-arm
  // effect-isolation role for the ROLE ConfigMap (fork|rehearsal).
  role?: 'server' | 'agent' | 'fork' | 'rehearsal';
  version?: string;
  apiPort?: number;
  airgapBundle?: string;
  registriesYaml?: string;
  disableComponents?: string;
  token?: string;
  node?: string;
  namespace?: string;
  // kube repo dispatch (runtime-generic repository_up kube arm) parameters
  datastore?: string;
  cephPool?: string;
  cephCluster?: string;
  // datastore_* (named datastore lifecycle: create/attach/detach/fork/snapshot) params
  name?: string;
  backend?: 'local' | 'ceph';
  writes?: 'local' | 'ceph';
  noAuto?: boolean;
  discard?: boolean;
  group?: string;
  /** datastore_snapshot_create: fork-path flush opt-in (default crash-consistent). */
  quiesce?: boolean;
  // kube_identity_rewrite / kube_prep_fork / kube_node_label (cluster fork/migrate) params
  operation?: 'fork' | 'migrate';
  mode?: 'server' | 'agent';
  newNodeIp?: string;
  newNetworkId?: string;
  bindIp?: string;
  keepThirdParty?: boolean;
  server?: string;
  removeLabel?: boolean;
  // repository_policy_set / repository_policy_get / repository_trim (size policy
  // + pool reclaim, renet#76). Tri-state booleans (auto_grow/auto_trim) are
  // ParamString on the renet side ("true"/"false"), so they carry a value.
  autoGrow?: boolean;
  maxQuota?: string;
  growThreshold?: string;
  growStep?: string;
  autoTrim?: boolean;
  trimInterval?: string;
  docker?: boolean;
  dockerVolumes?: boolean;
  reportOnly?: boolean;
}

/**
 * VM target types for test execution.
 * Tests execute on these VMs via two-hop SSH: Host → Bridge → Target
 */
export type VMTarget = string;

/**
 * Configuration for BridgeTestRunner.
 * targetVM is REQUIRED - no default execution target.
 */
export interface RunnerConfig {
  targetVM: VMTarget;
  timeout?: number;
}
