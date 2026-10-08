import { afterEach, describe, expect, it, vi } from 'vitest';

// The hydrator schedules itself at import against `document`; a node test gives it an empty page.
vi.stubGlobal('document', {
  readyState: 'complete',
  querySelectorAll: () => [],
  addEventListener: () => {},
});

const mountPlayers = vi.fn();
vi.mock('../tutorial-video-mount', () => ({
  mountPlayers: (...args: unknown[]) => mountPlayers(...args),
  whenVideoAppears: () => Promise.resolve(null),
}));
vi.mock('../video-theater', () => ({ openTheater: () => {} }));

/**
 * A stand-in element that keeps its LIVE click listeners and honors `{ once: true }` the way a
 * DOM does: a once-listener leaves the list before it runs. Counting live listeners (not every
 * add) is what makes "re-armed" mean a press can fire again.
 */
function fakeMount() {
  let live: { fn: () => void; once: boolean }[] = [];
  return {
    get live() {
      return live.length;
    },
    press() {
      for (const l of [...live]) {
        if (l.once) live = live.filter((x) => x !== l);
        l.fn();
      }
    },
    addEventListener: (_type: string, fn: () => void, opts?: { once?: boolean }) => {
      live.push({ fn, once: opts?.once === true });
    },
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('armInline', () => {
  afterEach(() => mountPlayers.mockReset());

  it('re-arms the press when the player chunk fails to load, so the next press retries', async () => {
    const { armInline } = await import('../tutorial-video-hydrate');
    const el = fakeMount();
    mountPlayers.mockRejectedValueOnce(new Error('chunk fetch failed'));
    armInline(el as unknown as HTMLElement);
    expect(el.live).toBe(1);
    el.press();
    // The once-listener is gone after the press, and nothing is live until the rejection lands.
    expect(el.live).toBe(0);
    await flush();
    // The failed load re-armed the press: the retry listener is the only live one.
    expect(el.live).toBe(1);
  });

  it('CONTROL: a press that loads the player does not re-arm', async () => {
    const { armInline } = await import('../tutorial-video-hydrate');
    const el = fakeMount();
    mountPlayers.mockResolvedValueOnce(undefined);
    armInline(el as unknown as HTMLElement);
    expect(el.live).toBe(1);
    el.press();
    await flush();
    expect(el.live).toBe(0);
  });
});
