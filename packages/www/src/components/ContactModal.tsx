import React, { useState, useEffect, useRef, useCallback } from 'react';
import TurnstileWidget from './TurnstileWidget';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';

declare global {
  interface Window {
    openContactModal?: (interest?: string) => void;
  }
}

type FormState = 'idle' | 'loading' | 'success' | 'error';

const INTEREST_TO_SUBJECT: Record<string, string> = {
  'disaster-recovery': 'disasterRecovery',
  partnership: 'partnership',
  'threat-response': 'technical',
  technical: 'technical',
  general: 'general',
};

const SUBJECTS = ['general', 'technical', 'partnership', 'disasterRecovery', 'other'] as const;
const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

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

const ContactModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('general');
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const modalRef = useRef<HTMLDivElement>(null);
  const firstFocusRef = useRef<HTMLInputElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const honeypotRef = useRef<HTMLInputElement>(null);
  const hasFiredStart = useRef(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  const open = useCallback((interest?: string) => {
    if (interest && INTEREST_TO_SUBJECT[interest]) {
      setSelectedSubject(INTEREST_TO_SUBJECT[interest]);
    }
    previousFocusRef.current = document.activeElement as HTMLElement;
    setIsOpen(true);
    setState('idle');
    setErrorMsg('');
    hasFiredStart.current = false;
    window.plausible('contact_modal_open', { props: { source: interest ? 'cta' : 'nav' } });
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    previousFocusRef.current?.focus();
  }, []);

  // Expose global function
  useEffect(() => {
    window.openContactModal = open;
    return () => {
      delete window.openContactModal;
    };
  }, [open]);

  // Focus trap + Escape + body scroll lock
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

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');
    if (captchaEnabled && !turnstileToken) {
      setState('error');
      setErrorMsg(t('captchaRequired') || 'Please complete captcha verification.');
      return;
    }

    try {
      const res = await fetch(`${window.location.origin}/account/api/v1/contact/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: nameRef.current?.value.trim(),
          email: emailRef.current?.value.trim(),
          subject: selectedSubject,
          message: messageRef.current?.value.trim(),
          source: 'contact-modal',
          lang: currentLang,
          company_url: honeypotRef.current?.value === '' ? undefined : honeypotRef.current?.value,
          turnstileToken: turnstileToken ?? undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? t('contactModal.error'));
      }

      setState('success');
      setTurnstileToken(null);
      const utm =
        (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ??
        {};
      const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
      window.plausible('contact_submit', {
        props: {
          subject: selectedSubject,
          source: 'contact-modal',
          ...utm,
          ...(lastSolution && { last_solution: lastSolution }),
        },
      });
    } catch (err) {
      setState('error');
      setErrorMsg(err instanceof Error ? err.message : t('contactModal.error'));
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="contact-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={t('contactModal.title')}
    >
      <div className="contact-modal-content" ref={modalRef}>
        <div className="contact-modal-header">
          <div>
            <h2 className="contact-modal-title">{t('contactModal.title')}</h2>
            <p className="contact-modal-description">{t('contactModal.description')}</p>
          </div>
          <button
            type="button"
            className="contact-modal-close"
            onClick={close}
            aria-label={t('contactModal.close')}
            data-track="cta_click"
            data-track-label="contact-close"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M5 5l10 10M15 5L5 15" />
            </svg>
          </button>
        </div>

        {state === 'success' ? (
          <div className="contact-modal-success">
            <svg
              className="contact-modal-check"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M8 12l3 3 5-5" />
            </svg>
            <p>{t('contactModal.success')}</p>
            <button
              type="button"
              className="contact-modal-done-btn"
              onClick={close}
              data-track="cta_click"
              data-track-label="contact-done"
            >
              {t('contactModal.close')}
            </button>
          </div>
        ) : (
          <form
            className="contact-modal-form"
            onSubmit={handleSubmit}
            noValidate
            onFocus={() => {
              if (!hasFiredStart.current) {
                hasFiredStart.current = true;
                window.plausible('contact_form_start', { props: { source: 'contact-modal' } });
              }
            }}
          >
            {/* Honeypot */}
            <div className="contact-honeypot" aria-hidden="true">
              <input
                type="text"
                name="company_url"
                ref={honeypotRef}
                tabIndex={-1}
                autoComplete="off"
              />
            </div>

            <div className="contact-modal-field">
              <label htmlFor="contact-name">{t('contactModal.fields.name')}</label>
              <input
                id="contact-name"
                ref={(el) => {
                  nameRef.current = el;
                  firstFocusRef.current = el;
                }}
                type="text"
                placeholder={t('contactModal.fields.namePlaceholder')}
                required
                maxLength={200}
                disabled={state === 'loading'}
              />
            </div>

            <div className="contact-modal-field">
              <label htmlFor="contact-email">{t('contactModal.fields.email')}</label>
              <input
                id="contact-email"
                ref={emailRef}
                type="email"
                placeholder={t('contactModal.fields.emailPlaceholder')}
                required
                disabled={state === 'loading'}
              />
            </div>

            <div className="contact-modal-field">
              <label htmlFor="contact-subject">{t('contactModal.fields.subject')}</label>
              <select
                id="contact-subject"
                value={selectedSubject}
                onChange={(e) => setSelectedSubject(e.target.value)}
                disabled={state === 'loading'}
              >
                {SUBJECTS.map((s) => (
                  <option key={s} value={s}>
                    {t(`contactModal.subjects.${s}`)}
                  </option>
                ))}
              </select>
            </div>

            <div className="contact-modal-field">
              <label htmlFor="contact-message">{t('contactModal.fields.message')}</label>
              <textarea
                id="contact-message"
                ref={messageRef}
                placeholder={t('contactModal.fields.messagePlaceholder')}
                required
                minLength={10}
                maxLength={5000}
                rows={4}
                disabled={state === 'loading'}
              />
            </div>

            {state === 'error' && (
              <p className="contact-modal-error" role="alert">
                {errorMsg}
              </p>
            )}

            {captchaEnabled && (
              <TurnstileWidget
                siteKey={turnstileSiteKey}
                action="contact_submit"
                onVerify={setTurnstileToken}
                onExpire={() => setTurnstileToken(null)}
              />
            )}

            <button type="submit" className="contact-modal-submit" disabled={state === 'loading'}>
              {state === 'loading' ? t('contactModal.sending') : t('contactModal.submit')}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default ContactModal;
