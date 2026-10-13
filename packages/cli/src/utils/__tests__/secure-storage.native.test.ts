/**
 * secure-storage.ts against its REAL backends. Nothing in this file is mocked.
 *
 * Every consumer test replaces the module with `vi.mock`, so until this file existed no test ran `keyctl`, `security` or PowerShell at all. Three groups:
 *
 *   1. The key allowlist, on every platform.
 *   2. The native backend of the host OS (keyctl on Linux, Keychain on macOS, DPAPI on Windows): the storage contract, backend selection, a cross-process read, what is left at rest, and that the secret is on no command line (Linux and macOS, through a recording wrapper on PATH; the Windows half is secure-storage.tools.test.ts, because a script cannot stand in for `powershell.exe` there).
 *   3. The file backend, which only `REDIACC_SECRET_STORE=file` selects (operator ruling 2026-10-13: no machine gets a disk-held secret without choosing it).
 *   4. The refusal: with no usable native backend and no opt-in, selection throws and stores nothing. `keyctl` off PATH, and a session keyring that cannot read the user keyring back.
 *
 * SKIP OR FAIL. Group 2 needs a backend the process can write AND read. Where it cannot be reached (a container, a session keyring that does not link the user keyring) the group skips with a printed reason, so a workstation without a keyring keeps a green unit suite. `SECURE_STORAGE_REQUIRE_NATIVE=1` removes the skip: every native test runs and an unreachable backend is a failure.
 * The CI job sets it, and `SECURE_STORAGE_NATIVE_RECEIPT` names a file the suite writes with the backend type and the number of native tests that ran, which the job reads back. A leg whose variable was misspelled writes no receipt and is red.
 *
 * ISOLATION. Keys carry a unique throwaway prefix and are deleted in `afterAll`. On Linux the config, state and cache homes are the per-file temporary ones from isolate-config-home.ts. The kernel user keyring (`@u`) is per-UID and cannot be redirected, so the throwaway keys do pass through it.
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
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { getRediaccDirs } from '@rediacc/shared/paths';
import { afterAll, describe, expect, it } from 'vitest';
import {
  getSecureStorage,
  type SecureStorage,
  SecureStorageUnavailableError,
} from '../secure-storage.js';

const NATIVE_BY_PLATFORM: Partial<Record<NodeJS.Platform, string>> = {
  linux: 'keyctl',
  darwin: 'keychain',
  win32: 'dpapi',
};
const EXPECTED_NATIVE = NATIVE_BY_PLATFORM[process.platform];
const REQUIRE_NATIVE = process.env.SECURE_STORAGE_REQUIRE_NATIVE === '1';
const RECEIPT_PATH = process.env.SECURE_STORAGE_NATIVE_RECEIPT;
const IS_LINUX = process.platform === 'linux';

const HERE = dirname(fileURLToPath(import.meta.url));
const PACKAGE_DIR = join(HERE, '..', '..', '..');
const MODULE_URL = pathToFileURL(join(HERE, '..', 'secure-storage.ts')).href;

// Production key shapes are `rdc:<org>:<team>:<config>` and `rdc:pw:<uuid>`; the throwaway keys keep that alphabet.
const RUN_ID = `${process.pid}-${randomBytes(4).toString('hex')}`;
const createdKeys = new Set<string>();
let keySeq = 0;
function freshKey(label: string): string {
  keySeq += 1;
  const key = `rdc:sstest_${RUN_ID}:${label}-${keySeq}`;
  createdKeys.add(key);
  return key;
}

function secret(bytes = 32): string {
  return randomBytes(bytes).toString('base64');
}

// ─── Reachability of the native backend ─────────────────────────────────

const HINTS: Partial<Record<NodeJS.Platform, string>> = {
  linux:
    "the session keyring must link the user keyring; run under `keyctl session - sh -c 'keyctl link @u @s && <command>'`",
  darwin:
    'the default keychain must exist and be unlocked (`security default-keychain`, `security unlock-keychain`)',
  win32: 'Windows PowerShell (`powershell`) must be on PATH and able to load ProtectedData',
};

interface Probe {
  reachable: boolean;
  type: string;
  detail: string;
}

async function probeNative(): Promise<Probe> {
  let type = 'none';
  try {
    const storage = getSecureStorage();
    type = storage.type;
    if (EXPECTED_NATIVE === undefined) {
      return {
        reachable: false,
        type,
        detail: `no native backend is defined for ${process.platform}`,
      };
    }
    if (type !== EXPECTED_NATIVE) {
      return {
        reachable: false,
        type,
        detail: `selected "${type}", expected "${EXPECTED_NATIVE}"`,
      };
    }
    const key = freshKey('probe');
    const value = secret();
    await storage.set(key, value);
    const got = await storage.get(key);
    await storage.delete(key);
    if (got !== value) {
      const read = got === null ? 'null' : 'a different value';
      return { reachable: false, type, detail: `set succeeded and the read back returned ${read}` };
    }
    return { reachable: true, type, detail: 'write and read back round trip' };
  } catch (error) {
    return {
      reachable: false,
      type,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

const probe = await probeNative();
const runNative = REQUIRE_NATIVE || probe.reachable;
const status = `[secure-storage.native] platform=${process.platform} backend=${probe.type} reachable=${probe.reachable} require=${REQUIRE_NATIVE ? 1 : 0}`;
const skipNote = `NATIVE TESTS SKIPPED: ${probe.detail}; ${HINTS[process.platform] ?? 'unsupported platform'}. SECURE_STORAGE_REQUIRE_NATIVE=1 turns this skip into a failure.`;
process.stderr.write(`${status} ${runNative ? `(${probe.detail})` : skipNote}\n`);

// Every native test goes through here, so the suite can prove afterwards that each one ran.
const declaredNative: string[] = [];
const ranNative = new Set<string>();
function nativeIt(name: string, fn: () => Promise<void> | void, ...only: NodeJS.Platform[]): void {
  const applies = only.length === 0 || only.includes(process.platform);
  if (applies) declaredNative.push(name);
  it.skipIf(!runNative || !applies)(name, async () => {
    ranNative.add(name);
    await fn();
  });
}

// ─── Helpers ────────────────────────────────────────────────────────────

/** Every regular file under `root`, recursively. A missing root is an empty answer. */
function filesUnder(root: string): string[] {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile())
    .map((entry) => join(entry.parentPath, entry.name));
}

