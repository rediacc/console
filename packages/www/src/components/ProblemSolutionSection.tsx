import React from 'react';
import { generateSectionAnchorId } from '../utils/slug';

interface ProblemSolutionSectionProps {
  number: number;
  title: string;
  subtitle?: string;
  problem: {
    description: string;
    story?: string;
    additionalPoints?: string[];
  };
  solution: {
    title: string;
    description: string;
    benefits: string[];
  };
  variant?: 'light' | 'dark';
  cta?: {
    text: string;
    href: string;
  };
  pageSlug?: string;
}

const LinkIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
);

const ProblemIcon = () => (
  <svg
    width="32"
    height="32"
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2" fill="none" />
    <path d="M16 8v8M16 20h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const SolutionIcon = () => (
  <svg
    width="32"
    height="32"
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2" fill="none" />
    <path
      d="M10 16l4 4 8-8"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const BenefitCheckmark = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      d="M4 10l4 4 8-8"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ProblemSolutionSection: React.FC<ProblemSolutionSectionProps> = ({
  number,
  title,
  subtitle,
  problem,
  solution,
  variant = 'light',
  cta,
  pageSlug,
}) => {
  const anchorId = pageSlug ? generateSectionAnchorId(pageSlug, number, title) : undefined;
  const [copied, setCopied] = React.useState(false);
  const sectionRef = React.useRef<HTMLElement>(null);

  const handleCopyLink = () => {
    if (anchorId && sectionRef.current) {
      const url = `${window.location.origin}${window.location.pathname}#${anchorId}`;
      navigator.clipboard.writeText(url).catch(() => {
        /* ignore clipboard errors */
      });
      setCopied(true);

      // Smooth scroll to section
      sectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });

      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <section ref={sectionRef} className={`problem-solution-section ${variant}`} id={anchorId}>
      <div className="container">
        <div className="section-number">
          <span className="number-badge">{number}</span>
        </div>

        <div className="section-content">
          <div className="section-title-wrapper">
            <h2 className="section-main-title">{title}</h2>
            {anchorId && (
              <button
                type="button"
                onClick={handleCopyLink}
                className="copy-link-button"
                title={copied ? 'Copied!' : 'Copy link to this section'}
                aria-label={`Copy link to ${title} section`}
              >
                <LinkIcon />
                <span className="copy-feedback">{copied ? 'Copied!' : ''}</span>
              </button>
            )}
          </div>
          {subtitle && (
            <p className="section-subtitle" dangerouslySetInnerHTML={{ __html: subtitle }} />
          )}

          {problem.story && (
            <div className="story-box-featured">
              <div className="story-label">Real Story:</div>
              <p className="story-text" dangerouslySetInnerHTML={{ __html: problem.story }} />
            </div>
          )}

          <div className="problem-solution-grid">
            {/* Problem Side */}
            <div className="problem-box">
              <div className="box-header">
                <ProblemIcon />
                <h3 className="box-title">The Problem</h3>
              </div>
              <p className="problem-description">{problem.description}</p>
              {problem.additionalPoints && problem.additionalPoints.length > 0 && (
                <ul className="additional-points">
                  {problem.additionalPoints.map((point, index) => (
                    <li key={index}>{point}</li>
                  ))}
                </ul>
              )}
            </div>

            {/* Solution Side */}
            <div className="solution-box">
              <div className="box-header">
                <SolutionIcon />
                <h3 className="box-title">{solution.title}</h3>
              </div>
              <p className="solution-description">{solution.description}</p>
              <ul className="solution-benefits">
                {solution.benefits.map((benefit, index) => (
                  <li key={index}>
                    <BenefitCheckmark />
                    <span>{benefit}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {cta && (
            <div className="section-cta">
              <a
                href={cta.href}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary btn-large"
              >
                {cta.text}
              </a>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default ProblemSolutionSection;
