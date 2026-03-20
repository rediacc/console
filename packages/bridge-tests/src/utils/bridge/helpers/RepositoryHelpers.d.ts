import type { ExecResult } from '../types';
/**
 * Repository-specific helper utilities for BridgeTestRunner.
 * Contains fork operations, file operations, and database helpers.
 */
export declare class RepositoryHelpers {
    private readonly executeViaBridge;
    constructor(executeViaBridge: (command: string, timeout?: number) => Promise<ExecResult>);
    /**
     * Write a file to a mounted repository.
     * Uses base64 encoding to safely handle special characters.
     * Uses sudo because repository mounts may have restricted permissions.
     *
     * Repository structure:
     * - Datastore: {datastorePath}
     * - Mounts: {datastorePath}/mounts/{repositoryName}  ← where content is accessible
     */
    writeFileToRepository(repositoryName: string, filePath: string, content: string, datastorePath: string): Promise<ExecResult>;
    /**
     * Check if a Docker container is running in a network-isolated docker daemon.
     * Uses sudo because Docker daemon access may require elevated privileges.
     * @param containerName The container name to check
     * @param networkId Network ID for network-isolated docker daemon (uses socket at /var/run/rediacc/docker-{networkId}.sock)
     */
    isContainerRunning(containerName: string, networkId: string): Promise<boolean>;
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
    createRepositoryFork(parentRepo: string, tag: string, datastorePath: string): Promise<ExecResult>;
    /**
     * Check if a repository exists in the datastore.
     * Repositories are LUKS image files, not directories.
     */
    repositoryExists(repositoryName: string, datastorePath: string): Promise<boolean>;
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
    waitForPostgresReady(containerName: string, networkId: string, maxAttempts?: number, intervalMs?: number): Promise<boolean>;
}
//# sourceMappingURL=RepositoryHelpers.d.ts.map