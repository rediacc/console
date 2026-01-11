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
  private readonly outputDir: string;
  private readonly testResults: Map<string, { test: TestCase; result: TestResult }> = new Map();
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
      .replaceAll(/[^a-z0-9]+/g, '-')
      .replaceAll(/^-+|-+$/g, '')
      .substring(0, 100);
  }

  /**
   * Unescape literal \n and \t sequences in log output.
   */
  private unescapeLogOutput(text: string): string {
    return text.replaceAll('\\n', '\n').replaceAll('\\t', '\t');
  }

  /**
   * Convert output buffer or string to unescaped text.
   */
  private formatOutput(output: string | Buffer): string {
    const text = typeof output === 'string' ? output : output.toString('utf-8');
    return this.unescapeLogOutput(text);
  }

  /**
   * Build header section for test output.
   */
  private buildTestHeader(test: TestCase, result: TestResult): string[] {
    return [
      '='.repeat(80),
      `TEST: ${test.title}`,
      '='.repeat(80),
      '',
      `File: ${test.location.file}:${test.location.line}`,
      `Status: ${result.status.toUpperCase()}`,
      `Duration: ${result.duration}ms`,
      `Retry: ${result.retry}`,
      `Start Time: ${result.startTime.toISOString()}`,
      '',
    ];
  }

  /**
   * Build suite path section if test has parent describe blocks.
   */
  private buildSuiteSection(test: TestCase): string[] {
    const parents: string[] = [];
    let parent: Suite | undefined = test.parent;
    while (parent) {
      if (parent.title) {
        parents.unshift(parent.title);
      }
      parent = parent.parent;
    }

    if (parents.length === 0) {
      return [];
    }

    return [`Suite: ${parents.join(' > ')}`, ''];
  }

  /**
   * Build a labeled section with outputs (stdout/stderr).
   */
  private buildOutputSection(label: string, outputs: (string | Buffer)[]): string[] {
    if (outputs.length === 0) {
      return [];
    }

    const lines: string[] = ['-'.repeat(40), `${label}:`, '-'.repeat(40)];
    for (const output of outputs) {
      lines.push(this.formatOutput(output));
    }
    lines.push('');
    return lines;
  }

  /**
   * Build errors section from test result.
   */
  private buildErrorsSection(errors: TestResult['errors']): string[] {
    if (errors.length === 0) {
      return [];
    }

    const lines: string[] = ['-'.repeat(40), 'ERRORS:', '-'.repeat(40)];
    for (const error of errors) {
      if (error.message) {
        lines.push(`Message: ${error.message}`);
      }
      if (error.stack) {
        lines.push('Stack:', error.stack);
      }
      lines.push('');
    }
    return lines;
  }

  /**
   * Format a single attachment's body content.
   */
  private formatAttachmentBody(body: Buffer): string {
    const bodyStr = body.toString('utf-8');
    if (bodyStr.length < 10000) {
      return this.unescapeLogOutput(bodyStr);
    }
    return `[Content too large: ${bodyStr.length} bytes]`;
  }

  /**
   * Build attachments section from test result.
   */
  private buildAttachmentsSection(attachments: TestResult['attachments']): string[] {
    if (attachments.length === 0) {
      return [];
    }

    const lines: string[] = ['-'.repeat(40), 'ATTACHMENTS:', '-'.repeat(40)];
    for (const attachment of attachments) {
      lines.push('', `- ${attachment.name}: ${attachment.contentType}`);
      if (attachment.body) {
        lines.push('', this.formatAttachmentBody(attachment.body));
      }
    }
    lines.push('');
    return lines;
  }

  /**
   * Build footer section for test output.
   */
  private buildTestFooter(): string[] {
    return ['='.repeat(80), `Generated: ${new Date().toISOString()}`, '='.repeat(80)];
  }

  private buildTestOutput(test: TestCase, result: TestResult): string {
    const sections: string[][] = [
      this.buildTestHeader(test, result),
      this.buildSuiteSection(test),
      this.buildOutputSection('STDOUT', result.stdout),
      this.buildOutputSection('STDERR', result.stderr),
      this.buildErrorsSection(result.errors),
      this.buildAttachmentsSection(result.attachments),
      this.buildTestFooter(),
    ];

    return sections.flat().join('\n');
  }

  /**
   * Build summary header section with timing information.
   */
  private buildSummaryHeader(result: FullResult, durationSeconds: number): string[] {
    return [
      '='.repeat(80),
      'TEST RUN SUMMARY',
      '='.repeat(80),
      '',
      `Start Time: ${this.startTime.toISOString()}`,
      `End Time: ${new Date().toISOString()}`,
      `Duration: ${durationSeconds.toFixed(2)}s`,
      `Status: ${result.status.toUpperCase()}`,
      '',
    ];
  }

  /**
   * Count test results by status.
   */
  private countResultsByStatus(): Record<string, number> {
    const counts: Record<string, number> = {
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

  /**
   * Build results counts section.
   */
  private buildResultsCountSection(counts: Record<string, number>): string[] {
    return [
      '-'.repeat(40),
      'RESULTS:',
      '-'.repeat(40),
      `  Passed:      ${counts.passed}`,
      `  Failed:      ${counts.failed}`,
      `  Timed Out:   ${counts.timedOut}`,
      `  Skipped:     ${counts.skipped}`,
      `  Interrupted: ${counts.interrupted}`,
      `  Total:       ${this.testResults.size}`,
      '',
    ];
  }

  /**
   * Format a single failed test entry.
   */
  private formatFailedTestEntry(test: TestCase, testResult: TestResult): string[] {
    const lines: string[] = [
      `  [${testResult.status.toUpperCase()}] ${test.title}`,
      `    File: ${test.location.file}:${test.location.line}`,
    ];

    const hasErrorMessage = testResult.errors.length > 0 && testResult.errors[0].message;
    if (hasErrorMessage) {
      const msg = testResult.errors[0].message.split('\n')[0];
      lines.push(`    Error: ${msg.substring(0, 100)}`);
    }

    return lines;
  }

  /**
   * Build failed tests section.
   */
  private buildFailedTestsSection(): string[] {
    const failedTests = Array.from(this.testResults.values()).filter(
      ({ result }) => result.status === 'failed' || result.status === 'timedOut'
    );

    if (failedTests.length === 0) {
      return [];
    }

    const lines: string[] = ['-'.repeat(40), 'FAILED TESTS:', '-'.repeat(40)];
    for (const { test, result: testResult } of failedTests) {
      lines.push(...this.formatFailedTestEntry(test, testResult));
    }
    lines.push('');
    return lines;
  }

  /**
   * Group test results by file name.
   */
  private groupResultsByFile(): Map<string, { test: TestCase; result: TestResult }[]> {
    const byFile = new Map<string, { test: TestCase; result: TestResult }[]>();
    for (const entry of this.testResults.values()) {
      const file = path.basename(entry.test.location.file);
      const existing = byFile.get(file) ?? [];
      existing.push(entry);
      byFile.set(file, existing);
    }
    return byFile;
  }

  /**
   * Lookup table for status icons.
   */
  private static readonly STATUS_ICONS: Record<string, string> = {
    passed: '✓',
    failed: '✗',
    skipped: '○',
  };

  /**
   * Get status icon for a test result status.
   */
  private getStatusIcon(status: string): string {
    return TextFileReporter.STATUS_ICONS[status] ?? '!';
  }

  /**
   * Build tests by file section.
   */
  private buildTestsByFileSection(): string[] {
    const lines: string[] = ['-'.repeat(40), 'ALL TESTS BY FILE:', '-'.repeat(40)];

    const byFile = this.groupResultsByFile();
    const sortedFiles = Array.from(byFile.keys()).sort();

    for (const file of sortedFiles) {
      lines.push('', `  ${file}:`);
      const tests = byFile.get(file)!;
      for (const { test, result: testResult } of tests) {
        const statusIcon = this.getStatusIcon(testResult.status);
        lines.push(`    ${statusIcon} ${test.title} (${testResult.duration}ms)`);
      }
    }

    return lines;
  }

  /**
   * Build summary footer section.
   */
  private buildSummaryFooter(): string[] {
    return ['', '='.repeat(80), `Generated: ${new Date().toISOString()}`, '='.repeat(80)];
  }

  private buildSummary(result: FullResult, durationSeconds: number): string {
    const counts = this.countResultsByStatus();

    const sections: string[][] = [
      this.buildSummaryHeader(result, durationSeconds),
      this.buildResultsCountSection(counts),
      this.buildFailedTestsSection(),
      this.buildTestsByFileSection(),
      this.buildSummaryFooter(),
    ];

    return sections.flat().join('\n');
  }
}
