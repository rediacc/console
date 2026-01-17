import React, { useEffect, useState } from 'react';
import { getLanguageFromPath } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  // eslint-disable-next-line react/hook-use-state
  const currentLang = useState<Language>(() => {
    if (typeof window === 'undefined') return 'en';
    return getLanguageFromPath(window.location.pathname);
  })[0];
  const { t } = useTranslation(currentLang);

  const navItems = [
    { href: `/${currentLang}/`, label: t('navigation.home') },
    {
      href: `/${currentLang}/solutions/disaster-recovery`,
      label: t('navigation.solutions.disasterRecovery'),
    },
    {
      href: `/${currentLang}/solutions/threat-response`,
      label: t('navigation.solutions.threatResponse'),
    },
    {
      href: `/${currentLang}/solutions/data-security`,
      label: t('navigation.solutions.dataSecurity'),
    },
    {
      href: `/${currentLang}/solutions/system-portability`,
      label: t('navigation.solutions.systemPortability'),
    },
    {
      href: `/${currentLang}/solutions/development-environments`,
      label: t('navigation.solutions.developmentEnvironments'),
    },
    { href: `/${currentLang}/blog`, label: t('navigation.blog') },
    { href: `/${currentLang}/docs`, label: t('navigation.docs') },
    { href: `/${currentLang}/downloads`, label: t('navigation.downloads') },
    { href: `/${currentLang}/contact`, label: t('navigation.contact') },
  ];

  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('sidebar-active');
    } else {
      document.body.classList.remove('sidebar-active');
    }

    return () => {
      document.body.classList.remove('sidebar-active');
    };
  }, [isOpen]);

  const handleLinkClick = () => {
    onClose();
  };

  return (
    <>
      {/* Sidebar */}
      <aside
        className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}
        role="navigation"
        aria-label={t('common.aria.mainNavigation')}
      >
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} className="sidebar-link" onClick={handleLinkClick}>
              {item.label}
            </a>
          ))}
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
