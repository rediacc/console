import { join } from 'node:path';
import { electronApp, is, optimizer } from '@electron-toolkit/utils';
import { app, BrowserWindow, session, shell } from 'electron';
import { cleanupIpcHandlers, registerIpcHandlers } from './ipc';
import { setupProtocolHandler } from './protocol';
import { setupAutoUpdater } from './updater/autoUpdater';
import { WindowManager } from './windowManager';

let mainWindow: BrowserWindow | null = null;
const windowManager = new WindowManager();

function createWindow(): void {
  const windowState = windowManager.loadState();

  mainWindow = new BrowserWindow({
    width: windowState.width || 1280,
    height: windowState.height || 800,
    x: windowState.x,
    y: windowState.y,
    minWidth: 900,
    minHeight: 600,
    show: false,
    autoHideMenuBar: true,
    icon: join(__dirname, '../../resources/icon.png'),
    title: 'Rediacc Console',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });

  // Track window state changes
  windowManager.track(mainWindow);

  // Show window when ready
  mainWindow.on('ready-to-show', () => {
    if (windowState.isMaximized) {
      mainWindow?.maximize();
    }
    mainWindow?.show();
  });

  mainWindow.webContents.setWindowOpenHandler((details) => {
    // Open external links in default browser
    void shell.openExternal(details.url);
    return { action: 'deny' };
  });

  // Set up Content Security Policy
  // Development mode allows unsafe-inline/eval for HMR, production is stricter
  const cspPolicy = is.dev
    ? // Development: Allow HMR and debugging
      "default-src 'self'; " +
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
      "style-src 'self' 'unsafe-inline'; " +
      "connect-src 'self' https://*.rediacc.com wss://*.rediacc.com https://*.trycloudflare.com http://localhost:* https://localhost:* ws://localhost:*; " +
      "img-src 'self' data: https:; " +
      "font-src 'self' data:;"
    : // Production: Strict CSP without unsafe-inline/eval
      "default-src 'self'; " +
      "script-src 'self'; " +
      "style-src 'self' 'unsafe-inline'; " + // unsafe-inline still needed for Ant Design runtime styles
      "connect-src 'self' https://*.rediacc.com wss://*.rediacc.com https://*.trycloudflare.com http://localhost:* https://localhost:* ws://localhost:*; " +
      "img-src 'self' data: https:; " +
      "font-src 'self' data:;";

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [cspPolicy],
      },
    });
  });

  // Load the renderer
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    void mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL']);
  } else {
    void mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }

  // Open DevTools in development
  if (is.dev) {
    mainWindow.webContents.openDevTools();
  }
}

// App lifecycle
void app.whenReady().then(() => {
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.rediacc.console');

  // Watch for shortcuts in development
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  // Set up protocol handler (rediacc:// URLs)
  // Must be done before registering IPC handlers
  setupProtocolHandler(() => mainWindow);

  // Register IPC handlers before creating window
  registerIpcHandlers();

  // Set up auto-updater (only in production)
  if (!is.dev) {
    setupAutoUpdater();
  }

  createWindow();

  app.on('activate', () => {
    // On macOS, re-create window when dock icon is clicked
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed (except on macOS)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Cleanup before quitting
app.on('before-quit', async () => {
  await cleanupIpcHandlers();
});

// Security: Prevent navigation to untrusted URLs
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, navigationUrl) => {
    const parsedUrl = new URL(navigationUrl);
    const allowedOrigins = ['localhost', 'rediacc.com'];

    // Precise hostname matching: exact match or subdomain (e.g., www.rediacc.com, sandbox.rediacc.com)
    const isAllowed = allowedOrigins.some(
      (origin) => parsedUrl.hostname === origin || parsedUrl.hostname.endsWith(`.${origin}`)
    );

    if (!isAllowed) {
      event.preventDefault();
    }
  });
});
