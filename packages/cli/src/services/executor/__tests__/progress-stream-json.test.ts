/**
 * Under `-o json` stdout carries one envelope and nothing else. `backup verify --restore-test -o json`
 * on hostinger (2026-11-27) printed `⠋ Deleting repository...✔ Repository deleted (182ms)` ahead of
 * its JSON, because the step timeline of the copy's delete rendered to stdout. Both renderers of a
 * step timeline (a job's events and a direct `renet execute` stdout) are held to the rule here.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { setOutputFormat } from '../../../utils/errors.js';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { renderEvent } from '../proxy-command.js';
import { renderJobEvent } from '../job-remote.js';
import { createStdoutHandler } from '../renet-output.js';
import type { RenetEvent } from '../types.js';

const STEP_EVENTS: RenetEvent[] = [
  { type: 'step_start', name: 'repo_delete' },
  { type: 'step_done', name: 'repo_delete', duration_ms: 182 },
];

async function captured(run: () => void): Promise<{ stdout: string; stderr: string }> {
  const context = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };
  await runInRequestContext(context, () => {
    run();
    return Promise.resolve();
  });
  return { stdout: context.stdout.join(''), stderr: context.stderr.join('') };
}

afterEach(() => setOutputFormat('table'));

describe('renderJobEvent under -o json', () => {
  it('control: a table run draws the step timeline on stdout', async () => {
    setOutputFormat('table');
    const out = await captured(() => STEP_EVENTS.forEach(renderJobEvent));
    expect(out.stdout).toContain('Deleting repository');
    expect(out.stdout).toContain('Repository deleted');
  });

  it('moves the step timeline to stderr, leaving stdout empty', async () => {
    setOutputFormat('json');
    const out = await captured(() => STEP_EVENTS.forEach(renderJobEvent));
    expect(out.stdout).toBe('');
    expect(out.stderr).toContain('Deleting repository');
    expect(out.stderr).toContain('Repository deleted');
  });

  it('keeps an output line on stdout: only progress moves', async () => {
    setOutputFormat('json');
    const out = await captured(() => renderJobEvent({ type: 'output', msg: 'hello' }));
    expect(out.stdout).toContain('hello');
  });
});

describe('the renet execute step detector under -o json', () => {
  const lines = Buffer.from(
    `${JSON.stringify({ step_start: { name: 'repo_delete' } })}\n${JSON.stringify({ step_done: { name: 'repo_delete', duration_ms: 182 } })}\n`
  );

  it('control: a table run draws the step timeline on stdout', async () => {
    setOutputFormat('table');
    const out = await captured(() => createStdoutHandler({} as never)(lines));
    expect(out.stdout).toContain('Repository deleted');
  });

  it('moves the step timeline to stderr, leaving stdout empty', async () => {
    setOutputFormat('json');
    const out = await captured(() => createStdoutHandler({} as never)(lines));
    expect(out.stdout).toBe('');
    expect(out.stderr).toContain('Repository deleted');
  });
});

describe('the proxy renderer under -o json', () => {
  it('control: a table run draws the step timeline on stdout', async () => {
    setOutputFormat('table');
    const out = await captured(() => STEP_EVENTS.forEach(renderEvent));
    expect(out.stdout).toContain('Repository deleted');
  });

  it('moves the step timeline to stderr, leaving stdout empty', async () => {
    setOutputFormat('json');
    const out = await captured(() => STEP_EVENTS.forEach(renderEvent));
    expect(out.stdout).toBe('');
    expect(out.stderr).toContain('Repository deleted');
  });
});
