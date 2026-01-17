import React from 'react';
import { CONTACT_EMAIL } from '../config/constants';

interface GetInTouchProps {
  title: string;
  description: string;
}

const GetInTouch: React.FC<GetInTouchProps> = ({ title, description }) => {
  return (
    <div className="form-notice">
      <div className="form-notice-icon">ℹ️</div>
      <div className="form-notice-content">
        <h3 className="form-notice-title">{title}</h3>
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
