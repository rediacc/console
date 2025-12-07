/**
 * Browser timer provider
 * Provides browser-native timer functions for the shared queue service
 */

import type { TimerProvider } from '@rediacc/shared/services/queue';

/**
 * Browser timer provider implementation
 * Uses window.setInterval, window.clearInterval, and window.setTimeout
 */
export const browserTimerProvider: TimerProvider = {
  setInterval: (callback: () => void, ms: number) => window.setInterval(callback, ms),
  clearInterval: (id: number | NodeJS.Timeout) => window.clearInterval(id as number),
  setTimeout: (callback: () => void, ms: number) => window.setTimeout(callback, ms),
};

/**
 * Detect if running in browser extension context
 * @returns True if running as a browser extension
 */
export function isExtensionContext(): boolean {
  try {
    return (
      typeof chrome !== 'undefined' &&
      chrome?.runtime !== undefined &&
      chrome.runtime.id !== undefined
    );
  } catch {
    return false;
  }
}

// Chrome type declaration for extension detection
declare const chrome:
  | {
      runtime?: {
        id?: string;
      };
    }
  | undefined;
