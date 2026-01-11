import { Page, TestInfo } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { format } from 'date-fns';

export interface ScreenshotOptions {
  fullPage?: boolean;
  clip?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  quality?: number;
  type?: 'png' | 'jpeg';
  timeout?: number;
}

export class ScreenshotManager {
  private page: Page;
  private testInfo: TestInfo;
  private screenshotDir: string;
  private testCaseDir: string;

  constructor(page: Page, testInfo: TestInfo) {
    this.page = page;
    this.testInfo = testInfo;
    this.screenshotDir = 'screenshots';
    this.testCaseDir = this.createTestCaseDirectory();
  }

  private createTestCaseDirectory(): string {
    const timestamp = format(new Date(), 'yyyy-MM-dd_HH-mm-ss');
    const testName = this.sanitizeFileName(this.testInfo.title);
    const projectName = this.testInfo.project.name;
    
    const dirName = `${timestamp}_${projectName}_${testName}`;
    const fullPath = path.join(this.screenshotDir, dirName);
    
    if (!fs.existsSync(fullPath)) {
      fs.mkdirSync(fullPath, { recursive: true });
    }
    
    return fullPath;
  }

  private sanitizeFileName(fileName: string): string {
    return fileName
      .replace(/[^a-zA-Z0-9\-_\.]/g, '_')
      .replace(/_+/g, '_')
      .toLowerCase();
  }

  async captureStep(stepName: string, options: ScreenshotOptions = {}): Promise<string> {
    const timestamp = format(new Date(), 'HH-mm-ss-SSS');
    const sanitizedStepName = this.sanitizeFileName(stepName);
    const fileName = `${timestamp}_${sanitizedStepName}.png`;
    const filePath = path.join(this.testCaseDir, fileName);

    const defaultOptions: ScreenshotOptions = {
      fullPage: true,
      type: 'png',
      timeout: 30000,
      ...options
    };

    try {
      await this.page.screenshot({
        path: filePath,
        ...defaultOptions
      });

      // Removed console.log for cleaner output - screenshot info is captured in step reporting
      return filePath;
    } catch (error) {
      console.error(`❌ Failed to capture screenshot: ${error}`);
      throw error;
    }
  }

  async captureElementScreenshot(
    selector: string, 
    stepName: string, 
    options: ScreenshotOptions = {}
  ): Promise<string> {
    const timestamp = format(new Date(), 'HH-mm-ss-SSS');
    const sanitizedStepName = this.sanitizeFileName(stepName);
    const fileName = `${timestamp}_element_${sanitizedStepName}.png`;
    const filePath = path.join(this.testCaseDir, fileName);

    const element = this.page.locator(selector);
    
    try {
      await element.screenshot({
        path: filePath,
        type: options.type || 'png',
        timeout: options.timeout || 30000
      });

      // Removed console.log for cleaner output
      return filePath;
    } catch (error) {
      console.error(`❌ Failed to capture element screenshot: ${error}`);
      throw error;
    }
  }

  async captureComparison(
    stepName: string,
    beforeAction: () => Promise<void>,
    afterAction: () => Promise<void>
  ): Promise<{ before: string; after: string }> {
    const beforePath = await this.captureStep(`${stepName}_before`);
    
    await beforeAction();
    await this.page.waitForLoadState('networkidle');
    
    const afterPath = await this.captureStep(`${stepName}_after`);
    
    await afterAction();

    return {
      before: beforePath,
      after: afterPath
    };
  }

  async capturePageFlow(steps: Array<{ name: string; action: () => Promise<void> }>): Promise<string[]> {
    const screenshots: string[] = [];

    for (const [index, step] of steps.entries()) {
      const stepNumber = String(index + 1).padStart(2, '0');
      const screenshotPath = await this.captureStep(`${stepNumber}_${step.name}`);
      screenshots.push(screenshotPath);
      
      await step.action();
      await this.page.waitForLoadState('networkidle');
    }

    return screenshots;
  }

  async captureError(errorMessage: string): Promise<string> {
    const timestamp = format(new Date(), 'HH-mm-ss-SSS');
    const fileName = `${timestamp}_ERROR.png`;
    const filePath = path.join(this.testCaseDir, fileName);

    try {
      await this.page.screenshot({
        path: filePath,
        fullPage: true,
        type: 'png'
      });

      const errorLogPath = path.join(this.testCaseDir, `${timestamp}_error.log`);
      fs.writeFileSync(errorLogPath, `Error: ${errorMessage}\nURL: ${this.page.url()}\nTimestamp: ${new Date().toISOString()}`);

      // Keep error screenshot log as it's important for debugging
      return filePath;
    } catch (screenshotError) {
      console.error(`❌ Failed to capture error screenshot: ${screenshotError}`);
      throw screenshotError;
    }
  }

  async captureViewports(): Promise<string[]> {
    const viewports = [
      { name: 'desktop', width: 1440, height: 900 },
      { name: 'tablet', width: 768, height: 1024 },
      { name: 'mobile', width: 375, height: 667 }
    ];

    const screenshots: string[] = [];

    for (const viewport of viewports) {
      await this.page.setViewportSize({ width: viewport.width, height: viewport.height });
      await this.page.waitForTimeout(1000);
      
      const screenshotPath = await this.captureStep(`viewport_${viewport.name}`);
      screenshots.push(screenshotPath);
    }

    return screenshots;
  }

  getTestCaseDirectory(): string {
    return this.testCaseDir;
  }

  async generateTestReport(): Promise<void> {
    const reportData = {
      testInfo: {
        title: this.testInfo.title,
        file: this.testInfo.file,
        project: this.testInfo.project.name,
        status: this.testInfo.status,
        duration: this.testInfo.duration,
        timeout: this.testInfo.timeout
      },
      screenshots: this.getScreenshotList(),
      environment: {
        url: this.page.url(),
        userAgent: await this.page.evaluate(() => navigator.userAgent),
        viewport: await this.page.viewportSize()
      },
      timestamp: new Date().toISOString()
    };

    const reportPath = path.join(this.testCaseDir, 'test-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(reportData, null, 2));
  }

  private getScreenshotList(): string[] {
    try {
      return fs.readdirSync(this.testCaseDir)
        .filter(file => file.endsWith('.png') || file.endsWith('.jpg'))
        .sort();
    } catch {
      return [];
    }
  }
}