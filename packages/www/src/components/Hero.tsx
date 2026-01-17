import React from 'react';
import { EXTERNAL_LINKS, getConsoleUrl } from '../config/constants';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface HeroProps {
  lang?: Language;
  origin?: string;
}

const Hero: React.FC<HeroProps> = ({ lang = 'en', origin }) => {
  const { t } = useTranslation(lang);

  // Get console URL (use origin from server-side if provided)
  const consoleUrl = getConsoleUrl(origin);

  return (
    <section className="hero hero-dark" id="hero">
      <div className="hero-container">
        <div className="hero-content">
          <h1 className="hero-title">
            {t('hero.title')}
            <span className="hero-highlight">{t('hero.titleHighlight')}</span>
          </h1>
          <p className="hero-subtitle">{t('hero.subtitle')}</p>
          <div className="hero-cta">
            <div className="hero-cta-primary">
              <div className="hero-badge">
                <span className="badge-icon">✓</span>
                <span>{t('hero.cta.freeBadge')}</span>
              </div>
              <a
                href={consoleUrl}
                className="btn btn-primary"
                target="_blank"
                rel="noopener noreferrer"
              >
                {t('hero.cta.contactUs')}
              </a>
              <p className="hero-cta-note">
                {t('hero.cta.benefits')}
                <br />
                <a href={`/${lang}/pricing#plans`}>{t('hero.cta.seeDetails')} →</a>
              </p>
            </div>
            <a
              href={EXTERNAL_LINKS.SCHEDULE_CONSULTATION}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
            >
              {t('hero.cta.bookDemo')}
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
