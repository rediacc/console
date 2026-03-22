import type { ExecResult } from '../types';
/**
 * SQL helper utilities for BridgeTestRunner.
 * Contains PostgreSQL-specific operations for fork testing.
 */
export declare class SqlHelpers {
    private readonly executeViaBridge;
    constructor(executeViaBridge: (command: string, timeout?: number) => Promise<ExecResult>);
    /**
     * Execute SQL on a PostgreSQL container using the network-isolated Docker socket.
     * Uses base64 encoding to safely pass SQL through multiple SSH hops.
     * @param containerName The container name (e.g., 'postgres-test-123')
     * @param sql SQL statement to execute
     * @param networkId Network ID for the docker socket
     * @returns Query result as string (trimmed output)
     */
    executeSql(containerName: string, sql: string, networkId: string): Promise<string>;
    /**
     * Insert a test record into the users table.
     * @param containerName PostgreSQL container name
     * @param username Unique username for the record
     * @param origin Repository origin identifier (e.g., 'parent-only', 'fork-only')
     * @param networkId Network ID for the docker socket
     */
    insertUserRecord(containerName: string, username: string, origin: string, networkId: string): Promise<void>;
    /**
     * Check if a record with the given origin exists in users table.
     * @returns true if at least one record exists with this origin
     */
    recordExistsByOrigin(containerName: string, origin: string, networkId: string): Promise<boolean>;
    /**
     * Get total record count in users table.
     */
    getUserRecordCount(containerName: string, networkId: string): Promise<number>;
    /**
     * Get MD5 hash of all users data for integrity verification.
     * Orders by id to ensure consistent hash across queries.
     */
    getUsersDataHash(containerName: string, networkId: string): Promise<string>;
    /**
     * Insert multiple test records for bulk data testing.
     * @param count Number of records to insert
     * @param origin Repository origin identifier
     */
    insertBulkUserRecords(containerName: string, count: number, origin: string, networkId: string): Promise<void>;
}
//# sourceMappingURL=SqlHelpers.d.ts.map
