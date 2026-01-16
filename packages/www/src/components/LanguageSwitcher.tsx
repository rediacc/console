import React, { useState } from 'react';
import { getLanguageName, getLanguageFlag } from '../i18n/language-utils';
import { setLanguageCookie } from '../utils/language-cookie';
import type { Language } from '../i18n/types';
import '../styles/language-switcher.css';

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
            Este contenido no está disponible en {getLanguageName(currentLang).toLowerCase()}.
            Mostrando versión en inglés.
          </span>
        </div>
      )}

      <div className="language-selector">
        <button
          type="button"
          className="language-trigger"
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Select language"
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
          <div className="language-menu top">
            {availableLanguages.map(({ lang, url }) => (
              <a
                key={lang}
                href={url}
                className={`language-option ${lang === currentLang ? 'active' : ''}`}
                onClick={() => handleLanguageSelect(lang)}
              >
                <span className="flag">{getLanguageFlag(lang)}</span>
                <span className="name">{getLanguageName(lang)}</span>
                {lang === currentLang && <span className="checkmark">✓</span>}
              </a>
            ))}
          </div>
        )}
      </div>

      <style
        dangerouslySetInnerHTML={{
          __html: `
        .language-switcher {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          margin-bottom: 1rem;
        }

        .translation-notice {
          display: flex;
          align-items: flex-start;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          background-color: #fff3cd;
          border: 1px solid #ffc107;
          border-radius: 6px;
          color: #856404;
          font-size: 0.875rem;
          line-height: 1.5;
        }

        .translation-notice svg {
          flex-shrink: 0;
          margin-top: 0.125rem;
        }

        @media (max-width: 768px) {
          .translation-notice {
            font-size: 0.8rem;
            padding: 0.6rem 0.75rem;
          }
        }
      `,
        }}
      />
    </div>
  );
};

export default LanguageSwitcher;
