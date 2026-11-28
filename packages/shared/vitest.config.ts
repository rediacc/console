import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // One run directory per `vitest run`, TMPDIR pointed at it for the workers, removed at teardown (PLAN-host-temp-disposal HT7).
    globalSetup: [fileURLToPath(new URL('../../scripts/lib/vitest-run-tmp.ts', import.meta.url))],
    // One module cache per workspace. The shared default (node_modules/.vitest-cache) is wiped by whichever vitest process first sees a changed lockfile hash, while sibling workspaces' runs are writing into it, and that run dies at startup with ENOTEMPTY.
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-shared', import.meta.url)
    ),
    globals: true,
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
});
