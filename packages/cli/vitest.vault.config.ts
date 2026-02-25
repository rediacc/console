import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/stores/__tests__/vault-store-adapter.integration.test.ts'],
    exclude: ['node_modules', 'dist', 'tests/**'],
    testTimeout: 30000,
  },
});
