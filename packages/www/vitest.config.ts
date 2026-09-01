import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    // scripts/ is included too: the release-gate helpers live there, and the one
    // environment that broke the readiness matcher (CI, where astro colours its banner)
    // was also the one nobody could exercise without starting a real dev server.
    include: ['src/**/__tests__/**/*.test.ts', 'scripts/**/__tests__/**/*.test.ts'],
  },
});
