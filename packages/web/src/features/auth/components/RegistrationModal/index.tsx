import React, { useState } from 'react';
import { Alert, Button, Checkbox, Flex, Form, Input, Modal, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import apiClient from '@/api/client';
import { LanguageLink } from '@/features/auth/components/LanguageLink';
import { Turnstile } from '@/features/auth/components/Turnstile';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { apiConnectionService } from '@/services/api';
import { hashPassword } from '@/utils/auth';
import { showMessage } from '@/utils/messages';
import {
  BankOutlined,
  CheckCircleOutlined,
  LockOutlined,
  MailOutlined,
} from '@/utils/optimizedIcons';

const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY ?? '';
const isCaptchaEnabled = !!turnstileSiteKey;

interface RegistrationModalProps {
  open: boolean;
  onCancel: () => void;
  autoFillData?: {
    email: string;
    password: string;
    organizationName: string;
    activationCode?: string;
  };
  autoSubmit?: boolean;
  onRegistrationComplete?: (credentials: { email: string; password: string }) => void;
}

interface RegistrationForm {
  email: string;
  password: string;
  passwordConfirm: string;
  organizationName: string;
  termsAccepted?: boolean;
}

interface VerificationForm {
  activationCode: string;
}

const RegistrationModal: React.FC<RegistrationModalProps> = ({
  open,
  onCancel,
  autoFillData,
  autoSubmit = false,
  onRegistrationComplete,
}) => {
  const { t, i18n } = useTranslation(['auth', 'common']);
  const [currentStep, setCurrentStep] = useState(0);
  const {
    execute: executeRegistration,
    isExecuting: isRegistering,
    error: registrationError,
    resetError: resetRegistrationError,
  } = useAsyncAction();
  const {
    execute: executeVerification,
    isExecuting: isVerifying,
    error: verificationError,
    resetError: resetVerificationError,
  } = useAsyncAction();
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  // Default to true (test mode) - this is safer as it allows form submission
  // If test mode is actually disabled, the check will set it to false
  // Server-side validation will enforce captcha requirements regardless
  const [testMode, setTestMode] = useState<boolean>(true);

  const [registrationData, setRegistrationData] = useState<{
    email: string;
    organizationName: string;
    passwordHash: string;
    password?: string; // Store password for auto-login
  } | null>(null);

  const [registrationForm] = Form.useForm<RegistrationForm>();
  const [verificationForm] = Form.useForm<VerificationForm>();

  // Combined loading state for backward compatibility
  const loading = isRegistering || isVerifying;
  // Combined error state
  const error = registrationError ?? verificationError;

  // Check if test mode is enabled (for testing/e2e)
  React.useEffect(() => {
    const checkTestMode = async () => {
      try {
        const isTest = await apiConnectionService.isTestMode();
        setTestMode(isTest);
      } catch (error) {
        console.error('Failed to check test mode:', error);
        setTestMode(false); // Default to false on error
      }
    };
    void checkTestMode();
  }, []);

  // Auto-fill and auto-submit logic
  React.useEffect(() => {
    if (open && autoFillData && autoSubmit) {
      // Auto-fill registration form
      registrationForm.setFieldsValue({
        email: autoFillData.email,
        password: autoFillData.password,
        passwordConfirm: autoFillData.password,
        organizationName: autoFillData.organizationName,
      });

      // Auto-submit registration form after a short delay
      setTimeout(() => {
        registrationForm.submit();
      }, 500);
    }
  }, [open, autoFillData, autoSubmit, registrationForm]);

  // Auto-fill and auto-submit verification code
  React.useEffect(() => {
    if (currentStep === 1 && autoFillData?.activationCode && autoSubmit) {
      verificationForm.setFieldsValue({
        activationCode: autoFillData.activationCode,
      });

      // Auto-submit verification form after a short delay
      setTimeout(() => {
        verificationForm.submit();
      }, 500);
    }
  }, [currentStep, autoFillData, autoSubmit, verificationForm]);

  const handleRegistration = async (values: RegistrationForm) => {
    // Check Turnstile token only if captcha is enabled and not in test mode
    if (isCaptchaEnabled && !testMode && !turnstileToken) {
      showMessage('error', t('auth:registration.captchaRequired', 'Please complete the captcha'));
      return;
    }

    // Check terms acceptance
    if (!values.termsAccepted) {
      showMessage(
        'error',
        t('auth:registration.termsRequired', 'You must accept the terms and conditions')
      );
      return;
    }

    const result = await executeRegistration(
      async () => {
        // Hash the password
        const passwordHash = await hashPassword(values.password);

        // Call register with proper auth headers
        await apiClient.register(values.organizationName, values.email, passwordHash, {
          languagePreference: i18n.language || 'en',
          turnstileToken: turnstileToken ?? undefined,
        });

        return {
          email: values.email,
          organizationName: values.organizationName,
          passwordHash,
          password: values.password, // Store for auto-login if needed
        };
      },
      {
        successMessage: t('auth:registration.registrationSuccess'),
        errorMessage: t('auth:registration.registrationFailed'),
        onError: () => {
          // Reset Turnstile token on error (widget will auto-reset)
          setTurnstileToken(null);
        },
      }
    );

    if (result.success && result.data) {
      // Store registration data for verification step
      setRegistrationData(result.data);
      // Move to verification step
      setCurrentStep(1);
    }
  };

  // Turnstile handlers
  const onTurnstileSuccess = (token: string) => {
    setTurnstileToken(token);
    resetRegistrationError(); // Clear error when captcha is completed
  };

  const onTurnstileExpire = () => {
    setTurnstileToken(null);
  };

  const onTurnstileError = (errorCode?: string) => {
    console.error('Turnstile error:', errorCode);
    setTurnstileToken(null);
  };

  const handleVerification = async (values: VerificationForm) => {
    if (!registrationData) return;

    const result = await executeVerification(
      async () => {
        // Use the updated activateUser method with authentication
        const response = await apiClient.activateUser(
          registrationData.email,
          values.activationCode,
          registrationData.passwordHash
        );

        if (response.failure !== 0) {
          throw new Error(response.errors.join('; ') || 'Activation failed');
        }

        return response;
      },
      {
        successMessage: t('auth:registration.activationSuccess'),
        errorMessage: t('auth:registration.activationFailed'),
      }
    );

    if (result.success) {
      // Move to success step
      setCurrentStep(2);

      // Call completion callback if provided (for auto-login)
      if (onRegistrationComplete && registrationData.password) {
        onRegistrationComplete({
          email: registrationData.email,
          password: registrationData.password,
        });
      }

      // Close modal immediately after success
      handleClose();
    }
  };

  const handleClose = () => {
    setCurrentStep(0);
    resetRegistrationError();
    resetVerificationError();
    setRegistrationData(null);
    setTurnstileToken(null);
    registrationForm.resetFields();
    verificationForm.resetFields();

    onCancel();
  };

  const renderRegistrationForm = () => (
    <Form
      form={registrationForm}
      layout="vertical"
      onFinish={handleRegistration}
      requiredMark={false}
      data-testid="registration-form"
    >
      <Form.Item
        name="organizationName"
        label={t('auth:registration.organizationName')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { min: 3, message: t('auth:registration.organizationNameMin') },
        ]}
      >
        <Input
          prefix={<BankOutlined />}
          placeholder={t('auth:registration.organizationNamePlaceholder')}
          data-testid="registration-organization-input"
        />
      </Form.Item>

      <Form.Item
        name="email"
        label={t('auth:registration.email')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { type: 'email', message: t('common:messages.invalidEmail') },
        ]}
      >
        <Input
          prefix={<MailOutlined />}
          placeholder={t('auth:registration.emailPlaceholder')}
          autoComplete="email"
          data-testid="registration-email-input"
        />
      </Form.Item>

      <Form.Item
        name="password"
        label={t('auth:registration.password')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { min: 8, message: t('auth:registration.passwordMin') },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('auth:registration.passwordPlaceholder')}
          autoComplete="new-password"
          data-testid="registration-password-input"
        />
      </Form.Item>

      <Form.Item
        name="passwordConfirm"
        label={t('auth:registration.passwordConfirm')}
        dependencies={['password']}
        rules={[
          { required: true, message: t('common:messages.required') },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('password') === value) {
                return Promise.resolve();
              }
              throw new Error(t('auth:registration.passwordMismatch'));
            },
          }),
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('auth:registration.passwordConfirmPlaceholder')}
          autoComplete="new-password"
          data-testid="registration-password-confirm-input"
        />
      </Form.Item>

      {/* Terms and HCaptcha side by side */}
      <Flex align="flex-start" wrap className="gap-md">
        {/* Terms and Conditions */}
        <Form.Item
          name="termsAccepted"
          valuePropName="checked"
          rules={[
            {
              validator: (_, value) => {
                if (value) {
                  return Promise.resolve();
                }
                throw new Error(
                  t('auth:registration.termsRequired', 'You must accept the terms and conditions')
                );
              },
            },
          ]}
        >
          <Checkbox data-testid="registration-terms-checkbox">
            {
              t(
                'auth:registration.termsText',
                'I accept the terms and conditions {terms} and {privacy}'
              ).split('{terms}')[0]
            }
            <LanguageLink to="/terms" className="underline" target="_blank">
              {t('auth:registration.termsLink', 'Terms of Use')}
            </LanguageLink>
            {
              t(
                'auth:registration.termsText',
                'I accept the terms and conditions {terms} and {privacy}'
              )
                .split('{terms}')[1]
                .split('{privacy}')[0]
            }
            <LanguageLink to="/privacy" className="underline" target="_blank">
              {t('auth:registration.privacyLink', 'Privacy Policy')}
            </LanguageLink>
            {
              t(
                'auth:registration.termsText',
                'I accept the terms and conditions {terms} and {privacy}'
              ).split('{privacy}')[1]
            }
          </Checkbox>
        </Form.Item>

        {/* Cloudflare Turnstile - only render if enabled and not in test mode */}
        {isCaptchaEnabled && !testMode && (
          <Flex className="flex-shrink-0">
            <Turnstile
              sitekey={turnstileSiteKey}
              onVerify={onTurnstileSuccess}
              onExpire={onTurnstileExpire}
              onError={onTurnstileError}
            />
          </Flex>
        )}
      </Flex>

      <Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          block
          loading={loading}
          disabled={isCaptchaEnabled && !testMode && !turnstileToken}
          data-testid="registration-submit-button"
        >
          {t('auth:registration.createAccount')}
        </Button>
      </Form.Item>
    </Form>
  );

  const renderVerificationForm = () => (
    <Form
      form={verificationForm}
      layout="vertical"
      onFinish={handleVerification}
      requiredMark={false}
      data-testid="registration-verification-form"
    >
      <Flex vertical className="w-full">
        <Alert
          message={t('auth:registration.verificationRequired')}
          description={t('auth:registration.verificationDescription')}
          type="info"
          data-testid="registration-verification-alert"
        />

        <Form.Item
          name="activationCode"
          label={t('auth:registration.activationCode')}
          rules={[
            { required: true, message: t('common:messages.required') },
            { len: 6, message: t('auth:registration.activationCodeLength') },
            { pattern: /^\d{6}$/, message: t('auth:registration.activationCodeFormat') },
          ]}
        >
          <Input
            placeholder={t('auth:registration.activationCodePlaceholder')}
            autoComplete="off"
            maxLength={6}
            data-testid="registration-activation-code-input"
          />
        </Form.Item>

        <Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loading}
            data-testid="registration-verify-button"
          >
            {t('auth:registration.verifyAccount')}
          </Button>
        </Form.Item>
      </Flex>
    </Form>
  );

  const renderSuccess = () => (
    <Flex vertical data-testid="registration-success-container">
      <Flex className="inline-flex" data-testid="registration-success-icon">
        <CheckCircleOutlined />
      </Flex>
      <Typography.Title level={4} data-testid="registration-success-title">
        {t('auth:registration.successTitle')}
      </Typography.Title>
      <Typography.Text data-testid="registration-success-description">
        {t('auth:registration.successDescription')}
      </Typography.Text>
    </Flex>
  );

  const renderContent = () => {
    switch (currentStep) {
      case 0:
        return renderRegistrationForm();
      case 1:
        return renderVerificationForm();
      case 2:
        return renderSuccess();
      default:
        return null;
    }
  };

  return (
    <Modal
      title={t('auth:registration.title')}
      open={open}
      onCancel={handleClose}
      footer={null}
      destroyOnHidden
      centered
      data-testid="registration-modal"
    >
      <Flex vertical className="w-full">
        {error && (
          <Alert
            message={error}
            type="error"
            closable
            onClose={() => {
              resetRegistrationError();
              resetVerificationError();
            }}
            data-testid="registration-error-alert"
          />
        )}

        {renderContent()}
      </Flex>
    </Modal>
  );
};

export default RegistrationModal;
