/**
 * The MCP job tools (PLAN-detached-jobs C7).
 *
 * `-m` is optional on `rdc job status` and `rdc job logs` when the config holds a
 * ticket for the job, so an agent that has only the job id must be able to call
 * the tool, and the argv it builds must not carry an empty `-m`. `job logs` keeps
 * `--since-line`, the resume cursor a caller passes back after a partial read.
 */

import type { ContractOption } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { deriveOptionType, type ToolDef } from '../tool-factory.js';
import { buildAllTools } from '../tools.js';

const TOOLS: ToolDef[] = buildAllTools();

function tool(name: string): ToolDef {
  const found = TOOLS.find((t) => t.name === name);
  if (!found) throw new Error(`MCP tool ${name} is missing`);
  return found;
}

/** The schema fields a call with these args is refused on; empty when the call is accepted. */
function refusedFields(def: ToolDef, args: Record<string, unknown>): string[] {
  const parsed = z.object(def.schema as z.ZodRawShape).safeParse(args);
  return parsed.success ? [] : parsed.error.issues.map((issue) => issue.path.join('.'));
}

describe('MCP job tools', () => {
  it('job_status with only an id is accepted and omits -m', () => {
    const status = tool('job_status');
    expect(refusedFields(status, { 'job-id': 'j-1' })).toEqual([]);
    const argv = status.command({ 'job-id': 'j-1' });
    expect(argv).toEqual(['job', 'status', 'j-1']);
    expect(argv).not.toContain('--machine');
    expect(argv).not.toContain('-m');
  });

  it('job_status passes -m through when given', () => {
    expect(tool('job_status').command({ 'job-id': 'j-1', machine: 'prod-1' })).toEqual([
      'job',
      'status',
      'j-1',
      '--machine',
      'prod-1',
    ]);
  });

  it('job_logs keeps since-line and drops follow', () => {
    const logs = tool('job_logs');
    expect(Object.keys(logs.schema)).toContain('since_line');
    expect(Object.keys(logs.schema)).not.toContain('follow');
    expect(refusedFields(logs, { 'job-id': 'j-1', since_line: '40' })).toEqual([]);
    expect(logs.command({ 'job-id': 'j-1', since_line: '40' })).toEqual([
      'job',
      'logs',
      'j-1',
      '--since-line',
      '40',
    ]);
  });

  it('job_logs with only an id omits -m', () => {
    const logs = tool('job_logs');
    expect(refusedFields(logs, { 'job-id': 'j-1' })).toEqual([]);
    expect(logs.command({ 'job-id': 'j-1' })).toEqual(['job', 'logs', 'j-1']);
  });

  it('job_wait refuses a call without timeout and accepts one with it', () => {
    const wait = tool('job_wait');
    expect(refusedFields(wait, { 'job-id': 'j-1' })).toContain('timeout');
    expect(refusedFields(wait, { 'job-id': 'j-1', timeout: '2m' })).toEqual([]);
  });
});

describe('requiredArgs on an option, whatever its flag shape', () => {
  const base = {
    long: 'x',
    variadic: false,
    mandatory: false,
    defaultValue: null,
    label: 'x',
  } as const;
  const parses = (type: z.ZodType, value: unknown): boolean => type.safeParse(value).success;

  it('makes a [v] option required when named', () => {
    const opt = { ...base, flags: '--x [v]', valueTaking: true } as unknown as ContractOption;
    expect(parses(deriveOptionType(opt, true), undefined)).toBe(false);
    expect(parses(deriveOptionType(opt, false), undefined)).toBe(true);
  });

  it('makes a boolean option required when named', () => {
    const opt = { ...base, flags: '--x', valueTaking: false } as unknown as ContractOption;
    expect(parses(deriveOptionType(opt, true), undefined)).toBe(false);
    expect(parses(deriveOptionType(opt, false), undefined)).toBe(true);
  });
});
