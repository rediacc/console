import {
  validateSize,
  validateNetworkId,
  validateSSHPrivateKey,
} from '@rediacc/shared/queue-vault';
import type { Rule } from 'antd/es/form';

export { isValidGuid } from '@rediacc/shared/validation';

// Used by UsersPage
export interface CreateUserFormValues {
  newUserEmail: string;
  newUserPassword: string;
}

// Validation rules
export const validationRules = {
  required: (fieldLabel: string): Rule => ({
    required: true,
    message: `${fieldLabel} is required`,
  }),

  resourceName: (resourceType: string): Rule[] => [
    { required: true, message: `${resourceType} name is required` },
    { max: 100, message: `${resourceType} name must be less than 100 characters` },
  ],

  /** Validates size format (e.g., "20G", "500M", "1T") using shared renet-compatible validation */
  sizeFormat: (): Rule => ({
    validator: (_, value: string | undefined) => {
      if (!value?.trim()) return Promise.resolve();
      const result = validateSize(value);
      if (!result.valid) {
        return Promise.reject(new Error(result.error));
      }
      return Promise.resolve();
    },
  }),

  /** Validates network ID format (>= 2816 and follows 2816 + n*64 pattern) */
  networkId: (): Rule => ({
    validator: (_, value: number | string | undefined) => {
      if (value === undefined || value === '') return Promise.resolve();
      const numValue = typeof value === 'string' ? Number.parseInt(value, 10) : value;
      if (Number.isNaN(numValue)) {
        return Promise.reject(new Error('Network ID must be a number'));
      }
      const result = validateNetworkId(numValue);
      if (!result.valid) {
        return Promise.reject(new Error(result.error));
      }
      return Promise.resolve();
    },
  }),

  /** Validates SSH private key format (PEM format) */
  sshPrivateKey: (): Rule => ({
    validator: (_, value: string | undefined) => {
      if (!value?.trim()) return Promise.resolve();
      const result = validateSSHPrivateKey(value);
      if (!result.valid) {
        return Promise.reject(new Error(result.error));
      }
      return Promise.resolve();
    },
  }),

  uuid: (): Rule => ({
    pattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    message: 'Invalid GUID format',
  }),
};

// Simple required validator for machine/size fields
export const conditionalRequired = (errorMessage: string): Rule => ({
  validator: (_, value: string | undefined) => {
    if (!value?.trim()) return Promise.reject(new Error(errorMessage));
    return Promise.resolve();
  },
});
