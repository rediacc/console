import { ConfigProvider, Flex } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { Outlet } from 'react-router-dom';
import logoBlack from '@/assets/logo_black.png';
import logoWhite from '@/assets/logo_white.png';
import LanguageSelector from '@/components/common/LanguageSelector';
import { RootState } from '@/store/store';
import { getThemeConfig } from '@/theme';

const AuthLayout: React.FC = () => {
  const { t } = useTranslation('common');
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const isDark = themeMode === 'dark';
  const logo = isDark ? logoWhite : logoBlack;

  return (
    <ConfigProvider theme={getThemeConfig(isDark)}>
      <Flex vertical className="auth-layout" data-testid="auth-layout-container">
        {/* Language selector - top right corner */}
        <Flex className="auth-header" justify="flex-end" align="center">
          <LanguageSelector iconOnly />
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
            <img src={logo} alt={t('alt.logo')} className="auth-logo" />
            <Outlet />
          </Flex>
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
