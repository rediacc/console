#!/usr/bin/env node

import { cli } from './cli.js';
import { isMcpServeFastPath } from './commands/mcp/fast-path.js';
import { printFeedbackHint } from './services/feedback/hint.js';
import { installStderrTap, recordCommand } from './services/feedback/ring.js';
import { telemetryService } from './services/telemetry/telemetry.js';
import {
  applyPendingUpdate,
  maybeSpawnBackgroundUpdate,
  runBackgroundUpdateWorker,
} from './services/update/background-updater.js';
import { handleError } from './utils/errors.js';
import { runWarmup } from './warmup.js';

// Warmup check: validate bundle coherence before full CLI initialization. Static import required - dynamic import() segfaults in SEA binaries on macOS ARM64.
if (process.argv.includes('--warmup')) {
  process.exit(runWarmup());
}

// MCP server mode, must run before normal CLI to avoid stdout pollution. The MCP protocol uses stdout for JSON-RPC, so no other CLI initialization (telemetry, i18n, update checks) can write to stdout.
if (isMcpServeFastPath(process.argv)) {
  const configIdx = process.argv.indexOf('--config');
  const configName = configIdx >= 0 ? process.argv[configIdx + 1] : undefined;
  const timeoutIdx = process.argv.indexOf('--timeout');
  const defaultTimeoutMs =
    timeoutIdx >= 0 ? Number.parseInt(process.argv[timeoutIdx + 1], 10) : 120_000;

  // MCP tools are derived from the generated CLI contract, not the live Commander tree, so this fast path no longer needs to import cli.js just to hand over the program instance.
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
  // Catch unhandled errors that escape the main try-catch
  process.on('uncaughtException', (error) => {
    recordCommand({
      argv: process.argv.slice(2),
      exitCode: 1,
      errorCode: 'UNCAUGHT_EXCEPTION',
      errorMessage: error instanceof Error ? error.message : String(error),
    });
    printFeedbackHint({ argv: process.argv.slice(2), exitCode: 1 });
    telemetryService.trackError(error, { source: 'uncaughtException' });
    void telemetryService.shutdown().finally(() => process.exit(1));
  });
  process.on('unhandledRejection', (reason) => {
    telemetryService.trackError(reason instanceof Error ? reason : new Error(String(reason)), {
      source: 'unhandledRejection',
    });
  });

  installStderrTap();

  // Normal CLI flow: apply pending update + spawn background check
  const applyPromise = applyPendingUpdate().catch(() => {});
  const spawnPromise = maybeSpawnBackgroundUpdate().catch(() => {});

  async function main() {
    try {
      await applyPromise; // fast: just file renames if update ready
      await spawnPromise; // near-instant: just spawns detached child

      await cli.parseAsync(process.argv);

      // Stop profiling and wait for telemetry shutdown (with timeout to avoid delaying exit)
      await telemetryService.stopProfiling();
      await Promise.race([
        telemetryService.shutdown(),
        new Promise((resolve) => {
          const t = setTimeout(resolve, 500);
          if (typeof t === 'object' && 'unref' in t) t.unref();
        }),
      ]);
    } catch (error) {
      handleError(error);
    }
  }

  void main();
}
