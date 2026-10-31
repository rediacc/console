import { describe, expect, it } from 'vitest';

import { RenetFunctionsTestRunner } from '../RenetFunctionsTestRunner';

type Flags = (opts: Record<string, unknown>) => string;

/** buildCrossVMFlags is a pure method of the flag set; skip the constructor, which needs a live ops fleet. */
function crossVMFlags(): Flags {
  const runner = Object.create(RenetFunctionsTestRunner.prototype) as Record<string, unknown>;
  return (opts) => (runner.buildCrossVMFlags as Flags).call(runner, opts);
}

describe('RenetFunctionsTestRunner.buildCrossVMFlags', () => {
  const user = process.env.USER || 'u';
  const key = `/home/${user}/.ssh/id_rsa`;

  it('gives cross-VM verbs the user and key flags on both machines', () => {
    for (const fn of ['backup_push', 'backup_pull', 'repository_migrate']) {
      expect(crossVMFlags()({ function: fn, sourceMachine: 'a', destMachine: 'b' })).toBe(
        ` --source-machine a --source-user ${user} --ssh-key ${key}` +
          ` --dest-machine b --dest-user ${user} --ssh-key ${key}`
      );
    }
  });

  it('gives other verbs the machine flags and neither user nor key', () => {
    const flags = crossVMFlags()({
      function: 'backup_list',
      sourceMachine: 'a',
      destMachine: 'b',
    });
    expect(flags).toBe(' --source-machine a --dest-machine b');
    expect(flags).not.toMatch(/--source-user|--dest-user|--ssh-key/);
  });

  it('emits nothing for a machine that is not named', () => {
    expect(crossVMFlags()({ function: 'backup_push', destMachine: 'b' })).not.toContain('--source');
    expect(crossVMFlags()({ function: 'backup_push' })).toBe('');
  });
});
