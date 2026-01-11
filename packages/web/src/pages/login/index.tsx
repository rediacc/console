import React from 'react';
import { Alert, Button, Flex, Space, Typography } from 'antd';
import InsecureConnectionWarning from '@/components/common/InsecureConnectionWarning';
import SandboxWarning from '@/components/common/SandboxWarning';
import EndpointSelector from '@/features/auth/components/EndpointSelector';
import RegistrationModal from '@/features/auth/components/RegistrationModal';
import { VaultProtocolState } from '@/utils/vaultProtocol';
import { LoginForm } from './components/LoginForm';
import { TFAModal } from './components/TFAModal';
import { useLoginPageController } from './hooks/useLoginPageController';
import { LoginPanel } from './styled';

const LoginPage: React.FC = () => {
  const controller = useLoginPageController();

  return (
    <>
      <SandboxWarning />
      <LoginPanel>
        <Flex vertical>
          {controller.error && (
            <Alert
              type="error"
              message={controller.error}
              closable
              onClose={controller.clearError}
              data-testid="login-error-alert"
            />
          )}

          {!controller.isConnectionSecure && !controller.insecureWarningDismissed && (
            <InsecureConnectionWarning onClose={controller.dismissInsecureWarning} />
          )}

          <LoginForm
            form={controller.form}
            onSubmit={controller.handleLogin}
            loading={controller.loading}
            error={controller.error}
            isConnectionSecure={controller.isConnectionSecure}
            vaultProtocolState={controller.vaultProtocolState}
            showAdvancedOptions={controller.showAdvancedOptions}
            t={controller.t}
          />

          <Space direction="vertical" size="middle">
            <Flex justify="center">
              <Typography.Text>
                {controller.t('auth:login.noAccount')}{' '}
                <a
                  onClick={controller.openRegistration}
                  tabIndex={0}
                  role="button"
                  aria-label={controller.t('auth:login.register')}
                  data-testid="login-register-link"
                >
                  {controller.t('auth:login.register')}
                </a>
              </Typography.Text>
            </Flex>

            <Flex vertical align="center">
              {!controller.showAdvancedOptions &&
              controller.vaultProtocolState !== VaultProtocolState.PASSWORD_REQUIRED &&
              controller.vaultProtocolState !== VaultProtocolState.INVALID_PASSWORD && (
                  <Button
                    type="text"
                    size="small"
                    onClick={controller.enableAdvancedOptions}
                    data-testid="login-advanced-options-toggle"
                  >
                    {controller.t('auth:login.advancedOptions')} →
                  </Button>
                )}

              {controller.showAdvancedOptions && (
                <Space direction="vertical" size="small" align="center">
                  <EndpointSelector />
                </Space>
              )}
            </Flex>
          </Space>
        </Flex>
      </LoginPanel>

      <TFAModal
        open={controller.showTFAModal}
        twoFACode={controller.twoFACode}
        setTwoFACode={controller.setTwoFACode}
        onVerify={controller.handleTFAVerification}
        onCancel={controller.handleTFACancel}
        isVerifying={controller.isVerifyingTFA}
        twoFAForm={controller.twoFAForm}
        t={controller.t}
      />

      <RegistrationModal
        open={controller.showRegistration}
        onCancel={controller.closeRegistration}
        autoFillData={controller.quickRegistrationData}
        autoSubmit={controller.isQuickRegistration}
        onRegistrationComplete={controller.handleRegistrationComplete}
      />
    </>
  );
};

export default LoginPage;
