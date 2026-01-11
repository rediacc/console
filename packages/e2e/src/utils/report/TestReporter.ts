import fs from 'node:fs';
import path from 'node:path';
import { Page, TestInfo } from '@playwright/test';
import { format } from 'date-fns';
import { requireEnvVar } from '../env';

export interface TestStep {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration?: number;
  startTime: Date;
  endTime?: Date;
  error?: string;
  screenshot?: string;
  details?: Record<string, unknown>;
}

export interface TestMetrics {
  responseTime?: number;
  pageLoadTime?: number;
  resourceCount?: number;
  memoryUsage?: number;
  networkFailures?: number;
}

interface NetworkLog {
  type: string;
  method?: string;
  status?: number;
  url: string;
  headers?: Record<string, string>;
  failure?: { errorText: string } | null;
  timestamp: string;
}

interface ConsoleLog {
  type: string;
  text: string;
  location?: { url: string; lineNumber: number; columnNumber: number };
  stack?: string;
  timestamp: string;
}

export class TestReporter {
  private readonly page: Page;
  private readonly testInfo: TestInfo;
  private readonly steps: TestStep[] = [];
  private readonly reportDir: string;
  private readonly testStartTime: Date;
  private metrics: TestMetrics = {};
  private hasStartedFirstStep = false;

  constructor(page: Page, testInfo: TestInfo) {
    this.page = page;
    this.testInfo = testInfo;
    this.testStartTime = new Date();
    this.reportDir = 'reports';
    this.ensureReportDirectory();
  }

  private ensureReportDirectory(): void {
    if (!fs.existsSync(this.reportDir)) {
      fs.mkdirSync(this.reportDir, { recursive: true });
    }
  }

  private getRetryLabel(): string {
    const maxRetries = this.testInfo.project.retries;
    const currentRetry = this.testInfo.retry;

    // Only show retry label if we're actually on a retry (not the first attempt)
    if (currentRetry === 0) return '';

    const currentAttempt = currentRetry + 1;
    const totalAttempts = maxRetries + 1;
    return `[${currentAttempt}/${totalAttempts}] `;
  }

  startStep(stepName: string, details?: Record<string, unknown>): TestStep {
    // Add separator line before the first step
    if (!this.hasStartedFirstStep) {
      console.warn('===================================================================');
      console.warn(`TEST : ${this.testInfo.title}`);
      console.warn('===================================================================');
      this.hasStartedFirstStep = true;
    }

    const step: TestStep = {
      name: stepName,
      status: 'passed',
      startTime: new Date(),
      details,
    };

    this.steps.push(step);
    console.warn(`${this.getRetryLabel()}   Starting step: ${stepName}`);

    return step;
  }

  completeStep(stepName: string, status: 'passed' | 'failed' | 'skipped', error?: string): void {
    const step = this.steps.find((s) => s.name === stepName && !s.endTime);

    if (step) {
      step.endTime = new Date();
      step.status = status;
      step.duration = step.endTime.getTime() - step.startTime.getTime();

      if (error) {
        step.error = error;
      }

      const statusLabel = this.getStatusLabel(status);
      console.warn(
        `${this.getRetryLabel()}   ${statusLabel} Completed step: ${stepName} (${step.duration}ms)`
      );
    }
  }

  private getStatusLabel(status: 'passed' | 'failed' | 'skipped'): string {
    switch (status) {
      case 'passed':
        return '[PASS]';
      case 'failed':
        return '[FAIL]';
      case 'skipped':
        return '[SKIP]';
    }
  }

  addStepScreenshot(stepName: string, screenshotPath: string): void {
    const step = this.steps.find((s) => s.name === stepName);
    if (step) {
      step.screenshot = screenshotPath;
    }
  }

