import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { escapeForDoubleQuotes, SSHExecutor } from './SSHExecutor';

// The real builders run under a real local `sh -c`, with `ssh` on PATH replaced by a stand-in that records the remote command it was handed and runs it through `bash -c`, as sshd does with the login shell.
// The inner hop of executeNested runs inside the first stand-in's bash, so it finds the same stand-in: every shell layer the fleet goes through is a real shell here.
const FAKE_SSH = `#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-i|-p|-l|-F) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
host="$1"; shift
cmd="$*"
printf '%s\\t%s\\0' "$host" "$cmd" >> "$FAKE_SSH_LOG"
exec bash -c "$cmd"
`;

// `$1`, `$(...)`, backticks, `"$u"`, `$?` and an arithmetic expansion are all meant for the remote shell; a backslash, a double quote and `!` must arrive unchanged too.
const REMOTE_COMMAND = [
  'u=remote-u',
  'set -- remote-first',
  `printf '%s|' "$1" "$u" "$(echo sub)" \`echo tick\` "$((2 + 3))"`,
  `echo 'a b' | awk '{print $1}'`,
  `false; echo "rc=$?"`,
  `printf '%s\\n' 'back\\slash "dq" bang!'`,
].join('; ');

const EXPECTED_STDOUT = 'remote-first|remote-u|sub|tick|5|a\nrc=1\nback\\slash "dq" bang!\n';

describe('SSHExecutor escaping round-trips through real shells', () => {
  let dir: string;
  let log: string;
  const saved = { PATH: process.env.PATH, USER: process.env.USER, LOG: process.env.FAKE_SSH_LOG };

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'ssh-escape-'));
    log = join(dir, 'ssh.log');
    const fake = join(dir, 'ssh');
    writeFileSync(fake, FAKE_SSH);
    chmodSync(fake, 0o755);
    process.env.PATH = `${dir}:${saved.PATH ?? ''}`;
    process.env.USER = 'tester';
    process.env.FAKE_SSH_LOG = log;
  });

  beforeEach(() => {
    writeFileSync(log, '');
  });

  afterAll(() => {
    // An unset variable is deleted, not assigned: assigning undefined stores the string 'undefined'.
    for (const [key, value] of Object.entries({ PATH: saved.PATH, USER: saved.USER })) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    if (saved.LOG === undefined) delete process.env.FAKE_SSH_LOG;
    else process.env.FAKE_SSH_LOG = saved.LOG;
    rmSync(dir, { recursive: true, force: true });
  });

  const hops = (): { host: string; command: string }[] =>
    readFileSync(log, 'utf8')
      .split('\0')
      .filter(Boolean)
      .map((entry) => {
        const tab = entry.indexOf('\t');
        return { host: entry.slice(0, tab), command: entry.slice(tab + 1) };
      });

  it('executeNested hands the target the command byte for byte and the target expands it', async () => {
    const executor = new SSHExecutor({ privateKeyPath: join(dir, 'no-such-key') });
    const result = await executor.executeNested('bridge', 'target', REMOTE_COMMAND, {
      quiet: true,
    });

    expect(result.stderr).toBe('');
    expect(result.success).toBe(true);
    const seen = hops();
    expect(seen.map((h) => h.host)).toEqual(['tester@bridge', 'tester@target']);
    expect(seen[1].command).toBe(REMOTE_COMMAND);
    expect(result.stdout).toBe(EXPECTED_STDOUT);
  });

  it('execute hands the host the command byte for byte and the host expands it', async () => {
    const executor = new SSHExecutor({ privateKeyPath: join(dir, 'no-such-key') });
    const result = await executor.execute('host', REMOTE_COMMAND, { quiet: true });

    expect(result.stderr).toBe('');
    expect(result.success).toBe(true);
    const seen = hops();
    expect(seen.map((h) => h.host)).toEqual(['tester@host']);
    expect(seen[0].command).toBe(REMOTE_COMMAND);
    expect(result.stdout).toBe(EXPECTED_STDOUT);
  });
});

describe('escapeForDoubleQuotes', () => {
  it('escapes exactly backslash, double quote, dollar and backtick', () => {
    expect(escapeForDoubleQuotes('a\\b"c$d`e!f\'g')).toBe('a\\\\b\\"c\\$d\\`e!f\'g');
  });
});
