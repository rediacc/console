import { useState, useCallback, useRef, useEffect } from 'react';
import type { TerminalConnectParams } from '@/types';
import { isElectron, getElectronAPI } from '@/types';

/**
 * Terminal connection options
 */
export interface UseTerminalOptions {
  /** SSH host to connect to */
  host: string;
  /** SSH username */
  user: string;
  /** SSH port (default: 22) */
  port?: number;
  /** SSH private key (PEM format) */
  privateKey: string;
  /** Known hosts entry for verification */
  known_hosts?: string;
  /** Environment variables to set */
  env?: Record<string, string>;
  /** Callback when connection is established */
  onConnect?: (sessionId: string) => void;
  /** Callback when connection is closed */
  onDisconnect?: (exitCode: number) => void;
  /** Callback when an error occurs */
  onError?: (error: string) => void;
}

/**
 * Terminal session state
 */
export type TerminalStatus = 'disconnected' | 'connecting' | 'connected' | 'disconnecting';

/**
 * Return type for useTerminal hook
 */
export interface UseTerminalReturn {
  /** Current session ID (null if not connected) */
  sessionId: string | null;
  /** Current connection status */
  status: TerminalStatus;
  /** Whether currently connecting */
  isConnecting: boolean;
  /** Whether currently connected */
  isConnected: boolean;
  /** Last error message */
  error: string | null;
  /** Connect to the terminal */
  connect: (cols?: number, rows?: number) => Promise<string | null>;
  /** Disconnect from the terminal */
  disconnect: () => Promise<void>;
  /** Write data to the terminal */
  write: (data: string) => void;
  /** Resize the terminal */
  resize: (cols: number, rows: number) => void;
  /** Subscribe to terminal data */
  onData: (callback: (data: string) => void) => () => void;
  /** Subscribe to terminal exit */
  onExit: (callback: (code: number) => void) => () => void;
  /** Check if Electron API is available */
  isAvailable: boolean;
}

/**
 * Hook for managing SSH terminal sessions via Electron IPC
 *
 * Provides connection management, data streaming, and resize handling
 * for xterm.js terminal integration.
 *
 * @example
 * ```tsx
 * const terminal = useTerminal({
 *   host: '192.168.1.100',
 *   user: 'admin',
 *   privateKey: sshPrivateKey,
 *   onConnect: (id) => console.log('Connected:', id),
 *   onDisconnect: (code) => console.log('Exited with code:', code),
 * });
 *
 * // Connect when component mounts
 * useEffect(() => {
 *   terminal.connect(80, 24);
 *   return () => terminal.disconnect();
 * }, []);
 *
 * // Wire up xterm.js data listener
 * useEffect(() => {
 *   if (terminal.sessionId) {
 *     return terminal.onData((data) => xtermInstance.write(data));
 *   }
 * }, [terminal.sessionId]);
 * ```
 */
export function useTerminal(options: UseTerminalOptions): UseTerminalReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<TerminalStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);

  // Keep options ref updated for callbacks
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Track cleanup functions
  const cleanupRef = useRef<(() => void)[]>([]);

  // Check if Electron API is available
  const isAvailable = isElectron();

  /**
   * Connect to the terminal
   */
  const connect = useCallback(
    async (cols = 80, rows = 24): Promise<string | null> => {
      if (!isAvailable) {
        const errorMsg = 'Terminal requires the desktop application';
        setError(errorMsg);
        optionsRef.current.onError?.(errorMsg);
        return null;
      }

      if (status === 'connecting' || status === 'connected') {
        return sessionId;
      }

      setStatus('connecting');
      setError(null);

      try {
        const api = getElectronAPI();
        const params: TerminalConnectParams = {
          host: optionsRef.current.host,
          user: optionsRef.current.user,
          port: optionsRef.current.port,
          privateKey: optionsRef.current.privateKey,
          known_hosts: optionsRef.current.known_hosts,
          cols,
          rows,
          env: optionsRef.current.env,
        };

        const result = await api.terminal.connect(params);
        setSessionId(result.sessionId);
        setStatus('connected');
        optionsRef.current.onConnect?.(result.sessionId);
        return result.sessionId;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to connect';
        setError(errorMsg);
        setStatus('disconnected');
        optionsRef.current.onError?.(errorMsg);
        return null;
      }
    },
    [isAvailable, status, sessionId]
  );

  /**
   * Disconnect from the terminal
   */
  const disconnect = useCallback(async (): Promise<void> => {
    if (!sessionId || !isAvailable) {
      return;
    }

    setStatus('disconnecting');

    try {
      const api = getElectronAPI();
      await api.terminal.close(sessionId);
    } catch (err) {
      console.error('Error closing terminal session:', err);
    } finally {
      // Cleanup all listeners
      cleanupRef.current.forEach((cleanup) => cleanup());
      cleanupRef.current = [];

      setSessionId(null);
      setStatus('disconnected');
    }
  }, [sessionId, isAvailable]);

  /**
   * Write data to the terminal
   */
  const write = useCallback(
    (data: string): void => {
      if (!sessionId || !isAvailable) {
        return;
      }
      const api = getElectronAPI();
      api.terminal.write(sessionId, data);
    },
    [sessionId, isAvailable]
  );

  /**
   * Resize the terminal
   */
  const resize = useCallback(
    (cols: number, rows: number): void => {
      if (!sessionId || !isAvailable) {
        return;
      }
      const api = getElectronAPI();
      api.terminal.resize(sessionId, cols, rows);
    },
    [sessionId, isAvailable]
  );

  /**
   * Subscribe to terminal data events
   */
  const onData = useCallback(
    (callback: (data: string) => void): (() => void) => {
      if (!sessionId || !isAvailable) {
        return () => {};
      }
      const api = getElectronAPI();
      const cleanup = api.terminal.onData(sessionId, callback);
      cleanupRef.current.push(cleanup);
      return cleanup;
    },
    [sessionId, isAvailable]
  );

  /**
   * Subscribe to terminal exit events
   */
  const onExit = useCallback(
    (callback: (code: number) => void): (() => void) => {
      if (!sessionId || !isAvailable) {
        return () => {};
      }
      const api = getElectronAPI();
      const cleanup = api.terminal.onExit(sessionId, (code) => {
        callback(code);
        optionsRef.current.onDisconnect?.(code);
        setStatus('disconnected');
        setSessionId(null);
      });
      cleanupRef.current.push(cleanup);
      return cleanup;
    },
    [sessionId, isAvailable]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Disconnect if still connected
      if (sessionId && isAvailable) {
        const api = getElectronAPI();
        api.terminal.close(sessionId).catch(console.error);
      }
      // Cleanup all listeners
      cleanupRef.current.forEach((cleanup) => cleanup());
      cleanupRef.current = [];
    };
  }, [sessionId, isAvailable]);

  return {
    sessionId,
    status,
    isConnecting: status === 'connecting',
    isConnected: status === 'connected',
    error,
    connect,
    disconnect,
    write,
    resize,
    onData,
    onExit,
    isAvailable,
  };
}
