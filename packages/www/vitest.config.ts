import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // One module cache per workspace. The shared default (node_modules/.vitest-cache) is wiped by whichever vitest process first sees a changed lockfile hash, while sibling workspaces' runs are writing into it, and that run dies at startup with ENOTEMPTY.
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-www', import.meta.url)
    ),
    environment: 'node',
    // scripts/ is included too: the release-gate helpers live there, and the one environment that broke the readiness matcher (CI, where astro colours its banner) was also the one nobody could exercise without starting a real dev server.
    include: ['src/**/__tests__/**/*.test.ts', 'scripts/**/__tests__/**/*.test.ts'],
  },
});
