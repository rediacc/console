/**
 * Platform-Native Secure Storage
 *
 * Stores secrets (passkey_secret) in OS-native secure storage:
 * - Linux:   Kernel user keyring (keyctl @u); emptied at every restart, the device then enrolls again
 * - macOS:   Keychain (security command), the value armoured as base64 so any string comes back byte-exact
 * - Windows: DPAPI (one ciphertext file per key, named by the SHA-256 of the key)
 *
 * NO SECRET ON A COMMAND LINE. Every backend hands the value to its tool on standard input, never as an argument: an argument is readable by other processes for the life of the child (`ps`, procfs) and is what process-creation auditing records.
 *
 * ONE RULE ON EVERY PLATFORM (operator ruling 2026-10-13). The native backend is used only after it stored, read back and removed a throwaway key in this process. When it cannot, selection refuses with SecureStorageUnavailableError, whose message names the missing tool and the opt-in. No machine gets a disk-held secret without choosing it:
 * `REDIACC_SECRET_STORE=file` selects the file backend (a JSON file, mode 0o600, in the CLI state directory) and says so once per process on stderr.
 *
 * Each secret is indexed by a server-provided storageKeyId.
 */

import { type ExecFileSyncOptionsWithStringEncoding, execFileSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { chmodSync, existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getRediaccDirs } from '@rediacc/shared/paths';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from './cli-exit-error.js';

const SERVICE_NAME = 'rdc-config';

// ─── Key allowlist (defense-in-depth) ───────────────────────────────────
//
// The storage key (`storageKeyId`) is SERVER-provided over the config-remote handoff, so it reaches these sinks fully untrusted. Even though every backend below passes it as an argv element or one token of a `security -i` line (never interpolated into a shell string or a script), we reject anything outside a conservative allowlist so a hostile value can never reach a native tool at all. Covers the handoff storageKeyId and
// the `rdc:pw:<uuid>` password-flow keys.
const SAFE_KEY = /^[A-Za-z0-9:_-]{1,200}$/;

function assertSafeStorageKey(key: string): void {
  if (!SAFE_KEY.test(key)) {
    throw new Error(
      `Refusing unsafe secure-storage key: only [A-Za-z0-9:_-] (max 200 chars) are allowed`
    );
  }
}

// ─── Interface ──────────────────────────────────────────────────────────

export interface SecureStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  readonly type: string;
}

/**
 * This device has no usable place for its secrets, and the file backend was not chosen. The message names what is missing and the opt-in (`REDIACC_SECRET_STORE=file`); `details` carries the native tool's own error line when it gave one. Thrown by `getSecureStorage()` before anything is stored, so a caller's `handleError` reports it with its code and guidance.
 */
export class SecureStorageUnavailableError extends CliExitError {
  constructor(message: string, detail?: string) {
    super(ERROR_CODES.PRECONDITION_MISMATCH, message, {
      details: detail === undefined ? undefined : [detail],
      retryable: false,
      guidance: message,
    });
    this.name = 'SecureStorageUnavailableError';
  }
}

// ─── Backends ───────────────────────────────────────────────────────────

/**
 * A native tool that could not do what was asked. Carries the tool's first stderr line and never Node's own error, whose message repeats the whole command line.
 */
class ToolFailure extends Error {
  constructor(
    tool: string,
    /** The tool itself could not be started (not installed, or not on PATH). */
    readonly missing: boolean,
    readonly detail: string | undefined
  ) {
    super(detail === undefined ? `${tool} failed` : `${tool}: ${detail}`);
    this.name = 'ToolFailure';
  }
}

function toolFailure(tool: string, error: unknown): ToolFailure {
  const { code, stderr } = error as { code?: unknown; stderr?: unknown };
  const line =
    typeof stderr === 'string'
      ? stderr
          .split('\n')
          .map((text) => text.trim())
          .find((text) => text.length > 0)
      : undefined;
  return new ToolFailure(tool, code === 'ENOENT', line);
}

/** stdout as text; the tool's stderr never reaches the terminal. */
const QUIET: ExecFileSyncOptionsWithStringEncoding = {
  encoding: 'utf-8',
  stdio: ['ignore', 'pipe', 'ignore'],
};

