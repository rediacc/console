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

const AuthLayout: React.FC = () => {
  const { t } = useTranslation('common');
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const isDark = themeMode === 'dark';
  const logo = isDark ? logoWhite : logoBlack;

  return (
    <ConfigProvider theme={getThemeConfig(isDark)}>
      <Flex vertical className="min-h-screen" data-testid="auth-layout-container">
        {/* Language selector - top right corner */}
        <Flex className="absolute right-0 top-0 z-10 px-6 py-4" justify="flex-end" align="center">
          <LanguageSelector iconOnly />
        </Flex>

        {/* Content - split screen on desktop */}
        <Flex className="flex-1 md:flex-row" vertical>
          <Flex className="hidden flex-1 md:flex" />
          <Flex
            vertical
            align="center"
            justify="center"
            className="flex-1 px-6 py-6 md:px-0 md:py-0"
            data-testid="auth-layout-content"
          >
            {/* Logo centered above form */}
            <img src={logo} alt={t('alt.logo')} className="mb-8 h-10" />
            <Outlet />
          </Flex>
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
