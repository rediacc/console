import { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter';
import fs from 'fs';
import path from 'path';

interface CustomTestResult {
  title: string;
  file: string;
  project: string;
  status: string;
  duration: number;
  startTime: string;
  endTime: string;
  error?: string;
  screenshots: string[];
}

export default class CustomReporter implements Reporter {
  private startTime: Date = new Date();
  private results: CustomTestResult[] = [];
  private outputDir: string = 'reports';

  onBegin(config: FullConfig, suite: Suite) {
    console.log(`🚀 Starting test run with ${suite.allTests().length} tests`);
    this.ensureOutputDirectory();
  }

  onTestBegin(test: TestCase, result: TestResult) {
    console.log(`🧪 Starting test: ${test.title}`);
  }

  onTestEnd(test: TestCase, result: TestResult) {
    const testResult: CustomTestResult = {
      title: test.title,
      file: test.location.file,
      project: test.parent.project()?.name || 'default',
      status: result.status,
      duration: result.duration,
      startTime: result.startTime.toISOString(),
      endTime: new Date(result.startTime.getTime() + result.duration).toISOString(),
      screenshots: this.extractScreenshots(result)
    };

    if (result.error) {
      testResult.error = result.error.message;
    }

    this.results.push(testResult);

    const statusEmoji = result.status === 'passed' ? '✅' : 
                       result.status === 'failed' ? '❌' : 
                       result.status === 'skipped' ? '⏭️' : '❓';
    
    console.log(`${statusEmoji} Test completed: ${test.title} (${result.duration}ms)`);
  }

  onEnd(result: FullResult) {
    const endTime = new Date();
    const totalDuration = endTime.getTime() - this.startTime.getTime();

    const summary = {
      timestamp: endTime.toISOString(),
      totalDuration,
      status: result.status,
      stats: {
        total: this.results.length,
        passed: this.results.filter(r => r.status === 'passed').length,
        failed: this.results.filter(r => r.status === 'failed').length,
        skipped: this.results.filter(r => r.status === 'skipped').length,
        timedOut: this.results.filter(r => r.status === 'timedOut').length
      },
      results: this.results
    };

    this.saveJsonReport(summary);
    this.generateHTMLSummary(summary);
    this.printConsoleSummary(summary);
  }

  private extractScreenshots(result: TestResult): string[] {
    const screenshots: string[] = [];
    
    for (const attachment of result.attachments) {
      if (attachment.name === 'screenshot' && attachment.path) {
        screenshots.push(attachment.path);
      }
    }

    return screenshots;
  }

  private ensureOutputDirectory(): void {
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }
  }

  private saveJsonReport(summary: any): void {
    const reportPath = path.join(this.outputDir, 'custom-test-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(summary, null, 2));
    console.log(`📊 Custom JSON report saved: ${reportPath}`);
  }

  private generateHTMLSummary(summary: any): void {
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Summary Report</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            line-height: 1.6; 
            color: #333; 
            background: #f5f5f5; 
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px; 
        }
        .header { 
            background: white; 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
            margin-bottom: 30px; 
            text-align: center;
        }
        .stats { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 20px; 
            margin-bottom: 30px; 
        }
        .stat-card { 
            background: white; 
            padding: 25px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
            text-align: center; 
        }
        .stat-number { 
            font-size: 2.5em; 
            font-weight: bold; 
            margin-bottom: 10px; 
        }
        .passed { color: #4CAF50; }
        .failed { color: #F44336; }
        .skipped { color: #FF9800; }
        .total { color: #2196F3; }
        .results-table { 
            background: white; 
            border-radius: 10px; 
            overflow: hidden; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
        }
        th, td { 
            padding: 15px; 
            text-align: left; 
            border-bottom: 1px solid #ddd; 
        }
        th { 
            background: #f8f9fa; 
            font-weight: 600; 
        }
        .status-badge { 
            padding: 5px 10px; 
            border-radius: 15px; 
            color: white; 
            font-size: 0.9em; 
        }
        .status-passed { background: #4CAF50; }
        .status-failed { background: #F44336; }
        .status-skipped { background: #FF9800; }
        .duration { color: #666; }
        .screenshots { max-width: 200px; }
        .screenshot-link { 
            display: inline-block; 
            margin: 2px; 
            padding: 2px 8px; 
            background: #e3f2fd; 
            color: #1976d2; 
            text-decoration: none; 
            border-radius: 3px; 
            font-size: 0.8em;
        }
        .error { 
            background: #ffebee; 
            color: #c62828; 
            padding: 10px; 
            border-radius: 5px; 
            font-size: 0.9em; 
            max-width: 300px; 
            word-break: break-word;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 Test Summary Report</h1>
            <p>Generated on ${summary.timestamp}</p>
            <p>Total Duration: ${Math.round(summary.totalDuration / 1000)}s</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number total">${summary.stats.total}</div>
                <div>Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-number passed">${summary.stats.passed}</div>
                <div>Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number failed">${summary.stats.failed}</div>
                <div>Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number skipped">${summary.stats.skipped}</div>
                <div>Skipped</div>
            </div>
        </div>

        <div class="results-table">
            <table>
                <thead>
                    <tr>
                        <th>Test</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Project</th>
                        <th>Screenshots</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    ${summary.results.map((result: any) => `
                        <tr>
                            <td><strong>${result.title}</strong></td>
                            <td>
                                <span class="status-badge status-${result.status}">
                                    ${result.status.toUpperCase()}
                                </span>
                            </td>
                            <td class="duration">${result.duration}ms</td>
                            <td>${result.project}</td>
                            <td class="screenshots">
                                ${result.screenshots.map((screenshot: any, index: number) => 
                                    `<a href="${screenshot}" class="screenshot-link" target="_blank">
                                        Screenshot ${index + 1}
                                    </a>`
                                ).join('')}
                            </td>
                            <td>
                                ${result.error ? `<div class="error">${result.error}</div>` : ''}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>`;

    const htmlPath = path.join(this.outputDir, 'custom-test-summary.html');
    fs.writeFileSync(htmlPath, html);
    console.log(`📄 Custom HTML summary saved: ${htmlPath}`);
  }

  private printConsoleSummary(summary: any): void {
    console.log('\n' + '='.repeat(80));
    console.log('🏁 TEST SUMMARY');
    console.log('='.repeat(80));
    console.log(`Total Tests: ${summary.stats.total}`);
    console.log(`✅ Passed: ${summary.stats.passed}`);
    console.log(`❌ Failed: ${summary.stats.failed}`);
    console.log(`⏭️ Skipped: ${summary.stats.skipped}`);
    console.log(`⏱️ Total Duration: ${Math.round(summary.totalDuration / 1000)}s`);
    console.log(`📊 Success Rate: ${Math.round((summary.stats.passed / summary.stats.total) * 100)}%`);
    console.log('='.repeat(80));
  }
}