/** The payload goes to the tool on stdin; stdout and stderr come back as text, so a failure can quote the tool's own words. */
function fed(input: string): ExecFileSyncOptionsWithStringEncoding {
  return { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'], input };
}

function settle<T>(operation: () => T): Promise<T> {
  try {
    return Promise.resolve(operation());
  } catch (error) {
    return Promise.reject(error instanceof Error ? error : new Error(String(error)));
  }
}

/**
 * Every backend does its work synchronously (`read`, `write`, `remove`), which is what lets `getSecureStorage()` prove a native one with a real round trip before it hands it out. The promise methods of `SecureStorage` are those same three operations.
 */
abstract class Backend implements SecureStorage {
  abstract readonly type: string;
  abstract read(key: string): string | null;
  abstract write(key: string, value: string): void;
  abstract remove(key: string): void;

  get(key: string): Promise<string | null> {
    return settle(() => this.read(key));
  }

  set(key: string, value: string): Promise<void> {
    return settle(() => this.write(key, value));
  }

  delete(key: string): Promise<void> {
    return settle(() => this.remove(key));
  }
}

// ─── Linux: Kernel Keyring (keyctl) ─────────────────────────────────────

class KeyctlStorage extends Backend {
  readonly type = 'keyctl';

  read(key: string): string | null {
    try {
      const keyId = execFileSync('keyctl', ['search', '@u', 'user', key], QUIET).trim();
      if (!keyId) return null;
      return execFileSync('keyctl', ['pipe', keyId], QUIET);
    } catch {
      return null;
    }
  }

  write(key: string, value: string): void {
    // Remove existing key if present
    this.remove(key);
    try {
      // `padd` reads the payload from stdin to its end, byte for byte; `add` took it as an argument.
      execFileSync('keyctl', ['padd', 'user', key, '@u'], fed(value));
    } catch (error) {
      throw toolFailure('keyctl', error);
    }
    // No timeout is set, and the key still does NOT outlive a restart: `@u` is the kernel's per-UID user keyring, held in kernel memory, so a reboot (on WSL, a restart of the VM) empties it, and the kernel may also free it once the user's last process exits. deriveCek() then finds no secret, and `rdc config remote enable` enrolls the device again (config-remote-reenroll.ts). Memory-only is the operator's choice (2026-10-13): there is no disk-held default.
  }

  remove(key: string): void {
    try {
      const keyId = execFileSync('keyctl', ['search', '@u', 'user', key], QUIET).trim();
      if (keyId) {
        execFileSync('keyctl', ['unlink', keyId, '@u'], QUIET);
      }
    } catch {
      // Key doesn't exist, ok
    }
  }
}

// ─── macOS: Keychain ────────────────────────────────────────────────────
//
// TWO PROPERTIES OF `security` SHAPE THIS BACKEND (Apple's SecurityTool source, and the first macOS run of the native suite).
//
// 1. `find-generic-password -w` prints the stored bytes as they are only when every byte is printable; otherwise it prints their hex digits, with nothing to tell the two apart. A value with a newline or a non-ASCII letter came back as hex.
//    So the value is stored ARMOURED, as `rdc-b64.<parts>.<base64 of the UTF-8 bytes>`: printable ASCII only, which `security` never rewrites. Hex output is never decoded, so a value that is itself hex digits needs no guess.
// 2. `add-generic-password` takes the password as an argument, or prompts for it through getpass(3), which reads the terminal. The one way to keep it off argv is `security -i`, which reads whole command lines from stdin.
//    A line there is at most 4095 bytes (`MAX_LINE_LEN 4096`), and a longer one is cut and its tail run as the next command. So the base64 text is split into parts that fit, one Keychain item each: the head under service `rdc-config`, part N under `rdc-config:N`.
//
// LEGACY ENTRIES. Before the armour, the value was stored as given. Every value this CLI stored is base64 text (a slot secret), which can never start with `rdc-b64.`: neither `-` nor `.` is in the base64 alphabet. A head without the marker is therefore a legacy entry and is returned as it is; the next write replaces it with the armoured form.

const KEYCHAIN_ARMOUR = /^rdc-b64\.(\d+)\.([A-Za-z0-9+/=]*)$/;
/** Base64 characters per Keychain item. With the longest key (200) the command line stays under 3400 bytes. */
const KEYCHAIN_PART_CHARS = 3072;
/** The longest line `security -i` takes whole. */
const SECURITY_LINE_MAX = 4095;
/** A token `security -i` passes through untouched: no whitespace, quote or backslash, the three things its line splitter interprets. */
const SECURITY_TOKEN = /^[A-Za-z0-9+/=:._-]+$/;

function keychainService(part: number): string {
  return part === 0 ? SERVICE_NAME : `${SERVICE_NAME}:${part}`;
}

/** One command line for `security -i`. Refuses a token the tool would reinterpret and a line it would cut, so neither can reach it. */
function securityLine(tokens: readonly string[]): string {
  const line = tokens.join(' ');
  if (!tokens.every((token) => SECURITY_TOKEN.test(token)) || line.length > SECURITY_LINE_MAX) {
    throw new Error('Refusing a `security` command line the tool would not read as written');
  }
  // The newline is part of the command: at EOF the tool drops a line that has none.
  return `${line}\n`;
}

class KeychainStorage extends Backend {
  readonly type = 'keychain';

  /** The password of one item, without the newline `security` prints after it. */
  private find(key: string, part: number): string | null {
    try {
      const printed = execFileSync(
        'security',
        ['find-generic-password', '-a', key, '-s', keychainService(part), '-w'],
        QUIET
      );
      return printed.endsWith('\n') ? printed.slice(0, -1) : printed;
    } catch {
      return null;
    }
  }

  read(key: string): string | null {
    const head = this.find(key, 0);
    if (head === null) return null;
    const armoured = KEYCHAIN_ARMOUR.exec(head);
    // A legacy entry: stored as given, returned as the code that stored it returned it.
    if (!armoured) return head.trim() || null;
    let encoded = armoured[2];
    for (let part = 1; part < Number(armoured[1]); part++) {
      const next = this.find(key, part);
      if (next === null) return null;
      encoded += next;
    }
    return Buffer.from(encoded, 'base64').toString('utf-8');
  }

  write(key: string, value: string): void {
    const encoded = Buffer.from(value, 'utf-8').toString('base64');
    const parts = encoded.match(new RegExp(`.{1,${KEYCHAIN_PART_CHARS}}`, 'g')) ?? [''];
    // Every part of the previous value goes first: a shorter value must not leave the tail of a longer one behind.
    this.remove(key);
    for (const [part, chunk] of parts.entries()) {
      const password = part === 0 ? `rdc-b64.${parts.length}.${chunk}` : chunk;
      const line = securityLine([
        'add-generic-password',
        '-a',
        key,
        '-s',
        keychainService(part),
        '-U',
        '-w',
        password,
      ]);
      try {
        // One command per process: `security -i` exits with the result of its last command.
        execFileSync('security', ['-i'], fed(line));
      } catch (error) {
        throw toolFailure('security', error);
      }
    }
  }

  remove(key: string): void {
    // The head, then the parts in order until one is absent. A legacy entry and a short value have none.
    for (let part = 0; ; part++) {
      try {
        execFileSync(
          'security',
          ['delete-generic-password', '-a', key, '-s', keychainService(part)],
          QUIET
        );
      } catch {
        if (part > 0) return;
      }
    }
  }
}

// ─── Windows: DPAPI ─────────────────────────────────────────────────────
//
// Windows PowerShell 5.1 (`powershell.exe`, part of every supported Windows) runs one fixed script. PowerShell 7 (`pwsh`) is never called, so whether it is installed does not matter.
//
// - `Add-Type -AssemblyName System.Security` comes first: on .NET Framework `ProtectedData` lives in System.Security.dll, which Windows PowerShell does not load on its own. Without it every call ended in `TypeNotFound`, so no secret was ever stored on Windows and there is no earlier file format to read.
// - The script text is a constant. Plaintext and ciphertext reach it on stdin, through `$input`, as base64; the result leaves on stdout as base64 behind a marker. Only ASCII crosses either pipe, so no console code page, BOM or line ending can change a byte, and no value can become script text.
// - `$ErrorActionPreference='Stop'` turns any failure into a non-zero exit. The marker makes the answer unmistakable either way: output without it is a failure, whatever the exit code.
// - `-Command` runs a string, which no execution policy governs (a policy governs script files), so none is passed.

const DPAPI_MARKER = 'rdc-dpapi:';
const DPAPI_ANSWER = /^rdc-dpapi:([A-Za-z0-9+/]*={0,2})$/;

function dpapiScript(method: 'Protect' | 'Unprotect'): string {
  return [
    "$ErrorActionPreference='Stop'",
    'Add-Type -AssemblyName System.Security',
    "$data=[Convert]::FromBase64String((@($input) -join ''))",
    `$result=[Security.Cryptography.ProtectedData]::${method}($data,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)`,
    `[Console]::Out.Write('${DPAPI_MARKER}'+[Convert]::ToBase64String($result))`,
  ].join(';');
}

/** Runs the script over `bytes` and returns the bytes it answered with. */
function dpapi(method: 'Protect' | 'Unprotect', bytes: Buffer): Buffer {
  let printed: string;
  try {
    printed = execFileSync(
      'powershell.exe',
      ['-NonInteractive', '-NoProfile', '-Command', dpapiScript(method)],
      fed(bytes.toString('base64'))
    );
  } catch (error) {
    throw toolFailure('powershell', error);
  }
  const answer = DPAPI_ANSWER.exec(printed.trim());
  if (!answer) throw new ToolFailure('powershell', false, undefined);
  return Buffer.from(answer[1], 'base64');
}

class DpapiStorage extends Backend {
  readonly type = 'dpapi';
  private readonly keysDir: string;

  constructor() {
    super();
    const { state } = getRediaccDirs();
    this.keysDir = join(state, 'keys');
    mkdirSync(this.keysDir, { recursive: true });
  }

  /**
   * One file per key, named by the SHA-256 of the key. Two keys never share a file, whatever they hold: the earlier name replaced `:` with `_`, so `a:b` and `a_b` were one file.
   * A spelled-out key cannot be the name. NTFS folds case, so `A` and `a` would be one file, and an escape that tells them apart grows a 200-character key past what a Windows path holds. The file records its key instead, and a read checks it.
   */
  private keyPath(key: string): string {
    return join(this.keysDir, `${createHash('sha256').update(key, 'utf-8').digest('hex')}.dpapi`);
  }

  read(key: string): string | null {
    const path = this.keyPath(key);
    if (!existsSync(path)) return null;
    try {
      const stored = JSON.parse(readFileSync(path, 'utf-8')) as { key?: unknown; blob?: unknown };
      if (stored.key !== key || typeof stored.blob !== 'string') return null;
      return dpapi('Unprotect', Buffer.from(stored.blob, 'base64')).toString('utf-8');
    } catch {
      return null;
    }
  }

  write(key: string, value: string): void {
    const blob = dpapi('Protect', Buffer.from(value, 'utf-8')).toString('base64');
    writeFileSync(this.keyPath(key), JSON.stringify({ key, blob }), { mode: 0o600 });
  }

  remove(key: string): void {
    const path = this.keyPath(key);
    if (existsSync(path)) {
      unlinkSync(path);
    }
  }
}

// ─── Opt-in: File (0o600) ───────────────────────────────────────────────

class FileStorage extends Backend {
  readonly type = 'file';
  readonly storePath: string;

  constructor() {
    super();
    const { state } = getRediaccDirs();
    this.storePath = join(state, 'secure-keys.json');
  }

  private load(): Record<string, string> {
    if (!existsSync(this.storePath)) return {};
    try {
      return JSON.parse(readFileSync(this.storePath, 'utf-8'));
    } catch {
      return {};
    }
  }

  private save(data: Record<string, string>): void {
    mkdirSync(join(this.storePath, '..'), { recursive: true });
    writeFileSync(this.storePath, JSON.stringify(data, null, 2), { mode: 0o600 });
    // `mode` applies only when the write creates the file; a file that already existed keeps whatever it had.
    chmodSync(this.storePath, 0o600);
  }

  read(key: string): string | null {
    return this.load()[key] ?? null;
  }

  write(key: string, value: string): void {
    const data = this.load();
    data[key] = value;
    this.save(data);
  }

  remove(key: string): void {
    const data = this.load();
    delete data[key];
    this.save(data);
  }
}

// ─── Validating wrapper (single choke-point) ────────────────────────────

/**
 * Wraps any backend and rejects unsafe keys BEFORE they reach a native tool.
 * Every path that touches secure storage goes through `getSecureStorage()`, so
 * validating here guarantees no untrusted `storageKeyId` reaches keyctl,
 * security, or PowerShell, regardless of which backend is active.
 */
class ValidatingStorage implements SecureStorage {
  constructor(private readonly inner: SecureStorage) {}

  get type(): string {
    return this.inner.type;
  }

  get(key: string): Promise<string | null> {
    assertSafeStorageKey(key);
    return this.inner.get(key);
  }

  set(key: string, value: string): Promise<void> {
    assertSafeStorageKey(key);
    return this.inner.set(key, value);
  }

  delete(key: string): Promise<void> {
    assertSafeStorageKey(key);
    return this.inner.delete(key);
  }
}

// ─── Selection ──────────────────────────────────────────────────────────

/** The one value of the one knob, `REDIACC_SECRET_STORE` (docs/environment-variables.md). Unset selects the native backend of the OS; `file` selects the file backend. */
const FILE_STORE = 'file';

/** The native backend of an OS and the two refusals it can raise. */
interface NativeStore {
  backend: Backend;
  /** The tool could not be started. */
  missing: () => string;
  /** The tool ran and a key did not come back. */
  unusable: () => string;
}

function nativeStoreFor(platform: NodeJS.Platform): NativeStore | undefined {
  switch (platform) {
    case 'linux':
      return {
        backend: new KeyctlStorage(),
        missing: () => t('commands.config.remote.secretStore.keyctlMissing'),
        unusable: () => t('commands.config.remote.secretStore.keyringUnusable'),
      };
    case 'darwin':
      return {
        backend: new KeychainStorage(),
        missing: () => t('commands.config.remote.secretStore.toolMissing', NATIVE_NAMES.darwin),
        unusable: () => t('commands.config.remote.secretStore.storeUnusable', NATIVE_NAMES.darwin),
      };
    case 'win32':
      return {
        backend: new DpapiStorage(),
        missing: () => t('commands.config.remote.secretStore.toolMissing', NATIVE_NAMES.win32),
        unusable: () => t('commands.config.remote.secretStore.storeUnusable', NATIVE_NAMES.win32),
      };
    default:
      return undefined;
  }
}

/** Proper names, the same in every language. */
const NATIVE_NAMES = {
  darwin: { tool: 'security', store: 'Keychain' },
  win32: { tool: 'powershell', store: 'DPAPI' },
} as const;

/**
 * Store, read back and remove a throwaway key through the backend's own operations: the calls a real secret takes, so a pass means a secret stored now can be read later. Returns null on a pass, else whether the tool was missing and its own error line.
 *
 * This replaces `keyctl show @u`, which answered "the command runs and a keyring is visible". A session keyring that does not link the user keyring (a systemd service, a container, a CI job) passes that and then refuses the read: the secret was stored, read back as null, and lost without a word.
 *
 * The CLI does NOT run `keyctl link @u @s` to cure that itself. The link lands in the session keyring the caller's whole session shares and outlives the CLI, and it hands every process of that session possession of every key in `@u`; a service manager that gave a unit a private session keyring chose that isolation. The refusal names the command, and running it stays the operator's decision.
 */
function proveRoundTrip(backend: Backend): { missing: boolean; detail?: string } | null {
  const key = `rdc:probe:${process.pid}-${randomBytes(6).toString('hex')}`;
  const value = randomBytes(24).toString('base64');
  try {
    backend.write(key, value);
    return backend.read(key) === value ? null : { missing: false };
  } catch (error) {
    if (error instanceof ToolFailure) return { missing: error.missing, detail: error.detail };
    throw error;
  } finally {
    try {
      backend.remove(key);
    } catch {
      // Nothing of the throwaway key is left to remove.
    }
  }
}

/** The native backend once it passed its proof in this process. A failed proof is not remembered: the next call proves again. */
let provenNative: Backend | undefined;
let fileNoticeShown = false;

function fileBackend(): Backend {
  const storage = new FileStorage();
  if (!fileNoticeShown) {
    fileNoticeShown = true;
    // stderr and the envelope's `warnings`, never stdout.
    outputService.warn(
      t('commands.config.remote.secretStore.fileNotice', { path: storage.storePath })
    );
  }
  return storage;
}

function selectBackend(): Backend {
  const choice = process.env.REDIACC_SECRET_STORE ?? '';
  if (choice === FILE_STORE) return fileBackend();
  if (choice !== '') {
    const message = t('commands.config.remote.secretStore.invalidChoice', { value: choice });
    // The message is the guidance: the exit code's generic line points at --help, which knows nothing of a variable.
    throw new CliExitError(ERROR_CODES.VALIDATION_ERROR, message, { guidance: message });
  }
  if (provenNative) return provenNative;

  const native = nativeStoreFor(process.platform);
  if (!native) {
    throw new SecureStorageUnavailableError(
      t('commands.config.remote.secretStore.unsupportedPlatform', { platform: process.platform })
    );
  }
  const failure = proveRoundTrip(native.backend);
  if (failure) {
    throw new SecureStorageUnavailableError(
      failure.missing ? native.missing() : native.unusable(),
      failure.detail
    );
  }
  provenNative = native.backend;
  return provenNative;
}

/**
 * The secure storage of this device: the native backend of the OS, proven by a round trip, or the file backend when `REDIACC_SECRET_STORE=file` chose it. Throws SecureStorageUnavailableError when the native backend cannot be used and the file backend was not chosen; nothing falls back on its own.
 * The returned storage validates every key (see ValidatingStorage).
 */
export function getSecureStorage(): SecureStorage {
  return new ValidatingStorage(selectBackend());
}
