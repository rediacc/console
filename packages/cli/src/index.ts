#!/usr/bin/env node

import { cli } from './cli.js';
import { apiClient } from './services/api.js';
import { authService } from './services/auth.js';
import {
  applyPendingUpdate,
  maybeSpawnBackgroundUpdate,
  runBackgroundUpdateWorker,
} from './services/background-updater.js';
import { telemetryService } from './services/telemetry.js';
import { handleError } from './utils/errors.js';
import { runWarmup } from './warmup.js';

// Warmup check: validate bundle coherence before full CLI initialization.
// Static import required - dynamic import() segfaults in SEA binaries on macOS ARM64.
if (process.argv.includes('--warmup')) {
  process.exit(runWarmup());
}

// MCP server mode — must run before normal CLI to avoid stdout pollution.
// The MCP protocol uses stdout for JSON-RPC, so no other CLI initialization
// (telemetry, i18n, update checks) can write to stdout.
if (process.argv.includes('mcp') && process.argv.includes('serve')) {
  const configIdx = process.argv.indexOf('--config');
  const configName = configIdx >= 0 ? process.argv[configIdx + 1] : undefined;
  const timeoutIdx = process.argv.indexOf('--timeout');
  const defaultTimeoutMs =
    timeoutIdx >= 0 ? Number.parseInt(process.argv[timeoutIdx + 1], 10) : 120_000;

  import('./commands/mcp/server.js')
    .then(({ startMcpServer }) => startMcpServer({ configName, defaultTimeoutMs }))
    .catch((err: unknown) => {
      process.stderr.write(
        `MCP server error: ${err instanceof Error ? err.message : String(err)}\n`
      );
      process.exit(1);
    });
} else if (process.argv.includes('--background-update')) {
  // Background update worker mode (detached process entry point)

  runBackgroundUpdateWorker()
    .then(() => process.exit(0))
    .catch(() => process.exit(1));
} else {
  // Normal CLI flow: apply pending update + spawn background check
  const applyPromise = applyPendingUpdate().catch(() => {});
  const spawnPromise = maybeSpawnBackgroundUpdate().catch(() => {});

  async function main() {
    try {
      await applyPromise; // fast: just file renames if update ready
      await spawnPromise; // near-instant: just spawns detached child

      // Connect auth service's master password getter to API client
      apiClient.setMasterPasswordGetter(() => authService.requireMasterPassword());

      await cli.parseAsync(process.argv);

      // Stop profiling and wait for telemetry shutdown (with timeout to avoid delaying exit)
      await telemetryService.stopProfiling();
      await Promise.race([
        telemetryService.shutdown(),
        new Promise((resolve) => setTimeout(resolve, 500)),
      ]);
    } catch (error) {
      handleError(error);
    }
  }

  void main();
}
