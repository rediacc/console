/**
 * Repository management methods for BridgeTestRunner.
 */
export class RepositoryMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async repositoryNew(name, size, password, datastorePath) {
        return this.testFunction({
            function: 'repository_create',
            repository: name,
            size,
            password,
            datastorePath,
        });
    }
    async repositoryRm(name, datastorePath) {
        return this.testFunction({
            function: 'repository_delete',
            repository: name,
            datastorePath,
        });
    }
    async repositoryMount(name, password, datastorePath) {
        return this.testFunction({
            function: 'repository_mount',
            repository: name,
            password,
            datastorePath,
        });
    }
    async repositoryUnmount(name, datastorePath) {
        return this.testFunction({
            function: 'repository_unmount',
            repository: name,
            datastorePath,
        });
    }
    async repositoryUp(name, datastorePath, networkId) {
        return this.testFunction({
            function: 'repository_up',
            repository: name,
            datastorePath,
            networkId,
        });
    }
    async repositoryDown(name, datastorePath, networkId) {
        return this.testFunction({
            function: 'repository_down',
            repository: name,
            datastorePath,
            networkId,
        });
    }
    async repositoryList(datastorePath) {
        return this.testFunction({
            function: 'repository_list',
            datastorePath,
        });
    }
    async repositoryResize(name, newSize, password, datastorePath) {
        return this.testFunction({
            function: 'repository_resize',
            repository: name,
            newSize,
            password,
            datastorePath,
        });
    }
    async repositoryInfo(name, datastorePath) {
        return this.testFunction({
            function: 'repository_info',
            repository: name,
            datastorePath,
        });
    }
    async repositoryStatus(name, datastorePath) {
        return this.testFunction({
            function: 'repository_status',
            repository: name,
            datastorePath,
        });
    }
    async repositoryValidate(name, datastorePath) {
        return this.testFunction({
            function: 'repository_validate',
            repository: name,
            datastorePath,
        });
    }
    async repositoryGrow(name, newSize, password, datastorePath) {
        return this.testFunction({
            function: 'repository_expand',
            repository: name,
            newSize,
            password,
            datastorePath,
        });
    }
}
//# sourceMappingURL=RepositoryMethods.js.map
