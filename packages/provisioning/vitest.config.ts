import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // One module cache per workspace. The shared default (node_modules/.vitest-cache) is wiped by whichever vitest process first sees a changed lockfile hash, while sibling workspaces' runs are writing into it, and that run dies at startup with ENOTEMPTY.
    fsModuleCachePath: fileURLToPath(
      new URL('../../node_modules/.vitest-cache-provisioning', import.meta.url)
    ),
  },
});
