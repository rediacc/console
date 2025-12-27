/**
 * Environment detection utilities
 * Used to detect the runtime environment (web, electron, etc.)
 */

/**
 * Detect if running in Electron environment
 * Checks for Electron-specific objects exposed via preload script
 */
export function isElectron(): boolean {
  // Primary check: electronAPI exposed via contextBridge
  if (typeof window !== 'undefined' && window.electronAPI !== undefined) {
    return true;
  }

  // Fallback: check user agent for Electron
  if (typeof navigator !== 'undefined') {
    return navigator.userAgent.toLowerCase().includes('electron');
  }

  return false;
}

/**
 * Check if running in development mode within Electron
 */
export function isElectronDev(): boolean {
  return isElectron() && import.meta.env.DEV;
}

/**
 * Check if running in production Electron build
 */
export function isElectronProduction(): boolean {
  return isElectron() && !import.meta.env.DEV;
}

/**
 * Get the platform identifier
 * Returns 'electron', 'web', or other identifiers as needed
 */
export function getPlatform(): 'electron' | 'web' {
  return isElectron() ? 'electron' : 'web';
}

/**
 * Check if the app is running in a browser extension context
 * (kept for compatibility with existing timer adapter)
 */
export function isExtensionContext(): boolean {
  const chromeGlobal = globalThis as unknown as { chrome?: { runtime?: { id?: string } } };
  return chromeGlobal.chrome?.runtime?.id !== undefined;
}
