import * as fs from 'node:fs';
import * as path from 'node:path';
import type {
  FullConfig,
  FullResult,
  Reporter,
  Suite,
  TestCase,
  TestResult,
} from '@playwright/test/reporter';

const DEFAULT_OUTPUT_DIR = 'test-outputs';

/**
 * Custom Playwright reporter that saves each test's output to a text file.
 *
 * Output structure:
 *   reports/bridge-logs/
 *   ├── 01-system-checks/
 *   │   ├── ping-should-return-pong.txt
 *   │   └── check_system-should-pass.txt
 *   ├── 02-machine-setup/
 *   │   └── setup-should-not-have-shell-syntax-errors.txt
 *   └── summary.txt
 */
export default class TextFileReporter implements Reporter {
  private readonly outputDir: string;
  private readonly testResults: Map<string, { test: TestCase; result: TestResult }> = new Map();
  private startTime: Date = new Date();

  constructor(options: { outputDir?: string } = {}) {
    this.outputDir = options.outputDir ?? DEFAULT_OUTPUT_DIR;
  }

  onBegin(_config: FullConfig, _suite: Suite): void {
    this.startTime = new Date();
    // Ensure output directory exists
    fs.mkdirSync(this.outputDir, { recursive: true });

    // eslint-disable-next-line no-console
    console.log(`[TextFileReporter] Output directory: ${path.resolve(this.outputDir)}`);
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
    // eslint-disable-next-line no-console
    console.log(`[${timestamp}] ${titlePath} (${durationSeconds}s, ${result.status})`);

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

    // eslint-disable-next-line no-console
    console.log(`[TextFileReporter] Results saved to ${path.resolve(this.outputDir)}`);
    // eslint-disable-next-line no-console
    console.log(`[TextFileReporter] Summary: ${summaryPath}`);
  }

  private sanitizeFilename(title: string): string {
    return title
      .toLowerCase()
      .replaceAll(/[^a-z0-9]+/g, '-')
      .replaceAll(/^-+|-+$/g, '')
      .substring(0, 100);
  }

  /**
   * Unescape literal \n and \t sequences in log output.
   * Go loggers often escape newlines in msg= fields.
   */
  private unescapeLogOutput(text: string): string {
    return text.replaceAll('\\n', '\n').replaceAll('\\t', '\t');
  }

  private addTestHeader(lines: string[], test: TestCase, result: TestResult): void {
    lines.push('='.repeat(80));
    lines.push(`TEST: ${test.title}`);
    lines.push('='.repeat(80));
    lines.push('');

    lines.push(`File: ${test.location.file}:${test.location.line}`);
    lines.push(`Status: ${result.status.toUpperCase()}`);
    lines.push(`Duration: ${result.duration}ms`);
    lines.push(`Retry: ${result.retry}`);
    lines.push(`Start Time: ${result.startTime.toISOString()}`);
    lines.push('');
  }

  private addSuiteInfo(lines: string[], test: TestCase): void {
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
  }

  private addOutputSection(lines: string[], outputs: (string | Buffer)[], title: string): void {
    if (outputs.length > 0) {
      lines.push('-'.repeat(40));
      lines.push(`${title}:`);
      lines.push('-'.repeat(40));
      for (const output of outputs) {
        const text = typeof output === 'string' ? output : output.toString('utf-8');
        lines.push(this.unescapeLogOutput(text));
      }
      lines.push('');
    }
  }

  private addErrors(lines: string[], errors: TestResult['errors']): void {
    if (errors.length > 0) {
      lines.push('-'.repeat(40));
      lines.push('ERRORS:');
      lines.push('-'.repeat(40));
      for (const error of errors) {
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
  }

  private formatAttachmentBody(body: Buffer): string {
    const bodyStr = body.toString('utf-8');
    if (bodyStr.length < 10000) {
      return this.unescapeLogOutput(bodyStr);
    }
    return `[Content too large: ${bodyStr.length} bytes]`;
  }

  private addAttachments(lines: string[], attachments: TestResult['attachments']): void {
    if (attachments.length === 0) {
      return;
    }

    lines.push('-'.repeat(40));
    lines.push('ATTACHMENTS:');
    lines.push('-'.repeat(40));

    for (const attachment of attachments) {
      lines.push('');
      lines.push(`- ${attachment.name}: ${attachment.contentType}`);
      if (attachment.body) {
        lines.push('');
        lines.push(this.formatAttachmentBody(attachment.body));
      }
    }
    lines.push('');
  }

  private buildTestOutput(test: TestCase, result: TestResult): string {
    const lines: string[] = [];

    this.addTestHeader(lines, test, result);
    this.addSuiteInfo(lines, test);
    this.addOutputSection(lines, result.stdout, 'STDOUT');
    this.addOutputSection(lines, result.stderr, 'STDERR');
    this.addErrors(lines, result.errors);
    this.addAttachments(lines, result.attachments);

    lines.push('='.repeat(80));
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('='.repeat(80));

    return lines.join('\n');
  }

  private addSummaryHeader(lines: string[], result: FullResult, durationSeconds: number): void {
    lines.push('='.repeat(80));
    lines.push('TEST RUN SUMMARY');
    lines.push('='.repeat(80));
    lines.push('');
    lines.push(`Start Time: ${this.startTime.toISOString()}`);
    lines.push(`End Time: ${new Date().toISOString()}`);
    lines.push(`Duration: ${durationSeconds.toFixed(2)}s`);
    lines.push(`Status: ${result.status.toUpperCase()}`);
    lines.push('');
  }

  private countTestResults(): Record<TestResult['status'], number> {
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

    return counts;
  }

  private addResultCounts(lines: string[], counts: Record<TestResult['status'], number>): void {
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
  }

  private addFailedTests(lines: string[]): void {
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
  }

  private getStatusIcon(status: TestResult['status']): string {
    if (status === 'passed') {
      return '✓';
    }
    if (status === 'failed') {
      return '✗';
    }
    if (status === 'skipped') {
      return '○';
    }
    return '!';
  }

  private groupTestsByFile(): Map<string, { test: TestCase; result: TestResult }[]> {
    const byFile = new Map<string, { test: TestCase; result: TestResult }[]>();
    for (const entry of this.testResults.values()) {
      const file = path.basename(entry.test.location.file);
      if (!byFile.has(file)) {
        byFile.set(file, []);
      }
      byFile.get(file)!.push(entry);
    }
    return byFile;
  }

  private addAllTestsByFile(lines: string[]): void {
    lines.push('-'.repeat(40));
    lines.push('ALL TESTS BY FILE:');
    lines.push('-'.repeat(40));

    const byFile = this.groupTestsByFile();
    const sortedFiles = Array.from(byFile.keys()).sort();

    for (const file of sortedFiles) {
      lines.push('');
      lines.push(`  ${file}:`);
      const tests = byFile.get(file)!;
      for (const { test, result: testResult } of tests) {
        const statusIcon = this.getStatusIcon(testResult.status);
        lines.push(`    ${statusIcon} ${test.title} (${testResult.duration}ms)`);
      }
    }
  }

  private buildSummary(result: FullResult, durationSeconds: number): string {
    const lines: string[] = [];

    this.addSummaryHeader(lines, result, durationSeconds);
    const counts = this.countTestResults();
    this.addResultCounts(lines, counts);
    this.addFailedTests(lines);
    this.addAllTestsByFile(lines);

    lines.push('');
    lines.push('='.repeat(80));
    lines.push(`Generated: ${new Date().toISOString()}`);
    lines.push('='.repeat(80));

    return lines.join('\n');
  }
}
