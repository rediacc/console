import React from 'react';
import { Form, Input } from 'antd';
import type { Rule } from 'antd/es/form';

const CenteredInput = (props: React.ComponentProps<typeof Input>) => (
  <Input
    style={{ textAlign: 'center', letterSpacing: '0.5em', fontFamily: 'monospace' }}
    {...props}
  />
);

export interface OTPCodeFieldProps {
  /** Field name in the form */
  name: string;
  /** Field label */
  label: string;
  /** Placeholder text */
  placeholder?: string;
  /** Whether field is required (default: true) */
  required?: boolean;
  /** Custom required message */
  requiredMessage?: string;
  /** Custom length message */
  lengthMessage?: string;
  /** Custom format message */
  formatMessage?: string;
  /** data-testid attribute */
  'data-testid'?: string;
}

/**
 * Reusable OTP code input field for 6-digit verification codes.
 *
 * @example
 * <OTPCodeField
 *   name="code"
 *   label="Verification Code"
 *   placeholder="000000"
 * />
 */
export const OTPCodeField: React.FC<OTPCodeFieldProps> = ({
  name,
  label,
  placeholder = '000000',
  required = true,
  requiredMessage,
  lengthMessage = 'Code must be 6 digits',
  formatMessage = 'Code must contain only digits',
  'data-testid': dataTestId,
}) => {
  const rules: Rule[] = [];

  if (required) {
    rules.push({
      required: true,
      message: requiredMessage || `Please enter ${label.toLowerCase()}`,
    });
  }

  rules.push({
    len: 6,
    message: lengthMessage,
  });

  rules.push({
    pattern: /^\d{6}$/,
    message: formatMessage,
  });

  return (
    <Form.Item name={name} label={label} rules={rules}>
      <CenteredInput
        placeholder={placeholder}
        maxLength={6}
        autoComplete="off"
        data-testid={dataTestId}
      />
    </Form.Item>
  );
};
