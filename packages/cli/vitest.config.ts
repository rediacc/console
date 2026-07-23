import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    // Several serve-suite tests bind a real HTTP server and loopback-fetch
    // (~100ms healthy). The vitest default 5s cap flakes on starved CI
    // runners (observed: a run where a fork worker took >60s to not even
    // start). 30s only delays genuinely-hung tests; it never slows green ones.
    testTimeout: 30_000,
    include: ['src/**/__tests__/**/*.test.ts'],
    exclude: [
      'node_modules',
      'dist',
      'tests/**',
      'src/**/*.integration.test.ts', // Integration tests (run separately)
    ],
  },
});
