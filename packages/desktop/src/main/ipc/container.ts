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
 * Container exec parameters from renderer
 */
interface ContainerExecParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  containerName?: string;
  command?: string; // Default: /bin/sh
  cols?: number;
  rows?: number;
}

/**
 * Container logs parameters from renderer
 */
interface ContainerLogsParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  follow?: boolean;
  tail?: number;
  cols?: number;
  rows?: number;
}

/**
 * Container stats parameters from renderer
 */
interface ContainerStatsParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  cols?: number;
  rows?: number;
}

/**
 * Maximum number of output chunks to buffer for session transfer
 */
const OUTPUT_BUFFER_MAX_SIZE = 10000;

/**
 * Container session type
 */
type ContainerSessionType = 'exec' | 'logs' | 'stats';

/**
 * Active container session
 */
interface ContainerSession {
  ptySession: PTYSession;
  keyFilePath: string;
  knownHostsPath?: string;
  cleanupData: () => void;
  cleanupExit: () => void;
  outputBuffer: string[];
  sessionType: ContainerSessionType;
  containerId: string;
  containerName?: string;
}

/**
 * Active container sessions map
 */
const sessions = new Map<string, ContainerSession>();

/**
 * Creates an SSH PTY session for container operations
 */
async function createContainerPTYSession(
  params: {
    host: string;
    user: string;
    port?: number;
    privateKey: string;
    known_hosts?: string;
    cols?: number;
    rows?: number;
  },
  remoteCommand: string
): Promise<{
  ptySession: PTYSession;
  keyFilePath: string;
  knownHostsPath?: string;
}> {
  // Create temp SSH key file
  const keyFilePath = await createTempSSHKeyFile(params.privateKey);

  // Create temp known hosts file if host entry provided
  let knownHostsPath: string | undefined;
  if (params.known_hosts) {
    knownHostsPath = await createTempKnownHostsFile(params.known_hosts);
  }

  // Create SSH connection object
  const sshConnection = new SSHConnection(params.privateKey, params.known_hosts ?? '', params.port);
  await sshConnection.setup();

  // Build destination
  const destination = `${params.user}@${params.host}`;

  // Build SSH options - add the remote command to execute
  const sshOptions = [...sshConnection.sshOptions, '-t', remoteCommand];

  // Create PTY session
  const ptySession = await createSSHPTYSession(destination, sshOptions, {
    cols: params.cols ?? 80,
    rows: params.rows ?? 24,
  });

  return { ptySession, keyFilePath, knownHostsPath };
}

/**
 * Registers container IPC handlers
 */
