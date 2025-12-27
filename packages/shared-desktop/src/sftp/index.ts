/**
 * SFTP module - Direct SSH/SFTP file operations
 *
 * Provides a Promise-based SFTP client for direct file browser functionality.
 * Used exclusively in Electron desktop app for direct machine connections.
 *
 * @module sftp
 *
 * @example
 * ```typescript
 * import { SFTPClient, createSFTPClient } from '@rediacc/shared-desktop/sftp';
 *
 * // Using credentials
 * const client = createSFTPClient(credentials);
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

export {
  SFTPClient,
  createSFTPClient,
  type SFTPClientConfig,
  type TransferProgressCallback,
} from './client.js';

// Re-export types for convenience
export type { FileInfo, SFTPSession, SSHCredentials } from '../types/index.js';
