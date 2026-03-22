import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter';
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
    private readonly outputDir;
    private readonly testResults;
    private startTime;
    constructor(options?: {
        outputDir?: string;
    });
    onBegin(_config: FullConfig, _suite: Suite): void;
    onTestBegin(_test: TestCase): void;
    onTestEnd(test: TestCase, result: TestResult): void;
    onEnd(result: FullResult): Promise<void> | void;
    private sanitizeFilename;
    /**
     * Unescape literal \n and \t sequences in log output.
     * Go loggers often escape newlines in msg= fields.
     */
    private unescapeLogOutput;
    private addTestHeader;
    private addSuiteInfo;
    private addOutputSection;
    private addErrors;
    private formatAttachmentBody;
    private addAttachments;
    private buildTestOutput;
    private addSummaryHeader;
    private countTestResults;
    private addResultCounts;
    private addFailedTests;
    private getStatusIcon;
    private groupTestsByFile;
    private addAllTestsByFile;
    private buildSummary;
}
//# sourceMappingURL=TextFileReporter.d.ts.map
