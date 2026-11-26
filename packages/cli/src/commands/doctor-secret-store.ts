import {
  getSecureStorage,
  type SecureStorage,
  SecureStorageUnavailableError,
} from '../utils/secure-storage.js';
import type { CheckResult } from './doctor.js';

export interface SecretStoreCheckDeps {
  /** The storage selection; defaults to the generic `getSecureStorage()`, which honours REDIACC_SECRET_STORE. */
  getStorage?: () => SecureStorage;
  /** The platform whose hint is shown; defaults to `process.platform`. */
  platform?: NodeJS.Platform;
}

const FILE_STORE_HINT = 'or set REDIACC_SECRET_STORE=file';

/** The remedy of the platform the check ran on, never another platform's. `detail` is the probe's own error line. */
function secretStoreHint(platform: NodeJS.Platform = process.platform, detail?: string): string {
  switch (platform) {
    case 'win32':
      return `Windows: the DPAPI probe through \`powershell\` failed${detail ? ` (${detail})` : ''}; check that powershell.exe runs for this user, ${FILE_STORE_HINT}`;
    case 'darwin':
      return `macOS: unlock or repair the login Keychain (the \`security\` tool); ${FILE_STORE_HINT}`;
    case 'linux':
      return `Linux: install keyutils (keyctl) and run \`keyctl link @u @s\` if the session keyring is private; ${FILE_STORE_HINT}`;
    default:
      return `Set REDIACC_SECRET_STORE=file`;
  }
}

/** The row for a backend that could not be selected or proven: a timeout is a warning, anything else a failure. */
function secretStoreFailure(name: string, error: unknown, platform: NodeJS.Platform): CheckResult {
  const detail = error instanceof Error ? error.message : String(error);
  const unavailable = error instanceof SecureStorageUnavailableError ? error : undefined;
  if (unavailable?.timedOut) {
    return {
      name,
      value: detail,
      status: 'warn',
      hint: 'The probe timed out, which a loaded machine causes: run the checks again when it is idle',
    };
  }
  return {
    name,
    value: detail,
    status: 'fail',
    hint: secretStoreHint(platform, unavailable?.details?.[0]),
  };
}

/** Store, read back and remove a throwaway key through the active backend: the calls a real secret takes. */
export async function checkSecretStore(deps: SecretStoreCheckDeps = {}): Promise<CheckResult> {
  const platform = deps.platform ?? process.platform;
  const name = 'Secret store';
  const choice = process.env.REDIACC_SECRET_STORE;
  try {
    const storage = (deps.getStorage ?? getSecureStorage)();
    const key = `rdc:doctor:${process.pid}-${Date.now()}`;
    const value = `probe-${Math.random().toString(36).slice(2)}`;
    let leftover: string | undefined;
    try {
      await storage.set(key, value);
      if ((await storage.get(key)) !== value) {
        return {
          name,
          value: `${storage.type}: a stored secret did not read back`,
          status: 'fail',
          hint: secretStoreHint(platform),
        };
      }
    } finally {
      await storage.delete(key).catch((error: unknown) => {
        leftover = error instanceof Error ? error.message : String(error);
      });
    }
    if (leftover !== undefined) {
      return {
        name,
        value: `${storage.type}: the probe secret ${key} could not be removed (${leftover})`,
        status: 'warn',
        hint: 'Remove that entry from the secret store by hand',
      };
    }
    return {
      name,
      value: choice ? `${storage.type} (REDIACC_SECRET_STORE=${choice})` : storage.type,
      status: 'ok',
    };
  } catch (error) {
    return secretStoreFailure(name, error, platform);
  }
}
