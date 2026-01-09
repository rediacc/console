import * as fs from 'fs';
import * as path from 'path';
import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';

/**
 * Custom Playwright reporter that saves each test's output to a text file.
 *
 * Output structure:
 *   reports/cli-logs/
 *   ├── 01-auth/
 *   │   ├── should-login-successfully.txt
 *   │   └── should-logout-successfully.txt
 *   ├── 02-team/
 *   │   └── should-list-teams.txt
 *   └── summary.txt
 */
export default class TextFileReporter implements Reporter {
  private outputDir: string;
  private testResults: Map<string, { test: TestCase; result: TestResult }> = new Map();
  private startTime: Date = new Date();

  constructor(options: { outputDir?: string } = {}) {
    this.outputDir = options.outputDir ?? 'test-outputs';
  }

  onBegin(_config: FullConfig, _suite: Suite): void {
    this.startTime = new Date();
    // Ensure output directory exists
    fs.mkdirSync(this.outputDir, { recursive: true });

    console.warn(`[TextFileReporter] Output directory: ${path.resolve(this.outputDir)}`);
  }

  onTestBegin(_test: TestCase): void {
    // No per-test start log; we emit a single line with start time + duration on end.
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    // Get the test file name (without extension) for folder name
    const testFile = path.basename(test.location.file, '.test.ts');
    const folderPath = path.join(this.outputDir, testFile);

    // Create folder if it doesn't exist
    if (!fs.existsSync(folderPath)) {
      fs.mkdirSync(folderPath, { recursive: true });
    }

    // Create safe filename from test title
    const safeTitle = this.sanitizeFilename(test.title);
    const filePath = path.join(folderPath, `${safeTitle}.txt`);

    // Build content
    const content = this.buildTestOutput(test, result);

    // Write to file
    fs.writeFileSync(filePath, content, 'utf-8');

    const timestamp = result.startTime.toISOString();
    const durationSeconds = (result.duration / 1000).toFixed(1);
    const titlePath = test.titlePath().join(' > ');
    console.warn(`[${timestamp}] ${titlePath} (${durationSeconds}s, ${result.status})`);

    // Store for summary
    this.testResults.set(test.id, { test, result });
  }

  onEnd(result: FullResult): Promise<void> | void {
    const endTime = new Date();
    const duration = (endTime.getTime() - this.startTime.getTime()) / 1000;

    // Write summary file
    const summaryPath = path.join(this.outputDir, 'summary.txt');
    const summary = this.buildSummary(result, duration);
    fs.writeFileSync(summaryPath, summary, 'utf-8');

    console.warn(`[TextFileReporter] Results saved to ${path.resolve(this.outputDir)}`);
    console.warn(`[TextFileReporter] Summary: ${summaryPath}`);
  }

  private sanitizeFilename(title: string): string {
    return title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .substring(0, 100);
  }

  /**
   * Unescape literal \n and \t sequences in log output.
   */
  private unescapeLogOutput(text: string): string {
    return text.replace(/\\n/g, '\n').replace(/\\t/g, '\t');
  }

  private buildTestOutput(test: TestCase, result: TestResult): string {
    const lines: string[] = [];

    // Header
    lines.push('='.repeat(80));
    lines.push(`TEST: ${test.title}`);
    lines.push('='.repeat(80));
    lines.push('');

    // Test info
    lines.push(`File: ${test.location.file}:${test.location.line}`);
    lines.push(`Status: ${result.status.toUpperCase()}`);
    lines.push(`Duration: ${result.duration}ms`);
    lines.push(`Retry: ${result.retry}`);
    lines.push(`Start Time: ${result.startTime.toISOString()}`);
    lines.push('');

    // Parent describe blocks
    const parents: string[] = [];
    let parent: Suite | undefined = test.parent;
    while (parent) {
      if (parent.title) {
        parents.unshift(parent.title);
      }
      parent = parent.parent;
    }
    if (parents.length > 0) {
      lines.push(`Suite: ${parents.join(' > ')}`);
      lines.push('');
    }

    // Stdout
    if (result.stdout.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('STDOUT:');
      lines.push('-'.repeat(40));
      for (const output of result.stdout) {
        const text = typeof output === 'string' ? output : output.toString('utf-8');
        lines.push(this.unescapeLogOutput(text));
      }
      lines.push('');
    }

    // Stderr
    if (result.stderr.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('STDERR:');
      lines.push('-'.repeat(40));
      for (const output of result.stderr) {
        const text = typeof output === 'string' ? output : output.toString('utf-8');
        lines.push(this.unescapeLogOutput(text));
      }
      lines.push('');
    }

    // Errors
    if (result.errors.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('ERRORS:');
      lines.push('-'.repeat(40));
      for (const error of result.errors) {
        if (error.message) {
          lines.push(`Message: ${error.message}`);
        }
        if (error.stack) {
          lines.push('Stack:');
          lines.push(error.stack);
        }
        lines.push('');
      }
    }

    // Attachments
    if (result.attachments.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('ATTACHMENTS:');
      lines.push('-'.repeat(40));
      for (const attachment of result.attachments) {
        lines.push('');
        lines.push(`- ${attachment.name}: ${attachment.contentType}`);
        if (attachment.body) {
          const bodyStr = attachment.body.toString('utf-8');
          lines.push('');
          if (bodyStr.length < 10000) {
            lines.push(this.unescapeLogOutput(bodyStr));
          } else {
            lines.push(`[Content too large: ${bodyStr.length} bytes]`);
          }
        }
      }
      lines.push('');
    }

    lines.push('='.repeat(80));
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('='.repeat(80));

    return lines.join('\n');
  }

