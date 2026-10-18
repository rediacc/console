/**
 * The browser VS Code server's per-launch secret (url token or password) never
 * rides a command line. The launch script that writes it used to travel as an
 * ssh command argument, readable in the local ssh argv, in the gateway's
 * `bash -c` argv and in `ps` on the machine. It now travels on the ssh
 * session's stdin. A fake ssh records exactly what each layer would see.
 */

import { execFileSync } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getServerProvider } from '../../../remote/vscode-server/index.js';
import type { ConnectionDetails } from '../../machine/ssh-connection.js';
import { LAUNCH_FROM_STDIN, launchServer } from '../vscode-server-remote.js';

interface Recorded {
  args: string[];
  stdin: string;
}

const recorded: Recorded[] = [];

vi.mock('../../../remote/ssh/index.js', () => ({
  SSHConnection: class {
    sshOptions = ['-o', 'BatchMode=yes'];
    agentSocketPath = undefined;
    setup() {
      return Promise.resolve();
    }
    cleanup() {
      return Promise.resolve();
    }
  },
  spawnSSH: (destination: string, sshOptions: string[], command?: string) => {
    const entry: Recorded = { args: [...sshOptions, destination, command ?? ''], stdin: '' };
    recorded.push(entry);
    const child = new EventEmitter() as EventEmitter & {
      stdin: PassThrough;
      stdout: PassThrough;
      stderr: PassThrough;
    };
    child.stdin = new PassThrough();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.stdin.on('data', (d: Buffer) => {
      entry.stdin += d.toString();
    });
    child.stdin.on('finish', () => {
      // Answer the way the launch script does, echoing the secret it was sent.
      const secret = /printf '%s' '([^']+)' > "\$STATE\/secret"/.exec(entry.stdin)?.[1] ?? '';
      child.stdout.end(`VSCODE_SERVER reused=0 port=9301 secret=${secret}\n`);
      child.stderr.end();
      setImmediate(() => child.emit('close', 0));
    });
    return child;
  },
}));

const details: ConnectionDetails = {
  host: 'h',
  user: 'repo',
  port: 22,
  privateKey: 'k',
  known_hosts: 'kh',
  datastore: WK_DATASTORE_PATH,
  universalUser: 'u',
  repositoryGuid: '11111111-2222-3333-4444-555555555555',
  workingDirectory: `${WK_DATASTORE_PATH}/mounts/x`,
};

describe('launchServer', () => {
  beforeEach(() => {
    recorded.length = 0;
  });

  for (const id of ['openvscode', 'code-server']) {
    it(`${id}: the secret is on stdin, never in the ssh argv`, async () => {
      const result = await launchServer(getServerProvider(id), details, { repoName: 'app' });

      expect(recorded).toHaveLength(1);
      const [{ args, stdin }] = recorded;
      expect(result.secret).toBeTruthy();
      expect(args.at(-1)).toBe(LAUNCH_FROM_STDIN);
      for (const arg of args) expect(arg).not.toContain(result.secret as string);
      expect(stdin).toContain(result.secret as string);
      expect(result.remotePort).toBe(9301);
    });
  }
});

describe('LAUNCH_FROM_STDIN, run for real', () => {
  it('runs a bash-only script from stdin through a POSIX login shell', () => {
    const script = [
      'set -e',
      'ARGS="--port __PORT__"',
      'PORT=9305',
      'ARGS="${ARGS//__PORT__/$PORT}"',
      // A command that reads stdin must find it drained, not the script's tail.
      'leftover="$(cat)"',
      'echo "out=$ARGS leftover=[$leftover]"',
      'exit 0',
      'echo unreachable',
    ].join('\n');
    const out = execFileSync('sh', ['-c', LAUNCH_FROM_STDIN], { input: script }).toString();
    expect(out).toBe('out=--port 9305 leftover=[]\n');
  });

  // The sandbox gateway hands a repo key's command to `bash -c` with the ssh session's stdin: it replaces itself with sudo (syscall.Exec, fd 0 inherited, private/renet/cmd/renet/sandbox_gateway.go:103), sudo runs `renet sandbox-exec ... -- bash -c <command>` (sandbox_gateway.go:151), whose overlay re-exec copies os.Stdin (sandbox_overlay_linux.go:103) and which replaces itself with that bash (syscall.Exec, sandbox_exec.go:193).
  // A machine key's command takes the same `bash -c` (sandbox_gateway.go:442).
  it('runs the script from stdin as the sandbox gateway execs it: bash -c, stdin a pipe', () => {
    const script = ['read -r first', 'echo "script ran, first=[$first]"'].join('\n');
    const out = execFileSync('bash', ['-c', LAUNCH_FROM_STDIN], {
      input: `${script}\n`,
      env: { PATH: process.env.PATH },
    }).toString();
    // `read` finds stdin drained by the launcher's `cat`, so first is empty.
    expect(out).toBe('script ran, first=[]\n');
  });
});
