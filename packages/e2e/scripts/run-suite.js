const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Read suite name and extra args from arguments
const suiteName = process.argv[2] || 'auth';
const extraArgs = process.argv.slice(3).join(' ');
const suitesConfigPath = path.resolve(__dirname, '../test-suites.json');

if (!fs.existsSync(suitesConfigPath)) {
  console.error('❌ Error: test-suites.json not found!');
  process.exit(1);
}

const config = JSON.parse(fs.readFileSync(suitesConfigPath, 'utf8'));
const tests = config.suites[suiteName];

if (!tests) {
  console.error(`❌ Error: Suite "${suiteName}" not found in test-suites.json!`);
  console.log('Available suites:', Object.keys(config.suites).join(', '));
  process.exit(1);
}

console.log(`🚀 Running test suite: ${suiteName}`);
if (extraArgs) console.log(`with args: ${extraArgs}`);
console.log(`📋 Sequence: ${tests.join(' -> ')}`);
console.log('═══════════════════════════════════════════════════════════════════');

// Run tests one by one to ensure sequential execution
for (const testFile of tests) {
  try {
    console.log(`\n🔍 Executing: ${testFile}`);
    // Forwarding extraArgs to playwright command
    execSync(`pnpm playwright test ${testFile} --workers=1 ${extraArgs}`, { stdio: 'inherit' });
    console.log(`✅ Passed: ${testFile}`);
  } catch (error) {
    console.error(`❌ Failed: ${testFile}`);
    // Stop sequence on failure
    process.exit(1);
  }
}

console.log('\n═══════════════════════════════════════════════════════════════════');
console.log(`✨ Suite "${suiteName}" completed successfully!`);
