import React from 'react';
import type { ReactNode } from 'react';
import { DefaultsWrapper, DefaultsAlert } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault/styles';

interface DefaultsBannerProps {
  title: string;
  content: ReactNode;
}

export const DefaultsBanner: React.FC<DefaultsBannerProps> = ({ title, content }) => (
  <DefaultsWrapper>
    <DefaultsAlert message={title} description={content} variant="info" showIcon />
  </DefaultsWrapper>
);
