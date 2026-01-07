import React, { type ReactNode } from 'react';
import { Alert, Flex } from 'antd';

interface DefaultsBannerProps {
  title: string;
  content: ReactNode;
}

export const DefaultsBanner: React.FC<DefaultsBannerProps> = ({ title, content }) => (
  <Flex>
    <Alert message={title} description={content} type="info" />
  </Flex>
);
