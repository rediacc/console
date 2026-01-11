import React from 'react';
import { ConfigProvider, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { Outlet } from 'react-router-dom';
import logoBlack from '@/assets/logo_black.png';
import logoWhite from '@/assets/logo_white.png';
import LanguageSelector from '@/components/common/LanguageSelector';
import { RootState } from '@/store/store';
import { getThemeConfig } from '@/theme';
import { AuthContent, AuthHeader, AuthLayoutBody, AuthLayoutContainer, AuthLayoutRoot } from './styled';

const AuthLayout: React.FC = () => {
  const { t } = useTranslation('common');
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const isDark = themeMode === 'dark';
  const logo = isDark ? logoWhite : logoBlack;

  return (
    <ConfigProvider theme={getThemeConfig(isDark)}>
      <AuthLayoutRoot>
        <AuthLayoutContainer vertical align="stretch" data-testid="auth-layout-container">
        {/* Language selector - top right corner */}
        <AuthHeader>
          <LanguageSelector iconOnly />
        </AuthHeader>

        {/* Content - split screen on desktop */}
        <AuthLayoutBody>
          <AuthContent>
            <Flex vertical align="center" justify="center" gap={32} data-testid="auth-layout-content">
              {/* Logo centered above form */}
              <img src={logo} alt={t('alt.logo')} className="auth-logo" height={40} />
              <Outlet />
            </Flex>
          </AuthContent>
        </AuthLayoutBody>
        </AuthLayoutContainer>
      </AuthLayoutRoot>
    </ConfigProvider>
  );
};

export default AuthLayout;
