import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface HeroProps {
  lang?: Language;
  origin?: string;
}

const Hero: React.FC<HeroProps> = ({ lang = 'en' }) => {
  const { t } = useTranslation(lang);

  return (
    <section className="hero hero-dark" id="hero">
      <div className="hero-container">
        <div className="hero-content">
          <span className="hero-eyebrow">{t('hero.eyebrow')}</span>
          <h1 className="hero-title">
            {t('hero.title')}
            <span className="hero-highlight">{t('hero.titleHighlight')}</span>
          </h1>
          <p className="hero-subtitle">{t('hero.subtitle')}</p>
          <div className="hero-cta-group">
            <a
              href={`/${lang}/install`}
              className="btn btn-primary"
              data-track="cta_click"
              data-track-label="hero-primary"
              data-track-dest="install"
            >
              {t('hero.cta.getStarted')}
            </a>
            <a
              href={`/${lang}/docs/quick-start`}
              className="btn btn-ghost"
              data-track="cta_click"
              data-track-label="hero-secondary"
              data-track-dest="docs"
            >
              {t('hero.cta.readDocs')}
            </a>
          </div>
          <span className="hero-cta-badge">{t('hero.cta.freeBadge')}</span>
        </div>
      </div>
    </section>
  );
};

export default Hero;
