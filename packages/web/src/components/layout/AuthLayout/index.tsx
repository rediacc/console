import React from 'react';
import { ConfigProvider, Flex } from 'antd';
import { Outlet } from 'react-router-dom';
import logoBlack from '@/assets/logo_black.png';
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
        {/* Header - always visible */}
        <Flex
          className="auth-header"
          justify="space-between"
          align="center"
          // eslint-disable-next-line no-restricted-syntax
          style={{ padding: '16px 24px' }}
        >
          <img
            src={logoBlack}
            alt="Rediacc"
            // eslint-disable-next-line no-restricted-syntax
            style={{ height: 32, width: 'auto', objectFit: 'contain' }}
          />
          <LanguageSelector iconOnly={true} />
        </Flex>

        {/* Content - split screen on desktop */}
        <Flex className="auth-content flex-1">
          <Flex className="auth-branding-panel" />
          <Flex
            vertical
            align="center"
            justify="center"
            className="auth-form-panel flex-1"
            data-testid="auth-layout-content"
          >
            <Outlet />
          </Flex>
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
