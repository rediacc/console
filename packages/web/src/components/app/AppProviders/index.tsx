import React from 'react';
import { App as AntApp, ConfigProvider } from 'antd';
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
import { darkTheme, lightTheme } from '@/config/antdTheme';
import { ThemeProvider, useTheme } from '@/context/ThemeContext';
import { ProvidersContainer } from './styles';

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
  const currentLocale: AntdLocale = antdLocales[i18n.language] || enUS;

  return (
    <ThemeProvider>
      <AppProvidersContent currentLocale={currentLocale} language={i18n.language}>
        {children}
      </AppProvidersContent>
    </ThemeProvider>
  );
};

interface AppProvidersContentProps {
  children: React.ReactNode;
  currentLocale: AntdLocale;
  language: string;
}

const AppProvidersContent: React.FC<AppProvidersContentProps> = ({
  children,
  currentLocale,
  language,
}) => {
  const { theme: currentTheme } = useTheme();

  // Select theme configuration based on current theme
  const themeConfig = currentTheme === 'dark' ? darkTheme : lightTheme;

  return (
    <ProvidersContainer data-testid="app-providers-container">
      <ConfigProvider
        key={language} // Force re-render when language changes
        locale={currentLocale}
        theme={themeConfig}
      >
        <AntApp>{children}</AntApp>
      </ConfigProvider>
    </ProvidersContainer>
  );
};
