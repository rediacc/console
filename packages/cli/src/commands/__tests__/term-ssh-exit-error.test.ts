import { PassThrough } from 'node:stream';
import { describe, expect, it, vi } from 'vitest';

const writes = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/request-context.js', async () => {
  const actual = await vi.importActual<object>('../../services/core/request-context.js');
  return { ...actual, writeStderr: (s: string) => writes.push(s) };
});

const { buildSSHExitErrorMessage, teeStderrTail } = await import('../term-ssh-exit.js');

describe("term connect carries the remote's own error (C11)", () => {
  it("makes renet's cobra Error line the message instead of the generic code hint", () => {
    const tail = 'time="x" level=info msg="start"\nError: repository mail is not mounted\n';
    const message = buildSSHExitErrorMessage(1, tail);
    expect(message).toContain('repository mail is not mounted');
    expect(message).not.toContain('Generic error');
  });

  it("ignores ssh's own sign-off line", () => {
    const message = buildSSHExitErrorMessage(1, 'Connection to 10.0.0.5 closed.\n');
    expect(message).toContain('Generic error');
  });

  it('names the version skew when the remote renet rejects a flag the CLI sent', () => {
    const tail = 'Error: unknown flag: --datastore\nUsage: renet term ...\n';
    const message = buildSSHExitErrorMessage(1, tail, 'server-1');
    expect(message).toBe('renet on server-1 is older than this CLI; run machine setup');
    expect(message).not.toContain('unknown flag');
  });

  it("leaves a -c command's own unknown-flag line alone", () => {
    const message = buildSSHExitErrorMessage(2, 'mytool: unknown flag: --x\n', 'server-1');
    expect(message).not.toContain('older than this CLI');
    expect(message).toContain('unknown flag: --x');
  });

  it('keeps cobra text for an unknown flag when no machine is named', () => {
    expect(buildSSHExitErrorMessage(1, 'Error: unknown flag: --datastore\n')).toContain(
      'unknown flag'
    );
  });

  it('keeps the per-code hint when the remote printed nothing', () => {
    expect(buildSSHExitErrorMessage(255)).toContain('SSH connection failed');
  });

  it('tees every stderr chunk to the terminal and keeps the tail for the error', async () => {
    writes.length = 0;
    const stream = new PassThrough();
    const tail = teeStderrTail(stream);
    stream.write('first line\n');
    stream.end('Error: unknown repo\n');
    await new Promise((r) => stream.on('end', r));
    expect(writes.join('')).toBe('first line\nError: unknown repo\n');
    expect(buildSSHExitErrorMessage(1, tail())).toContain('unknown repo');
  });
});
