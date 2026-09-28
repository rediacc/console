import { describe, expect, it } from 'vitest';
import { runSetupStepsConcurrently } from '../bridge-global-setup';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

describe('runSetupStepsConcurrently', () => {
  it('starts every step before any finishes', async () => {
    const events: string[] = [];
    const step = (name: string) => ({
      name,
      run: async () => {
        events.push(`start ${name}`);
        await delay(20);
        events.push(`end ${name}`);
      },
    });
    await runSetupStepsConcurrently([step('a'), step('b'), step('c')]);
    expect(events.slice(0, 3)).toEqual(['start a', 'start b', 'start c']);
    expect(events.slice(3).sort()).toEqual(['end a', 'end b', 'end c']);
  });

  it('names every failed step, not only the first', async () => {
    const first = new Error('rustfs down');
    const error = await runSetupStepsConcurrently([
      { name: 'Step 5', run: () => Promise.reject(first) },
      { name: 'Step 6', run: () => Promise.resolve() },
      {
        name: 'Step 7',
        run: async () => {
          await delay(10);
          throw new Error('datastore init failed on 192.168.111.11');
        },
      },
    ]).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(Error);
    const message = (error as Error).message;
    expect(message).toContain('2 of 3 concurrent setup step(s) failed');
    expect(message).toContain('[Step 5] rustfs down');
    expect(message).toContain('[Step 7] datastore init failed on 192.168.111.11');
    expect(message).not.toContain('[Step 6]');
    expect((error as Error).cause).toBe(first);
  });

  it('waits for a slow step to settle before rejecting', async () => {
    let slowDone = false;
    const error = await runSetupStepsConcurrently([
      { name: 'fast', run: () => Promise.reject(new Error('boom')) },
      {
        name: 'slow',
        run: async () => {
          await delay(30);
          slowDone = true;
        },
      },
    ]).catch((err: unknown) => err);
    expect(error).toBeInstanceOf(Error);
    expect(slowDone).toBe(true);
  });

  it('keeps a non-Error rejection readable', async () => {
    await expect(
      runSetupStepsConcurrently([{ name: 'odd', run: () => Promise.reject('plain string') }])
    ).rejects.toThrow('[odd] plain string');
  });
});
