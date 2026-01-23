import React, { useState } from 'react';
import { getLanguageFlag, getLanguageName } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import { setLanguageCookie } from '../utils/language-cookie';
import type { Language } from '../i18n/types';
import '../styles/language-switcher.css';
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
  const [isOpen, setIsOpen] = useState(false);
  const { t } = useTranslation(currentLang);

  // Handler to set language cookie when switching languages
  const handleLanguageSelect = (lang: Language) => {
    setLanguageCookie(lang);
  };

  // If only one language available, don't show switcher
  if (availableLanguages.length <= 1 && !showFallbackNotice) {
    return null;
  }

  return (
    <div className="language-switcher">
      {showFallbackNotice && (
        <div className="translation-notice">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
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

      <div className="language-selector">
        <button
          type="button"
          className="language-trigger"
          onClick={() => setIsOpen(!isOpen)}
          aria-label={t('navigation.selectLanguage')}
          aria-expanded={isOpen}
        >
          <span className="language-flag">{getLanguageFlag(currentLang)}</span>
          <span className="language-name">{getLanguageName(currentLang)}</span>
          <svg
            className={`language-chevron ${isOpen ? 'open' : ''}`}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {isOpen && (
          <div
            className="language-menu top"
            role="menu"
            aria-label={t('navigation.languageSelectionMenu')}
          >
            {availableLanguages.map(({ lang, url }) => (
              <a
                key={lang}
                href={url}
                className={`language-option ${lang === currentLang ? 'active' : ''}`}
                onClick={() => handleLanguageSelect(lang)}
              >
                <span className="flag">{getLanguageFlag(lang)}</span>
                <span className="name">{getLanguageName(lang)}</span>
                {lang === currentLang && (
                  <svg
                    className="checkmark"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default LanguageSwitcher;
