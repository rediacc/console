import React, { useState, useRef } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
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
  const inputRef = useRef<HTMLInputElement>(null);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const email = inputRef.current?.value.trim();
    if (!email) return;

    setState('loading');
    setErrorMsg('');
    if (openOnSuccessUrl) {
      window.open(openOnSuccessUrl, '_blank', 'noopener,noreferrer');
    }

    try {
      const res = await fetch(`${window.location.origin}/account/api/v1/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, source, lang: currentLang }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? t('newsletter.errorGeneric'));
      }

      setState('success');
      onSuccess?.();
      const utm =
        (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ??
        {};
      window.plausible('newsletter_signup', { props: { source, variant, ...utm } });
    } catch (err) {
      setState('error');
      setErrorMsg(err instanceof Error ? err.message : t('newsletter.errorGeneric'));
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
      {(variant === 'inline' || variant === 'page' || variant === 'modal') && (
        <div className="newsletter-header">
          <h3 className="newsletter-heading">{heading}</h3>
          <p className="newsletter-description">{desc}</p>
        </div>
      )}

      {variant === 'footer' && (
        <div className="newsletter-header">
          <h4 className="footer-heading">{t('newsletter.title')}</h4>
          <p className="newsletter-footer-desc">{t('newsletter.description')}</p>
        </div>
      )}

      <form className="newsletter-form" onSubmit={handleSubmit} noValidate>
        <div className="newsletter-input-group">
          <input
            ref={inputRef}
            type="email"
            className="newsletter-input"
            placeholder={t('newsletter.placeholder')}
            required
            aria-label={t('newsletter.placeholder')}
            disabled={state === 'loading'}
          />
          <button type="submit" className="newsletter-button" disabled={state === 'loading'}>
            {state === 'loading' ? (
              <span className="newsletter-spinner" aria-hidden="true" />
            ) : (
              (ctaLabel ?? t('newsletter.subscribe'))
            )}
          </button>
        </div>
        {state === 'error' && (
          <p className="newsletter-error" role="alert">
            {errorMsg}
          </p>
        )}
      </form>
    </div>
  );
};

export default NewsletterSignup;
