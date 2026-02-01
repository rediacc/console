import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
    exclude: [
      'node_modules',
      'dist',
      'tests/**',
      'src/**/*.integration.test.ts', // S3 integration tests (run via test:unit:s3)
    ],
  },
});
