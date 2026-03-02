import React, { useState, useRef } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';

const INTEREST_TO_SUBJECT: Record<string, string> = {
  'disaster-recovery': 'disasterRecovery',
  'partnership': 'partnership',
  'threat-response': 'technical',
  'technical': 'technical',
  'general': 'general',
};

const SUBJECTS = ['general', 'technical', 'partnership', 'disasterRecovery', 'other'] as const;

type FormState = 'idle' | 'loading' | 'success' | 'error';

interface Props {
  interest?: string;
}

const ContactForm: React.FC<Props> = ({ interest }) => {
  const initialSubject = (interest && INTEREST_TO_SUBJECT[interest]) || 'general';
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');

    try {
      const res = await fetch(
        `${window.location.origin}/account/api/v1/contact/submit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: nameRef.current?.value.trim(),
            email: emailRef.current?.value.trim(),
            subject: selectedSubject,
            message: messageRef.current?.value.trim(),
            source: 'contact-page',
            lang: currentLang,
            company_url: honeypotRef.current?.value || undefined,
          }),
        }
      );

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error || t('contactModal.error'));
      }

      setState('success');
      const utm = (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ?? {};
      const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
      window.plausible?.('contact_submit', {
        props: { subject: selectedSubject, source: 'contact-page', ...utm, ...(lastSolution && { last_solution: lastSolution }) },
      });
    } catch (err) {
      setState('error');
      setErrorMsg(err instanceof Error ? err.message : t('contactModal.error'));
    }
  };

  if (state === 'success') {
    return (
      <div className="contact-inline-success">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--color-success)' }}>
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12l3 3 5-5" />
        </svg>
        <p>{t('contactModal.success')}</p>
      </div>
    );
  }

  return (
    <form className="contact-inline-form" onSubmit={handleSubmit} noValidate onFocus={() => {
      if (!hasFiredStart.current) {
        hasFiredStart.current = true;
        window.plausible?.('contact_form_start', { props: { source: 'contact-page' } });
      }
    }}>
      <h2 className="contact-inline-title">{t('contactModal.title')}</h2>

      {/* Honeypot */}
      <div style={{ position: 'absolute', left: '-9999px' }} aria-hidden="true">
        <input type="text" name="company_url" ref={honeypotRef} tabIndex={-1} autoComplete="off" />
      </div>

      <div className="contact-inline-field">
        <label htmlFor="page-contact-name">{t('contactModal.fields.name')}</label>
        <input
          id="page-contact-name"
          ref={nameRef}
          type="text"
          placeholder={t('contactModal.fields.namePlaceholder')}
          required
          maxLength={200}
          disabled={state === 'loading'}
        />
      </div>

      <div className="contact-inline-field">
        <label htmlFor="page-contact-email">{t('contactModal.fields.email')}</label>
        <input
          id="page-contact-email"
          ref={emailRef}
          type="email"
          placeholder={t('contactModal.fields.emailPlaceholder')}
          required
          disabled={state === 'loading'}
        />
      </div>

      <div className="contact-inline-field">
        <label htmlFor="page-contact-subject">{t('contactModal.fields.subject')}</label>
        <select
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

      <div className="contact-inline-field">
        <label htmlFor="page-contact-message">{t('contactModal.fields.message')}</label>
        <textarea
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
        <p className="contact-inline-error" role="alert">{errorMsg}</p>
      )}

      <button type="submit" className="contact-inline-submit" disabled={state === 'loading'}>
        {state === 'loading' ? t('contactModal.sending') : t('contactModal.submit')}
      </button>
    </form>
  );
};

export default ContactForm;