  async recordMetrics(): Promise<void> {
    try {
      // Check if page is still usable before collecting metrics
      if (this.page.isClosed()) {
        return;
      }

      const performanceMetrics = await this.page.evaluate(() => {
        const navigation = performance.getEntriesByType(
          'navigation'
        )[0] as PerformanceNavigationTiming;
        const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[];

        return {
          pageLoadTime: navigation.loadEventEnd - navigation.fetchStart,
          responseTime: navigation.responseEnd - navigation.requestStart,
          resourceCount: resources.length,
          networkFailures: resources.filter((r) => r.transferSize === 0).length,
        };
      });

      this.metrics = { ...this.metrics, ...performanceMetrics };
    } catch (metricsError) {
      // Silently handle page closure errors to avoid noisy logs on test failures
      const errorMessage = String(metricsError);
      if (!errorMessage.includes('Target page, context or browser has been closed')) {
        console.warn(`Failed to collect performance metrics: ${metricsError}`);
      }
    }
  }

  recordNetworkActivity(): void {
    const networkLogs: NetworkLog[] = [];

    this.page.on('request', (request) => {
      networkLogs.push({
        type: 'request',
        method: request.method(),
        url: request.url(),
        headers: request.headers(),
        timestamp: new Date().toISOString(),
      });
    });

    this.page.on('response', (response) => {
      networkLogs.push({
        type: 'response',
        status: response.status(),
        url: response.url(),
        headers: response.headers(),
        timestamp: new Date().toISOString(),
      });
    });

    this.page.on('requestfailed', (request) => {
      networkLogs.push({
        type: 'failed',
        method: request.method(),
        url: request.url(),
        failure: request.failure(),
        timestamp: new Date().toISOString(),
      });
    });

    const networkLogPath = path.join(this.reportDir, `network-${this.getTestFileName()}.json`);
    fs.writeFileSync(networkLogPath, JSON.stringify(networkLogs, null, 2));
  }

  recordConsoleActivity(): void {
    const consoleLogs: ConsoleLog[] = [];

    this.page.on('console', (message) => {
      consoleLogs.push({
        type: message.type(),
        text: message.text(),
        location: message.location(),
        timestamp: new Date().toISOString(),
      });
    });

    this.page.on('pageerror', (error) => {
      consoleLogs.push({
        type: 'error',
        text: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
      });
    });

    const consoleLogPath = path.join(this.reportDir, `console-${this.getTestFileName()}.json`);
    fs.writeFileSync(consoleLogPath, JSON.stringify(consoleLogs, null, 2));
  }

