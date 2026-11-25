/** Vitest setup: lets the OAuth library's `cloudflare:workers` import resolve on Node (see packages/shared/src/mcp-host/node-workers-shim.ts). */
import { installCloudflareWorkersShim } from '../../../../../packages/shared/src/mcp-host/node-workers-shim.js';

installCloudflareWorkersShim();
