import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { ipcMain } from 'electron';
import type { FileInfo } from '@rediacc/shared-desktop';

/**
 * SFTP connection parameters from renderer
 */
interface SFTPConnectParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  passphrase?: string;
}

/**
 * Active SFTP session
 */
interface SFTPSession {
  client: SFTPClient;
  host: string;
  user: string;
  createdAt: number;
}

/**
 * Active SFTP sessions map
 */
const sessions = new Map<string, SFTPSession>();

/**
 * Generate a unique session ID
 */
function generateSessionId(): string {
  return `sftp_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
}

/**
 * Registers SFTP IPC handlers for file browser functionality
 */
export function registerSftpHandlers(): void {
  // Connect to SFTP
  ipcMain.handle(
    'sftp:connect',
    async (_event, params: SFTPConnectParams): Promise<{ sessionId: string }> => {
      const client = new SFTPClient({
        host: params.host,
        port: params.port ?? 22,
        username: params.user,
        privateKey: params.privateKey,
        passphrase: params.passphrase,
      });

      await client.connect();

      const sessionId = generateSessionId();
      sessions.set(sessionId, {
        client,
        host: params.host,
        user: params.user,
        createdAt: Date.now(),
      });

      return { sessionId };
    }
  );

  // List directory contents
  ipcMain.handle(
    'sftp:listDirectory',
    (_event, sessionId: string, path: string): Promise<FileInfo[]> => {
      const session = sessions.get(sessionId);
      if (!session) {
        return Promise.reject(new Error('SFTP session not found'));
      }

      return session.client.listDirectory(path);
    }
  );

  // Read file contents
  ipcMain.handle('sftp:readFile', (_event, sessionId: string, path: string): Promise<Buffer> => {
    const session = sessions.get(sessionId);
    if (!session) {
      return Promise.reject(new Error('SFTP session not found'));
    }

    return session.client.readFile(path);
  });

  // Write file contents
  ipcMain.handle(
    'sftp:writeFile',
    async (_event, sessionId: string, path: string, data: ArrayBuffer | Buffer): Promise<void> => {
      const session = sessions.get(sessionId);
      if (!session) {
        throw new Error('SFTP session not found');
      }

      const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data);
      await session.client.writeFile(path, buffer);
    }
  );

  // Create directory
  ipcMain.handle('sftp:mkdir', async (_event, sessionId: string, path: string): Promise<void> => {
    const session = sessions.get(sessionId);
    if (!session) {
      throw new Error('SFTP session not found');
    }

    await session.client.mkdir(path);
  });

  // Delete file or directory
  ipcMain.handle(
    'sftp:delete',
    async (_event, sessionId: string, path: string, isDirectory: boolean): Promise<void> => {
      const session = sessions.get(sessionId);
      if (!session) {
        throw new Error('SFTP session not found');
      }

      await session.client.delete(path, isDirectory);
    }
  );

  // Delete recursively
  ipcMain.handle(
    'sftp:deleteRecursive',
    async (_event, sessionId: string, path: string): Promise<void> => {
      const session = sessions.get(sessionId);
      if (!session) {
        throw new Error('SFTP session not found');
      }

      await session.client.deleteRecursive(path);
    }
  );

  // Rename/move file or directory
  ipcMain.handle(
    'sftp:rename',
    async (_event, sessionId: string, oldPath: string, newPath: string): Promise<void> => {
      const session = sessions.get(sessionId);
      if (!session) {
        throw new Error('SFTP session not found');
      }

      await session.client.rename(oldPath, newPath);
    }
  );

  // Get file/directory stats
  ipcMain.handle('sftp:stat', (_event, sessionId: string, path: string): Promise<FileInfo> => {
    const session = sessions.get(sessionId);
    if (!session) {
      return Promise.reject(new Error('SFTP session not found'));
    }

    return session.client.stat(path);
  });

  // Check if path exists
  ipcMain.handle('sftp:exists', (_event, sessionId: string, path: string): Promise<boolean> => {
    const session = sessions.get(sessionId);
    if (!session) {
      return Promise.reject(new Error('SFTP session not found'));
    }

    return session.client.exists(path);
  });

  // Close SFTP session
  ipcMain.handle('sftp:close', (_event, sessionId: string): void => {
    cleanupSession(sessionId);
  });

  // Get active session count (for debugging)
  ipcMain.handle('sftp:getSessionCount', (): number => {
    return sessions.size;
  });

  // Get session info (for debugging)
  ipcMain.handle(
    'sftp:getSessionInfo',
    (_event, sessionId: string): { host: string; user: string; createdAt: number } | null => {
      const session = sessions.get(sessionId);
      if (!session) return null;

      return {
        host: session.host,
        user: session.user,
        createdAt: session.createdAt,
      };
    }
  );
}

/**
 * Cleans up an SFTP session
 */
function cleanupSession(sessionId: string): void {
  const session = sessions.get(sessionId);
  if (!session) return;

  try {
    session.client.close();
  } catch {
    // Ignore errors during cleanup
  }

  sessions.delete(sessionId);
}

/**
 * Cleanup all SFTP sessions (call on app quit)
 */
export function cleanupAllSftpSessions(): void {
  const sessionIds = Array.from(sessions.keys());
  sessionIds.forEach((id) => cleanupSession(id));
}
