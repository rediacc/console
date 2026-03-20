/**
 * Daemon management methods for BridgeTestRunner.
 */
export class DaemonMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async daemonSetup(networkId) {
        return this.testFunction({
            function: 'daemon_setup',
            networkId,
        });
    }
    async daemonTeardown(networkId) {
        return this.testFunction({
            function: 'daemon_teardown',
            networkId,
        });
    }
    async daemonStart(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'daemon_start',
            repository,
            datastorePath,
            networkId,
        });
    }
    async daemonStop(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'daemon_stop',
            repository,
            datastorePath,
            networkId,
        });
    }
    async daemonStatus(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'daemon_status',
            repository,
            datastorePath,
            networkId,
        });
    }
    async daemonRestart(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'daemon_restart',
            repository,
            datastorePath,
            networkId,
        });
    }
    async daemonLogs(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'daemon_logs',
            repository,
            datastorePath,
            networkId,
        });
    }
    async renetStart(networkId) {
        return this.testFunction({ function: 'daemon_start', networkId });
    }
    async renetStop(networkId) {
        return this.testFunction({ function: 'daemon_stop', networkId });
    }
    async renetStatus(networkId) {
        return this.testFunction({ function: 'daemon_status', networkId });
    }
}
//# sourceMappingURL=DaemonMethods.js.map
