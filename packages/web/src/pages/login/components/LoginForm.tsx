import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Button, Flex, Form, Input, Tooltip, Typography } from 'antd';
import type { FormInstance } from 'antd/es/form';
import React from 'react';
import type { LoginFormValues } from '@/features/auth/types';
import {
  InfoCircleOutlined,
  KeyOutlined,
  LockOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import { VaultProtocolState } from '@/utils/vaultProtocol';

interface LoginFormProps {
  form: FormInstance<LoginFormValues>;
  onSubmit: (values: LoginFormValues) => void;
  loading: boolean;
  error: string | null;
  isConnectionSecure: boolean;
  vaultProtocolState: VaultProtocolState | null;
  showAdvancedOptions: boolean;
  t: TypedTFunction;
}

export const LoginForm: React.FC<LoginFormProps> = ({
  form,
  onSubmit,
  loading,
  error,
  isConnectionSecure,
  vaultProtocolState,
  showAdvancedOptions,
  t,
}) => {
  const showMasterPasswordField =
    vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
    vaultProtocolState === VaultProtocolState.INVALID_PASSWORD ||
    showAdvancedOptions;

  return (
    <Form form={form} name="login" onFinish={onSubmit} layout="vertical" requiredMark={false}>
      <Form.Item
        name="email"
        label={
          <label htmlFor="login-email-input" className="block">
            {t('auth:login.email')}
          </label>
        }
        rules={[
          { required: true, message: t('common:messages.required') },
          { type: 'email', message: t('common:messages.invalidEmail') },
        ]}
        validateStatus={error ? 'error' : undefined}
      >
        <Input
          id="login-email-input"
          prefix={<UserOutlined />}
          placeholder={t('auth:login.emailPlaceholder')}
          autoComplete="email"
          data-testid="login-email-input"
          aria-label={t('auth:login.email')}
          aria-describedby="email-error"
        />
      </Form.Item>

      <Form.Item
        name="password"
        label={
          <label htmlFor="login-password-input" className="block">
            {t('auth:login.password')}
          </label>
        }
        rules={[{ required: true, message: t('common:messages.required') }]}
        validateStatus={error ? 'error' : undefined}
      >
        <Input.Password
          id="login-password-input"
          prefix={<LockOutlined />}
          placeholder={t('auth:login.passwordPlaceholder')}
          autoComplete="current-password"
          data-testid="login-password-input"
          aria-label={t('auth:login.password')}
          aria-describedby="password-error"
        />
      </Form.Item>

      {showMasterPasswordField && (
        <Flex vertical>
          <Form.Item
            name="masterPassword"
            label={
              <label htmlFor="login-master-password-input">
                <Flex align="center" className="flex">
                  <Typography.Text>{t('auth:login.masterPassword')}</Typography.Text>
                  <Tooltip title={t('auth:login.masterPasswordTooltip')}>
                    <InfoCircleOutlined />
                  </Tooltip>
                </Flex>
              </label>
            }
            validateStatus={
              vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED ||
              vaultProtocolState === VaultProtocolState.INVALID_PASSWORD
                ? 'error'
                : undefined
            }
            required={vaultProtocolState === VaultProtocolState.PASSWORD_REQUIRED}
          >
            <Input.Password
              id="login-master-password-input"
              prefix={<KeyOutlined />}
              placeholder={t('auth:login.masterPasswordPlaceholder')}
              autoComplete="off"
              data-testid="login-master-password-input"
              aria-label={t('auth:login.masterPassword')}
              aria-describedby="master-password-error"
            />
          </Form.Item>
        </Flex>
      )}

      <Form.Item>
        <Tooltip
          title={isConnectionSecure ? undefined : t('auth:login.insecureConnection.buttonDisabled')}
        >
          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loading}
            disabled={!isConnectionSecure}
            data-testid="login-submit-button"
          >
            {loading ? t('auth:login.signingIn') : t('auth:login.signIn')}
          </Button>
        </Tooltip>
      </Form.Item>
    </Form>
  );
};
