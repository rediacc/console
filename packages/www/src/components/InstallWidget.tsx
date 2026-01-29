import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface InstallWidgetProps {
  lang?: Language;
}

type Platform = 'linux' | 'macos' | 'windows';

const INSTALL_COMMANDS: Record<Platform, string> = {
  linux: 'curl -fsSL https://www.rediacc.com/install.sh | bash',
  macos: 'brew install rediacc/tap/rediacc-cli',
  windows: 'irm https://www.rediacc.com/install.ps1 | iex',
} as const;

const LinuxIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12.5 2c-1.6 0-2.9 1.3-3.1 2.9-.5.2-.9.5-1.3.9C7.1 6.7 6.5 8 6.5 9.5v3c0 .8-.3 1.6-.8 2.2l-1.5 1.8c-.4.5-.2 1.1.1 1.5.3.3.7.5 1.2.5h2.7c.3 1.5 1.5 2.5 3 2.5h1.6c1.5 0 2.7-1 3-2.5h2.7c.5 0 .9-.2 1.2-.5.3-.4.5-1 .1-1.5l-1.5-1.8c-.5-.6-.8-1.4-.8-2.2v-3c0-1.5-.6-2.8-1.6-3.7-.4-.4-.8-.7-1.3-.9C14.4 3.3 13.1 2 12.5 2zm0 1.5c.8 0 1.5.7 1.5 1.5 0 .1 0 .2-.1.3-.5-.1-.9-.2-1.4-.2s-1 .1-1.4.2c0-.1-.1-.2-.1-.3 0-.8.7-1.5 1.5-1.5zm0 3.1c1.9 0 3.5 1.6 3.5 3.5v3c0 1.1.4 2.2 1.2 3l.8 1H6l.8-1c.7-.8 1.2-1.9 1.2-3v-3c0-1.9 1.6-3.5 3.5-3.5zM11 18.5h3c-.2.6-.9 1-1.5 1h-1.6c-.3 0-.7-.4-.9-1z" />
  </svg>
);

const AppleIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M18.7 19.4c-.7 1-1.4 2-2.6 2-1.1 0-1.4-.7-2.7-.7-1.3 0-1.7.7-2.7.7-1.2 0-2.1-1.1-2.8-2.1-1.5-2.1-2.6-6-.1-8.6.8-1.1 2.1-1.7 3.4-1.8 1.1 0 2.1.7 2.7.7.7 0 1.9-.9 3.2-.7.5 0 2 .2 3 1.6-.1.1-1.8 1-1.8 3.1 0 2.4 2.1 3.2 2.1 3.2-.1.1-.3 1.1-1.1 2.2l.4.4zM15 3.7c.7-.8 1.1-2 1-3.1-1 0-2.2.7-2.9 1.5-.7.7-1.2 1.8-1.1 2.9 1.1.1 2.3-.5 3-1.3z" />
  </svg>
);

const WindowsIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M3 5.5l7.5-1v7H3V5.5zm0 13l7.5 1v-7H3v6zm8.5 1.2L21 21V12.5h-9.5v7.2zm0-15.4v7.2H21V3l-9.5 1.3z" />
  </svg>
);

const CopyIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
  </svg>
);

const CheckIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const TABS: { key: Platform; icon: React.FC }[] = [
  { key: 'linux', icon: LinuxIcon },
  { key: 'macos', icon: AppleIcon },
  { key: 'windows', icon: WindowsIcon },
];

const InstallWidget: React.FC<InstallWidgetProps> = ({ lang = 'en' }) => {
  const { t } = useTranslation(lang);
  const [activePlatform, setActivePlatform] = useState<Platform>('linux');
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes('win')) setActivePlatform('windows');
    else if (ua.includes('mac')) setActivePlatform('macos');
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMANDS[activePlatform]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      if (codeRef.current) {
        const range = document.createRange();
        range.selectNodeContents(codeRef.current);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
    }
  };

  return (
    <div
      className="install-widget"
      role="region"
      aria-label={t('hero.install.ariaLabel')}
    >
      <div
        className="install-tabs"
        role="tablist"
        aria-label={t('hero.install.tabsLabel')}
      >
        {TABS.map(({ key, icon: Icon }) => (
          <button
            key={key}
            role="tab"
            aria-selected={activePlatform === key}
            className={`install-tab${activePlatform === key ? ' install-tab--active' : ''}`}
            onClick={() => setActivePlatform(key)}
          >
            <Icon />
            <span className="install-tab-label">
              {t(`hero.install.tabs.${key}`)}
            </span>
          </button>
        ))}
      </div>
      <div className="install-command" role="tabpanel">
        <code className="install-code" dir="ltr" ref={codeRef}>
          $ {INSTALL_COMMANDS[activePlatform]}
        </code>
        <button
          className={`install-copy-btn${copied ? ' install-copy-btn--copied' : ''}`}
          onClick={handleCopy}
          aria-label={copied ? t('hero.install.copied') : t('hero.install.copy')}
          title={copied ? t('hero.install.copied') : t('hero.install.copy')}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
        </button>
      </div>
      <div className="install-alt-methods">
        <a href={`/${lang}/install#homebrew`}>{t('hero.install.alt.brew')}</a>
        <span className="install-alt-sep">&middot;</span>
        <a href={`/${lang}/install#apt`}>{t('hero.install.alt.apt')}</a>
        <span className="install-alt-sep">&middot;</span>
        <a href={`/${lang}/install#docker`}>{t('hero.install.alt.docker')}</a>
        <span className="install-alt-sep">&middot;</span>
        <a href={`/${lang}/install`}>{t('hero.install.alt.more')}</a>
      </div>
    </div>
  );
};

export default InstallWidget;
