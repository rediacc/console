/**
 * The Windows launchers run ssh from a temp `.cmd` file (cmd, Windows
 * Terminal) or an encoded PowerShell script. The remote command ships as
 * base64 text with no line break or metacharacter, and the terminal deletes
 * the handed-off files (and the `.cmd` itself) when ssh ends.
 */
import { execFileSync } from 'node:child_process';
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

interface Spawned {
  file: string;
  args: string[];
}
const spawned: Spawned[] = [];
let spawnThrows = false;

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: (file: string, args: string[]) => {
    if (spawnThrows) throw new Error('spawn refused');
    spawned.push({ file, args });
    return { unref: () => undefined };
  },
}));
vi.mock('../detector.js', () => ({ findMSYS2Installation: () => undefined }));

const { launchTerminal } = await import('../launchers.js');
const {
  cmdLaunchScript,
  cmdQuoteArg,
  powershellCleanupSuffix,
  powershellEncodedCommand,
  powershellLiteral,
  windowsRemoteBootstrap,
} = await import('../windows-launch.js');

const KEY = 'C:/Users/rdc/AppData/Local/Temp/ssh-key-0123456789abcdef.pem';
const KH = 'C:/Users/rdc/AppData/Local/Temp/known_hosts-0123456789abcdef';
const KEY_BS = 'C:\\Users\\rdc\\AppData\\Local\\Temp\\ssh-key-0123456789abcdef.pem';
const KH_BS = 'C:\\Users\\rdc\\AppData\\Local\\Temp\\known_hosts-0123456789abcdef';

/** A remote command shaped like the real bootstrap: a heredoc, `$`, `!`, `&&`, `>`, `()`, quotes and a caret. */
const REAL_SCRIPT = [
  'export REDIACC_REPOSITORY=\'app\'; cd "/mnt/a b" && echo "$HOME" 2>/dev/null',
  "cat > ~/.bashrc-rediacc <<'EOF'",
  'rdc_fn() { [ ! -d "$1" ] && echo "no^dir" >&2; (cd /tmp); }',
  'EOF',
  'exec bash --rcfile <(echo "source ~/.bashrc-rediacc") -i',
].join('\n');

const SSH_ARGV = [
  'ssh',
  '-tt',
  '-o',
  'StrictHostKeyChecking=yes',
  '-o',
  `UserKnownHostsFile=${KH}`,
  '-p',
  '22',
  '-i',
  KEY,
  '-o',
  'IdentitiesOnly=yes',
  'rdc@10.0.0.2',
  windowsRemoteBootstrap(REAL_SCRIPT),
];

function launchedScripts(): string[] {
  return spawned.flatMap(({ args }) =>
    args.flatMap((a) => /"?([^" ]*rdc-term-[0-9a-f]{16}\.cmd)"?$/.exec(a)?.[1] ?? [])
  );
}

// BLOCKER: the tests marked posixIt run the remote bootstrap under a real `bash` (heredoc, BASH_ENV, process substitution); that script runs on the remote Linux end, and the Windows host has no bash on PATH. The cmd and PowerShell tests run everywhere.
const posixIt = it.skipIf(process.platform === 'win32');

