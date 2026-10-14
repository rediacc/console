import { Turnstile } from '@marsidev/react-turnstile';
import React from 'react';
import type { CaptchaGuard } from '../hooks/useCaptchaGuard';

interface CaptchaFieldProps {
  captcha: CaptchaGuard;
  /** False when no site key is configured or CI mode is on: nothing renders. */
  enabled: boolean;
  siteKey: string;
  options: React.ComponentProps<typeof Turnstile>['options'];
  unavailableText: string;
  retryText: string;
}

/** The Turnstile widget plus its "widget never loaded" notice with a retry button. */
const CaptchaField: React.FC<CaptchaFieldProps> = ({
  captcha,
  enabled,
  siteKey,
  options,
  unavailableText,
  retryText,
}) => {
  if (!enabled) return null;
  return (
    <>
      <Turnstile
        key={captcha.nonce}
        siteKey={siteKey}
        options={options}
        onSuccess={captcha.onSuccess}
        onExpire={captcha.onExpire}
        onError={captcha.onError}
      />
      {captcha.failed && (
        <p className="form-error" role="status">
          {unavailableText}{' '}
          <button
            type="button"
            className="form-inline-action"
            onClick={captcha.retry}
            data-track="captcha_retry"
          >
            {retryText}
          </button>
        </p>
      )}
    </>
  );
};

export default CaptchaField;
