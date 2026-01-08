import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts', 'src/**/*.test.ts'],
    testTimeout: 30000,
    hookTimeout: 60000, // Increased for parallel registration
    // Setup file runs for each test file - creates isolated test accounts
    // Each file gets its own organization via generateTestAccount()
    setupFiles: ['./tests/setup.ts'],
    // Enable parallel execution across test files
    // Each file runs in a separate process (forks) for complete isolation
    // This ensures module-level state (like currentTestAccount) is not shared
    fileParallelism: true,
    pool: 'forks',
    maxWorkers: 4,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts', 'src/types/**', 'src/__tests__/**'],
      reporter: ['text', 'text-summary'],
    },
  },
});