export function registerContainerHandlers(): void {
  // Execute into container (docker exec -it)
  ipcMain.handle(
    'container:exec',
    async (event, params: ContainerExecParams): Promise<{ sessionId: string }> => {
      // Build docker exec command
      const shell = params.command ?? '/bin/sh';
      const remoteCommand = `docker exec -it ${params.containerId} ${shell}`;

      const { ptySession, keyFilePath, knownHostsPath } = await createContainerPTYSession(
        params,
        remoteCommand
      );

      const sessionId = ptySession.sessionId;
      const outputBuffer: string[] = [];

      // Set up data forwarding to renderer with buffering
      const cleanupData = ptySession.onData((data: string) => {
        outputBuffer.push(data);
        if (outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          outputBuffer.shift();
        }

        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:data:${sessionId}`, data);
        }
      });

      // Set up exit handling
      const cleanupExit = ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:exit:${sessionId}`, exitCode);
        }
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
        sessionType: 'exec',
        containerId: params.containerId,
        containerName: params.containerName,
      });

      return { sessionId };
    }
  );

  // Stream container logs (docker logs -f)
  ipcMain.handle(
    'container:logs',
    async (event, params: ContainerLogsParams): Promise<{ sessionId: string }> => {
      // Build docker logs command
      const tailArg = params.tail ? `--tail ${params.tail}` : '--tail 100';
      const followArg = params.follow === false ? '' : '-f';
      const remoteCommand = `docker logs ${followArg} ${tailArg} ${params.containerId}`;

      const { ptySession, keyFilePath, knownHostsPath } = await createContainerPTYSession(
        params,
        remoteCommand
      );

      const sessionId = ptySession.sessionId;
      const outputBuffer: string[] = [];

      const cleanupData = ptySession.onData((data: string) => {
        outputBuffer.push(data);
        if (outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          outputBuffer.shift();
        }

        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:data:${sessionId}`, data);
        }
      });

      const cleanupExit = ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:exit:${sessionId}`, exitCode);
        }
        void cleanupSession(sessionId);
      });

      sessions.set(sessionId, {
        ptySession,
        keyFilePath,
        knownHostsPath,
        cleanupData,
        cleanupExit,
        outputBuffer,
        sessionType: 'logs',
        containerId: params.containerId,
      });

      return { sessionId };
    }
  );

  // Stream container stats (docker stats)
  ipcMain.handle(
    'container:stats',
    async (event, params: ContainerStatsParams): Promise<{ sessionId: string }> => {
      // Build docker stats command
      const remoteCommand = `docker stats ${params.containerId}`;

      const { ptySession, keyFilePath, knownHostsPath } = await createContainerPTYSession(
        params,
        remoteCommand
      );

      const sessionId = ptySession.sessionId;
      const outputBuffer: string[] = [];

      const cleanupData = ptySession.onData((data: string) => {
        outputBuffer.push(data);
        if (outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          outputBuffer.shift();
        }

        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:data:${sessionId}`, data);
        }
      });

      const cleanupExit = ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:exit:${sessionId}`, exitCode);
        }
        void cleanupSession(sessionId);
      });

      sessions.set(sessionId, {
        ptySession,
        keyFilePath,
        knownHostsPath,
        cleanupData,
        cleanupExit,
        outputBuffer,
        sessionType: 'stats',
        containerId: params.containerId,
      });

      return { sessionId };
    }
  );

  // Write data to container session
  ipcMain.on('container:write', (_event, sessionId: string, data: string) => {
    const session = sessions.get(sessionId);
    if (session) {
      session.ptySession.write(data);
    }
  });

  // Resize container terminal
  ipcMain.on('container:resize', (_event, sessionId: string, cols: number, rows: number) => {
    const session = sessions.get(sessionId);
    if (session) {
      session.ptySession.resize(cols, rows);
    }
  });

  // Close container session
  ipcMain.handle('container:close', async (_event, sessionId: string): Promise<void> => {
    await cleanupSession(sessionId);
  });

  // Transfer container session to a new window
  ipcMain.handle(
    'container:transfer',
    (event, sessionId: string): { success: boolean; error?: string; buffer?: string } => {
      const session = sessions.get(sessionId);
      if (!session) {
        return { success: false, error: 'Session not found' };
      }

      // Capture buffer before re-registering listeners
      const buffer = session.outputBuffer.join('');

      // Cleanup old listeners
      session.cleanupData();
      session.cleanupExit();

      // Re-register listeners with new window's webContents
      const cleanupData = session.ptySession.onData((data: string) => {
        session.outputBuffer.push(data);
        if (session.outputBuffer.length > OUTPUT_BUFFER_MAX_SIZE) {
          session.outputBuffer.shift();
        }

        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:data:${sessionId}`, data);
        }
      });

      const cleanupExit = session.ptySession.onExit((exitCode: number) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send(`container:exit:${sessionId}`, exitCode);
        }
        void cleanupSession(sessionId);
      });

      session.cleanupData = cleanupData;
      session.cleanupExit = cleanupExit;

      return { success: true, buffer };
    }
  );

  // Get active session count (for debugging)
  ipcMain.handle('container:getSessionCount', (): number => {
    return sessions.size;
  });
}

/**
 * Cleans up a container session
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
 * Cleanup all container sessions (call on app quit)
 */
export async function cleanupAllContainerSessions(): Promise<void> {
  const sessionIds = Array.from(sessions.keys());
  await Promise.all(sessionIds.map((id) => cleanupSession(id)));
}
