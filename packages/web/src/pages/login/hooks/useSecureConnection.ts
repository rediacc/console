import { useEffect, useState } from 'react';
import { isSecureContext } from '@/utils/secureContext';

export const useSecureConnection = () => {
  const isConnectionSecure = isSecureContext();
  const [insecureWarningDismissed, setInsecureWarningDismissed] = useState(false);

  useEffect(() => {
    if (!isConnectionSecure) {
      console.warn('[LoginPage] Insecure connection detected. Web Crypto API unavailable.');
    }
  }, [isConnectionSecure]);

  return {
    isConnectionSecure,
    insecureWarningDismissed,
    dismissInsecureWarning: () => setInsecureWarningDismissed(true),
  };
};
