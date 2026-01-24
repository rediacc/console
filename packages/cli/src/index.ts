#!/usr/bin/env node

import { cli } from './cli.js';
import { apiClient } from './services/api.js';
import { authService } from './services/auth.js';
import { telemetryService } from './services/telemetry.js';
import { startupUpdateCheck } from './services/updater.js';
import { handleError } from './utils/errors.js';
import { runWarmup } from './warmup.js';

// Warmup check: validate bundle coherence before full CLI initialization.
// Static import required - dynamic import() segfaults in SEA binaries on macOS ARM64.
if (process.argv.includes('--warmup')) {
  process.exit(runWarmup());
}

// Start non-blocking update check (resolves silently on error)
const updateCheckPromise = startupUpdateCheck().catch(() => {});

async function main() {
  try {
    // Connect auth service's master password getter to API client
    apiClient.setMasterPasswordGetter(() => authService.requireMasterPassword());

    await cli.parseAsync(process.argv);

    // Wait for update check and telemetry shutdown (with timeout to avoid delaying exit)
    await Promise.race([
      Promise.all([telemetryService.shutdown(), updateCheckPromise]),
      new Promise((resolve) => setTimeout(resolve, 500)),
    ]);
  } catch (error) {
    handleError(error);
  }
}

void main();
