import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/__tests__/**/*.integration.test.ts'],
    exclude: [
      'node_modules',
      'dist',
      'tests/**',
      'src/stores/__tests__/vault-*.integration.test.ts',
    ],
    testTimeout: 30000,
  },
});
