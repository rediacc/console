import React from 'react';
import { ConfigProvider, Flex } from 'antd';
import { Outlet } from 'react-router-dom';
import LanguageSelector from '@/components/common/LanguageSelector';
import { getThemeConfig } from '@/theme';

const AuthLayout: React.FC = () => {
  return (
    <ConfigProvider theme={getThemeConfig(false)}>
      <Flex
        vertical
        // eslint-disable-next-line no-restricted-syntax
        style={{ minHeight: '100vh' }}
        data-testid="auth-layout-container"
      >
        <Flex
          // eslint-disable-next-line no-restricted-syntax
          style={{ position: 'absolute', top: 24, right: 24, zIndex: 1000 }}
          data-testid="auth-layout-controls-wrapper"
        >
          <LanguageSelector iconOnly={true} />
        </Flex>
        <Flex align="center" justify="center" className="flex-1" data-testid="auth-layout-content">
          <Outlet />
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
