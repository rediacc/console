/**
 * CLI bundle warmup validation.
 *
 * Verifies the bundled CLI executable is coherent:
 * - VERSION is correctly embedded (not the dev placeholder)
 * - Core imported modules are accessible (proves bundle integrity)
 *
 * Used by CI as a smoke test after building the SEA binary.
 * Since esbuild bundles all dependencies inline (external: []),
 * imports here verify the bundle is intact. If truncated or corrupted,
 * the import resolution at the top of the bundle would fail before
 * reaching this code.
 */

// These static imports prove the bundle includes these modules.
// If the bundle is incomplete, these will throw at load time.
import { Command } from 'commander';
import { VERSION } from './version.js';

export function runWarmup(): number {
  const checks: { name: string; status: 'ok' | 'fail'; error?: string }[] = [];

  // Check version is set (cast to string since VERSION may be modified at build time)
  try {
    const version: string = VERSION;
    if (!version || version === '0.0.0-development') throw new Error('Version not set');
    checks.push({ name: 'version', status: 'ok' });
  } catch (e: unknown) {
    checks.push({
      name: 'version',
      status: 'fail',
      error: e instanceof Error ? e.message : String(e),
    });
  }

  // Verify Commander is functional (proves bundle coherence)
  try {
    const program = new Command();
    program.name('warmup-test');
    checks.push({ name: 'commander', status: 'ok' });
  } catch (e: unknown) {
    checks.push({
      name: 'commander',
      status: 'fail',
      error: e instanceof Error ? e.message : String(e),
    });
  }

  const failed = checks.filter((c) => c.status === 'fail');
  const output = { success: failed.length === 0, results: checks };
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  return failed.length === 0 ? 0 : 1;
}
