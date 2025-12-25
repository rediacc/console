import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts', 'src/**/*.test.ts'],
    testTimeout: 30000, // CLI commands may take time
    hookTimeout: 30000,
    // Setup file only runs for blackbox tests (tests/ directory)
    // Unit tests in src/__tests__ don't need API setup
    setupFiles: ['./tests/setup.ts'],
    // Run tests sequentially to avoid auth state conflicts
    fileParallelism: false,
    sequence: {
      concurrent: false,
    },
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts', 'src/types/**', 'src/__tests__/**'],
      reporter: ['text', 'text-summary'],
    },
  },
});
