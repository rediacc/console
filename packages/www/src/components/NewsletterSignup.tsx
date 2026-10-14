import React, { useRef, useState } from 'react';
import { captchaMessage, useCaptchaGuard } from '../hooks/useCaptchaGuard';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import CaptchaField from './CaptchaField';
import '../styles/newsletter.css';

type Variant = 'inline' | 'footer' | 'sticky-bar' | 'page' | 'modal';

interface Props {
  variant: Variant;
  source: string;
  title?: string;
  description?: string;
  onSuccess?: () => void;
  ctaLabel?: string;
  openOnSuccessUrl?: string;
}

type FormState = 'idle' | 'loading' | 'success' | 'error';
const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** POST the subscription; throws the server's error text, or `fallbackError` when it sent none. */
async function postSubscribe(
  payload: { email: string; source: string; lang: string; turnstileToken: string | null },
  fallbackError: string
): Promise<void> {
  const res = await fetch(`${window.location.origin}/account/api/v1/newsletter/subscribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, turnstileToken: payload.turnstileToken ?? undefined }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.error ?? fallbackError);
  }
}

function trackSignup(source: string, variant: Variant): void {
  const utm = window.__pa_get_utm?.() ?? {};
  window.plausible?.('newsletter_signup', { props: { source, variant, ...utm } });
}

const NewsletterHeader: React.FC<{
  variant: Variant;
  heading: string;
  desc: string;
  t: (key: string) => string;
}> = ({ variant, heading, desc, t }) => {
  if (variant === 'footer') {
    return (
      <div className="newsletter-header">
        <h4 className="footer-heading">{t('newsletter.title')}</h4>
        <p className="newsletter-footer-desc">{t('newsletter.description')}</p>
      </div>
    );
  }
  return (
    <div className="newsletter-header">
      <h3 className="newsletter-heading">{heading}</h3>
      <p className="newsletter-description">{desc}</p>
    </div>
  );
};

const NewsletterSignup: React.FC<Props> = ({
  variant,
  source,
  title,
  description,
  onSuccess,
  ctaLabel,
  openOnSuccessUrl,
}) => {
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  // Shared state machine; see useCaptchaGuard for the widget-never-mounted case.
  const captcha = useCaptchaGuard();
  const inputRef = useRef<HTMLInputElement>(null);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const email = inputRef.current?.value.trim();
    // A BARE `return` HERE MADE THE BUTTON DEAD. The form sets noValidate, so the browser does not enforce `required`; an empty submit read the input, found nothing, and returned without a message, a focus move or a state change. Nothing told the visitor why, on the site's main email capture.
    if (!email) {
      setState('error');
      setErrorMsg(t('newsletter.errorRequiredEmail'));
      return;
    }

    setState('loading');
    setErrorMsg('');
    if (captchaEnabled && !captcha.token) {
      setState('error');
      setErrorMsg(captchaMessage(captcha, t('captchaUnavailable'), t('captchaRequired')));
      return;
    }
    if (openOnSuccessUrl) {
      window.open(openOnSuccessUrl, '_blank', 'noopener,noreferrer');
    }

    try {
      await postSubscribe(
        { email, source, lang: currentLang, turnstileToken: captcha.token },
        t('newsletter.errorGeneric')
      );

      setState('success');
      captcha.reset();
      onSuccess?.();
      trackSignup(source, variant);
    } catch (err) {
      setState('error');
      setErrorMsg(errorText(err, t('newsletter.errorGeneric')));
    }
  };

  if (state === 'success') {
    return (
      <div className={`newsletter-signup newsletter-${variant} newsletter-success`}>
        <div className="newsletter-success-content">
          <svg
            className="newsletter-check-icon"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
          <p>{t('newsletter.successMessage')}</p>
        </div>
      </div>
    );
  }

  const heading = title ?? (variant === 'page' ? t('newsletter.pageTitle') : t('newsletter.title'));
  const desc =
    description ??
    (variant === 'page' ? t('newsletter.pageDescription') : t('newsletter.description'));

  return (
    <div className={`newsletter-signup newsletter-${variant}`}>
      {variant !== 'sticky-bar' && (
        <NewsletterHeader variant={variant} heading={heading} desc={desc} t={t} />
      )}

      <form className="newsletter-form" onSubmit={handleSubmit} noValidate>
        <div className="newsletter-input-group">
          <input
            ref={inputRef}
            type="email"
            className="form-input newsletter-input"
            placeholder={t('newsletter.placeholder')}
            required
            aria-label={t('newsletter.placeholder')}
            disabled={state === 'loading'}
          />
          <button
            type="submit"
            className="btn btn--primary btn--sm newsletter-button"
            disabled={state === 'loading'}
          >
            {state === 'loading' ? (
              <span className="newsletter-spinner" aria-hidden="true" />
            ) : (
              (ctaLabel ?? t('newsletter.subscribe'))
            )}
          </button>
        </div>
        {state === 'error' && (
          <p className="form-error" role="alert">
            {errorMsg}
          </p>
        )}
        <CaptchaField
          captcha={captcha}
          enabled={captchaEnabled}
          siteKey={turnstileSiteKey}
          options={{ action: 'newsletter_subscribe' }}
          unavailableText={t('captchaUnavailable')}
          retryText={t('captchaRetry')}
        />
      </form>
    </div>
  );
};

export default NewsletterSignup;
