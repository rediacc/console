/**
 * The macOS and Windows backends of secure-storage.ts, driven on a POSIX host through STAND-INS for `security` and `powershell.exe`.
 *
 * secure-storage.native.test.ts runs the real tools, each on its own operating system, and only there. This file is what a Linux run can hold: the module is real, the child processes are real, and the tool at the other end of the pipe is a script this file writes onto PATH. It pins what the module SENDS:
 *
 *   - the exact PowerShell script text, and its arguments;
 *   - that the payload travels on stdin, as base64, and is on no command line in any encoding;
 *   - the Keychain armour, the split into items, and the read of an entry stored before the armour;
 *   - the DPAPI file name and content, and what a damaged file reads as;
 *   - the refusal when the tool fails, answers nothing, or is absent.
 *
 * WHAT A STAND-IN CANNOT PROVE. That Windows PowerShell 5.1 runs the script, that `Add-Type -AssemblyName System.Security` makes `ProtectedData` resolve, that `$input` carries stdin there, that `security -i` stores what the line says. Those belong to the macOS and Windows legs of the `Quality / Secure Storage` job.
 *
 * HOW FAITHFUL THE STAND-INS ARE. The `security` one follows Apple's SecurityTool source: `find-generic-password -w` prints hex when any byte is not printable, `-i` reads lines of at most 4095 bytes, cuts a longer one and runs its tail as the next command, drops a last line with no newline, and exits with the result of the last command.
 * Its first two tests hold it to the two outputs the real tool gave on the macOS runner. The `powershell.exe` one accepts exactly the two scripts spelled out below and nothing else, so a changed script is a red test here before it is a red leg there.
 */

import { execFileSync, spawnSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SecureStorage } from '../secure-storage.js';

// The scripts, spelled out. secure-storage.ts builds them from parts; this is the text Windows PowerShell must receive, character for character.
const PROTECT_SCRIPT =
  "$ErrorActionPreference='Stop';Add-Type -AssemblyName System.Security;$data=[Convert]::FromBase64String((@($input) -join ''));$result=[Security.Cryptography.ProtectedData]::Protect($data,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser);[Console]::Out.Write('rdc-dpapi:'+[Convert]::ToBase64String($result))";
const UNPROTECT_SCRIPT = PROTECT_SCRIPT.replace('::Protect(', '::Unprotect(');

/** The two outputs of the real `security find-generic-password -w` on the macOS runner (job 115445766913), for the two values under them. */
const SEEN_ON_MACOS: readonly (readonly [string, string])[] = [
  ['line one\nline two', '6c696e65206f6e650a6c696e652074776f'],
  ['şifre-пароль-密码-🔑', 'c59f696672652dd0bfd0b0d180d0bed0bbd18c2de5af86e7a0812df09f9491'],
];

const VALUES: readonly (readonly [string, string])[] = [
  ['the production shape (base64 of 32 bytes)', randomBytes(32).toString('base64')],
  ['an embedded newline', 'line one\nline two'],
  ['a trailing newline, CRLF and outer spaces', '  padded\r\nvalue \n'],
  ['unicode', 'şifre-пароль-密码-🔑'],
  ['only hex digits', '6c696e65206f6e650a'],
  ['a PowerShell breakout', "'; Remove-Item -Recurse C:\\ ; '$(whoami)`n\""],
  ['a `security -i` breakout', 'x\ndelete-generic-password -s rdc-config\n"\'\\'],
  ['4 KB', randomBytes(3072).toString('base64')],
  ['the empty string', ''],
];

/** The value as it could appear on a command line: raw, and base64 and hex of its bytes. The empty string has no form to look for. */
function formsOf(value: string): string[] {
  const bytes = Buffer.from(value, 'utf-8');
  return [value, bytes.toString('base64'), bytes.toString('hex')].filter((form) => form !== '');
}

// ─── The stand-ins ──────────────────────────────────────────────────────

/** Both stand-ins start with this: every start is one JSON line in the log, arguments and stdin. */
function recorderSource(tool: string, log: string): string {
  return `
const fs = require('node:fs');
const argv = process.argv.slice(2);
const stdin = fs.readFileSync(0, 'utf-8');
fs.appendFileSync(${JSON.stringify(log)}, JSON.stringify({ tool: ${JSON.stringify(tool)}, argv, stdin }) + '\\n');
`;
}

