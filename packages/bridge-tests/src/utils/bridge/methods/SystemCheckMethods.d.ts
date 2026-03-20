import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * System check and verification methods for BridgeTestRunner.
 * Contains methods for testing machine health, compatibility, and setup status.
 */
export declare class SystemCheckMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    ping(): Promise<ExecResult>;
    nop(): Promise<ExecResult>;
    hello(): Promise<ExecResult>;
    sshTest(): Promise<ExecResult>;
    checkKernelCompatibility(): Promise<ExecResult>;
    checkSetup(): Promise<ExecResult>;
    checkMemory(): Promise<ExecResult>;
    checkSudo(): Promise<ExecResult>;
    checkTools(): Promise<ExecResult>;
    checkRenet(): Promise<ExecResult>;
    checkCriu(): Promise<ExecResult>;
    checkBtrfs(): Promise<ExecResult>;
    checkDrivers(): Promise<ExecResult>;
    checkSystem(): Promise<ExecResult>;
    checkUsers(): Promise<ExecResult>;
    checkRediaccCli(): Promise<ExecResult>;
    checkDatastore(datastorePath?: string): Promise<ExecResult>;
}
//# sourceMappingURL=SystemCheckMethods.d.ts.map
