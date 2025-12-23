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
        {/* Language selector - top right corner */}
        <Flex
          className="auth-header"
          justify="flex-end"
          align="center"
          // eslint-disable-next-line no-restricted-syntax
          style={{ padding: '16px 24px', position: 'absolute', top: 0, right: 0, zIndex: 1 }}
        >
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
            {/* Logo centered above form */}
            <img
              src={logoBlack}
              alt="Rediacc"
              // eslint-disable-next-line no-restricted-syntax
              style={{ height: 40, width: 'auto', objectFit: 'contain', marginBottom: 32 }}
            />
            <Outlet />
          </Flex>
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
