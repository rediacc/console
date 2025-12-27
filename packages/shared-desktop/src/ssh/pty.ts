import type { PTYOptions, PTYSession } from '../types/index.js';

// node-pty types (will be imported dynamically)
type IPty = import('node-pty').IPty;

/**
 * Session counter for unique IDs
 */
let sessionCounter = 0;

/**
 * Active PTY sessions map
 */
const activeSessions = new Map<string, IPty>();

/**
 * Generates a unique session ID
 */
function generateSessionId(): string {
  return `pty-${Date.now()}-${++sessionCounter}`;
}

/**
 * Creates a PTY session for an SSH connection
 *
 * @param destination - SSH destination (user@host)
 * @param sshOptions - SSH options array from SSHConnection
 * @param options - PTY options
 * @returns PTY session object
 */
export async function createSSHPTYSession(
  destination: string,
  sshOptions: string[],
  options?: PTYOptions
): Promise<PTYSession> {
  // Dynamically import node-pty to avoid issues if not installed
  const nodePty = await import('node-pty');

  const sessionId = generateSessionId();
  const args = [...sshOptions, destination];

  // Default terminal settings
  const cols = options?.cols ?? 80;
  const rows = options?.rows ?? 24;
  const name = options?.name ?? 'xterm-256color';

  // Merge environment
  const env = {
    ...process.env,
    ...options?.env,
    TERM: name,
  };

  // Spawn the PTY
  const pty = nodePty.spawn('ssh', args, {
    name,
    cols,
    rows,
    cwd: options?.cwd ?? process.cwd(),
    env,
  });

  // Store in active sessions
  activeSessions.set(sessionId, pty);

  // Data callback handlers
  const dataCallbacks: ((data: string) => void)[] = [];
  const exitCallbacks: ((exitCode: number, signal?: number) => void)[] = [];

  // Set up data listener
  pty.onData((data) => {
    for (const callback of dataCallbacks) {
      callback(data);
    }
  });

  // Set up exit listener
  pty.onExit(({ exitCode, signal }) => {
    activeSessions.delete(sessionId);
    for (const callback of exitCallbacks) {
      callback(exitCode, signal);
    }
  });

  return {
    sessionId,
    pid: pty.pid,

    write: (data: string) => {
      pty.write(data);
    },

    resize: (newCols: number, newRows: number) => {
      pty.resize(newCols, newRows);
    },

    kill: (signal?: string) => {
      pty.kill(signal);
      activeSessions.delete(sessionId);
    },

    onData: (callback: (data: string) => void) => {
      dataCallbacks.push(callback);
      // Return cleanup function
      return () => {
        const index = dataCallbacks.indexOf(callback);
        if (index !== -1) {
          dataCallbacks.splice(index, 1);
        }
      };
    },

    onExit: (callback: (exitCode: number, signal?: number) => void) => {
      exitCallbacks.push(callback);
      // Return cleanup function
      return () => {
        const index = exitCallbacks.indexOf(callback);
        if (index !== -1) {
          exitCallbacks.splice(index, 1);
        }
      };
    },
  };
}

/**
 * Gets an active PTY session by ID
 *
 * @param sessionId - Session ID
 * @returns The raw IPty instance or undefined
 */
export function getActiveSession(sessionId: string): IPty | undefined {
  return activeSessions.get(sessionId);
}

/**
 * Checks if a session is active
 *
 * @param sessionId - Session ID to check
 * @returns true if session exists and is active
 */
export function isSessionActive(sessionId: string): boolean {
  return activeSessions.has(sessionId);
}

/**
 * Gets the count of active sessions
 *
 * @returns Number of active PTY sessions
 */
export function getActiveSessionCount(): number {
  return activeSessions.size;
}

/**
 * Kills all active PTY sessions
 * Useful for cleanup on application exit
 */
export function killAllSessions(): void {
  for (const [sessionId, pty] of activeSessions) {
    try {
      pty.kill();
    } catch {
      // Ignore errors during cleanup
    }
    activeSessions.delete(sessionId);
  }
}

/**
 * Creates a local shell PTY session (not SSH)
 *
 * @param shell - Shell to spawn (default: system default)
 * @param options - PTY options
 * @returns PTY session object
 */
export async function createLocalPTYSession(
  shell?: string,
  options?: PTYOptions
): Promise<PTYSession> {
  const nodePty = await import('node-pty');
  const os = await import('os');

  const sessionId = generateSessionId();

  // Determine shell
  const defaultShell =
    os.platform() === 'win32' ? 'powershell.exe' : (process.env.SHELL ?? '/bin/bash');
  const shellToUse = shell ?? defaultShell;

  const cols = options?.cols ?? 80;
  const rows = options?.rows ?? 24;
  const name = options?.name ?? 'xterm-256color';

  const env = {
    ...process.env,
    ...options?.env,
    TERM: name,
  };

  const pty = nodePty.spawn(shellToUse, [], {
    name,
    cols,
    rows,
    cwd: options?.cwd ?? process.cwd(),
    env,
  });

  activeSessions.set(sessionId, pty);

  const dataCallbacks: ((data: string) => void)[] = [];
  const exitCallbacks: ((exitCode: number, signal?: number) => void)[] = [];

  pty.onData((data) => {
    for (const callback of dataCallbacks) {
      callback(data);
    }
  });

  pty.onExit(({ exitCode, signal }) => {
    activeSessions.delete(sessionId);
    for (const callback of exitCallbacks) {
      callback(exitCode, signal);
    }
  });

  return {
    sessionId,
    pid: pty.pid,
    write: (data: string) => pty.write(data),
    resize: (newCols: number, newRows: number) => pty.resize(newCols, newRows),
    kill: (signal?: string) => {
      pty.kill(signal);
      activeSessions.delete(sessionId);
    },
    onData: (callback: (data: string) => void) => {
      dataCallbacks.push(callback);
      return () => {
        const index = dataCallbacks.indexOf(callback);
        if (index !== -1) dataCallbacks.splice(index, 1);
      };
    },
    onExit: (callback: (exitCode: number, signal?: number) => void) => {
      exitCallbacks.push(callback);
      return () => {
        const index = exitCallbacks.indexOf(callback);
        if (index !== -1) exitCallbacks.splice(index, 1);
      };
    },
  };
}