/** Every file under `root` whose bytes contain one of the needles. */
function filesContaining(root: string, needles: readonly string[]): string[] {
  return filesUnder(root).filter((path) => {
    const bytes = readFileSync(path);
    return needles.some((needle) => bytes.includes(needle));
  });
}

/** The secret as it could sit in a file or on a command line: raw, and base64 and hex of the raw bytes. */
function atRestForms(value: string): string[] {
  const bytes = Buffer.from(value, 'utf-8');
  return [value, bytes.toString('base64'), bytes.toString('hex')];
}

/** The DPAPI file of a key, computed here and not asked of the module: SHA-256 of the key, in hex. */
function dpapiFile(key: string): string {
  const name = createHash('sha256').update(key, 'utf-8').digest('hex');
  return join(getRediaccDirs().state, 'keys', `${name}.dpapi`);
}

/** The first `name` on PATH, as an absolute path. */
function toolOnPath(name: string): string {
  for (const dir of (process.env.PATH ?? '').split(delimiter)) {
    if (dir !== '' && existsSync(join(dir, name))) return join(dir, name);
  }
  throw new Error(`${name} is not on PATH`);
}

/**
 * A directory to put first on PATH: its `tool` writes every argument it was started with to `log`, one per line, and then becomes the real tool. What the log holds is what `ps` could have shown.
 */
function argvRecorder(tool: string): { bin: string; log: string } {
  const bin = mkdtempSync(join(tmpdir(), 'rdc-sstest-argv-'));
  const log = join(bin, 'argv.log');
  const script = [
    '#!/bin/sh',
    `for arg in "$@"; do printf '%s\\n' "$arg"; done >> '${log}'`,
    `exec '${toolOnPath(tool)}' "$@"`,
    '',
  ].join('\n');
  writeFileSync(join(bin, tool), script);
  chmodSync(join(bin, tool), 0o755);
  return { bin, log };
}

/** The password of one Keychain item, read with the tool and not the module; null when the item is absent. */
function keychainItem(key: string, service: string): string | null {
  const run = spawnSync('security', ['find-generic-password', '-a', key, '-s', service, '-w'], {
    encoding: 'utf-8',
  });
  return run.status === 0 ? run.stdout.replace(/\n$/, '') : null;
}

/** The per-file temporary home that holds the Linux config, state and cache directories. */
function linuxHome(): string {
  return dirname(dirname(getRediaccDirs().config));
}

