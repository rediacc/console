import { nodeCryptoProvider } from '../adapters/crypto.js';
import { t } from '../i18n/index.js';
import { EXIT_CODES } from '../types/index.js';
import { AuthError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';
import { configService } from './config-resources.js';

let cachedMasterPassword: string | null = null;

/**
 * Resolve the master password used for encrypted local configs.
 * Order: process cache → REDIACC_MASTER_PASSWORD env → interactive prompt
 * verified against the stored `credentials.masterPasswordVerifier`.
 */
export async function requireMasterPassword(): Promise<string> {
  if (cachedMasterPassword) {
    return cachedMasterPassword;
  }

  const envPassword = process.env.REDIACC_MASTER_PASSWORD;
  if (envPassword) {
    cachedMasterPassword = envPassword;
    return envPassword;
  }

  const encrypted = await configService.getMasterPassword();

  if (encrypted) {
    if (!process.stdin.isTTY) {
      throw new AuthError(
        'Master password required but running in non-interactive mode. Set REDIACC_MASTER_PASSWORD environment variable.',
        EXIT_CODES.AUTH_REQUIRED
      );
    }

    const password = await askPassword(t('prompts.masterPassword'));

    try {
      const decrypted = await nodeCryptoProvider.decrypt(encrypted, password);
      cachedMasterPassword = decrypted;
      return decrypted;
    } catch {
      throw new AuthError('Invalid master password', EXIT_CODES.AUTH_REQUIRED);
    }
  }

  throw new AuthError('No master password configured for this config.', EXIT_CODES.AUTH_REQUIRED);
}
