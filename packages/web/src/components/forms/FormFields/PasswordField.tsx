import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from 'react-i18next';
import { KeyOutlined } from '@/utils/optimizedIcons';
import type { Rule } from 'antd/es/form';

export interface PasswordFieldProps {
  /** Field name in the form */
  name: string;
  /** Field label */
  label: string;
  /** Placeholder text */
  placeholder?: string;
  /** Minimum password length (default: 8) */
  minLength?: number;
  /** Whether field is required (default: true) */
  required?: boolean;
  /** Custom required message */
  requiredMessage?: string;
  /** Custom min length message */
  minLengthMessage?: string;
  /** Custom pattern message */
  patternMessage?: string;
  /** Show key icon prefix (default: false) */
  showIcon?: boolean;
  /** Autocomplete attribute (default: 'new-password') */
  autoComplete?: string;
  /** data-testid attribute */
  'data-testid'?: string;
  /** Additional validation rules */
  additionalRules?: Rule[];
}

/**
 * Reusable password field component with common validation rules.
 *
 * @example
 * // Basic usage
 * <PasswordField
 *   name="password"
 *   label="Password"
 *   placeholder="Enter password"
 * />
 *
 * @example
 * // With custom min length (12 chars for master password)
 * <PasswordField
 *   name="masterPassword"
 *   label="Master Password"
 *   minLength={12}
 *   showIcon
 * />
 */
export const PasswordField: React.FC<PasswordFieldProps> = ({
  name,
  label,
  placeholder,
  minLength = 8,
  required = true,
  requiredMessage,
  minLengthMessage,
  patternMessage,
  showIcon = false,
  autoComplete = 'new-password',
  'data-testid': dataTestId,
  additionalRules = [],
}) => {
  const { t } = useTranslation();
  const rules: Rule[] = [];

  if (required) {
    rules.push({
      required: true,
      message: requiredMessage ?? `Please enter ${label.toLowerCase()}`,
    });
  }

  rules.push({
    min: minLength,
    message: minLengthMessage ?? `Password must be at least ${minLength} characters`,
  });

  rules.push({
    pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d])/,
    message: patternMessage ?? t('common:errors.passwordValidation'),
  });

  if (additionalRules.length > 0) {
    rules.push(...additionalRules);
  }

  return (
    <Form.Item name={name} label={label} rules={rules}>
      <Input.Password
        prefix={showIcon ? <KeyOutlined /> : undefined}
        placeholder={placeholder}
        autoComplete={autoComplete}
        data-testid={dataTestId}
      />
    </Form.Item>
  );
};
