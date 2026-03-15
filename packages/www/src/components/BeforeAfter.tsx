import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface BeforeAfterProps {
  lang?: Language;
}

const BeforeAfter: React.FC<BeforeAfterProps> = ({ lang = 'en' }) => {
  const { t, to } = useTranslation(lang);
  const beforePoints = (to('beforeAfter.before.points') as string[] | undefined) ?? [];
  const afterPoints = (to('beforeAfter.after.points') as string[] | undefined) ?? [];

  return (
    <section className="before-after">
      <div className="container">
        <header className="section-header">
          <h2 className="section-title">{t('beforeAfter.title')}</h2>
        </header>
        <div className="before-after-grid">
          <div className="before-after-card before-after-card--before">
            <h3>{t('beforeAfter.before.label')}</h3>
            <ul>
              {beforePoints.map((point, index) => (
                <li key={`before-${index}`}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M4 4l8 8M12 4l-8 8"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <div className="before-after-card before-after-card--after">
            <h3>{t('beforeAfter.after.label')}</h3>
            <ul>
              {afterPoints.map((point, index) => (
                <li key={`after-${index}`}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M3 8l4 4 6-6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
};

export default BeforeAfter;
