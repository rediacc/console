import React, { useState, useRef } from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import { PLATFORMS, QUICK_INSTALL_COMMANDS, detectPlatform } from '../config/install';
import type { Platform } from '../config/install';
import { copyToClipboard } from '../utils/clipboard';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import { CopyIcon, CheckIcon } from './icons/ClipboardIcons';

interface InstallWidgetProps {
  lang?: Language;
}

const TABS = PLATFORMS.map(({ key }) => ({
  key,
  icon: PLATFORM_ICON_MAP[key],
}));

const InstallWidget: React.FC<InstallWidgetProps> = ({ lang = 'en' }) => {
  const { t } = useTranslation(lang);
  const [activePlatform, setActivePlatform] = useState<Platform>(detectPlatform);
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLElement>(null);

  const handleCopy = async () => {
    const success = await copyToClipboard(
      QUICK_INSTALL_COMMANDS[activePlatform],
      codeRef.current ?? undefined
    );
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="install-widget" role="region" aria-label={t('hero.install.ariaLabel')}>
      <div className="install-tabs" role="tablist" aria-label={t('hero.install.tabsLabel')}>
        {TABS.map(({ key, icon: Icon }) => (
          <button
            type="button"
            key={key}
            role="tab"
            aria-selected={activePlatform === key}
            className={`install-tab${activePlatform === key ? ' install-tab--active' : ''}`}
            onClick={() => setActivePlatform(key)}
          >
            <Icon />
            <span className="install-tab-label">{t(`hero.install.tabs.${key}`)}</span>
          </button>
        ))}
      </div>
      <div className="install-command" role="tabpanel">
        <code className="install-code" dir="ltr" ref={codeRef}>
          $ {QUICK_INSTALL_COMMANDS[activePlatform]}
        </code>
        <button
          type="button"
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
