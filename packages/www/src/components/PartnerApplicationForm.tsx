import { Turnstile, type TurnstileInstance } from '@marsidev/react-turnstile';
import React, { useRef, useState } from 'react';
import { captchaMessage, useCaptchaGuard } from '../hooks/useCaptchaGuard';
import { useLanguage } from '../hooks/useLanguage';
// Route-scoped translations: this island hydrates on ONE page, so its strings ride
// this component's chunk instead of the catalog every route downloads.
import { useRouteTranslation } from '../i18n/react-route';

/**
 * Public application form for The Rediacc Partner 1st Program. Mirrors
 * ContactForm mechanics (Turnstile + PUBLIC_CI_MODE branch + a `company_url`
 * honeypot) and POSTs a flat JSON body that matches the backend
 * `partnerApplicationSubmitSchema` field-for-field
 * (private/account/src/types/partner.ts). On success the form is replaced by
 * a confirmation panel.
 */

// Backend enum: private/account/src/types/partner.ts partnerTypeSchema.
const PARTNER_TYPES = ['reseller', 'msp', 'consultant', 'distributor', 'referral'] as const;
type PartnerType = (typeof PARTNER_TYPES)[number];

const HOW_HEARD_OPTIONS = ['search', 'referral', 'event', 'socialMedia', 'blog', 'other'] as const;

// Country names are shown in the site language; the field stores the chosen
// name as a plain string (schema: country, max 128 chars). Kept as a flat list
// so the select has no extra dependency.
const COUNTRIES = [
  'Argentina',
  'Australia',
  'Austria',
  'Belgium',
  'Brazil',
  'Bulgaria',
  'Canada',
  'Chile',
  'China',
  'Colombia',
  'Croatia',
  'Czechia',
  'Denmark',
  'Egypt',
  'Estonia',
  'Finland',
  'France',
  'Germany',
  'Greece',
  'Hungary',
  'Iceland',
  'India',
  'Indonesia',
  'Ireland',
  'Israel',
  'Italy',
  'Japan',
  'Jordan',
  'Kenya',
  'Latvia',
  'Lithuania',
  'Luxembourg',
  'Malaysia',
  'Mexico',
  'Morocco',
  'Netherlands',
  'New Zealand',
  'Nigeria',
  'Norway',
  'Pakistan',
  'Philippines',
  'Poland',
  'Portugal',
  'Qatar',
  'Romania',
  'Saudi Arabia',
  'Serbia',
  'Singapore',
  'Slovakia',
  'Slovenia',
  'South Africa',
  'South Korea',
  'Spain',
  'Sweden',
  'Switzerland',
  'Taiwan',
  'Thailand',
  'Turkey',
  'Ukraine',
  'United Arab Emirates',
  'United Kingdom',
  'United States',
  'Vietnam',
] as const;

/** Trim a value and collapse an empty result to undefined (so optional,
 * unfilled fields are omitted from the request body rather than sent blank). */
const orUndef = (value: string | undefined): string | undefined => {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed;
};

const turnstileSiteKey = import.meta.env.PUBLIC_TURNSTILE_SITE_KEY ?? '';
const ciMode =
  String(import.meta.env.PUBLIC_CI_MODE ?? '').toLowerCase() === 'true' ||
  String(import.meta.env.PUBLIC_CI_MODE ?? '') === '1';
const captchaEnabled = !!turnstileSiteKey && !ciMode;

type FormState = 'idle' | 'loading' | 'success' | 'error';

const NS = 'pages.partners.form';

