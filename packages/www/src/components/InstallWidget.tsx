import React, { useRef, useState } from 'react';
import { detectPlatform, PLATFORMS, QUICK_INSTALL_COMMANDS } from '../config/install';
import { useTranslation } from '../i18n/react';
import { copyToClipboard } from '../utils/clipboard';
import { CheckIcon, CopyIcon } from './icons/ClipboardIcons';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import type { Platform } from '../config/install';
import type { Language } from '../i18n/types';

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
            data-track="cta_click"
            data-track-label="install-tab"
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
          data-track="cta_click"
          data-track-label="install-copy"
          data-track-dest={activePlatform}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
        </button>
      </div>
      <div className="install-alt-methods">
        <a
          href={`/${lang}/install#homebrew`}
          data-track="cta_click"
          data-track-label="install-alt"
          data-track-dest="homebrew"
        >
          {t('hero.install.alt.brew')}
        </a>
        <span className="install-alt-sep">&middot;</span>
        <a
          href={`/${lang}/install#apt`}
          data-track="cta_click"
          data-track-label="install-alt"
          data-track-dest="apt"
        >
          {t('hero.install.alt.apt')}
        </a>
        <span className="install-alt-sep">&middot;</span>
        <a
          href={`/${lang}/install#docker`}
          data-track="cta_click"
          data-track-label="install-alt"
          data-track-dest="docker"
        >
          {t('hero.install.alt.docker')}
        </a>
        <span className="install-alt-sep">&middot;</span>
        <a
          href={`/${lang}/install`}
          data-track="cta_click"
          data-track-label="install-alt"
          data-track-dest="all"
        >
          {t('hero.install.alt.more')}
        </a>
      </div>
    </div>
  );
};

export default InstallWidget;
