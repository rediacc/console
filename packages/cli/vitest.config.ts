import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts', 'src/**/*.test.ts'],
    testTimeout: 30000,
    hookTimeout: 30000,
    // Setup file runs for integration tests in tests/ directory
    // It checks test path and skips setup for unit tests
    setupFiles: ['./tests/setup.ts'],
    fileParallelism: false,
    sequence: { concurrent: false },
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts', 'src/types/**', 'src/__tests__/**'],
      reporter: ['text', 'text-summary'],
    },
  },
});
