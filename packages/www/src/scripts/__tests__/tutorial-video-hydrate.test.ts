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
  whenVideoAppears: async () => null,
}));
vi.mock('../video-theater', () => ({ openTheater: () => {} }));

/** A stand-in element that records its click listeners, so a press can be fired by hand. */
function fakeMount() {
  const listeners: Array<() => void> = [];
  return {
    listeners,
    addEventListener: (_type: string, fn: () => void) => {
      listeners.push(fn);
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
    expect(el.listeners).toHaveLength(1);
    el.listeners[0]();
    await flush();
    expect(el.listeners).toHaveLength(2);
  });

  it('CONTROL: a press that loads the player does not re-arm', async () => {
    const { armInline } = await import('../tutorial-video-hydrate');
    const el = fakeMount();
    mountPlayers.mockResolvedValueOnce(undefined);
    armInline(el as unknown as HTMLElement);
    el.listeners[0]();
    await flush();
    expect(el.listeners).toHaveLength(1);
  });
});
