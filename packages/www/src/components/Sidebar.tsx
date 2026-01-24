import React, { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../hooks/useLanguage';
import { useTranslation } from '../i18n/react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);
  const sidebarRef = useRef<HTMLElement>(null);
  const [currentPath, setCurrentPath] = useState('');

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
    setCurrentPath(window.location.pathname);
  }, []);

  const isActive = (href: string) => {
    if (!currentPath) return false;
    const normalizedHref = href.endsWith('/') ? href : href + '/';
    const normalizedPath = currentPath.endsWith('/') ? currentPath : currentPath + '/';
    return normalizedPath === normalizedHref;
  };

  useEffect(() => {
    if (isOpen) {
      document.body.classList.add('sidebar-active');
      document.body.style.overflow = 'hidden';
      // Focus the first link when sidebar opens
      const firstLink = sidebarRef.current?.querySelector<HTMLAnchorElement>('.sidebar-link');
      firstLink?.focus();
    } else {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    }

    return () => {
      document.body.classList.remove('sidebar-active');
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      // Focus trap
      if (e.key === 'Tab' && sidebarRef.current) {
        const focusableElements = sidebarRef.current.querySelectorAll<HTMLElement>(
          'a[href], button, [tabindex]:not([tabindex="-1"])'
        );
        const firstEl = focusableElements[0];
        const lastEl = focusableElements[focusableElements.length - 1];

        if (e.shiftKey && document.activeElement === firstEl) {
          e.preventDefault();
          lastEl?.focus();
        } else if (!e.shiftKey && document.activeElement === lastEl) {
          e.preventDefault();
          firstEl?.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleLinkClick = () => {
    onClose();
  };

  return (
    <>
      {/* Backdrop overlay */}
      <div
        className={`sidebar-overlay ${isOpen ? 'sidebar-overlay-visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Sidebar */}
      <aside
        ref={sidebarRef}
        id="navigation-sidebar"
        className={`sidebar ${isOpen ? 'sidebar-open' : ''}`}
        role="navigation"
        aria-label={t('common.aria.mainNavigation')}
        aria-hidden={!isOpen}
      >
        <nav className="sidebar-nav">
          {navItems.map((item) => {
            const active = isActive(item.href);
            return (
              <a
                key={item.href}
                href={item.href}
                className={`sidebar-link${active ? ' active' : ''}`}
                onClick={handleLinkClick}
                tabIndex={isOpen ? 0 : -1}
                aria-current={active ? 'page' : undefined}
              >
                {item.label}
              </a>
            );
          })}
        </nav>
      </aside>
    </>
  );
};

export default Sidebar;
