/**
 * Window IPC Handlers
 * Provides IPC handlers for managing pop-out windows
 */

import { join } from 'node:path';
import { is } from '@electron-toolkit/utils';
import { BrowserWindow, ipcMain } from 'electron';

/**
 * Options for creating a pop-out window
 */
export interface PopoutWindowOptions {
  /** Type of popout window */
  type: 'terminal';
  /** Terminal session ID (for terminal type) */
  sessionId: string;
  /** Window title */
  title?: string;
  /** Window width */
  width?: number;
  /** Window height */
  height?: number;
  /** Machine name for display */
  machineName?: string;
  /** Repository name for display */
  repositoryName?: string;
}

/**
 * Result of creating a pop-out window
 */
export interface PopoutWindowResult {
  success: boolean;
  windowId?: number;
  error?: string;
}

// Track popout windows for cleanup
const popoutWindows: Map<number, BrowserWindow> = new Map();

/**
 * Registers window IPC handlers
 */
export function registerWindowHandlers(): void {
  // Open a pop-out window
  ipcMain.handle(
    'window:openPopout',
    async (_event, options: PopoutWindowOptions): Promise<PopoutWindowResult> => {
      try {
        const title = options.title ?? buildWindowTitle(options);

        const popout = new BrowserWindow({
          width: options.width ?? 900,
          height: options.height ?? 600,
          minWidth: 500,
          minHeight: 400,
          title,
          autoHideMenuBar: true,
          webPreferences: {
            preload: join(__dirname, '../preload/index.js'),
            sandbox: true,
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: true,
          },
        });

        // Track the window
        popoutWindows.set(popout.id, popout);

        // Clean up when window is closed
        popout.on('closed', () => {
          popoutWindows.delete(popout.id);
        });

        // Build the URL with query params
        const queryParams = new URLSearchParams({
          sessionId: options.sessionId,
          ...(options.machineName && { machineName: options.machineName }),
          ...(options.repositoryName && { repositoryName: options.repositoryName }),
        });

        // Load the terminal popout route
        if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
          // Development: Use dev server with hash router
          const devUrl = `${process.env['ELECTRON_RENDERER_URL']}#/terminal-popout?${queryParams.toString()}`;
          await popout.loadURL(devUrl);
        } else {
          // Production: Load from file with hash router
          const prodUrl = `file://${join(__dirname, '../renderer/index.html')}#/terminal-popout?${queryParams.toString()}`;
          await popout.loadURL(prodUrl);
        }

        // Open DevTools in development
        if (is.dev) {
          popout.webContents.openDevTools();
        }

        return {
          success: true,
          windowId: popout.id,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to create popout window';
        console.error('Failed to create popout window:', error);
        return {
          success: false,
          error: message,
        };
      }
    }
  );

  // Close a pop-out window by ID
  ipcMain.handle('window:closePopout', (_event, windowId: number): boolean => {
    const popout = popoutWindows.get(windowId);
    if (popout && !popout.isDestroyed()) {
      popout.close();
      return true;
    }
    return false;
  });

  // Get count of open popout windows
  ipcMain.handle('window:getPopoutCount', (): number => {
    return popoutWindows.size;
  });
}

/**
 * Build window title based on options
 */
function buildWindowTitle(options: PopoutWindowOptions): string {
  const parts = ['Terminal'];
  if (options.machineName) {
    parts.push(options.machineName);
  }
  if (options.repositoryName) {
    parts.push(options.repositoryName);
  }
  return parts.join(' - ');
}

/**
 * Cleanup all popout windows
 */
export function cleanupPopoutWindows(): void {
  for (const [id, window] of popoutWindows) {
    if (!window.isDestroyed()) {
      window.close();
    }
    popoutWindows.delete(id);
  }
}
