import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface LogoWallProps {
  lang?: Language;
}

const LogoWall: React.FC<LogoWallProps> = ({ lang = 'en' }) => {
  const { t, to } = useTranslation(lang);
  const categories = to('logoWall.categories');

  if (categories.length === 0) return null;

  return (
    <section className="logo-wall" aria-label={t('logoWall.title')}>
      <div className="container">
        <p className="logo-wall-label">{t('logoWall.title')}</p>
        <div className="logo-wall-row">
          {categories.map((category, index) => (
            <span key={`lw-${index}`} className="logo-wall-badge">
              {category}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
};

export default LogoWall;
