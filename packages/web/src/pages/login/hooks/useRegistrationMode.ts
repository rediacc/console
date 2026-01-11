import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiConnectionService } from '@/services/api';
import {
  generateRandomEmail,
  generateRandomOrganizationName,
  generateRandomPassword,
} from '@/utils/generators';
import { showMessage } from '@/utils/messages';

export const useRegistrationMode = (params: {
  openRegistration: () => void;
  enableQuickRegistration: (data: {
    email: string;
    password: string;
    organizationName: string;
    activationCode: string;
  }) => void;
}) => {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const checkRegistrationMode = async () => {
      const registerParam = searchParams.get('register');

      if (registerParam === 'quick') {
        try {
          const ciMode = await apiConnectionService.isCiMode();
          if (ciMode) {
            params.enableQuickRegistration({
              email: generateRandomEmail(),
              password: generateRandomPassword(),
              organizationName: generateRandomOrganizationName(),
              activationCode: '111111',
            });
            params.openRegistration();
          } else {
            console.warn('Quick registration is only available in CI/TEST mode');
            showMessage('warning', 'Quick registration is only available in CI/TEST mode');
            params.openRegistration();
          }
        } catch (caughtError) {
          console.error('Could not check CI mode, falling back to normal registration', caughtError);
          params.openRegistration();
        }
      } else if (registerParam === 'manual') {
        params.openRegistration();
      }

      if (registerParam) {
        searchParams.delete('register');
        const newUrl = searchParams.toString()
          ? `${window.location.pathname}?${searchParams.toString()}`
          : window.location.pathname;
        window.history.replaceState({}, '', newUrl);
      }
    };

    void checkRegistrationMode();
  }, [params, searchParams]);
};
