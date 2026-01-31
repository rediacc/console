import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import type { Platform, InstallMethod } from '../config/install';
import {
  PLATFORMS,
  METHOD_META,
  QUICK_INSTALL_UNIX,
  QUICK_INSTALL_WIN,
  BINARY_COMMANDS,
  DOCKER_COMMANDS,
  APT_COMMANDS,
  DNF_COMMANDS,
  HOMEBREW_COMMAND,
  detectPlatform,
} from '../config/install';
import { copyToClipboard } from '../utils/clipboard';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import { CopyIcon, CheckIcon } from './icons/ClipboardIcons';
import PlatformTabs from './PlatformTabs';

interface InstallMethodsProps {
  lang: Language;
}

type FilterTab = 'all' | Platform;

/** Map method anchor to the platform it implies for auto-selection */
const ANCHOR_PLATFORM_MAP: Record<string, Platform> = {
  apt: 'linux',
  dnf: 'linux',
  homebrew: 'macos',
};

interface CodeBlockProps {
  id: string;
  label: string;
  code: string;
  copyText: string;
  copiedText: string;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ id, label, code, copyText, copiedText }) => {
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLElement>(null);

  const handleCopy = async () => {
    const success = await copyToClipboard(code, codeRef.current ?? undefined);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="code-block">
      <div className="code-header">
        <span>{label}</span>
        <button
          type="button"
          className={`copy-btn${copied ? ' copied' : ''}`}
          onClick={handleCopy}
        >
          <span className="copy-btn-icon">{copied ? <CheckIcon /> : <CopyIcon />}</span>
          <span>{copied ? copiedText : copyText}</span>
        </button>
      </div>
      <pre><code id={`code-${id}`} ref={codeRef}>{code}</code></pre>
    </div>
  );
};

/** Return code blocks for a given method, optionally filtered by platform */
function getMethodBlocks(
  method: InstallMethod,
  filter: FilterTab,
): { id: string; label: string; code: string }[] {
  switch (method) {
    case 'quick': {
      const blocks: { id: string; label: string; code: string }[] = [];
      if (filter === 'all' || filter === 'linux' || filter === 'macos') {
        blocks.push({ id: 'quick-unix', label: 'bash', code: QUICK_INSTALL_UNIX });
      }
      if (filter === 'all' || filter === 'windows') {
        blocks.push({ id: 'quick-win', label: 'powershell', code: QUICK_INSTALL_WIN });
      }
      return blocks;
    }
    case 'binary': {
      if (filter === 'all') {
        // Show all platforms combined like the original static page
        const combined = [
          BINARY_COMMANDS.linux,
          BINARY_COMMANDS.macos,
          BINARY_COMMANDS.windows,
        ].join('\n\n');
        return [{ id: 'binary', label: 'bash', code: combined }];
      }
      const platform = filter as Platform;
      const lang = platform === 'windows' ? 'powershell' : 'bash';
      return [{ id: `binary-${platform}`, label: lang, code: BINARY_COMMANDS[platform] }];
    }
    case 'docker':
      return [{ id: 'docker', label: 'bash', code: DOCKER_COMMANDS }];
    case 'apt':
      return [{ id: 'apt', label: 'bash', code: APT_COMMANDS }];
    case 'dnf':
      return [{ id: 'dnf', label: 'bash', code: DNF_COMMANDS }];
    case 'homebrew':
      return [{ id: 'homebrew', label: 'bash', code: HOMEBREW_COMMAND }];
    default:
      return [];
  }
}

const InstallMethods: React.FC<InstallMethodsProps> = ({ lang }) => {
  const { t } = useTranslation(lang);
  const [filter, setFilter] = useState<FilterTab>('all');
  const [initialized, setInitialized] = useState(false);

  const handleFilterChange = useCallback((tab: FilterTab) => {
    setFilter(tab);
  }, []);

  // On mount: detect platform and handle URL hash for deep-linking
  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash && ANCHOR_PLATFORM_MAP[hash]) {
      setFilter(ANCHOR_PLATFORM_MAP[hash]);
      // Scroll to the anchor after a short delay to let React render
      requestAnimationFrame(() => {
        const el = document.getElementById(hash);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      });
    } else {
      // Auto-detect platform and pre-select
      const detected = detectPlatform();
      setFilter(detected);
    }
    setInitialized(true);
  }, []);

  // Filter methods: "all" shows everything, platform filter hides unsupported methods
  const visibleMethods = METHOD_META.filter(
    (m) => filter === 'all' || m.platforms.includes(filter as Platform),
  );

  const filterTabs: { key: FilterTab; label: string; icon?: React.FC }[] = [
    { key: 'all', label: t('pages.install.platformFilter.all') },
    ...PLATFORMS.map(({ key }) => ({
      key: key as FilterTab,
      label: t(`hero.install.tabs.${key}`),
      icon: PLATFORM_ICON_MAP[key],
    })),
  ];

  return (
    <section className="install-methods section-light">
      <div className="container">
        {/* Platform filter tabs */}
        <PlatformTabs
          tabs={filterTabs}
          activeTab={filter}
          onTabChange={(key) => handleFilterChange(key as FilterTab)}
          ariaLabel={t('pages.install.platformFilter.label')}
        />

        {/* Method cards */}
        {visibleMethods.map((method) => {
          const blocks = getMethodBlocks(method.id, filter);
          if (blocks.length === 0) return null;

          return (
            <div
              key={method.id}
              id={method.anchor}
              className={`method-card${method.featured ? ' method-card-featured' : ''}${initialized ? ' method-card--visible' : ''}`}
            >
              <div className="method-header">
                <h2>{t(`pages.install.methods.${method.id}.title`)}</h2>
                <p className="method-description">
                  {t(`pages.install.methods.${method.id}.description`)}
                </p>
              </div>
              {blocks.map((block) => (
                <CodeBlock
                  key={block.id}
                  id={block.id}
                  label={block.label}
                  code={block.code}
                  copyText={t('pages.install.copy')}
                  copiedText={t('pages.install.copied')}
                />
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default InstallMethods;
