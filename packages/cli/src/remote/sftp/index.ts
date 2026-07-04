/**
 * SFTP module - Direct SSH/SFTP file operations
 *
 * Provides a Promise-based SFTP client used by the CLI's remote layer for
 * direct file operations over an SSH connection.
 *
 * @module sftp
 *
 * @example
 * ```typescript
 * import { SFTPClient } from '../remote/sftp/index.js';
 *
 * const client = new SFTPClient(config);
 * await client.connect();
 *
 * // List directory
 * const files = await client.listDirectory('/home/user');
 *
 * // Read file
 * const content = await client.readFile('/home/user/file.txt');
 *
 * // Write file
 * await client.writeFile('/home/user/newfile.txt', Buffer.from('content'));
 *
 * // Clean up
 * await client.close();
 * ```
 */

export { SFTPClient, type SFTPClientConfig } from './client.js';
