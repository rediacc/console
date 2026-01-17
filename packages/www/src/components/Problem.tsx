import React from 'react';
import { useTranslation } from '../i18n/react';

interface WindowWithImageModal extends Window {
  openImageModal?: (src: string, alt: string) => void;
}

const Problem: React.FC = () => {
  const { t } = useTranslation();

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
          <div className="scenario-grid">
            <div className="scenario-column">
              <div className="problem-scenario">
                <h3>{t('problem.reality.title')}</h3>
                <div className="scenario-illustration">
                  <img
                    src="/assets/images/problem.svg"
                    alt={t('problem.reality.imageAlt')}
                    className="scenario-image clickable-image"
                    loading="lazy"
                    decoding="async"
                    onClick={() =>
                      openImageModal('/assets/images/problem.svg', t('problem.reality.imageAlt'))
                    }
                  />
                </div>
              </div>
            </div>
            <div className="scenario-column">
              <div className="solution-scenario">
                <h3>{t('problem.solution.title')}</h3>
                <div className="scenario-illustration">
                  <img
                    src="/assets/images/solution.svg"
                    alt={t('problem.solution.imageAlt')}
                    className="scenario-image clickable-image"
                    loading="lazy"
                    decoding="async"
                    onClick={() =>
                      openImageModal('/assets/images/solution.svg', t('problem.solution.imageAlt'))
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Problem;