describe('windowsRemoteBootstrap', () => {
  it('has no line break, quote, caret or percent sign', () => {
    const remote = windowsRemoteBootstrap(REAL_SCRIPT);
    expect(remote).not.toMatch(/[\r\n"^%!;]/);
    expect(remote).not.toContain("'");
  });

  it('carries the real script through base64 unchanged', () => {
    const remote = windowsRemoteBootstrap(REAL_SCRIPT);
    const payload = /echo ([A-Za-z0-9+/=]+)\|base64 -d/.exec(remote)?.[1] as string;
    expect(gunzipSync(Buffer.from(payload, 'base64')).toString('utf8')).toBe(
      `if [ -n "$RDC_BASH_ENV" ]; then export BASH_ENV=$RDC_BASH_ENV; else unset BASH_ENV; fi; unset RDC_BASH_ENV; rm -f -- "$0"\n${REAL_SCRIPT}\n`
    );
  });

  posixIt('runs under bash: heredoc and metacharacters intact, the script file removed', () => {
    const script = [
      'cat <<"EOF"',
      'a $HOME ! && > () ^',
      'EOF',
      'echo "$0" | sed -e "s/.*/&/"',
    ].join('\n');
    const out = execFileSync('bash', ['-c', windowsRemoteBootstrap(script)]).toString();
    const [heredoc, scriptPath] = out.split('\n');
    expect(heredoc).toBe('a $HOME ! && > () ^');
    expect(existsSync(scriptPath)).toBe(false);
  });

  posixIt(
    'reads BASH_ENV once (the gateway bash), so the sandbox banner prints once, and restores it for the script',
    () => {
      const dir = mkdtempSync(join(tmpdir(), 'rdc-be-'));
      try {
        const marker = join(dir, 'count');
        const benv = join(dir, 'bashrc');
        writeFileSync(benv, `echo x >> ${marker}\n`);
        const out = execFileSync(
          'bash',
          ['-c', windowsRemoteBootstrap('echo "BE=$BASH_ENV"; echo "RDC=${RDC_BASH_ENV-unset}"')],
          { env: { ...process.env, BASH_ENV: benv } }
        ).toString();
        expect(out).toContain(`BE=${benv}`);
        expect(out).toContain('RDC=unset');
        expect(readFileSync(marker, 'utf8')).toBe('x\n');
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    }
  );
});

describe('windowsRemoteBootstrap without a gateway BASH_ENV', () => {
  posixIt('leaves BASH_ENV unset for the script, not an empty string', () => {
    const env = { ...process.env };
    delete env.BASH_ENV;
    const out = execFileSync('bash', ['-c', windowsRemoteBootstrap('echo "BE=${BASH_ENV+set}"')], {
      env,
    }).toString();
    expect(out).toBe('BE=\n');
  });
});

describe('cmdLaunchScript', () => {
  const script = cmdLaunchScript(SSH_ARGV, [KEY, KH]);
  const [line1, line2, line3, rest] = script.split('\r\n');

  it('is three CRLF lines, the first the unbroken ssh command with no caret', () => {
    expect(rest).toBe('');
    expect(line1.startsWith('@ssh -tt -o StrictHostKeyChecking=yes')).toBe(true);
    expect(line1).not.toMatch(/[\r\n^]/);
    expect(line1.endsWith(` ${cmdQuoteArg(SSH_ARGV.at(-1) as string)}`)).toBe(true);
  });

  it('deletes the key and known_hosts, then itself silently as the last line', () => {
    expect(line2).toBe(`@del /q "${KEY_BS}" "${KH_BS}"`);
    expect(line3).toBe('@(goto) 2>nul & del /q "%~f0"');
  });

  it('doubles percent signs, quotes metacharacters and keeps a trailing backslash literal', () => {
    expect(cmdQuoteArg('a&b|c')).toBe('"a&b|c"');
    expect(cmdQuoteArg('100%')).toBe('"100%%"');
    expect(cmdQuoteArg('C:\\dir with space\\')).toBe('"C:\\dir with space\\\\"');
    expect(cmdQuoteArg('plain-arg_1.2')).toBe('plain-arg_1.2');
  });

  it.each(['say "hi"', 'a\nb', 'caf\u00e9'])('refuses the argument %j', (arg) => {
    expect(() => cmdLaunchScript(['ssh', arg], [])).toThrow(/cannot quote/);
  });

  it.each(['C:\\100%\\k', 'C:\\a"b\\k', 'C:\\caf\u00e9\\k'])('refuses the path %j', (path) => {
    expect(() => cmdLaunchScript(['ssh'], [path])).toThrow(/cannot quote/);
  });

  it('refuses a line past the cmd.exe limit', () => {
    expect(() => cmdLaunchScript(['ssh', 'x'.repeat(8100)], [])).toThrow(/too long/);
  });
});

describe('Windows launchers', () => {
  beforeEach(() => {
    spawned.length = 0;
    spawnThrows = false;
  });
  afterEach(() => {
    for (const path of launchedScripts()) rmSync(path, { force: true });
  });

  it('windows-terminal runs only the script path through cmd /k', () => {
    const result = launchTerminal('windows-terminal', {
      argv: SSH_ARGV,
      title: 'Rediacc - m',
      keepOpen: true,
      cleanupFiles: [KEY, KH],
    });
    expect(result.success).toBe(true);
    expect(spawned[0].file).toBe('wt.exe');
    const [path] = launchedScripts();
    expect(spawned[0].args).toEqual([
      '--title',
      '"Rediacc - m"',
      'cmd.exe',
      '/k',
      'call',
      `"${path}"`,
    ]);
    expect(readFileSync(path, 'utf8')).toBe(cmdLaunchScript(SSH_ARGV, [KEY, KH]));
    if (process.platform !== 'win32') expect(statSync(path).mode & 0o777).toBe(0o600);
  });

  it('cmd runs it too, and without keepOpen the window closes (/c)', () => {
    launchTerminal('cmd', { argv: SSH_ARGV, keepOpen: true, cleanupFiles: [KEY] });
    launchTerminal('cmd', { argv: SSH_ARGV });
    const [first, second] = launchedScripts();
    expect(spawned[0].args).toEqual(['/k', 'call', `"${first}"`]);
    expect(spawned[1].args).toEqual(['/c', 'call', `"${second}"`]);
  });

  it('a script that cannot be written fails the launch before spawning', () => {
    const result = launchTerminal('cmd', { argv: SSH_ARGV, cleanupFiles: ['C:\\100%\\k'] });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/cannot quote/);
    expect(spawned).toHaveLength(0);
  });

  it('a failed spawn removes the script it wrote', () => {
    const isolated = mkdtempSync(join(tmpdir(), 'rdc-cleanup-'));
    vi.stubEnv('TMPDIR', isolated);
    vi.stubEnv('TEMP', isolated);
    vi.stubEnv('TMP', isolated);
    try {
      launchTerminal('cmd', { argv: SSH_ARGV });
      expect(readdirSync(isolated).filter((n) => n.startsWith('rdc-term-'))).toHaveLength(1);
      for (const name of readdirSync(isolated)) rmSync(join(isolated, name));
      spawnThrows = true;
      const result = launchTerminal('cmd', { argv: SSH_ARGV });
      expect(result.success).toBe(false);
      expect(spawned).toHaveLength(1);
      expect(readdirSync(isolated)).toEqual([]);
    } finally {
      vi.unstubAllEnvs();
      rmSync(isolated, { recursive: true, force: true });
    }
  });
});

describe('PowerShell', () => {
  beforeEach(() => {
    spawnThrows = false;
  });

  const decode = (b64: string) => Buffer.from(b64, 'base64').toString('utf16le');

  it('runs each argument as a literal, the bootstrap included, then removes the files', () => {
    const script = decode(powershellEncodedCommand(SSH_ARGV, true, [KEY, KH]));
    expect(script).toBe(
      `& ${SSH_ARGV.map(powershellLiteral).join(' ')}\nRemove-Item -LiteralPath '${KEY}','${KH}' -Force -ErrorAction SilentlyContinue`
    );
    expect(script.split('\n')).toHaveLength(2);
    expect(decode(powershellEncodedCommand(SSH_ARGV, false))).toContain('Read-Host');
  });

  it('launches powershell.exe with the encoded script', () => {
    spawned.length = 0;
    launchTerminal('powershell', { argv: SSH_ARGV, keepOpen: true, cleanupFiles: [KEY] });
    expect(spawned[0].args).toEqual([
      '-NoExit',
      '-EncodedCommand',
      powershellEncodedCommand(SSH_ARGV, true, [KEY]),
    ]);
  });

  it('doubles ASCII single quotes', () => {
    expect(powershellLiteral("it's")).toBe("'it''s'");
    expect(powershellCleanupSuffix(["C:\\it's\\k"])).toContain("'C:\\it''s\\k'");
  });

  it.each(['\u2018', '\u2019', '\u201A', '\u201B'])('refuses a path holding U+%j', (quote) => {
    const path = `C:\\Users\\a${quote}b\\ssh-key-0123456789abcdef.pem`;
    expect(() => powershellCleanupSuffix([path])).toThrow(/cannot quote/);
    expect(() => powershellEncodedCommand(['ssh', path], true)).toThrow(/cannot quote/);
    spawned.length = 0;
    const result = launchTerminal('powershell', { argv: ['ssh'], cleanupFiles: [path] });
    expect(result.success).toBe(false);
    expect(spawned).toHaveLength(0);
  });

  it('refuses a double quote or line break in an argument', () => {
    expect(() => powershellEncodedCommand(['ssh', 'a"b'], true)).toThrow(/cannot quote/);
    expect(() => powershellEncodedCommand(['ssh', 'a\nb'], true)).toThrow(/cannot quote/);
  });
});
