/**
 * Shared types for BridgeTestRunner and method classes.
 */

export interface QueueTaskOptions {
  function: string;
  machine: string;
  team: string;
  priority?: number;
}

export interface QueueTaskResult {
  taskId: string;
}

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
  rcloneSource?: 'install-script' | 'package-manager' | 'manual';
  dockerSource?: 'docker-repo' | 'package-manager' | 'snap' | 'manual';
  installAmdDriver?: 'auto' | 'true' | 'false';
  installNvidiaDriver?: 'auto' | 'true' | 'false';
  installCriu?: 'auto' | 'true' | 'false' | 'manual';
  // Repository prep-only option
  prepOnly?: boolean;
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
