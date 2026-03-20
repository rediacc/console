import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Datastore management methods for BridgeTestRunner.
 */
export declare class DatastoreMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    datastoreInit(size: string, datastorePath?: string, force?: boolean): Promise<ExecResult>;
    datastoreMount(datastorePath?: string): Promise<ExecResult>;
    datastoreUnmount(datastorePath?: string): Promise<ExecResult>;
    datastoreExpand(newSize: string, datastorePath?: string): Promise<ExecResult>;
    datastoreResize(newSize: string, datastorePath?: string): Promise<ExecResult>;
    datastoreValidate(datastorePath?: string): Promise<ExecResult>;
}
//# sourceMappingURL=DatastoreMethods.d.ts.map