  private buildSummary(result: FullResult, durationSeconds: number): string {
    const lines: string[] = [];

    lines.push('='.repeat(80));
    lines.push('TEST RUN SUMMARY');
    lines.push('='.repeat(80));
    lines.push('');
    lines.push(`Start Time: ${this.startTime.toISOString()}`);
    lines.push(`End Time: ${new Date().toISOString()}`);
    lines.push(`Duration: ${durationSeconds.toFixed(2)}s`);
    lines.push(`Status: ${result.status.toUpperCase()}`);
    lines.push('');

    // Count by status
    const counts = {
      passed: 0,
      failed: 0,
      timedOut: 0,
      skipped: 0,
      interrupted: 0,
    };

    for (const { result: testResult } of this.testResults.values()) {
      counts[testResult.status]++;
    }

    lines.push('-'.repeat(40));
    lines.push('RESULTS:');
    lines.push('-'.repeat(40));
    lines.push(`  Passed:      ${counts.passed}`);
    lines.push(`  Failed:      ${counts.failed}`);
    lines.push(`  Timed Out:   ${counts.timedOut}`);
    lines.push(`  Skipped:     ${counts.skipped}`);
    lines.push(`  Interrupted: ${counts.interrupted}`);
    lines.push(`  Total:       ${this.testResults.size}`);
    lines.push('');

    // List failed tests
    const failedTests = Array.from(this.testResults.values()).filter(
      ({ result }) => result.status === 'failed' || result.status === 'timedOut'
    );

    if (failedTests.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('FAILED TESTS:');
      lines.push('-'.repeat(40));
      for (const { test, result: testResult } of failedTests) {
        lines.push(`  [${testResult.status.toUpperCase()}] ${test.title}`);
        lines.push(`    File: ${test.location.file}:${test.location.line}`);
        if (testResult.errors.length > 0 && testResult.errors[0].message) {
          const msg = testResult.errors[0].message.split('\n')[0];
          lines.push(`    Error: ${msg.substring(0, 100)}`);
        }
      }
      lines.push('');
    }

    // List all tests by file
    lines.push('-'.repeat(40));
    lines.push('ALL TESTS BY FILE:');
    lines.push('-'.repeat(40));

    const byFile = new Map<string, { test: TestCase; result: TestResult }[]>();
    for (const entry of this.testResults.values()) {
      const file = path.basename(entry.test.location.file);
      if (!byFile.has(file)) {
        byFile.set(file, []);
      }
      byFile.get(file)!.push(entry);
    }

    const sortedFiles = Array.from(byFile.keys()).sort();
    for (const file of sortedFiles) {
      lines.push('');
      lines.push(`  ${file}:`);
      const tests = byFile.get(file)!;
      for (const { test, result: testResult } of tests) {
        const statusIcon =
          testResult.status === 'passed'
            ? '✓'
            : testResult.status === 'failed'
              ? '✗'
              : testResult.status === 'skipped'
                ? '○'
                : '!';
        lines.push(`    ${statusIcon} ${test.title} (${testResult.duration}ms)`);
      }
    }

    lines.push('');
    lines.push('='.repeat(80));
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('='.repeat(80));

    return lines.join('\n');
  }
}
