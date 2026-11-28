/** buildReport stamps the report with where it came from (review a4348b2e.2). */
import { feedbackReportSchema } from '@rediacc/shared';
import { describe, expect, it } from 'vitest';
import { buildReport } from '../send.js';

describe('buildReport', () => {
  it('stamps source "cli" and yields a body the report schema accepts', () => {
    const report = buildReport({ kind: 'bug', message: '  it broke  ' });
    expect(report.source).toBe('cli');
    expect(report.message).toBe('it broke');
    expect(feedbackReportSchema.safeParse(report).success).toBe(true);
  });
});
