import {
  buildCliCommand,
  PROTOCOL_SCHEME,
  parseProtocolUrl,
} from '@rediacc/shared-desktop/protocol';
import { app, BrowserWindow } from 'electron';
import type { ProtocolUrl } from '@rediacc/shared-desktop';

/**
 * Main window getter type
 */
type GetMainWindow = () => BrowserWindow | null;

/**
 * Protocol URL handler callback type
 */
type ProtocolUrlHandler = (parsed: ProtocolUrl) => void;

/**
 * Registered protocol URL handlers
 */
const urlHandlers: ProtocolUrlHandler[] = [];

/**
 * Sets up the protocol handler for rediacc:// URLs
 *
 * @param getMainWindow - Function to get the main window
 * @returns true if protocol was registered successfully
 */
export function setupProtocolHandler(getMainWindow: GetMainWindow): boolean {
  // Register as default protocol handler
  const registered = app.setAsDefaultProtocolClient(PROTOCOL_SCHEME);

  if (!registered) {
    console.warn(`Failed to register ${PROTOCOL_SCHEME}:// protocol handler`);
  }

  // Handle single instance lock (Windows/Linux)
  // This is needed for protocol URLs on Windows
  const gotTheLock = app.requestSingleInstanceLock();

  if (!gotTheLock) {
    // Another instance is already running
    // The other instance will handle the URL
    app.quit();
    return false;
  }

  // Second instance handling (Windows/Linux)
  app.on('second-instance', (_event, argv) => {
    // Find the protocol URL in argv
    const url = argv.find((arg) => arg.startsWith(`${PROTOCOL_SCHEME}://`));
    if (url) {
      handleProtocolUrl(url, getMainWindow());
    }

    // Focus the main window
    focusMainWindow(getMainWindow);
  });

  // Handle open-url (macOS)
  app.on('open-url', (event, url) => {
    event.preventDefault();
    handleProtocolUrl(url, getMainWindow());
  });

  // Handle startup with protocol URL (Windows)
  // Check if app was started with a protocol URL
  const startupUrl = process.argv.find((arg) => arg.startsWith(`${PROTOCOL_SCHEME}://`));
  if (startupUrl) {
    // Delay handling to ensure window is ready
    void app.whenReady().then(() => {
      setTimeout(() => {
        handleProtocolUrl(startupUrl, getMainWindow());
      }, 500);
    });
  }

  return registered;
}

/**
 * Handles a protocol URL
 *
 * @param url - The full protocol URL
 * @param mainWindow - The main browser window
 */
function handleProtocolUrl(url: string, mainWindow: BrowserWindow | null): void {
  try {
    const parsed = parseProtocolUrl(url);

    // eslint-disable-next-line no-console
    console.log(
      `Handling protocol URL: ${PROTOCOL_SCHEME}://${parsed.teamName}/${parsed.machineName}/${parsed.action}`
    );

    // Send to renderer process
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('protocol:open', parsed);
    }

    // Call registered handlers
    for (const handler of urlHandlers) {
      try {
        handler(parsed);
      } catch (error) {
        console.error('Protocol URL handler error:', error);
      }
    }
  } catch (error) {
    console.error('Failed to parse protocol URL:', error);
  }
}

/**
 * Focuses the main window
 *
 * @param getMainWindow - Function to get the main window
 */
function focusMainWindow(getMainWindow: GetMainWindow): void {
  const mainWindow = getMainWindow();
  if (mainWindow) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();
  }
}

/**
 * Registers a handler for protocol URLs
 *
 * @param handler - Handler function
 * @returns Cleanup function to unregister the handler
 */
export function onProtocolUrl(handler: ProtocolUrlHandler): () => void {
  urlHandlers.push(handler);
  return () => {
    const index = urlHandlers.indexOf(handler);
    if (index !== -1) {
      urlHandlers.splice(index, 1);
    }
  };
}

/**
 * Builds a CLI command equivalent from a protocol URL
 *
 * @param url - The protocol URL
 * @returns Array of CLI arguments
 */
export function getCliCommandFromUrl(url: string): string[] {
  const parsed = parseProtocolUrl(url);
  return buildCliCommand(parsed);
}
