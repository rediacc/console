import React, { useState, useEffect } from 'react';
import LanguageMenu from './LanguageMenu';
import { SUPPORTED_LANGUAGES, getLanguageFromPath } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import '../styles/language-switcher.css';

const Footer: React.FC = () => {
  const currentYear = new Date().getFullYear();
  const [currentLang, setCurrentLang] = useState<Language>('en');
  const { t } = useTranslation(currentLang);

  // Get current language from URL on mount
  useEffect(() => {
    const lang = getLanguageFromPath(window.location.pathname);
    setCurrentLang(lang);
  }, []);

  return (
    <footer id="footer" className="footer" role="contentinfo">
      <div className="footer-container">
        <div className="footer-columns">
          {/* Navigation Column */}
          <div className="footer-column footer-nav">
            <a href={`/${currentLang}/`} className="footer-link">
              {t('navigation.home')}
            </a>
            <a href={`/${currentLang}/blog`} className="footer-link">
              {t('navigation.blog')}
            </a>
            <a href={`/${currentLang}/docs`} className="footer-link">
              {t('navigation.docs')}
            </a>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('navigation.contact')}
            </a>
          </div>

          {/* Product Column */}
          <div className="footer-column">
            <h4 className="footer-heading">{t('footer.columns.product')}</h4>
            <a href={`/${currentLang}/#solutions`} className="footer-link">
              {t('footer.productLinks.solutions')}
            </a>
            <a href={`/${currentLang}/#problem`} className="footer-link">
              {t('footer.productLinks.overview')}
            </a>
            <a href={`/${currentLang}/pricing`} className="footer-link">
              {t('footer.productLinks.pricing')}
            </a>
            <a href={`/${currentLang}/professional-services`} className="footer-link">
              {t('footer.productLinks.professionalServices')}
            </a>
          </div>

          {/* Organization Column */}
          <div className="footer-column">
            <h4 className="footer-heading">{t('footer.columns.organization')}</h4>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.organizationLinks.aboutUs')}
            </a>
            <a href={`/${currentLang}/team`} className="footer-link">
              {t('footer.organizationLinks.team')}
            </a>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.organizationLinks.contact')}
            </a>
          </div>

          {/* Support Column */}
          <div className="footer-column">
            <h4 className="footer-heading">{t('footer.columns.support')}</h4>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.supportLinks.helpCenter')}
            </a>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.supportLinks.contactSupport')}
            </a>
          </div>

          {/* Legal Column */}
          <div className="footer-column">
            <h4 className="footer-heading">{t('footer.columns.legal')}</h4>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.legalLinks.termsOfUse')}
            </a>
            <a href={`/${currentLang}/contact`} className="footer-link">
              {t('footer.legalLinks.privacyPolicy')}
            </a>
          </div>
        </div>

        {/* Footer Bottom */}
        <div className="footer-bottom">
          <div className="footer-bottom-left">
            {/* Social Icons */}
            <div className="footer-social">
              <a href="#" className="footer-social-link" aria-label="X (Twitter)">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </a>
              <a
                href="https://github.com/orgs/rediacc/"
                className="footer-social-link"
                aria-label="GitHub"
                target="_blank"
                rel="noopener noreferrer"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.17 6.839 9.49.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.167 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                </svg>
              </a>
              <a
                href="https://www.linkedin.com/organization/rediacc/about"
                className="footer-social-link"
                aria-label="LinkedIn"
                target="_blank"
                rel="noopener noreferrer"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                </svg>
              </a>
            </div>
            <p className="footer-copyright">Rediacc &copy; 2023-{currentYear}</p>
          </div>
          <div className="footer-bottom-right">
            <LanguageMenu
              variant="flag-name"
              currentLang={currentLang}
              languages={SUPPORTED_LANGUAGES}
              position="bottom"
              navigationMode="button"
              ariaLabel={t('navigation.selectLanguage')}
            />
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
