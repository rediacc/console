import { describe, expect, it } from 'vitest';
import { resolveTermOutputMode } from '../term.js';

describe('resolveTermOutputMode', () => {
  it('interactive shell: keep spinners + force TTY', () => {
    expect(resolveTermOutputMode({})).toEqual({ quietOutput: false, noTTY: false });
  });

  it('plain command: silence chatter and drop TTY', () => {
    expect(resolveTermOutputMode({ command: 'echo HELLO' })).toEqual({
      quietOutput: true,
      noTTY: true,
    });
  });

  it('container exec with command: silence chatter but keep TTY for docker exec -it', () => {
    expect(
      resolveTermOutputMode({
        command: 'bash',
        container: 'web',
        containerAction: 'exec',
      })
    ).toEqual({ quietOutput: true, noTTY: false });
  });

  it('container terminal with command: same TTY exception as exec', () => {
    expect(
      resolveTermOutputMode({
        command: 'bash',
        container: 'web',
        containerAction: 'terminal',
      })
    ).toEqual({ quietOutput: true, noTTY: false });
  });

  it('container without explicit action: defaults to terminal mode, keep TTY', () => {
    expect(
      resolveTermOutputMode({
        command: 'bash',
        container: 'web',
      })
    ).toEqual({ quietOutput: true, noTTY: false });
  });

  it('container logs with command: NOT interactive, drop TTY', () => {
    expect(
      resolveTermOutputMode({
        command: 'irrelevant',
        container: 'web',
        containerAction: 'logs',
      })
    ).toEqual({ quietOutput: true, noTTY: true });
  });

  it('container without command: silence chatter, keep TTY (interactive default)', () => {
    expect(resolveTermOutputMode({ container: 'web' })).toEqual({
      quietOutput: true,
      noTTY: false,
    });
  });
});
