import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';

interface TestimonialItem {
  role: string;
  quote: string;
  name?: string;
  company?: string;
  avatar?: string;
}

interface TestimonialsProps {
  lang?: Language;
}

const Testimonials: React.FC<TestimonialsProps> = ({ lang = 'en' }) => {
  const { t, to } = useTranslation(lang);
  const items = to('testimonials.items') as TestimonialItem[];

  if (items.length === 0) return null;

  return (
    <section className="testimonials" id="testimonials">
      <div className="container">
        <div className="section-header reveal">
          <h2 className="section-title">{t('testimonials.title')}</h2>
          <p className="section-subtitle">{t('testimonials.subtitle')}</p>
        </div>
        <div className="testimonials-grid reveal-stagger">
          {items.map((item, index) => (
            <div key={`testimonial-${index}`} className="testimonial-card reveal">
              <blockquote className="testimonial-quote">&ldquo;{item.quote}&rdquo;</blockquote>
              <div className="testimonial-author">
                {item.avatar ? (
                  <img
                    src={item.avatar}
                    alt=""
                    className="testimonial-avatar-img"
                    width="40"
                    height="40"
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className="testimonial-avatar" aria-hidden="true">
                    {(item.name ?? item.role).charAt(0)}
                  </div>
                )}
                <div className="testimonial-meta">
                  {item.name && <span className="testimonial-name">{item.name}</span>}
                  <span className="testimonial-role">
                    {item.role}
                    {item.company && <>, {item.company}</>}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Testimonials;
