#!/usr/bin/env node

import { cli } from './cli.js';
import { apiClient } from './services/api.js';
import { authService } from './services/auth.js';
import { handleError } from './utils/errors.js';

async function main() {
  try {
    // Connect auth service's master password getter to API client
    apiClient.setMasterPasswordGetter(() => authService.requireMasterPassword());

    await cli.parseAsync(process.argv);
  } catch (error) {
    handleError(error);
  }
}

void main();
