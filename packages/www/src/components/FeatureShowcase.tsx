import React, { useRef, useState, useMemo } from 'react';
import { useTranslation } from '../i18n/react';
import { SOLUTION_PAGES, CATEGORY_ORDER } from '../config/solution-pages';
import { CATEGORY_ICONS } from './CategoryIcons';
import type { Language } from '../i18n/types';
import type { SolutionCategory } from '../config/solution-pages';

interface FeatureShowcaseProps {
  lang?: Language;
}

const FeatureShowcase: React.FC<FeatureShowcaseProps> = ({ lang = 'en' }) => {
  const { t, to } = useTranslation(lang);
  const [activeIndex, setActiveIndex] = useState(0);
  const tabStartRef = useRef(Date.now());

  const categories = useMemo(
    () =>
      CATEGORY_ORDER.map((cat) => {
        const solutions = Object.entries(SOLUTION_PAGES)
          .filter(([, cfg]) => cfg.category === cat)
          .map(([slug, cfg]) => {
            const content = to(`pages.solutionPages.${cfg.contentKey}`) as
              | { hero?: { title?: string } }
              | undefined;
            return { slug, title: content?.hero?.title ?? slug };
          });
        return {
          key: cat,
          label: t(`solutions.categories.${cat}`),
          description: t(`featureShowcase.categoryDescriptions.${cat}`),
          solutions,
          Icon: CATEGORY_ICONS[cat as SolutionCategory],
        };
      }),
    [t, to],
  );

  const active = categories[activeIndex];
  if (!active) return null;

  return (
    <section className="feature-showcase" id="features">
      <div className="container">
        <header className="section-header reveal">
          <h2 className="section-title">{t('featureShowcase.title')}</h2>
          <p className="section-subtitle">{t('featureShowcase.subtitle')}</p>
        </header>
        <div className="feature-tabs reveal">
          <div className="feature-tab-list" role="tablist">
            {categories.map((cat, index) => (
              <button
                key={cat.key}
                type="button"
                role="tab"
                className={`feature-tab${index === activeIndex ? ' feature-tab--active' : ''}`}
                aria-selected={index === activeIndex}
                aria-controls={`feature-panel-${cat.key}`}
                onClick={() => {
                  const elapsed = Math.round((Date.now() - tabStartRef.current) / 1000);
                  const prevTab = categories[activeIndex]?.key;
                  if (elapsed >= 2 && prevTab) {
                    window.plausible?.('feature_tab_dwell', { props: { tab: prevTab, seconds: String(elapsed) } });
                  }
                  tabStartRef.current = Date.now();
                  setActiveIndex(index);
                  window.plausible?.('feature_tab_click', { props: { tab: cat.key } });
                }}
                data-track="cta_click"
                data-track-label="feature-tab"
                data-track-dest={cat.key}
              >
                <cat.Icon size={16} className="feature-tab-icon" />
                {cat.label}
              </button>
            ))}
          </div>
          <div
            className="feature-tab-panel"
            role="tabpanel"
            id={`feature-panel-${active.key}`}
          >
            <p className="feature-tab-description">{active.description}</p>
            <ul className="feature-tab-solutions">
              {active.solutions.map((s) => (
                <li key={s.slug}>
                  <a
                    href={`/${lang}/solutions/${s.slug}`}
                    className="feature-tab-solution-link"
                    data-track="cta_click"
                    data-track-label="feature-solution"
                    data-track-dest={s.slug}
                  >
                    {s.title}
                    <span aria-hidden="true">&rarr;</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
};

export default FeatureShowcase;