function securitySource(log: string, store: string): string {
  return `#!${process.execPath}
${recorderSource('security', log)}
const STORE = ${JSON.stringify(store)};
const load = () => (fs.existsSync(STORE) ? JSON.parse(fs.readFileSync(STORE, 'utf-8')) : {});
const save = (items) => fs.writeFileSync(STORE, JSON.stringify(items));

function run(args) {
  const [command, ...rest] = args;
  const flag = (name) => (rest.includes(name) ? rest[rest.indexOf(name) + 1] : undefined);
  const id = flag('-s') + '\\n' + flag('-a');
  const items = load();
  if (command === 'add-generic-password') {
    if (id in items && !rest.includes('-U')) {
      process.stderr.write('security: SecKeychainItemCreateFromContent (<default>): The specified item already exists in the keychain.\\n');
      return 45;
    }
    items[id] = Buffer.from(flag('-w'), 'utf-8').toString('hex');
    save(items);
    return 0;
  }
  if (!(id in items)) {
    process.stderr.write('security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.\\n');
    return 44;
  }
  if (command === 'find-generic-password') {
    // keychain_find.c, do_password_item_printing: hex when any byte fails isprint(), the bytes themselves otherwise, then a newline.
    const bytes = Buffer.from(items[id], 'hex');
    const printable = bytes.every((byte) => byte >= 0x20 && byte <= 0x7e);
    process.stdout.write(printable ? bytes : bytes.toString('hex'));
    process.stdout.write('\\n');
    return 0;
  }
  if (command === 'delete-generic-password') {
    delete items[id];
    save(items);
    return 0;
  }
  return 2;
}

if (argv[0] === '-i') {
  // security.c and readline.c: a line is at most MAX_LINE_LEN - 1 bytes, the rest of a longer one is read as the next line, and input that ends without a newline is dropped.
  let result = 0;
  let rest = stdin;
  while (rest.includes('\\n')) {
    const end = Math.min(rest.indexOf('\\n'), 4095);
    const line = rest.slice(0, end);
    rest = rest.slice(end === 4095 ? end : end + 1);
    result = run(line.split(/\\s+/).filter((token) => token !== ''));
    if (result !== 0) process.stderr.write(line.split(/\\s+/)[0] + ': returned ' + result + '\\n');
  }
  process.exit(result);
}
process.exit(run(argv));
`;
}

function powershellSource(log: string): string {
  return `#!${process.execPath}
${recorderSource('powershell.exe', log)}
const SCRIPTS = ${JSON.stringify({ [PROTECT_SCRIPT]: 'Protect', [UNPROTECT_SCRIPT]: 'Unprotect' })};
const fail = (line) => {
  process.stderr.write(line + '\\n');
  process.exit(1);
};
const mode = process.env.SSTOOLS_POWERSHELL ?? 'works';
// What Windows PowerShell 5.1 said on the Windows runner (job 115445766551) before the assembly was loaded.
if (mode === 'type-not-found') fail('Unable to find type [Security.Cryptography.ProtectedData].');
if (mode === 'silent') process.exit(0);
if (argv.length !== 4 || argv[0] !== '-NonInteractive' || argv[1] !== '-NoProfile' || argv[2] !== '-Command') {
  fail('stand-in: unexpected arguments');
}
const method = SCRIPTS[argv[3]];
if (method === undefined) fail('stand-in: not one of the two pinned scripts');
// $input is the lines of stdin; the script joins them and FromBase64String refuses what is not base64.
const text = stdin.split(/\\r?\\n/).join('');
if (!/^[A-Za-z0-9+/]*={0,2}$/.test(text) || text.length % 4 !== 0) {
  fail('Exception calling "FromBase64String" with "1" argument(s)');
}
const data = Buffer.from(text, 'base64');
const MAGIC = Buffer.from('stand-in DPAPI blob:');
const flip = (bytes) => Buffer.from(bytes.map((byte) => byte ^ 0x5a));
let result;
if (method === 'Protect') {
  result = Buffer.concat([MAGIC, flip(data)]);
} else {
  if (data.length < MAGIC.length || !data.subarray(0, MAGIC.length).equals(MAGIC)) {
    fail('Exception calling "Unprotect" with "3" argument(s): "The data is invalid."');
  }
  result = flip(data.subarray(MAGIC.length));
}
process.stdout.write('rdc-dpapi:' + result.toString('base64'));
`;
}

// ─── A host that looks like macOS or Windows ────────────────────────────

interface Call {
  tool: string;
  argv: string[];
  stdin: string;
}

