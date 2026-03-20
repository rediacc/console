import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Daemon management methods for BridgeTestRunner.
 */
export declare class DaemonMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    daemonSetup(networkId?: string): Promise<ExecResult>;
    daemonTeardown(networkId?: string): Promise<ExecResult>;
    daemonStart(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    daemonStop(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    daemonStatus(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    daemonRestart(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    daemonLogs(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    renetStart(networkId?: string): Promise<ExecResult>;
    renetStop(networkId?: string): Promise<ExecResult>;
    renetStatus(networkId?: string): Promise<ExecResult>;
}
//# sourceMappingURL=DaemonMethods.d.ts.map
