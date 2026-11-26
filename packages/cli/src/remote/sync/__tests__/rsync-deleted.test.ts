import { describe, expect, it } from 'vitest';
import { buildRsyncArgs } from '../rsync.js';
import { createDeleteCounter } from '../rsync-deleted.js';

describe('createDeleteCounter (4f037bc9.2)', () => {
  it('counts itemized deletions', () => {
    const c = createDeleteCounter();
    c.push('*deleting   old.txt\n*deleting   dir/\n');
    expect(c.count()).toBe(2);
  });

  it('does not count a transferred file whose name starts with "deleting "', () => {
    const c = createDeleteCounter();
    c.push('>f+++++++++ deleting plans.txt\ndeleting plans.txt\n');
    expect(c.count()).toBe(0);
  });

  it('joins a line split across chunks', () => {
    const c = createDeleteCounter();
    c.push('*delet');
    c.push('ing   a.txt\n');
    expect(c.count()).toBe(1);
  });
});

describe('a mirror run is itemized so deletions are distinguishable', () => {
  it('adds --itemize-changes to a real mirror run only', () => {
    expect(buildRsyncArgs({ mirror: true }, 'ssh')).toContain('--itemize-changes');
    expect(buildRsyncArgs({}, 'ssh')).not.toContain('--itemize-changes');
  });
});
