import { useState, useCallback, useRef, useEffect } from 'react';
import type { ContainerExecParams, ContainerLogsParams, ContainerStatsParams } from '@/types';
import { isElectron, getElectronAPI } from '@/types';

/**
 * Container session type
 */
export type ContainerSessionType = 'exec' | 'logs' | 'stats';

/**
 * Base container connection options
 */
interface BaseContainerOptions {
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
  /** Docker container ID */
  containerId: string;
  /** Docker container name (for display) */
  containerName?: string;
  /** Callback when connection is established */
  onConnect?: (sessionId: string) => void;
  /** Callback when connection is closed */
  onDisconnect?: (exitCode: number) => void;
  /** Callback when an error occurs */
  onError?: (error: string) => void;
}

/**
 * Container exec options
 */
export interface UseContainerExecOptions extends BaseContainerOptions {
  type: 'exec';
  /** Command to run in container (default: /bin/sh) */
  command?: string;
}

/**
 * Container logs options
 */
export interface UseContainerLogsOptions extends BaseContainerOptions {
  type: 'logs';
  /** Follow log output */
  follow?: boolean;
  /** Number of lines to show from the end */
  tail?: number;
}

/**
 * Container stats options
 */
export interface UseContainerStatsOptions extends BaseContainerOptions {
  type: 'stats';
}

/**
 * Union type for all container options
 */
export type UseContainerOptions =
  | UseContainerExecOptions
  | UseContainerLogsOptions
  | UseContainerStatsOptions;

/**
 * Container session state
 */
export type ContainerStatus = 'disconnected' | 'connecting' | 'connected' | 'disconnecting';

/**
 * Return type for useContainer hook
 */
export interface UseContainerReturn {
  /** Current session ID (null if not connected) */
  sessionId: string | null;
  /** Current connection status */
  status: ContainerStatus;
  /** Whether currently connecting */
  isConnecting: boolean;
  /** Whether currently connected */
  isConnected: boolean;
  /** Last error message */
  error: string | null;
  /** Connect to the container */
  connect: (cols?: number, rows?: number) => Promise<string | null>;
  /** Disconnect from the container */
  disconnect: () => Promise<void>;
  /** Write data to the container (only for exec) */
  write: (data: string) => void;
  /** Resize the container terminal */
  resize: (cols: number, rows: number) => void;
  /** Subscribe to container data */
  onData: (callback: (data: string) => void) => () => void;
  /** Subscribe to container exit */
  onExit: (callback: (code: number) => void) => () => void;
  /** Check if Electron API is available */
  isAvailable: boolean;
  /** Container session type */
  sessionType: ContainerSessionType;
}

/**
 * Hook for managing Docker container sessions via Electron IPC
 *
 * Supports three modes:
 * - exec: Interactive shell inside container
 * - logs: Stream container logs
 * - stats: Stream container stats
 *
 * @example
 * ```tsx
 * // Container exec example
 * const container = useContainer({
 *   type: 'exec',
 *   host: '192.168.1.100',
 *   user: 'admin',
 *   privateKey: sshPrivateKey,
 *   containerId: 'abc123',
 *   containerName: 'my-container',
 *   command: '/bin/bash',
 *   onConnect: (id) => console.log('Connected:', id),
 * });
 *
 * // Container logs example
 * const logs = useContainer({
 *   type: 'logs',
 *   host: '192.168.1.100',
 *   user: 'admin',
 *   privateKey: sshPrivateKey,
 *   containerId: 'abc123',
 *   follow: true,
 *   tail: 100,
 * });
 * ```
 */