const PartnerApplicationForm: React.FC = () => {
  const currentLang = useLanguage();
  const { t } = useRouteTranslation(currentLang);

  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [country, setCountry] = useState('');
  const [partnerTypes, setPartnerTypes] = useState<PartnerType[]>([]);
  const [isDistributor, setIsDistributor] = useState(false);
  const [howHeard, setHowHeard] = useState('');
  const [consent, setConsent] = useState(false);
  // Shared state machine; see useCaptchaGuard for the widget-never-mounted case.
  const captcha = useCaptchaGuard();

  const contactNameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const companyRef = useRef<HTMLInputElement>(null);
  const jobTitleRef = useRef<HTMLInputElement>(null);
  const websiteRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const honeypotRef = useRef<HTMLInputElement>(null);
  const turnstileRef = useRef<TurnstileInstance>(undefined);
  const hasFiredStart = useRef(false);

  const togglePartnerType = (value: PartnerType) => {
    setPartnerTypes((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    );
  };

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');

    const contactName = contactNameRef.current?.value.trim() ?? '';
    const email = emailRef.current?.value.trim() ?? '';
    const company = companyRef.current?.value.trim() ?? '';

    if (!contactName || !email || !company || !country || partnerTypes.length === 0) {
      setState('error');
      setErrorMsg(t(`${NS}.errors.requiredFields`));
      return;
    }
    if (!consent) {
      setState('error');
      setErrorMsg(t(`${NS}.errors.consent`));
      return;
    }
    if (captchaEnabled && !captcha.token) {
      setState('error');
      setErrorMsg(
        captchaMessage(captcha, t(`${NS}.errors.captchaUnavailable`), t(`${NS}.errors.captcha`))
      );
      return;
    }

    try {
      const honeypotValue = honeypotRef.current?.value;

      const res = await fetch(`${window.location.origin}/account/api/v1/partner/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contactName,
          email,
          company,
          website: orUndef(websiteRef.current?.value),
          country: orUndef(country),
          message: orUndef(messageRef.current?.value),
          lang: currentLang,
          title: orUndef(jobTitleRef.current?.value),
          phone: orUndef(phoneRef.current?.value),
          partnerTypes: partnerTypes.length > 0 ? partnerTypes : undefined,
          isDistributor,
          howHeard: orUndef(howHeard),
          consent,
          company_url: honeypotValue === '' ? undefined : honeypotValue,
          turnstileToken: captcha.token ?? undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? t(`${NS}.errors.generic`));
      }

      setState('success');
      captcha.reset();
      const utm =
        (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ??
        {};
      window.plausible?.('partner_apply_submit', {
        props: {
          source: 'partners-page',
          ...utm,
        },
      });
    } catch (err) {
      setState('error');
      setErrorMsg(err instanceof Error ? err.message : t(`${NS}.errors.generic`));
      // Turnstile tokens are single-use: the failed request consumed this one,
      // so reset the widget or every retry would fail captcha until a reload.
      captcha.reset();
      turnstileRef.current?.reset();
    }
  };

  if (state === 'success') {
    return (
      <div className="partner-form-success">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="partner-form-success-icon"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12l3 3 5-5" />
        </svg>
        <h3>{t(`${NS}.success.title`)}</h3>
        <p>{t(`${NS}.success.body`)}</p>
      </div>
    );
  }

  const disabled = state === 'loading';

  return (
    <form
      className="partner-form"
      onSubmit={handleSubmit}
      noValidate
      onFocus={() => {
        if (!hasFiredStart.current) {
          hasFiredStart.current = true;
          window.plausible?.('partner_form_start', { props: { source: 'partners-page' } });
        }
      }}
    >
      {/* Honeypot: bots fill this; a filled value yields a silent success. */}
      <div className="partner-form-honeypot" aria-hidden="true">
        <input type="text" name="company_url" ref={honeypotRef} tabIndex={-1} autoComplete="off" />
      </div>

      <div className="partner-form-row">
        <div className="partner-form-field">
          <label htmlFor="partner-contact-name">{t(`${NS}.fields.contactName`)}</label>
          <input
            id="partner-contact-name"
            ref={contactNameRef}
            type="text"
            placeholder={t(`${NS}.fields.contactNamePlaceholder`)}
            required
            maxLength={200}
            disabled={disabled}
          />
        </div>
        <div className="partner-form-field">
          <label htmlFor="partner-job-title">{t(`${NS}.fields.jobTitle`)}</label>
          <input
            id="partner-job-title"
            ref={jobTitleRef}
            type="text"
            placeholder={t(`${NS}.fields.jobTitlePlaceholder`)}
            maxLength={200}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="partner-form-row">
        <div className="partner-form-field">
          <label htmlFor="partner-email">{t(`${NS}.fields.email`)}</label>
          <input
            id="partner-email"
            ref={emailRef}
            type="email"
            placeholder={t(`${NS}.fields.emailPlaceholder`)}
            required
            disabled={disabled}
          />
        </div>
        <div className="partner-form-field">
          <label htmlFor="partner-phone">{t(`${NS}.fields.phone`)}</label>
          <input
            id="partner-phone"
            ref={phoneRef}
            type="tel"
            placeholder={t(`${NS}.fields.phonePlaceholder`)}
            maxLength={64}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="partner-form-row">
        <div className="partner-form-field">
          <label htmlFor="partner-company">{t(`${NS}.fields.company`)}</label>
          <input
            id="partner-company"
            ref={companyRef}
            type="text"
            placeholder={t(`${NS}.fields.companyPlaceholder`)}
            required
            maxLength={200}
            disabled={disabled}
          />
        </div>
        <div className="partner-form-field">
          <label htmlFor="partner-website">{t(`${NS}.fields.website`)}</label>
          <input
            id="partner-website"
            ref={websiteRef}
            type="url"
            placeholder={t(`${NS}.fields.websitePlaceholder`)}
            maxLength={512}
            disabled={disabled}
          />
        </div>
      </div>

      <div className="partner-form-field">
        <label htmlFor="partner-country">{t(`${NS}.fields.country`)}</label>
        <select
          id="partner-country"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          required
          disabled={disabled}
        >
          <option value="">{t(`${NS}.fields.countryPlaceholder`)}</option>
          {COUNTRIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <fieldset className="partner-form-fieldset">
        <legend>{t(`${NS}.fields.partnerTypes`)}</legend>
        <div className="partner-form-checkboxes">
          {PARTNER_TYPES.map((type) => (
            <label key={type} className="partner-form-checkbox">
              <input
                type="checkbox"
                checked={partnerTypes.includes(type)}
                onChange={() => togglePartnerType(type)}
                disabled={disabled}
              />
              <span>{t(`${NS}.partnerTypeOptions.${type}`)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="partner-form-checkbox partner-form-checkbox--block">
        <input
          type="checkbox"
          checked={isDistributor}
          onChange={(e) => setIsDistributor(e.target.checked)}
          disabled={disabled}
        />
        <span>{t(`${NS}.fields.isDistributor`)}</span>
      </label>

      <div className="partner-form-field">
        <label htmlFor="partner-how-heard">{t(`${NS}.fields.howHeard`)}</label>
        <select
          id="partner-how-heard"
          value={howHeard}
          onChange={(e) => setHowHeard(e.target.value)}
          disabled={disabled}
        >
          <option value="">{t(`${NS}.fields.howHeardPlaceholder`)}</option>
          {HOW_HEARD_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {t(`${NS}.howHeardOptions.${option}`)}
            </option>
          ))}
        </select>
      </div>

      <div className="partner-form-field">
        <label htmlFor="partner-message">{t(`${NS}.fields.message`)}</label>
        <textarea
          id="partner-message"
          ref={messageRef}
          placeholder={t(`${NS}.fields.messagePlaceholder`)}
          maxLength={4000}
          rows={5}
          disabled={disabled}
        />
      </div>

      <label className="partner-form-checkbox partner-form-checkbox--block">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          required
          disabled={disabled}
        />
        <span>{t(`${NS}.fields.consent`)}</span>
      </label>

      {state === 'error' && (
        <p className="partner-form-error" role="alert">
          {errorMsg}
        </p>
      )}

      {captchaEnabled && (
        <Turnstile
          ref={turnstileRef}
          siteKey={turnstileSiteKey}
          options={{ action: 'partner_apply' }}
          key={captcha.nonce}
          onSuccess={captcha.onSuccess}
          onExpire={captcha.onExpire}
          onError={captcha.onError}
        />
      )}
      {captchaEnabled && captcha.failed && (
        <p className="partner-form-error" role="status">
          {t(`${NS}.errors.captchaUnavailable`)}{' '}
          <button
            type="button"
            className="form-inline-action"
            onClick={captcha.retry}
            data-track="captcha_retry"
          >
            {t(`${NS}.errors.captchaRetry`)}
          </button>
        </p>
      )}

      <button type="submit" className="partner-form-submit" disabled={disabled}>
        {disabled ? t(`${NS}.sending`) : t(`${NS}.submit`)}
      </button>
    </form>
  );
};

export default PartnerApplicationForm;
