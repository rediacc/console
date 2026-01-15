import React from 'react';
import { App as AntApp, ConfigProvider, Flex } from 'antd';
import arEG from 'antd/locale/ar_EG';
import deDE from 'antd/locale/de_DE';
import enUS from 'antd/locale/en_US';
import esES from 'antd/locale/es_ES';
import frFR from 'antd/locale/fr_FR';
import jaJP from 'antd/locale/ja_JP';
import ruRU from 'antd/locale/ru_RU';
import trTR from 'antd/locale/tr_TR';
import zhCN from 'antd/locale/zh_CN';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';
import { getThemeConfig } from '@/theme';

type AntdLocale = typeof enUS;

const antdLocales: Record<string, AntdLocale> = {
  en: enUS,
  es: esES,
  fr: frFR,
  de: deDE,
  zh: zhCN,
  ja: jaJP,
  ar: arEG,
  tr: trTR,
  ru: ruRU,
};

interface AppProvidersProps {
  children: React.ReactNode;
}

export const AppProviders: React.FC<AppProvidersProps> = ({ children }) => {
  const { i18n } = useTranslation();
  const currentLocale: AntdLocale = antdLocales[i18n.language] ?? enUS;
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const themeConfig = getThemeConfig(themeMode === 'dark');

  return (
    <Flex vertical data-testid="app-providers-container">
      <ConfigProvider
        key={i18n.language}
        locale={currentLocale}
        theme={themeConfig}
        flex={{ className: 'rediacc-flex' }}
      >
        <AntApp>{children}</AntApp>
      </ConfigProvider>
    </Flex>
  );
};
