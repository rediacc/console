/**
 * `term connect` output mode. With the container side door retired (spec §5.8:
 * `--container`, `--container-action`, `--log-lines`, `--follow` are deleted in
 * favour of `repo logs` / `repo exec`), the only axis left is whether the
 * invocation is a one-shot `-c` command or an interactive shell.
 */

import { describe, expect, it } from 'vitest';
import { resolveTermOutputMode } from '../term.js';

describe('resolveTermOutputMode', () => {
  it('interactive shell: keep spinners + force TTY', () => {
    expect(resolveTermOutputMode({})).toEqual({ quietOutput: false, noTTY: false });
  });

  it('one-shot command: silence chatter and drop TTY so stdout stays pipeable', () => {
    expect(resolveTermOutputMode({ command: 'echo HELLO' })).toEqual({
      quietOutput: true,
      noTTY: true,
    });
  });

  it('--external alone does not change the output mode', () => {
    expect(resolveTermOutputMode({ external: true })).toEqual({
      quietOutput: false,
      noTTY: false,
    });
  });
});
