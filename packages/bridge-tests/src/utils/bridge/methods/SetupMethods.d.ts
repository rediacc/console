import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Machine setup and initialization methods for BridgeTestRunner.
 */
export declare class SetupMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    setup(datastorePath?: string, uid?: string): Promise<ExecResult>;
    osSetup(datastorePath?: string, uid?: string): Promise<ExecResult>;
    /**
     * Setup with all installation parameters.
     * Tests the 6 new installation params added for vault parameter fixes.
     */
    setupWithOptions(options: {
        datastorePath?: string;
        uid?: string;
        from?: 'apt-repo' | 'tar-static' | 'deb-local';
        dockerSource?: 'docker-repo' | 'package-manager' | 'snap' | 'manual';
        installAmdDriver?: 'auto' | 'true' | 'false';
        installNvidiaDriver?: 'auto' | 'true' | 'false';
        installCriu?: 'auto' | 'true' | 'false' | 'manual';
    }): Promise<ExecResult>;
    fixUserGroups(uid?: string): Promise<ExecResult>;
}
//# sourceMappingURL=SetupMethods.d.ts.map