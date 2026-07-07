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
  role?: 'server' | 'agent';
  version?: string;
  apiPort?: number;
  airgapBundle?: string;
  disableComponents?: string;
  token?: string;
  node?: string;
  namespace?: string;
  // kube namespace/PV lifecycle (wave 5a) parameters
  datastore?: string;
  pvc?: string;
  pvBackend?: string;
  backend?: string;
  srcPv?: string;
  dstNamespace?: string;
  pv?: string;
  cephPool?: string;
  cephCluster?: string;
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
