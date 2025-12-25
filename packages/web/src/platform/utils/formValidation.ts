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

  sizeFormat: (): Rule => ({
    validator: (_, value: string | undefined) => {
      if (!value?.trim()) return Promise.resolve();
      const match = value.match(/^(\d+)([GT])$/);
      if (!match || parseInt(match[1], 10) <= 0) {
        return Promise.reject(new Error('Invalid size format (e.g., 10G, 100G, 1T)'));
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
