import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface WindowWithImageModal extends Window {
  openImageModal?: (src: string, alt: string) => void;
}

interface ProblemProps {
  lang?: Language;
}

const Problem: React.FC<ProblemProps> = ({ lang = 'en' }) => {
  const { t } = useTranslation(lang);

  const openImageModal = (src: string, alt: string) => {
    // This function will be available from the global script
    const win = window as WindowWithImageModal;
    if (typeof window !== 'undefined' && win.openImageModal) {
      win.openImageModal(src, alt);
    }
  };

  return (
    <section className="problem" id="problem">
      <div className="container">
        <div className="section-header">
          <h2 className="section-title">{t('problem.title')}</h2>
          <p className="section-subtitle">{t('problem.subtitle')}</p>
        </div>
        <div className="problem-content">
          <div className="problem-illustration">
            {(() => {
              const langSuffix = lang === 'en' ? '' : `.${lang}`;
              const landscape = `/assets/images/problem${langSuffix}.svg`;
              const mobile = `/assets/images/problem${langSuffix}.mobile.svg`;
              return (
                <button
                  type="button"
                  className="image-button"
                  onClick={() => openImageModal(landscape, t('problem.reality.imageAlt'))}
                  aria-label={t('common.aria.clickToEnlarge')}
                  data-track="cta_click"
                  data-track-label="problem-image"
                  data-track-dest="modal"
                >
                  <picture>
                    <source media="(max-width: 768px)" srcSet={mobile} />
                    <img
                      src={landscape}
                      alt={t('problem.reality.imageAlt')}
                      className="scenario-image clickable-image"
                      loading="lazy"
                      decoding="async"
                      width="800"
                      height="450"
                    />
                  </picture>
                </button>
              );
            })()}
          </div>
        </div>
      </div>
    </section>
  );
};

export default Problem;
