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
    filesystem?: string;
    label?: string;
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
    sourceType?: 'machine' | 'storage';
    from?: string;
    installSource?: 'apt-repo' | 'tar-static' | 'deb-local';
    dockerSource?: 'docker-repo' | 'package-manager' | 'snap' | 'manual';
    installAmdDriver?: 'auto' | 'true' | 'false';
    installNvidiaDriver?: 'auto' | 'true' | 'false';
    installCriu?: 'auto' | 'true' | 'false' | 'manual';
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
//# sourceMappingURL=types.d.ts.map
