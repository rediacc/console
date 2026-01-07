import {
  createSSHPTYSession,
  SSHConnection,
  createTempSSHKeyFile,
  removeTempSSHKeyFile,
  createTempKnownHostsFile,
  removeTempKnownHostsFile,
} from '@rediacc/shared-desktop/ssh';
import { ipcMain } from 'electron';
import type { PTYSession } from '@rediacc/shared-desktop';

/**
 * Terminal connection parameters from renderer
 */
interface TerminalConnectParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  cols?: number;
  rows?: number;
  env?: Record<string, string>;
  command?: string;
}

/**
 * Active terminal session
 */
interface TerminalSession {
  ptySession: PTYSession;
  keyFilePath: string;
  knownHostsPath?: string;
  cleanupData: () => void;
  cleanupExit: () => void;
}

/**
 * Active terminal sessions map
 */
const sessions = new Map<string, TerminalSession>();

/**
 * Registers terminal IPC handlers
 */
export function registerTerminalHandlers(): void {
  // Connect to SSH and create PTY session
  ipcMain.handle(
    'terminal:connect',
    async (event, params: TerminalConnectParams): Promise<{ sessionId: string }> => {
      // Create temp SSH key file
      const keyFilePath = await createTempSSHKeyFile(params.privateKey);

      // Create temp known hosts file if host entry provided
      let knownHostsPath: string | undefined;
      if (params.known_hosts) {
        knownHostsPath = await createTempKnownHostsFile(params.known_hosts);
      }

      // Create SSH connection object
      const sshConnection = new SSHConnection(
        params.privateKey,
        params.known_hosts ?? '',
        params.port
      );
      await sshConnection.setup();

      // Build destination
      const destination = `${params.user}@${params.host}`;

      // Build SSH options array including the command if provided
      const sshOptions = [...sshConnection.sshOptions];

      // Create PTY session
      const ptySession = await createSSHPTYSession(destination, sshOptions, {
        cols: params.cols ?? 80,
        rows: params.rows ?? 24,
        env: params.env,
      });

      const sessionId = ptySession.sessionId;

      // Set up data forwarding to renderer
      const cleanupData = ptySession.onData((data: string) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`terminal:data:${sessionId}`, data);
        }
      });

      // Set up exit handling
      const cleanupExit = ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`terminal:exit:${sessionId}`, exitCode);
        }
        // Cleanup session
        void cleanupSession(sessionId);
      });

      // Store session
      sessions.set(sessionId, {
        ptySession,
        keyFilePath,
        knownHostsPath,
        cleanupData,
        cleanupExit,
      });

      return { sessionId };
    }
  );

  // Write data to terminal
  ipcMain.on('terminal:write', (_event, sessionId: string, data: string) => {
    const session = sessions.get(sessionId);
    if (session) {
      session.ptySession.write(data);
    }
  });

  // Resize terminal
  ipcMain.on('terminal:resize', (_event, sessionId: string, cols: number, rows: number) => {
    const session = sessions.get(sessionId);
    if (session) {
      session.ptySession.resize(cols, rows);
    }
  });

  // Close terminal session
  ipcMain.handle('terminal:close', async (_event, sessionId: string): Promise<void> => {
    await cleanupSession(sessionId);
  });

  // Get active session count (for debugging)
  ipcMain.handle('terminal:getSessionCount', (): number => {
    return sessions.size;
  });
}

/**
 * Cleans up a terminal session
 */
async function cleanupSession(sessionId: string): Promise<void> {
  const session = sessions.get(sessionId);
  if (!session) return;

  // Remove listeners
  session.cleanupData();
  session.cleanupExit();

  // Kill the PTY
  try {
    session.ptySession.kill();
  } catch {
    // Ignore errors during cleanup
  }

  // Remove temp files
  try {
    await removeTempSSHKeyFile(session.keyFilePath);
    if (session.knownHostsPath) {
      await removeTempKnownHostsFile(session.knownHostsPath);
    }
  } catch {
    // Ignore cleanup errors
  }

  // Remove from sessions map
  sessions.delete(sessionId);
}

/**
 * Cleanup all sessions (call on app quit)
 */
export async function cleanupAllTerminalSessions(): Promise<void> {
  const sessionIds = Array.from(sessions.keys());
  await Promise.all(sessionIds.map((id) => cleanupSession(id)));
}
