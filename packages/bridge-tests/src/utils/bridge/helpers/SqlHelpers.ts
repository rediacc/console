import type { ExecResult } from '../types';

/**
 * SQL helper utilities for BridgeTestRunner.
 * Contains PostgreSQL-specific operations for fork testing.
 */
export class SqlHelpers {
  constructor(
    private readonly executeViaBridge: (command: string, timeout?: number) => Promise<ExecResult>
  ) {}

  /**
   * Execute SQL on a PostgreSQL container using the network-isolated Docker socket.
   * Uses base64 encoding to safely pass SQL through multiple SSH hops.
   * @param containerName The container name (e.g., 'postgres-test-123')
   * @param sql SQL statement to execute
   * @param networkId Network ID for the docker socket
   * @returns Query result as string (trimmed output)
   */
  async executeSql(containerName: string, sql: string, networkId: string): Promise<string> {
    // Use base64 encoding to safely pass SQL through multiple SSH hops
    const base64Sql = Buffer.from(sql).toString('base64');
    const result = await this.executeViaBridge(
      `echo "${base64Sql}" | base64 -d | sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock exec -i ${containerName} psql -U postgres -d testdb -t`
    );
    return result.stdout.trim();
  }

  /**
   * Insert a test record into the users table.
   * @param containerName PostgreSQL container name
   * @param username Unique username for the record
   * @param origin Repository origin identifier (e.g., 'parent-only', 'fork-only')
   * @param networkId Network ID for the docker socket
   */
  async insertUserRecord(
    containerName: string,
    username: string,
    origin: string,
    networkId: string
  ): Promise<void> {
    await this.executeSql(
      containerName,
      `INSERT INTO users (username, email, repo_origin) VALUES ('${username}', '${username}@test.com', '${origin}')`,
      networkId
    );
  }

  /**
   * Check if a record with the given origin exists in users table.
   * @returns true if at least one record exists with this origin
   */
  async recordExistsByOrigin(
    containerName: string,
    origin: string,
    networkId: string
  ): Promise<boolean> {
    const count = await this.executeSql(
      containerName,
      `SELECT COUNT(*) FROM users WHERE repo_origin = '${origin}'`,
      networkId
    );
    return Number.parseInt(count.trim()) > 0;
  }

  /**
   * Get total record count in users table.
   */
  async getUserRecordCount(containerName: string, networkId: string): Promise<number> {
    const count = await this.executeSql(containerName, 'SELECT COUNT(*) FROM users', networkId);
    return Number.parseInt(count.trim());
  }

  /**
   * Get MD5 hash of all users data for integrity verification.
   * Orders by id to ensure consistent hash across queries.
   */
  async getUsersDataHash(containerName: string, networkId: string): Promise<string> {
    const hash = await this.executeSql(
      containerName,
      `SELECT MD5(string_agg(id::text || username || email || COALESCE(repo_origin, ''), '' ORDER BY id)) FROM users`,
      networkId
    );
    return hash.trim();
  }

  /**
   * Insert multiple test records for bulk data testing.
   * @param count Number of records to insert
   * @param origin Repository origin identifier
   */
  async insertBulkUserRecords(
    containerName: string,
    count: number,
    origin: string,
    networkId: string
  ): Promise<void> {
    // Use a single INSERT with multiple VALUES for efficiency
    const values: string[] = [];
    for (let i = 0; i < count; i++) {
      const username = `bulk_user_${origin}_${i}_${Date.now()}`;
      values.push(`('${username}', '${username}@test.com', '${origin}')`);
    }

    // PostgreSQL can handle large inserts, but we'll batch for safety
    const batchSize = 100;
    for (let i = 0; i < values.length; i += batchSize) {
      const batch = values.slice(i, i + batchSize);
      await this.executeSql(
        containerName,
        `INSERT INTO users (username, email, repo_origin) VALUES ${batch.join(', ')}`,
        networkId
      );
    }
  }
}
