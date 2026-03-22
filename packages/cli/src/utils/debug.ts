/**
 * Debug logging helper - outputs when REDIACC_DEBUG or DEBUG env var is set
 */
export function debugLog(message: string): void {
  if (process.env.REDIACC_DEBUG || process.env.DEBUG) {
    console.warn(`[DEBUG] ${message}`);
  }
}
