/** The served call route is service-layer code: it must not import a command module (review 4da67de3.1). */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { JOB_WAIT_CEILING_MS, JOB_WAIT_INTERVAL_MS } from '../../../commands/mcp/custom-tools.js';
import * as limits from '../job-wait-limits.js';

const source = readFileSync(new URL('../mcp-call-route.ts', import.meta.url), 'utf-8');
const importsOf = (text: string): string[] =>
  [...text.matchAll(/from '([^']+)'/g)].map((match) => match[1]);

describe('mcp-call-route.ts layering', () => {
  it('imports nothing from the commands layer', () => {
    const imports = importsOf(source);
    expect(imports.filter((specifier) => /\/commands\//.test(specifier))).toEqual([]);
    // Control: the scan sees the file's imports at all.
    expect(imports).toContain('./job-wait-limits.js');
  });

  it('the local job_wait tool and the route share one definition of the limits', () => {
    const toolSource = readFileSync(
      new URL('../../../commands/mcp/custom-tools.ts', import.meta.url),
      'utf-8'
    );
    const fromLimits = /import \{[^}]*\} from '[^']*job-wait-limits\.js'/;
    expect(source).toMatch(fromLimits);
    expect(toolSource).toMatch(fromLimits);
    // Neither file declares its own copy of either limit.
    for (const text of [source, toolSource]) {
      expect(text).not.toMatch(/(const|let)\s+JOB_WAIT_(CEILING|INTERVAL)_MS\b/);
    }
    expect(JOB_WAIT_CEILING_MS).toBe(limits.JOB_WAIT_CEILING_MS);
    expect(JOB_WAIT_INTERVAL_MS).toBe(limits.JOB_WAIT_INTERVAL_MS);
  });
});
