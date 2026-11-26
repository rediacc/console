import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // One run directory per `vitest run`, TMPDIR pointed at it for the workers, removed at teardown (PLAN-host-temp-disposal HT7).
    globalSetup: [fileURLToPath(new URL('../../scripts/lib/vitest-run-tmp.ts', import.meta.url))],
    // One module cache per workspace: the shared default is wiped by whichever vitest process first sees a changed lockfile hash, while sibling workspaces' runs write into it.
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-workers-account', import.meta.url)
    ),
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
});
