/**
 * Desktop warmup validation.
 *
 * Attempts to load all externalized native modules and reports pass/fail.
 * Used by CI to verify the packaged desktop app contains all required modules.
 *
 * The externals list is sourced from externals.json (single source of truth).
 */

import { createRequire } from 'node:module';
import externalsConfig from '../../externals.json';

// Externals that must be resolvable at runtime (from externals.json).
// 'managed' (electron) is excluded since it's provided by Electron itself.
// 'optional' (cpu-features) is excluded since ssh2 works without it.
const REQUIRED_EXTERNALS = externalsConfig.externals;

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
