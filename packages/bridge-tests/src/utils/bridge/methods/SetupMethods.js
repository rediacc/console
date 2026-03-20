/**
 * Machine setup and initialization methods for BridgeTestRunner.
 */
export class SetupMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async setup(datastorePath, uid) {
        return this.testFunction({
            function: 'setup',
            datastorePath,
            uid,
        });
    }
    async osSetup(datastorePath, uid) {
        // os_setup is now an alias for setup
        return this.testFunction({
            function: 'setup',
            datastorePath,
            uid,
        });
    }
    /**
     * Setup with all installation parameters.
     * Tests the 6 new installation params added for vault parameter fixes.
     */
    async setupWithOptions(options) {
        return this.testFunction({
            function: 'setup',
            datastorePath: options.datastorePath,
            uid: options.uid,
            installSource: options.from,
            dockerSource: options.dockerSource,
            installAmdDriver: options.installAmdDriver,
            installNvidiaDriver: options.installNvidiaDriver,
            installCriu: options.installCriu,
        });
    }
    async fixUserGroups(uid) {
        return this.testFunction({
            function: 'machine_fix_groups',
            uid,
        });
    }
}
//# sourceMappingURL=SetupMethods.js.map