import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    testTimeout: 30000, // CLI commands may take time
    hookTimeout: 30000,
    setupFiles: ['./tests/setup.ts'],
    // Run tests sequentially to avoid auth state conflicts
    fileParallelism: false,
    sequence: {
      concurrent: false,
    },
  },
});
