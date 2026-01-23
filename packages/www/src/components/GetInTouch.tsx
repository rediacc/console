import React from 'react';
import { CONTACT_EMAIL } from '../config/constants';

interface GetInTouchProps {
  title: string;
  description: string;
}

const GetInTouch: React.FC<GetInTouchProps> = ({ title, description }) => {
  return (
    <div className="form-notice" role="note" aria-label="Contact information">
      <div className="form-notice-icon" aria-hidden="true">
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </div>
      <div className="form-notice-content">
        <p className="form-notice-title">
          <strong>{title}</strong>
        </p>
        <p className="form-notice-text">
          {description}{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className="form-notice-email">
            {CONTACT_EMAIL}
          </a>
        </p>
      </div>
    </div>
  );
};

export default GetInTouch;
