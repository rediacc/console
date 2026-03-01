import React from 'react';
import { SOLUTION_PAGES, type SolutionCategory } from '../config/solution-pages';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

const CATEGORY_ORDER = [
  'ransomware',
  'multi-cloud',
  'backups',
  'encryption',
  'dev-env',
  'defense',
] as const satisfies readonly SolutionCategory[];

interface WindowWithImageModal extends Window {
  openImageModal?: (src: string, alt: string) => void;
}

interface SolutionsProps {
  lang?: Language;
}

const Solutions: React.FC<SolutionsProps> = ({ lang = 'en' }) => {
  const { t, to } = useTranslation(lang);
  const categories = to('solutions.categories') as Record<string, string>;

  const openImageModal = (src: string, alt: string) => {
    const win = window as WindowWithImageModal;
    if (typeof window !== 'undefined' && win.openImageModal) {
      win.openImageModal(src, alt);
    }
  };

  const grouped = React.useMemo(() => {
    const slugs = Object.keys(SOLUTION_PAGES);
    return CATEGORY_ORDER.map((cat) => ({
      category: cat,
      label: categories[cat] ?? cat,
      pages: slugs
        .filter((slug) => SOLUTION_PAGES[slug].category === cat)
        .map((slug) => {
          const config = SOLUTION_PAGES[slug];
          const content = to(`pages.solutionPages.${config.contentKey}`) as
            | { hero?: { title?: string }; meta?: { description?: string } }
            | undefined;
          return {
            slug,
            title: content?.hero?.title ?? slug,
            description: content?.meta?.description ?? '',
            href: `/${lang}/solutions/${slug}`,
          };
        }),
    }));
  }, [categories, lang, to]);

  return (
    <section className="solutions" id="solutions">
      <div className="container">
        <div className="section-header reveal">
          <h2 className="section-title">{t('solutions.title')}</h2>
          <p className="section-subtitle">{t('solutions.subtitle')}</p>
        </div>
        <div className="solutions-categories reveal">
          {grouped.map((group) => (
            <div key={group.category} className="solutions-category">
              <h3 className="solutions-category-title">{group.label}</h3>
              <div className="solutions-category-grid reveal-stagger">
                {group.pages.map((page) => (
                  <a
                    key={page.slug}
                    href={page.href}
                    className="solution-card solution-card-link reveal"
                  >
                    <h4 className="solution-title">{page.title}</h4>
                    <p className="solution-description">{page.description}</p>
                    <div className="solution-card-footer">
                      <span className="learn-more-link">
                        {t('common.buttons.learnMore')}
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 16 16"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                          aria-hidden="true"
                        >
                          <path
                            d="M6 12l4-4-4-4"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </span>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="solution-illustration">
          <button
            type="button"
            className="image-button"
            onClick={() =>
              openImageModal('/assets/images/solution.svg', t('problem.solution.imageAlt'))
            }
            aria-label={t('common.aria.clickToEnlarge')}
          >
            <img
              src="/assets/images/solution.svg"
              alt={t('problem.solution.imageAlt')}
              className="scenario-image clickable-image"
              loading="lazy"
              decoding="async"
              width="1200"
              height="675"
            />
          </button>
        </div>
      </div>
    </section>
  );
};

export default Solutions;
