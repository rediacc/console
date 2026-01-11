import { Page, TestInfo } from '@playwright/test';
import fs from 'fs';
import path from 'path';
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
  details?: Record<string, any>;
}

export interface TestMetrics {
  responseTime?: number;
  pageLoadTime?: number;
  resourceCount?: number;
  memoryUsage?: number;
  networkFailures?: number;
}

export class TestReporter {
  private page: Page;
  private testInfo: TestInfo;
  private steps: TestStep[] = [];
  private reportDir: string;
  private testStartTime: Date;
  private metrics: TestMetrics = {};

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

  async startStep(stepName: string, details?: Record<string, any>): Promise<TestStep> {
    // Add separator line before the first step
    if (!this.hasStartedFirstStep) {
      console.log('═══════════════════════════════════════════════════════════════════');
      console.log(`🎯 TEST : ${this.testInfo.title}`);
      console.log('═══════════════════════════════════════════════════════════════════');
      this.hasStartedFirstStep = true;
    }

    const step: TestStep = {
      name: stepName,
      status: 'passed',
      startTime: new Date(),
      details
    };

    this.steps.push(step);
    console.log(`${this.getRetryLabel()}   🚀 Starting step: ${stepName}`);

    return step;
  }

  async completeStep(stepName: string, status: 'passed' | 'failed' | 'skipped', error?: string): Promise<void> {
    const step = this.steps.find(s => s.name === stepName && !s.endTime);
    
    if (step) {
      step.endTime = new Date();
      step.status = status;
      step.duration = step.endTime.getTime() - step.startTime.getTime();
      
      if (error) {
        step.error = error;
      }

      const statusEmoji = status === 'passed' ? '✅' : status === 'failed' ? '❌' : '⏭️';
      console.log(`${this.getRetryLabel()}   ${statusEmoji} Completed step: ${stepName} (${step.duration}ms)`);
    }
  }

