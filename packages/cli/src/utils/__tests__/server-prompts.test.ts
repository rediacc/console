/**
 * The machine question of `rdc server install`: the provision hint is written to stderr, so
 * stdout stays clean for machine-readable output.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  writeStderr: vi.fn(),
  answers: [] as string[],
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/request-context.js')>()),
  writeStderr: m.writeStderr,
}));
vi.mock('inquirer', () => ({
  createPromptModule: () => () => Promise.resolve({ value: m.answers.shift() }),
}));

import { inquirerPrompts } from '../server-prompts.js';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('inquirerPrompts().machine', () => {
  it('writes the provision hint to stderr when a new machine is being added', async () => {
    m.answers = ['__add-existing__', '203.0.113.10', 'admin', '22', 'm1'];
    const answer = await inquirerPrompts().machine([]);
    expect(m.writeStderr).toHaveBeenCalledWith('commands.server.prompts.provisionHint\n');
    expect(answer).toMatchObject({ kind: 'add', name: 'm1', ip: '203.0.113.10' });
  });

  it('writes no hint when a configured machine is picked', async () => {
    m.answers = ['m1'];
    const answer = await inquirerPrompts().machine(['m1']);
    expect(answer).toEqual({ kind: 'existing', name: 'm1' });
    expect(m.writeStderr).not.toHaveBeenCalled();
  });
});
