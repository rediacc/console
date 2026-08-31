import { Turnstile } from '@marsidev/react-turnstile';
import React, { useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { captchaMessage, useCaptchaGuard } from '../hooks/useCaptchaGuard';
import { useTranslation } from '../i18n/react';

const INTEREST_TO_SUBJECT: Record<string, string> = {
  'disaster-recovery': 'disasterRecovery',
  partnership: 'partnership',
  'threat-response': 'technical',
  technical: 'technical',
  general: 'general',
};

const SUBJECTS = ['general', 'technical', 'partnership', 'disasterRecovery', 'other'] as const;

const DEFAULT_SUBJECT = SUBJECTS[0];
const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

type FormState = 'idle' | 'loading' | 'success' | 'error';

interface Props {
  interest?: string;
}

const ContactForm: React.FC<Props> = ({ interest }) => {
  const initialSubject = INTEREST_TO_SUBJECT[interest ?? ''] ?? DEFAULT_SUBJECT;
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedSubject, setSelectedSubject] = useState(initialSubject);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const hasFiredStart = useRef(false);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const honeypotRef = useRef<HTMLInputElement>(null);
  // Shared state machine; see useCaptchaGuard for the widget-never-mounted case.
  const captcha = useCaptchaGuard();

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');
    // BEFORE the captcha guard, deliberately: an empty form sails straight past
    // that one, POSTs an empty payload, and renders "Something went wrong" from
    // the network-error branch -- which reads as a broken site rather than as a
    // form the visitor has not filled in.
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
      const honeypotValue = honeypotRef.current?.value;
      const res = await fetch(`${window.location.origin}/account/api/v1/contact/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          email,
          subject: selectedSubject,
          message,
          source: 'contact-page',
          lang: currentLang,
          company_url: honeypotValue === '' ? undefined : honeypotValue,
          turnstileToken: captcha.token ?? undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? t('contactModal.error'));
      }

      setState('success');
      captcha.reset();
      const utm =
        (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ??
        {};
      const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
      window.plausible?.('contact_submit', {
        props: {
          subject: selectedSubject,
          source: 'contact-page',
          ...utm,
          ...(lastSolution && { last_solution: lastSolution }),
        },
      });
    } catch (err) {
      setState('error');
      setErrorMsg(err instanceof Error ? err.message : t('contactModal.error'));
    }
  };

  if (state === 'success') {
    return (
      <div className="form-outcome">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          className="icon form-outcome-mark"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12l3 3 5-5" />
        </svg>
        <p>{t('contactModal.success')}</p>
      </div>
    );
  }

  return (
    <form
      className="form"
      onSubmit={handleSubmit}
      noValidate
      onFocus={() => {
        if (!hasFiredStart.current) {
          hasFiredStart.current = true;
          window.plausible?.('contact_form_start', { props: { source: 'contact-page' } });
        }
      }}
    >
      <h2 className="form-title">{t('contactModal.title')}</h2>

      {/* Honeypot */}
      <div className="honeypot" aria-hidden="true">
        <input type="text" name="company_url" ref={honeypotRef} tabIndex={-1} autoComplete="off" />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="page-contact-name">
          {t('contactModal.fields.name')}
        </label>
        <input
          className="form-input"
          id="page-contact-name"
          ref={nameRef}
          type="text"
          placeholder={t('contactModal.fields.namePlaceholder')}
          required
          maxLength={200}
          disabled={state === 'loading'}
        />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="page-contact-email">
          {t('contactModal.fields.email')}
        </label>
        <input
          className="form-input"
          id="page-contact-email"
          ref={emailRef}
          type="email"
          placeholder={t('contactModal.fields.emailPlaceholder')}
          required
          disabled={state === 'loading'}
        />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="page-contact-subject">
          {t('contactModal.fields.subject')}
        </label>
        <select
          className="form-select"
          id="page-contact-subject"
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
        <label className="form-label" htmlFor="page-contact-message">
          {t('contactModal.fields.message')}
        </label>
        <textarea
          className="form-textarea"
          id="page-contact-message"
          ref={messageRef}
          placeholder={t('contactModal.fields.messagePlaceholder')}
          required
          minLength={10}
          maxLength={5000}
          rows={6}
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
  );
};

export default ContactForm;
