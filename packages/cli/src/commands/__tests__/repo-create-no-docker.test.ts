import { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import { registerRepoCreateDeleteCommands, repoCreateOptions } from '../repo-create-delete.js';

/** The options Commander parses for `repo create`, read off the real command without running it. */
function parsed(args: string[]): Record<string, unknown> {
  const repo = new Command('repo');
  registerRepoCreateDeleteCommands(repo);
  const create = repo.commands.find((c) => c.name() === 'create');
  if (!create) throw new Error('repo create is not registered');
  create.action(() => undefined);
  create.parse(['web', ...args], { from: 'user' });
  return create.opts();
}

describe('repo create --no-docker', () => {
  it('maps the flag Commander parses as docker: false to noDocker: true', () => {
    const opts = parsed(['-m', 'box', '--no-docker']);
    expect(opts.docker).toBe(false);
    expect(repoCreateOptions(opts).noDocker).toBe(true);
  });

  it('leaves noDocker false without the flag', () => {
    const opts = parsed(['-m', 'box']);
    expect(repoCreateOptions(opts).noDocker).toBe(false);
  });
});
