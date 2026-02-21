import React from 'react';
import { ConfigProvider, Flex } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { Outlet } from 'react-router-dom';
import LanguageSelector from '@/components/common/LanguageSelector';
import BrandMark from '@/components/layout/BrandMark';
import { RootState } from '@/store/store';
import { getThemeConfig } from '@/theme';

const AuthLayout: React.FC = () => {
  const { t } = useTranslation('common');
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const isDark = themeMode === 'dark';

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
            {/* Shared brand mark keeps logo/text alignment consistent across layouts */}
            <BrandMark
              logoSrc={`${import.meta.env.BASE_URL}favicon.svg`}
              logoAlt={t('alt.logo')}
              showText
              logoSize={36}
              textSize={32}
              className="mb-8"
            />
            <Outlet />
          </Flex>
        </Flex>
      </Flex>
    </ConfigProvider>
  );
};

export default AuthLayout;
