import { Turnstile } from '@marsidev/react-turnstile';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { captchaMessage, useCaptchaGuard } from '../hooks/useCaptchaGuard';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import Overlay from './Overlay';

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

interface ContactModalProps {
  /** Locale from BaseLayout; authoritative on the server. See the note above. */
  lang?: Language;
}

/**
 * `lang` is passed by BaseLayout and is AUTHORITATIVE on the server.
 *
 * `useLanguage()` reads `window.location.pathname`, and there is no `window` during SSR,
 * so it returns 'en' for every locale. That made this island server-render English on all
 * twelve non-English locales: crawlers and no-JS visitors saw an English nav, and everyone
 * else got a flash of English until hydration corrected it. Astro knows the locale, so it
 * hands it down; the hook stays as the fallback for any mount that does not.
 */
const ContactModal: React.FC<ContactModalProps> = ({ lang }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('general');
  const detectedLang = useLanguage();
  const currentLang = lang ?? detectedLang;
  const { t } = useTranslation(currentLang);

  const firstFocusRef = useRef<HTMLInputElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const honeypotRef = useRef<HTMLInputElement>(null);
  const hasFiredStart = useRef(false);
  // Shared state machine; see useCaptchaGuard for the widget-never-mounted case.
  const captcha = useCaptchaGuard();

  const open = useCallback((interest?: string) => {
    if (interest && INTEREST_TO_SUBJECT[interest]) {
      setSelectedSubject(INTEREST_TO_SUBJECT[interest]);
    }
    setIsOpen(true);
    setState('idle');
    setErrorMsg('');
    hasFiredStart.current = false;
    window.plausible?.('contact_modal_open', { props: { source: interest ? 'cta' : 'nav' } });
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  // Expose global function
  useEffect(() => {
    window.openContactModal = open;
    return () => {
      delete window.openContactModal;
    };
  }, [open]);

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');
    // Same shape as ContactForm, and before the captcha guard for the same
    // reason: an empty form passes that one and POSTs an empty payload, so the
    // visitor is told "Something went wrong" about their own blank fields.
    // BOUND FIRST, then tested -- the shape PartnerApplicationForm.tsx:149 uses.
    // Testing `nameRef.current?.value.trim()` inline reads identically to a
    // human and is invisible to check-form-validation, whose fieldIdentifiers()
    // only recognises a field that is assigned to a variable. It also stops the
    // payload below reading each ref a second time.
    const name = nameRef.current?.value.trim() ?? '';
    const email = emailRef.current?.value.trim() ?? '';
    const message = messageRef.current?.value.trim() ?? '';
    if (!name || !email || !message) {
      setState('error');
      setErrorMsg(t('contactModal.errorRequiredFields'));
      return;
    }
    if (captchaEnabled && !captcha.token) {
      setState('error');
      // The widget is present and unsolved, or it never loaded at all. Only the second
      // one needs a retry, and saying "complete the captcha" there points at nothing.
      setErrorMsg(captchaMessage(captcha, t('captchaUnavailable'), t('captchaRequired')));
      return;
    }

    try {
      const res = await fetch(`${window.location.origin}/account/api/v1/contact/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          email,
          subject: selectedSubject,
          message,
          source: 'contact-modal',
          lang: currentLang,
          company_url: honeypotRef.current?.value === '' ? undefined : honeypotRef.current?.value,
          turnstileToken: captcha.token ?? undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? t('contactModal.error'));
      }

      setState('success');
      captcha.reset();
      const utm = window.__pa_get_utm?.() ?? {};
      const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
      window.plausible?.('contact_submit', {
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

  return (
    <Overlay
      open={isOpen}
      onClose={close}
      label={t('contactModal.title')}
      title={t('contactModal.title')}
      description={t('contactModal.description')}
      closeLabel={t('contactModal.close')}
      closeTrackLabel="contact-close"
      initialFocusRef={firstFocusRef}
    >
      {state === 'success' ? (
        <div className="form-outcome">
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
          <p>{t('contactModal.success')}</p>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={close}
            data-track="cta_click"
            data-track-label="contact-done"
          >
            {t('contactModal.close')}
          </button>
        </div>
      ) : (
        <form
          className="overlay-body"
          onSubmit={handleSubmit}
          noValidate
          onFocus={() => {
            if (!hasFiredStart.current) {
              hasFiredStart.current = true;
              window.plausible?.('contact_form_start', { props: { source: 'contact-modal' } });
            }
          }}
        >
          {/* Honeypot */}
          <div className="honeypot" aria-hidden="true">
            <input
              type="text"
              name="company_url"
              ref={honeypotRef}
              tabIndex={-1}
              autoComplete="off"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="contact-name">
              {t('contactModal.fields.name')}
            </label>
            <input
              className="form-input"
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

          <div className="form-group">
            <label className="form-label" htmlFor="contact-email">
              {t('contactModal.fields.email')}
            </label>
            <input
              className="form-input"
              id="contact-email"
              ref={emailRef}
              type="email"
              placeholder={t('contactModal.fields.emailPlaceholder')}
              required
              disabled={state === 'loading'}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="contact-subject">
              {t('contactModal.fields.subject')}
            </label>
            <select
              className="form-select"
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

          <div className="form-group">
            <label className="form-label" htmlFor="contact-message">
              {t('contactModal.fields.message')}
            </label>
            <textarea
              className="form-textarea"
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
            <p className="form-error" role="alert">
              {errorMsg}
            </p>
          )}

          {captchaEnabled && (
            <Turnstile
              key={captcha.nonce}
              siteKey={turnstileSiteKey}
              options={{ action: 'contact_submit' }}
              onSuccess={captcha.onSuccess}
              onExpire={captcha.onExpire}
              onError={captcha.onError}
            />
          )}
          {captchaEnabled && captcha.failed && (
            <p className="form-error" role="status">
              {t('captchaUnavailable')}{' '}
              <button
                type="button"
                className="form-inline-action"
                onClick={captcha.retry}
                data-track="captcha_retry"
              >
                {t('captchaRetry')}
              </button>
            </p>
          )}

          <button type="submit" className="btn btn--primary" disabled={state === 'loading'}>
            {state === 'loading' ? t('contactModal.sending') : t('contactModal.submit')}
          </button>
        </form>
      )}
    </Overlay>
  );
};

export default ContactModal;
