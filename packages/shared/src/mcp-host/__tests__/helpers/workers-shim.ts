/** Vitest setup: lets the OAuth library's `cloudflare:workers` import resolve on Node (see packages/shared/src/mcp-host/node-workers-shim.ts). */
import { afterAll } from 'vitest';
import { installCloudflareWorkersShim, uninstallCloudflareWorkersShim } from '../../node-workers-shim.js';

installCloudflareWorkersShim();

// The hook is process-wide, so each suite removes it when it finishes.
afterAll(uninstallCloudflareWorkersShim);
