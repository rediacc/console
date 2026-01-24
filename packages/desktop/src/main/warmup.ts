/**
 * Desktop warmup validation.
 *
 * Attempts to load all externalized native modules and reports pass/fail.
 * Used by CI to verify the packaged desktop app contains all required modules.
 *
 * The REQUIRED_EXTERNALS list must stay in sync with electron.vite.config.ts
 * ssr.external (excluding 'electron' which is provided by Electron itself,
 * and 'cpu-features' which is optional).
 */

import { createRequire } from 'node:module';

// Externals that must be resolvable at runtime.
// Keep in sync with electron.vite.config.ts ssr.external
const REQUIRED_EXTERNALS = ['ssh2', 'node-pty', 'electron-updater'] as const;

export function runWarmup(): number {
  const results: { module: string; status: 'ok' | 'fail'; error?: string }[] = [];
  const nodeRequire = createRequire(import.meta.url);

  for (const mod of REQUIRED_EXTERNALS) {
    try {
      nodeRequire(mod);
      results.push({ module: mod, status: 'ok' });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      results.push({ module: mod, status: 'fail', error: msg });
    }
  }

  const failed = results.filter((r) => r.status === 'fail');
  const output = { success: failed.length === 0, results };
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  return failed.length === 0 ? 0 : 1;
}
