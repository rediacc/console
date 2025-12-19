import React, { useMemo } from 'react';
import { HomeOutlined, RightOutlined } from '@ant-design/icons';
import { Breadcrumb } from 'antd';

interface BrowserBreadcrumbProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

export const BrowserBreadcrumb: React.FC<BrowserBreadcrumbProps> = ({ currentPath, onNavigate }) => {
  const breadcrumbItems = useMemo(() => {
    const items = [
      {
        title: (
          <span data-testid="file-browser-breadcrumb-home">
            <HomeOutlined />
          </span>
        ),
        onClick: () => onNavigate(''),
      },
    ];

    if (currentPath) {
      const parts = currentPath.split('/').filter(Boolean);
      parts.forEach((part, index) => {
        const path = parts.slice(0, index + 1).join('/');
        items.push({
          title: <span data-testid={`file-browser-breadcrumb-${part}`}>{part}</span>,
          onClick: () => onNavigate(path),
        });
      });
    }

    return items;
  }, [currentPath, onNavigate]);

  if (!currentPath) {
    return null;
  }

  return (
    <Breadcrumb
      items={breadcrumbItems}
      separator={<RightOutlined />}
      data-testid="file-browser-breadcrumb"
    />
  );
};
