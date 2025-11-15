import React from 'react';
import { ConfigProvider, App as AntApp } from 'antd';
import { useTranslation } from 'react-i18next';
import { ThemeProvider, useTheme } from '@/context/ThemeContext';
import { lightTheme, darkTheme } from '@/config/antdTheme';
import enUS from 'antd/locale/en_US';
import esES from 'antd/locale/es_ES';
import frFR from 'antd/locale/fr_FR';
import deDE from 'antd/locale/de_DE';
import zhCN from 'antd/locale/zh_CN';
import jaJP from 'antd/locale/ja_JP';
import arEG from 'antd/locale/ar_EG';
import trTR from 'antd/locale/tr_TR';
import ruRU from 'antd/locale/ru_RU';
import { ProvidersContainer } from './styles'

const antdLocales = {
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
  const currentLocale = antdLocales[i18n.language as keyof typeof antdLocales] || enUS;

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
  currentLocale: any;
  language: string;
}

const AppProvidersContent: React.FC<AppProvidersContentProps> = ({ children, currentLocale, language }) => {
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
        <AntApp>
          {children}
        </AntApp>
      </ConfigProvider>
    </ProvidersContainer>
  );
};
