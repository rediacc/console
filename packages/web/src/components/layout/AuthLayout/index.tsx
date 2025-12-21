import React from 'react';
import { Flex, Layout, Space } from 'antd';
import { Outlet } from 'react-router-dom';
import LanguageSelector from '@/components/common/LanguageSelector';
import { ThemeToggle } from '@/components/common/ThemeToggle';

const AuthLayout: React.FC = () => {
  return (
    <Layout style={{ minHeight: '100vh' }} data-testid="auth-layout-container">
      <Flex
        style={{ position: 'absolute', top: 24, right: 24, zIndex: 1000 }}
        data-testid="auth-layout-controls-wrapper"
      >
        <Space size="small">
          <LanguageSelector iconOnly={true} />
          <ThemeToggle data-testid="auth-layout-theme-toggle" />
        </Space>
      </Flex>
      <Layout.Content
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
        data-testid="auth-layout-content"
      >
        <Outlet />
      </Layout.Content>
    </Layout>
  );
};

export default AuthLayout;