export function useContainer(options: UseContainerOptions): UseContainerReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<ContainerStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);

  // Keep options ref updated for callbacks
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Track cleanup functions
  const cleanupRef = useRef<(() => void)[]>([]);

  // Check if Electron API is available
  const isAvailable = isElectron();

  /**
   * Connect to the container
   */
  const connect = useCallback(
    async (cols = 80, rows = 24): Promise<string | null> => {
      if (!isAvailable) {
        const errorMsg = 'Container access requires the desktop application';
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
        const opts = optionsRef.current;
        let result: { sessionId: string };

        switch (opts.type) {
          case 'exec': {
            const params: ContainerExecParams = {
              host: opts.host,
              user: opts.user,
              port: opts.port,
              privateKey: opts.privateKey,
              known_hosts: opts.known_hosts,
              containerId: opts.containerId,
              containerName: opts.containerName,
              command: opts.command,
              cols,
              rows,
            };
            result = await api.container.exec(params);
            break;
          }
          case 'logs': {
            const params: ContainerLogsParams = {
              host: opts.host,
              user: opts.user,
              port: opts.port,
              privateKey: opts.privateKey,
              known_hosts: opts.known_hosts,
              containerId: opts.containerId,
              follow: opts.follow,
              tail: opts.tail,
              cols,
              rows,
            };
            result = await api.container.logs(params);
            break;
          }
          case 'stats': {
            const params: ContainerStatsParams = {
              host: opts.host,
              user: opts.user,
              port: opts.port,
              privateKey: opts.privateKey,
              known_hosts: opts.known_hosts,
              containerId: opts.containerId,
              cols,
              rows,
            };
            result = await api.container.stats(params);
            break;
          }
        }

        setSessionId(result.sessionId);
        setStatus('connected');
        optionsRef.current.onConnect?.(result.sessionId);
        return result.sessionId;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to connect to container';
        setError(errorMsg);
        setStatus('disconnected');
        optionsRef.current.onError?.(errorMsg);
        return null;
      }
    },
    [isAvailable, status, sessionId]
  );

  /**
   * Disconnect from the container
   */
  const disconnect = useCallback(async (): Promise<void> => {
    if (!sessionId || !isAvailable) {
      return;
    }

    setStatus('disconnecting');

    try {
      const api = getElectronAPI();
      await api.container.close(sessionId);
    } catch (err) {
      console.error('Error closing container session:', err);
    } finally {
      // Cleanup all listeners
      cleanupRef.current.forEach((cleanup) => cleanup());
      cleanupRef.current = [];

      setSessionId(null);
      setStatus('disconnected');
    }
  }, [sessionId, isAvailable]);

  /**
   * Write data to the container (only works for exec mode)
   */
  const write = useCallback(
    (data: string): void => {
      if (!sessionId || !isAvailable) {
        return;
      }
      // Only allow write for exec mode
      if (optionsRef.current.type !== 'exec') {
        console.warn('Write is only supported for container exec mode');
        return;
      }
      const api = getElectronAPI();
      api.container.write(sessionId, data);
    },
    [sessionId, isAvailable]
  );

  /**
   * Resize the container terminal
   */
  const resize = useCallback(
    (cols: number, rows: number): void => {
      if (!sessionId || !isAvailable) {
        return;
      }
      const api = getElectronAPI();
      api.container.resize(sessionId, cols, rows);
    },
    [sessionId, isAvailable]
  );

  /**
   * Subscribe to container data events
   */
  const onData = useCallback(
    (callback: (data: string) => void): (() => void) => {
      if (!sessionId || !isAvailable) {
        return () => {};
      }
      const api = getElectronAPI();
      const cleanup = api.container.onData(sessionId, callback);
      cleanupRef.current.push(cleanup);
      return cleanup;
    },
    [sessionId, isAvailable]
  );

  /**
   * Subscribe to container exit events
   */
  const onExit = useCallback(
    (callback: (code: number) => void): (() => void) => {
      if (!sessionId || !isAvailable) {
        return () => {};
      }
      const api = getElectronAPI();
      const cleanup = api.container.onExit(sessionId, (code) => {
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
        api.container.close(sessionId).catch(console.error);
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
    sessionType: options.type,
  };
}
