import React, { useState } from 'react';
import type { Platform } from '../config/install';
import { detectPlatform, PLATFORMS } from '../config/install';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import type { CLIFile, ReleaseData } from '../utils/release-parser';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import PlatformTabs from './PlatformTabs';

interface DownloadsListProps {
  lang: Language;
  releaseData: ReleaseData | null;
}

function archLabel(t: (key: string) => string, file: CLIFile): string {
  if (file.platform === 'macos') {
    return file.arch === 'arm64'
      ? t('pages.downloads.architectures.arm64_apple')
      : t('pages.downloads.architectures.x64_intel');
  }
  return t(`pages.downloads.architectures.${file.arch}`);
}

const DownloadsList: React.FC<DownloadsListProps> = ({ lang, releaseData }) => {
  const { t } = useTranslation(lang);
  const [activePlatform, setActivePlatform] = useState<Platform>(detectPlatform);

  const tabs = PLATFORMS.map(({ key }) => ({
    key,
    label: t(`hero.install.tabs.${key}`),
    icon: PLATFORM_ICON_MAP[key],
  }));

  if (!releaseData) {
    return (
      <div className="no-releases">
        <p>{t('pages.downloads.noReleases')}</p>
      </div>
    );
  }

  const cliFiles = releaseData.cliFiles.filter((f) => f.platform === activePlatform);

  return (
    <>
      <PlatformTabs
        tabs={tabs}
        activeTab={activePlatform}
        onTabChange={setActivePlatform}
        ariaLabel={t('pages.install.platformFilter.label')}
      />

      {cliFiles.length > 0 ? (
        <>
          <h2 className="section-heading cli-section-heading">
            {t('pages.downloads.sections.cli')}
          </h2>
          <p className="cli-description">{t('pages.downloads.cli.description')}</p>

          <div className="platform-section cli-section">
            <div className="platform-header">
              <h2>{t(`pages.downloads.platforms.${activePlatform}`)}</h2>
            </div>
            <div className="download-list">
              {cliFiles.map((file) => (
                <div key={file.name} className="download-item">
                  <div className="download-info">
                    <span className="download-arch">{archLabel(t, file)}</span>
                    <span className="download-size">{file.size}</span>
                  </div>
                  <a
                    href={file.url}
                    className="btn btn-primary download-button"
                    data-track="cta_click"
                    data-track-label="download-cli"
                    data-track-dest={file.name}
                  >
                    {t('pages.downloads.actions.download')} {file.name}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="no-releases">
          <p>{t('pages.downloads.noReleases')}</p>
        </div>
      )}
    </>
  );
};

export default DownloadsList;
