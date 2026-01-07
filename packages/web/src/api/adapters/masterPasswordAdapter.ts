import { masterPasswordService } from '@/services/auth/masterPasswordService';
import type { MasterPasswordProvider } from '@rediacc/shared/api';

/**
 * Web master password provider wrapping the masterPasswordService.
 * Provides secure in-memory master password storage.
 */
export const masterPasswordAdapter: MasterPasswordProvider = {
  getMasterPassword: () => masterPasswordService.getMasterPassword(),
};
