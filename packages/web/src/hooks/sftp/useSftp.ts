import { useCallback, useEffect, useState, useRef } from 'react';
import { isElectron, type SFTPFileInfo } from '@/types';

/**
 * File information from SFTP
 */
export interface SFTPFile {
  name: string;
  path: string;
  isDirectory: boolean;
  isFile: boolean;
  isSymlink: boolean;
  size: number;
  modifiedAt: Date;
  permissions: string;
  owner?: string;
  group?: string;
}

/**
 * SFTP connection options
 */
export interface SFTPConnectionOptions {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  passphrase?: string;
}

/**
 * SFTP hook state
 */
export interface UseSftpState {
  isConnected: boolean;
  isConnecting: boolean;
  isLoading: boolean;
  error: string | null;
  files: SFTPFile[];
  currentPath: string;
  sessionId: string | null;
}

/**
 * SFTP hook actions
 */
export interface UseSftpActions {
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  navigate: (path: string) => Promise<void>;
  refresh: () => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
  downloadFile: (path: string) => Promise<void>;
  deleteFile: (path: string, isDirectory: boolean) => Promise<void>;
  createFolder: (name: string) => Promise<void>;
  rename: (oldPath: string, newName: string) => Promise<void>;
}

/**
 * Hook for SFTP file operations in Electron
 *
 * Provides a React-friendly API for SFTP operations via Electron IPC.
 * Only functional in Electron environment.
 *
 * @param options - Connection options (host, user, privateKey)
 * @param initialPath - Initial directory path to navigate to after connection
 */
export function useSftp(
  options: SFTPConnectionOptions,
  initialPath = '/'
): UseSftpState & UseSftpActions {
  const [state, setState] = useState<UseSftpState>({
    isConnected: false,
    isConnecting: false,
    isLoading: false,
    error: null,
    files: [],
    currentPath: initialPath,
    sessionId: null,
  });

  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Connect to SFTP server
  const connect = useCallback(async () => {
    if (!isElectron()) {
      setState((prev) => ({ ...prev, error: 'SFTP is only available in desktop app' }));
      return;
    }

    setState((prev) => ({ ...prev, isConnecting: true, error: null }));

    try {
      const result = await window.electronAPI!.sftp.connect({
        host: optionsRef.current.host,
        user: optionsRef.current.user,
        port: optionsRef.current.port,
        privateKey: optionsRef.current.privateKey,
        passphrase: optionsRef.current.passphrase,
      });

      setState((prev) => ({
        ...prev,
        isConnected: true,
        isConnecting: false,
        sessionId: result.sessionId,
      }));

      // Load initial directory after connection
      await loadDirectory(result.sessionId, initialPath);
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isConnecting: false,
        error: error instanceof Error ? error.message : 'Connection failed',
      }));
    }
  }, [initialPath]);

  // Disconnect from SFTP server
  const disconnect = useCallback(async () => {
    if (state.sessionId && isElectron()) {
      try {
        await window.electronAPI!.sftp.close(state.sessionId);
      } catch {
        // Ignore cleanup errors
      }
    }

    setState({
      isConnected: false,
      isConnecting: false,
      isLoading: false,
      error: null,
      files: [],
      currentPath: initialPath,
      sessionId: null,
    });
  }, [state.sessionId, initialPath]);

  // Load directory contents
  const loadDirectory = async (sessionId: string, path: string): Promise<void> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const files = await window.electronAPI!.sftp.listDirectory(sessionId, path);

      // Convert dates from serialization
      const processedFiles: SFTPFile[] = files.map((file: SFTPFileInfo) => ({
        ...file,
        modifiedAt: new Date(file.modifiedAt),
      }));

      setState((prev) => ({
        ...prev,
        isLoading: false,
        files: processedFiles,
        currentPath: path,
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load directory',
      }));
    }
  };

  // Navigate to a directory
  const navigate = useCallback(
    async (path: string) => {
      if (!state.sessionId || !isElectron()) return;
      await loadDirectory(state.sessionId, path);
    },
    [state.sessionId]
  );

  // Refresh current directory
  const refresh = useCallback(async () => {
    if (!state.sessionId || !isElectron()) return;
    await loadDirectory(state.sessionId, state.currentPath);
  }, [state.sessionId, state.currentPath]);

  // Upload a file
  const uploadFile = useCallback(
    async (file: File) => {
      if (!state.sessionId || !isElectron()) return;

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const buffer = await file.arrayBuffer();
        const targetPath = `${state.currentPath}/${file.name}`.replaceAll(/\/+/g, '/');
        await window.electronAPI!.sftp.writeFile(state.sessionId, targetPath, buffer);
        await loadDirectory(state.sessionId, state.currentPath);
      } catch (error) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: error instanceof Error ? error.message : 'Upload failed',
        }));
      }
    },
    [state.sessionId, state.currentPath]
  );

  // Download a file
  const downloadFile = useCallback(
    async (path: string) => {
      if (!state.sessionId || !isElectron()) return;

      try {
        const data = await window.electronAPI!.sftp.readFile(state.sessionId, path);

        // Convert ArrayBuffer to Blob and trigger download
        const blob = new Blob([data]);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = path.split('/').pop() ?? 'file';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (error) {
        setState((prev) => ({
          ...prev,
          error: error instanceof Error ? error.message : 'Download failed',
        }));
      }
    },
    [state.sessionId]
  );

  // Delete a file or directory
  const deleteFile = useCallback(
    async (path: string, isDirectory: boolean) => {
      if (!state.sessionId || !isElectron()) return;

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        if (isDirectory) {
          await window.electronAPI!.sftp.deleteRecursive(state.sessionId, path);
        } else {
          await window.electronAPI!.sftp.delete(state.sessionId, path, false);
        }
        await loadDirectory(state.sessionId, state.currentPath);
      } catch (error) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: error instanceof Error ? error.message : 'Delete failed',
        }));
      }
    },
    [state.sessionId, state.currentPath]
  );

  // Create a new folder
  const createFolder = useCallback(
    async (name: string) => {
      if (!state.sessionId || !isElectron()) return;

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const folderPath = `${state.currentPath}/${name}`.replaceAll(/\/+/g, '/');
        await window.electronAPI!.sftp.mkdir(state.sessionId, folderPath);
        await loadDirectory(state.sessionId, state.currentPath);
      } catch (error) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: error instanceof Error ? error.message : 'Failed to create folder',
        }));
      }
    },
    [state.sessionId, state.currentPath]
  );

  // Rename a file or directory
  const rename = useCallback(
    async (oldPath: string, newName: string) => {
      if (!state.sessionId || !isElectron()) return;

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        const dir = oldPath.substring(0, oldPath.lastIndexOf('/'));
        const newPath = `${dir}/${newName}`.replaceAll(/\/+/g, '/');
        await window.electronAPI!.sftp.rename(state.sessionId, oldPath, newPath);
        await loadDirectory(state.sessionId, state.currentPath);
      } catch (error) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          error: error instanceof Error ? error.message : 'Rename failed',
        }));
      }
    },
    [state.sessionId, state.currentPath]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (state.sessionId && isElectron()) {
        window.electronAPI!.sftp.close(state.sessionId).catch(() => {
          // Ignore cleanup errors
        });
      }
    };
  }, [state.sessionId]);

  return {
    ...state,
    connect,
    disconnect,
    navigate,
    refresh,
    uploadFile,
    downloadFile,
    deleteFile,
    createFolder,
    rename,
  };
}
