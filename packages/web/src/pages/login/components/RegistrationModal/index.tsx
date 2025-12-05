import React, { useState } from 'react';
import { Form, Input, Alert, Checkbox } from 'antd';
import {
  UserOutlined,
  LockOutlined,
  MailOutlined,
  BankOutlined,
  SafetyCertificateOutlined,
  CheckCircleOutlined,
} from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { showMessage } from '@/utils/messages';
import { hashPassword } from '@/utils/auth';
import apiClient, { api } from '@/api/client';
import { apiConnectionService } from '@/services/apiConnectionService';
import { Turnstile } from '@/pages/login/components/Turnstile';
import { LanguageLink } from '@/pages/login/components/LanguageLink';
import {
  StyledModal,
  VerticalStack,
  FormField,
  TermsRow,
  TermsField,
  CaptchaWrapper,
  SubmitButton,
  VerificationButton,
  CodeInput,
  SuccessContainer,
  SuccessIcon,
  SuccessTitle,
  SuccessDescription,
  StepsWrapper,
} from './styles';

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      setError(t('auth:registration.captchaRequired', 'Please complete the captcha'));
      return;
    }

    // Check terms acceptance
    if (!values.termsAccepted) {
      setError(t('auth:registration.termsRequired', 'You must accept the terms and conditions'));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Hash the password
      const passwordHash = await hashPassword(values.password);

      // Call CreateNewCompany with headers and captcha token
      await api.company.registerCompany(
        values.companyName,
        values.email,
        passwordHash,
        turnstileToken || undefined,
        i18n.language || 'en'
      );

      // Store registration data for verification step
      setRegistrationData({
        email: values.email,
        companyName: values.companyName,
        passwordHash: passwordHash,
        password: values.password, // Store for auto-login if needed
      });

      // Move to verification step
      setCurrentStep(1);
      showMessage('success', t('auth:registration.registrationSuccess'));
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : t('auth:registration.registrationFailed');
      setError(errorMessage);
      showMessage('error', errorMessage);

      // Reset Turnstile token on error (widget will auto-reset)
      setTurnstileToken(null);
    } finally {
      setLoading(false);
    }
  };

  // Turnstile handlers
  const onTurnstileSuccess = (token: string) => {
    setTurnstileToken(token);
    setError(null); // Clear error when captcha is completed
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

    setLoading(true);
    setError(null);

    try {
      // Use the updated activateUser method with authentication
      const response = await apiClient.activateUser(
        registrationData.email,
        values.activationCode,
        registrationData.passwordHash
      );

      if (response.failure !== 0) {
        throw new Error(response.errors?.join('; ') || 'Activation failed');
      }

      // Move to success step
      setCurrentStep(2);
      showMessage('success', t('auth:registration.activationSuccess'));

      // Call completion callback if provided (for auto-login)
      if (onRegistrationComplete && registrationData?.password) {
        onRegistrationComplete({
          email: registrationData.email,
          password: registrationData.password,
        });
      }

      // Close modal immediately after success
      handleClose();
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : t('auth:registration.activationFailed');
      setError(errorMessage);
      showMessage('error', errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setCurrentStep(0);
    setError(null);
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
      <FormField
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
          size="large"
          data-testid="registration-company-input"
        />
      </FormField>

      <FormField
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
          size="large"
          autoComplete="email"
          data-testid="registration-email-input"
        />
      </FormField>

      <FormField
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
          size="large"
          autoComplete="new-password"
          data-testid="registration-password-input"
        />
      </FormField>

      <FormField
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
              return Promise.reject(new Error(t('auth:registration.passwordMismatch')));
            },
          }),
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('auth:registration.passwordConfirmPlaceholder')}
          size="large"
          autoComplete="new-password"
          data-testid="registration-password-confirm-input"
        />
      </FormField>

      {/* Terms and HCaptcha side by side */}
      <TermsRow>
        {/* Terms and Conditions */}
        <TermsField
          name="termsAccepted"
          valuePropName="checked"
          rules={[
            {
              validator: (_, value) =>
                value
                  ? Promise.resolve()
                  : Promise.reject(
                      new Error(
                        t(
                          'auth:registration.termsRequired',
                          'You must accept the terms and conditions'
                        )
                      )
                    ),
            },
          ]}
          $noMargin
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
        </TermsField>

        {/* Cloudflare Turnstile - only render if enabled and not in CI mode */}
        {isCaptchaEnabled && !ciMode && (
          <CaptchaWrapper>
            <Turnstile
              sitekey={turnstileSiteKey}
              onVerify={onTurnstileSuccess}
              onExpire={onTurnstileExpire}
              onError={onTurnstileError}
              theme="light"
            />
          </CaptchaWrapper>
        )}
      </TermsRow>

      <FormField $noMargin>
        <SubmitButton
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loading}
          disabled={isCaptchaEnabled && !ciMode && !turnstileToken}
          data-testid="registration-submit-button"
        >
          {t('auth:registration.createAccount')}
        </SubmitButton>
      </FormField>
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
      <VerticalStack orientation="vertical">
        <Alert
          message={t('auth:registration.verificationRequired')}
          description={t('auth:registration.verificationDescription')}
          type="info"
          showIcon
          data-testid="registration-verification-alert"
        />

        <FormField
          name="activationCode"
          label={t('auth:registration.activationCode')}
          rules={[
            { required: true, message: t('common:messages.required') },
            { len: 6, message: t('auth:registration.activationCodeLength') },
            { pattern: /^\d{6}$/, message: t('auth:registration.activationCodeFormat') },
          ]}
        >
          <CodeInput
            size="large"
            placeholder={t('auth:registration.activationCodePlaceholder')}
            autoComplete="off"
            maxLength={6}
            data-testid="registration-activation-code-input"
          />
        </FormField>

        <FormField $noMargin>
          <VerificationButton
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            data-testid="registration-verify-button"
          >
            {t('auth:registration.verifyAccount')}
          </VerificationButton>
        </FormField>
      </VerticalStack>
    </Form>
  );

  const renderSuccess = () => (
    <SuccessContainer data-testid="registration-success-container">
      <SuccessIcon data-testid="registration-success-icon">
        <CheckCircleOutlined />
      </SuccessIcon>
      <SuccessTitle data-testid="registration-success-title">
        {t('auth:registration.successTitle')}
      </SuccessTitle>
      <SuccessDescription type="secondary" data-testid="registration-success-description">
        {t('auth:registration.successDescription')}
      </SuccessDescription>
    </SuccessContainer>
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
    <StyledModal
      title={t('auth:registration.title')}
      open={open}
      onCancel={handleClose}
      footer={null}
      destroyOnHidden
      data-testid="registration-modal"
    >
      <VerticalStack orientation="vertical">
        <StepsWrapper
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
            onClose={() => setError(null)}
            data-testid="registration-error-alert"
          />
        )}

        {renderContent()}
      </VerticalStack>
    </StyledModal>
  );
};

export default RegistrationModal;
