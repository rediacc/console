import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Repository management methods for BridgeTestRunner.
 */
export declare class RepositoryMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    repositoryNew(name: string, size: string, password?: string, datastorePath?: string): Promise<ExecResult>;
    repositoryRm(name: string, datastorePath?: string): Promise<ExecResult>;
    repositoryMount(name: string, password?: string, datastorePath?: string): Promise<ExecResult>;
    repositoryUnmount(name: string, datastorePath?: string): Promise<ExecResult>;
    repositoryUp(name: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    repositoryDown(name: string, datastorePath?: string, networkId?: string): Promise<ExecResult>;
    repositoryList(datastorePath?: string): Promise<ExecResult>;
    repositoryResize(name: string, newSize: string, password?: string, datastorePath?: string): Promise<ExecResult>;
    repositoryInfo(name: string, datastorePath?: string): Promise<ExecResult>;
    repositoryStatus(name: string, datastorePath?: string): Promise<ExecResult>;
    repositoryValidate(name: string, datastorePath?: string): Promise<ExecResult>;
    repositoryGrow(name: string, newSize: string, password?: string, datastorePath?: string): Promise<ExecResult>;
}
//# sourceMappingURL=RepositoryMethods.d.ts.map
