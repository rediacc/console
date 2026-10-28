import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    // `cloudflare:workers` exists only inside workerd; modules that import it load against this stub.
    alias: {
      'cloudflare:workers': fileURLToPath(
        new URL('./src/__tests__/cloudflare-workers-stub.ts', import.meta.url)
      ),
    },
  },
  test: {
    // One module cache per workspace. The shared default (node_modules/.vitest-cache) is wiped by whichever vitest process first sees a changed lockfile hash, while sibling workspaces' runs are writing into it, and that run dies at startup with ENOTEMPTY.
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-workers-proxy', import.meta.url)
    ),
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
});
