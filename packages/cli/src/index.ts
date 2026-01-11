#!/usr/bin/env node

import { cli } from './cli.js';
import { apiClient } from './services/api.js';
import { authService } from './services/auth.js';
import { telemetryService } from './services/telemetry.js';
import { handleError } from './utils/errors.js';

async function main() {
  try {
    // Connect auth service's master password getter to API client
    apiClient.setMasterPasswordGetter(() => authService.requireMasterPassword());

    await cli.parseAsync(process.argv);

    // Shutdown telemetry after successful command completion
    // Use a short timeout (500ms) to avoid delaying CLI exit
    await Promise.race([
      telemetryService.shutdown(),
      new Promise((resolve) => setTimeout(resolve, 500)),
    ]);
  } catch (error) {
    handleError(error);
  }
}

void main();
