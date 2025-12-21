import React, { useState } from 'react';
import { Alert, Button, Checkbox, Flex, Form, Input, Modal, Steps, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import apiClient, { api } from '@/api/client';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { LanguageLink } from '@/pages/login/components/LanguageLink';
import { Turnstile } from '@/pages/login/components/Turnstile';
import { apiConnectionService } from '@/services/apiConnectionService';
import { hashPassword } from '@/utils/auth';
import { showMessage } from '@/utils/messages';
import {
  BankOutlined,
  CheckCircleOutlined,
  LockOutlined,
  MailOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';

const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || '';
const isCaptchaEnabled = !!turnstileSiteKey;

interface RegistrationModalProps {
  open: boolean;
  onCancel: () => void;
  autoFillData?: {
    email: string;
    password: string;
    companyName: string;
    activationCode?: string;
  };
  autoSubmit?: boolean;
  onRegistrationComplete?: (credentials: { email: string; password: string }) => void;
}

interface RegistrationForm {
  email: string;
  password: string;
  passwordConfirm: string;
  companyName: string;
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
  // Default to true (CI mode) - this is safer as it allows form submission
  // If CI mode is actually disabled, the check will set it to false
  // Server-side validation will enforce captcha requirements regardless
  const [ciMode, setCiMode] = useState<boolean>(true);

  const [registrationData, setRegistrationData] = useState<{
    email: string;
    companyName: string;
    passwordHash: string;
    password?: string; // Store password for auto-login
  } | null>(null);

  const [registrationForm] = Form.useForm<RegistrationForm>();
  const [verificationForm] = Form.useForm<VerificationForm>();

  // Combined loading state for backward compatibility
  const loading = isRegistering || isVerifying;
  // Combined error state
  const error = registrationError || verificationError;

  // Check if CI mode is enabled (for testing/e2e)
  React.useEffect(() => {
    const checkCiMode = async () => {
      try {
        const isCI = await apiConnectionService.isCiMode();
        setCiMode(isCI);
      } catch (error) {
        console.error('Failed to check CI mode:', error);
        setCiMode(false); // Default to false on error
      }
    };
    checkCiMode();
  }, []);

  // Auto-fill and auto-submit logic
  React.useEffect(() => {
    if (open && autoFillData && autoSubmit) {
      // Auto-fill registration form
      registrationForm.setFieldsValue({
        email: autoFillData.email,
        password: autoFillData.password,
        passwordConfirm: autoFillData.password,
        companyName: autoFillData.companyName,
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
    // Check Turnstile token only if captcha is enabled and not in CI mode
    if (isCaptchaEnabled && !ciMode && !turnstileToken) {
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

        // Call CreateNewCompany with headers and captcha token
        await api.company.registerCompany(
          values.companyName,
          values.email,
          passwordHash,
          turnstileToken ?? undefined,
          i18n.language || 'en'
        );

        return {
          email: values.email,
          companyName: values.companyName,
          passwordHash: passwordHash,
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
          throw new Error(response.errors?.join('; ') || 'Activation failed');
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
      if (onRegistrationComplete && registrationData?.password) {
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
        name="companyName"
        label={t('auth:registration.companyName')}
        rules={[
          { required: true, message: t('common:messages.required') },
          { min: 3, message: t('auth:registration.companyNameMin') },
        ]}
      >
        <Input
          prefix={<BankOutlined />}
          placeholder={t('auth:registration.companyNamePlaceholder')}
          data-testid="registration-company-input"
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
      <Flex align="flex-start" wrap gap={16}>
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
          style={{ marginBottom: 0 }}
        >
          <Checkbox>
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

        {/* Cloudflare Turnstile - only render if enabled and not in CI mode */}
        {isCaptchaEnabled && !ciMode && (
          <Flex style={{ flex: '0 0 auto' }}>
            <Turnstile
              sitekey={turnstileSiteKey}
              onVerify={onTurnstileSuccess}
              onExpire={onTurnstileExpire}
              onError={onTurnstileError}
            />
          </Flex>
        )}
      </Flex>

      <Form.Item style={{ marginBottom: 0 }}>
        <Button
          type="primary"
          htmlType="submit"
          block
          loading={loading}
          disabled={isCaptchaEnabled && !ciMode && !turnstileToken}
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
      <Flex vertical gap={16} style={{ width: '100%' }}>
        <Alert
          message={t('auth:registration.verificationRequired')}
          description={t('auth:registration.verificationDescription')}
          type="info"
          showIcon
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
            style={{ fontSize: 16, letterSpacing: '0.5em', textAlign: 'center' }}
            placeholder={t('auth:registration.activationCodePlaceholder')}
            autoComplete="off"
            maxLength={6}
            data-testid="registration-activation-code-input"
          />
        </Form.Item>

        <Form.Item style={{ marginBottom: 0 }}>
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
    <Flex vertical style={{ textAlign: 'center' }} data-testid="registration-success-container">
      <Flex
        style={{ display: 'inline-flex', fontSize: 40 }}
        data-testid="registration-success-icon"
      >
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
      destroyOnClose
      data-testid="registration-modal"
    >
      <Flex vertical gap={16} style={{ width: '100%' }}>
        <Steps
          current={currentStep}
          size="small"
          data-testid="registration-steps"
          items={[
            { title: t('auth:registration.steps.register'), icon: <UserOutlined /> },
            { title: t('auth:registration.steps.verify'), icon: <SafetyCertificateOutlined /> },
            { title: t('auth:registration.steps.complete'), icon: <CheckCircleOutlined /> },
          ]}
        />

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
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
