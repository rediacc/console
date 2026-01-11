import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useTelemetry } from '@/components/common/TelemetryProvider';
import { useLoginForm } from '@/features/auth/hooks/useLoginForm';
import { useTFAVerification } from '@/features/auth/hooks/useTFAVerification';
import type { LoginFormValues } from '@/features/auth/types';
import { useLoginFlow } from './useLoginFlow';
import { usePowerModeShortcut } from './usePowerModeShortcut';
import { useRegistrationMode } from './useRegistrationMode';
import { useSecureConnection } from './useSecureConnection';

export const useLoginPageController = () => {
  const [showRegistration, setShowRegistration] = useState(false);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [quickRegistrationData, setQuickRegistrationData] = useState<
    | {
        email: string;
        password: string;
        organizationName: string;
        activationCode: string;
      }
    | undefined
  >(undefined);
  const [isQuickRegistration, setIsQuickRegistration] = useState(false);

  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { form, twoFAForm } = useLoginForm();
  const { t, i18n } = useTranslation(['auth', 'common']);
  const verifyTFAMutation = useTFAVerification();
  const { trackUserAction } = useTelemetry();

  const secureConnection = useSecureConnection();

  const handleToggleAdvancedOptions = useCallback((newState: boolean) => {
    setShowAdvancedOptions(newState);
  }, []);

  usePowerModeShortcut(handleToggleAdvancedOptions);

  const enableQuickRegistration = useCallback(
    (data: {
      email: string;
      password: string;
      organizationName: string;
      activationCode: string;
    }) => {
      setQuickRegistrationData(data);
      setIsQuickRegistration(true);
    },
    []
  );

  const openRegistration = useCallback(() => {
    setShowRegistration(true);
  }, []);

  useRegistrationMode({
    openRegistration,
    enableQuickRegistration,
  });

  const loginFlow = useLoginFlow({
    form,
    t,
    i18n,
    navigate: (path) => {
      void navigate(path);
    },
    dispatch,
    trackUserAction,
    verifyTFAMutation,
  });

  const closeRegistration = () => {
    setShowRegistration(false);
    setIsQuickRegistration(false);
    setQuickRegistrationData(undefined);
  };

  const handleRegistrationComplete = async (credentials: { email: string; password: string }) => {
    if (isQuickRegistration) {
      setShowRegistration(false);
      await loginFlow.handleLogin({ email: credentials.email, password: credentials.password } as LoginFormValues);
    }
  };

  return {
    t,
    form,
    twoFAForm,
    loading: loginFlow.loading,
    error: loginFlow.error,
    clearError: loginFlow.clearError,
    isConnectionSecure: secureConnection.isConnectionSecure,
    insecureWarningDismissed: secureConnection.insecureWarningDismissed,
    dismissInsecureWarning: secureConnection.dismissInsecureWarning,
    vaultProtocolState: loginFlow.vaultProtocolState,
    showAdvancedOptions,
    enableAdvancedOptions: () => setShowAdvancedOptions(true),
    showTFAModal: loginFlow.showTFAModal,
    twoFACode: loginFlow.twoFACode,
    setTwoFACode: loginFlow.setTwoFACode,
    handleTFAVerification: loginFlow.handleTFAVerification,
    handleTFACancel: loginFlow.handleTFACancel,
    isVerifyingTFA: loginFlow.isVerifyingTFA,
    showRegistration,
    openRegistration,
    closeRegistration,
    quickRegistrationData,
    isQuickRegistration,
    handleRegistrationComplete,
    handleLogin: loginFlow.handleLogin,
  };
};
