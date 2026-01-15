import type { MasterPasswordProvider } from '@rediacc/shared/api';
import { masterPasswordService } from '@/services/auth/masterPasswordService';

/**
 * Web master password provider wrapping the masterPasswordService.
 * Provides secure in-memory master password storage.
 */
export const masterPasswordAdapter: MasterPasswordProvider = {
  getMasterPassword: () => masterPasswordService.getMasterPassword(),
};
