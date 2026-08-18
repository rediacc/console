import { Turnstile } from '@marsidev/react-turnstile';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import Overlay from './Overlay';
import '../styles/lead-magnet-modal.css';

declare global {
  interface Window {
    openLeadMagnetModal?: (opts: LeadMagnetOpenOpts) => void;
  }
}

interface LeadMagnetOpenOpts {
  /** Slug from the account worker registry (e.g. "ransomware-survival-cto"). */
  magnetName: string;
  /** Source tag for analytics / lead-attribution. */
  source: string;
  /** Optional human label shown in the modal heading. Falls back to i18n string. */
  label?: string;
}

type FormState = 'idle' | 'loading' | 'success' | 'error';

const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

const AUTO_CLOSE_MS = 3500;

const LeadMagnetModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [opts, setOpts] = useState<LeadMagnetOpenOpts | null>(null);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const firstFocusRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const autoCloseTimer = useRef<number | null>(null);

  const open = useCallback((nextOpts: LeadMagnetOpenOpts) => {
    setOpts(nextOpts);
    setIsOpen(true);
    setState('idle');
    setErrorMsg('');
    setTurnstileToken(null);
    window.plausible?.('lead_magnet_open', {
      props: { source: nextOpts.source, magnetName: nextOpts.magnetName },
    });
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    setOpts(null);
    if (autoCloseTimer.current != null) {
      window.clearTimeout(autoCloseTimer.current);
      autoCloseTimer.current = null;
    }
  }, []);

  // Expose global function + custom event listener for use from Astro.
  useEffect(() => {
    window.openLeadMagnetModal = open;
    const onCustomEvent = (e: Event) => {
      const detail = (e as CustomEvent<LeadMagnetOpenOpts>).detail;
      if (typeof detail.magnetName === 'string') open(detail);
    };
    window.addEventListener('lead-magnet:open', onCustomEvent);
    return () => {
      delete window.openLeadMagnetModal;
      window.removeEventListener('lead-magnet:open', onCustomEvent);
    };
  }, [open]);

  useEffect(
    () => () => {
      if (autoCloseTimer.current != null) window.clearTimeout(autoCloseTimer.current);
    },
    []
  );

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!opts) return;
    const email = emailRef.current?.value.trim();
    if (!email) return;

    if (captchaEnabled && !turnstileToken) {
      setState('error');
      setErrorMsg(
        t('pages.solutionPages.leadMagnetModal.captchaRequired') ||
          'Please complete captcha verification.'
      );
      return;
    }

    setState('loading');
    setErrorMsg('');

    // Open the tab synchronously inside the click handler so popup blockers
    // honor the user-activation token. We point it to about:blank and rewrite
    // the URL after the API responds. If the API errors we close the tab.
    const pdfWindow = window.open('about:blank', '_blank', 'noopener,noreferrer');

    try {
      const res = await fetch(`${window.location.origin}/account/api/v1/newsletter/lead-magnet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          magnetName: opts.magnetName,
          source: opts.source,
          lang: currentLang,
          turnstileToken: turnstileToken ?? undefined,
        }),
      });
      const body = (await res.json().catch(() => null)) as {
        message?: string;
        pdfUrl?: string;
        error?: string;
      } | null;
      if (!res.ok || !body?.pdfUrl) {
        pdfWindow?.close();
        throw new Error(body?.error ?? t('pages.solutionPages.leadMagnetModal.errorGeneric'));
      }

      // Route the pre-opened tab to the PDF; this keeps the popup-blocker
      // happy because the open() call was inside the user-activation window.
      if (pdfWindow) {
        pdfWindow.location.href = body.pdfUrl;
      } else {
        window.open(body.pdfUrl, '_blank', 'noopener,noreferrer');
      }

      const utm =
        (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ??
        {};
      window.plausible?.('lead_magnet_submit', {
        props: {
          source: opts.source,
          magnetName: opts.magnetName,
          lang: currentLang,
          ...utm,
        },
      });

      setState('success');
      setTurnstileToken(null);
      autoCloseTimer.current = window.setTimeout(close, AUTO_CLOSE_MS);
    } catch (err) {
      pdfWindow?.close();
      setState('error');
      setErrorMsg(
        err instanceof Error ? err.message : t('pages.solutionPages.leadMagnetModal.errorGeneric')
      );
    }
  };

  const heading = opts?.label ?? t('pages.solutionPages.leadMagnetModal.title');

  return (
    <Overlay
      open={isOpen && !!opts}
      onClose={close}
      align="center"
      label={heading}
      title={state === 'success' ? t('pages.solutionPages.leadMagnetModal.successTitle') : heading}
      description={
        state === 'success'
          ? t('pages.solutionPages.leadMagnetModal.successBody')
          : t('pages.solutionPages.leadMagnetModal.description')
      }
      closeLabel={t('pages.solutionPages.leadMagnetModal.closeLabel') || 'Close'}
      closeTrackLabel="lead-magnet-modal-close"
      initialFocusRef={firstFocusRef}
    >
      {state === 'success' ? (
        <div className="form-outcome" role="status">
          <svg
            className="icon form-outcome-mark"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M8 12l3 3 5-5" />
          </svg>
        </div>
      ) : (
        <form className="overlay-body" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label className="form-label" htmlFor="lead-magnet-modal-email">
              {t('pages.solutionPages.leadMagnetModal.emailLabel')}
            </label>
            <input
              ref={(el) => {
                emailRef.current = el;
                firstFocusRef.current = el;
              }}
              id="lead-magnet-modal-email"
              type="email"
              required
              className="form-input"
              placeholder={t('pages.solutionPages.leadMagnetModal.emailPlaceholder')}
              aria-required="true"
              disabled={state === 'loading'}
            />
          </div>
          {captchaEnabled && (
            <Turnstile
              siteKey={turnstileSiteKey}
              options={{ action: 'newsletter_lead_magnet', size: 'flexible' }}
              onSuccess={setTurnstileToken}
              onExpire={() => setTurnstileToken(null)}
              onError={() => setTurnstileToken(null)}
            />
          )}
          {state === 'error' && (
            <p className="form-error" role="alert">
              {errorMsg}
            </p>
          )}
          <button
            type="submit"
            className="btn btn--primary"
            disabled={state === 'loading'}
            data-track="cta_click"
            data-track-label={`lead-magnet-submit-${opts?.magnetName ?? ''}`}
          >
            {state === 'loading'
              ? t('pages.solutionPages.leadMagnetModal.sendingLabel')
              : t('pages.solutionPages.leadMagnetModal.submitLabel')}
          </button>
          <p className="form-disclaimer">{t('pages.solutionPages.leadMagnetModal.disclaimer')}</p>
        </form>
      )}
    </Overlay>
  );
};

export default LeadMagnetModal;
