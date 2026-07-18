/**
 * SSH private-key reading.
 *
 * A leaf module: the connection pool (machine-connection.ts) needs to resolve a
 * team key, and every renet path needs one too. Keeping it here rather than in
 * renet-execution.ts keeps the pool free of a renet import cycle. renet-execution
 * re-exports both helpers, so existing importers are unaffected.
 */

import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';

/**
 * Read an SSH key from the filesystem. Expands a leading `~` to the home directory.
 */
export async function readSSHKey(keyPath: string): Promise<string> {
  const expandedPath = keyPath.startsWith('~')
    ? path.join(os.homedir(), keyPath.slice(1))
    : keyPath;

  try {
    return await fs.readFile(expandedPath, 'utf-8');
  } catch (error) {
    throw new Error(`Failed to read SSH key from ${expandedPath}: ${error}`);
  }
}

/**
 * Read an SSH key, returning an empty string when the path is unset or unreadable.
 */
export async function readOptionalSSHKey(keyPath: string | undefined): Promise<string> {
  if (!keyPath) return '';
  return readSSHKey(keyPath).catch(() => '');
}