  async generateDetailedReport(): Promise<string> {
    await this.recordMetrics();

    const pageUrl = this.page.isClosed() ? 'page closed' : this.page.url();
    const viewport = this.page.isClosed() ? null : this.page.viewportSize();
    const userAgent = this.page.isClosed()
      ? 'page closed'
      : await this.page.evaluate(() => navigator.userAgent);

    const report = {
      testInfo: {
        title: this.testInfo.title,
        file: this.testInfo.file,
        line: this.testInfo.line,
        column: this.testInfo.column,
        project: this.testInfo.project.name,
        status: this.testInfo.status,
        duration: this.testInfo.duration,
        timeout: this.testInfo.timeout,
        annotations: this.testInfo.annotations,
        tags: this.testInfo.tags,
      },
      execution: {
        startTime: this.testStartTime.toISOString(),
        endTime: new Date().toISOString(),
        duration: Date.now() - this.testStartTime.getTime(),
        url: pageUrl,
        viewport,
        userAgent,
      },
      steps: this.steps,
      metrics: this.metrics,
      environment: {
        baseURL: requireEnvVar('E2E_BASE_URL'),
        nodeVersion: process.version,
        platform: process.platform,
        ci: !!process.env.CI,
      },
      errors: this.testInfo.errors,
    };

    const reportPath = path.join(this.reportDir, `detailed-${this.getTestFileName()}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.warn('===================================================================');
    console.warn(`Report: ${reportPath}`);
    console.warn('===================================================================');
    return reportPath;
  }

  async generateHTMLReport(): Promise<string> {
    const detailedReportPath = await this.generateDetailedReport();
    const reportData = JSON.parse(fs.readFileSync(detailedReportPath, 'utf8')) as {
      testInfo: { title: string; status: string; duration: number; project: string };
      execution: { url: string };
      metrics: Record<string, unknown>;
      steps: TestStep[];
      errors: { message: string }[];
    };

    const metricsHtml = Object.entries(reportData.metrics)
      .map(
        ([key, value]) => `
                <div class="metric-card">
                    <h4>${key.replaceAll(/([A-Z])/g, ' $1').toUpperCase()}</h4>
                    <p>${typeof value === 'number' ? value.toLocaleString() : String(value)}</p>
                </div>
            `
      )
      .join('');

    const stepsHtml = reportData.steps
      .map(
        (step) => `
            <div class="step ${step.status}">
                <h4>${step.name}</h4>
                <p><strong>Status:</strong> ${step.status}</p>
                <p><strong>Duration:</strong> ${step.duration ?? 0}ms</p>
                ${step.error ? `<div class="error">Error: ${step.error}</div>` : ''}
                ${step.screenshot ? `<img src="${step.screenshot}" alt="Screenshot" class="screenshot">` : ''}
            </div>
        `
      )
      .join('');

    const errorsHtml =
      reportData.errors.length > 0
        ? `
        <div class="section">
            <h3>Errors</h3>
            ${reportData.errors.map((error) => `<div class="error">${error.message}</div>`).join('')}
        </div>
    `
        : '';

    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - ${reportData.testInfo.title}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .header { background: #f4f4f4; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .section { margin-bottom: 30px; }
        .step { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .step.passed { border-left: 5px solid #4CAF50; }
        .step.failed { border-left: 5px solid #F44336; }
        .step.skipped { border-left: 5px solid #FF9800; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .metric-card { background: #f9f9f9; padding: 15px; border-radius: 5px; text-align: center; }
        .error { background: #ffebee; color: #c62828; padding: 10px; border-radius: 5px; }
        .screenshot { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Test Report</h1>
        <h2>${reportData.testInfo.title}</h2>
        <p><strong>Status:</strong> ${reportData.testInfo.status}</p>
        <p><strong>Duration:</strong> ${reportData.testInfo.duration}ms</p>
        <p><strong>Project:</strong> ${reportData.testInfo.project}</p>
        <p><strong>URL:</strong> ${reportData.execution.url}</p>
    </div>

    <div class="section">
        <h3>Performance Metrics</h3>
        <div class="metrics">
            ${metricsHtml}
        </div>
    </div>

    <div class="section">
        <h3>Test Steps</h3>
        ${stepsHtml}
    </div>

    ${errorsHtml}
</body>
</html>`;

    const htmlPath = path.join(this.reportDir, `report-${this.getTestFileName()}.html`);
    fs.writeFileSync(htmlPath, html);

    console.warn(`   HTML report generated: ${htmlPath}`);
    return htmlPath;
  }

  private getTestFileName(): string {
    const timestamp = format(new Date(), 'yyyy-MM-dd_HH-mm-ss');
    const testName = this.testInfo.title.replaceAll(/[^a-zA-Z0-9\-_]/g, '_').toLowerCase();
    return `${timestamp}_${testName}`;
  }

  getSteps(): TestStep[] {
    return this.steps;
  }

  getMetrics(): TestMetrics {
    return this.metrics;
  }

  logTestCompletion(): void {
    const totalDuration = Date.now() - this.testStartTime.getTime();
    const passedSteps = this.steps.filter((s) => s.status === 'passed').length;
    const failedSteps = this.steps.filter((s) => s.status === 'failed').length;
    const skippedSteps = this.steps.filter((s) => s.status === 'skipped').length;

    const durationStr =
      totalDuration < 1000 ? `${totalDuration}ms` : `${(totalDuration / 1000).toFixed(2)}s`;

    console.warn('===================================================================');
    console.warn(`Test completed: ${this.testInfo.title}`);
    console.warn(`   Total duration: ${durationStr}`);
    console.warn(`   Steps: ${passedSteps} passed, ${failedSteps} failed, ${skippedSteps} skipped`);
    console.warn('===================================================================');
  }

  /**
   * Finalizes the test by generating reports and logging completion.
   * This should be called at the very end of a test, after all steps are completed.
   * Closes the browser context after completion.
   */
  async finalizeTest(): Promise<void> {
    await this.generateDetailedReport();
    this.logTestCompletion();
  }
}
