import React from 'react';
import { Form, Input } from 'antd';
import type { Rule } from 'antd/es/form';

export interface PasswordConfirmFieldProps {
  /** Field name for this confirmation field */
  name: string;
  /** Field label */
  label: string;
  /** Name of the password field to match against */
  passwordFieldName: string;
  /** Placeholder text */
  placeholder?: string;
  /** Whether field is required (default: true) */
  required?: boolean;
  /** Custom required message */
  requiredMessage?: string;
  /** Custom mismatch message */
  mismatchMessage?: string;
  /** Autocomplete attribute (default: 'new-password') */
  autoComplete?: string;
  /** data-testid attribute */
  'data-testid'?: string;
}

/**
 * Reusable password confirmation field component with match validation.
 *
 * @example
 * <PasswordField
 *   name="password"
 *   label="New Password"
 * />
 * <PasswordConfirmField
 *   name="confirmPassword"
 *   label="Confirm Password"
 *   passwordFieldName="password"
 *   mismatchMessage="Passwords do not match"
 * />
 */
export const PasswordConfirmField: React.FC<PasswordConfirmFieldProps> = ({
  name,
  label,
  passwordFieldName,
  placeholder,
  required = true,
  requiredMessage,
  mismatchMessage = 'Passwords do not match',
  autoComplete = 'new-password',
  'data-testid': dataTestId,
}) => {
  const rules: Rule[] = [];

  if (required) {
    rules.push({
      required: true,
      message: requiredMessage ?? `Please confirm ${label.toLowerCase()}`,
    });
  }

  rules.push(({ getFieldValue }) => ({
    validator(_, value) {
      if (!value || getFieldValue(passwordFieldName) === value) {
        return Promise.resolve();
      }
      throw new Error(mismatchMessage);
    },
  }));

  return (
    <Form.Item name={name} label={label} dependencies={[passwordFieldName]} rules={rules}>
      <Input.Password
        placeholder={placeholder}
        autoComplete={autoComplete}
        data-testid={dataTestId}
      />
    </Form.Item>
  );
};