interface Host {
  storage: () => SecureStorage;
  /** Every start of a stand-in so far. */
  calls: () => Call[];
  /** The stand-in Keychain: `<service>\n<account>` to the stored text. */
  keychain: () => Record<string, string>;
  /** Where the Windows state directory is on this host. */
  keysDir: string;
  bin: string;
  UnavailableError: typeof import('../secure-storage.js').SecureStorageUnavailableError;
}

const saved = {
  platform: process.platform,
  PATH: process.env.PATH,
  LOCALAPPDATA: process.env.LOCALAPPDATA,
  APPDATA: process.env.APPDATA,
};
const roots: string[] = [];

function setEnv(name: string, value: string | undefined): void {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

afterEach(() => {
  Object.defineProperty(process, 'platform', { value: saved.platform });
  setEnv('PATH', saved.PATH);
  setEnv('LOCALAPPDATA', saved.LOCALAPPDATA);
  setEnv('APPDATA', saved.APPDATA);
  delete process.env.SSTOOLS_POWERSHELL;
  delete process.env.REDIACC_SECRET_STORE;
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

/** A fresh copy of the module on a host whose platform is `platform` and whose PATH starts with the stand-ins. */
async function hostOf(platform: 'darwin' | 'win32', tools = true): Promise<Host> {
  const root = mkdtempSync(join(tmpdir(), 'rdc-sstools-'));
  roots.push(root);
  const bin = join(root, 'bin');
  const log = join(root, 'calls.jsonl');
  const store = join(root, 'keychain.json');
  mkdirSync(bin);
  if (tools) {
    writeFileSync(join(bin, 'security'), securitySource(log, store));
    writeFileSync(join(bin, 'powershell.exe'), powershellSource(log));
    for (const tool of readdirSync(bin)) chmodSync(join(bin, tool), 0o755);
  }
  // With the stand-ins the rest of PATH stays; without them PATH is the empty directory alone, so no real tool of the host answers.
  process.env.PATH = tools ? `${bin}${delimiter}${saved.PATH ?? ''}` : bin;
  process.env.LOCALAPPDATA = join(root, 'LocalAppData');
  process.env.APPDATA = join(root, 'AppData');
  delete process.env.REDIACC_SECRET_STORE;
  Object.defineProperty(process, 'platform', { value: platform });
  // The module remembers a proven backend; each host gets its own copy.
  vi.resetModules();
  const module = await import('../secure-storage.js');
  return {
    storage: module.getSecureStorage,
    calls: () =>
      existsSync(log)
        ? readFileSync(log, 'utf-8')
            .split('\n')
            .filter((line) => line !== '')
            .map((line) => JSON.parse(line) as Call)
        : [],
    keychain: () => {
      if (!existsSync(store)) return {};
      const items = JSON.parse(readFileSync(store, 'utf-8')) as Record<string, string>;
      return Object.fromEntries(
        Object.entries(items).map(([id, hex]) => [id, Buffer.from(hex, 'hex').toString('utf-8')])
      );
    },
    keysDir: join(root, 'LocalAppData', 'rediacc', 'keys'),
    bin,
    UnavailableError: module.SecureStorageUnavailableError,
  };
}

function dpapiFile(host: Host, key: string): string {
  return join(host.keysDir, `${createHash('sha256').update(key, 'utf-8').digest('hex')}.dpapi`);
}

/** Runs `fn` and returns the calls it made, without the ones before it (selection proves the backend with a throwaway key first). */
async function callsDuring(host: Host, fn: () => Promise<unknown>): Promise<Call[]> {
  const before = host.calls().length;
  await fn();
  return host.calls().slice(before);
}

const posixIt = it.skipIf(process.platform === 'win32');

// ─── macOS: Keychain through the `security` stand-in ────────────────────

describe('secure storage: the Keychain backend against a stand-in for `security`', () => {
  posixIt.each(SEEN_ON_MACOS)(
    'control: the stand-in prints what the real tool printed for a value stored as given (%j)',
    async (value, printed) => {
      const host = await hostOf('darwin');
      const security = join(host.bin, 'security');
      execFileSync(security, ['add-generic-password', '-a', 'k', '-s', 'rdc-config', '-w', value]);
      const found = execFileSync(
        security,
        ['find-generic-password', '-a', 'k', '-s', 'rdc-config', '-w'],
        { encoding: 'utf-8' }
      );
      // Hex, and nothing that says so: the defect the armour exists for.
      expect(found).toBe(`${printed}\n`);
    }
  );

  posixIt(
    'control: the stand-in cuts a `-i` line at 4095 bytes and stores the cut value, as the real tool does',
    async () => {
      const host = await hostOf('darwin');
      const head = 'add-generic-password -a k -s rdc-config -U -w ';
      const run = spawnSync(join(host.bin, 'security'), ['-i'], {
        input: `${head}${'A'.repeat(5000)}\n`,
        encoding: 'utf-8',
      });
      expect(host.keychain()['rdc-config\nk']).toBe('A'.repeat(4095 - head.length));
      // The tail ran as a command of its own and failed; that failure is the exit code.
      expect(run.status).not.toBe(0);
    }
  );

  posixIt.each(VALUES)('round-trips %s byte-exact', async (_label, value) => {
    const host = await hostOf('darwin');
    const storage = host.storage();
    expect(storage.type).toBe('keychain');
    await storage.set('rdc:pw:value', value);
    expect(await storage.get('rdc:pw:value')).toBe(value);
  });

  posixIt('stores the armoured form, which the tool prints as it is', async () => {
    const host = await hostOf('darwin');
    const value = SEEN_ON_MACOS[0][0];
    await host.storage().set('rdc:pw:armour', value);
    expect(host.keychain()).toEqual({
      'rdc-config\nrdc:pw:armour': `rdc-b64.1.${Buffer.from(value).toString('base64')}`,
    });
  });

  posixIt(
    'the secret reaches `security` on stdin, one whole line per item, and is on no command line',
    async () => {
      const host = await hostOf('darwin');
      const storage = host.storage();
      const value = `${randomBytes(3072).toString('base64')}\nşifre`;
      const encoded = Buffer.from(value).toString('base64');
      const calls = await callsDuring(host, async () => {
        await storage.set('rdc:pw:argv', value);
        expect(await storage.get('rdc:pw:argv')).toBe(value);
      });

      const writes = calls.filter((call) => call.stdin !== '');
      // Control: the recorder holds the payload where it does travel. Joined in order, the stdin lines carry the whole encoded value.
      expect(writes.length).toBeGreaterThan(1);
      expect(
        writes
          .map((call) => call.stdin.trimEnd().split(' ').at(-1))
          .join('')
          .replace(`rdc-b64.${writes.length}.`, '')
      ).toBe(encoded);
      for (const call of writes) {
        expect(call.argv).toEqual(['-i']);
        expect(call.stdin.endsWith('\n')).toBe(true);
        expect(call.stdin.indexOf('\n')).toBe(call.stdin.length - 1);
        expect(call.stdin.length - 1).toBeLessThanOrEqual(4095);
      }
      const commandLines = calls.map((call) => call.argv.join(' ')).join('\n');
      expect(commandLines).toContain('rdc:pw:argv');
      for (const form of formsOf(value)) expect(commandLines).not.toContain(form);
      expect(commandLines).not.toContain(encoded.slice(0, 64));
    }
  );

  posixIt(
    'an entry stored before the armour reads as it was stored, and the next set replaces it',
    async () => {
      const host = await hostOf('darwin');
      const legacy = randomBytes(32).toString('base64');
      execFileSync(join(host.bin, 'security'), [
        'add-generic-password',
        '-a',
        'rdc:org:team:config',
        '-s',
        'rdc-config',
        '-w',
        legacy,
        '-U',
      ]);
      const storage = host.storage();
      expect(await storage.get('rdc:org:team:config')).toBe(legacy);

      const next = randomBytes(32).toString('base64');
      await storage.set('rdc:org:team:config', next);
      expect(await storage.get('rdc:org:team:config')).toBe(next);
      expect(host.keychain()).toEqual({
        'rdc-config\nrdc:org:team:config': `rdc-b64.1.${Buffer.from(next).toString('base64')}`,
      });
    }
  );

  posixIt(
    'a long value spans several items; a shorter set and a delete leave none behind',
    async () => {
      const host = await hostOf('darwin');
      const storage = host.storage();
      const long = randomBytes(6000).toString('base64');
      await storage.set('rdc:pw:parts', long);
      expect(Object.keys(host.keychain()).sort((a, b) => Number(a > b) - Number(a < b))).toEqual([
        'rdc-config\nrdc:pw:parts',
        'rdc-config:1\nrdc:pw:parts',
        'rdc-config:2\nrdc:pw:parts',
        'rdc-config:3\nrdc:pw:parts',
      ]);
      expect(await storage.get('rdc:pw:parts')).toBe(long);

      await storage.set('rdc:pw:parts', 'short');
      expect(host.keychain()).toEqual({ 'rdc-config\nrdc:pw:parts': 'rdc-b64.1.c2hvcnQ=' });
      expect(await storage.get('rdc:pw:parts')).toBe('short');

      await storage.set('rdc:pw:parts', long);
      await storage.delete('rdc:pw:parts');
      expect(host.keychain()).toEqual({});
      expect(await storage.get('rdc:pw:parts')).toBeNull();
    }
  );

  posixIt('a value whose later item is gone reads as null, never as its first part', async () => {
    const host = await hostOf('darwin');
    const storage = host.storage();
    await storage.set('rdc:pw:torn', randomBytes(6000).toString('base64'));
    execFileSync(join(host.bin, 'security'), [
      'delete-generic-password',
      '-a',
      'rdc:pw:torn',
      '-s',
      'rdc-config:2',
    ]);
    expect(await storage.get('rdc:pw:torn')).toBeNull();
  });

  posixIt('with `security` absent, selection refuses and names the tool', async () => {
    const host = await hostOf('darwin', false);
    expect(() => host.storage()).toThrow(host.UnavailableError);
    expect(() => host.storage()).toThrow(/security/);
  });
});

// ─── Windows: DPAPI through the `powershell.exe` stand-in ───────────────

describe('secure storage: the DPAPI backend against a stand-in for `powershell.exe`', () => {
  posixIt('the script is ASCII, holds no double quote, and loads the assembly first', () => {
    for (const script of [PROTECT_SCRIPT, UNPROTECT_SCRIPT]) {
      // A double quote would have to survive the Windows command line; a non-ASCII byte would depend on the code page.
      expect(script).toMatch(/^[\x20-\x7e]+$/);
      expect(script).not.toContain('"');
      expect(script.indexOf('Add-Type -AssemblyName System.Security')).toBeGreaterThan(0);
      expect(script.indexOf('Add-Type')).toBeLessThan(script.indexOf('ProtectedData'));
    }
  });

  posixIt(
    'runs `powershell.exe -NonInteractive -NoProfile -Command <script>` with exactly the two scripts',
    async () => {
      const host = await hostOf('win32');
      const storage = host.storage();
      expect(storage.type).toBe('dpapi');
      const calls = await callsDuring(host, async () => {
        await storage.set('rdc:pw:script', 'value');
        await storage.get('rdc:pw:script');
      });
      expect(calls.map((call) => [call.tool, call.argv])).toEqual([
        ['powershell.exe', ['-NonInteractive', '-NoProfile', '-Command', PROTECT_SCRIPT]],
        ['powershell.exe', ['-NonInteractive', '-NoProfile', '-Command', UNPROTECT_SCRIPT]],
      ]);
    }
  );

  posixIt.each(VALUES)('round-trips %s byte-exact', async (_label, value) => {
    const host = await hostOf('win32');
    const storage = host.storage();
    await storage.set('rdc:pw:value', value);
    expect(await storage.get('rdc:pw:value')).toBe(value);
  });

  posixIt.each(VALUES)(
    'the secret reaches PowerShell on stdin as base64 and is on no command line (%s)',
    async (_label, value) => {
      const host = await hostOf('win32');
      const storage = host.storage();
      const calls = await callsDuring(host, () => storage.set('rdc:pw:argv', value));
      expect(calls).toHaveLength(1);
      // Control: the recorder holds the payload where it does travel.
      expect(calls[0].stdin).toBe(Buffer.from(value).toString('base64'));
      expect(calls[0].stdin).toMatch(/^[A-Za-z0-9+/]*={0,2}$/);
      const commandLine = calls[0].argv.join(' ');
      expect(commandLine).toBe(`-NonInteractive -NoProfile -Command ${PROTECT_SCRIPT}`);
      for (const form of formsOf(value)) expect(commandLine).not.toContain(form);
    }
  );

  posixIt(
    'the key file is named by the SHA-256 of the key and holds the key and the ciphertext, never the secret',
    async () => {
      const host = await hostOf('win32');
      const value = randomBytes(32).toString('base64');
      await host.storage().set('rdc:org:team:config', value);
      const file = dpapiFile(host, 'rdc:org:team:config');
      expect(readdirSync(host.keysDir)).toEqual([file.slice(host.keysDir.length + 1)]);
      const content = readFileSync(file, 'utf-8');
      const stored = JSON.parse(content) as { key: string; blob: string };
      expect(Object.keys(stored)).toEqual(['key', 'blob']);
      expect(stored.key).toBe('rdc:org:team:config');
      expect(stored.blob).toMatch(/^[A-Za-z0-9+/]+=*$/);
      for (const form of formsOf(value)) expect(content).not.toContain(form);
    }
  );

  posixIt(
    'keys that differ only in ":" against "_", or only in letter case, are distinct',
    async () => {
      const host = await hostOf('win32');
      const storage = host.storage();
      const keys = ['a:b', 'a_b', 'A:b', 'A_B'];
      // Distinct even on a file system that folds case: the names are lower-case hex.
      const names = keys.map((key) => dpapiFile(host, key).toLowerCase());
      expect(new Set(names).size).toBe(keys.length);
      for (const key of keys) await storage.set(key, `value of ${key}`);
      for (const key of keys) expect(await storage.get(key)).toBe(`value of ${key}`);
      await storage.delete('a:b');
      expect(await storage.get('a:b')).toBeNull();
      expect(await storage.get('a_b')).toBe('value of a_b');
      expect(readdirSync(host.keysDir)).toHaveLength(3);
    }
  );

  posixIt('a 200-character key has a file name of 70 characters', async () => {
    const host = await hostOf('win32');
    const key = 'K'.repeat(200);
    await host.storage().set(key, 'value');
    expect(readdirSync(host.keysDir).map((name) => name.length)).toEqual([70]);
    expect(await host.storage().get(key)).toBe('value');
  });

  posixIt(
    'a damaged key file, and a key file copied under the name of another key, read as null',
    async () => {
      const host = await hostOf('win32');
      const storage = host.storage();
      await storage.set('rdc:pw:owner', 'value');
      const file = dpapiFile(host, 'rdc:pw:owner');
      const intact = readFileSync(file, 'utf-8');

      writeFileSync(dpapiFile(host, 'rdc:pw:other'), intact);
      expect(await storage.get('rdc:pw:other')).toBeNull();

      const breakout = "'))); New-Item -ItemType File -Path 'C:\\pwned'; #";
      for (const content of [
        breakout,
        JSON.stringify({ key: 'rdc:pw:owner', blob: breakout }),
        JSON.stringify({ key: 'rdc:pw:owner', blob: Buffer.from(breakout).toString('base64') }),
        JSON.stringify({ key: 'rdc:pw:owner' }),
      ]) {
        writeFileSync(file, content);
        const calls = await callsDuring(host, async () => {
          expect(await storage.get('rdc:pw:owner')).toBeNull();
        });
        // Whatever the file held, PowerShell saw the pinned script and base64 on stdin, and nothing of the file as script text.
        for (const call of calls) {
          expect(call.argv[3]).toBe(UNPROTECT_SCRIPT);
          expect(call.stdin).toMatch(/^[A-Za-z0-9+/]*={0,2}$/);
        }
      }
      writeFileSync(file, intact);
      expect(await storage.get('rdc:pw:owner')).toBe('value');
    }
  );

  posixIt(
    'PowerShell that cannot find ProtectedData: selection refuses with its line, and nothing is stored',
    async () => {
      const host = await hostOf('win32');
      // Control: the same host stores a value while the stand-in works.
      await host.storage().set('rdc:pw:control', 'value');
      expect(readdirSync(host.keysDir)).toHaveLength(1);

      process.env.SSTOOLS_POWERSHELL = 'type-not-found';
      const refused = await hostOf('win32');
      let error: unknown;
      try {
        refused.storage();
      } catch (caught) {
        error = caught;
      }
      expect(error).toBeInstanceOf(refused.UnavailableError);
      expect(error).toMatchObject({
        code: 'PRECONDITION_MISMATCH',
        details: ['Unable to find type [Security.Cryptography.ProtectedData].'],
      });
      expect((error as Error).message).toContain('REDIACC_SECRET_STORE=file');
      expect(readdirSync(refused.keysDir)).toEqual([]);
    }
  );

  posixIt(
    'PowerShell that exits 0 and answers nothing is a failure, not an empty value',
    async () => {
      process.env.SSTOOLS_POWERSHELL = 'silent';
      const host = await hostOf('win32');
      expect(() => host.storage()).toThrow(host.UnavailableError);
      expect(readdirSync(host.keysDir)).toEqual([]);
    }
  );

  posixIt('with `powershell.exe` absent, selection refuses and names the tool', async () => {
    const host = await hostOf('win32', false);
    expect(() => host.storage()).toThrow(host.UnavailableError);
    expect(() => host.storage()).toThrow(/powershell/);
  });
});
