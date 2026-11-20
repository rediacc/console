import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { buildSSHExitErrorMessage, createStderrTail, sshExitError } from '../term-ssh-exit.js';

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
    expect(message).toBe(
      'renet on server-1 is older than this CLI; run machine setup directly, without --proxy, since an executor never uploads renet'
    );
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

  it('keeps the stderr tail for the error', () => {
    const tail = createStderrTail();
    tail.add('first line\n');
    tail.add('Error: unknown repo\n');
    expect(tail.read()).toBe('first line\nError: unknown repo\n');
    tail.add('x'.repeat(5000));
    expect(tail.read()).toHaveLength(4096);
    expect(buildSSHExitErrorMessage(1, 'first line\nError: unknown repo\n')).toContain(
      'unknown repo'
    );
  });
});

describe('the exit code of a term connect session', () => {
  it("makes a -c command's exit code the CLI's exit code", () => {
    const error = sshExitError(3, '', 'server-1', true);
    expect(error).toBeInstanceOf(CliExitError);
    expect((error as CliExitError).exitCode).toBe(3);
  });

  it("keeps 255 as ssh's own connection failure, and an interactive shell's generic failure", () => {
    expect(sshExitError(255, '', 'server-1', true)).not.toBeInstanceOf(CliExitError);
    expect(sshExitError(3, '', 'server-1', false)).not.toBeInstanceOf(CliExitError);
  });
});
