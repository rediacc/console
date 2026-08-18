import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { InstallMethod, Platform } from '../config/install';
import {
  APK_COMMANDS,
  APT_COMMANDS,
  BINARY_COMMANDS,
  DNF_COMMANDS,
  DOCKER_COMMANDS,
  detectPlatform,
  HOMEBREW_COMMAND,
  METHOD_META,
  PACMAN_COMMANDS,
  PLATFORMS,
  QUICK_INSTALL_UNIX,
  QUICK_INSTALL_WIN,
} from '../config/install';
// Route-scoped translations: this island hydrates on ONE page, so its strings ride
// this component's chunk instead of the catalog every route downloads.
import { useRouteTranslation } from '../i18n/react-route';
import type { Language } from '../i18n/types';
import { copyToClipboard } from '../utils/clipboard';
import { CheckIcon, CopyIcon } from './icons/ClipboardIcons';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import PlatformTabs from './PlatformTabs';

interface InstallMethodsProps {
  lang: Language;
}

type FilterTab = 'all' | Platform;

/** Map method anchor to the platform it implies for auto-selection */
const ANCHOR_PLATFORM_MAP: Record<string, Platform> = {
  apt: 'linux',
  dnf: 'linux',
  apk: 'linux',
  pacman: 'linux',
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
          data-track="cta_click"
          data-track-label="copy-code"
          data-track-dest={id}
        >
          <span className="copy-btn-icon">{copied ? <CheckIcon /> : <CopyIcon />}</span>
          <span>{copied ? copiedText : copyText}</span>
        </button>
      </div>
      <pre>
        <code id={`code-${id}`} ref={codeRef}>
          {code}
        </code>
      </pre>
    </div>
  );
};

/** Return code blocks for a given method, optionally filtered by platform */
function getMethodBlocks(
  method: InstallMethod,
  filter: FilterTab
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
      const lang = filter === 'windows' ? 'powershell' : 'bash';
      return [{ id: `binary-${filter}`, label: lang, code: BINARY_COMMANDS[filter] }];
    }
    case 'docker':
      return [{ id: 'docker', label: 'bash', code: DOCKER_COMMANDS }];
    case 'apt':
      return [{ id: 'apt', label: 'bash', code: APT_COMMANDS }];
    case 'dnf':
      return [{ id: 'dnf', label: 'bash', code: DNF_COMMANDS }];
    case 'apk':
      return [{ id: 'apk', label: 'sh', code: APK_COMMANDS }];
    case 'pacman':
      return [{ id: 'pacman', label: 'bash', code: PACMAN_COMMANDS }];
    case 'homebrew':
      return [{ id: 'homebrew', label: 'bash', code: HOMEBREW_COMMAND }];
    default:
      return [];
  }
}

const InstallMethods: React.FC<InstallMethodsProps> = ({ lang }) => {
  const { t } = useRouteTranslation(lang);

  // A useState initializer must be PURE. This one read window.location.hash and
  // called detectPlatform(), so the server's first render ('all') and the client's
  // first render could disagree, and it also called requestAnimationFrame from inside
  // the initializer, which StrictMode runs twice. Honest note on the evidence: the
  // symptom that sent me here, /en/install#homebrew rendering zero platform tabs,
  // turned out to be a two-day-old dev server whose module graph had gone stale, NOT
  // this code, and on a clean server the previous version logged no hydration warning
  // either. This change is correctness by the rules of the hook, not a repair of a
  // reproduced failure. Verified on a clean dev server: four tabs, macOS selected for
  // #homebrew, zero console errors.
  const [filter, setFilter] = useState<FilterTab>('all');

  // Platform detection and anchor handling belong after mount, where reading the URL
  // and the user agent is legal and cannot disagree with the server.
  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash && hash in ANCHOR_PLATFORM_MAP) {
      setFilter(ANCHOR_PLATFORM_MAP[hash]);
      const el = document.getElementById(hash);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    setFilter(detectPlatform());
  }, []);

  const handleFilterChange = useCallback((tab: FilterTab) => {
    setFilter(tab);
  }, []);

  // Filter methods: "all" shows everything, platform filter hides unsupported methods
  const visibleMethods = METHOD_META.filter(
    (m) => filter === 'all' || m.platforms.includes(filter)
  );

  const filterTabs: { key: FilterTab; label: string; icon?: React.FC }[] = [
    { key: 'all', label: t('pages.install.platformFilter.all') },
    ...PLATFORMS.map(({ key }) => ({
      key,
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
          onTabChange={handleFilterChange}
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
              className={`method-card${method.featured ? ' method-card-featured' : ''} method-card--visible`}
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
