import React from 'react';
import { CONTACT_EMAIL } from '../config/constants';
import { useTranslation } from '../i18n/react';

const EarlyAccess: React.FC = () => {
  const { t, ta, to } = useTranslation();
  const benefits = ta('earlyAccess.benefits');
  const formFields = to('earlyAccess.form.fields');

  return (
    <section className="early-access" id="early-access">
      <div className="container">
        <div className="early-access-content">
          <div className="early-access-text">
            <h2 className="section-title">{t('earlyAccess.title')}</h2>
            <p className="section-subtitle">{t('earlyAccess.subtitle')}</p>
            <ul className="early-access-benefits">
              {benefits.map((benefit, index) => (
                <li key={`benefit-${index}-${benefit.substring(0, 20)}`}>{benefit}</li>
              ))}
            </ul>
          </div>
          <div className="early-access-form">
            <form
              name="early-access"
              method="POST"
              action={`mailto:${CONTACT_EMAIL}?subject=Early%20Access%20Request%20-%20Rediacc%20Platform`}
              encType="text/plain"
              className="form"
            >
              <div className="form-group">
                <label htmlFor="name" className="form-label">
                  {formFields.name.label}
                </label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  className="form-input"
                  required
                  aria-describedby="name-error"
                  aria-invalid="false"
                  onInvalid={(e) => e.currentTarget.setAttribute('aria-invalid', 'true')}
                  onInput={(e) => {
                    if (e.currentTarget.validity.valid) {
                      e.currentTarget.setAttribute('aria-invalid', 'false');
                    }
                  }}
                  autoComplete={formFields.name.autoComplete}
                  suppressHydrationWarning
                />
                <div className="form-error" id="name-error" role="alert" aria-live="polite" />
              </div>

              <div className="form-group">
                <label htmlFor="email" className="form-label">
                  {formFields.email.label}
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  className="form-input"
                  required
                  aria-describedby="email-error"
                  aria-invalid="false"
                  onInvalid={(e) => e.currentTarget.setAttribute('aria-invalid', 'true')}
                  onInput={(e) => {
                    if (e.currentTarget.validity.valid) {
                      e.currentTarget.setAttribute('aria-invalid', 'false');
                    }
                  }}
                  autoComplete={formFields.email.autoComplete}
                  suppressHydrationWarning
                />
                <div className="form-error" id="email-error" role="alert" aria-live="polite" />
              </div>

              <div className="form-group">
                <label htmlFor="organization" className="form-label">
                  {formFields.organization.label}
                </label>
                <input
                  type="text"
                  id="organization"
                  name="organization"
                  className="form-input"
                  required
                  aria-describedby="organization-error"
                  autoComplete={formFields.organization.autoComplete}
                  suppressHydrationWarning
                />
                <div
                  className="form-error"
                  id="organization-error"
                  role="alert"
                  aria-live="polite"
                />
              </div>

              <div className="form-group">
                <label htmlFor="role" className="form-label">
                  {formFields.role.label}
                </label>
                <input
                  type="text"
                  id="role"
                  name="role"
                  className="form-input"
                  autoComplete={formFields.role.autoComplete}
                  suppressHydrationWarning
                />
              </div>

              <div className="form-group">
                <label htmlFor="use-case" className="form-label">
                  {formFields.useCase.label}
                </label>
                <select
                  id="use-case"
                  name="use-case"
                  className="form-select"
                  required
                  aria-describedby="use-case-error"
                >
                  <option value="">{formFields.useCase.options.placeholder}</option>
                  <option value="development-acceleration">
                    {formFields.useCase.options.developmentAcceleration}
                  </option>
                  <option value="disaster-recovery">
                    {formFields.useCase.options.disasterRecovery}
                  </option>
                  <option value="ai-safe-operations">
                    {formFields.useCase.options.aiSafeOperations}
                  </option>
                  <option value="multiple">{formFields.useCase.options.multiple}</option>
                  <option value="other">{formFields.useCase.options.other}</option>
                </select>
                <div className="form-error" id="use-case-error" role="alert" aria-live="polite" />
              </div>

              <div className="form-group">
                <label htmlFor="message" className="form-label">
                  {formFields.message.label}
                </label>
                <textarea
                  id="message"
                  name="message"
                  className="form-textarea"
                  rows={4}
                  aria-describedby="message-error"
                  placeholder={formFields.message.placeholder}
                  suppressHydrationWarning
                />
                <div className="form-error" id="message-error" role="alert" aria-live="polite" />
              </div>

              <button type="submit" className="btn btn-primary btn-full">
                {t('earlyAccess.form.submit')}
              </button>
            </form>
          </div>
        </div>
      </div>
    </section>
  );
};

export default EarlyAccess;
