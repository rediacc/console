import React, { type ReactNode } from 'react';
import { Alert } from 'antd';

interface DefaultsBannerProps {
  title: string;
  content: ReactNode;
}

export const DefaultsBanner: React.FC<DefaultsBannerProps> = ({ title, content }) => (
  <div>
    <Alert message={title} description={content} type="info" showIcon />
  </div>
);
