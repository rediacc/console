import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Turnstile } from '@marsidev/react-turnstile';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import '../styles/lead-magnet-modal.css';

declare global {
  interface Window {
    openLeadMagnetModal?: (opts: LeadMagnetOpenOpts) => void;
  }
}

export interface LeadMagnetOpenOpts {
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

function handleFocusTrap(e: KeyboardEvent, modal: HTMLDivElement, close: () => void): void {
  if (e.key === 'Escape') {
    close();
    return;
  }
  if (e.key !== 'Tab') return;
  const focusable = modal.querySelectorAll<HTMLElement>(
    'input, select, textarea, button, [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

const LeadMagnetModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [opts, setOpts] = useState<LeadMagnetOpenOpts | null>(null);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const modalRef = useRef<HTMLDivElement>(null);
  const firstFocusRef = useRef<HTMLInputElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const autoCloseTimer = useRef<number | null>(null);

  const open = useCallback((nextOpts: LeadMagnetOpenOpts) => {
    previousFocusRef.current = document.activeElement as HTMLElement;
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
    previousFocusRef.current?.focus();
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

  // Focus trap + Escape + body scroll lock.
  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(() => firstFocusRef.current?.focus());
    const onKeyDown = (e: KeyboardEvent) => {
      const modal = modalRef.current;
      if (!modal) return;
      handleFocusTrap(e, modal, close);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen, close]);

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
        throw new Error(body?.error ?? t('pages.solutionPages.leadMagnetModal.errorGeneric'));
      }

      // Open the PDF in a new tab immediately.
      window.open(body.pdfUrl, '_blank', 'noopener,noreferrer');

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
      setState('error');
      setErrorMsg(
        err instanceof Error ? err.message : t('pages.solutionPages.leadMagnetModal.errorGeneric')
      );
    }
  };

  if (!isOpen || !opts) return null;

  const titleId = 'lead-magnet-modal-title';
  const heading = opts.label ?? t('pages.solutionPages.leadMagnetModal.title');

  return (
    <div
      className="lead-magnet-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div ref={modalRef} className="lead-magnet-modal">
        <button
          type="button"
          className="lead-magnet-modal__close"
          aria-label={t('pages.solutionPages.leadMagnetModal.closeLabel') || 'Close'}
          onClick={close}
          data-track="cta_click"
          data-track-label="lead-magnet-modal-close"
          data-track-dest="modal-close"
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z" />
          </svg>
        </button>

        {state === 'success' ? (
          <div className="lead-magnet-modal__success" role="status">
            <svg
              className="lead-magnet-modal__check"
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
            <h2 id={titleId} className="lead-magnet-modal__title">
              {t('pages.solutionPages.leadMagnetModal.successTitle')}
            </h2>
            <p className="lead-magnet-modal__description">
              {t('pages.solutionPages.leadMagnetModal.successBody')}
            </p>
          </div>
        ) : (
          <>
            <h2 id={titleId} className="lead-magnet-modal__title">
              {heading}
            </h2>
            <p className="lead-magnet-modal__description">
              {t('pages.solutionPages.leadMagnetModal.description')}
            </p>
            <form className="lead-magnet-modal__form" onSubmit={handleSubmit} noValidate>
              <label className="lead-magnet-modal__label" htmlFor="lead-magnet-modal-email">
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
                className="lead-magnet-modal__input"
                placeholder={t('pages.solutionPages.leadMagnetModal.emailPlaceholder')}
                aria-required="true"
                disabled={state === 'loading'}
              />
              {captchaEnabled && (
                <div className="lead-magnet-modal__turnstile">
                  <Turnstile
                    siteKey={turnstileSiteKey}
                    options={{ action: 'newsletter_lead_magnet', size: 'flexible' }}
                    onSuccess={setTurnstileToken}
                    onExpire={() => setTurnstileToken(null)}
                    onError={() => setTurnstileToken(null)}
                  />
                </div>
              )}
              {state === 'error' && (
                <p className="lead-magnet-modal__error" role="alert">
                  {errorMsg}
                </p>
              )}
              <button
                type="submit"
                className="lead-magnet-modal__submit"
                disabled={state === 'loading'}
                data-track="cta_click"
                data-track-label={`lead-magnet-submit-${opts.magnetName}`}
              >
                {state === 'loading'
                  ? t('pages.solutionPages.leadMagnetModal.sendingLabel')
                  : t('pages.solutionPages.leadMagnetModal.submitLabel')}
              </button>
              <p className="lead-magnet-modal__disclaimer">
                {t('pages.solutionPages.leadMagnetModal.disclaimer')}
              </p>
            </form>
          </>
        )}
      </div>
    </div>
  );
};

export default LeadMagnetModal;
