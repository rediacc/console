import React, { useState } from 'react';
import { PLATFORMS, detectPlatform } from '../config/install';
import { useTranslation } from '../i18n/react';
import { PLATFORM_ICON_MAP } from './icons/PlatformIcons';
import PlatformTabs from './PlatformTabs';
import type { Platform } from '../config/install';
import type { Language } from '../i18n/types';
import type { ReleaseData, DownloadFile, CLIFile } from '../utils/release-parser';

interface DownloadsListProps {
  lang: Language;
  releaseData: ReleaseData | null;
}

function archLabel(t: (key: string) => string, file: DownloadFile | CLIFile): string {
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

  const desktopFiles = releaseData.desktopFiles.filter((f) => f.platform === activePlatform);
  const cliFiles = releaseData.cliFiles.filter((f) => f.platform === activePlatform);

  const linuxAppImages = desktopFiles.filter((f) => f.type === 'AppImage');
  const linuxDebs = desktopFiles.filter((f) => f.type === 'deb');
  const isLinux = activePlatform === 'linux';

  return (
    <>
      <PlatformTabs
        tabs={tabs}
        activeTab={activePlatform}
        onTabChange={(key) => setActivePlatform(key as Platform)}
        ariaLabel={t('pages.install.platformFilter.label')}
      />

      {/* Desktop section */}
      <h2 className="section-heading">{t('pages.downloads.sections.desktop')}</h2>

      {desktopFiles.length > 0 ? (
        <div className="platform-section">
          <div className="platform-header">
            <h2>{t(`pages.downloads.platforms.${activePlatform}`)}</h2>
          </div>

          {isLinux ? (
            <>
              {linuxAppImages.length > 0 && (
                <div className="linux-subsection">
                  <h3>{t('pages.downloads.types.appimage')}</h3>
                  <div className="download-list">
                    {linuxAppImages.map((file) => (
                      <div key={file.name} className="download-item">
                        <div className="download-info">
                          <span className="download-arch">{archLabel(t, file)}</span>
                          <span className="download-size">{file.size}</span>
                        </div>
                        <a href={file.url} className="btn btn-primary download-button">
                          {t('pages.downloads.actions.download')}
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {linuxDebs.length > 0 && (
                <div className="linux-subsection">
                  <h3>{t('pages.downloads.types.deb')}</h3>
                  <div className="download-list">
                    {linuxDebs.map((file) => (
                      <div key={file.name} className="download-item">
                        <div className="download-info">
                          <span className="download-arch">{archLabel(t, file)}</span>
                          <span className="download-size">{file.size}</span>
                        </div>
                        <a href={file.url} className="btn btn-primary download-button">
                          {t('pages.downloads.actions.download')}
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="download-list">
              {desktopFiles.map((file) => (
                <div key={file.name} className="download-item">
                  <div className="download-info">
                    <span className="download-arch">{archLabel(t, file)}</span>
                    <span className="download-size">{file.size}</span>
                  </div>
                  <a href={file.url} className="btn btn-primary download-button">
                    {t('pages.downloads.actions.download')} .{file.type}
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="no-releases">
          <p>{t('pages.downloads.noReleases')}</p>
        </div>
      )}

      {/* CLI section */}
      {cliFiles.length > 0 && (
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
                  <a href={file.url} className="btn btn-primary download-button">
                    {t('pages.downloads.actions.download')} {file.name}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
};

export default DownloadsList;
