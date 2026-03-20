/**
 * Container management methods for BridgeTestRunner.
 */
export class ContainerMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async containerStart(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_start',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerStop(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_stop',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerRestart(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_restart',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerLogs(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_logs',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerExec(name, command, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_exec',
            container: name,
            command,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerInspect(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_inspect',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerStats(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_stats',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerList(repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_list',
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerKill(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_kill',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerPause(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_pause',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
    async containerUnpause(name, repository, datastorePath, networkId) {
        return this.testFunction({
            function: 'container_unpause',
            container: name,
            repository,
            datastorePath,
            networkId,
        });
    }
}
//# sourceMappingURL=ContainerMethods.js.map