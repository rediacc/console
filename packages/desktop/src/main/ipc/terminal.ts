import { DEFAULTS } from '@rediacc/shared/config';
import type { PTYSession } from '@rediacc/shared-desktop';
import {
  createSSHPTYSession,
  createTempKnownHostsFile,
  createTempSSHKeyFile,
  removeTempKnownHostsFile,
  removeTempSSHKeyFile,
  SSHConnection,
} from '@rediacc/shared-desktop/ssh';
import { ipcMain } from 'electron';

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
 * Maximum number of output chunks to buffer for session transfer
 * This allows history to be replayed when popping out to a new window
 */
const OUTPUT_BUFFER_MAX_SIZE = 10000;

/**
 * Active terminal session
 */
interface TerminalSession {
  ptySession: PTYSession;
  keyFilePath: string;
  knownHostsPath?: string;
  cleanupData: () => void;
  cleanupExit: () => void;
  /** Output buffer for preserving terminal history on transfer */
  outputBuffer: string[];
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
        cols: params.cols ?? DEFAULTS.SSH.TERMINAL_COLS,
        rows: params.rows ?? DEFAULTS.SSH.TERMINAL_ROWS,
        env: params.env,
      });

      const sessionId = ptySession.sessionId;

      // Output buffer for preserving history on session transfer
      const outputBuffer: string[] = [];

      // Set up data forwarding to renderer with buffering
      const cleanupData = ptySession.onData((data: string) => {
        // Buffer the output (circular buffer - keep last N chunks)
        outputBuffer.push(data);
        if (outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          outputBuffer.shift();
        }

        // Forward to renderer
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
        outputBuffer,
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

  // Transfer terminal session to a new window
  // Re-registers event listeners to send data to the calling window
  // Returns buffered output for history replay
  ipcMain.handle(
    'terminal:transfer',
    (event, sessionId: string): { success: boolean; error?: string; buffer?: string } => {
      const session = sessions.get(sessionId);
      if (!session) {
        return { success: false, error: 'Session not found' };
      }

      // Capture buffer before re-registering listeners
      const buffer = session.outputBuffer.join('');

      // Cleanup old listeners (pointing to previous window)
      session.cleanupData();
      session.cleanupExit();

      // Re-register listeners with new window's webContents
      const cleanupData = session.ptySession.onData((data: string) => {
        // Continue buffering for potential future transfers
        session.outputBuffer.push(data);
        if (session.outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          session.outputBuffer.shift();
        }

        if (!event.sender.isDestroyed()) {
          event.sender.send(`terminal:data:${sessionId}`, data);
        }
      });

      const cleanupExit = session.ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`terminal:exit:${sessionId}`, exitCode);
        }
        void cleanupSession(sessionId);
      });

      // Update session with new cleanup functions
      session.cleanupData = cleanupData;
      session.cleanupExit = cleanupExit;

      return { success: true, buffer };
    }
  );
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
