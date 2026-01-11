import { FullConfig } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { requireEnvVar } from '../utils/env';

async function globalTeardown(config: FullConfig) {
  console.log('🧹 Starting global teardown...');

  await cleanupTemporaryFiles();
  
  await generateTestSummary();

  console.log('✅ Global teardown completed');
}

async function cleanupTemporaryFiles() {
  console.log('🗑️ Cleaning up temporary files...');
  
  const tempFiles = ['auth.json', '.auth/user.json', '.auth/admin.json'];
  
  tempFiles.forEach(file => {
    const fullPath = path.resolve(file);
    if (fs.existsSync(fullPath)) {
      fs.unlinkSync(fullPath);
      console.log(`🗑️ Deleted: ${file}`);
    }
  });
}

async function generateTestSummary() {
  console.log('📊 Generating test summary...');
  
  try {
    const resultsPath = path.resolve('reports/test-results.json');
    if (fs.existsSync(resultsPath)) {
      const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
      
      const summary = {
        timestamp: new Date().toISOString(),
        stats: results.stats || {},
        environment: {
          baseURL: requireEnvVar('BASE_URL'),
          browser: requireEnvVar('BROWSER'),
          ci: !!process.env.CI
        }
      };

      const summaryPath = path.resolve('reports/test-summary.json');
      fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
      
      console.log('📊 Test summary saved to reports/test-summary.json');
    }
  } catch (error) {
    console.log(`⚠️ Failed to generate test summary: ${error}`);
  }
}

export default globalTeardown;