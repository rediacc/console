import React from 'react';
import { getLanguageName } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import LanguageMenu from './LanguageMenu';
import '../styles/language-switcher-inline.css';

interface LanguageSwitcherProps {
  currentLang: Language;
  availableLanguages: { lang: Language; url: string }[];
  showFallbackNotice?: boolean;
}

const LanguageSwitcher: React.FC<LanguageSwitcherProps> = ({
  currentLang,
  availableLanguages,
  showFallbackNotice = false,
}) => {
  const { t } = useTranslation(currentLang);

  // If only one language available, don't show switcher
  if (availableLanguages.length <= 1 && !showFallbackNotice) {
    return null;
  }

  return (
    <div className="language-switcher">
      {showFallbackNotice && (
        <div className="translation-notice" role="status">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>
            {t('common.contentNotAvailable', {
              language: getLanguageName(currentLang).toLowerCase(),
            })}
          </span>
        </div>
      )}

      <LanguageMenu
        currentLang={currentLang}
        languages={availableLanguages}
        position="top"
        navigationMode="link"
        ariaLabel={t('navigation.selectLanguage')}
      />
    </div>
  );
};

export default LanguageSwitcher;
