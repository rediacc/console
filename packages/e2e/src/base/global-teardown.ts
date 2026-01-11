import fs from 'node:fs';
import path from 'node:path';
import { FullConfig } from '@playwright/test';
import { requireEnvVar } from '../utils/env';

function globalTeardown(_config: FullConfig) {
  console.warn('Starting global teardown...');

  cleanupTemporaryFiles();

  generateTestSummary();

  console.warn('Global teardown completed');
}

function cleanupTemporaryFiles() {
  console.warn('Cleaning up temporary files...');

  const tempFiles = ['auth.json', '.auth/user.json', '.auth/admin.json'];

  for (const file of tempFiles) {
    const fullPath = path.resolve(file);
    if (fs.existsSync(fullPath)) {
      fs.unlinkSync(fullPath);
      console.warn(`Deleted: ${file}`);
    }
  }
}

function generateTestSummary() {
  console.warn('Generating test summary...');

  try {
    const resultsPath = path.resolve('reports/test-results.json');
    if (fs.existsSync(resultsPath)) {
      const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8')) as {
        stats?: Record<string, unknown>;
      };

      const summary = {
        timestamp: new Date().toISOString(),
        stats: results.stats ?? {},
        environment: {
          baseURL: requireEnvVar('BASE_URL'),
          browser: requireEnvVar('BROWSER'),
          ci: !!process.env.CI,
        },
      };

      const summaryPath = path.resolve('reports/test-summary.json');
      fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

      console.warn('Test summary saved to reports/test-summary.json');
    }
  } catch (summaryError) {
    console.warn(`Failed to generate test summary: ${summaryError}`);
  }
}

export default globalTeardown;