function unlinkFromUserKeyring(key: string): void {
  try {
    const id = execFileSync('keyctl', ['search', '@u', 'user', key], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    if (id) execFileSync('keyctl', ['unlink', id, '@u'], { stdio: 'ignore' });
  } catch {
    // Absent key or absent keyctl: nothing to remove.
  }
}

const KNOB = 'REDIACC_SECRET_STORE';

/** Runs `fn` with the knob set to `value` (undefined unsets it), then puts the previous value back. */
function withKnob<T>(value: string | undefined, fn: () => T): T {
  const saved = process.env[KNOB];
  if (value === undefined) delete process.env[KNOB];
  else process.env[KNOB] = value;
  try {
    return fn();
  } finally {
    if (saved === undefined) delete process.env[KNOB];
    else process.env[KNOB] = saved;
  }
}

/** The file backend, the way a user reaches it: the knob. Selection reads the knob in getSecureStorage() and the backend never reads it again. */
function openFileStore(): SecureStorage {
  return withKnob('file', getSecureStorage);
}

/** Descriptions of the keys in the user keyring that a probe of process `pid` would have left. */
function probeKeysOf(pid: number): string[] {
  const listing = execFileSync('keyctl', ['show', '@u'], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  return listing.split('\n').filter((line) => line.includes(`rdc:probe:${pid}-`));
}

// The child takes everything as arguments: module URL, operation, key, value. It selects the storage TWICE, so "once per process" has a second call to hold against, and it reports a refusal instead of dying on it.
const CHILD_SCRIPT = `
const [moduleUrl, op, key, value] = process.argv.slice(1);
const { getSecureStorage } = await import(moduleUrl);
const result = { pid: process.pid, type: null, value: null, error: null };
try {
  getSecureStorage();
  const storage = getSecureStorage();
  result.type = storage.type;
  if (op === 'set' || op === 'roundtrip') await storage.set(key, value);
  if (op === 'get' || op === 'roundtrip') result.value = await storage.get(key);
} catch (error) {
  result.error = { name: error.name, code: error.code ?? null, message: error.message, details: error.details ?? null };
}
process.stdout.write('SSTEST_RESULT ' + JSON.stringify(result) + '\\n');
`;

interface ChildResult {
  pid: number;
  type: string | null;
  value: string | null;
  error: { name: string; code: string | null; message: string; details: string[] | null } | null;
  /** Everything the child wrote, so a test can hold stdout to the result line and count the notices on stderr. */
  stdout: string;
  stderr: string;
}

interface ChildOptions {
  /** Prefixes the command, for example `keyctl session -`. */
  wrap?: readonly string[];
  /** Overrides on top of this process's environment; undefined removes a variable. */
  env?: Record<string, string | undefined>;
}

/** Runs the real module in a SEPARATE node process. */
function inChild(
  op: 'select' | 'set' | 'get' | 'roundtrip',
  key = '',
  value = '',
  options: ChildOptions = {}
): ChildResult {
  const argv = [
    ...(options.wrap ?? []),
    process.execPath,
    '--import',
    'tsx',
    '--input-type=module',
    '-e',
    CHILD_SCRIPT,
    MODULE_URL,
    op,
    key,
    value,
  ];
  const env: NodeJS.ProcessEnv = { ...process.env };
  // A knob left in the developer's shell must not choose the backend of a test that did not ask for it.
  delete env[KNOB];
  for (const [name, override] of Object.entries(options.env ?? {})) {
    if (override === undefined) delete env[name];
    else env[name] = override;
  }
  const run = spawnSync(argv[0], argv.slice(1), { cwd: PACKAGE_DIR, encoding: 'utf-8', env });
  const line = run.stdout.split('\n').find((l) => l.startsWith('SSTEST_RESULT '));
  if (line === undefined) {
    throw new Error(
      `the child printed no SSTEST_RESULT line (status ${run.status}): ${run.stdout}${run.stderr}`
    );
  }
  const result = JSON.parse(line.slice('SSTEST_RESULT '.length)) as Omit<
    ChildResult,
    'stdout' | 'stderr'
  >;
  return { ...result, stdout: run.stdout, stderr: run.stderr };
}

/** A directory with no tool in it, to stand in for PATH on a machine without `keyctl`. */
function emptyPath(): string {
  return mkdtempSync(join(tmpdir(), 'rdc-sstest-nopath-'));
}

const VALUE_CLASSES: readonly (readonly [string, string])[] = [
  ['the production shape (base64 of 32 bytes)', secret()],
  ['a leading dash (base64url alphabet)', `-${secret().replaceAll('+', '-').replaceAll('/', '_')}`],
  ['an embedded newline', 'line one\nline two'],
  ['a trailing newline, CRLF and outer spaces', '  padded\r\nvalue \n'],
  ['only hex digits (what `security` prints for bytes it will not show)', '6c696e65206f6e650a'],
  ['single and double quotes', `it's a "quoted" value`],
  ['a dollar sign and backticks', 'cost $HOME $(id) `id` ${PATH}'],
  ['unicode', 'şifre-пароль-密码-🔑'],
  ['4 KB', randomBytes(3072).toString('base64')],
  ['3 KB of unicode lines (two Keychain items)', 'şifre-密码-🔑\n'.repeat(160)],
];

type Register = (name: string, fn: () => Promise<void> | void) => void;

/** The storage contract every backend owes its callers. Registered once for the native backend and once for the file backend. */
function storageContract(register: Register, open: () => SecureStorage): void {
  for (const [label, value] of VALUE_CLASSES) {
    register(`round-trips ${label} byte-exact`, async () => {
      const storage = open();
      const key = freshKey('value');
      await storage.set(key, value);
      expect(await storage.get(key)).toBe(value);
    });
  }

  register('a missing key reads as null', async () => {
    expect(await open().get(freshKey('missing'))).toBeNull();
  });

  register('a second set overwrites the first', async () => {
    const storage = open();
    const key = freshKey('overwrite');
    const first = secret();
    const second = secret();
    await storage.set(key, first);
    await storage.set(key, second);
    expect(await storage.get(key)).toBe(second);
  });

  register('delete then get returns null, and deleting a missing key resolves', async () => {
    const storage = open();
    const key = freshKey('delete');
    await storage.set(key, secret());
    await storage.delete(key);
    expect(await storage.get(key)).toBeNull();
    await expect(storage.delete(key)).resolves.toBeUndefined();
  });

  register('two keys do not collide, and deleting one leaves the other', async () => {
    const storage = open();
    const a = freshKey('pair');
    const b = freshKey('pair');
    const valueA = secret();
    const valueB = secret();
    await storage.set(a, valueA);
    await storage.set(b, valueB);
    expect(await storage.get(a)).toBe(valueA);
    expect(await storage.get(b)).toBe(valueB);
    await storage.delete(a);
    expect(await storage.get(a)).toBeNull();
    expect(await storage.get(b)).toBe(valueB);
  });
}

afterAll(async () => {
  if (probe.type !== 'none') {
    const storage = getSecureStorage();
    for (const key of createdKeys) await storage.delete(key).catch(() => {});
  }
  // Independent of the module under test: a run that broke `delete` must not leave throwaway keys in the user keyring.
  if (IS_LINUX) for (const key of createdKeys) unlinkFromUserKeyring(key);
  if (!REQUIRE_NATIVE) return;
  // Under the requirement a native test that did not run is a failure, never a pass.
  const missed = declaredNative.filter((name) => !ranNative.has(name));
  if (RECEIPT_PATH) {
    const receipt = {
      platform: process.platform,
      backend: probe.type,
      reachable: probe.reachable,
      declared: declaredNative.length,
      ran: ranNative.size,
    };
    writeFileSync(RECEIPT_PATH, `${JSON.stringify(receipt)}\n`);
  }
  expect(declaredNative.length).toBeGreaterThan(0);
  expect(missed).toEqual([]);
});

// ─── 1. Key allowlist ───────────────────────────────────────────────────

describe('secure storage: key allowlist (ValidatingStorage)', () => {
  const UNSAFE_KEYS: readonly (readonly [string, string])[] = [
    ['empty', ''],
    ['a space', 'rdc:pw a'],
    ['a shell separator', 'rdc:pw;id'],
    ['a path traversal', '../../etc/passwd'],
    ['a slash', 'rdc/pw'],
    ['a newline', 'rdc:pw\nx'],
    ['a PowerShell breakout', "k'; Write-Output pwned; '"],
    ['a non-ASCII letter', 'rdc:pw:é'],
    ['201 characters', 'k'.repeat(201)],
  ];

  // Through the file backend, so the allowlist is tested on a host with no usable native backend too.
  it.each(UNSAFE_KEYS)('refuses a key with %s on get, set and delete', async (_label, key) => {
    const storage = openFileStore();
    // The wrapper throws before any promise exists, so each call sits inside an async function.
    await expect((async () => storage.get(key))()).rejects.toThrow(
      /Refusing unsafe secure-storage key/
    );
    await expect((async () => storage.set(key, 'v'))()).rejects.toThrow(
      /Refusing unsafe secure-storage key/
    );
    await expect((async () => storage.delete(key))()).rejects.toThrow(
      /Refusing unsafe secure-storage key/
    );
  });

  it.skipIf(!IS_LINUX)(
    'a refused set reaches no backend, and a 200-character key is accepted (file backend)',
    async () => {
      const storage = openFileStore();
      const store = join(getRediaccDirs().state, 'secure-keys.json');
      const before = existsSync(store) ? readFileSync(store, 'utf-8') : null;
      await expect((async () => storage.set('rdc:pw a', 'leak-canary'))()).rejects.toThrow(
        /Refusing/
      );
      expect(existsSync(store) ? readFileSync(store, 'utf-8') : null).toBe(before);

      const longest = `${freshKey('max')}:`.padEnd(200, 'k');
      createdKeys.add(longest);
      const value = secret();
      await storage.set(longest, value);
      expect(await storage.get(longest)).toBe(value);
      await storage.delete(longest);
    }
  );
});

// ─── 2. The native backend of this OS ───────────────────────────────────

describe(`secure storage: native backend (${EXPECTED_NATIVE ?? 'none'} on ${process.platform})`, () => {
  it.skipIf(!REQUIRE_NATIVE)(
    'SECURE_STORAGE_REQUIRE_NATIVE: the native backend is reachable, so nothing below is skipped',
    () => {
      const hint = HINTS[process.platform] ?? 'unsupported platform';
      expect(probe, `${probe.detail}; ${hint}`).toMatchObject({
        reachable: true,
        type: EXPECTED_NATIVE,
      });
    }
  );

  nativeIt('backend selection returns the native backend of this OS', () => {
    expect(EXPECTED_NATIVE).toBeDefined();
    expect(getSecureStorage().type).toBe(EXPECTED_NATIVE);
  });

  storageContract(nativeIt, getSecureStorage);

  nativeIt('a value stored by this process is read back by a separate process', async () => {
    const key = freshKey('xproc-out');
    const value = secret();
    await getSecureStorage().set(key, value);
    expect(inChild('get', key)).toMatchObject({ type: EXPECTED_NATIVE, value, error: null });
  });

  nativeIt('a value stored by a separate process is read back by this one', async () => {
    const key = freshKey('xproc-in');
    const value = secret();
    expect(inChild('set', key, value).type).toBe(EXPECTED_NATIVE);
    expect(await getSecureStorage().get(key)).toBe(value);
  });

  nativeIt(
    'Linux: after a set through keyctl no file under the config, state or cache home holds the secret',
    async () => {
      const key = freshKey('at-rest');
      const value = secret();
      // The directories exist and are scanned for real: a planted marker must be found by the same scanner.
      const marker = `marker-${secret()}`;
      const { config, state, cache } = getRediaccDirs();
      for (const dir of [config, state, cache]) mkdirSync(dir, { recursive: true });
      writeFileSync(join(state, 'sstest-marker'), marker);
      await getSecureStorage().set(key, value);
      expect(await getSecureStorage().get(key)).toBe(value);
      expect(filesContaining(linuxHome(), [marker])).toEqual([join(state, 'sstest-marker')]);
      expect(filesContaining(linuxHome(), atRestForms(value))).toEqual([]);
      rmSync(join(state, 'sstest-marker'));
    },
    'linux'
  );

  nativeIt(
    'Linux: selection proves the keyring with a throwaway key and leaves none behind',
    () => {
      const child = inChild('select');
      expect(child).toMatchObject({ type: 'keyctl', error: null });
      expect(probeKeysOf(child.pid)).toEqual([]);
    },
    'linux'
  );

  nativeIt(
    'Linux: a session keyring that does not link @u is refused, naming `keyctl link @u @s` and the opt-in, and nothing is stored (the hosted-runner shape that read back null)',
    async () => {
      const key = freshKey('unlinked');
      const value = secret();
      // Control: the same child in THIS session, whose keyring is readable, stores and reads the value.
      expect(inChild('roundtrip', key, value)).toMatchObject({
        type: 'keyctl',
        value,
        error: null,
      });
      await getSecureStorage().delete(key);

      // `keyctl session -` gives the child a fresh, empty session keyring: @u is writable by UID and not possessed, so a write lands and the read is denied.
      const child = inChild('roundtrip', key, value, { wrap: ['keyctl', 'session', '-'] });
      expect(child.type).toBeNull();
      expect(child.value).toBeNull();
      expect(child.error).toMatchObject({
        name: 'SecureStorageUnavailableError',
        code: 'PRECONDITION_MISMATCH',
      });
      expect(child.error?.message).toContain('keyctl link @u @s');
      expect(child.error?.message).toContain('REDIACC_SECRET_STORE=file');
      // The refusal came before the write: this process, whose session does link @u, finds neither the value nor the probe's throwaway key.
      expect(await getSecureStorage().get(key)).toBeNull();
      expect(probeKeysOf(child.pid)).toEqual([]);
    },
    'linux'
  );

  nativeIt(
    'Windows: a value shaped like a PowerShell breakout round-trips byte-exact and executes nothing',
    async () => {
      const storage = getSecureStorage();
      const canaryDir = mkdtempSync(join(tmpdir(), 'rdc-sstest-canary-'));
      const canary = join(canaryDir, 'pwned');
      const hostile = [
        "'; Write-Output pwned; '",
        `'; New-Item -ItemType File -Path '${canary}'; '`,
        `"; New-Item -ItemType File -Path "${canary}"; "`,
        `$(New-Item -ItemType File -Path '${canary}')`,
      ];
      for (const value of hostile) {
        const key = freshKey('ps-breakout');
        await storage.set(key, value);
        expect(await storage.get(key)).toBe(value);
        expect(existsSync(canary)).toBe(false);
      }
      rmSync(canaryDir, { recursive: true, force: true });
    },
    'win32'
  );

  nativeIt(
    'Windows: a tampered key file reads as null and executes nothing',
    async () => {
      const storage = getSecureStorage();
      const canaryDir = mkdtempSync(join(tmpdir(), 'rdc-sstest-canary-'));
      const canary = join(canaryDir, 'pwned');
      const key = freshKey('tampered');
      const value = secret();
      await storage.set(key, value);
      const file = dpapiFile(key);
      const intact = readFileSync(file, 'utf-8');
      // Control: the file this test is about to damage is the one the module reads.
      expect(await storage.get(key)).toBe(value);

      const breakout = `'))); New-Item -ItemType File -Path '${canary}'; #`;
      // Not JSON at all, then JSON whose ciphertext is script text, then ciphertext that is base64 and not a DPAPI blob.
      const damaged = [
        breakout,
        JSON.stringify({ key, blob: breakout }),
        JSON.stringify({ key, blob: Buffer.from(breakout).toString('base64') }),
      ];
      for (const content of damaged) {
        writeFileSync(file, content);
        expect(await storage.get(key)).toBeNull();
        expect(existsSync(canary)).toBe(false);
      }
      writeFileSync(file, intact);
      expect(await storage.get(key)).toBe(value);
      rmSync(canaryDir, { recursive: true, force: true });
    },
    'win32'
  );

  nativeIt(
    'Windows: the key file holds the key and DPAPI ciphertext, never the secret, its base64 or its hex',
    async () => {
      const key = freshKey('at-rest');
      const value = secret();
      await getSecureStorage().set(key, value);
      const file = dpapiFile(key);
      expect(existsSync(file)).toBe(true);
      const stored = JSON.parse(readFileSync(file, 'utf-8')) as { key: string; blob: string };
      expect(stored.key).toBe(key);
      expect(stored.blob).toMatch(/^[A-Za-z0-9+/]+=*$/);
      // A DPAPI blob is longer than what it protects.
      expect(Buffer.from(stored.blob, 'base64').length).toBeGreaterThan(Buffer.from(value).length);
      expect(filesContaining(dirname(file), atRestForms(value))).toEqual([]);
    },
    'win32'
  );

  nativeIt(
    'Windows: keys that differ only in ":" against "_", or only in letter case, are distinct and have distinct files',
    async () => {
      const storage = getSecureStorage();
      const colon = freshKey('alias');
      const underscore = colon.replaceAll(':', '_');
      const upper = colon.toUpperCase();
      createdKeys.add(underscore);
      createdKeys.add(upper);
      const values = new Map([colon, underscore, upper].map((key) => [key, secret()]));
      expect(new Set([...values.keys()].map(dpapiFile)).size).toBe(3);
      for (const [key, value] of values) await storage.set(key, value);
      for (const [key, value] of values) expect(await storage.get(key)).toBe(value);
      await storage.delete(colon);
      expect(await storage.get(colon)).toBeNull();
      expect(await storage.get(underscore)).toBe(values.get(underscore));
      expect(await storage.get(upper)).toBe(values.get(upper));
    },
    'win32'
  );

  nativeIt(
    'Windows: a key file copied under the name of another key does not answer for it',
    async () => {
      const storage = getSecureStorage();
      const owner = freshKey('owner');
      const other = freshKey('other');
      await storage.set(owner, secret());
      writeFileSync(dpapiFile(other), readFileSync(dpapiFile(owner)));
      expect(await storage.get(other)).toBeNull();
      rmSync(dpapiFile(other));
    },
    'win32'
  );

  nativeIt(
    'macOS: an entry stored before the armour (the value as given, under `rdc-config`) still reads, and the next set replaces it',
    async () => {
      const storage = getSecureStorage();
      const key = freshKey('legacy');
      const legacy = secret();
      // The command the earlier code ran. A throwaway value, so its place on this command line gives nothing away.
      execFileSync('security', [
        'add-generic-password',
        '-a',
        key,
        '-s',
        'rdc-config',
        '-w',
        legacy,
        '-U',
      ]);
      expect(keychainItem(key, 'rdc-config')).toBe(legacy);
      expect(await storage.get(key)).toBe(legacy);

      const next = secret();
      await storage.set(key, next);
      expect(await storage.get(key)).toBe(next);
      expect(keychainItem(key, 'rdc-config')).toBe(
        `rdc-b64.1.${Buffer.from(next).toString('base64')}`
      );
    },
    'darwin'
  );

  nativeIt(
    'macOS: a long value spans several items, and a shorter set or a delete leaves none of them behind',
    async () => {
      const storage = getSecureStorage();
      const key = freshKey('parts');
      const long = randomBytes(6000).toString('base64');
      await storage.set(key, long);
      expect(await storage.get(key)).toBe(long);
      expect(keychainItem(key, 'rdc-config')).toMatch(/^rdc-b64\.4\.[A-Za-z0-9+/]{3072}$/);
      expect(keychainItem(key, 'rdc-config:3')).not.toBeNull();
      expect(keychainItem(key, 'rdc-config:4')).toBeNull();

      const short = secret();
      await storage.set(key, short);
      expect(await storage.get(key)).toBe(short);
      expect(keychainItem(key, 'rdc-config:1')).toBeNull();

      await storage.set(key, long);
      await storage.delete(key);
      expect(await storage.get(key)).toBeNull();
      for (const service of ['rdc-config', 'rdc-config:1', 'rdc-config:2', 'rdc-config:3']) {
        expect(keychainItem(key, service)).toBeNull();
      }
    },
    'darwin'
  );

  nativeIt(
    'Linux, macOS: the secret is on no command line of the native tool, in any encoding',
    () => {
      const tool = IS_LINUX ? 'keyctl' : 'security';
      const recorder = argvRecorder(tool);
      const key = freshKey('argv');
      const value = secret();
      const child = inChild('roundtrip', key, value, {
        env: { PATH: `${recorder.bin}${delimiter}${process.env.PATH ?? ''}` },
      });
      const recorded = readFileSync(recorder.log, 'utf-8');
      rmSync(recorder.bin, { recursive: true, force: true });

      expect(child).toMatchObject({ type: EXPECTED_NATIVE, value, error: null });
      // Control: the recorder saw the calls of this round trip, the write included. Without that an empty log would pass.
      const args = recorded.split('\n');
      expect(args).toContain(key);
      expect(args).toContain(IS_LINUX ? 'padd' : '-i');
      for (const form of atRestForms(value)) expect(recorded).not.toContain(form);
    },
    'linux',
    'darwin'
  );
});

// ─── 3. The file backend, by opt-in ─────────────────────────────────────

describe('secure storage: the file backend chosen with REDIACC_SECRET_STORE=file (Linux)', () => {
  const fileIt: Register = (name, fn) => {
    it.skipIf(!IS_LINUX)(name, fn);
  };

  fileIt(
    'the secret sits in plaintext in state/secure-keys.json at mode 0600, and a file that was wider is narrowed',
    async () => {
      const storage = openFileStore();
      expect(storage.type).toBe('file');

      const store = join(getRediaccDirs().state, 'secure-keys.json');
      mkdirSync(dirname(store), { recursive: true });
      writeFileSync(store, '{}', { mode: 0o644 });

      const key = freshKey('file');
      const value = secret();
      await storage.set(key, value);

      expect(statSync(store).mode & 0o777).toBe(0o600);
      expect((JSON.parse(readFileSync(store, 'utf-8')) as Record<string, string>)[key]).toBe(value);
      // The same scanner that finds nothing after a keyctl set finds the secret here, in exactly one file.
      expect(filesContaining(linuxHome(), [value])).toEqual([store]);
      await storage.delete(key);
      expect(filesContaining(linuxHome(), [value])).toEqual([]);
    }
  );

  fileIt(
    'with keyctl off PATH and the opt-in set: the file backend, one notice on stderr, and nothing but the result on stdout',
    () => {
      const bin = emptyPath();
      const key = freshKey('optin');
      const value = secret();
      const child = inChild('roundtrip', key, value, { env: { PATH: bin, [KNOB]: 'file' } });
      rmSync(bin, { recursive: true, force: true });

      expect(child).toMatchObject({ type: 'file', value, error: null });
      // The child selected the storage twice; the notice is per process.
      expect(child.stderr.split(`${KNOB}=file`).length - 1).toBe(1);
      expect(child.stderr).toContain(join(getRediaccDirs().state, 'secure-keys.json'));
      expect(child.stdout.trim().split('\n')).toHaveLength(1);
      expect(child.stdout).not.toContain(KNOB);
      expect(statSync(join(getRediaccDirs().state, 'secure-keys.json')).mode & 0o777).toBe(0o600);
    }
  );

  fileIt(
    'the opt-in is a choice, not a fallback: it selects the file backend on a host whose keyring works',
    () => {
      expect(openFileStore().type).toBe('file');
    }
  );

  storageContract(fileIt, openFileStore);
});

// ─── 4. The refusal ─────────────────────────────────────────────────────

describe('secure storage: no usable native backend and no opt-in', () => {
  it.skipIf(!IS_LINUX)(
    'Linux, keyctl off PATH: selection refuses, naming `keyctl` and the opt-in, and writes no file',
    () => {
      const store = join(getRediaccDirs().state, 'secure-keys.json');
      const before = existsSync(store) ? readFileSync(store, 'utf-8') : null;
      const bin = emptyPath();
      // Control: the same child, same empty PATH, reaches a backend once the opt-in is set. The refusal below is the knob's absence, not a child that cannot start.
      expect(inChild('select', '', '', { env: { PATH: bin, [KNOB]: 'file' } })).toMatchObject({
        type: 'file',
        error: null,
      });

      const child = inChild('roundtrip', freshKey('refused'), secret(), { env: { PATH: bin } });
      rmSync(bin, { recursive: true, force: true });

      expect(child.type).toBeNull();
      expect(child.error).toMatchObject({
        name: 'SecureStorageUnavailableError',
        code: 'PRECONDITION_MISMATCH',
      });
      expect(child.error?.message).toContain('`keyctl` is not installed');
      expect(child.error?.message).toContain('REDIACC_SECRET_STORE=file');
      expect(existsSync(store) ? readFileSync(store, 'utf-8') : null).toBe(before);
      expect(child.stdout.trim().split('\n')).toHaveLength(1);
    }
  );

  it('the refusal is a typed error that carries its own guidance', () => {
    const error = new SecureStorageUnavailableError(
      'no keyring',
      'add_key: Operation not permitted'
    );
    expect(error).toBeInstanceOf(Error);
    expect(error).toMatchObject({
      name: 'SecureStorageUnavailableError',
      code: 'PRECONDITION_MISMATCH',
      retryable: false,
      guidance: 'no keyring',
      details: ['add_key: Operation not permitted'],
    });
  });

  it('a value of the knob other than "file" is refused, never read as unset', () => {
    expect(() => withKnob('File', getSecureStorage)).toThrow(
      /REDIACC_SECRET_STORE is set to "File"/
    );
    expect(() => withKnob('keyring', getSecureStorage)).toThrow(/not a secret store/);
  });
});
