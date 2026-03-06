import React from 'react';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import { TEAM_MEMBERS, type TeamMemberMedia } from '../config/team-videos';

interface TestimonialItem {
  role: string;
  quote: string;
}

interface TestimonialsProps {
  lang?: Language;
  /** Team member slug to feature at position 0. Default: 'founder' */
  featuredMember?: string;
}

const Testimonials: React.FC<TestimonialsProps> = ({ lang = 'en', featuredMember = 'founder' }) => {
  const { t, to } = useTranslation(lang);
  const items = to('testimonials.items') as TestimonialItem[];
  const member = TEAM_MEMBERS[featuredMember] as TeamMemberMedia | undefined;
  const founderQuote = t(`team.${featuredMember}.quote`);

  if (items.length === 0) return null;

  return (
    <section className="testimonials" id="testimonials">
      <div className="container">
        <div className="section-header reveal">
          <h2 className="section-title">{t('testimonials.title')}</h2>
          <p className="section-subtitle">{t('testimonials.subtitle')}</p>
        </div>
        <div className="testimonials-grid reveal-stagger">
          {member && founderQuote && (
            <div className="testimonial-card reveal testimonial-card--featured testimonial-card--team">
              <div className="testimonial-team-header">
                <img
                  src={member.photos.headshot}
                  alt={member.name}
                  className="testimonial-team-photo"
                  loading="lazy"
                  decoding="async"
                />
                <div className="testimonial-meta">
                  <span className="testimonial-name">{member.name}</span>
                  <span className="testimonial-role">{member.role}</span>
                </div>
              </div>
              <blockquote className="testimonial-quote">&ldquo;{founderQuote}&rdquo;</blockquote>
            </div>
          )}
          {items.map((item, index) => (
            <div key={`testimonial-${index}`} className="testimonial-card reveal">
              <blockquote className="testimonial-quote">&ldquo;{item.quote}&rdquo;</blockquote>
              <div className="testimonial-author">
                <div className="testimonial-meta">
                  <span className="testimonial-role">{item.role}</span>
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
