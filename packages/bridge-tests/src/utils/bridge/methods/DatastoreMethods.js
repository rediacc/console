/**
 * Datastore management methods for BridgeTestRunner.
 */
export class DatastoreMethods {
    constructor(testFunction) {
        this.testFunction = testFunction;
    }
    async datastoreInit(size, datastorePath, force) {
        return this.testFunction({
            function: 'datastore_init',
            size,
            datastorePath,
            force,
        });
    }
    async datastoreMount(datastorePath) {
        return this.testFunction({
            function: 'datastore_mount',
            datastorePath,
        });
    }
    async datastoreUnmount(datastorePath) {
        return this.testFunction({
            function: 'datastore_unmount',
            datastorePath,
        });
    }
    async datastoreExpand(newSize, datastorePath) {
        return this.testFunction({
            function: 'datastore_expand',
            newSize,
            datastorePath,
        });
    }
    async datastoreResize(newSize, datastorePath) {
        return this.testFunction({
            function: 'datastore_resize',
            newSize,
            datastorePath,
        });
    }
    async datastoreValidate(datastorePath) {
        return this.testFunction({
            function: 'datastore_validate',
            datastorePath,
        });
    }
}
//# sourceMappingURL=DatastoreMethods.js.map