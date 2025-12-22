import React from 'react';
import { Flex } from 'antd';
import { Outlet } from 'react-router-dom';
import LanguageSelector from '@/components/common/LanguageSelector';

const AuthLayout: React.FC = () => {
  return (
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
  );
};

export default AuthLayout;
