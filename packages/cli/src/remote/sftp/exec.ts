/**
 * Exec channels over an established ssh2 connection: buffered, streaming and line-protocol sessions.
 */

import type { ClientChannel, Client as SSHClient } from 'ssh2';
import type { ExecSessionHandle } from './types.js';

/**
 * Execute a command on the remote machine via SSH
 *
 * @param command - Command to execute
 * @returns Command output (stdout)
 * @throws Error if command fails or returns non-zero exit code
 */
export function execCommand(ssh: SSHClient, command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    ssh.exec(command, (err, channel) => {
      if (err) {
        reject(new Error(`Failed to execute command: ${err.message}`));
        return;
      }

      let stdout = '';
      let stderr = '';

      channel.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      channel.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      channel.on('close', (code: number) => {
        if (code === 0) {
          resolve(stdout);
        } else {
          reject(new Error(`Command exited with code ${code}: ${stderr || stdout}`));
        }
      });

      channel.on('error', (channelErr: Error) => {
        reject(new Error(`Channel error: ${channelErr.message}`));
      });
    });
  });
}

/**
 * Execute a command with streaming stdin/stdout/stderr support.
 * Unlike exec(), this streams output in real-time and supports writing to stdin.
 *
 * @param command - Command to execute
 * @param options - Streaming options
 * @returns Exit code from the remote command
 */
export function execStreaming(
  ssh: SSHClient,
  command: string,
  options: {
    stdin?: string;
    onStdout?: (data: Buffer) => void;
    onStderr?: (data: Buffer) => void;
  }
): Promise<number> {
  return new Promise((resolve, reject) => {
    ssh.exec(command, (err, channel) => {
      if (err) {
        reject(new Error(`Failed to execute command: ${err.message}`));
        return;
      }

      if (options.stdin) {
        channel.write(options.stdin);
        channel.end();
      } else {
        channel.end();
      }

      channel.on('data', (data: Buffer) => {
        if (options.onStdout) {
          options.onStdout(data);
        }
      });

      channel.stderr.on('data', (data: Buffer) => {
        if (options.onStderr) {
          options.onStderr(data);
        }
      });

      channel.on('close', (code: number) => {
        resolve(code);
      });

      channel.on('error', (channelErr: Error) => {
        reject(new Error(`Channel error: ${channelErr.message}`));
      });
    });
  });
}

/**
 * Open an exec channel whose stdin stays open, for a line protocol with a long-lived remote helper (`renet backup export|import`).
 * Unlike execStreaming, stdin is NOT ended: the caller writes lines with `write` and ends the session with `end` (stdin EOF).
 * stdout is split into lines; `nextLine` resolves with the next one, or null once the channel has closed and every buffered line was read.
 * `exit` resolves with the exit code on close (null when the channel closed without one).
 */
export function openExecSession(
  ssh: SSHClient,
  command: string,
  options: { onStderr?: (data: Buffer) => void } = {}
): Promise<ExecSessionHandle> {
  return new Promise((resolve, reject) => {
    ssh.exec(command, (err, channel) => {
      if (err) {
        reject(new Error(`Failed to execute command: ${err.message}`));
        return;
      }
      resolve(wireExecSession(channel, options));
    });
  });
}

/** Line-buffer an open exec channel's stdout and expose it as an ExecSessionHandle. */
function wireExecSession(
  channel: ClientChannel,
  options: { onStderr?: (data: Buffer) => void }
): ExecSessionHandle {
  const lines: string[] = [];
  const waiters: ((line: string | null) => void)[] = [];
  let partial = '';
  let closed = false;
  let resolveExit: (code: number | null) => void = () => undefined;
  const exit = new Promise<number | null>((r) => {
    resolveExit = r;
  });
  const push = (line: string | null): void => {
    const waiter = waiters.shift();
    if (waiter) waiter(line);
    else if (line !== null) lines.push(line);
  };
  channel.on('data', (data: Buffer) => {
    partial += data.toString();
    let nl = partial.indexOf('\n');
    while (nl >= 0) {
      push(partial.slice(0, nl).replace(/\r$/, ''));
      partial = partial.slice(nl + 1);
      nl = partial.indexOf('\n');
    }
  });
  channel.stderr.on('data', (data: Buffer) => options.onStderr?.(data));
  channel.on('close', (code: number | null) => {
    if (partial) push(partial);
    partial = '';
    closed = true;
    while (waiters.length > 0) waiters.shift()?.(null);
    resolveExit(typeof code === 'number' ? code : null);
  });
  channel.on('error', () => {
    // A channel error is followed by close, which settles every waiter and the exit promise.
  });
  return {
    write: (line: string) => {
      if (!closed) channel.write(line.endsWith('\n') ? line : `${line}\n`);
    },
    end: () => {
      if (!closed) channel.end();
    },
    nextLine: () => {
      const line = lines.shift();
      if (line !== undefined) return Promise.resolve(line);
      if (closed) return Promise.resolve(null);
      return new Promise<string | null>((r) => waiters.push(r));
    },
    exit,
    isClosed: () => closed,
  };
}
