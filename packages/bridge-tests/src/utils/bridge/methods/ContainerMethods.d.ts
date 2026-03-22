import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Container management methods for BridgeTestRunner.
 */
export declare class ContainerMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    containerStart(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerStop(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerRestart(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerLogs(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerExec(name: string, command: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerInspect(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerStats(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerList(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerKill(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerPause(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    containerUnpause(name: string, repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
}
//# sourceMappingURL=ContainerMethods.d.ts.map