  async addStepScreenshot(stepName: string, screenshotPath: string): Promise<void> {
    const step = this.steps.find(s => s.name === stepName);
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
        const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
        const resources = performance.getEntriesByType('resource');

        return {
          pageLoadTime: navigation ? navigation.loadEventEnd - navigation.fetchStart : 0,
          responseTime: navigation ? navigation.responseEnd - navigation.requestStart : 0,
          resourceCount: resources.length,
          networkFailures: resources.filter((r: any) => r.transferSize === 0).length
        };
      });

      this.metrics = { ...this.metrics, ...performanceMetrics };

      if ('memory' in performance && !this.page.isClosed()) {
        const memoryInfo = await this.page.evaluate(() => (performance as any).memory);
        if (memoryInfo) {
          this.metrics.memoryUsage = memoryInfo.usedJSHeapSize;
        }
      }
    } catch (error) {
      // Silently handle page closure errors to avoid noisy logs on test failures
      const errorMessage = String(error);
      if (!errorMessage.includes('Target page, context or browser has been closed')) {
        console.warn(`⚠️ Failed to collect performance metrics: ${error}`);
      }
    }
  }

  async recordNetworkActivity(): Promise<void> {
    const networkLogs: any[] = [];

    this.page.on('request', request => {
      networkLogs.push({
        type: 'request',
        method: request.method(),
        url: request.url(),
        headers: request.headers(),
        timestamp: new Date().toISOString()
      });
    });

    this.page.on('response', response => {
      networkLogs.push({
        type: 'response',
        status: response.status(),
        url: response.url(),
        headers: response.headers(),
        timestamp: new Date().toISOString()
      });
    });

    this.page.on('requestfailed', request => {
      networkLogs.push({
        type: 'failed',
        method: request.method(),
        url: request.url(),
        failure: request.failure(),
        timestamp: new Date().toISOString()
      });
    });

    const networkLogPath = path.join(this.reportDir, `network-${this.getTestFileName()}.json`);
    fs.writeFileSync(networkLogPath, JSON.stringify(networkLogs, null, 2));
  }

  async recordConsoleActivity(): Promise<void> {
    const consoleLogs: any[] = [];

    this.page.on('console', message => {
      consoleLogs.push({
        type: message.type(),
        text: message.text(),
        location: message.location(),
        timestamp: new Date().toISOString()
      });
    });

    this.page.on('pageerror', error => {
      consoleLogs.push({
        type: 'error',
        text: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString()
      });
    });

    const consoleLogPath = path.join(this.reportDir, `console-${this.getTestFileName()}.json`);
    fs.writeFileSync(consoleLogPath, JSON.stringify(consoleLogs, null, 2));
  }

  async generateDetailedReport(): Promise<string> {
    await this.recordMetrics();

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
        tags: this.testInfo.tags
      },
      execution: {
        startTime: this.testStartTime.toISOString(),
        endTime: new Date().toISOString(),
        duration: Date.now() - this.testStartTime.getTime(),
        url: this.page.isClosed() ? 'page closed' : this.page.url(),
        viewport: this.page.isClosed() ? null : await this.page.viewportSize(),
        userAgent: this.page.isClosed() ? 'page closed' : await this.page.evaluate(() => navigator.userAgent)
      },
      steps: this.steps,
      metrics: this.metrics,
      environment: {
        baseURL: requireEnvVar('BASE_URL'),
        nodeVersion: process.version,
        platform: process.platform,
        ci: !!process.env.CI
      },
      errors: this.testInfo.errors || []
    };

    const reportPath = path.join(this.reportDir, `detailed-${this.getTestFileName()}.json`);
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log(`═══════════════════════════════════════════════════════════════════`);
    console.log(`📊 Report: ${reportPath}`);
    console.log(`═══════════════════════════════════════════════════════════════════`);
    return reportPath;
  }

  async generateHTMLReport(): Promise<string> {
    const detailedReportPath = await this.generateDetailedReport();
    const report = JSON.parse(fs.readFileSync(detailedReportPath, 'utf8'));

    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - ${report.testInfo.title}</title>
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
        <h2>${report.testInfo.title}</h2>
        <p><strong>Status:</strong> ${report.testInfo.status}</p>
        <p><strong>Duration:</strong> ${report.testInfo.duration}ms</p>
        <p><strong>Project:</strong> ${report.testInfo.project}</p>
        <p><strong>URL:</strong> ${report.execution.url}</p>
    </div>

    <div class="section">
        <h3>Performance Metrics</h3>
        <div class="metrics">
            ${Object.entries(report.metrics).map(([key, value]) => `
                <div class="metric-card">
                    <h4>${key.replace(/([A-Z])/g, ' $1').toUpperCase()}</h4>
                    <p>${typeof value === 'number' ? value.toLocaleString() : value}</p>
                </div>
            `).join('')}
        </div>
    </div>

    <div class="section">
        <h3>Test Steps</h3>
        ${report.steps.map((step: any) => `
            <div class="step ${step.status}">
                <h4>${step.name}</h4>
                <p><strong>Status:</strong> ${step.status}</p>
                <p><strong>Duration:</strong> ${step.duration || 0}ms</p>
                ${step.error ? `<div class="error">Error: ${step.error}</div>` : ''}
                ${step.screenshot ? `<img src="${step.screenshot}" alt="Screenshot" class="screenshot">` : ''}
            </div>
        `).join('')}
    </div>

    ${report.errors.length > 0 ? `
        <div class="section">
            <h3>Errors</h3>
            ${report.errors.map((error: any) => `<div class="error">${error.message}</div>`).join('')}
        </div>
    ` : ''}
</body>
</html>`;

    const htmlPath = path.join(this.reportDir, `report-${this.getTestFileName()}.html`);
    fs.writeFileSync(htmlPath, html);

    console.log(`   📄 HTML report generated: ${htmlPath}`);
    return htmlPath;
  }

  private getTestFileName(): string {
    const timestamp = format(new Date(), 'yyyy-MM-dd_HH-mm-ss');
    const testName = this.testInfo.title.replace(/[^a-zA-Z0-9\-_]/g, '_').toLowerCase();
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
    const passedSteps = this.steps.filter(s => s.status === 'passed').length;
    const failedSteps = this.steps.filter(s => s.status === 'failed').length;
    const skippedSteps = this.steps.filter(s => s.status === 'skipped').length;
    
    console.log('═══════════════════════════════════════════════════════════════════');
    console.log(`🏁 Test completed: ${this.testInfo.title}`);
    console.log(`   ⏱️  Total duration: ${totalDuration < 1000 ? `${totalDuration}ms` : `${(totalDuration / 1000).toFixed(2)}s`}`);
    console.log(`   📊 Steps: ${passedSteps} passed, ${failedSteps} failed, ${skippedSteps} skipped`);
    console.log('═══════════════════════════════════════════════════════════════════');
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