/**
 * Repository-specific helper utilities for BridgeTestRunner.
 * Contains fork operations, file operations, and database helpers.
 */
export class RepositoryHelpers {
    constructor(executeViaBridge) {
        this.executeViaBridge = executeViaBridge;
    }
    /**
     * Write a file to a mounted repository.
     * Uses base64 encoding to safely handle special characters.
     * Uses sudo because repository mounts may have restricted permissions.
     *
     * Repository structure:
     * - Datastore: {datastorePath}
     * - Mounts: {datastorePath}/mounts/{repositoryName}  ← where content is accessible
     */
    async writeFileToRepository(repositoryName, filePath, content, datastorePath) {
        const base64Content = Buffer.from(content).toString('base64');
        // Repository content is at {datastore}/mounts/{repositoryName}
        const mountPath = `${datastorePath}/mounts/${repositoryName}`;
        const fullPath = `${mountPath}/${filePath}`;
        return this.executeViaBridge(`sudo mkdir -p "$(dirname ${fullPath})" && echo "${base64Content}" | base64 -d | sudo tee ${fullPath} > /dev/null`);
    }
    /**
     * Check if a Docker container is running in a network-isolated docker daemon.
     * Uses sudo because Docker daemon access may require elevated privileges.
     * @param containerName The container name to check
     * @param networkId Network ID for network-isolated docker daemon (uses socket at /var/run/rediacc/docker-{networkId}.sock)
     */
    async isContainerRunning(containerName, networkId) {
        const CONTAINER_RUNNING_MARKER = 'running';
        const result = await this.executeViaBridge(`sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock ps --filter "name=^${containerName}$" --format "{{.Names}}" | grep -q "^${containerName}$" && echo "${CONTAINER_RUNNING_MARKER}" || echo "stopped"`);
        return result.stdout.trim() === CONTAINER_RUNNING_MARKER;
    }
    /**
     * Create a fork of a repository by copying its LUKS image file.
     * This uses the renet repository fork command for proper CoW forking.
     *
     * IMPORTANT: Parent repository MUST be unmounted before forking.
     *
     * Repository structure: ${datastorePath}/repositories/${repositoryName}
     * Each repository is a single LUKS-encrypted image file (not a directory).
     *
     * @param parentRepo Name of the parent repository
     * @param tag Fork tag/name (cannot be 'latest')
     * @param datastorePath Path to the datastore
     */
    async createRepositoryFork(parentRepo, tag, datastorePath) {
        // Use renet repository fork command for proper CoW forking
        return this.executeViaBridge(`sudo renet repository fork --name "${parentRepo}" --tag "${tag}" --datastore "${datastorePath}"`);
    }
    /** Freeze a working fork into a new immutable commit (issue #75 Phase 2). */
    async repositoryCommit(workingFork, commitGuid, message, datastorePath, commitParent) {
        const parentFlag = commitParent ? ` --commit-parent "${commitParent}"` : '';
        return this.executeViaBridge(`sudo renet repository commit --name "${workingFork}" --tag "${commitGuid}" --message "${message}" --datastore "${datastorePath}"${parentFlag}`);
    }
    /** Check a commit out into a fresh writable working fork (reflink fork of the commit). */
    async repositoryCheckout(commitGuid, tag, datastorePath) {
        return this.createRepositoryFork(commitGuid, tag, datastorePath);
    }
    /** Walk the commit history reachable from a working fork or commit. */
    async repositoryLog(startGuid, datastorePath) {
        return this.executeViaBridge(`sudo renet repository log --name "${startGuid}" --datastore "${datastorePath}" -o json`);
    }
    /**
     * Lifecycle-safe merge. Without `resolve` it is a whole-image take-theirs; with
     * `resolve` (+ `base`) it is a per-file three-way merge, which mounts the lineage
     * and needs the repo `password` (piped via --password-stdin).
     */
    async repositoryMerge(target, source, datastorePath, opts = {}) {
        let cmd = `sudo renet repository merge --name "${target}" --from "${source}" --datastore "${datastorePath}"`;
        if (opts.force)
            cmd += ' --force';
        if (opts.resolve)
            cmd += ` --resolve ${opts.resolve}`;
        if (opts.base)
            cmd += ` --base "${opts.base}"`;
        if (opts.password) {
            cmd += ' --password-stdin';
            return this.executeViaBridge(`printf '%s' '${opts.password}' | ${cmd}`);
        }
        return this.executeViaBridge(cmd);
    }
    /** Create an immutable (read-only) fork — the commit-equivalent base; refuses to mount. */
    async repositoryForkImmutable(parentRepo, tag, datastorePath) {
        return this.executeViaBridge(`sudo renet repository fork --name "${parentRepo}" --tag "${tag}" --datastore "${datastorePath}" --immutable`);
    }
    /**
     * Deterministic CoW-delta push from THIS worker to another machine. --dest-user
     * omitted → renet infers it from SUDO_USER. retainBase retains a base on both
     * ends; deltaBase ships only the changed extents.
     */
    async deltaPushToMachine(repoGuid, destHost, datastorePath, opts = {}) {
        let cmd = `sudo renet backup push --name "${repoGuid}" --datastore "${datastorePath}"` +
            ` --target machine --dest-host "${destHost}"` +
            ` --dest-path "${datastorePath}" --dest "${repoGuid}" --strategy physical`;
        if (opts.destUser)
            cmd += ` --dest-user "${opts.destUser}"`;
        if (opts.deltaBase)
            cmd += ` --delta-base "${opts.deltaBase}"`;
        if (opts.retainBase)
            cmd += ` --retain-base "${opts.retainBase}"`;
        return this.executeViaBridge(cmd);
    }
    /** Deterministic CoW-delta pull from another machine onto THIS worker. */
    async deltaPullFromMachine(repoGuid, srcHost, datastorePath, opts = {}) {
        let cmd = `sudo renet backup pull --name "${repoGuid}" --datastore "${datastorePath}"` +
            ` --source machine --src-host "${srcHost}"` +
            ` --src-path "${datastorePath}" --src "${repoGuid}" --strategy physical`;
        if (opts.srcUser)
            cmd += ` --src-user "${opts.srcUser}"`;
        if (opts.deltaBase)
            cmd += ` --delta-base "${opts.deltaBase}"`;
        if (opts.force)
            cmd += ' --force';
        return this.executeViaBridge(cmd);
    }
    /** sha256 of a repository image file (for byte-identity assertions). */
    async repositoryImageSha256(repoGuid, datastorePath) {
        return this.executeViaBridge(`sudo sha256sum "${datastorePath}/repositories/${repoGuid}" | cut -d' ' -f1`);
    }
    /**
     * Check if a repository exists in the datastore.
     * Repositories are LUKS image files, not directories.
     */
    async repositoryExists(repositoryName, datastorePath) {
        const REPO_EXISTS_MARKER = 'exists';
        const result = await this.executeViaBridge(`test -f "${datastorePath}/repositories/${repositoryName}" && echo "${REPO_EXISTS_MARKER}" || echo "not_found"`);
        return result.stdout.trim() === REPO_EXISTS_MARKER;
    }
    /**
     * Wait for PostgreSQL container to be ready to accept connections.
     * Uses an actual query (SELECT 1) to verify database is fully operational,
     * not just pg_isready which only checks if socket accepts connections.
     *
     * @param containerName PostgreSQL container name
     * @param networkId Network ID for the docker socket
     * @param maxAttempts Maximum number of attempts (default: 30)
     * @param intervalMs Interval between attempts in ms (default: 1000)
     * @returns true if PostgreSQL is ready, false if timed out
     */
    async waitForPostgresReady(containerName, networkId, maxAttempts = 30, intervalMs = 1000) {
        for (let i = 0; i < maxAttempts; i++) {
            // Use actual query instead of pg_isready - this verifies the database
            // is fully operational, not just that the socket accepts connections.
            // This avoids race conditions where pg_isready passes but init scripts
            // are still running or the database is restarting.
            const result = await this.executeViaBridge(`sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock exec ${containerName} psql -U postgres -d testdb -c "SELECT 1" -t -q 2>/dev/null`);
            if (result.code === 0) {
                // eslint-disable-next-line no-console
                console.log(`[PostgreSQL] Container ${containerName} is ready after ${i + 1} attempts`);
                return true;
            }
            // eslint-disable-next-line no-console
            console.log(`[PostgreSQL] Waiting for ${containerName}... (${i + 1}/${maxAttempts})`);
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
        // eslint-disable-next-line no-console
        console.log(`[PostgreSQL] Container ${containerName} failed to be ready after ${maxAttempts} attempts`);
        return false;
    }
}
//# sourceMappingURL=RepositoryHelpers.js.map
